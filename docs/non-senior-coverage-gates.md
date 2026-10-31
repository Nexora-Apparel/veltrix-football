# Non-senior competition coverage gates

## Current policy

Women's, youth, reserve, academy, B-team and junior fixtures are withheld from probability generation unless Veltrix has category-matched historical results. The current historical-results dataset is predominantly senior competition data; team-name similarity or a provider league ID is not evidence that the same squad is represented.

The report status for a recognized non-senior fixture must be `UNSUPPORTED_COMPETITION`, including when the historical file is empty. It must not contain probability fields or betting recommendations.

## Requirements before enabling a category

A proposed source or competition mapping must pass all of these checks before it is used in production:

1. **Rights and terms:** confirm redistribution and automated use are allowed; record source URL, license, attribution and any share-alike or non-commercial restrictions.
2. **Category identity:** retain competition name, season, age/gender/squad category, country, and source competition ID. Do not merge senior, reserve, youth and women's competitions.
3. **Stable team identity:** preserve source team IDs where available; normalize names only as a secondary aid. Do not fuzzy-merge across squad categories.
4. **Score and date validation:** require valid match dates, non-negative integer full-time scores, a consistent result label, and valid home/away identities.
5. **Duplicate control:** deduplicate using source competition/season, match date, home and away identities, while investigating near-duplicates instead of silently dropping them.
6. **Coverage evidence:** publish match counts, earliest/latest dates, seasons represented, and per-competition coverage gaps. A few current-season fixtures do not qualify as historical training data.
7. **Chronological evaluation:** run a category-specific time-ordered backtest against simple baselines before exposing probabilities. Keep the category withheld if the sample is too small or evaluation is inconclusive.
8. **Regression tests:** prove that a category cannot borrow senior history and that unsupported records have no probabilities.

## Candidate source notes

- The existing open historical CSV is audited by `scripts/audit_historical_csv.py`; the latest recorded audit covered 38 divisions and ended on 2026-09-03. That does not establish historical coverage for reserve, youth or women's club competitions.
- The English Women's Football database may provide WSL and Women's Championship history, but it does not by itself prove coverage of lower-tier labels such as `EngNLW`. Verify actual competition identity, dates, schema and CC BY-SA 4.0 obligations before importing.
- A current-season fixture/results feed is useful for monitoring and current result collection, but must not be presented as multi-season historical training data.
- Women's international results are not substitutes for women's club results.
- Sources with non-commercial restrictions must not be used for any commercial deployment unless the license holder explicitly permits it.

## Enablement rule

Do not add a league alias alone to enable a competition. Enablement requires a documented source, category-matched data, a passing integrity/coverage audit, and a passing chronological evaluation. Until then, withholding the forecast is the correct result.

## Women's club history pilot

A category-isolated importer is available at `scripts/import_womens_club_history.py`. It reads the English Women's Football (EWF) database and writes to `data/womens_club_historical_matches.csv` by default. The file retains source match IDs, team IDs, season, tier and the `WOMENS_CLUB` category. It must remain separate from `data/open_historical_matches.csv`; it is not automatically enabled for live predictions.

Example manual import:

```bash
python scripts/import_womens_club_history.py --from 2011-01-01 --to 2026-12-31 --output data/womens_club_historical_matches.csv
python scripts/audit_historical_csv.py --input data/womens_club_historical_matches.csv --json-output reports/womens_history_audit.json --markdown-output reports/womens_history_audit.md
```

The source covers the English Women's Super League from 2011 and Women's Championship from 2014, with source-specific season structure. It is licensed CC BY-SA 4.0. Any public redistribution must include attribution and comply with ShareAlike requirements; verify how the license applies to the intended output before distributing it. This pilot does not cover lower-tier women's leagues or any reserve/youth competition.


## Fixture visibility invariant

A fixture may be excluded from probability generation, but it must not be silently removed from the fixture report solely because the model lacks history, the competition is unsupported, or kickoff metadata is missing. Such records remain visible with an explicit status; no forecast or betting signal is attached. A missing or invalid kickoff is labelled `KICKOFF_UNVERIFIED`. The same-day provider query remains the boundary for the fixture inventory, and confirmed past kickoffs or other-date fixtures are not presented as upcoming matches.

This visibility rule is covered by report-generation, delivery-filter and Telegram tests.


## End-to-end verification execution

The production workflow must run the full test suite, fetch the target-day fixture response from the primary provider, preserve every eligible scheduled fixture row, validate row-count reconciliation, then deliver and publish only after validation succeeds.


Verification receipt contract: every full daily run records unit-test, dashboard syntax, fixture generation, fixture-visibility, odds enrichment, value evidence, certificate, Telegram, artifact, paper tracking and command-data publication outcomes in `public-data/verification_status.json` on the `command-data` branch. A test-only push is labelled separately from a live run.


Final verification run requested on 2026-10-31: execute the complete test suite and live same-day fixture pipeline, then publish the verification receipt only after all gated stages finish.


Final verification receipt now includes the exact generated report's fixture counts, status distribution, visibility validation, odds status, value certificate state and evidence/paper-ledger summaries.


## Provider-outage recovery

Transient transport failures are retried with bounded backoff; definitive HTTP responses are not retried. If the primary fixture provider remains unreachable, the daily workflow attempts to restore the already-published report for the same Nigeria-local date, filters out past and other-date kickoffs, retains fixtures with unverified kickoff metadata, and labels the result `REUSED_SNAPSHOT_NOT_REFRESHED`. It never substitutes another date, fabricates fixtures, or describes a reused report as a fresh provider fetch. If no valid same-day snapshot exists, the run remains failed and the verification receipt records the failure.


Final end-to-end run: verify the primary provider with bounded transport retries, automatically recover today's already-published report if necessary, validate every visible fixture row, and confirm publication and Telegram delivery state.


## Telegram same-day update idempotency

The delivery guard stores hashes of the exact rendered report messages per local date. An identical report is suppressed, but a changed fixture inventory or forecast for the same date is sent as an explicitly labelled same-day update. Legacy date-only markers are migrated by sending one update and recording its content hash.


Final delivery verification: re-run the same-day report after the content-hash guard migration so the current 25-fixture inventory is sent once as an update rather than suppressed by a legacy date-only marker.
