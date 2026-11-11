import unittest
from collections import Counter

from app.feature_domain_catalogue import FEATURE_DOMAINS
from app.point_in_time_feature_contract import FEATURE_CATALOGUE


class FeatureDomainCatalogueTests(unittest.TestCase):
    def test_every_model_feature_belongs_to_exactly_one_reporting_domain(self):
        counts = Counter(
            feature
            for domain_features in FEATURE_DOMAINS.values()
            for feature in domain_features
        )
        self.assertEqual(set(counts), set(FEATURE_CATALOGUE))
        self.assertTrue(all(count == 1 for count in counts.values()))

    def test_reporting_domains_are_nonempty_and_stably_named(self):
        self.assertTrue(FEATURE_DOMAINS)
        self.assertTrue(all(
            isinstance(name, str) and name and isinstance(features, list) and features
            for name, features in FEATURE_DOMAINS.items()
        ))


if __name__ == "__main__":
    unittest.main()
