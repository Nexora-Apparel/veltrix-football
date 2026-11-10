import ast
import unittest
from pathlib import Path

from app.team_name_normalization import normalize_team_name


class TeamNameNormalizationTests(unittest.TestCase):
    def test_explicit_aliases_normalize_without_fuzzy_matching(self):
        self.assertEqual(normalize_team_name("Man Utd"), "manchesterunited")
        self.assertEqual(normalize_team_name("PSG"), "parissaintgermain")
        self.assertEqual(normalize_team_name("FC Barcelona"), "barcelona")
        self.assertEqual(normalize_team_name("Bayern München"), "bayernmunich")

    def test_women_and_reserve_squads_remain_distinct(self):
        self.assertNotEqual(
            normalize_team_name("Arsenal"),
            normalize_team_name("Arsenal Women"),
        )
        self.assertNotEqual(
            normalize_team_name("Real Madrid"),
            normalize_team_name("Real Madrid B"),
        )

    def test_unknown_names_are_normalized_but_not_fuzzy_aliased(self):
        self.assertEqual(
            normalize_team_name("Some Unknown Club FC"),
            "someunknownclub",
        )
        self.assertNotEqual(
            normalize_team_name("Some Unknown Club"),
            normalize_team_name("Some Unknown Club United"),
        )

    def test_provider_adapters_no_longer_import_legacy_prediction_pipeline(self):
        source = Path("app/provider_adapters.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        self.assertNotIn("app.live_predictions", imports)
        self.assertIn("app.team_name_normalization", imports)


if __name__ == "__main__":
    unittest.main()
