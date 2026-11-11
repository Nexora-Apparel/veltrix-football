import unittest

from app.independent_report_contract import (
    MODEL_PORTFOLIO_ID,
    REPORT_SCHEMA,
    is_publishable_independent_report,
    is_value_betting_authorized_report,
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
            "as_of_date": "2026-11-11",
        }

    def test_report_stays_locked_even_with_release_metadata_until_code_gate_is_enabled(self):
        self.assertFalse(is_publishable_independent_report(self.valid_report()))

    def test_forecast_rows_require_independent_portfolio_and_feature_provenance(self):
        report = self.valid_report()
        report["predictions"] = [{
            "model_portfolio_id": MODEL_PORTFOLIO_ID,
            "legacy_model_dependency": False,
            "probabilities": {"home_win": 0.5, "draw": 0.25, "away_win": 0.25},
            "feature_snapshot_sha256": "b" * 64,
            "model_versions": ["results_history_logistic"],
        }]
        self.assertFalse(is_publishable_independent_report(report))
        report["predictions"][0]["model_portfolio_id"] = "legacy"
        self.assertFalse(is_publishable_independent_report(report))

    def test_legacy_model_labels_cannot_hide_inside_independent_report(self):
        report = self.valid_report()
        report["predictions"] = [{
            "model_portfolio_id": MODEL_PORTFOLIO_ID,
            "legacy_model_dependency": False,
            "model": "experimental_recent_goals_poisson",
            "probabilities": {"home_win": 0.5, "draw": 0.25, "away_win": 0.25},
            "feature_snapshot_sha256": "b" * 64,
            "model_versions": ["results_history_logistic"],
        }]
        self.assertFalse(is_publishable_independent_report(report))

    def test_legacy_report_is_never_publishable(self):
        self.assertFalse(is_publishable_independent_report({
            "predictions": [{"home_team": "Legacy FC", "probabilities": {}}],
            "status": "PUBLISHED",
        }))

    def test_independent_report_without_authorization_is_not_publishable(self):
        report = self.valid_report()
        report["publication_allowed"] = False
        self.assertFalse(is_publishable_independent_report(report))

    def test_value_betting_requires_separate_market_certificate(self):
        report = self.valid_report()
        self.assertFalse(is_value_betting_authorized_report(report))
        report["value_betting_authorized"] = True
        report["value_validation_certificate"] = {
            "status": "CERTIFIED",
            "model_portfolio_id": MODEL_PORTFOLIO_ID,
            "approved_markets": ["BTTS"],
            "alerts_enabled": True,
            "signature_verified": True,
            "certificate_sha256": "b" * 64,
        }
        self.assertFalse(is_value_betting_authorized_report(report))

    def test_value_betting_rejects_partial_or_unverified_certificate(self):
        report = self.valid_report()
        report["value_betting_authorized"] = True
        report["value_validation_certificate"] = {
            "status": "PARTIALLY_VALIDATED",
            "model_portfolio_id": MODEL_PORTFOLIO_ID,
            "approved_markets": ["BTTS"],
            "alerts_enabled": True,
            "signature_verified": True,
            "certificate_sha256": "b" * 64,
        }
        self.assertFalse(is_value_betting_authorized_report(report))

    def test_unverified_or_malformed_release_certificate_is_rejected(self):
        report = self.valid_report()
        report["release_certificate"]["signature_verified"] = False
        self.assertFalse(is_publishable_independent_report(report))
        report = self.valid_report()
        report["release_certificate"]["certificate_sha256"] = "not-a-digest"
        self.assertFalse(is_publishable_independent_report(report))


if __name__ == "__main__":
    unittest.main()
