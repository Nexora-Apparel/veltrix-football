# VELTRIX 2.0 — Free provider qualification review

Date: 2026-11-14
Scope: public documentation and terms review only. No provider endpoint was called, no key was created, no quota was consumed, and no data was imported.

## Executive decision

No newly reviewed source is promoted to a certified prediction-data provider by this review.

The most useful additional candidate is **OpenLigaDB**, limited to competition coverage it actually lists and subject to operator confirmation for VELTRIX's application scope. It can supplement fixtures and settled scores, but it is not an xG, lineup, injury, player-statistics or odds provider. Its `lastUpdateDateTime` field is a mutable record-update timestamp; it does not, by itself, prove the exact time a particular result revision first became publicly available or prove complete revision history. Therefore, an API snapshot captured today can support prospective capture after the capture time, but old match records fetched today cannot be backdated into point-in-time training evidence.

A second candidate, **football-data.org**, offers fixtures, results, tables, squads and lineups subject to plan/competition coverage. Its free plan is rate-limited (10 requests/minute in the current official documentation). The API exposes `lastUpdated`, but this review has not established a per-revision publication timestamp, complete revision history, or a rights contract that covers every intended VELTRIX use. Keep conditional; do not build an assumption of global free coverage.

**Football API (footballapi.org) is excluded from integration for now.** Its complimentary key is limited to this season's Premier League, 50 calls/day and 10/minute. More importantly, its current terms allow use in one's own apps but prohibit bulk redistribution, bulk collection to rebuild the dataset, and use to build a competing product. VELTRIX is a football prediction product, so this restriction creates a material scope conflict. Do not create an account/key or send requests unless written permission explicitly covers this product.

**StatsBomb Open Data** remains a selected-match historical research source, not a current fixture or broad coverage source. It provides events and lineups for selected matches. Its README requires StatsBomb attribution and logo when publishing research/analysis/insights based on the data. Research-use scope and downstream publication rights must be approved before any VELTRIX production use.

## Provider matrix

| Provider | No-cost access evidence | Useful domains | Temporal/PIT assessment | Decision |
|---|---|---|---|---|
| 5DollarFootballAPI | Existing free-tier credential; five competitions and request limits previously verified | Fixtures, finished results | Existing historical import lacks source publication, recorded-at and complete revision evidence | Keep active-limited; capture new snapshots only through the strict contract |
| OpenFootball World | Public-domain static archive | Historical fixtures/results | Date-only historical records; no publication/revision timestamps | Archive-only; exploratory reconciliation, not PIT training |
| OpenLigaDB | Keyless API; published 60 requests/minute IP limit; fair-use caching/backoff requirements | Fixtures, results, tables, goal events for listed competitions | Per-match `lastUpdateDateTime` and league/group last-change endpoints are update indicators, not proof of first-publication time or complete revision history | Conditional candidate; no dispatch until scope/terms review and source qualification |
| football-data.org | Free registered tier; 10 requests/minute; access depends on plan and competition | Fixtures, results, standings, squads/lineups for eligible resources | `lastUpdated` alone is insufficient to establish historical revision completeness | Conditional candidate; verify exact competition access and intended use |
| StatsBomb Open Data | Public selected-match archive | Events, lineups, selected xG/event data | Historical match archive; not a general live or comprehensive pre-match source | Archive-only research; attribution and rights gate |
| The Odds API | Optional provider; not assumed free | Conditional 1X2, totals, BTTS | Quote-level timestamps possible when legitimately captured; quota and rights gates remain | Optional and locked |
| GOAL API | Credits exhausted | Dormant | No requests until next monthly reset | Hard blocked |
| StrikerAPI | Credits exhausted | Dormant | No requests until next monthly reset | Hard blocked |
| Football API (footballapi.org) | Complimentary Premier League key, 50 calls/day | Fixtures, results, tables, selected match statistics | Its own current terms create a competing-product restriction | Excluded pending written permission |

## OpenLigaDB: qualification details

Official API documentation: https://api.openligadb.de/index.html

Official terms: https://www.openligadb.de/en/terms-of-use

Data license: https://www.openligadb.de/en/license

The API documents season/league match retrieval, match detail, current/last match, team match history and last-change endpoints. The current documented fair-use expectations include:

