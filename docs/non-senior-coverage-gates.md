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
