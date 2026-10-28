# Veltrix Football — Provider Reference Register

This register captures the exact provider references found in the earlier project discussion. A URL in this file is a research starting point, not proof of successful access, free-tier availability, or production suitability.

## Candidate sources from the multi-source plan

### 1. 5DollarFootballAPI
- Website: https://5dollarfootballapi.com/
- Python SDK repository: https://github.com/5dollarfootball-api/football-api-python-sdk
- Intended evaluation: fixtures, results, bookmaker odds and available match statistics.
- Verify: official docs and base URL, authentication, endpoint coverage, free/paid quotas, historical depth, odds market names, update cadence, and SDK maintenance.

### 2. InferSports
- OpenAPI specification referenced in the earlier discussion: https://github.com/infersports-dev/infersports/blob/main/openapi.yaml
- Intended evaluation: secondary odds and market information.
- Verify: service identity, whether the OpenAPI spec is current, authentication, available markets, bookmaker coverage, quota and timestamp semantics before implementing.

### 3. The Odds API
- Website: https://the-odds-api.com/
- Additional listing referenced in the earlier discussion: https://rapidapi.com/theoddsapi/api/live-sports-odds
- Intended evaluation: supplemental bookmaker odds and market coverage.
- Verify whether direct access or the RapidAPI listing is the intended product, since their credentials, endpoints and limits may differ. Do not mix their configurations.

### 4. Open Matchday
- GitHub repository referenced in the earlier discussion: https://github.com/oladeeayo/open-matchday
- Intended evaluation: supplementary historical fixtures, results and match statistics.
- Verify actual data delivery method, coverage, schema, licensing and update cadence. Do not assume a repository name guarantees a live API.

## Separate provider previously investigated: OddsPapi

- RapidAPI documentation/listing referenced earlier: https://rapidapi.com/odds-papi-odds-papi-default/api/odds-api1
- Existing repository integration: `app/oddspapi_odds.py` and `scripts/enrich_oddspapi_odds.py`.
- Repository README describes it as optional odds enrichment using the GitHub Actions secret `ODDSPAPI_API_KEY`, attached after the primary report and matched by exact home/away team names.
- This is distinct from The Odds API and from API-Football/API-Sports. Do not conflate the provider names, keys or API endpoints.
- Verify the current secret configuration and live access before treating it as operational.

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
