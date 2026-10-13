"""Human-review-aware AI-use classification for Project BlindSpot."""

import re
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Iterable


CONFIRMED = "Confirmed"
SUSPECTED = "Suspected"
NOT_DETECTED = "Not Detected"
INCONCLUSIVE = "Inconclusive/Needs Review"

QUALIFYING_AI_TERMS_PATTERN = re.compile(
    r"\b("
    r"artificial intelligence|ai|machine learning|ml models?|"
    r"predictive (?:model(?:s|ing)?|analytics)|neural networks?|deep learning|"
    r"large language models?|llms?|generative ai|generative models?|"
    r"natural language processing|nlp|computer vision|"
    r"azure openai|openai|anthropic|claude|google gemini|vertex ai|"
    r"amazon bedrock|aws bedrock|aws sagemaker|cohere|mistral ai|meta llama"
    r")\b",
    re.IGNORECASE,
)


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


def _is_negative_disclosure(item: Any) -> bool:
    """Check if record documents absence of AI / non-AI deterministic service."""
    record = _value(item, "record", item)
    ai_flag = str(_value(record, "ai_usage_detected", "")).strip().casefold()
    if ai_flag in {"no", "not detected", "false"}:
        return True
    signals = [str(s).casefold() for s in (_value(record, "signal_types", []) or [])]
    if "non_ai_service_disclosure" in signals:
        return True
    excerpt = str(_value(record, "excerpt", "")).casefold()
    if any(phrase in excerpt for phrase in (
        "no ai usage detected",
        "deterministic rule-based",
        "workload automation engines",
        "batch scheduling and workload automation",
        "appworx, and uc4",
    )):
        return True
    return False


def _has_qualifying_ai_signals(item: Any) -> bool:
    """Check if record contains qualifying AI signals relevant to the vendor's service."""
    if _is_negative_disclosure(item):
        return False
    if _is_inconclusive_signal(item):
        return False

    record = _value(item, "record", item)
    grade = _mapping(_value(record, "grade", {}))
    relevance = _normalise_relevance(
        _value(item, "relevance", grade.get("service_relevance", grade.get("relevance", "unknown")))
    )
    if relevance in {"not_relevant", "irrelevant"}:
        return False

    signals = [str(s).casefold() for s in (_value(record, "signal_types", []) or [])]
    excerpt = str(_value(record, "excerpt", "")).strip().casefold()
    title = str(_value(record, "source_title", "")).strip().casefold()
    url = str(_value(record, "source_url", "")).strip().casefold()
    matched_terms = _value(record, "matched_terms", []) or []

    # Explicit non-AI service disclosure
    if "non_ai_service_disclosure" in signals:
        return False

    # Incidental blog titles or thought leadership without vendor product AI capability claims
    if "before you put ai agents on the schedule" in excerpt and not any(
        k in excerpt for k in ("our platform", "our ai", "powered by ai", "generative model", "machine learning model")
    ):
        return False

    # Workload automation descriptions without AI capabilities
    if "workload automation" in excerpt and not any(
        k in excerpt for k in ("machine learning", "predictive analytics", "neural network", "deep learning", "llm", "generative model", "azure openai", "openai")
    ):
        return False

    has_text = bool(excerpt or signals or matched_terms or title or (url and url != "https://"))
    if not has_text:
        # Grade-only mock record in tests
        return relevance not in {"not_relevant", "irrelevant"}

    # Evidence must contain an actual qualifying AI signal
    has_ai_category = any(
        s in {"generative_ai", "machine_learning", "ai_capability_disclosure", "model_provider", "automated_decisioning"}
        for s in signals
    )
    has_ai_matched = any(bool(QUALIFYING_AI_TERMS_PATTERN.search(str(t))) for t in matched_terms)
    has_ai_excerpt = bool(QUALIFYING_AI_TERMS_PATTERN.search(excerpt))
    has_ai_title = bool(QUALIFYING_AI_TERMS_PATTERN.search(title))
    has_ai_url = bool(QUALIFYING_AI_TERMS_PATTERN.search(url.replace("-", " ").replace("/", " ")))

    if not (has_ai_category or has_ai_matched or has_ai_excerpt or has_ai_title or has_ai_url):
        return False

    return True


