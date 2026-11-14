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
    ProviderProfile("5DollarFootballAPI", "5dollarfootballapi", ProviderState.ACTIVE_LIMITED, True,
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
        ), "Free tier; respect its accessible competitions and request limits."),
    ProviderProfile("OpenFootball", "openfootball-world", ProviderState.ARCHIVE_ONLY, False,
        _caps(
            (DataDomain.FIXTURES, CapabilityState.CONDITIONAL, "Static archive only; not a live fixture feed."),
            (DataDomain.RESULTS, CapabilityState.AVAILABLE, "Historical scores; imported date-only rows are not point-in-time certifiable."),
            (DataDomain.TEAM_FORM, CapabilityState.DERIVED, "Exploratory unless source observations independently pass temporal eligibility."),
            (DataDomain.TEAM_STRENGTH, CapabilityState.DERIVED, "Exploratory unless source observations independently pass temporal eligibility."),
            (DataDomain.REST_DAYS, CapabilityState.UNAVAILABLE, "Date-only records do not support exact rest-day calculations."),
            (DataDomain.ODDS_1X2, CapabilityState.UNAVAILABLE, "No odds data."),
            (DataDomain.ODDS_TOTALS, CapabilityState.UNAVAILABLE, "No odds data."),
            (DataDomain.ODDS_BTTS, CapabilityState.UNAVAILABLE, "No odds data."),
            (DataDomain.EXPECTED_GOALS, CapabilityState.UNAVAILABLE, "No xG data."),
            (DataDomain.LINEUPS, CapabilityState.UNAVAILABLE, "No lineup data."),
            (DataDomain.INJURIES, CapabilityState.UNAVAILABLE, "No injury data."),
            (DataDomain.PLAYER_STATS, CapabilityState.UNAVAILABLE, "No player-stat data."),
        ), "Static public-domain results archive; no automatic/live retrieval."),
    ProviderProfile("The Odds API", "the-odds-api", ProviderState.OPTIONAL_GATED, False,
        _caps(
            (DataDomain.FIXTURES, CapabilityState.CONDITIONAL, "Event discovery only; not canonical fixture source."),
            (DataDomain.ODDS_1X2, CapabilityState.CONDITIONAL, "Soccer h2h market; event, region, bookmaker and quote timestamp coverage must be checked."),
            (DataDomain.ODDS_TOTALS, CapabilityState.CONDITIONAL, "Totals coverage must be checked per competition/region/bookmaker."),
            (DataDomain.ODDS_BTTS, CapabilityState.CONDITIONAL, "Event-specific market; verify availability and request budget."),
        ), "Optional odds only; rights, quota, account allowance and explicit spend caps gate dispatch."),
    ProviderProfile("GOAL API", "goal-api", ProviderState.SUSPENDED_CREDITS, False,
        _caps(*((domain, CapabilityState.NOT_VERIFIED, "Dormant while credits are exhausted; do not call.") for domain in DataDomain)),
        "No calls, retries, scans or credit checks until reset and requalification."),
    ProviderProfile("StrikerAPI", "strikerapi", ProviderState.SUSPENDED_CREDITS, False,
        _caps(*((domain, CapabilityState.NOT_VERIFIED, "Dormant while credits are exhausted; do not call.") for domain in DataDomain)),
        "No calls, retries, scans or credit checks until next monthly reset and requalification."),
)


def providers_for(domain: DataDomain, *, include_conditional: bool = False) -> tuple[ProviderProfile, ...]:
    """List collection-enabled providers with usable declared coverage."""
    states = {CapabilityState.AVAILABLE, CapabilityState.DERIVED}
    if include_conditional:
        states.add(CapabilityState.CONDITIONAL)
    return tuple(
        profile for profile in PROVIDER_REGISTRY
        if profile.collection_allowed
        and profile.state is ProviderState.ACTIVE_LIMITED
        and profile.capability(domain).state in states
    )


def assert_provider_dispatch_allowed(provider: str) -> ProviderProfile:
    """Fail closed before transport construction or request dispatch."""
    matches = tuple(p for p in PROVIDER_REGISTRY if p.provider == provider)
    if len(matches) != 1:
        raise ValueError("PROVIDER_NOT_REGISTERED")
    profile = matches[0]
    if not profile.collection_allowed or profile.state is not ProviderState.ACTIVE_LIMITED:
        raise PermissionError(f"PROVIDER_COLLECTION_DISABLED:{profile.provider}:{profile.state.value}")
    return profile
