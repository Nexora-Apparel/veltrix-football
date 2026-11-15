# VELTRIX FOOTBALL 2.0 — AI Midas Brazil Série B 2026 identity reconciliation

**Audit date:** 2026-11-15  
**Disposition:** 369/369 fixture identities and score agreements independently verified; reviewer acceptance pending; two canonical fixtures absent from the source file  
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
| Team-row Goals / Goals Conceded checks | 738/738 |
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

All 369 matches passed all checks. The fixture IDs are distinct; no source match maps to a reused canonical fixture. All 738 team rows agree with the score orientation in their parent match label.

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

**All 369 identity candidates are independently verified, but none is marked `RESOLVED` in the database.**

The audit artifact records each candidate as `REVIEW_REQUIRED` and includes its source row IDs/fingerprints, canonical fixture ID, provider fixture ID, date delta and score agreement. Reviewer acceptance remains pending because no reviewer identity/acceptance event has been recorded for this complete evidence set.

This is intentional: a verified candidate is not the same thing as a reviewer-approved crosswalk. The two missing canonical fixtures remain `UNRESOLVED_NO_REPLACEMENT_MAPPING`. No `entity_crosswalk_versions`, `fixtures`, `fixture_results` or normalized statistics rows are written by this audit.

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
- `.github/workflows/phase2-aimidas-brazil-serie-b-identity.yml`

The workflow fetches the pinned source snapshot, independently verifies file pins and CSV inventory, performs a read-only staging transaction, checks the staging raw bytes against the source snapshot, calculates all row fingerprints and uploads only the sanitized audit JSON. The workflow result and artifact hash are appended to this report after completion.

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
