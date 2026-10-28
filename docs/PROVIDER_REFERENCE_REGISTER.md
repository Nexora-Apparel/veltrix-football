# Veltrix Football — Provider Reference Register

This register captures the exact provider references found in the earlier project discussion. A URL in this file is a research starting point, not proof of successful access, free-tier availability, or production suitability.

## Candidate sources from the multi-source plan

### 1. 5DollarFootballAPI
- Website: https://5dollarfootballapi.com/
- Python SDK repository: https://github.com/5dollarfootball-api/football-api-python-sdk
- Intended evaluation: fixtures, results, bookmaker odds and available match statistics.
- **Status (2026-10-28): LIVE AUTH + FIXTURE + ODDS ENDPOINTS VERIFIED.** GitHub Actions authenticated successfully, retrieved today's fixtures, and read a fixture odds board with `1x2`, `btts`, `goal_line`, and `goal_line_fixed` market keys.
- Integrated as the primary fixture/results source in `app/provider_adapters.py`; historical refresh is bounded and records failed dates separately so successful dates are preserved.
- Continue monitoring free-tier coverage, request quotas, and historical gaps. The live check verifies endpoint/schema access, not complete coverage of every competition.

### 2. InferSports
- OpenAPI specification referenced in the earlier discussion: https://github.com/infersports-dev/infersports/blob/main/openapi.yaml
- Intended evaluation: secondary odds and market information.
- **Status: NOT INTEGRATED / NOT VERIFIED.** No credential has been configured for the current integration work. Verify service identity, OpenAPI currency, auth, markets, bookmakers, quotas and timestamps before implementation.

### 3. The Odds API
- Website: https://the-odds-api.com/
- Additional listing referenced in the earlier discussion: https://rapidapi.com/theoddsapi/api/live-sports-odds
- Intended evaluation: supplemental bookmaker odds and market coverage.
- **Status (2026-10-28): LIVE AUTH + SOCCER MARKETS VERIFIED.** Direct API access accepted the configured key and listed 50 active soccer sports. A bounded live probe returned `h2h`, `totals`, and `btts` market keys; the event-specific BTTS endpoint returned prices. The probe consumed three odds credits, leaving 497 at that time.
- Integrated as a quota-bounded supplemental source; the daily report requests only supported competitions represented in the report, and caps event-specific BTTS requests at three.
- The RapidAPI listing is a distinct product/configuration and is not used by this integration.

### 4. Open Matchday
- GitHub repository referenced in the earlier discussion: https://github.com/oladeeayo/open-matchday
- Intended evaluation: supplementary historical fixtures, results and match statistics.
- **Status: NOT INTEGRATED / NOT VERIFIED.** Verify actual data delivery method, coverage, schema, licensing and update cadence. Do not assume a repository name guarantees a live API.

## Separate provider previously investigated: OddsPapi

- RapidAPI documentation/listing referenced earlier: https://rapidapi.com/odds-papi-odds-papi-default/api/odds-api1
- Existing repository integration: `app/oddspapi_odds.py` and `scripts/enrich_oddspapi_odds.py`.
- Repository README describes it as optional odds enrichment using the GitHub Actions secret `ODDSPAPI_API_KEY`, attached after the primary report and matched by exact home/away team names.
- This is distinct from The Odds API and from API-Football/API-Sports. Do not conflate the provider names, keys or API endpoints.
- Existing repository adapter is retained and included as optional post-report enrichment. Its status is separate from The Odds API; confirm fresh live coverage in its own workflow before treating it as healthy.

## Suspended provider — do not use as active dependency

- API-Football / API-Sports v3 was reported by the project owner as suspended.
- `API_FOOTBALL_KEY` must not be required for builds, scheduled reports, history refreshes or production data fetching while suspended.
- Keep historical records and useful code for audit purposes, but disable active calls and ensure failure cannot block the new provider path.

## Integration checklist

For each candidate, record:
1. Exact official product and documentation URL.
2. Credential variable name (never record the credential value).
3. Base URL and API version.
4. Authentication test result and timestamp.
5. Fixtures/results/history/odds capabilities tested separately.
6. Free-tier quota and observed request consumption.
7. Competition and bookmaker coverage observed in responses.
8. Data freshness and market timestamp behavior.
9. Fixture matching and normalization tests.
10. Go/no-go decision with evidence.

Do not put API keys or tokens in this document, source control, logs, screenshots or Telegram messages.
