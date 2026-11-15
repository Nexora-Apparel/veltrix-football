# VELTRIX FOOTBALL 2.0 — AI Midas Brazil Série B 2026 identity reconciliation

**Audit date:** 2026-11-15  
**Disposition:** 389 reviewer-backed staging crosswalks accepted and independently read back (20 teams + 369 fixtures); two canonical fixtures remain unresolved; two contradictory team-stat rows remain quarantined  
**Canonical competition:** 5DollarFootballAPI Brazil Série B, provider competition ID `522514093`  
**Staging target:** Neon project `withered-sky-75161174`, branch `br-silent-violet-bc5de88s`, database `veltrix_football_staging`  
**Source approval:** `approval-aimidas-football-data-noncommercial-2026-11-15`

## 1. Source provenance

- Repository: `aimidas1/aimidas1`
- Pinned commit: `29baca362a34ce5dcd3924b07ec9c7d5139d83fc`
- File: `advanced stats/Brazil Serie B 2026.csv`
- Git blob SHA-1: `b6bdb94c053d2149e6232fb100e1f158e46e4533`
- File size: 192,284 bytes
- Stored raw-response SHA-256: `55b0c00629abd2d4ff3c31659ada950b67ffc2752609284b32c15c99f71152ab`
- Staging `source_observations.id`: `432397`
- Staging `provider_responses.id`: `1238`
- Staging source-observation payload SHA-256: `21d05be37e65f8e0856045c50819863e111bad3d06e8589757e678eedc59766c`
- Retrieved: `2026-11-15T19:41:39.577Z`
- Raw bytes were read from the staging response and independently compared to the pinned source file during the dedicated reconciliation workflow.
- Source terms: internal non-commercial project use, attribution required, raw redistribution prohibited.

The database stores the source as one immutable file-level observation, not as 738 normalized match rows or 369 persisted crosswalks. The audit reads the exact raw response and independently parses it; it does not treat file-level storage as prior match-level acceptance.

## 2. Audit result

| Control | Result |
|---|---:|
| Source team-stat rows | 738 |
| Distinct source matches | 369 |
| Distinct source team identities | 20 |
| Canonical 2026 fixtures in registry | 371 |
| Team identities uniquely mapped | 20/20 |
| Fixture identities uniquely matched | 369/369 |
| Distinct canonical fixture IDs | 369 |
| Independent score agreements | 369/369 |
| Team-row Goals / Goals Conceded checks | 736/738 consistent; 2 quarantined |
| Ambiguous fixture candidates | 0 |
| Score disagreements | 0 |
| Duplicate source match groups | 0 |
| Canonical fixtures absent from source | 2 |

The independent staging SQL audit used the stored raw CSV body, split the 738 team rows into 369 distinct match labels, parsed the ordered home/away names and score, joined the explicit team aliases to the canonical team registry, and compared the resulting ordered team IDs, date window and scores against the 2026 canonical fixture set. It returned 369 unique fixture IDs and 369 exact score agreements.

The source date is a date-only match label, not a verified kickoff timestamp. Among the 369 matches, 333 canonical kickoff UTC dates equal the source date and 36 canonical kickoff UTC dates are one day later. The one-day date tolerance is used only as corroboration after exact competition and ordered team identity; it does not rewrite the source date or infer a kickoff time.

## 3. Team identity crosswalk evidence

All 20 source teams map one-to-one to distinct 5DollarFootballAPI team IDs. The ten accent/spelling differences are explicit aliases; the other ten are exact-name matches.

