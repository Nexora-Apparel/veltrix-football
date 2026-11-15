# VELTRIX FOOTBALL 2.0 — AI Midas dataset inventory and temporal audit

**Audit date:** 2026-11-15  
**Classification:** PARTIAL — source authorized; inventory and immutable snapshot verified; staging database ingestion and model admission not performed  
**Source repository:** https://github.com/aimidas1/aimidas1  
**Pinned source commit:** `29baca362a34ce5dcd3924b07ec9c7d5139d83fc`  
**Repository pushed at:** `2026-11-11T00:00:10Z`  
**Authorization:** `approval-aimidas-football-data-noncommercial-2026-11-15`  
**Rights record:** `docs/legal/aimidas-noncommercial-authorization-2026-11-15.md`

## 1. Executive result

AI Midas is a useful supplementary historical-statistics source and materially improves Brazil Série B coverage. It is **not** a replacement for timestamped bookmaker closing odds and does not close the Stage 2 98% odds, CLV or PIT walk-forward gates.

Verified at the pinned commit:

- Six historical match datasets cover Brazil Série A and five European target competitions from 2016 through 2024/25: **19,605 match rows**.
- The historical files contain complete, numerically valid average 1X2 odds in **19,454/19,605 rows (99.23%)** across those six competitions.
- Six completed 2025/26 match files add **2,131 rows** across Brazil Série A, EPL, Ligue 1, Bundesliga, Italy Serie A and La Liga.
- A separate Brazil Série A 2026 file contains **177 rows**, dated 2026-01-28 through 2026-05-31.
- Brazil Série B has **738 team rows representing 369 distinct matches**, 20 teams and dates 2026-03-21 through 2026-11-08 in its 2026 advanced-statistics CSV.
- No Brazil Série B historical 2016–2025 match dataset was found. The combined `csv/matches/leagues_total/all_matches.csv` also contains no Brazil Série B label.
- No 2026/27 European target-league match files were present in the pinned repository tree.
- Public GitHub raw-file retrieval requires no AI Midas API key and no additional Veltrix secret.

## 2. Seven-competition coverage matrix

| Veltrix competition | Historical match archive | 2025/26 or 2026 match file | Brazil/Europe advanced stats | Decision |
|---|---|---|---|---|
| Brazil Série A | 2016–2024: 3,419 rows | 2025–2026-labelled file: 380 rows; separate 2026 file: 177 rows | 2026 advanced stats present | Useful historical/statistical supplement |
| Brazil Série B | No 2016–2025 match archive found | No standard match/odds file found | 2026 advanced file: 738 team rows / 369 matches | **2026 advanced stats only; historical gap remains** |
| England Premier League | 2016/17–2024/25: 3,420 rows | 2025/26: 380 rows | No separate EPL advanced-stats file in the advanced-stats directory | Useful historical/statistical supplement |
| France Ligue 1 | 2016/17–2024/25: 3,171 rows | 2025/26: 305 rows | No separate Ligue 1 advanced-stats file in the advanced-stats directory | Useful historical/statistical supplement |
| Germany Bundesliga I | 2016/17–2024/25: 2,754 rows | 2025/26: 306 rows | No separate Bundesliga advanced-stats file in the advanced-stats directory | Useful historical/statistical supplement |
| Italy Serie A | 2016/17–2024/25: 3,421 rows | 2025/26: 380 rows | No separate Italy advanced-stats file in the advanced-stats directory | Useful historical/statistical supplement |
| Spain La Liga | 2016/17–2024/25: 3,420 rows | 2025/26: 380 rows | No separate La Liga advanced-stats file in the advanced-stats directory | Useful historical/statistical supplement |

The 2025/26 file row counts are inventory counts, not proof that every scheduled fixture is represented. In particular, the Ligue 1 file contains 305 rows; no completeness claim is made without an independent schedule reconciliation.

## 3. Historical 1X2 average-odds audit

The six historical CSVs contain `avg_odds_ft_1`, `avg_odds_ft_x` and `avg_odds_ft_2`. The count below requires all three values to parse as finite numbers greater than 1 and less than 1,000.

