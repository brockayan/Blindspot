"""Human review workflow for Project BlindSpot evidence."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


VALID_DECISIONS = {
    "Accepted",
    "Rejected",
    "Needs review",
}

VALID_REASONS = {
    "Relevant and credible",
    "Not relevant to the vendor",
    "AI usage not established",
    "Duplicate evidence",
    "Source reliability concern",
    "Insufficient context",
    "Other",
}
REVIEW_REASONS = sorted(VALID_REASONS)


@dataclass
class ReviewDecision:
    """A traceable human decision about an evidence item."""

    evidence_id: str
    decision: str
    reason: str
    reviewer: str
    notes: str
    reviewed_at: str


def _get(item: Any, key: str, default: Any = None) -> Any:
    """Read a field from a dictionary or an object."""
    if isinstance(item, dict):
        return item.get(key, default)

    return getattr(item, key, default)


def review_evidence(
    evidence: Any,
    decision: str,
    reviewer: str,
    reason: str,
    notes: str = "",
) -> ReviewDecision:
    """Validate and record a review decision.

    This function returns a decision record. It does not modify the
    original evidence object or workbook.
    """
    evidence_id = _get(evidence, "evidence_id")

    if not evidence_id:
        evidence_id = _get(evidence, "id")

    if not evidence_id:
        raise ValueError("The evidence item must have an evidence ID.")

    if decision not in VALID_DECISIONS:
        raise ValueError(
            f"Invalid decision. Choose from: {', '.join(VALID_DECISIONS)}"
        )

    if not reviewer.strip():
        raise ValueError("Enter the reviewer's name or assigned reviewer ID.")

    if reason not in VALID_REASONS:
        raise ValueError(
            f"Invalid reason. Choose from: {', '.join(VALID_REASONS)}"
        )

    if decision == "Rejected" and not notes.strip():
        raise ValueError(
            "Add a note explaining why the evidence was rejected."
        )

    return ReviewDecision(
        evidence_id=str(evidence_id),
        decision=decision,
        reason=reason,
        reviewer=reviewer.strip(),
        notes=notes.strip(),
        reviewed_at=datetime.now(timezone.utc).isoformat(),
    )


def apply_review_status(
    evidence: Any,
    review: ReviewDecision,
) -> dict[str, Any]:
    """Return a copy of an evidence item with its review status updated.

    The source object is left unchanged.
    """
    if isinstance(evidence, dict):
        record = dict(evidence)
    else:
        record = {
            "evidence_id": _get(evidence, "evidence_id", ""),
            "vendor_id": _get(evidence, "vendor_id", ""),
            "vendor_name": _get(evidence, "vendor_name", ""),
            "source_url": _get(evidence, "source_url", ""),
            "excerpt": _get(evidence, "excerpt", ""),
            "grade": _get(evidence, "grade", None),
        }

    record["review_status"] = review.decision
    record["review_reason"] = review.reason
    record["reviewer"] = review.reviewer
    record["review_notes"] = review.notes
    record["reviewed_at"] = review.reviewed_at

    return record


def review_as_record(review: ReviewDecision) -> dict[str, str]:
    """Convert a review decision into a row suitable for a review log."""
    return {
        "Evidence ID": review.evidence_id,
        "Decision": review.decision,
        "Reason": review.reason,
        "Reviewer": review.reviewer,
        "Notes": review.notes,
        "Reviewed At (UTC)": review.reviewed_at,
    }


def review_summary(evidence_records: list[Any]) -> dict[str, int]:
    """Summarise the review queue."""
    summary = {
        "Total": len(evidence_records),
        "Accepted": 0,
        "Rejected": 0,
        "Needs review": 0,
    }

    for evidence in evidence_records:
        status = str(
            _get(evidence, "review_status", "Needs review")
        ).strip().lower()

        if status in {"accepted", "reviewed", "approved"}:
            summary["Accepted"] += 1
        elif status == "rejected":
            summary["Rejected"] += 1
        else:
            summary["Needs review"] += 1

    return summary
