"""Human-review-aware AI-use classification for Project BlindSpot."""

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Iterable


CONFIRMED = "Confirmed"
SUSPECTED = "Suspected"
NOT_DETECTED = "Not Detected"
INCONCLUSIVE = "Inconclusive/Needs Review"


@dataclass
class AIUseAssessment:
    """A traceable summary of the current AI-use assessment."""

    status: str
    confidence: str
    summary: str
    evidence_ids: list[str]
    rationale: list[str]
    follow_up: list[str]
    review_required: bool


def _value(item: Any, key: str, default=None):
    """Read a field from a dictionary or object."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _mapping(value: Any) -> dict:
    """Convert a nested grade object to a dictionary."""
    if isinstance(value, dict):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return vars(value).copy()
    return {}


def _normalise_status(value: Any) -> str:
    return str(value or "Needs review").strip().casefold()


def _normalise_directness(value: Any) -> str:
    return str(value or "unclear").strip().casefold()


def _normalise_relevance(value: Any) -> str:
    return str(value or "unclear").strip().casefold()


def _score(grade: dict) -> float:
    try:
        return float(grade.get("score", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _evidence_id(record: Any, index: int) -> str:
    value = _value(record, "evidence_id", None)
    return str(value).strip() if value not in (None, "") else f"Evidence-{index + 1}"


def classify_ai_usage(
    evidence_records: Iterable[Any],
    collection_complete: bool = False,
) -> AIUseAssessment:
    """
    Classify AI-use signals conservatively.

    Only evidence explicitly accepted by a human reviewer can support a
    positive classification. Keyword matches and unreviewed records are not
    treated as proof. `collection_complete` means the reviewer considers the
    defined public-source scope sufficiently searched; it does not prove that
    a vendor does not use AI.
    """
    records = list(evidence_records or [])

    accepted = []
    pending = []
    rejected_count = 0

    for index, record in enumerate(records):
        review_status = _normalise_status(
            _value(record, "review_status", "Needs review")
        )

        if review_status == "rejected":
            rejected_count += 1
            continue

        if review_status != "accepted":
            pending.append(record)
            continue

        grade = _mapping(_value(record, "grade", {}))
        score = _score(grade)
        directness = _normalise_directness(grade.get("directness"))
        relevance = _normalise_relevance(
            grade.get("service_relevance", grade.get("relevance"))
        )

        accepted.append({
            "record": record,
            "id": _evidence_id(record, index),
            "score": score,
            "directness": directness,
            "relevance": relevance,
        })

    if pending:
        pending_ids = [
            _evidence_id(record, index)
            for index, record in enumerate(records)
            if _normalise_status(
                _value(record, "review_status", "Needs review")
            ) not in {"rejected", "accepted"}
        ]
        return AIUseAssessment(
            status=INCONCLUSIVE,
            confidence="Low",
            summary=(
                "One or more evidence records remain unresolved. Review "
                "them before relying on a positive or negative conclusion."
            ),
            evidence_ids=pending_ids,
            rationale=[
                f"{len(pending)} evidence record(s) remain unreviewed or require review.",
                "Unreviewed keyword matches are not treated as proof of AI usage.",
            ],
            follow_up=[
                "Review the pending evidence and record an explicit decision.",
                "Resolve any conflicts with the accepted evidence before classification.",
            ],
            review_required=True,
        )

    confirmed = [
        item for item in accepted
        if item["score"] >= 4
        and item["directness"] == "direct"
        and item["relevance"] == "relevant"
        and _normalise_status(
            _mapping(_value(item["record"], "grade", {})).get("recency")
        ) == "current"
    ]

    suspected = [
        item for item in accepted
        if item["score"] >= 2
        and item["relevance"] == "relevant"
    ]

    # Strong direct evidence takes precedence over weaker signals.
    if confirmed:
        ids = [item["id"] for item in confirmed]
        independent_sources = {
            str(_value(item["record"], "source_url", "")).strip()
            for item in confirmed
            if _normalise_status(
                _mapping(_value(item["record"], "grade", {})).get(
                    "corroboration"
                )
            ) == "independent"
            and str(_value(item["record"], "source_url", "")).strip()
        }
        rationale = [
            "At least one evidence record was accepted by a human reviewer.",
            "The accepted evidence has a source score of at least 4, is marked "
            "direct and current, and is relevant to the vendor's service.",
            "This classification reflects the reviewed public evidence, not "
            "a complete technical audit of the vendor.",
        ]
        follow_up = [
            "Validate the vendor's AI-related data flows and subprocessors.",
            "Review retention, model-training, hosting, and human-oversight terms.",
        ]
        return AIUseAssessment(
            status=CONFIRMED,
            confidence=(
                "High" if len(independent_sources) >= 2 else "Moderate"
            ),
            summary=(
                "Reviewed evidence supports AI use relevant to the vendor's "
                "service. Confirm the scope and security implications with "
                "additional due diligence."
            ),
            evidence_ids=ids,
            rationale=rationale,
            follow_up=follow_up,
            review_required=False,
        )

    if suspected:
        ids = [item["id"] for item in suspected]
        independent_sources = {
            str(_value(item["record"], "source_url", "")).strip()
            for item in suspected
            if _normalise_status(
                _mapping(_value(item["record"], "grade", {})).get(
                    "corroboration"
                )
            ) == "independent"
            and str(_value(item["record"], "source_url", "")).strip()
        }
        rationale = [
            "At least one evidence record was accepted by a human reviewer.",
            "The evidence is relevant to the vendor's service and has a source "
            "score of at least 2, but it does not meet the stricter criteria "
            "for Confirmed.",
        ]
        follow_up = [
            "Seek direct vendor documentation or a technical announcement.",
            "Confirm whether AI is used in the specific service under review.",
            "Review data handling, subprocessors, retention, and oversight.",
        ]
        return AIUseAssessment(
            status=SUSPECTED,
            confidence=(
                "Moderate" if len(independent_sources) >= 2 else "Low"
            ),
            summary=(
                "Reviewed evidence suggests possible AI use relevant to the "
                "vendor's service, but stronger direct evidence is needed."
            ),
            evidence_ids=ids,
            rationale=rationale,
            follow_up=follow_up,
            review_required=True,
        )

    if not collection_complete:
        return AIUseAssessment(
            status=INCONCLUSIVE,
            confidence="Low",
            summary=(
                "No qualifying accepted evidence was identified, but the "
                "defined public-source collection scope has not been marked "
                "complete. This is not evidence that the vendor does not use AI."
            ),
            evidence_ids=[],
            rationale=[
                "No accepted evidence met the positive classification criteria.",
                "The reviewer has not marked the collection scope complete.",
            ],
            follow_up=[
                "Investigate relevant official product, technical, and developer sources.",
                "Mark the collection scope complete only after the agreed searches "
                "have been performed and collection limitations are recorded.",
            ],
            review_required=True,
        )

    return AIUseAssessment(
        status=NOT_DETECTED,
        confidence="Low",
        summary=(
            "No qualifying AI-use evidence was detected within the reviewed "
            "public-source scope. This does not prove that the vendor does not use AI."
        ),
        evidence_ids=[],
        rationale=[
            "No accepted evidence met the criteria for Confirmed or Suspected.",
            "The reviewer marked the defined public-source collection scope complete.",
            f"{rejected_count} rejected record(s) were excluded from classification.",
        ],
        follow_up=[
            "Record source coverage and access limitations in the assessment.",
            "Revisit the conclusion if new evidence becomes available or the vendor's "
            "services change.",
        ],
        review_required=False,
    )