| Competition | Historical rows | Complete valid average 1X2 | Coverage |
|---|---:|---:|---:|
| Brazil Série A | 3,419 | 3,379 | 98.83% |
| England Premier League | 3,420 | 3,416 | 99.88% |
| France Ligue 1 | 3,171 | 3,169 | 99.94% |
| Germany Bundesliga I | 2,754 | 2,667 | 96.84% |
| Italy Serie A | 3,421 | 3,420 | 99.97% |
| Spain La Liga | 3,420 | 3,403 | 99.50% |
| **Total** | **19,605** | **19,454** | **99.23%** |

The completed 2025/26 files have valid average 1X2 values in: Brazil Série A 380/380; EPL 379/380; Ligue 1 305/305; Bundesliga 306/306; Italy Serie A 380/380; La Liga 380/380. The separate Brazil Série A 2026 file has 177/177.

**Critical market-data distinction:** these are average odds columns. The inspected schema does not identify the bookmaker(s), constituent prices, quote timestamp, collection timestamp, market closing definition or pre-kickoff observation time. Therefore:

- They may be retained as non-certified descriptive historical average-odds context, subject to temporal and leakage controls.
- They are not bookmaker-specific quotes.
- They are not proven closing odds.
- They cannot be used to claim CLV, timestamped-odds coverage, the 98% gate or bookmaker benchmark certification.
- Brazil Série B's advanced-statistics file contains no odds fields.

## 4. Brazil Série B 2026 advanced-statistics file

File: `advanced stats/Brazil Serie B 2026.csv`  
Pinned blob: `b6bdb94c053d2149e6232fb100e1f158e46e4533`  
Size: 192,284 bytes in GitHub tree metadata  
Parsed rows: 738  
Distinct `Match` labels: 369  
Distinct teams: 20  
Date range: 2026-03-21 to 2026-11-08  
Columns: 50

The file contains team-match rows and advanced fields including xG/xGA/xGD, open-play xG, set-piece xG, non-penalty xG, possession, field tilt, vertical tendency, xT, passes into the box, shots, PPDA, high recoveries, crosses, corners, fouls and pressure/control metrics.

It contains `Team`, `Match` and date-only `Date` fields, not a canonical fixture ID or a timezone-aware kickoff timestamp. Match identity must be reconciled against Veltrix's canonical fixture registry using both teams, competition and date, with ambiguity quarantined. Two team rows per distinct match are expected in this file.

These are match-completion statistics. They are not pre-match features for the same fixture. The file's date field does not establish when the source first published each row.

## 5. Temporal and feature-use classification

| Field family | Observed semantics | Admission decision |
|---|---|---|
| `homeGoalCount`, `awayGoalCount`, final/half-time scores, result labels | Settled match outcomes | Retrospective labels; preserve actual Veltrix import time; no backdated PIT claim |
| Actual `team_a_xg`, `team_b_xg`, total xG, shots, possession, PPDA, cards, corners and advanced Brazil B metrics | Match/post-match observations | Never use as same-match pre-kickoff features |
| `pre_match_*` and `*_prematch` fields | Named as pre-match in the schema, but no row-level source availability timestamp or methodology proof was found | PIT-ineligible pending independent temporal evidence |
| `avg_odds_ft_*` and other `avg_odds_*` fields | Average odds, without bookmaker identity or quote timestamp | Non-certified descriptive market context only; not closing odds or CLV |
| `date` fields | Local-looking date/time strings; timezone not specified | Preserve raw value; do not manufacture UTC kickoff time |
| Brazil Série B `Match` + `Date` | Text fixture label and date-only value | Identity reconciliation required; not a time-stamped fixture key |

The source repository commit timestamp is repository revision metadata, not proof of the first public availability of every row or field. Veltrix must store its actual retrieval and recording times and set historical rows to non-PIT unless a separate publication-time proof is available.

The historical match outcomes can support retrospective research and future model development after actual ingestion. They must not be backdated into historical walk-forward cutoffs. Same-match post-match fields must never leak into that match's prediction features.

## 6. Retrieval, pinning and provenance

- Repository: `aimidas1/aimidas1`
- Pinned commit: `29baca362a34ce5dcd3924b07ec9c7d5139d83fc`
- Public raw GitHub files can be retrieved without an API key.
- Do not execute the source repository's `sync_stats.py` as a Veltrix ingestion mechanism. It expects a local `.env`, may use a GitHub token and pushes updates to the source owner's own repository. Veltrix can read the public files directly and immutably.
- `sync_stats.py` identifies `griffisben/Post_Match_App/Stat_Files` as the upstream location for the `advanced stats` mirror. Preserve this upstream lineage in any future manifest.
- GitHub repository metadata for AI Midas and the identified upstream repository reports `license: null`; no root `LICENSE` file was present in the inspected trees. The user-confirmed AI Midas authorization is recorded separately. Do not infer an independent upstream SPDX licence or redistribute raw files.

