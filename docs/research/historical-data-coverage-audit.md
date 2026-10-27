# Veltrix Football: Historical Data Coverage and Validation Audit

**Research date:** 2026-10-27  
**Repository reviewed:** https://github.com/Nexora-Apparel/veltrix-football  
**Purpose:** establish what is known, what is not yet proven, and the fastest evidence-based remediation sequence. This is a research note, not a claim that the dataset has already been repaired.

## Executive finding

Veltrix's history should currently be treated as **potentially useful but not proven complete**. The repository README describes an imported dataset of 70,444 matches across 38 division codes from 2020-01-01 through 2026-10-24, and elsewhere records a much larger historical evaluation through 2026-09-03. These are dated snapshots/configured import windows, not a live audit of the deployed dataset. The actual minimum/maximum match date, duplicate count, per-season coverage, and unresolved date gaps in the current deployed data were not independently verified in this research pass because the raw CSV is not committed in the repository and the workflow output is a temporary artifact.

The upstream Club-Football-Match-Data repository currently describes **238,858 records across 38 league/division codes**, spanning the 2000/01 season through 2026-09-03. Veltrix's importer command in the README deliberately requests records from 2020-01-01, so Veltrix's intended imported range is narrower than the upstream dataset's stated range. The upstream source's overall row count must not be confused with Veltrix's imported or production row count.

## Findings supported by primary sources

### 1. Dataset sources and intended date range

