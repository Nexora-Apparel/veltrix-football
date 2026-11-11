import unittest

from app.independent_report_contract import (
    MODEL_PORTFOLIO_ID,
    REPORT_SCHEMA,
    is_publishable_independent_report,
)


class IndependentReportContractTests(unittest.TestCase):
    def valid_report(self):
        return {
            "report_schema": REPORT_SCHEMA,
            "model_portfolio_id": MODEL_PORTFOLIO_ID,
            "legacy_model_dependency": False,
            "publication_allowed": True,
            "release_certificate": {
                "status": "CERTIFIED",
                "publication_authorized": True,
                "signature_verified": True,
                "certificate_sha256": "a" * 64,
                "model_portfolio_id": MODEL_PORTFOLIO_ID,
            },
            "predictions": [],
        }

    def test_valid_independent_report_requires_release_authorization(self):
        self.assertTrue(is_publishable_independent_report(self.valid_report()))

    def test_legacy_report_is_never_publishable(self):
        self.assertFalse(is_publishable_independent_report({
            "predictions": [{"home_team": "Legacy FC", "probabilities": {}}],
            "status": "PUBLISHED",
        }))

    def test_independent_report_without_authorization_is_not_publishable(self):
        report = self.valid_report()
        report["publication_allowed"] = False
        self.assertFalse(is_publishable_independent_report(report))

    def test_unverified_or_malformed_release_certificate_is_rejected(self):
        report = self.valid_report()
        report["release_certificate"]["signature_verified"] = False
        self.assertFalse(is_publishable_independent_report(report))
        report = self.valid_report()
        report["release_certificate"]["certificate_sha256"] = "not-a-digest"
        self.assertFalse(is_publishable_independent_report(report))


if __name__ == "__main__":
    unittest.main()