| AI Midas source label | Canonical 5Dollar name | Provider team ID |
|---|---|---:|
| América Mineiro | America MG | 1102583842 |
| Athletic Club MG | Athletic Club MG | 3007875643 |
| Atlético Goianiense | Atletico GO | 1684426968 |
| Avaí | Avai | 1446563615 |
| Botafogo SP | Botafogo SP | 3250670103 |
| CRB | CRB | 2651466053 |
| Ceará | Ceara | 1657329649 |
| Criciúma | Criciuma | 3324195045 |
| Cuiabá | Cuiaba | 4227927162 |
| Fortaleza | Fortaleza | 744720326 |
| Goiás | Goias | 3126624865 |
| Juventude | Juventude | 2672186301 |
| Londrina | Londrina | 3219034225 |
| Novorizontino | Novorizontino | 1620921678 |
| Náutico | Nautico | 4267737771 |
| Operário PR | Operario PR | 2016651568 |
| Ponte Preta | Ponte Preta | 1548718709 |
| Sport Recife | Sport Recife | 559667509 |
| São Bernardo | Sao Bernardo | 844813267 |
| Vila Nova | Vila Nova | 2434042650 |

The source file contains 37 rows for 18 teams and 36 rows each for Botafogo SP and Náutico, totalling 738 team rows. No two source labels resolve to the same canonical team ID.

## 4. Fixture and score verification method

For each source match, the audit:

1. Preserves the source date, raw match label, ordered home and away labels, and source team rows.
2. Parses the full-time score from the match label.
3. Checks each team's `Goals` and `Goals Conceded` fields against its home/away side in the match label.
4. Resolves both team identities through the explicit 20-team alias/exact-name map.
5. Requires exact canonical competition identity and exact ordered home/away team IDs.
6. Allows a maximum one-calendar-day difference between source date and canonical UTC kickoff date, without converting the source date into a kickoff timestamp.
7. Requires exactly one canonical fixture candidate.
8. Independently compares canonical home and away result scores to the source match-label score.

All 369 match-level fixture-identity and canonical score checks passed. The fixture IDs are distinct; no source match maps to a reused canonical fixture. 736/738 team rows agree with the score orientation in their parent match label. Two rows in the Náutico 0–3 CRB match do not agree and are individually quarantined from statistics/features; they do not invalidate the exact match-label-to-canonical fixture identity.


### 4.1 Team-stat row discrepancy — quarantine

The canonical result and AI Midas Match label both report **Náutico 0–3 CRB**, and the match-level score agreement passes. Two of the associated team-stat rows contain a conflicting Goals / Goals Conceded pair:

| CSV line | Team row | Stored Goals | Stored Goals Conceded | Match-label expected | Disposition |
|---:|---|---:|---:|---|---|
| 8 | CRB | 2 | 0 | 3 goals, 0 conceded | QUARANTINED_TEAM_STAT_ROW |
| 9 | Náutico | 0 | 2 | 0 goals, 3 conceded | QUARANTINED_TEAM_STAT_ROW |

The two rows appear to reflect a 0–2 team-stat score while the Match label and canonical result are 0–3. The available evidence does not establish which upstream processing step caused the inconsistency. Preserve both original row fingerprints and source line numbers; do not rewrite either row or silently reconcile the values.

Disposition: 736/738 team rows pass the Goals / Goals Conceded check; 2/738 fail. The affected match identity and its 0–3 result remain verified, but both team-stat rows are excluded from feature admission pending source review.

## 5. Two missing canonical fixtures — exact discrepancy

The canonical 2026 Série B registry contains 371 finished fixtures. The AI Midas file contains 369 distinct matches. The following two canonical fixtures have no corresponding AI Midas match row after exact ordered-team and date-window comparison.

| Canonical fixture | Kickoff (UTC) | Score | Fixture ID | 5Dollar fixture ID | Discrepancy |
|---|---|---:|---:|---:|---|
| Náutico vs Botafogo SP | 2026-09-03 23:00 | 1–0 | 1927 | 3538579905 | Absent from source despite falling inside the source file's 2026-03-21 to 2026-11-08 date span |
| Londrina vs Náutico | 2026-11-11 22:00 | 2–1 | 1807 | 1878457839 | Kickoff is after the source file's final date, 2026-11-08 |