### Audited file pins

| Dataset | Repository path | Git blob SHA |
|---|---|---|
| Brazil Série A historical 2016–2024 | `csv/past-seasons/leagues/Brasileirão_Série_A_2016-2024.csv` | `5a42af579f336938eaad8ab08e60bd83ca0ed66d` |
| EPL historical 2016–2025 | `csv/past-seasons/leagues/England_Premier_League_2016-2025.csv` | `92bebb1ba8471fdd404ea48193fe2cacbe51ccdb` |
| Ligue 1 historical 2016–2025 | `csv/past-seasons/leagues/France_Ligue_1_2016-2025.csv` | `666555e3e60a3b59ef720ecd52557ac0522a0038` |
| Bundesliga historical 2016–2025 | `csv/past-seasons/leagues/Germany_Bundesliga_2016-2025.csv` | `f39c8fbedcea2d1dc0771d844657f437a76663d6` |
| Italy Serie A historical 2016–2025 | `csv/past-seasons/leagues/Italy_Serie_A_2016-2025.csv` | `56478b8dc15ec0af0a340253889e10dbf2f51283` |
| La Liga historical 2016–2025 | `csv/past-seasons/leagues/Spain_La_Liga_2016-2025.csv` | `e0dfc6f2129df1c857022b16fe1693811f8870a1` |
| Brazil Série A 2025–2026-labelled match file | `csv/matches/leagues/Brasileirão_Série_A_2025-2026.csv` | `0779b8d3d1a626ae2dc4e2e9b30debc0f1e4ed89` |
| Brazil Série A 2026 match file | `csv/matches/leagues/Brasileirão_Série_A_2026.csv` | `a3fffa1187ad0a1745c11a77f57e1d632168f768` |
| EPL 2025–2026 | `csv/matches/leagues/England_Premier_League_2025-2026.csv` | `3589069f19f804efcb7bc8b97dffb412ea1d4ded` |
| Ligue 1 2025–2026 | `csv/matches/leagues/France_Ligue_1_2025-2026.csv` | `4b3b3db181dcb8e6a0249ded8b7cfe7cd8b8c9e7` |
| Bundesliga 2025–2026 | `csv/matches/leagues/Germany_Bundesliga_2025-2026.csv` | `e1674246aa2f9d6f2006d46887e9ee69ee7eaec3` |
| Italy Serie A 2025–2026 | `csv/matches/leagues/Italy_Serie_A_2025-2026.csv` | `ae6ee88284cf474b226a39561d13008fa07d3368` |
| La Liga 2025–2026 | `csv/matches/leagues/Spain_La_Liga_2025-2026.csv` | `076fea41135d65ad8fee7993b167bc7ddce7c1bf` |
| Brazil Série B 2026 advanced stats | `advanced stats/Brazil Serie B 2026.csv` | `b6bdb94c053d2149e6232fb100e1f158e46e4533` |

Git blob SHA is recorded as the immutable repository object identifier; it is not relabelled as a SHA-256 digest.

## 7. Stage 2 disposition

**Approved role:** supplementary historical match/statistics research and Brazil Série B 2026 advanced-statistics research, under the non-commercial authorization.

**Not approved by this audit:** historical PIT walk-forward admission, same-match feature use, bookmaker benchmark certification, timestamped closing-odds certification, CLV or value-bet activation.

**Not performed:** Neon writes, production imports, model training, prediction changes, deployment, schedule activation, Telegram delivery or PR merge.

## 8. Brazil Série B crosswalk audit — read-only staging comparison

The AI Midas 2026 Brazil Série B advanced-statistics file was reconciled against the canonical 5DollarFootballAPI Brazil Série B fixture registry using a read-only query on Neon project `withered-sky-75161174`, branch `br-silent-violet-bc5de88s` (`veltrix-phase3-import-dry-run`), database `veltrix_football_staging`. No rows were inserted or updated.

