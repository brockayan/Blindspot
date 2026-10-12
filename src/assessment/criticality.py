
"""Explainable vendor criticality scoring for Project BlindSpot.

Important:
- Criticality measures business importance, not AI usage or security risk.
- Missing information stays unknown.
- Criticality weights and thresholds require case-guidance validation.
- No final tier is assigned automatically by this draft.
"""

from dataclasses import dataclass, asdict
import re
from typing import Optional


WEIGHTS = {
    "data_sensitivity": 0.30,
    "operational_dependency": 0.25,
    "regulatory_exposure": 0.20,
    "payment_involvement": 0.15,
    "annual_data_volume": 0.10,
}


@dataclass
class CriticalityResult:
    score: Optional[float]
    status: str
    coverage_percent: float
    known_factors: int
    total_factors: int
    factor_ratings: dict
    factor_explanations: dict
    missing_factors: list
    rationale: str

    def to_dict(self):
        return asdict(self)


def _normalise(value):
    """Convert a supplied value into a comparable string."""
    if value is None:
        return ""

    try:
        # pandas NaN without importing pandas in this module
        if value != value:
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip().casefold()


def rate_data_sensitivity(value):
    """Map only clear, explicitly supplied classification labels."""
    text = _normalise(value)

    mapping = {
        "public": 1,
        "low": 1,
        "internal": 3,
        "business": 3,
        "confidential": 4,
        "high": 5,
        "restricted": 5,
        "highly sensitive": 5,
        "regulated": 5,
    }

    if not text:
        return None, "Data classification is missing."

    for label, rating in mapping.items():
        if text == label:
            return rating, f"Classification '{value}' mapped to {rating}/5."

    return None, (
        f"Classification '{value}' has no approved mapping; "
        "manual review is required."
    )


def rate_operational_dependency(value):
    """Map clear dependency labels to draft ratings."""
    text = _normalise(value)

    mapping = {
        "low": 1,
        "low dependency": 1,
        "moderate": 3,
        "medium": 3,
        "moderate dependency": 3,
        "high": 4,
        "high dependency": 4,
        "critical": 5,
        "critical dependency": 5,
    }

    if not text:
        return None, "Operational dependency is missing."

    if text in mapping:
        rating = mapping[text]
        return rating, (
            f"Dependency '{value}' mapped to {rating}/5 "
            "using the draft rubric."
        )

    return None, (
        f"Dependency '{value}' has no approved mapping; "
        "manual review is required."
    )


def rate_numeric_factor(value, approved_bands=None):
    """Rate a numeric factor only when approved bands are provided.

    approved_bands must be a sequence of:
        (minimum, maximum, rating)

    Example:
        [(0, 1000, 1), (1001, 10000, 3), (10001, float("inf"), 5)]

    These example bands are illustrative only and must not be used
    until the project team approves actual thresholds.
    """
    if approved_bands is None:
        return None, (
            "Numeric rating bands have not been approved; "
            "manual review is required."
        )

    if value is None or not str(value).strip():
        return None, "Numeric input is missing."

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, (
            f"'{value}' is not a directly usable number. "
            "Normalize units or provide an approved category."
        )

    for minimum, maximum, rating in approved_bands:
        if minimum <= number <= maximum:
            if rating not in range(1, 6):
                raise ValueError("Ratings must be integers from 1 to 5.")

            return rating, (
                f"Value {number:g} matched an approved band "
                f"and received {rating}/5."
            )

    return None, "Value does not fall within an approved numeric band."


