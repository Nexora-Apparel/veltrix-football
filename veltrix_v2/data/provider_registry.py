"""Provider capability registry for the provider-independent VELTRIX v2 pipeline.

Policy metadata only: no network calls, secrets, credit consumption, or rights
certification. Live adapters must still pass evidence-capture gates.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum


class ProviderState(StrEnum):
    ACTIVE_LIMITED = "ACTIVE_LIMITED"
    ARCHIVE_ONLY = "ARCHIVE_ONLY"
    OPTIONAL_GATED = "OPTIONAL_GATED"
    SUSPENDED_CREDITS = "SUSPENDED_CREDITS"


class DataDomain(StrEnum):
    FIXTURES = "FIXTURES"
    RESULTS = "RESULTS"
    TEAM_FORM = "TEAM_FORM"
    TEAM_STRENGTH = "TEAM_STRENGTH"
    REST_DAYS = "REST_DAYS"
    ODDS_1X2 = "ODDS_1X2"
    ODDS_TOTALS = "ODDS_TOTALS"
    ODDS_BTTS = "ODDS_BTTS"
    EXPECTED_GOALS = "EXPECTED_GOALS"
    LINEUPS = "LINEUPS"
    INJURIES = "INJURIES"
    PLAYER_STATS = "PLAYER_STATS"


class CapabilityState(StrEnum):
    AVAILABLE = "AVAILABLE"
    DERIVED = "DERIVED"
    CONDITIONAL = "CONDITIONAL"
    NOT_VERIFIED = "NOT_VERIFIED"
    UNAVAILABLE = "UNAVAILABLE"
    EXPLORATORY_ONLY = "EXPLORATORY_ONLY"


@dataclass(frozen=True, slots=True)
class Capability:
    domain: DataDomain
    state: CapabilityState
    evidence_note: str


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    provider: str
    source_id: str
    state: ProviderState
    capabilities: tuple[Capability, ...]
    collection_allowed: bool
    note: str

    def capability(self, domain: DataDomain) -> Capability:
        matches = tuple(item for item in self.capabilities if item.domain is domain)
        if len(matches) != 1:
            raise ValueError(f"PROVIDER_CAPABILITY_NOT_UNIQUE:{self.provider}:{domain.value}")
        return matches[0]


def _caps(*items: tuple[DataDomain, CapabilityState, str]) -> tuple[Capability, ...]:
    declared = {domain: (state, note) for domain, state, note in items}
    return tuple(
        Capability(domain, *declared.get(domain, (
            CapabilityState.NOT_VERIFIED, "No verified provider capability contract."
        )))
        for domain in DataDomain
    )


PROVIDER_REGISTRY: tuple[ProviderProfile, ...] = (
    ProviderProfile("5DollarFootballAPI", "5dollarfootballapi", ProviderState.ACTIVE_LIMITED,
        _caps(
            (DataDomain.FIXTURES, CapabilityState.AVAILABLE, "Fixture feed; five accessible competitions and free-tier quota limits apply."),
            (DataDomain.RESULTS, CapabilityState.AVAILABLE, "Finished scores exist; current historical rows lack strict publication/availability and revision evidence."),
            (DataDomain.TEAM_FORM, CapabilityState.DERIVED, "Calculate only from eligible, cutoff-safe result observations."),
            (DataDomain.TEAM_STRENGTH, CapabilityState.DERIVED, "Calculate Elo/goal strengths only from eligible, cutoff-safe results."),
            (DataDomain.REST_DAYS, CapabilityState.CONDITIONAL, "Requires exact timezone-aware kickoff timestamps."),
            (DataDomain.ODDS_1X2, CapabilityState.UNAVAILABLE, "Not an odds source in the qualified contract."),
            (DataDomain.ODDS_TOTALS, CapabilityState.UNAVAILABLE, "Not an odds source in the qualified contract."),
            (DataDomain.ODDS_BTTS, CapabilityState.UNAVAILABLE, "Not an odds source in the qualified contract."),
            (DataDomain.EXPECTED_GOALS, CapabilityState.NOT_VERIFIED, "No qualified xG contract."),
            (DataDomain.LINEUPS, CapabilityState.NOT_VERIFIED, "No qualified lineup contract."),
            (DataDomain.INJURIES, CapabilityState.NOT_VERIFIED, "No qualified injury contract."),
            (DataDomain.PLAYER_STATS, CapabilityState.NOT_VERIFIED, "No qualified player-stat contract."),
        ), True, "Free tier; respect its accessible competitions and request limits."),
    ProviderProfile("OpenFootball", "openfootball-world", ProviderState.ARCHIVE_ONLY,
        _caps(
            (DataDomain.FIXTURES, CapabilityState.CONDITIONAL, "Static archive only; not a live fixture feed."),
            (DataDomain.RESULTS, CapabilityState.AVAILABLE, "Historical scores; imported date-only rows are not point-in-time certifiable."),
            (DataDomain.TEAM_FORM, CapabilityState.EXPLORATORY_ONLY, "Date-only archive rows are exploratory and cannot enter strict point-in-time training."),
            (DataDomain.TEAM_STRENGTH, CapabilityState.EXPLORATORY_ONLY, "Date-only archive rows are exploratory and cannot enter strict point-in-time training."),
            (DataDomain.REST_DAYS, CapabilityState.UNAVAILABLE, "Date-only records do not support exact rest-day calculations."),
            (DataDomain.ODDS_1X2, CapabilityState.UNAVAILABLE, "No odds data."),
            (DataDomain.ODDS_TOTALS, CapabilityState.UNAVAILABLE, "No odds data."),
            (DataDomain.ODDS_BTTS, CapabilityState.UNAVAILABLE, "No odds data."),
            (DataDomain.EXPECTED_GOALS, CapabilityState.UNAVAILABLE, "No xG data."),
            (DataDomain.LINEUPS, CapabilityState.UNAVAILABLE, "No lineup data."),
            (DataDomain.INJURIES, CapabilityState.UNAVAILABLE, "No injury data."),
            (DataDomain.PLAYER_STATS, CapabilityState.UNAVAILABLE, "No player-stat data."),
        ), False, "Static public-domain results archive; no automatic/live retrieval."),
    ProviderProfile("StatsBomb Open Data", "statsbomb-open-data", ProviderState.ARCHIVE_ONLY,
        _caps(
            (DataDomain.FIXTURES, CapabilityState.CONDITIONAL, "Selected historical match lists only; no live fixture feed."),
            (DataDomain.RESULTS, CapabilityState.AVAILABLE, "Selected historical match records; temporal certification must be established independently."),
            (DataDomain.TEAM_FORM, CapabilityState.EXPLORATORY_ONLY, "Historical sample coverage is selective and not a substitute for current competition-wide form."),
            (DataDomain.TEAM_STRENGTH, CapabilityState.EXPLORATORY_ONLY, "Historical sample coverage is selective and not a substitute for current competition-wide ratings."),
            (DataDomain.EXPECTED_GOALS, CapabilityState.CONDITIONAL, "Shot-level StatsBomb xG exists in selected event files; research-use and attribution review required."),
            (DataDomain.LINEUPS, CapabilityState.CONDITIONAL, "Lineup JSON exists for selected historical matches; research-use and attribution review required."),
        ), False, "Static selected-match research archive. No live data; do not use commercially or publish derived material until rights scope is reviewed and attribution requirements are implemented."),
    ProviderProfile("The Odds API", "the-odds-api", ProviderState.OPTIONAL_GATED,
        _caps(
            (DataDomain.FIXTURES, CapabilityState.CONDITIONAL, "Event discovery only; not canonical fixture source."),
            (DataDomain.ODDS_1X2, CapabilityState.CONDITIONAL, "Soccer h2h market; event, region, bookmaker and quote timestamp coverage must be checked."),
            (DataDomain.ODDS_TOTALS, CapabilityState.CONDITIONAL, "Totals coverage must be checked per competition/region/bookmaker."),
            (DataDomain.ODDS_BTTS, CapabilityState.CONDITIONAL, "Event-specific market; verify availability and request budget."),
        ), False, "Optional odds only; rights, quota, account allowance and explicit spend caps gate dispatch."),
    ProviderProfile("GOAL API", "goal-api", ProviderState.SUSPENDED_CREDITS,
        _caps(*((domain, CapabilityState.NOT_VERIFIED, "Dormant while credits are exhausted; do not call.") for domain in DataDomain)),
        False, "No calls, retries, scans or credit checks until reset and requalification."),
    ProviderProfile("StrikerAPI", "strikerapi", ProviderState.SUSPENDED_CREDITS,
        _caps(*((domain, CapabilityState.NOT_VERIFIED, "Dormant while credits are exhausted; do not call.") for domain in DataDomain)),
        False, "No calls, retries, scans or credit checks until next monthly reset and requalification."),
)


def providers_for(domain: DataDomain, *, include_conditional: bool = False) -> tuple[ProviderProfile, ...]:
    """List sources with declared coverage, including static archives."""
    states = {CapabilityState.AVAILABLE, CapabilityState.DERIVED}
    if include_conditional:
        states.add(CapabilityState.CONDITIONAL)
    return tuple(
        profile for profile in PROVIDER_REGISTRY
        if profile.state not in {ProviderState.SUSPENDED_CREDITS}
        and profile.capability(domain).state in states
    )


def dispatchable_providers_for(domain: DataDomain, *, include_conditional: bool = False) -> tuple[ProviderProfile, ...]:
    """Return sources with the static registry switch enabled, not final authorization.

Callers must still independently pass source rights, account, quota, request
budget and provider-specific evidence gates before creating a transport.
"""
    return tuple(
        profile for profile in providers_for(domain, include_conditional=include_conditional)
        if profile.collection_allowed and profile.state is ProviderState.ACTIVE_LIMITED
    )


def assert_provider_dispatch_allowed(provider: str) -> ProviderProfile:
    """Reject statically disabled sources before transport construction.

A successful return is not complete authorization: callers must still pass
rights, account, quota, request-budget and endpoint-specific checks.
"""
    matches = tuple(p for p in PROVIDER_REGISTRY if p.provider == provider)
    if len(matches) != 1:
        raise ValueError("PROVIDER_NOT_REGISTERED")
    profile = matches[0]
    if not profile.collection_allowed or profile.state is not ProviderState.ACTIVE_LIMITED:
        raise PermissionError(f"PROVIDER_COLLECTION_DISABLED:{profile.provider}:{profile.state.value}")
    return profile
