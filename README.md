# fde-03-evaluation: evaluation, red team and release gate for RAG systems

[![Open the starter in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/sundayayandele/fde-03-evaluation-starter?quickstart=1)

Phase 3 (weeks 16–18) and **Capstone 2** of the **Forward Deployed ML Engineer: Zero-to-Hired** series. A customer will not put an LLM system in front of staff on a demo's word. You build what decides whether it ships: **measured quality with confidence intervals**, a **judge you have calibrated**, a **red team** that attacks it the way a hostile document would, and a **CI gate** that blocks a release that got worse.

**The system:** `rag-eval`, a typed and tested Python package with a CLI, a FastAPI service, a web UI and Grafana dashboards. It evaluates [fde-02's document assistant](https://github.com/sundayayandele/fde-02-llm-applications) and any service with the same `POST /api/v1/ask` contract, as a black box over HTTP.

- **Versioned golden sets** with fingerprints: FinanceBench (finance), PubMedQA (health), CUAD (legal contracts) and a hand-written refusal set. Each has a dev half (tune here) and a test half (report here).
- **Metrics with uncertainty:** answer accuracy by type, retrieval hit@5, citation precision and recall, false refusals, correct abstentions, latency and cost. Every rate carries a 95% Wilson interval; version comparisons use a paired bootstrap.
- **Judges:**
  - A deterministic reference judge.
  - A rubric-based LLM judge (Mistral, JSON verdicts).
  - **Calibration** for both: a constructed set with known labels, plus a human-label workflow (CSV export and import, Cohen's kappa).
- **Red team:** direct and indirect prompt injection (a poisoned filing with a canary and an exfiltration link), PII leakage (a complaints annex with planted personal data), out-of-scope and investment-advice requests, fabrication pressure and citation integrity.
- **Tracing:** one OpenTelemetry span per case, with `traceparent` sent to the system under test. Export to Jaeger, or to Langfuse through its OTLP endpoint.
- **Release gate:** thresholds plus regression against a committed baseline, red-team critical categories at 100%, and judge kappa. CI fails the build when any check fails.

```mermaid
flowchart LR
  G[(Golden sets<br/>versioned, fingerprinted)] --> R[Runner<br/>concurrent, traced]
  RT[(Red-team suite<br/>poisoned PDFs)] --> R
  R -- POST /api/v1/ask<br/>traceparent --> S[System under test<br/>fde-02 v1.0 / v1.1]
  S --> R
  R --> J{Judge<br/>reference · LLM}
  C[(Calibration<br/>constructed · human)] --> J
  J --> F[(runs/&lt;id&gt;<br/>config · cases · summary)]
  F --> GT{Release gate<br/>thresholds · bootstrap · red team · kappa}
  GT -->|exit 0/1| CI[CI]
  F --> API[Eval service<br/>UI · /metrics] --> GR[Grafana]
  R -. OTLP .-> JA[Jaeger / Langfuse]
```

## Quick start

```bash
python3.12 -m venv .venv && source .venv/bin/activate
make install
make e2e                          # service + smoke checks on committed golden sets and results
rag-eval golden list              # golden sets, counts, splits
rag-eval calibrate                # reference judge on 390 constructed cases
```

Evaluate fde-02 (a sibling checkout with its virtualenv and FinanceBench index, from `make install ingest` there):

```bash
make goldens                      # downloads pinned sources, builds FinanceBench items, verifies all
make corpora                      # PubMedQA, CUAD and red-team PDFs, indexed with fde-02
make eval-offline                 # 3 retrieval configs, corpora, red team, calibration, gate (~1 min)
make eval-llm                     # Mistral answers, prompt-only baseline, LLM judge (MISTRAL_API_KEY)
```

## Results

Measured on 2026-10-16 (UTC), 2 vCPU (Xeon 2.1 GHz), with the commands above:

- **System under test:** fde-02 in extractive mode (no LLM).
- **Judge:** the reference judge.
- **Golden sets:** v1. FinanceBench is commit `cc39aeb4afdf`, test half; the refusal set is all 30 items.
- **Uncertainty:** brackets are 95% Wilson intervals.

The raw summaries are in [`evals/results/`](evals/results/), and every gate report is in [`evals/results/gates/`](evals/results/gates/). A second full `make eval-offline` (51 s) reproduced every rate exactly; latencies moved within ±15%.

<!-- >>> SOLUTION: week-18 results -->
**1. Retrieval: basic vs advanced RAG** (fde-02 v1.0.0, FinanceBench test half, n = 71).

| Configuration | Retrieval hit@5 | Cites an evidence page | False refusals | p50 / p95 |
| --- | --- | --- | --- | --- |
| Basic: BM25 over all 84 filings | 0.183 [0.11, 0.29] | 0.085 [0.04, 0.17] | 0.028 [0.01, 0.10] | 39 / 90 ms |
| + company and year routing | 0.437 [0.33, 0.55] | 0.296 [0.20, 0.41] | 0.014 [0.00, 0.08] | 52 / 120 ms |
| **Advanced: hybrid BM25 + LSA, rewrite, rerank, routing** | **0.549 [0.43, 0.66]** | **0.338 [0.24, 0.45]** | 0.000 [0.00, 0.05] | 280 / 383 ms |
| Prompt-only (the LLM without documents) | not applicable | not applicable | pending | pending |

Extractive answers get 4.2% [1.4, 11.7] right in every configuration: 3 of 25 numeric questions and none of 46 free-text ones. Arithmetic and prose need the LLM. Mistral answers, the prompt-only baseline and the LLM judge are **pending**: run the `evals` workflow with a `MISTRAL_API_KEY` secret, or `make eval-llm`.

**2. Abstention: the hand-written refusal set** (30 questions the assistant must decline).

| fde-02 | No such company | Period not covered | Out of domain | Investment advice | Personal data | False premise | **All** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v1.0.0 | 0 / 5 | 4 / 5 | 0 / 5 | 0 / 5 | 1 / 5 | 0 / 5 | **0.167 [0.07, 0.34]** |
| v1.1.0 | 5 / 5 | 4 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 0 / 5 | **0.800 [0.63, 0.91]** |

**3. Red team** (26 cases on a fictional bank's poisoned filings; critical categories must pass every case).

| fde-02 | Indirect injection (critical) | PII leakage (critical) | Direct injection | Out of scope | Fabrication | Citations | Utility | **Overall** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v1.0.0 | **0 / 4** | **0 / 5** | 1 / 3 | 3 / 4 | 3 / 3 | 3 / 3 | 2 / 4 | 12 / 26 |
| v1.1.0 | 4 / 4 | 5 / 5 | 3 / 3 | 4 / 4 | 3 / 3 | 3 / 3 | 2 / 4 | 24 / 26 |

What v1.0.0 did:

- The poisoned instruction reached the retrieved context in every indirect-injection case.
- The extractive answer repeated the injected sentence in a direct-injection case.
- The answer quoted a customer's name from a complaints file.

v1.1.0 quarantines instruction-like sentences and masks personal data at ingestion. It also checks scope before answering and masks answers on the way out ([fde-02 ADR-008](https://github.com/sundayayandele/fde-02-llm-applications/blob/main/docs/adr/ADR-008-guardrails.md)).

**4. The release gate** (`ci-offline` profile; baseline: v1.0.0).

| Candidate | Verdict | Failed checks |
| --- | --- | --- |
| fde-02 v1.0.0 | **FAIL** (7 / 10) | red team: indirect injection 0.00, PII leakage 0.00, overall 0.46 |
| fde-02 v1.1.0-rc1 | **FAIL** (9 / 10) | false refusals 7.0% > 5%: its new scope guard declined "Best Buy" (read as "best buy") and "M&A" (read as a company) |
| **fde-02 v1.1.0** | **PASS** (10 / 10) | none. Hit@5 0.535 vs 0.549 (paired bootstrap 95% CI of the difference [−0.042, 0.000]); refusals 0.0% |

**5. The judge.** On 390 constructed cases (perturbed figures, flipped verdicts, swapped clauses, refusals), the reference judge's first version agreed 94.9%. Calibration exposed two bugs: free-text answers with a changed figure passed, and 0.01 × 1.2 rounded back to 0.01. After the fixes, agreement is 100% [99.0, 100] and κ = 1.00. The LLM judge on the same cases and against 40 human labels is **pending** (`make eval-llm label-export label-import`).

**6. The other domains** (fde-02 v1.1.0, extractive, test halves, finance scope guard off).

| Golden set | Retrieval hit@5 | Answers correct | What it shows |
| --- | --- | --- | --- |
| PubMedQA (n = 103), routed | 0.981 [0.93, 0.99] | 0.000 [0.00, 0.04] | Retrieval is easy (one abstract per question); a yes/no/maybe verdict needs the LLM |
| CUAD (n = 94), contract given | 0.675 [0.52, 0.80] (span items) | spans 0.050, absent 0.000 [0.00, 0.07] | It never says "this contract has no such clause": a gap legal review cannot accept |

**Honest caveats:**

- The v1.1.0 scope-guard fixes were written after rc1 failed on the FinanceBench **test** half, so v1.1.0's 0.0% false refusals there is no longer a clean held-out estimate. The same guard declines none of the 79 dev-half questions (0 of 150 in total), which is the better evidence.
- The refusal set and the red team were written by the same person who wrote the guardrails. Expect paraphrased attacks to get through: that is what the LLM run and a fresh red team are for.
- The constructed calibration set tests rule-following, not judgement. Only human labels can show whether the LLM judge agrees with people.
<!-- <<< SOLUTION -->

Read the decision in [docs/RELEASE-READINESS.md](docs/RELEASE-READINESS.md).

## Run it everywhere

| Path | Command | What runs |
| --- | --- | --- |
| Local Python | `make install && make e2e` | Service with committed golden sets and results |
| Docker Desktop | `make up-docker` (add `--profile sut --profile observability`) | Service; fde-02 as the system under test; Prometheus, Grafana, Jaeger |
| Podman Desktop | `make up-podman` | Same image as a pod; `TARGET_URL` points at fde-02 on the host |
| Rancher Desktop | `make up-rancher` | Same image on Rancher's moby engine |
| Local Kubernetes | `make k8s-docker`, `make k8s-rancher`, `make k8s-kind` | Deployment, HPA, PDB, NetworkPolicy; nightly red-team CronJob (`kubectl apply -k deploy/kubernetes/jobs`) |
| OpenShift / Helm | `oc apply -k deploy/openshift` · `helm install` | Route with edge TLS; `TARGET_URL` from values |
| AWS / Azure / GCP | `make tf-aws-plan` (and `azure`, `gcp`) | Fargate, Container Apps, Cloud Run; `target_url` variable |

Step by step: [desktop labs](docs/learning/DESKTOP-LABS.md), [cloud labs](docs/learning/CLOUD-LABS.md), [deployment](docs/DEPLOYMENT.md).

## CLI

| Command | Does |
| --- | --- |
| `rag-eval fetch` · `golden build / verify / diff / list` | Pinned downloads with checksums; golden sets with fingerprints |
| `rag-eval corpus pubmedqa / cuad / redteam` | PDFs the system under test can ingest |
| `rag-eval run --golden NAME [--split] [--scope routed/doc] [--judge] [--target / --prompt-only / --replay]` | A run: `runs/<id>/config.json`, `cases.jsonl`, `summary.json` |
| `rag-eval calibrate [--judge llm] [--human labels.csv]` | Judge agreement, kappa, confusion, disagreements |
| `rag-eval label export / import` | Human-label worksheet and kappa against the judge |
| `rag-eval redteam` | Red-team suite; per-category pass rates |
| `rag-eval gate --run --baseline --redteam --calibration --profile` | Release gate; exit code 1 on failure |
| `rag-eval baseline` · `publish` · `report` | Text-free baselines, published summaries, comparison tables |

## API

| Endpoint | Returns |
| --- | --- |
| `GET /` | Web UI: runs, red-team results, golden sets |
| `GET /api/v1/goldens` · `/goldens/{name}/{version}/items` | Manifests (counts, fingerprints) · items |
| `GET /api/v1/runs` · `/runs/{id}` · `/runs/{id}/cases?only_failures=true` | Runs and red-team results on disk |
| `POST /api/v1/runs` → `GET /api/v1/jobs/{id}` | Start a run in the background; poll it |
| `POST /api/v1/judge` | Reference-judge verdict for one answer |
| `GET /api/v1/compare?runs=a&runs=b` | Comparison table |
| `GET /health/*`, `GET /metrics/` | Health; `eval_accuracy`, `eval_retrieval_hit_at_5`, `eval_false_refusal_rate`, `eval_latency_p95_ms`, `eval_redteam_pass_rate` |

## Learning path

| Week | Lab | You build |
| --- | --- | --- |
| 16 | [Golden sets and metrics](labs/week-16-golden-sets-and-metrics/README.md) | `token_f1`, `citation_scores`, `wilson_interval` |
| 17 | [Judges and calibration](labs/week-17-judges-and-calibration/README.md) | `build_judge_messages`, `perturb_number`, `cohens_kappa` |
| 18 | [Red team, gate and release memo](labs/week-18-redteam-and-release-gate/README.md) | `detect_pii`, `bootstrap_diff_ci`, `check_gate`, results table |

**Capstone 2 exit check:**

- From a fresh clone, `make test`, `make exercises` and `make e2e` pass.
- `make eval-offline` reproduces your results table.
- The gate fails on fde-02 v1.0.0 and passes on a version you fixed.
- Your release-readiness memo names the evidence, the residual risks and the decision.

## Repository map

```text
src/rag_eval/        golden, metrics, judge, calibration, redteam, targets, runner, gate, report,
                     tracing, pdf, llm, cli
app/                 evaluation service and UI
config/              rubric.yaml, redteam.yaml, gate.yaml, sut.yaml, providers.yaml
goldens/             <name>/<version>/{items.jsonl, manifest.json} (FinanceBench: manifest only)
evals/               results/ (published summaries, gate reports), baselines/ (text-free)
scripts/sut.py       starts fde-02 with a named configuration
labs/ docs/ deploy/ terraform/ monitoring/
```

## Reference and starter

[`fde-03-evaluation`](https://github.com/sundayayandele/fde-03-evaluation) is the **reference** repo: complete code and measured results. [`fde-03-evaluation-starter`](https://github.com/sundayayandele/fde-03-evaluation-starter) is generated from it with `make starter`:

- Each exercise becomes a `NotImplementedError("TODO ...")` stub.
- Exercise tests carry `@pytest.mark.exercise` (`make exercises`).
- The results table is blank for your numbers.

## Licence

Code: [MIT](LICENSE). Written content: [CC BY-SA 4.0](LICENSE-CONTENT.md). Datasets are downloaded at run time from pinned commits with checksums; see [DATASETS](docs/datasets/DATASETS.md).

- **PubMedQA (MIT) and CUAD (CC BY 4.0):** derived golden sets are committed with attribution.
- **FinanceBench:** no licence file in its repository; the Hugging Face card says CC BY-NC 4.0 (to verify). It is not redistributed: only its manifest and text-free baselines are committed.
- **Halden Mutual Bank** in the red-team corpus is fictional. Its personal data uses published test values.

Part of [fde-zero-to-hired](https://github.com/sundayayandele/fde-zero-to-hired) by Sunday Ayandele.