**Finding for 3 September:** this is an internal source-coverage hole. The file contains other matches dated before and after 3 September, but no corresponding Náutico–Botafogo SP match label. The available evidence does not establish whether the upstream cause was an omitted match, a source collection gap or another upstream publishing issue. It is recorded as an unexplained source omission, not repaired.

**Finding for 11 November:** this fixture is outside the source snapshot's observed date range. The file ends on 8 November; the canonical fixture is dated 11 November. This is a source snapshot cutoff/coverage gap.

No replacement rows, inferred mappings, duplicate matches or synthetic statistics were created. Both fixtures remain unresolved and absent from the AI Midas source crosswalk.

## 6. Source row identity and fingerprints

The reconciliation code generates a stable identity for every one of the 738 team rows using:

- pinned repository and commit;
- exact CSV path and Git blob SHA-1;
- file SHA-256 from the immutable snapshot manifest;
- original CSV line number;
- canonical JSON serialization of the full parsed source row (`sort_keys=True`, UTF-8, no ASCII escaping, compact separators);
- SHA-256 of that canonical row serialization.

Each row ID has the form:

`aimidas:<commit>:<path>:<line-number>:<first-16-hex-of-row-sha256>`

Each match also receives a stable SHA-256 match key based on the pinned source commit, source path, literal source date and literal match label. The sanitized workflow artifact carries all 738 row IDs, line numbers, row SHA-256 fingerprints and match-key hashes, plus the 369 candidate fixture links. It does not include the raw CSV body or full row payloads.

## 7. Reviewer-backed crosswalk disposition

**Accepted: 389 RESOLVED crosswalk versions are persisted in Neon staging.** The reviewer is an independent automated reviewer (`automated-independent-reconciliation-v1`), not a named human signatory.

- TEAM: 20/20 resolved (10 exact-name mappings and 10 explicit aliases).
- FIXTURE: 369/369 resolved using exact ordered team identity, date and score evidence.
- Every row has the reviewer ID and evidence observation reference `432397`; all 389 evidence foreign keys resolve.
- Independent read-back confirms 389 rows, 389 unique source IDs and 389 unique canonical IDs; no duplicate or many-to-one mapping violations.
- The two canonical fixtures absent from the source remain `UNRESOLVED_NO_REPLACEMENT_MAPPING`: fixture `1927` (Náutico–Botafogo SP, 3 September 2026) and fixture `1807` (Londrina–Náutico, 11 November 2026).
- The two inconsistent team-stat rows (CSV lines 8–9) remain quarantined; fixture identity and match-label score agreement do not admit those row-level statistics.

