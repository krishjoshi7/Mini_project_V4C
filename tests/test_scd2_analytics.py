from __future__ import annotations

import unittest

from src.ETL.synthesizer import DataSynthesizer
from src.managers import AnalyticsManager


class CapturingAnalyticsManager(AnalyticsManager):
    def fetch_all(self, query: str, params: tuple = ()):
        self.last_query = query
        return []


class Scd2AnalyticsTests(unittest.TestCase):
    def test_synthesizer_creates_current_and_prior_versions(self):
        synthesizer = DataSynthesizer(rows=100, historical_fraction=0.3)
        employees = synthesizer.generate_base_employee_data()
        history = synthesizer.generate_scd_type_2_history(employees)
        reviews = synthesizer.generate_performance_reviews(employees)

        self.assertEqual(len(employees), 100)
        self.assertEqual(int(history["is_current"].sum()), 100)
        self.assertEqual(len(history), 130)
        self.assertTrue({"performance_score", "attrition_risk"}.issubset(history.columns))
        self.assertTrue((history.loc[~history["is_current"], "end_date"] > history.loc[~history["is_current"], "start_date"]).all())
        self.assertTrue((reviews["review_date"] >= employees["hire_date"]).all())

    def test_department_at_review_uses_effective_date_join(self):
        analytics = CapturingAnalyticsManager()
        analytics.get_top_performers("review")

        self.assertIn("f.review_date >= e.start_date", analytics.last_query)
        self.assertIn("e.end_date IS NULL OR f.review_date < e.end_date", analytics.last_query)
        self.assertNotIn("e.is_current = TRUE", analytics.last_query)

    def test_current_department_uses_current_dimension_version(self):
        analytics = CapturingAnalyticsManager()
        analytics.get_top_performers("current")

        self.assertIn("e.is_current = TRUE", analytics.last_query)
        self.assertNotIn("f.review_date >= e.start_date", analytics.last_query)

    def test_unknown_department_basis_is_rejected(self):
        with self.assertRaises(ValueError):
            CapturingAnalyticsManager().get_top_performers("arbitrary SQL")


if __name__ == "__main__":
    unittest.main()
