from veltrix_v2.identity import TeamCrosswalk, resolve_team


def row(**overrides):
    values = dict(provider="strikerapi", competition_key="EPL", season="2026",
                  provider_team_id="team-12", canonical_team_id="veltrix-team-9",
                  evidence_ref="audit:crosswalk-12", status="approved")
    values.update(overrides)
    return TeamCrosswalk(**values)


def test_only_approved_scoped_crosswalk_resolves():
    rows = (row(status="candidate"), row(provider_team_id="team-13"))
    assert resolve_team(rows, provider="strikerapi", competition_key="EPL",
                        season="2026", provider_team_id="team-12") is None
    assert resolve_team((row(),), provider="strikerapi", competition_key="EPL",
                        season="2026", provider_team_id="team-12") == "veltrix-team-9"


def test_crosswalk_does_not_leak_across_competition_or_season():
    assert resolve_team((row(),), provider="strikerapi", competition_key="NWSL",
                        season="2026", provider_team_id="team-12") is None
    assert resolve_team((row(),), provider="strikerapi", competition_key="EPL",
                        season="2025", provider_team_id="team-12") is None


def test_ambiguous_approved_mapping_fails_closed():
    with pytest.raises(ValueError, match="multiple approved"):
        resolve_team((row(), row(canonical_team_id="another-team")),
                     provider="strikerapi", competition_key="EPL",
                     season="2026", provider_team_id="team-12")


import pytest
