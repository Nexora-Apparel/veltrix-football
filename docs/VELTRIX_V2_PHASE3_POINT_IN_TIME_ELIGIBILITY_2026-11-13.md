# VELTRIX FOOTBALL 2.0 — Historical Data Eligibility Assessment

**Assessment date:** 2026-11-13  
**Dataset:** 5DollarFootballAPI Community account, seven approved competitions  
**Staging import:** import_run_id=1; 2,496 fixture/result observations; 28 exact raw provider responses  
**Import manifest SHA-256:** `50b785f7594a2a4db29927b33f0ea68eb68b0177fc3914939b3c1df224bc771d`  
**Audit:** PASS; audit SHA-256 `ad0f7d60886807b4863c02eb15de7688e9aa84246ccaf89c763d32a59ea04a49`

## 1. Decision

The imported dataset is accepted as a traceable historical **settled-result label archive** within the recorded provider rights scope. It is **not accepted as a point-in-time feature archive** and must not be used to claim leakage-free historical prediction performance.

The audit verifies integrity and provenance of the bytes acquired during the 2026 import. It does not establish when the provider first published each historical fixture field or result.

## 2. Verified facts

- 2,496 fixtures were seen and inserted; 2,496 source observations and 2,496 result versions are linked.
- 28 provider responses are archived with exact response-byte hashes.
- Raw response, canonical payload, response linkage, rights provenance, result linkage, and reconciliation checks passed.
- The source approval is tied to the seven account-entitled competition IDs and the reviewed terms evidence document.
- The source's result-publication timestamp is not supplied in the acquired historical response.
- The stored four-day post-kickoff availability value is a conservative proxy only. Every imported observation has `point_in_time_certifiable=false`.
- The audit reports zero failures, zero quarantined rows, and zero open quarantine records.

## 3. Field/use eligibility

| Data class | Permitted treatment | Prohibited treatment |
|---|---|---|
| Final home/away scores | Supervised target labels; result reconciliation; descriptive historical reporting | Pre-kickoff input, feature, or predictor |
| Derived 1X2 outcome, BTTS, totals | Labels derived strictly from final scores | Historical features or evidence that a market outcome was knowable before kickoff |
| Provider fixture ID and team/competition IDs | Identity, deduplication, joins, grouping and audit keys | Predictive signal by themselves |
| Team names, competition names, kickoff timestamp | Display, grouping, schedule identity and joins, with provenance caveat | Assume historical values were frozen as-of kickoff without dated snapshots |
| Four-day availability proxy | Conservative archival bookkeeping and explicit exclusion logic | Exact source publication time, feature availability time, or point-in-time proof |
| Odds, lineups, injuries, xG, shots, PPDA, player availability, weather, travel/fatigue | Not present as certified historical features in this import | Any backtest feature claim based on this import |

## 4. Model-training boundary

1. Do not train or evaluate a historical pre-match model using the imported post-match payload as a feature matrix.
2. Final scores may be joined as labels to independently sourced features only when each feature has verifiable event/publication timestamps no later than the prediction cutoff.
3. A missing timestamp is not repaired by inference, current web pages, or the four-day proxy.
4. A feature snapshot fetched after kickoff is ineligible for that fixture's pre-match evaluation, even if the value appears static.
5. Historical joins must be one-to-one by stable provider/team/competition identity and kickoff; ambiguous joins are quarantined, not guessed.
6. Chronological splits must be by kickoff date, with no random split and no post-cutoff corrections leaking into an earlier fold.
7. This import cannot satisfy the 1,000-match walk-forward threshold, the 300 prospective settled-selection threshold, odds timestamp coverage, or bookmaker benchmark requirements on its own.

## 5. Required evidence for future features

Every candidate feature source must provide and persist:
- exact raw response bytes and SHA-256;
- provider/source identity, endpoint, request parameters with secrets removed, HTTP status and retrieval timestamp;
- source event/publication timestamp or a documented provider guarantee sufficient to establish availability;
- point-in-time cutoff policy and feature-specific availability rule;
- explicit source-rights approval for collection, storage, model training and any public display;
- stable entity IDs and deterministic fixture/team mapping;
- revision/correction handling that preserves prior observations instead of overwriting them.

For odds, additionally require bookmaker identity, market/selection/line, decimal price, quote timestamp, and proof that the quote predates kickoff. Untimestamped odds are not benchmark evidence.

## 6. Release gate

**Historical label archive:** PASS for the 2,496 imported records, subject to the source and retention limitations recorded in the rights review.

**Historical point-in-time features:** FAIL / NOT AVAILABLE from this dataset.

**Prediction-model historical backtest readiness:** NOT YET ESTABLISHED. It requires separately acquired, rights-approved, point-in-time feature data and a validated label join.

**Prospective paper-trading readiness:** NOT YET ESTABLISHED. It requires timestamped pre-kickoff feature and odds capture, frozen predictions, and later result settlement.

No prediction engine, production publication, Telegram delivery, scheduled report, or value-bet market is authorized by this assessment. Phase 4 may begin only with a new, independent feature-source qualification and point-in-time capture design; the legacy prediction stack remains excluded.
