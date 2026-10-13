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


def classify_preliminary_ai_usage(
    evidence_records: Iterable[Any],
    collection_complete: bool = False,
    collection_failed: bool = False,
    failure_reason: str = "",
) -> AIUseAssessment:
    """Automated preliminary AI-use classification before human review.

    Applies documented safeguards:
    - Technical job postings alone do not prove production AI use (capped at Suspected).
    - Generic marketing language does not establish AI use in the supplied service.
    - Direct, relevant, credible documentation/announcements support Confirmed.
    - Not Detected requires completed scope without access failure.
    - Failed collection or incomplete scope yields Inconclusive.
    - Absence of public evidence is not proof of absence.
    """
    if collection_failed:
        return AIUseAssessment(
            status=INCONCLUSIVE,
            confidence="Low",
            summary=(
                f"Automated public collection was limited or restricted "
                f"({failure_reason or 'access blocked or robots policy'}). "
                "Cannot determine AI usage from public sources alone."
            ),
            evidence_ids=[],
            rationale=[
                "Public source collection failed or was restricted by robots.txt / access controls.",
                "Absence of public evidence is not proof of absence.",
                "Preliminary automated status remains Inconclusive pending direct inquiry.",
            ],
            follow_up=[
                "Verify vendor public accessibility and trust documentation manually.",
                "Issue direct vendor due diligence questionnaire.",
            ],
            review_required=True,
        )

    records = list(evidence_records or [])
    eligible = []
    rejected_count = 0

    for index, record in enumerate(records):
        review_status = _normalise_status(
            _value(record, "review_status", "Needs review")
        )
        if review_status == "rejected":
            rejected_count += 1
            continue

        grade = _mapping(_value(record, "grade", {}))
        score = _score(grade)
        source_type = str(grade.get("source_type", "")).strip().casefold()
        directness = _normalise_directness(grade.get("directness"))
        relevance = _normalise_relevance(
            grade.get("service_relevance", grade.get("relevance"))
        )
        recency = _normalise_status(grade.get("recency", "unknown"))

        eligible.append({
            "record": record,
            "id": _evidence_id(record, index),
            "score": score,
            "source_type": source_type,
            "directness": directness,
            "relevance": relevance,
            "recency": recency,
        })

    # Filter confirmed candidates:
    # Direct, relevant, score >= 4, NOT job posting alone, NOT generic marketing, not dated
    confirmed = [
        item for item in eligible
        if item["score"] >= 4
        and item["directness"] == "direct"
        and item["relevance"] == "relevant"
        and item["source_type"] not in {
            "relevant_technical_job_posting",
            "generic_marketing",
        }
        and item["recency"] != "dated"
    ]

    # Filter suspected candidates:
    # Service relevant with score >= 2 (includes job postings or indirect technical signals)
    suspected = [
        item for item in eligible
        if item not in confirmed
        and item["score"] >= 2
        and item["relevance"] in {"relevant", "unclear"}
        and item["source_type"] != "generic_marketing"
    ]

    if confirmed:
        ids = [item["id"] for item in confirmed]
        rationale = [
            "Direct official technical documentation or announcements confirm AI capabilities.",
            "Evidence indicates AI is relevant to the product or service supplied to Meridian.",
            "Preliminary automated finding awaiting final human reviewer validation.",
        ]
        follow_up = [
            "Review named model providers, hosting infrastructure, and subprocessors.",
            "Validate human-in-the-loop oversight and customer data retention terms.",
        ]
        return AIUseAssessment(
            status=CONFIRMED,
            confidence="High" if len(confirmed) >= 2 else "Moderate",
            summary=(
                "Preliminary automated assessment identified direct, authoritative "
                "evidence of AI use relevant to the vendor's service offering."
            ),
            evidence_ids=ids,
            rationale=rationale,
            follow_up=follow_up,
            review_required=True,
        )

    if suspected:
        ids = [item["id"] for item in suspected]
        job_postings_only = all(
            item["source_type"] == "relevant_technical_job_posting"
            for item in suspected
        )
        rationale = [
            "Public signals indicate AI activity (e.g. engineering hiring, indirect integrations).",
            (
                "A relevant job posting alone does not prove production AI deployment in Meridian's service."
                if job_postings_only
                else "Signals require context validation before establishing production AI use."
            ),
            "Preliminary automated finding awaiting human reviewer confirmation.",
        ]
        follow_up = [
            "Seek direct product documentation or technical architectural disclosures.",
            "Verify whether AI capabilities are active in Meridian's specific tenant/instance.",
        ]
        return AIUseAssessment(
            status=SUSPECTED,
            confidence="Moderate" if len(suspected) >= 2 else "Low",
            summary=(
                "Preliminary signals suggest possible AI usage, but direct proof "
                "of production deployment in the specific service is unconfirmed."
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
                "No qualifying AI evidence was detected, but public collection "
                "scope is incomplete or unverified. Absence of evidence is not proof of absence."
            ),
            evidence_ids=[],
            rationale=[
                "No evidence met Confirmed or Suspected thresholds.",
                "Collection scope has not been completed or verified.",
                "Absence of public evidence is not proof of absence.",
            ],
            follow_up=[
                "Complete investigation of vendor product, developer, and trust pages.",
                "Document collection coverage and limitations.",
            ],
            review_required=True,
        )

    return AIUseAssessment(
        status=NOT_DETECTED,
        confidence="Low",
        summary=(
            "No qualifying AI-use evidence was detected across the completed "
            "investigation scope. This does not prove that the vendor does not use AI."
        ),
        evidence_ids=[],
        rationale=[
            "No evidence met Confirmed or Suspected thresholds within the investigated scope.",
            "Investigation scope was executed without fatal collection failures.",
            f"{rejected_count} rejected record(s) excluded.",
            "Absence of public evidence is not proof of absence.",
        ],
        follow_up=[
            "Record collection coverage and access limitations in the assessment report.",
            "Include standard AI disclosure obligations in annual vendor attestations.",
        ],
        review_required=True,
    )

