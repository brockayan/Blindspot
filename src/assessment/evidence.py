<<<<<<< HEAD

"""Explainable evidence grading for Project BlindSpot.

Evidence strength is separate from AI-use confidence and security risk.
Grades are proposed defaults and must be validated against the case rubric.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlparse


# Proposed starting points from the project SRS.
SOURCE_TYPE_POINTS = {
    "official_product_documentation": 5,
    "official_technical_announcement": 4,
    "relevant_technical_job_posting": 3,
    "developer_reference": 2,
    "indirect_technical_signal": 2,
    "generic_marketing": 1,
}


@dataclass
class EvidenceGrade:
    score: int | None
    grade: str
    source_type: str
    source_authority: str
    directness: str
    service_relevance: str
    recency: str
    corroboration: str
    rationale: str

    def to_dict(self):
        return asdict(self)


@dataclass
class EvidenceRecord:
    evidence_id: str
    vendor_id: str
    vendor_name: str
    source_url: str
    source_title: str
    source_type: str
    retrieved_at: str
    excerpt: str
    signal_types: list
    matched_terms: list
    grade: EvidenceGrade
    review_status: str = "Needs review"

    def to_dict(self):
        record = asdict(self)
        record["grade"] = self.grade.to_dict()
        return record


def _clean(value):
    if value is None:
        return ""
    return str(value).strip()


def validate_public_url(url):
    """Accept only ordinary HTTP(S) source URLs."""
    try:
        parsed = urlparse(_clean(url))
        return (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def grade_evidence(
    source_type,
    source_url,
    directness,
    service_relevance,
    recency="unknown",
    corroboration="unknown",
):
    """Grade a source using the proposed source-type points.

    Args:
        source_type:
            One of SOURCE_TYPE_POINTS.
        source_url:
            URL supporting the passage.
        directness:
            "direct", "indirect", or "unclear".
        service_relevance:
            "relevant", "unclear", or "not_relevant".
        recency:
            "current", "dated", or "unknown".
        corroboration:
            "independent", "not_corroborated", or "unknown".

    The numeric score represents the proposed source-type grade, not
    the probability that a vendor uses AI. Contextual limitations are
    reflected in the grade label and rationale.
    """

    source_type = _clean(source_type).lower()
    directness = _clean(directness).lower()
    service_relevance = _clean(service_relevance).lower()
    recency = _clean(recency).lower()
    corroboration = _clean(corroboration).lower()

    if not validate_public_url(source_url):
        return EvidenceGrade(
            score=None,
            grade="Unverified source",
            source_type=source_type,
            source_authority="Unverified",
            directness=directness or "unclear",
            service_relevance=service_relevance or "unclear",
            recency=recency or "unknown",
            corroboration=corroboration or "unknown",
            rationale=(
                "A valid public HTTP(S) source URL is required before "
                "the evidence can be graded."
            ),
        )

    if source_type not in SOURCE_TYPE_POINTS:
        return EvidenceGrade(
            score=None,
            grade="Needs review",
            source_type=source_type or "unknown",
            source_authority="Unclassified",
            directness=directness or "unclear",
            service_relevance=service_relevance or "unclear",
            recency=recency or "unknown",
            corroboration=corroboration or "unknown",
            rationale=(
                "Source type is not in the approved grading dictionary. "
                "Classify the source before assigning points."
            ),
        )

    if directness not in {"direct", "indirect", "unclear"}:
        raise ValueError(
            "directness must be direct, indirect, or unclear."
        )

    if service_relevance not in {
        "relevant", "unclear", "not_relevant"
    }:
        raise ValueError(
            "service_relevance must be relevant, unclear, or not_relevant."
        )

    if recency not in {"current", "dated", "unknown"}:
        raise ValueError(
            "recency must be current, dated, or unknown."
        )

    if corroboration not in {
        "independent", "not_corroborated", "unknown"
    }:
        raise ValueError(
            "corroboration must be independent, "
            "not_corroborated, or unknown."
        )

    score = SOURCE_TYPE_POINTS[source_type]

    if score >= 5:
        authority = "Official and directly relevant source type"
    elif score >= 4:
        authority = "Strong official source type"
    elif score == 3:
        authority = "Indirect signal: hiring or development activity"
    elif score == 2:
        authority = "Technical lead requiring context"
    else:
        authority = "Weak, general signal"

    limitations = []

    if directness == "indirect":
        limitations.append(
            "The passage is indirect and does not itself prove deployment."
        )
    elif directness == "unclear":
        limitations.append(
            "Directness has not been verified."
        )

    if service_relevance == "not_relevant":
        limitations.append(
            "The evidence is not relevant to the service being assessed."
        )
    elif service_relevance == "unclear":
        limitations.append(
            "Relevance to Meridian's specific service is unconfirmed."
        )

    if recency == "dated":
        limitations.append(
            "The source may describe an outdated capability."
        )
    elif recency == "unknown":
        limitations.append(
            "The publication or update date is unknown."
        )

    if corroboration == "not_corroborated":
        limitations.append(
            "No independent corroborating source has been identified."
        )
    elif corroboration == "unknown":
        limitations.append(
            "Independent corroboration has not been assessed."
        )

    if service_relevance == "not_relevant":
        grade = "Not relevant to assessed service"
    elif directness == "direct" and service_relevance == "relevant":
        if score >= 4 and recency == "current":
            grade = "Strong"
        else:
            grade = "Moderate — review context"
    elif score <= 2:
        grade = "Weak — lead only"
    else:
        grade = "Moderate — needs verification"

    rationale = (
        f"Source type '{source_type}' receives {score}/5 proposed points. "
        f"Directness: {directness}; service relevance: {service_relevance}. "
    )

    if limitations:
        rationale += "Limitations: " + " ".join(limitations)
    else:
        rationale += (
            "No limitations were selected in the supplied grading fields; "
            "the source excerpt still requires reviewer verification."
        )

    return EvidenceGrade(
        score=score,
        grade=grade,
        source_type=source_type,
        source_authority=authority,
        directness=directness,
        service_relevance=service_relevance,
        recency=recency,
        corroboration=corroboration,
        rationale=rationale,
    )


def create_evidence_record(
    candidate,
    vendor_id,
    vendor_name,
    source_type,
    directness="unclear",
    service_relevance="unclear",
    recency="unknown",
    corroboration="unknown",
):
    """Convert an extracted candidate into a traceable evidence record."""

    if hasattr(candidate, "to_dict"):
        data = candidate.to_dict()
    else:
        data = dict(candidate)

    source_url = data.get("source_url", "")
    excerpt = _clean(data.get("excerpt"))

    if not excerpt:
        raise ValueError(
            "An evidence record must include a supporting excerpt."
        )

    normalized_vendor_id = _clean(vendor_id)
    normalized_vendor_name = _clean(vendor_name)
    if not normalized_vendor_id or not normalized_vendor_name:
        raise ValueError("Vendor ID and vendor name are required.")

    evidence_id = _clean(data.get("evidence_id"))
    if not evidence_id:
        identity = (
            f"{normalized_vendor_id.casefold()}|{source_url}|"
            f"{excerpt.casefold()}"
        )
        evidence_id = "E-" + sha256(identity.encode("utf-8")).hexdigest()[:12].upper()
    else:
        evidence_id = "E-" + sha256(
            f"{normalized_vendor_id.casefold()}|{evidence_id}".encode("utf-8")
        ).hexdigest()[:12].upper()

    grade = grade_evidence(
        source_type=source_type,
        source_url=source_url,
        directness=directness,
        service_relevance=service_relevance,
        recency=recency,
        corroboration=corroboration,
    )

    return EvidenceRecord(
        evidence_id=evidence_id,
        vendor_id=normalized_vendor_id,
        vendor_name=normalized_vendor_name,
        source_url=source_url,
        source_title=_clean(data.get("source_title")),
        source_type=source_type,
        retrieved_at=(
            _clean(data.get("retrieved_at"))
            or datetime.now(timezone.utc).isoformat()
        ),
        excerpt=excerpt,
        signal_types=data.get("signal_types", []),
        matched_terms=data.get("matched_terms", []),
        grade=grade,
    )
=======

"""Explainable evidence grading for Project BlindSpot.

