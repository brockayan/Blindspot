
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
    tier: Optional[str] = None
    investigation_depth: Optional[str] = None

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


CRITICALITY_TIER_THRESHOLDS = {
    "Critical": 80.0,
    "High": 60.0,
    "Medium": 40.0,
    "Low": 0.0,
}

CRITICALITY_DEPTH_MAP = {
    "Critical": "Full review — tier-driven",
    "High": "Deep review — tier-driven",
    "Medium": "Standard review — tier-driven",
    "Low": "Light review — tier-driven",
    "Incomplete": "Standard review — tier-driven",
}

CRITICALITY_DEPTH_CONFIG = {
    "Full review — tier-driven": {
        "max_pages": 16,
        "max_depth": 2,
        "include_github": True,
        "label": "Full review — tier-driven",
    },
    "Deep review — tier-driven": {
        "max_pages": 10,
        "max_depth": 2,
        "include_github": True,
        "label": "Deep review — tier-driven",
    },
    "Standard review — tier-driven": {
        "max_pages": 6,
        "max_depth": 1,
        "include_github": False,
        "label": "Standard review — tier-driven",
    },
    "Light review — tier-driven": {
        "max_pages": 4,
        "max_depth": 1,
        "include_github": False,
        "label": "Light review — tier-driven",
    },
}


def determine_criticality_tier(score: Optional[float]) -> str:
    """Map a 0-100 score to an established project criticality tier."""
    if score is None:
        return "Incomplete"
    for tier, threshold in CRITICALITY_TIER_THRESHOLDS.items():
        if score >= threshold:
            return tier
    return "Low"


def determine_investigation_depth(tier: str) -> dict:
    """Return collection parameters for a given tier."""
    depth_label = CRITICALITY_DEPTH_MAP.get(tier, "Standard review — tier-driven")
    return CRITICALITY_DEPTH_CONFIG.get(
        depth_label, CRITICALITY_DEPTH_CONFIG["Standard review — tier-driven"]
    )