- Veltrix README documents importing Club-Football-Match-Data (https://github.com/xgabora/Club-Football-Match-Data) with --from 2020-01-01, validating rows, skipping malformed rows, and deduplicating by competition/date/home/away.
- The same README records a successful import snapshot on 2026-10-24: **70,444 completed matches, 38 competition codes, 2020-01-01 through 2026-10-24, one malformed row skipped**. This is a historical run summary, not proof that the current deployed data still contains exactly those rows.
- Upstream Club-Football-Match-Data's README describes 238,858 match records in 38 divisions and a latest match date of 2026-09-03. It says results/statistics/odds are sourced from Football-Data.co.uk and Elo data from ClubElo. Its stated coverage and row count can change as that repository is updated.
- Veltrix's importer also contains a supplemental football-data.co.uk path for a defined set of divisions and current-season results. That supplement can extend recent coverage, but it is not evidence of complete coverage across all countries, competitions, or seasons.

**Conclusion:** the phrase “2020–present” is the intended Veltrix import window, not proof that every date or every competition in that interval is covered. We must measure the actual imported file.

### 2. API-Football cannot be assumed to fill every gap

The official API-Football documentation (https://www.api-football.com/documentation_v3) states that competition coverage varies by season and feature, and that a feature marked available does **not** guarantee 100% data availability. The documentation also exposes available seasons and competition-specific coverage, which should be inspected before scheduling bulk history requests.

The official API-Football pricing page (https://www.api-football.com/pricing) lists the Free plan at **100 requests/day** and says Free plans are limited in available seasons. Veltrix's README likewise says historical retention and availability depend on the subscription. With a 100-request daily allowance, a one-request-per-day historical scan is costly and slow: 365 calendar dates would require at least 365 requests before retries or other daily fixture/odds work. A plan/subscription denial must be recorded as unresolved, not reported as a successful empty day or as complete history.

### 3. Current safeguards and known validation state

- The README says the recent-goals Poisson pipeline underperformed the de-vigged market on the reported same-fixture comparison: Poisson Brier 0.6443 vs market 0.6003, log loss 1.0684 vs 1.0037; the competition Elo alternative also underperformed the market on those metrics (Elo Brier 0.6192 vs market 0.6002; log loss 1.0313 vs 1.0036).
- The README's recent Elo holdout also underperformed the market (Elo accuracy 48.98%, Brier 0.6137, log loss 1.0232; market accuracy 50.69%, Brier 0.5980, log loss 1.0004).
- The README explicitly states that historical odds timestamps/closing-line quality have not been verified and that betting/value alerts should remain disabled. This is the correct safety posture until stronger validation exists.
- The README documents a walk-forward backtest command and says same-day predictions are made before same-day results are ingested. These are useful safeguards, but the reported metrics still need reproducible runs on the exact dataset version being deployed.
- The recent-results module queries bounded date ranges and marks incomplete refreshes as partial/unavailable. Incremental gap retry state exists in the code path, but the actual production cache and its current unresolved gap ledger were not available for independent inspection in this research pass.

## Highest-priority remediation

### P0 — Produce a deterministic audit of the actual CSV

Run the audit against the exact CSV used for backtesting and/or production—not the upstream README and not an old report. Publish a machine-readable JSON plus a human-readable Markdown summary containing:

- dataset SHA-256, byte size, generation time, source/version, and import arguments;
- row count before/after normalization, malformed-row count, duplicate count, and conflict count;
- actual minimum and maximum match dates;
- counts by year, division/competition, and division-season;
- calendar-date gaps only where the competition schedule makes a gap meaningful; do not treat every no-match day as missing data;
- per-division season completeness compared with upstream/source schedules where available;
- missing outcome/odds/feature rates and source provenance;
- unresolved API-Football dates with error class/reason, attempt count, and next retry time.

The report must distinguish **no matches scheduled**, **provider returned zero fixtures**, **request failed**, **season unsupported by subscription**, and **data not checked**. These are not interchangeable states.

### P1 — Repair the gap ledger and retry policy

1. Keep a durable gap ledger separate from the forward freshness cursor.
2. Retry only dates/ranges that failed or were incomplete, with bounded exponential backoff and a strict daily request budget.
3. Inspect competition/season availability first, then stop retrying dates known to be outside the account's available historical seasons.
4. Do not mark a range complete solely because the HTTP response was 200; verify the response shape, fixture statuses, and requested date bounds.
5. Keep coverage status as GAPPED/PARTIAL while unresolved required ranges remain. Surface the reason in the dashboard/report.
6. Avoid spending requests repeatedly on known subscription/plan errors; route those dates to a compatible public source where licensing and schema quality permit.

### P2 — Establish an auditable backtest

- Pin each backtest to a dataset hash and a fixed date range.
- Use chronological walk-forward splits; ensure every feature (including form, Elo, odds, and rolling statistics) is available as of prediction time.
- Test a recent untouched holdout and report results by competition and season, not only aggregate results.
- Compare each model with a de-vigged bookmaker baseline on the **same fixtures**, and disclose odds timestamp/closing-line limitations.
- Report Brier score, log loss, calibration, sample size, and uncertainty. Accuracy alone is insufficient.
- Add tests that deliberately place a match result in the future relative to a prediction and verify that it cannot affect that prediction's features.
- Do not enable value alerts or describe predictions as profitable until the model passes predeclared out-of-sample criteria and market comparisons.

### P3 — Make prediction eligibility explicit

For each fixture, expose whether required team history and competition mapping are sufficient. If not, either fall back to a clearly labelled baseline or suppress the forecast. Do not present a high-confidence score when the underlying history is sparse, stale, or mapped ambiguously. Preserve experimental predictions for tracking, but keep value/betting alerts disabled.

## Recommended completion criteria

Do not declare this issue resolved until all of the following are true:

1. A fresh coverage report is generated from the exact data artifact used by the model.
2. The report contains real min/max dates, counts, duplicates, per-competition/season coverage, and an explicit unresolved-gap ledger.
3. A clean repeat run produces the same audit for the same data hash.
4. Known unsupported dates are not retried endlessly, and unresolved gaps remain visibly unresolved.
5. The chronological backtest is reproducible from the pinned dataset and shows no temporal leakage.
6. Prediction/value-alert safeguards remain active until predeclared out-of-sample acceptance criteria are met.

## Follow-up repository evidence (2026-10-27)

### Production-data audit is still blocked by artifact availability

- The daily prediction workflow run **40554516330** (commit `39fb42b112e32fa82ef9be6961dd094d0b1554ca`, 2026-10-27 17:51 UTC) failed during unit tests: **192 passed, 1 failed**. The failing test is `tests/test_report_artifacts.py::test_report_loader_reads_published_snapshot_without_github_api_or_forecast`; it expected a raw.githubusercontent.com URL, while the implementation used the GitHub Contents API URL with a cache-busting parameter.
- Because the unit-test step failed, downstream steps in that run—including historical-match import and report generation—were skipped. Do not use that run as evidence of a successful refresh.
- The previous successful run **40552093140** (2026-10-27 17:36 UTC) published only `veltrix-paper-ledger` and `veltrix-daily-predictions` artifacts. Neither artifact is the full historical match CSV, so it cannot establish the actual dataset's minimum date, maximum date, duplicates, or coverage gaps.
- The historical import workflow is configured to upload `data/open_historical_matches.csv` as a 30-day artifact. That artifact must be retrieved from a successful run of the dedicated historical import workflow, then audited. The daily workflow's small prediction report is not a substitute.
- The backtest workflow is configured to import the source data and run `scripts/run_backtest.py`, but its historical report is also an artifact rather than a committed production dataset. Its metrics need to be tied to the exact dataset hash.

**Remediation and follow-up verification (2026-10-27, 18:10 UTC):**

- Fixed the test to validate the implementation's intended cache-busted GitHub Contents API request, including the `command-data` branch selector and numeric cache-buster, instead of requiring the older raw CDN URL. The production loader was not weakened or reverted.
- Commit **92ed93f3215a90d81f8b2faa518de197ba11ab04** triggered fresh workflow runs. The Daily Fixture Predictions workflow's unit-test step passed and the workflow completed successfully; its push-triggered run intentionally skipped the scheduled/dispatch prediction-generation steps, so it is not evidence of a new Telegram prediction delivery.
- Historical Model Backtest run **40557259141** completed successfully: unit tests passed, the historical dataset import step passed, the chronological model comparison passed, and the **veltrix-backtest-report** artifact was uploaded (40,432 bytes; created 2026-10-27 18:09:58 UTC).
- This is a meaningful recovery: the immediate CI blocker is fixed, and a fresh backtest report exists. However, the artifact has not yet been inspected here and the raw historical CSV has not been independently audited for duplicates, actual min/max dates, division-season completeness, or unresolved gaps. The dedicated historical-dataset-import workflow still needs a successful run if we need its standalone `open_historical_matches.csv` artifact.

**Next action:** inspect the newly generated backtest report and run/audit the standalone historical CSV artifact. Keep value/betting alerts disabled until coverage and out-of-sample results are verified.

## Sources

1. Veltrix README and documented import/backtest behavior: https://github.com/Nexora-Apparel/veltrix-football/blob/main/README.md
2. Veltrix importer implementation: https://github.com/Nexora-Apparel/veltrix-football/blob/main/scripts/import_open_dataset.py
3. Veltrix recent-result refresh implementation: https://github.com/Nexora-Apparel/veltrix-football/blob/main/app/recent_results.py
4. Upstream Club-Football-Match-Data README and stated dataset scope: https://github.com/xgabora/Club-Football-Match-Data
5. API-Football official documentation, including competition/season coverage caveats: https://www.api-football.com/documentation_v3
6. API-Football official pricing and request quotas: https://www.api-football.com/pricing