Evidence strength is separate from AI-use confidence and security risk.
Grades are proposed defaults and must be validated against the case rubric.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlparse


# Proposed starting points from the project SRS.
SOURCE_TYPE_POINTS = {
    "official_product_documentation": 5,
    "official_technical_announcement": 4,
    "relevant_technical_job_posting": 3,
    "developer_reference": 2,
    "indirect_technical_signal": 2,
    "generic_marketing": 1,
}


@dataclass
class EvidenceGrade:
    score: int | None
    grade: str
    source_type: str
    source_authority: str
    directness: str
    service_relevance: str
    recency: str
    corroboration: str
    rationale: str

    def to_dict(self):
        return asdict(self)


@dataclass
class EvidenceRecord:
    evidence_id: str
    vendor_id: str
    vendor_name: str
    source_url: str
    source_title: str
    source_type: str
    retrieved_at: str
    excerpt: str
    signal_types: list
    matched_terms: list
    grade: EvidenceGrade
    review_status: str = "Needs review"

    def to_dict(self):
        record = asdict(self)
        record["grade"] = self.grade.to_dict()
        return record


def _clean(value):
    if value is None:
        return ""
    return str(value).strip()


def validate_public_url(url):
    """Accept only ordinary HTTP(S) source URLs."""
    try:
        parsed = urlparse(_clean(url))
        return (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def grade_evidence(
    source_type,
    source_url,
    directness,
    service_relevance,
    recency="unknown",
    corroboration="unknown",
):
    """Grade a source using the proposed source-type points.

    Args:
        source_type:
            One of SOURCE_TYPE_POINTS.
        source_url:
            URL supporting the passage.
        directness:
            "direct", "indirect", or "unclear".
        service_relevance:
            "relevant", "unclear", or "not_relevant".
        recency:
            "current", "dated", or "unknown".
        corroboration:
            "independent", "not_corroborated", or "unknown".

    The numeric score represents the proposed source-type grade, not
    the probability that a vendor uses AI. Contextual limitations are
    reflected in the grade label and rationale.
    """

    source_type = _clean(source_type).lower()
    directness = _clean(directness).lower()
    service_relevance = _clean(service_relevance).lower()
    recency = _clean(recency).lower()
    corroboration = _clean(corroboration).lower()

    if not validate_public_url(source_url):
        return EvidenceGrade(
            score=None,
            grade="Unverified source",
            source_type=source_type,
            source_authority="Unverified",
            directness=directness or "unclear",
            service_relevance=service_relevance or "unclear",
            recency=recency or "unknown",
            corroboration=corroboration or "unknown",
            rationale=(
                "A valid public HTTP(S) source URL is required before "
                "the evidence can be graded."
            ),
        )

    if source_type not in SOURCE_TYPE_POINTS:
        return EvidenceGrade(
            score=None,
            grade="Needs review",
            source_type=source_type or "unknown",
            source_authority="Unclassified",
            directness=directness or "unclear",
            service_relevance=service_relevance or "unclear",
            recency=recency or "unknown",
            corroboration=corroboration or "unknown",
            rationale=(
                "Source type is not in the approved grading dictionary. "
                "Classify the source before assigning points."
            ),
        )

    if directness not in {"direct", "indirect", "unclear"}:
        raise ValueError(
            "directness must be direct, indirect, or unclear."
        )

    if service_relevance not in {
        "relevant", "unclear", "not_relevant"
    }:
        raise ValueError(
            "service_relevance must be relevant, unclear, or not_relevant."
        )

    if recency not in {"current", "dated", "unknown"}:
        raise ValueError(
            "recency must be current, dated, or unknown."
        )

    if corroboration not in {
        "independent", "not_corroborated", "unknown"
    }:
        raise ValueError(
            "corroboration must be independent, "
            "not_corroborated, or unknown."
        )

    score = SOURCE_TYPE_POINTS[source_type]

    if score >= 5:
        authority = "Official and directly relevant source type"
    elif score >= 4:
        authority = "Strong official source type"
    elif score == 3:
        authority = "Indirect signal: hiring or development activity"
    elif score == 2:
        authority = "Technical lead requiring context"
    else:
        authority = "Weak, general signal"

    limitations = []

    if directness == "indirect":
        limitations.append(
            "The passage is indirect and does not itself prove deployment."
        )
    elif directness == "unclear":
        limitations.append(
            "Directness has not been verified."
        )

    if service_relevance == "not_relevant":
        limitations.append(
            "The evidence is not relevant to the service being assessed."
        )
    elif service_relevance == "unclear":
        limitations.append(
            "Relevance to Meridian's specific service is unconfirmed."
        )

    if recency == "dated":
        limitations.append(
            "The source may describe an outdated capability."
        )
    elif recency == "unknown":
        limitations.append(
            "The publication or update date is unknown."
        )

    if corroboration == "not_corroborated":
        limitations.append(
            "No independent corroborating source has been identified."
        )
    elif corroboration == "unknown":
        limitations.append(
            "Independent corroboration has not been assessed."
        )

    if service_relevance == "not_relevant":
        grade = "Not relevant to assessed service"
    elif directness == "direct" and service_relevance == "relevant":
        if score >= 4 and recency == "current":
            grade = "Strong"
        else:
            grade = "Moderate — review context"
    elif score <= 2:
        grade = "Weak — lead only"
    else:
        grade = "Moderate — needs verification"

    rationale = (
        f"Source type '{source_type}' receives {score}/5 proposed points. "
        f"Directness: {directness}; service relevance: {service_relevance}. "
    )

    if limitations:
        rationale += "Limitations: " + " ".join(limitations)
    else:
        rationale += (
            "No limitations were selected in the supplied grading fields; "
            "the source excerpt still requires reviewer verification."
        )

    return EvidenceGrade(
        score=score,
        grade=grade,
        source_type=source_type,
        source_authority=authority,
        directness=directness,
        service_relevance=service_relevance,
        recency=recency,
        corroboration=corroboration,
        rationale=rationale,
    )


def create_evidence_record(
    candidate,
    vendor_id,
    vendor_name,
    source_type,
    directness="unclear",
    service_relevance="unclear",
    recency="unknown",
    corroboration="unknown",
):
    """Convert an extracted candidate into a traceable evidence record."""

    if hasattr(candidate, "to_dict"):
        data = candidate.to_dict()
    else:
        data = dict(candidate)

    source_url = data.get("source_url", "")
    excerpt = _clean(data.get("excerpt"))

    if not excerpt:
        raise ValueError(
            "An evidence record must include a supporting excerpt."
        )

    normalized_vendor_id = _clean(vendor_id)
    normalized_vendor_name = _clean(vendor_name)
    if not normalized_vendor_id or not normalized_vendor_name:
        raise ValueError("Vendor ID and vendor name are required.")

    evidence_id = _clean(data.get("evidence_id"))
    if not evidence_id:
        identity = (
            f"{normalized_vendor_id.casefold()}|{source_url}|"
            f"{excerpt.casefold()}"
        )
        evidence_id = "E-" + sha256(identity.encode("utf-8")).hexdigest()[:12].upper()
    else:
        evidence_id = "E-" + sha256(
            f"{normalized_vendor_id.casefold()}|{evidence_id}".encode("utf-8")
        ).hexdigest()[:12].upper()

    grade = grade_evidence(
        source_type=source_type,
        source_url=source_url,
        directness=directness,
        service_relevance=service_relevance,
        recency=recency,
        corroboration=corroboration,
    )

    return EvidenceRecord(
        evidence_id=evidence_id,
        vendor_id=normalized_vendor_id,
        vendor_name=normalized_vendor_name,
        source_url=source_url,
        source_title=_clean(data.get("source_title")),
        source_type=source_type,
        retrieved_at=(
            _clean(data.get("retrieved_at"))
            or datetime.now(timezone.utc).isoformat()
        ),
        excerpt=excerpt,
        signal_types=data.get("signal_types", []),
        matched_terms=data.get("matched_terms", []),
        grade=grade,
    )
>>>>>>> origin/main
