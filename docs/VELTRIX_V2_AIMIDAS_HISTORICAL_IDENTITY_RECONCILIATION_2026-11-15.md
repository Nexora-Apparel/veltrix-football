# VELTRIX FOOTBALL 2.0 — AI Midas historical match-identity reconciliation

**Audit date:** 2026-11-15  
**Status:** READ-ONLY RECONCILIATION COMPLETE — SOURCE ROWS IDENTIFIED; NO CANONICAL FIXTURE CANDIDATES; REVIEW REQUIRED  
**Source:** `aimidas1/aimidas1@29baca362a34ce5dcd3924b07ec9c7d5139d83fc`  
**Approval:** `approval-aimidas-football-data-noncommercial-2026-11-15`  
**Staging target:** Neon `withered-sky-75161174` / `br-silent-violet-bc5de88s` / `veltrix_football_staging`

## 1. Execution result

The six AI Midas historical match archives were parsed from the pinned immutable snapshot and reconciled against the current canonical staging fixture/team registry.

- Source rows audited: **19,605 / 19,605**.
- Canonical fixtures examined: **2,496**.
- Exact duplicate source fixture groups: **0**.
- Conflicting duplicate groups: **0**.
- Unique canonical fixture candidates with score agreement: **0**.
- Ambiguous canonical fixture candidates: **0**.
- Rows with both exact-normalized team names represented in the current canonical registry but no matching fixture: **6,495**.
- Rows where at least one team is absent from the current canonical registry: **13,110**.
- Crosswalk rows written: **0**.
- Normalized fixture/result rows written: **0**.
- Database mutations: **0**.
- Model admission / PIT certification: **false**.

The result is a successful identity audit, not a successful canonical mapping. The historical rows retain stable AI Midas source identities; no row was marked `RESOLVED`.

## 2. Archive inventory and season boundaries

| Competition | Source rows | Source period | Season convention |
|---|---:|---|---|
| Brazil Série A | 3,419 | 2016–2024 | Calendar year |
| England Premier League | 3,420 | 2016/17–2024/25 | July–June season boundary |
| France Ligue 1 | 3,171 | 2016/17–2024/25 | July–June season boundary |
| Germany Bundesliga I | 2,754 | 2016/17–2024/25 | July–June season boundary |
| Italy Serie A | 3,421 | 2016/17–2024/25 | July–June season boundary |
| Spain La Liga | 3,420 | 2016/17–2024/25 | July–June season boundary |
| **Total** | **19,605** | | |

Every row preserves the literal source `season` field and date string. A separate derived season key is used only for partitioning and candidate matching: calendar-year seasons for Brazil Série A and July-to-June seasons for the European leagues. Shortened or expanded COVID-era season counts remain as observed; no 380-match assumption or row imputation is applied.

## 3. Stable source-row identity and provenance

Each source row is identified by:

- AI Midas repository and pinned commit.
- Exact CSV path and Git blob SHA-1.
- Exact raw-file SHA-256 from the immutable snapshot manifest.
- Original CSV line number (header is line 1).
- Canonicalized row-content SHA-256.
- Derived source fixture key: `aimidas:<commit>:<path>:<line>:<row-hash-prefix>`.

The row key is a Veltrix provenance identifier, not an upstream provider fixture ID. The source CSVs do not supply a canonical Veltrix fixture ID. Original source date and raw season values remain unchanged.

The reconciliation also re-read the six corresponding staging `provider_responses` and linked `source_observations`, recomputed response SHA-256 hashes from stored raw bytes, and verified their source-approval linkage and non-PIT temporal classification.

## 4. Matching and duplicate policy

Candidate matching is deliberately conservative:

1. Competition must match the explicit archive-to-canonical competition mapping.
2. Home and away order must match; home/away are never swapped.
3. Team names are compared after Unicode accent removal, punctuation normalization and whitespace collapse. No fuzzy matching or unreviewed aliases are used.
4. Candidate dates must be within one calendar day of the canonical UTC kickoff date. The source date is date-only/local-looking and has no proven timezone; it is never converted into a fabricated kickoff timestamp.
5. Derived season keys must agree, preventing cross-season matches.
6. Canonical scores, when present, are a separate corroboration check. A score mismatch or absent result cannot be silently accepted.
7. A unique candidate remains `REVIEW_REQUIRED`; it is never automatically marked `RESOLVED`.
8. Multiple candidates, duplicate conflicts, team ambiguity or missing coverage remain quarantined for reviewer resolution.

Exact duplicate detection uses competition, derived season, source calendar date, ordered normalized teams and full-time score. The audit found no repeated exact identities and no conflicting score pairs.

## 5. Why no canonical candidates were found

The current staging canonical fixture registry examined by this run contains 2,496 fixtures, with competition coverage beginning in November 2025. The six historical archives end no later than 25 May 2025. There is therefore no overlapping canonical fixture date range for the six archives.

The 6,495 rows whose two team names are present in the current registry are not fixture matches: team presence alone cannot establish a fixture identity. The remaining 13,110 rows include historical clubs not represented in the current canonical team registry. Neither group is promoted by inference.

This is a canonical-history coverage gap, not evidence that the AI Midas source rows are duplicates or invalid.

## 6. Workflow and verification

- Workflow: `.github/workflows/phase2-aimidas-historical-identity.yml`
- Run: [#43755219763](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43755219763)
- Code head: `a951513f2518842a03b6305245b66b3591f5ced0`
- Result: **SUCCESS**
- Focused tests: **19 passed**
- Pinned source snapshot: **14/14 files fetched and independently verified**
- Reconciliation: **19,605/19,605 historical rows audited**
- Sanitized aggregate artifact: [historical identity summary](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43755219763/artifacts/14178350008)
- Row-level detail was retained only in the ephemeral workflow runner and was not uploaded. Raw CSV snapshots were not included in the artifact.

The reconciliation transaction was explicitly set read-only and checked `current_database`, `current_user` and `transaction_read_only=on` before reading canonical tables. It reads staging only; production was not accessed.

## 7. Disposition and next work

- Keep all 19,605 source rows as source-attributed retrospective history, not canonical fixtures.
- Do not create AI Midas fixture crosswalks until historical canonical fixture coverage exists and exact reviewer-backed evidence is available.
- Do not resolve AI Midas team names by fuzzy matching. If a later provider archive supplies stable team IDs or a reviewed alias table, rerun the candidate audit with that evidence.
- Keep the Brazil Série B historical 2016–2025 archive gap unchanged; this six-file reconciliation does not cover Brazil Série B.
- Keep all AI Midas historical observations non-PIT. The source repository commit time and Veltrix import time do not prove original row availability.
- Keep average odds outside bookmaker-specific quote, closing-odds, CLV and 98% timestamped-odds certification.
- No model training, prediction publication, value betting, deployment, Telegram delivery, schedule activation or PR merge is authorized by this audit.

**Next component:** build a separate, read-only source-to-source identity report for the 2025/26 AI Midas season files only if their date range overlaps the canonical fixture universe. Do not merge those season files into these six historical archives or blur their season semantics.
