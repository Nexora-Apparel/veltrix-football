# VELTRIX FOOTBALL 2.0 — AI Midas dataset inventory and temporal audit

**Audit date:** 2026-11-15  
**Classification:** PARTIAL — source authorized; inventory verified; staging ingestion and model admission not performed  
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

### Remaining bounded actions

1. Add a deterministic, pinned, no-key snapshot collector that stores raw files and hashes in an isolated artifact; no database writes by default.
2. Build exact team/competition/date crosswalk candidates for Brazil Série B and quarantine ambiguous matches.
3. Keep the 2016–2025 Brazil Série B historical gap explicit; do not silently substitute Brazil Série A or Italy Serie B.
4. Keep average odds separate from bookmaker quote observations and continue searching for timestamped closing odds.
5. Admit only leakage-safe features for future cutoffs after the actual Veltrix import timestamp; keep retrospective walk-forward certification blocked.