def _normalise_header(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _explicit_rating(value):
    """Accept only an explicitly supplied integer rating from 1 to 5."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer() and 1 <= number <= 5:
        return int(number)
    return None


def _ordinal_category(value):
    text = _normalise(value)
    categories = {
        "very low": 1,
        "low": 2,
        "limited": 2,
        "moderate": 3,
        "medium": 3,
        "high": 4,
        "very high": 5,
        "critical": 5,
    }
    return categories.get(text)


def rate_inventory_row(row):
    """Derive only transparent, directly supported inventory ratings.

    Numeric annual-volume values deliberately remain unassessed because the
    project has no approved volume bands. Explicit 1–5 rating columns and
    unambiguous ordinal categories can be assessed automatically.
    """
    aliases = {
        "data_sensitivity": {
            "datasensitivity", "datasensitivityrating", "dataclassification",
            "sensitivityrating",
        },
        "operational_dependency": {
            "operationaldependency", "operationaldependencyrating",
            "servicecriticalityrating",
        },
        "regulatory_exposure": {
            "regulatoryexposure", "regulatoryexposurerating",
            "regulatoryriskrating",
        },
        "payment_involvement": {
            "paymentinvolvement", "paymentinvolvementrating",
            "paymentprocessing",
        },
        "annual_data_volume": {
            "annualdatavolume", "annualdatavolumerating", "datavolumerating",
        },
    }
    normalized_columns = {
        _normalise_header(column): column
        for column in row.index
    }
    ratings = {}
    notes = {}

    for factor, candidate_headers in aliases.items():
        column = next(
            (
                normalized_columns[header]
                for header in candidate_headers
                if header in normalized_columns
            ),
            None,
        )
        if column is None:
            ratings[factor] = None
            notes[factor] = "No recognized inventory field; requires review."
            continue

        value = row.get(column)
        header_key = _normalise_header(column)
        rating = None
        explanation = ""

        if header_key.endswith(("rating", "score")):
            rating = _explicit_rating(value)
            explanation = (
                "Explicit inventory rating accepted."
                if rating is not None
                else "Rating column must contain an integer from 1 to 5."
            )
        elif factor == "data_sensitivity":
            rating, explanation = rate_data_sensitivity(value)
        elif factor == "operational_dependency":
            rating, explanation = rate_operational_dependency(value)
        elif factor == "regulatory_exposure":
            rating = _ordinal_category(value)
            if _normalise(value) in {"none", "no", "not applicable"}:
                rating = 1
            explanation = (
                f"Recognized ordinal category '{value}' mapped to {rating}/5."
                if rating is not None
                else "Regulatory exposure category is not mapped."
            )
        elif factor == "payment_involvement":
            text = _normalise(value)
            if text in {"no", "none", "false", "not involved"}:
                rating = 1
            elif text in {"yes", "true", "high", "significant", "involved"}:
                rating = 5
            else:
                rating = _ordinal_category(value)
            explanation = (
                f"Recognized payment category '{value}' mapped to {rating}/5."
                if rating is not None
                else "Payment involvement category is not mapped."
            )
        elif factor == "annual_data_volume":
            rating = _ordinal_category(value)
            explanation = (
                f"Recognized volume category '{value}' mapped to {rating}/5."
                if rating is not None
                else (
                    "Annual volume is unassessed: numeric volume bands have "
                    "not been approved."
                )
            )

        ratings[factor] = rating
        notes[factor] = f"{explanation} Source field: {column}; value: {value!s}"

    return ratings, notes


def initialize_inventory_criticality(inventory):
    """Create an initial explainable assessment for each valid vendor row."""
    assessments = {}
    seen_vendor_ids = set()
    for _, row in inventory.iterrows():
        vendor_id = str(row.get("Vendor ID", "")).strip()
        vendor_name = str(row.get("Vendor Name", "")).strip()
        if (
            not vendor_id
            or vendor_id.casefold() == "nan"
            or not vendor_name
            or vendor_name.casefold() == "nan"
        ):
            continue
        if vendor_id.casefold() in seen_vendor_ids:
            continue
        seen_vendor_ids.add(vendor_id.casefold())
        ratings, notes = rate_inventory_row(row)
        assessments[vendor_id] = {
            "vendor_name": vendor_name,
            "ratings": ratings,
            "notes": notes,
            "result": calculate_criticality(ratings),
            "auto_calculated": True,
        }
    return assessments


def calculate_criticality(
    factor_ratings,
    approved_weights=None,
):
    """Calculate an explainable weighted criticality score.

    factor_ratings:
        Dictionary of factor names to ratings from 1 to 5.
        Use None for unknown values.

    approved_weights:
        Optional validated weight dictionary. Defaults to draft weights.

    Policy:
        If any factor is unknown, this draft does not publish a final
        score or tier. It reports coverage and explains missing factors.
    """
    weights = approved_weights or WEIGHTS

    if set(weights) != set(WEIGHTS):
        raise ValueError(
            "Weights must include exactly the five criticality factors."
        )

    if any(weight < 0 for weight in weights.values()):
        raise ValueError("Weights cannot be negative.")

    if sum(weights.values()) <= 0:
        raise ValueError("At least one weight must be positive.")

    ratings = {}
    explanations = {}
    missing = []

    for factor in WEIGHTS:
        value = factor_ratings.get(factor)

        if value is None:
            ratings[factor] = None
            explanations[factor] = "Unknown — no approved rating supplied."
            missing.append(factor)
            continue

        if isinstance(value, bool) or value not in range(1, 6):
            raise ValueError(
                f"{factor} must be an integer from 1 to 5, or None."
            )

        ratings[factor] = value
        explanations[factor] = (
            f"Rating {value}/5; weighted contribution "
            f"{value / 5 * weights[factor] * 100:.1f} points."
        )

    known = [
        factor for factor, rating in ratings.items()
        if rating is not None
    ]

    coverage = (
        sum(weights[factor] for factor in known)
        / sum(weights.values())
        * 100
    )

    # The rubric says not to silently renormalize an incomplete score.
    if missing:
        return CriticalityResult(
            score=None,
            status="Incomplete — review required",
            coverage_percent=round(coverage, 1),
            known_factors=len(known),
            total_factors=len(WEIGHTS),
            factor_ratings=ratings,
            factor_explanations=explanations,
            missing_factors=missing,
            rationale=(
                "No final score assigned because one or more factors "
                "are unknown. Complete the missing factors or apply "
                "an explicitly approved incomplete-data policy."
            ),
        )

    weighted_score = sum(
        (ratings[factor] / 5) * weights[factor]
        for factor in WEIGHTS
    ) / sum(weights.values()) * 100

    return CriticalityResult(
        score=round(weighted_score, 1),
        status="Calculated — tier thresholds pending approval",
        coverage_percent=100.0,
        known_factors=len(known),
        total_factors=len(WEIGHTS),
        factor_ratings=ratings,
        factor_explanations=explanations,
        missing_factors=[],
        rationale=(
            "All five factors are rated. The score is the weighted "
            "average of the approved 1–5 factor ratings, normalized "
            "to 0–100. No criticality tier is assigned because "
            "thresholds have not yet been approved."
        ),
    )
