"""Release gate: absolute thresholds, regression against a baseline run, red-team rules and
judge calibration. CI runs it and fails the job when any check fails."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from rag_eval.metrics import bootstrap_diff_ci


@dataclass
class GateCheck:
    name: str
    passed: bool
    observed: float | None
    threshold: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def load_gate(path: Path, profile: str) -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if profile not in cfg["profiles"]:
        raise ValueError(f"unknown gate profile {profile!r}; have {sorted(cfg['profiles'])}")
    return cfg["profiles"][profile]


def lookup(summary: dict, dotted: str) -> float | None:
    """summary["a"]["b"] for "a.b"; None when any part is missing or null."""
    value = summary
    for part in dotted.split("."):
        if not isinstance(value, dict) or value.get(part) is None:
            return None
        value = value[part]
    return float(value) if isinstance(value, (int, float)) else None


def _metric_values(rows: list[dict], metric: str) -> dict[str, float]:
    return {r["id"]: float(bool(r[metric])) for r in rows if r.get(metric) is not None}


def check_gate(cfg: dict, summary: dict, *, current_rows: list[dict] | None = None,
               baseline_rows: list[dict] | None = None, redteam: dict | None = None,
               calibration: dict | None = None) -> list[GateCheck]:
    """Evaluate every rule in a gate profile.

    1. cfg["thresholds"]: a list of {"metric": dotted path into summary, "min" or "max"}.
       A missing metric (None) fails with detail "missing".
    2. cfg["regression"] = {"metrics": [...], "max_drop": d}: for each metric, pair the
       baseline and current rows by id (cases present in both), run bootstrap_diff_ci(base,
       current) and fail when observed < −max_drop or the CI upper bound < 0 (a significant
       drop). Skip with a passing check, detail "no baseline", when either row list is None.
    3. cfg["redteam"] = {"critical_min": x, "overall_min": y}: every category whose severity
       is "critical" needs pass_rate ≥ critical_min; the overall pass_rate ≥ overall_min.
       Missing red-team results fail.
    4. cfg["judge"] = {"kappa_min": k}: calibration["kappa"] ≥ k. Missing calibration fails.
    Sections absent from cfg are not checked.
    """
    checks: list[GateCheck] = []
    # >>> SOLUTION: week-18 release gate
    for rule in cfg.get("thresholds", []):
        value = lookup(summary, rule["metric"])
        if "min" in rule:
            ok, bound = value is not None and value >= rule["min"], f">= {rule['min']}"
        else:
            ok, bound = value is not None and value <= rule["max"], f"<= {rule['max']}"
        checks.append(GateCheck(rule["metric"], ok, value, bound,
                                "missing" if value is None else ""))

    reg = cfg.get("regression")
    if reg:
        for metric in reg["metrics"]:
            name = f"regression:{metric}"
            if current_rows is None or baseline_rows is None:
                checks.append(GateCheck(name, True, None, "", "no baseline"))
                continue
            base, cur = _metric_values(baseline_rows, metric), _metric_values(current_rows, metric)
            ids = sorted(base.keys() & cur.keys())
            if not ids:
                checks.append(GateCheck(name, False, None, "", "no shared cases"))
                continue
            observed, lower, upper = bootstrap_diff_ci([base[i] for i in ids],
                                                       [cur[i] for i in ids])
            ok = observed >= -reg["max_drop"] and upper >= 0
            checks.append(GateCheck(name, ok, round(observed, 4),
                                    f"drop <= {reg['max_drop']} and CI upper >= 0",
                                    f"n={len(ids)} ci95=[{lower:.4f}, {upper:.4f}]"))

    rt = cfg.get("redteam")
    if rt:
        if redteam is None:
            checks.append(GateCheck("redteam", False, None, "", "missing"))
        else:
            for cat, res in sorted(redteam["categories"].items()):
                if res["severity"] == "critical":
                    ok = res["pass_rate"] >= rt["critical_min"]
                    checks.append(GateCheck(f"redteam:{cat}", ok, res["pass_rate"],
                                            f">= {rt['critical_min']}",
                                            ", ".join(res["failures"])))
            overall = redteam["pass_rate"]
            checks.append(GateCheck("redteam:overall", overall >= rt["overall_min"], overall,
                                    f">= {rt['overall_min']}"))

    jd = cfg.get("judge")
    if jd:
        kappa = calibration.get("kappa") if calibration else None
        checks.append(GateCheck("judge:kappa", kappa is not None and kappa >= jd["kappa_min"],
                                kappa, f">= {jd['kappa_min']}",
                                "" if kappa is not None else "missing"))
    # <<< SOLUTION
    return checks


def render(checks: list[GateCheck]) -> str:
    lines = ["| Check | Result | Observed | Threshold | Detail |",
             "| --- | --- | --- | --- | --- |"]
    for c in checks:
        observed = "—" if c.observed is None else f"{c.observed:.4g}"
        lines.append(f"| {c.name} | {'pass' if c.passed else '**FAIL**'} | {observed} | "
                     f"{c.threshold} | {c.detail} |")
    verdict = "PASS" if all(c.passed for c in checks) else "FAIL"
    return f"**Gate: {verdict}** ({sum(c.passed for c in checks)}/{len(checks)} checks)\n\n" \
        + "\n".join(lines)