Acceptance workflow: [#43762497871](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43762497871), accepted at code head `cb30b76ba8446170eb8639fe58789dca7176d8c2`. Sanitized artifact: [#14180892673](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43762497871/artifacts/14180892673), ZIP SHA-256 `1870fc9066afed1ee0cc0db11911270808408cc77dee34013b3d63e5ce20ac81`. Source snapshot SHA-256: `55b0c00629abd2d4ff3c31659ada950b67ffc2752609284b32c15c99f71152ab`.

The acceptance transaction wrote only `entity_crosswalk_versions` in `veltrix_football_staging`. Independent post-run database checks confirmed zero missing reviewer/evidence references, zero evidence orphans, and no duplicate source/canonical mappings. The Brazil Série B 2026 fixture and result counts remain 371 each; no fixture or result rows were created during the acceptance interval. No production writes, deployments, prediction publication, Telegram delivery, schedule activation or model admission occurred.

## 8. Temporal, model and odds boundary

- All AI Midas file observations remain `point_in_time_certifiable=false`.
- Source rows have date-only match labels and no verified publication/effective timestamps or revision history.
- The AI Midas average pre-match 1X2 odds are not timestamped bookmaker-specific closing quotes.
- This reconciliation does not qualify historical closing odds, odds movement, CLV, walk-forward pre-match features or any market certification.
- No AI Midas row is admitted to model training or prediction generation.
- **Value betting remains LOCKED.**

## 9. Execution and verification

Dedicated implementation:

- `scripts/veltrix_v2/reconcile_aimidas_brazil_serie_b_2026.py`
- `tests/veltrix_v2/test_aimidas_brazil_serie_b_2026.py`
- `.github/workflows/veltrix-v2-foundation.yml`

The workflow fetches the pinned source snapshot, independently verifies file pins and CSV inventory, performs a read-only staging transaction, checks the staging raw bytes against the source snapshot, calculates all row fingerprints and uploads only the sanitized audit JSON. The workflow result and artifact hash are recorded below.



### Row-level quarantine identifiers

The two quarantined rows retain the following stable source IDs and canonical-row SHA-256 fingerprints:

| CSV line | Source row ID | Canonical row SHA-256 |
|---:|---|---|
| 8 (CRB) | aimidas:29baca362a34ce5dcd3924b07ec9c7d5139d83fc:advanced stats/Brazil Serie B 2026.csv:8:78d9492295da1b8d | 78d9492295da1b8dfa9ef735b786f63412089a37640b1f01aa3d57395707abc6 |
| 9 (Náutico) | aimidas:29baca362a34ce5dcd3924b07ec9c7d5139d83fc:advanced stats/Brazil Serie B 2026.csv:9:ce5bf78a5090a5be | ce5bf78a5090a5bef9997ae65c3b5a8e864e117218ed0404e59384b57a62bfb4 |

The shared source match-key SHA-256 is 2ead50b10c190f2c4db326f25a0b15cf73a0e129c89c9a15d1cb58f19466af82.

### Completed workflow verification

- Workflow: VELTRIX 2.0 Phase 2 Data Foundation Tests
- Run: [#43758559130](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43758559130)
- Audit job: aimidas-brazil-serie-b-identity — SUCCESS
- Run head: a36198f2d5b128ed96ce5ef140d38254c637b542
- Focused tests: 21 passed
- Reconciliation output: 20 teams verified; 369 fixture identities verified; 369 canonical score agreements; 2 absent canonical fixtures; 2 quarantined team-stat rows; 0 database mutations; 0 crosswalk writes.
- Sanitized artifact: [artifact #14178319188](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43758559130/artifacts/14178319188)
- Artifact ZIP SHA-256: 4b8c0ed7489cf82dd48c34ca1ba55f884ae5fe652fb2190c919139721a764500
- Artifact ZIP size: 110,951 bytes; embedded JSON manifest: 713,060 bytes.
- The artifact contains 738 unique source row IDs and 738 unique row SHA-256 fingerprints, 369 unique match-key hashes and 369 candidate fixture links. It excludes the raw CSV body.

The run's audit job and focused tests passed. PR #120 remains draft/open/unmerged; this audit success is not a merge or release approval.

## 10. Side effects

- Database transaction: read-only.
- Database mutations: 0.
- Crosswalk rows written: 0.
- Normalized fixtures/results/statistics written: 0.
- Production writes/deployments: 0.
- Predictions changed: 0.
- Telegram messages sent: 0.
- Schedule activation: 0.
- Value betting unlocked: false.


### Replacement-source exclusion

The Odds API's public technical catalogue lists Brazil Série B, but the active Veltrix source approval for that provider is limited to five European competitions and excludes Brazil Série B. The Brazil metadata-only discovery results are therefore not admitted as fixture identity or odds evidence. They were not persisted and cannot be used to create replacement crosswalks. The two absent canonical fixtures remain `UNRESOLVED`; no replacement mapping was invented. Reviewer-backed crosswalk acceptance is complete in staging: 389 RESOLVED crosswalk versions are independently verified; the two source-absent canonical fixtures remain unresolved.
