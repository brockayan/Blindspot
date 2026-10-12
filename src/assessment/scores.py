"""Separate aggregate evidence quality and cybersecurity risk scores."""

from dataclasses import asdict, is_dataclass


def _get(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _mapping(value):
    if isinstance(value, dict):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return vars(value).copy()
    return {}


def calculate_evidence_score(evidence_records):
    """Average source-grade points for accepted, relevant evidence only.

    The 0–100 result is normalized source-quality points, not probability or
    confidence. Pending, rejected, irrelevant, or ungraded items are excluded.
    """
    eligible_scores = []
    excluded_count = 0
    for record in evidence_records or []:
        if str(_get(record, "review_status", "Needs review")).strip().casefold() != "accepted":
            excluded_count += 1
            continue
        grade = _mapping(_get(record, "grade"))
        if str(
            grade.get("service_relevance", grade.get("relevance", ""))
        ).strip().casefold() == "not_relevant":
            excluded_count += 1
            continue
        try:
            points = float(grade.get("score"))
        except (TypeError, ValueError):
            excluded_count += 1
            continue
        if 1 <= points <= 5:
            eligible_scores.append(points)
        else:
            excluded_count += 1

    if not eligible_scores:
        return {
            "score": None,
            "status": "Unassessed — accepted graded evidence required",
            "evidence_count": 0,
            "excluded_count": excluded_count,
            "rationale": (
                "No accepted, relevant, graded evidence is available. "
                "The score is source-quality points normalized to 0–100; "
                "it is not probability or AI-use confidence."
            ),
        }

    average_points = sum(eligible_scores) / len(eligible_scores)
    return {
        "score": round(average_points / 5 * 100, 1),
        "status": "Assessed — source-quality index",
        "evidence_count": len(eligible_scores),
        "excluded_count": excluded_count,
        "average_points_out_of_5": round(average_points, 2),
        "rationale": (
            "Arithmetic mean of source-type points (1–5) for accepted, "
            "relevant evidence, normalized to 0–100. The score is not "
            "probability, confidence, or cybersecurity risk."
        ),
    }