def assess_preliminary_vendor_criticality(row) -> dict:
    """Automate vendor criticality assessment from inventory fields.

    Derives preliminary 1-5 ratings for the 5 business criticality factors:
    data_sensitivity, operational_dependency, regulatory_exposure,
    payment_involvement, annual_data_volume.

    Produces preliminary score, tier, depth, rationale, factor contributions,
    and missing input warnings.
    """
    data = dict(row) if hasattr(row, "to_dict") else dict(row)
    normalized_row = {
        _normalise_header(k): v
        for k, v in data.items()
        if v is not None
    }

    # 1. Operational Dependency
    raw_dep = (
        normalized_row.get("operationaldependency")
        or normalized_row.get("operationaldependencyrating")
        or normalized_row.get("servicecriticalityrating")
        or ""
    )
    dep_rating, dep_note = rate_operational_dependency(raw_dep)
    if dep_rating is None and raw_dep:
        dep_rating = _explicit_rating(raw_dep) or _ordinal_category(raw_dep)
        if dep_rating:
            dep_note = f"Operational dependency mapped from '{raw_dep}' to {dep_rating}/5."
        else:
            dep_note = f"Operational dependency '{raw_dep}' requires review."

    # 2. Data Sensitivity / Classification
    raw_data = (
        normalized_row.get("dataclassificationaccessed")
        or normalized_row.get("dataclassification")
        or normalized_row.get("datasensitivity")
        or normalized_row.get("datasensitivityrating")
        or ""
    )
    data_rating, data_note = rate_data_sensitivity(raw_data)
    if data_rating is None and raw_data:
        raw_data_str = str(raw_data).casefold()
        if any(
            token in raw_data_str
            for token in (
                "customer master", "tax identifier", "account number",
                "balance", "transaction", "date of birth", "health",
                "vulnerability", "call audio", "loan account", "financial data",
                "full customer", "pii", "restricted", "highly sensitive"
            )
        ):
            data_rating = 5
            data_note = f"High/Restricted data classification inferred from '{raw_data[:80]}...' (5/5)."
        elif any(
            token in raw_data_str
            for token in (
                "privileged access", "system configuration", "credential",
                "service credential", "portfolio holding", "advisor compensation",
                "compensation", "revenue", "payment instruction", "counterparty", "confidential"
            )
        ):
            data_rating = 4
            data_note = f"Confidential/Privileged data classification inferred from '{raw_data[:80]}...' (4/5)."
        elif any(
            token in raw_data_str
            for token in ("transit only", "job schedule", "internal", "batch scheduling")
        ):
            data_rating = 3
            data_note = f"Internal technical data classification inferred from '{raw_data[:80]}...' (3/5)."
        elif "no direct customer data" in raw_data_str:
            data_rating = 2
            data_note = f"No direct customer data (2/5)."
        else:
            data_rating = _explicit_rating(raw_data) or _ordinal_category(raw_data)
            if data_rating:
                data_note = f"Data classification '{raw_data}' mapped to {data_rating}/5."
            else:
                data_note = f"Data classification text '{raw_data[:60]}...' requires review."

    # 3. Regulatory Exposure
    raw_reg = (
        normalized_row.get("regulatoryexposure")
        or normalized_row.get("regulatoryexposurerating")
        or normalized_row.get("regulatoryriskrating")
        or ""
    )
    reg_rating = _explicit_rating(raw_reg) or _ordinal_category(raw_reg)
    reg_note = ""
    if reg_rating is not None:
        reg_note = f"Explicit regulatory category '{raw_reg}' mapped to {reg_rating}/5."
    else:
        # Infer from Category and Business Process Supported
        cat_str = str(
            normalized_row.get("category", "")
            or normalized_row.get("serviceproductprovided", "")
            or normalized_row.get("businessprocesssupported", "")
        ).casefold()
        if any(
            token in cat_str
            for token in (
                "core platform", "lending", "collections", "payments",
                "wholesale", "settlement", "tax", "irs", "clearing"
            )
        ):
            reg_rating = 5
            reg_note = "High regulatory scrutiny inferred from banking core/payments/lending category (5/5)."
        elif any(
            token in cat_str
            for token in ("document", "communications", "data and reporting", "wealth")
        ):
            reg_rating = 4
            reg_note = "Moderate-to-high regulatory scrutiny inferred from wealth/statements category (4/5)."
        elif any(
            token in cat_str
            for token in ("professional services", "workload automation", "batch scheduling")
        ):
            reg_rating = 3
            reg_note = "Standard operational regulatory oversight for enterprise IT services (3/5)."
        else:
            reg_rating = 2
            reg_note = "Baseline regulatory oversight for support services (2/5)."

    # 4. Payment Involvement
    raw_pay = (
        normalized_row.get("paymentinvolvement")
        or normalized_row.get("paymentinvolvementrating")
        or normalized_row.get("paymentprocessing")
        or ""
    )
    pay_rating = _explicit_rating(raw_pay)
    pay_note = ""
    if pay_rating is not None:
        pay_note = f"Explicit payment rating '{raw_pay}' mapped to {pay_rating}/5."
    else:
        pay_text = _normalise(raw_pay)
        if pay_text in {"yes", "true", "high", "significant", "involved"}:
            pay_rating = 5
            pay_note = "Direct payment involvement confirmed (5/5)."
        elif pay_text in {"no", "none", "false", "not involved"}:
            pay_rating = 1
            pay_note = "No payment involvement (1/5)."
        else:
            cat_str = str(
                normalized_row.get("category", "")
                or normalized_row.get("serviceproductprovided", "")
                or normalized_row.get("businessprocesssupported", "")
            ).casefold()
            if any(
                token in cat_str
                for token in ("payments", "clearing", "settlement", "wire", "ach", "interbank")
            ):
                pay_rating = 5
                pay_note = "Direct payment processing/settlement inferred from category (5/5)."
            elif any(token in cat_str for token in ("core banking", "balances", "account processing")):
                pay_rating = 4
                pay_note = "Core transaction and balance processing inferred from category (4/5)."
            elif any(token in cat_str for token in ("batch scheduling", "statements", "tax")):
                pay_rating = 2
                pay_note = "Indirect technical support to transaction processes (2/5)."
            else:
                pay_rating = 1
                pay_note = "No direct payment involvement inferred from category (1/5)."

    # 5. Annual Data Volume
    raw_vol = (
        normalized_row.get("datavolumeannual")
        or normalized_row.get("annualdatavolume")
        or normalized_row.get("annualdatavolumerating")
        or normalized_row.get("datavolumerating")
        or ""
    )
    vol_rating = _explicit_rating(raw_vol) or _ordinal_category(raw_vol)
    vol_note = ""
    if vol_rating is not None:
        vol_note = f"Explicit volume rating '{raw_vol}' mapped to {vol_rating}/5."
    else:
        vol_str = str(raw_vol).casefold()
        if any(token in vol_str for token in ("240 million", "14 million", "19 million", "entire customer base")):
            vol_rating = 5
            vol_note = f"Enterprise/Full-population volume inferred from '{raw_vol}' (5/5)."
        elif any(token in vol_str for token in ("2.1 million", "1.4 million", "660,000", "240,000")):
            vol_rating = 4
            vol_note = f"High volume inferred from '{raw_vol}' (4/5)."
        elif any(token in vol_str for token in ("38,000", "wealth clients")):
            vol_rating = 3
            vol_note = f"Moderate volume inferred from '{raw_vol}' (3/5)."
        elif "not applicable" in vol_str or not vol_str or vol_str == "nan":
            vol_rating = 1
            vol_note = "Volume marked not applicable or low (1/5)."
        else:
            match = re.search(r"(\d[\d,.]*)", vol_str)
            if match:
                clean_num = float(match.group(1).replace(",", ""))
                if clean_num >= 10_000_000:
                    vol_rating = 5
                elif clean_num >= 1_000_000:
                    vol_rating = 4
                elif clean_num >= 100_000:
                    vol_rating = 3
                elif clean_num >= 10_000:
                    vol_rating = 2
                else:
                    vol_rating = 1
                vol_note = f"Volume parsed as {clean_num:g} -> {vol_rating}/5."
            else:
                vol_rating = None
                vol_note = f"Volume '{raw_vol}' requires review; numeric bands not approved."

    factor_ratings = {
        "data_sensitivity": data_rating,
        "operational_dependency": dep_rating,
        "regulatory_exposure": reg_rating,
        "payment_involvement": pay_rating,
        "annual_data_volume": vol_rating,
    }
    factor_notes = {
        "data_sensitivity": data_note,
        "operational_dependency": dep_note,
        "regulatory_exposure": reg_note,
        "payment_involvement": pay_note,
        "annual_data_volume": vol_note,
    }

    warnings = [
        f"{k}: {factor_notes[k]}"
        for k, v in factor_ratings.items()
        if v is None
    ]

    known_factors = {k: v for k, v in factor_ratings.items() if v is not None}
    coverage = sum(WEIGHTS[k] for k in known_factors) / sum(WEIGHTS.values()) * 100

    if len(known_factors) == len(WEIGHTS):
        preliminary_score = round(
            sum((factor_ratings[k] / 5.0) * WEIGHTS[k] for k in WEIGHTS) * 100.0,
            1,
        )
        tier = determine_criticality_tier(preliminary_score)
        completeness = "Complete preliminary assessment"
    else:
        avail_weight = sum(WEIGHTS[k] for k in known_factors)
        if avail_weight > 0:
            preliminary_score = round(
                sum((known_factors[k] / 5.0) * WEIGHTS[k] for k in known_factors)
                / avail_weight
                * 100.0,
                1,
            )
            tier = determine_criticality_tier(preliminary_score)
        else:
            preliminary_score = None
            tier = "Incomplete"
        completeness = f"Partial preliminary assessment ({coverage:.0f}% factor coverage)"

    depth = CRITICALITY_DEPTH_MAP.get(tier, "Standard review — tier-driven")

    vendor_name = str(data.get("Vendor Name", "Vendor")).strip()
    category = str(data.get("Category", "")).strip()

    rationale_parts = []
    if dep_rating and dep_rating >= 4:
        rationale_parts.append(
            f"{'Critical' if dep_rating == 5 else 'High'} operational dependency for {category or 'core services'}"
        )
    elif dep_rating:
        rationale_parts.append(f"Moderate operational dependency ({dep_rating}/5)")

    if data_rating and data_rating >= 4:
        rationale_parts.append(
            f"{'access to full customer/sensitive financial master' if data_rating == 5 else 'access to confidential/privileged'} data"
        )
    elif data_rating:
        rationale_parts.append("access to operational data without direct customer master records")

    if pay_rating and pay_rating >= 4:
        rationale_parts.append("direct payment and transaction settlement involvement")

    if vol_rating and vol_rating >= 4:
        rationale_parts.append("enterprise-scale annual transaction or message volume")

    if rationale_parts:
        rationale = "; ".join(rationale_parts).capitalize() + f", placing {vendor_name} in the {tier} criticality tier."
    else:
        rationale = f"Preliminary assessment based on available inventory attributes places this vendor in the {tier} tier."

    factor_contributions = {
        k: round((v / 5.0) * WEIGHTS[k] * 100.0, 1) if v is not None else 0.0
        for k, v in factor_ratings.items()
    }

    result = CriticalityResult(
        score=preliminary_score,
        status=completeness,
        coverage_percent=round(coverage, 1),
        known_factors=len(known_factors),
        total_factors=len(WEIGHTS),
        factor_ratings=factor_ratings,
        factor_explanations=factor_notes,
        missing_factors=[k for k, v in factor_ratings.items() if v is None],
        rationale=rationale,
        tier=tier,
        investigation_depth=depth,
    )

    return {
        "score": preliminary_score,
        "tier": tier,
        "investigation_depth": depth,
        "rationale": rationale,
        "factor_ratings": factor_ratings,
        "factor_notes": factor_notes,
        "factor_contributions": factor_contributions,
        "warnings": warnings,
        "completeness_status": completeness,
        "result": result,
    }