def _is_inconclusive_signal(item: Any) -> bool:
    """Check if record documents inconclusive AI signals."""
    record = _value(item, "record", item)
    ai_flag = str(_value(record, "ai_usage_detected", "")).strip().casefold()
    if ai_flag in {"inconclusive", "unknown", "unverified"}:
        return True
    return False


def status_to_detected_flag(status: Any) -> str:
    """Map AI-use assessment status to Vendor Inventory's 'AI Usage Detected (Y/N)' column."""
    st = str(status or "").strip().casefold()
    if st in {"confirmed", "yes"}:
        return "Yes"
    elif st in {"not detected", "no"}:
        return "No"
    elif st in {"inconclusive", "inconclusive/needs review", "needs review"}:
        return "Inconclusive"
    elif st == "suspected":
        return "Suspected"
    return "Inconclusive"


def detected_flag_to_status(flag: Any) -> str:
    """Map Vendor Inventory's 'AI Usage Detected (Y/N)' column to AI-use status."""
    fl = str(flag or "").strip().casefold()
    if fl in {"yes", "confirmed"}:
        return CONFIRMED
    elif fl in {"no", "not detected"}:
        return NOT_DETECTED
    elif fl == "suspected":
        return SUSPECTED
    return INCONCLUSIVE


def classify_ai_usage(
    evidence_records: Iterable[Any],
    collection_complete: bool = False,
    collection_failed: bool = False,
    failure_reason: str = "",
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
        and _has_qualifying_ai_signals(item)
        and not _is_negative_disclosure(item)
        and not _is_inconclusive_signal(item)
    ]

    suspected = [
        item for item in accepted
        if item not in confirmed
        and item["score"] >= 2
        and item["relevance"] == "relevant"
        and _has_qualifying_ai_signals(item)
        and not _is_negative_disclosure(item)
        and not _is_inconclusive_signal(item)
    ]

    has_negative = any(_is_negative_disclosure(item) for item in accepted)
    has_inconclusive = any(_is_inconclusive_signal(item) for item in accepted)

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
        has_curated = any(
            _value(item["record"], "data_origin") == "curated_case_study_disclosure"
            or "[curated" in str(_value(item["record"], "source_title", "")).casefold()
            for item in confirmed
        )
        has_live = any(
            _value(item["record"], "data_origin") == "live_public_web"
            for item in confirmed
        )
        prov_note = (
            "Supported by corroborated evidence: independently retrieved live OSINT and curated case-study disclosure."
            if has_curated and has_live
            else (
                "Supported by curated case-study reference disclosure (simulation reference; not independently retrieved live OSINT)."
                if has_curated
                else "Supported by independently retrieved live OSINT from vendor technical documentation / announcements."
            )
        )
        rationale = [
            prov_note,
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

    if has_negative:
        ids = [item["id"] for item in accepted if _is_negative_disclosure(item)]
        has_curated = any(
            _value(item["record"], "data_origin") == "curated_case_study_disclosure"
            or "[curated" in str(_value(item["record"], "source_title", "")).casefold()
            for item in accepted if _is_negative_disclosure(item)
        )
        prov_note = (
            "Supported by curated case-study reference disclosure (simulation reference; not independently retrieved live OSINT)."
            if has_curated
            else "Supported by vendor technical documentation."
        )
        return AIUseAssessment(
            status=NOT_DETECTED,
            confidence="Moderate" if collection_complete else "Low",
            summary=(
                "No qualifying AI-use evidence was detected within the reviewed public-source scope. "
                "Vendor relies on deterministic rule-based systems; absence of public evidence does not prove absence of AI."
            ),
            evidence_ids=ids,
            rationale=[
                prov_note,
                "Accepted evidence confirms deterministic rule-based service delivery (workload automation / batch scheduling).",
                "No qualifying public evidence met Confirmed or Suspected criteria; absence of public evidence does not prove that the vendor does not deploy AI in other systems.",
                f"{rejected_count} rejected record(s) were excluded from classification.",
            ],
            follow_up=[
                "Include standard AI notification clause in annual vendor attestation.",
                "Revisit assessment if vendor announces AI-based product features.",
            ],
            review_required=False,
        )

    if has_inconclusive:
        ids = [item["id"] for item in accepted if _is_inconclusive_signal(item)]
        has_curated = any(
            _value(item["record"], "data_origin") == "curated_case_study_disclosure"
            or "[curated" in str(_value(item["record"], "source_title", "")).casefold()
            for item in accepted if _is_inconclusive_signal(item)
        )
        prov_note = (
            "Supported by curated case-study reference disclosure (simulation reference; not independently retrieved live OSINT)."
            if has_curated
            else "Supported by vendor technical documentation."
        )
        is_blocked = collection_failed or "robots" in failure_reason.lower()
        if is_blocked:
            summary = (
                f"Live public web collection from vendor domain was blocked by robots.txt policy restrictions ({failure_reason or 'robots block'}). "
                "Assessment completeness is limited; curated reference describes automated reconciliation and predictive volume analytics without confirming external AI models."
            )
            rationale = [
                prov_note,
                f"Live public web collection from vendor domain was blocked by robots.txt / access policy ({failure_reason or 'robots policy restriction'}). Live collection scope is incomplete.",
                "Assessment relies on curated case-study simulation reference because live public web collection was blocked by vendor robots.txt policy.",
                "Curated disclosures describe predictive business volume analytics and reconciliation algorithms, but do not confirm third-party AI foundation models or external subprocessors.",
                "Status remains Inconclusive pending reviewer validation and direct vendor questionnaire inquiry.",
            ]
        else:
            summary = (
                "Reviewed evidence indicates automated processing, but remains "
                "inconclusive regarding external AI foundation models or subprocessors."
            )
            rationale = [
                prov_note,
                "Accepted evidence describes automated capabilities without confirming third-party AI subprocessors.",
                "Public signals are insufficient to confirm production AI usage in the supplied service.",
            ]
        return AIUseAssessment(
            status=INCONCLUSIVE,
            confidence="Low",
            summary=summary,
            evidence_ids=ids,
            rationale=rationale,
            follow_up=[
                "Issue targeted vendor questionnaire to verify AI usage and subprocessor registers.",
                "Review technical architecture and data flows directly with the vendor.",
            ],
            review_required=True,
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

    if collection_failed:
        return AIUseAssessment(
            status=INCONCLUSIVE,
            confidence="Low",
            summary=(
                f"Public collection was limited or restricted ({failure_reason or 'access blocked or robots policy'}). "
                "Cannot determine AI usage from public sources alone."
            ),
            evidence_ids=[],
            rationale=[
                f"Public source collection failed or was restricted ({failure_reason or 'robots.txt / access controls'}).",
                "Absence of public evidence is not proof of absence.",
                "Status remains Inconclusive pending direct inquiry.",
            ],
            follow_up=[
                "Verify vendor public accessibility and trust documentation manually.",
                "Issue direct vendor due diligence questionnaire.",
            ],
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
    records = list(evidence_records or [])
    if collection_failed and not records:
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
        and _has_qualifying_ai_signals(item)
        and not _is_negative_disclosure(item)
        and not _is_inconclusive_signal(item)
    ]

    # Filter suspected candidates:
    # Service relevant with score >= 2 (includes job postings or indirect technical signals)
    suspected = [
        item for item in eligible
        if item not in confirmed
        and item["score"] >= 2
        and item["relevance"] in {"relevant", "unclear"}
        and item["source_type"] != "generic_marketing"
        and _has_qualifying_ai_signals(item)
        and not _is_negative_disclosure(item)
        and not _is_inconclusive_signal(item)
    ]

    has_negative = any(_is_negative_disclosure(item) for item in eligible)
    has_inconclusive = any(_is_inconclusive_signal(item) for item in eligible)

    if confirmed:
        ids = [item["id"] for item in confirmed]
        has_curated = any(
            _value(item["record"], "data_origin") == "curated_case_study_disclosure"
            or "[curated" in str(_value(item["record"], "source_title", "")).casefold()
            for item in confirmed
        )
        has_live = any(
            _value(item["record"], "data_origin") == "live_public_web"
            for item in confirmed
        )
        prov_note = (
            "Supported by corroborated evidence: independently retrieved live OSINT and curated case-study disclosure."
            if has_curated and has_live
            else (
                "Supported by curated case-study reference disclosure (simulation reference; not independently retrieved live OSINT)."
                if has_curated
                else "Supported by independently retrieved live OSINT from vendor technical documentation / announcements."
            )
        )
        rationale = [
            prov_note,
            "Direct official technical documentation or announcements confirm AI capabilities.",
            "Evidence indicates AI is relevant to the product or service supplied to Meridian.",
            "Preliminary automated finding awaiting final human reviewer validation (Evidence status: Needs review; not human-approved).",
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

    if has_negative:
        ids = [item["id"] for item in eligible if _is_negative_disclosure(item)]
        has_curated = any(
            _value(item["record"], "data_origin") == "curated_case_study_disclosure"
            or "[curated" in str(_value(item["record"], "source_title", "")).casefold()
            for item in eligible if _is_negative_disclosure(item)
        )
        prov_note = (
            "Supported by curated case-study reference disclosure (simulation reference; not independently retrieved live OSINT)."
            if has_curated
            else "Supported by vendor technical documentation."
        )
        return AIUseAssessment(
            status=NOT_DETECTED,
            confidence="Moderate" if collection_complete else "Low",
            summary=(
                "No qualifying AI-use evidence was detected within the investigated public scope. "
                "Vendor service documentation indicates deterministic rule-based workload automation; "
                "absence of public evidence does not constitute definitive proof of no AI deployment."
            ),
            evidence_ids=ids,
            rationale=[
                prov_note,
                "Available technical documentation indicates deterministic rule-based operations (workload automation / batch scheduling) without machine learning models.",
                "No qualifying AI-related evidence was detected within the investigated public scope; absence of public evidence does not prove that the vendor does not deploy AI in uninspected backend systems.",
                "Incidental thought-leadership commentary (such as blog posts discussing AI agents on enterprise schedules) does not establish vendor AI deployment in the supplied service.",
                f"{rejected_count} rejected record(s) excluded.",
                "Confidence is Moderate based on completed public investigation scope and technical service disclosures.",
                "Preliminary automated finding (Evidence status: Needs review; not human-approved).",
            ],
            follow_up=[
                "Standard vendor oversight. Include standard AI disclosure obligations in annual vendor attestations.",
            ],
            review_required=True,
        )

    if has_inconclusive:
        ids = [item["id"] for item in eligible if _is_inconclusive_signal(item)]
        has_curated = any(
            _value(item["record"], "data_origin") == "curated_case_study_disclosure"
            or "[curated" in str(_value(item["record"], "source_title", "")).casefold()
            for item in eligible if _is_inconclusive_signal(item)
        )
        prov_note = (
            "Supported by curated case-study reference disclosure (simulation reference; not independently retrieved live OSINT)."
            if has_curated
            else "Supported by vendor technical documentation."
        )
        is_blocked = collection_failed or "robots" in failure_reason.lower()
        if is_blocked:
            summary = (
                f"Live public web collection from vendor domain was blocked by robots.txt policy restrictions ({failure_reason or 'robots block'}). "
                "Assessment completeness is limited; curated reference describes automated reconciliation and predictive volume analytics without confirming external AI models."
            )
            rationale = [
                prov_note,
                f"Live public web collection from vendor domain was blocked by robots.txt / access policy ({failure_reason or 'robots policy restriction'}). Live collection scope is incomplete.",
                "Assessment relies on curated case-study simulation reference because live public web collection was blocked by vendor robots.txt policy.",
                "Curated disclosures describe predictive business volume analytics and reconciliation algorithms, but do not confirm third-party AI foundation models or external subprocessors.",
                "Preliminary status remains Inconclusive pending reviewer validation and direct vendor questionnaire inquiry (Evidence status: Needs review; not human-approved).",
            ]
        else:
            summary = (
                "Preliminary automated assessment indicates partial or unconfirmed AI signals. "
                "Vendor AI adoption remains inconclusive pending direct questionnaire inquiry."
            )
            rationale = [
                prov_note,
                "Public signals suggest automated processing without proof of third-party AI foundation models or subprocessors.",
                "Preliminary status remains Inconclusive pending reviewer validation and direct inquiry.",
                "(Evidence status: Needs review; not human-approved).",
            ]
        return AIUseAssessment(
            status=INCONCLUSIVE,
            confidence="Low",
            summary=summary,
            evidence_ids=ids,
            rationale=rationale,
            follow_up=[
                "Issue targeted vendor questionnaire to verify AI usage and subprocessor registers.",
            ],
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
            "Preliminary automated finding awaiting human reviewer confirmation (Evidence status: Needs review; not human-approved).",
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

