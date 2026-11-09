import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.provider_team_aliases import (
    AliasRegistryError, alias_pair_is_approved, load_registry, validate_registry,
)


REGISTRY_PATH = Path("data/provider_team_aliases.json")


class ProviderTeamAliasRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry(REGISTRY_PATH)

    def test_registry_contains_twenty_pending_candidates(self):
        self.assertEqual(len(self.registry["candidates"]), 20)
        self.assertTrue(all(
            row["status"] == "pending_independent_verification"
            for row in self.registry["candidates"]
        ))

    def test_pending_candidate_never_matches(self):
        self.assertFalse(alias_pair_is_approved(
            self.registry, "england_premier_league", "2026-27", "360", "762247077"
        ))

    def test_wrong_competition_or_season_never_matches(self):
        self.assertFalse(alias_pair_is_approved(
            self.registry, "england_championship", "2026-27", "360", "762247077"
        ))
        self.assertFalse(alias_pair_is_approved(
            self.registry, "england_premier_league", "2025-26", "360", "762247077"
        ))

    def test_duplicate_striker_id_in_scope_is_rejected(self):
        bad = copy.deepcopy(self.registry)
        bad["candidates"].append(copy.deepcopy(bad["candidates"][0]))
        with self.assertRaises(AliasRegistryError):
            validate_registry(bad)

    def test_same_id_in_distinct_competition_scope_is_not_a_collision(self):
        scoped = copy.deepcopy(self.registry)
        extra = copy.deepcopy(scoped["candidates"][0])
        extra["competition_key"] = "another_competition"
        extra["striker_team_id"] = "999"
        extra["fivedollar_team_id"] = "998"
        scoped["candidates"].append(extra)
        validate_registry(scoped)

    def test_approved_row_requires_evidence_and_reviewer(self):
        approved = copy.deepcopy(self.registry)
        approved["status"] = "approved"
        row = approved["candidates"][0]
        row["status"] = "approved"
        with self.assertRaises(AliasRegistryError):
            validate_registry(approved)
        row["evidence_url"] = "https://provider.example/team/306"
        row["evidence_retrieved_at"] = "2026-11-09T12:00:00Z"
        row["reviewer"] = "independent-review"
        validate_registry(approved)
        self.assertTrue(alias_pair_is_approved(
            approved, "england_premier_league", "2026-27",
            row["striker_team_id"], row["fivedollar_team_id"]
        ))

    def test_approved_evidence_must_have_timezone(self):
        approved = copy.deepcopy(self.registry)
        approved["status"] = "approved"
        row = approved["candidates"][0]
        row.update({
            "status": "approved",
            "evidence_url": "https://provider.example/team/306",
            "evidence_retrieved_at": "2026-11-09T12:00:00",
            "reviewer": "independent-review",
        })
        with self.assertRaises(AliasRegistryError):
            validate_registry(approved)


if __name__ == "__main__":
    unittest.main()
