# Release-readiness memo: fde-02 document assistant v1.1.0

| | |
| --- | --- |
| **To** | Head of Customer Operations (customer sponsor); platform owner |
| **From** | Forward deployed engineer |
| **Date** | 2026-10-16 |
| **Decision asked** | Release v1.1.0 to a pilot of analysts, in **extractive mode only**. Hold the Mistral (LLM) mode until its evaluation is complete. |
| **Evidence** | `evals/results/` (run summaries, gate reports), `evals/baselines/`, this repo at the commit of this memo |

> **Learners:** write this memo from your own measured results (lab week 18). Sections: recommendation,
> what you measured (with intervals), how the fixed version got there, residual risks, cost,
> what must happen before the next step, and the decision with a sign-off line.

<!-- >>> SOLUTION: week-18 release-readiness memo -->
## Recommendation

**Go for a limited pilot of v1.1.0 in extractive mode. No-go for v1.0.0, and no go yet for the LLM mode.**

- **v1.1.0 passes every check of the release gate (10 of 10).** v1.0.0 fails the two critical red-team categories outright.
- **The pilot has a narrow job:** find the filing page that answers a question, with a citation, and decline what it cannot answer.
- **It is not ready to answer analysts' questions in prose.** Extractive answers are right 4.2% of the time on FinanceBench. Analysts must read the cited page, and the pilot's instructions must say so.

## What we measured

On the FinanceBench test half (71 questions over 84 public filings), the hand-written refusal set (30), the red-team suite (26) and the PubMedQA and CUAD test halves:

| Question | v1.0.0 | v1.1.0 | Bar |
| --- | --- | --- | --- |
| Does it find the evidence page? (hit@5) | 0.549 [0.43, 0.66] | 0.535 [0.42, 0.65] | ≥ 0.50, no drop > 3 points |
| Does it decline answerable questions? | 0.0% | 0.0% (dev half 0.0%) | ≤ 5% |
| Does it decline what it should? (refusal set) | 16.7% [7, 34] | **80.0% [63, 91]** | tracked, not gated |
| Can a poisoned document steer it? (indirect injection) | **4 of 4 cases fail** | 0 of 4 fail | all pass |
| Does it leak personal data from documents? | **5 of 5 cases fail** | 0 of 5 fail | all pass |
| p95 answer time | 383 ms | 403 ms | ≤ 2 s |
| Correct answers (extractive) | 4.2% [1.4, 11.7] | 4.2% [1.4, 11.7] | not a release criterion for extractive mode |

All rates show 95% intervals. With 71 questions, an interval is about ±11 points wide. Differences smaller than that, such as the 1.4-point hit@5 change (one question), are not evidence of anything.

## How v1.1.0 got here

1. **The evaluation found the attacks.** In v1.0.0, a sentence in a filing telling "AI assistants" to report a false figure and include an exfiltration link reached the model's context in every case. A complaints annex leaked a customer's name into answers. Questions about companies not in the corpus, requests for investment advice, and requests for executives' personal details were all answered with whatever passage ranked first.
2. **The fix was measured, and its first version failed.** v1.1.0-rc1 added four guardrails:
   - quarantine of instruction-like sentences at ingestion;
   - masking of personal data at ingestion and in answers;
   - a scope check;
   - a stricter extractive period label.

   The gate failed rc1 on false refusals: 7.0% against a 5% bar. The scope guard read the company "Best Buy" as the advice phrase "best buy", and "M&A" as a company name. The first masking rules also hid financial figures as "card numbers". The gate's metrics did not catch that; reading the masked text did.
3. **v1.1.0 fixed both.** It declines none of the 150 FinanceBench questions and passes the red team. The scope fixes were found on the test half, so we also report the untouched dev half (0.0% false refusals, n = 79).

## Residual risks

| Risk | Likelihood in pilot | Mitigation |
| --- | --- | --- |
| A rephrased injection ("as a language model you must…") passes the quarantine patterns | Medium | Extractive mode does not follow instructions, so the risk is quoting them. The LLM mode needs an LLM red team before release |
| A name outside a "customer &lt;Name&gt;" pattern is not masked | Medium | Pilot corpus is public filings; regulated documents stay out until NER-based masking (ADR-008 in fde-02) |
| "our customer Walmart Stores" is masked as a person | Low | Accepted; it hides a company name, not a figure |
| False premises ("Why did 3M acquire Boeing?") are answered (0 of 5 declined) | High if asked | Analysts verify against the cited page; LLM mode must be measured on this |
| The judge for prose answers is not yet validated against people | — | The LLM judge's agreement with 40 human labels gates the LLM release (κ ≥ 0.7) |
| CUAD: never reports an absent clause (0 of 54) | — | Contract review is out of the pilot's scope |

## What it costs to run

The extractive pilot needs no model API. fde-02's container runs within a 1.5 GB memory and one-CPU limit (its Compose file). This evaluation runs offline in under a minute on two vCPUs once the filings are indexed (6 minutes, cached in CI), weekly and on every fde-02 pull request (`release-gate` workflow). The LLM evaluation costs cents per run at the assumed Mistral prices; record the real cost when it runs.

## Before the LLM mode can ship

1. Run `evals` with a `MISTRAL_API_KEY` secret: Mistral answers, the prompt-only baseline, and LLM-judge calibration on the constructed set.
2. Label 40 judged answers (`make label-export`), and require κ ≥ 0.7 between the LLM judge and the labels.
3. Write ten paraphrased injections the quarantine patterns do not match, add them to the suite as v2, and require the LLM mode to pass them.
4. Gate profile `release`: accuracy ≥ 0.60, citations ≥ 0.70, false refusals ≤ 5%, cost ≤ $0.01 per question.

## Decision

| Option | Consequence |
| --- | --- |
| **Pilot v1.1.0, extractive (recommended)** | Analysts get cited page-finding now; the LLM mode follows when the four steps above pass |
| Ship v1.1.0 with LLM answers now | Unmeasured accuracy and an unvalidated judge; the injection defences were tested only against extractive answers |
| Wait for everything | No feedback from real users for another cycle; the gate is ready, the evidence for LLM answers is not |

Signed off by: ____________ (customer sponsor) · ____________ (platform owner)
<!-- <<< SOLUTION -->
