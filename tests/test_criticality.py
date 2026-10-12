<<<<<<< HEAD

"""Tests for Project BlindSpot criticality scoring."""

import sys
import unittest
from pathlib import Path

# Allow tests to run directly from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.assessment.criticality import (
    WEIGHTS,
    calculate_criticality,
)


class TestCriticalityScoring(unittest.TestCase):

    def setUp(self):
        self.complete_ratings = {
            "data_sensitivity": 5,
            "operational_dependency": 4,
            "regulatory_exposure": 3,
            "payment_involvement": 2,
            "annual_data_volume": 1,
        }

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0)

    def test_complete_score(self):
        result = calculate_criticality(self.complete_ratings)

        expected = (
            (5 / 5) * 0.30
            + (4 / 5) * 0.25
            + (3 / 5) * 0.20
            + (2 / 5) * 0.15
            + (1 / 5) * 0.10
        ) * 100

        self.assertAlmostEqual(result.score, expected, places=1)
        self.assertEqual(result.coverage_percent, 100.0)
        self.assertEqual(result.known_factors, 5)
        self.assertEqual(len(result.missing_factors), 0)

    def test_all_high_ratings(self):
        ratings = {factor: 5 for factor in WEIGHTS}
        result = calculate_criticality(ratings)

        self.assertEqual(result.score, 100.0)

    def test_all_low_ratings(self):
        ratings = {factor: 1 for factor in WEIGHTS}
        result = calculate_criticality(ratings)

        self.assertEqual(result.score, 20.0)

    def test_missing_factor_does_not_produce_final_score(self):
        ratings = self.complete_ratings.copy()
        ratings["annual_data_volume"] = None

        result = calculate_criticality(ratings)

        self.assertIsNone(result.score)
        self.assertIn(
            "annual_data_volume",
            result.missing_factors,
        )
        self.assertLess(result.coverage_percent, 100.0)
        self.assertEqual(
            result.status,
            "Incomplete — review required",
        )

    def test_invalid_rating_is_rejected(self):
        ratings = self.complete_ratings.copy()
        ratings["data_sensitivity"] = 6

        with self.assertRaises(ValueError):
            calculate_criticality(ratings)

    def test_boolean_rating_is_rejected(self):
        ratings = self.complete_ratings.copy()
        ratings["data_sensitivity"] = True

        with self.assertRaises(ValueError):
            calculate_criticality(ratings)

    def test_unknown_factor_name_is_not_scored(self):
        ratings = self.complete_ratings.copy()
        ratings["unknown_factor"] = 5

        # Extra keys do not alter the five defined factors.
        result = calculate_criticality(ratings)
        self.assertEqual(result.score, 70.0)

    def test_no_criticality_tier_is_invented(self):
        result = calculate_criticality(self.complete_ratings)

        self.assertIn(
            "thresholds pending approval",
            result.status,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
=======

"""Tests for Project BlindSpot criticality scoring."""

import sys
import unittest
from pathlib import Path

# Allow tests to run directly from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.assessment.criticality import (
    WEIGHTS,
    calculate_criticality,
)


class TestCriticalityScoring(unittest.TestCase):

    def setUp(self):
        self.complete_ratings = {
            "data_sensitivity": 5,
            "operational_dependency": 4,
            "regulatory_exposure": 3,
            "payment_involvement": 2,
            "annual_data_volume": 1,
        }

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0)

    def test_complete_score(self):
        result = calculate_criticality(self.complete_ratings)

        expected = (
            (5 / 5) * 0.30
            + (4 / 5) * 0.25
            + (3 / 5) * 0.20
            + (2 / 5) * 0.15
            + (1 / 5) * 0.10
        ) * 100

        self.assertAlmostEqual(result.score, expected, places=1)
        self.assertEqual(result.coverage_percent, 100.0)
        self.assertEqual(result.known_factors, 5)
        self.assertEqual(len(result.missing_factors), 0)

    def test_all_high_ratings(self):
        ratings = {factor: 5 for factor in WEIGHTS}
        result = calculate_criticality(ratings)

        self.assertEqual(result.score, 100.0)

    def test_all_low_ratings(self):
        ratings = {factor: 1 for factor in WEIGHTS}
        result = calculate_criticality(ratings)

        self.assertEqual(result.score, 20.0)

    def test_missing_factor_does_not_produce_final_score(self):
        ratings = self.complete_ratings.copy()
        ratings["annual_data_volume"] = None

        result = calculate_criticality(ratings)

        self.assertIsNone(result.score)
        self.assertIn(
            "annual_data_volume",
            result.missing_factors,
        )
        self.assertLess(result.coverage_percent, 100.0)
        self.assertEqual(
            result.status,
            "Incomplete — review required",
        )

    def test_invalid_rating_is_rejected(self):
        ratings = self.complete_ratings.copy()
        ratings["data_sensitivity"] = 6

        with self.assertRaises(ValueError):
            calculate_criticality(ratings)

    def test_boolean_rating_is_rejected(self):
        ratings = self.complete_ratings.copy()
        ratings["data_sensitivity"] = True

        with self.assertRaises(ValueError):
            calculate_criticality(ratings)

    def test_unknown_factor_name_is_not_scored(self):
        ratings = self.complete_ratings.copy()
        ratings["unknown_factor"] = 5

        # Extra keys do not alter the five defined factors.
        result = calculate_criticality(ratings)
        self.assertEqual(result.score, 70.0)

    def test_no_criticality_tier_is_invented(self):
        result = calculate_criticality(self.complete_ratings)

        self.assertIn(
            "thresholds pending approval",
            result.status,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
>>>>>>> origin/main