- Canonical competition: Brazil Série B; 5Dollar provider competition ID `522514093`.
- Canonical 2026 fixture universe in this branch: **371 fixtures**, all FINISHED and with canonical result rows; 20 distinct teams.
- AI Midas source: **369 distinct matches**, 738 team rows.
- Team identity: **20/20 source teams** map to the canonical team registry after accent/spelling normalization. Ten source labels required aliases: América Mineiro → America MG; Atlético Goianiense → Atletico GO; Avaí → Avai; Ceará → Ceara; Criciúma → Criciuma; Cuiabá → Cuiaba; Goiás → Goias; Náutico → Nautico; Operário PR → Operario PR; São Bernardo → Sao Bernardo.
- Fixture identity: **369/369** source matches map to one unique canonical fixture; **0 unmatched, 0 ambiguous, 369 distinct fixture IDs**.
- Score reconciliation: **369/369** AI Midas match labels agree with the canonical 5Dollar result; no canonical result is missing.
- Date reconciliation: all 369 source date values fall within one UTC calendar day of the canonical kickoff date; 333 share the same UTC date and 36 are one UTC day later. This confirms the source date is not a UTC kickoff timestamp.
- Coverage against the inspected 371-fixture canonical universe: **369/371 = 99.46%**. Two canonical fixtures are absent from the AI Midas file. The source file ends on 2026-11-08, while the canonical fixture universe extends to 2026-11-11.

This is a verified identity crosswalk result, not a PIT admission. Keep the source date-only value unchanged; do not convert it to UTC or use it as a precise kickoff time. The two missing fixtures remain missing; no imputation is permitted.

## 9. Immutable snapshot execution — 2026-11-15

- Added `scripts/veltrix_v2/collect_aimidas_snapshot.py` and `scripts/veltrix_v2/verify_aimidas_snapshot.py`.
- Added `tests/veltrix_v2/test_aimidas_snapshot.py`: **7 passed**.
- Added no-key workflow `.github/workflows/phase2-aimidas-snapshot-audit.yml`, triggered only by relevant integration-branch pushes; no schedule or provider API secret is used.
- Workflow [#43752239352](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43752239352) first passed the collector/verifier but uploaded a raw-source artifact. That artifact was deleted by the subsequent privacy correction; the prior run now has no artifacts.
- Workflow [#43752435643](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43752435643) completed **success** on code commit `4b666d6666b0aaf32daaa60a6ffb75cc2d76a306`. The cleanup step confirmed deletion of the prior raw artifact.
- Collector captured **14/14 pinned CSV files**, 11,599,486 source bytes, with expected Git blob SHA-1 checks and SHA-256 manifests. Independent offline verifier reproduced all 14 CSV audits and returned `PASS`.
- The public artifact now contains **only** `manifest.json` and `verification.json`; the 11.6 MB raw snapshots remain ephemeral on the runner and are not uploaded. Artifact [#14176976339](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43752435643/artifacts/14176976339), ZIP SHA-256 `54ce4e05d6fd84f410c6723c181030ecde4376a10003ed6523ff9b536591b595`.
- A subsequent idempotency regression run [#43752821538](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43752821538) passed after the prior raw artifact had already been deleted; it retained only metadata artifact [#14176614669](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43752821538/artifacts/14176614669), ZIP SHA-256 `02377544a7c9f361b441e641fcad37bc575e3dd16a43092355d3e3dd2123718a`.
- Workflow output confirms `database_written=false`, `production_written=false`, `model_admitted=false`, `predictions_changed=false`, `point_in_time_certifiable=false`. The metadata artifact is not a Neon import or PIT evidence.

### Remaining bounded actions

1. Implement the staging-only importer and independent read-after-commit verifier defined in `docs/VELTRIX_V2_AIMIDAS_STAGING_IMPORT_CONTRACT_2026-11-15.md`; keep production untouched.
2. Obtain reviewer-backed evidence before marking the 369 Brazil Série B fixture mappings RESOLVED in `entity_crosswalk_versions`.
3. Keep the 2016–2025 Brazil Série B historical gap explicit; do not silently substitute Brazil Série A or Italy Serie B.
4. Keep average odds separate from bookmaker quote observations and continue searching for timestamped closing odds.
5. Admit only leakage-safe features for future cutoffs after the actual Veltrix import timestamp; keep retrospective walk-forward certification blocked.
