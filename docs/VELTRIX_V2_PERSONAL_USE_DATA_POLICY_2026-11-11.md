# VELTRIX FOOTBALL 2.0 — Personal-Use Data Policy and OpenPlay Adapter
Date: 2026-11-11
Branch: `veltrix-2.0-architecture-blueprint`
Scope: private, non-commercial football analysis by the account owner.

## Operating assumption

VELTRIX is being used for the user's own personal football analysis, not as a paid service, commercial product, public data feed or customer-facing model. This changes the candidate-source policy: sources expressly limited to personal, academic, research or non-commercial use may be considered within those terms.

This is not a blanket waiver. Each provider's access method, rate limits, attribution, retention, redistribution and upstream rights still apply. Personal use does not authorize bypassing authentication, scraping against terms, excessive automated access, or republishing source data.

## Source decisions

| Source | Personal-use position | VELTRIX decision |
|---|---|---|
| OpenPlay `data-v0.1.0` | Release declares CC BY 4.0 and requests attribution to `openplay (Noah Bair)`. Maintainer discloses WhoScored / Opta / Stats Perform as upstream origin. | Strong historical research candidate. Keep release pinned, attribute, preserve xG model identity, and retain upstream provenance note. Not a live 2026/27 feed. |
| StatsBomb Open Data | Official repository makes selected data available for research and genuine interest in football analytics. Published analysis requires StatsBomb attribution and logo. | Eligible for personal research after following its current user agreement / registration and attribution requirements. Competition/season coverage is selective; never assume global coverage. |
| Football-Data.co.uk | Site says free CSV/Excel files are for private individuals' personal betting and/or academic interest; access should be manual or at most light automated download (twice weekly maximum). Heavy repeated automated access and commercial/data-training projects are excluded. | Personal research candidate. Prefer manual downloads; if automated, remain within the stated twice-weekly maximum and polite request limits. Do not bulk-poll. |
| Open Matchday | Repository says informational, non-commercial use, including personal projects/research, with attribution. It also states upstream provider rights remain in force and lists limitations including fixed CET-1 kickoff offset, no xG, lineups, injuries, odds or play-by-play. | Personal-use fixture/results and basic-stat candidate only. Preserve source and provider lineage, validate each competition, and do not trust its kickoff offset as exact local time. |
| FPL | Terms reviewed by the project prohibit automated extraction/access without permission. | Automated ingestion remains excluded, even for personal use. Do not call its endpoints through VELTRIX. |
| OpenFootball | CC0 supplemental historical fixture/results candidate; recent 90-day EPL paired reconciliation yielded only 45/100 exact score coverage. | Keep as a limited historical supplement; not current EPL results primary. |

## OpenPlay technical adapter

Added:
- `veltrix_v2/ingestion/openplay_player_stats.py`
- `tests/veltrix_v2/test_openplay_player_stats_adapter.py`

The adapter:
- retains native match/player/team IDs, competition and season;
- preserves the source match date and scraped-at value as raw strings;
- does not manufacture UTC kickoff or availability timestamps;
- requires explicit xG and xA model identifiers when those metrics are present;
- preserves nulls as nulls and validates numeric/count fields;
- hashes each normalized source row deterministically;
- quarantines known-issue matches and competition-season rows outside the supplied coverage allowlist;
- does not create rights approval, ingest into Neon, train a model or publish predictions.

The source player-match table does not itself prove that a row was available before a historical forecast cutoff. A later point-in-time join must use defensible publication/availability evidence. If that evidence is absent, the feature must be unavailable for pre-match training rather than backdated from a post-match scrape.

## Validation evidence

- OpenPlay pinned release technical qualification: [GitHub Actions #43006720029](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43006720029).
- New adapter and tests were added to the PR branch.
- Foundation CI after adapter addition: [GitHub Actions #43011984377](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43011984377), job completed successfully, including the full `tests/veltrix_v2` suite and legacy-import boundary check.

## Next data work

1. Build an OpenPlay match/coverage/known-issue join that feeds the adapter the exact xG model ID and quarantine flags.
2. Add a separate StatsBomb event/lineup adapter with competition-season coverage manifests and explicit attribution metadata.
3. Add an Open Matchday current-season snapshot validator; treat its kickoff timestamps as approximate until independently corrected.
4. Keep Football-Data.co.uk as a user-downloaded/manual snapshot path unless its stated light-access ceiling is respected.
5. Keep all historical rows quarantined from pre-match training unless the data's actual availability time can be established.
6. Do not write to Neon, train models, calibrate, deploy or reactivate Telegram schedules until the relevant source and point-in-time gates pass.

## Source references

- OpenPlay release and declared data licence: https://github.com/nlbair/openplay
- StatsBomb Open Data repository and attribution instructions: https://github.com/hudl/open-data
- Football-Data.co.uk fair data usage policy: https://football-data.co.uk/contact.php
- Open Matchday description, limitations and non-commercial terms: https://github.com/oladeeayo/open-matchday