- Use `getlastchangedate` for inexpensive polling and retrieve full data only when changed.
- Cache centrally.
- Outside live matches, only a few requests per day are usually needed.
- During live matches, at most one request every 30–60 seconds per league.
- Back off exponentially on 429 and 5xx responses.
- Identify the application with a meaningful User-Agent.
- The operator may throttle or block excessive use.

The data is crowd-maintained, has no editorial review, and carries no guarantee of accuracy, completeness or timeliness. The operator describes the service as intended for hobby and specialist applications. VELTRIX must obtain confirmation from the operator before automated recurring collection for a larger/public prediction product.

The data is licensed under ODbL 1.0. Public use requires attribution. Public distribution of a modified database triggers share-alike obligations. API access terms and the data license are separate and both must be followed. Team icon URLs point to third-party hosted images and do not grant image rights.

**Timestamp rule:** store the exact request/retrieval/recording timestamps and preserve the raw response. Keep provider `lastUpdateDateTime` in its own source-update field. Do not relabel it as `source_published_at`, `available_at`, or a complete revision sequence unless provider documentation and evidence establish that exact semantic.

## football-data.org: qualification details

Official API reference: https://www.football-data.org/documentation/api

Current request-throttling policy: https://docs.football-data.org/general/v4/policies.html

The current official documentation describes a registered free plan at 10 requests/minute. Competition access is plan-dependent. The resource catalogue includes matches, teams, standings and other subresources; lineups/squads are not guaranteed for every competition or plan. The API includes update metadata, but a mutable `lastUpdated` value is not enough to reconstruct prior states or certify that every revision was captured.

Before adapter implementation, verify the actual key's competition entitlement, per-endpoint access, retention/reuse terms and whether VELTRIX may store and use the response for model training and public prediction insights. Do not scrape the website as a workaround for API restrictions.

## Football API (footballapi.org): exclusion rationale

Documentation: https://footballapi.org/documentation

Terms: https://footballapi.org/terms

The complimentary plan reads only the current Premier League season, with 50 calls/day and 10 calls/minute. The terms permit use in personal/business apps and showing results to users, but prohibit reselling, redistributing or republishing the data itself in bulk, bulk downloads to rebuild the collection, and using the data to build a competing product. Because VELTRIX's core product is football prediction/analysis, the competing-product clause is a material unresolved restriction. No integration or account creation is authorized by this review.

## StatsBomb Open Data: research boundary

Repository and terms: https://github.com/hudl/open-data

The archive contains selected competitions/seasons, match files, event files and lineup files. Its README asks users who publish, share or distribute research, analysis or insights based on the data to credit StatsBomb and use its logo. This is not comprehensive coverage and is not a current pre-match data feed. Treat it as a separately rights-gated research dataset; do not assume it can populate live fixture coverage or prospective lineup snapshots.

## Capture and certification rules that remain unchanged

1. Preserve exact raw response bytes and SHA-256.
2. Preserve provider/source/endpoint/request identity and request, retrieval, recording and source timestamps separately.
3. Treat source update timestamps according to documented semantics; never infer publication time from retrieval time.
4. Require complete revision-history evidence for historical PIT certification.
5. Resolve canonical fixture/team/competition identity through evidence-backed crosswalks.
6. Evaluate rights at use time for the exact provider, source, domain, competition, purpose and retention scope.
7. Missing data remains missing; no zero-fill, proxy timestamp, or synthetic feature.
8. Provider capability does not imply publication eligibility or model-training eligibility.
9. No live dispatch until a provider has passed terms, rights, endpoint, quota, temporal semantics, parser, persistence and independent audit gates.

## Next actions

1. Ask OpenLigaDB operator whether automated central collection for a public football analytics/prediction product is within acceptable specialist use; retain the answer as rights evidence.
2. Qualify football-data.org only if an existing legitimate credential or free registration is available and the relevant competition access can be verified without exceeding the free rate.
3. Keep Football API excluded unless written permission resolves its competing-product clause.
4. Build an offline OpenLigaDB parser/fixture identity contract using archived sample bytes only after a lawful sample response is obtained; no endpoint calls are part of this review.
5. Continue strict prospective capture using the already-qualified 5Dollar source where its actual endpoint, entitlement and terms permit.
