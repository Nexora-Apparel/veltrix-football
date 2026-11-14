import copy
import unittest
from pathlib import Path

from app.provider_team_aliases import (
    AliasRegistryError, alias_pair_is_approved, load_registry, validate_registry,
)

REGISTRY_PATH = Path("data/provider_team_aliases.json")


def fully_approved_copy(registry, timestamp="2026-11-09T12:00:00Z"):
    approved = copy.deepcopy(registry)
    approved["status"] = "approved"
    for row in approved["candidates"]:
        row.update({
            "status": "approved",
            "evidence_url": f"https://provider.example/team/{row['striker_team_id']}",
            "evidence_retrieved_at": timestamp,
            "reviewer": "independent-review",
        })
    return approved


class ProviderTeamAliasRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry(REGISTRY_PATH)

    def test_registry_contains_twenty_approved_scoped_candidates(self):
        self.assertEqual(len(self.registry["candidates"]), 20)
        self.assertEqual(self.registry["status"], "approved")
        self.assertTrue(all(row["status"] == "approved" for row in self.registry["candidates"]))
        self.assertTrue(all(row["competition_key"] == "england_premier_league" and row["season"] == "2026-27" for row in self.registry["candidates"]))
        self.assertTrue(all(row["catalogue_verified"] and row["crosswalk_fixture_support_count"] >= 3 for row in self.registry["candidates"]))

    def test_pending_candidate_never_matches(self):
        review_only = copy.deepcopy(self.registry)
        review_only["status"] = "review_only"
        self.assertFalse(alias_pair_is_approved(
            review_only, "england_premier_league", "2026-27", "360", "762247077"
        ))
        pending = copy.deepcopy(self.registry)
        pending["candidates"][0]["status"] = "pending_independent_verification"
        with self.assertRaises(AliasRegistryError):
            validate_registry(pending)

    def test_wrong_competition_or_season_never_matches(self):
        approved = fully_approved_copy(self.registry)
        self.assertFalse(alias_pair_is_approved(
            approved, "england_championship", "2026-27", "360", "762247077"
        ))
        self.assertFalse(alias_pair_is_approved(
            approved, "england_premier_league", "2025-26", "360", "762247077"
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

    def test_activation_requires_every_candidate_to_be_evidenced(self):
        approved = copy.deepcopy(self.registry)
        approved["candidates"][0]["status"] = "pending_independent_verification"
        with self.assertRaises(AliasRegistryError):
            validate_registry(approved)
        approved = fully_approved_copy(self.registry)
        validate_registry(approved)
        row = approved["candidates"][0]
        self.assertTrue(alias_pair_is_approved(
            approved, "england_premier_league", "2026-27",
            row["striker_team_id"], row["fivedollar_team_id"]
        ))

    def test_approved_evidence_must_have_timezone(self):
        approved = fully_approved_copy(self.registry, timestamp="2026-11-09T12:00:00")
        with self.assertRaises(AliasRegistryError):
            validate_registry(approved)


if __name__ == "__main__":
    unittest.main()
