
"""Explainable security risk assessment for Project BlindSpot.

Security risk findings are based on reviewed evidence and recorded
assessment inputs. They are not proof of a security incident.
"""

from dataclasses import dataclass, field
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable


RISK_THEMES = {
    "sensitive_data_exposure": {
        "label": "Sensitive Data Exposure",
        "description": (
            "Potential exposure of confidential, personal, or sensitive "
            "information through AI systems or related services."
        ),
        "follow_up": (
            "Review data categories, minimisation, access controls, "
            "and approved-use restrictions."
        ),
    },
    "provider_transparency": {
        "label": "AI Provider Transparency",
        "description": (
            "Insufficient clarity about AI providers, models, or "
            "subprocessors involved in the service."
        ),
        "follow_up": (
            "Identify relevant providers and subprocessors and review "
            "their responsibilities."
        ),
    },
    "retention_and_training": {
        "label": "Retention and Model Training",
        "description": (
            "Unclear data-retention, model-training, or data-use terms."
        ),
        "follow_up": (
            "Review contractual terms for retention, training use, deletion, "
            "and permitted processing."
        ),
    },
    "hosting_and_data_location": {
        "label": "Hosting and Data Location",
        "description": (
            "Insufficient clarity about processing locations, hosting, "
            "or cross-border data handling."
        ),
        "follow_up": (
            "Review hosting arrangements, processing locations, and "
            "applicable data-residency requirements."
        ),
    },
    "transparency_and_oversight": {
        "label": "Transparency and Oversight",
        "description": (
            "Limited visibility into AI functionality, governance, "
            "human oversight, or control mechanisms."
        ),
        "follow_up": (
            "Request or review relevant governance, oversight, and "
            "technical-control documentation."
        ),
    },
    "operational_dependency": {
        "label": "Operational Dependency",
        "description": (
            "Potential business disruption if an AI-enabled service "
            "becomes unavailable or changes materially."
        ),
        "follow_up": (
            "Review service criticality, contingency arrangements, "
            "recovery objectives, and alternative processes."
        ),
    },
    "evidence_gaps": {
        "label": "Evidence and Assurance Gaps",
        "description": (
            "Insufficient public evidence to establish relevant security "
            "or governance controls."
        ),
        "follow_up": (
            "Record the evidence gap and determine whether authorised "
            "internal documentation or formal review is needed."
        ),
    },
    "other": {
        "label": "Other",
        "description": "A reviewer-documented vendor security concern.",
        "follow_up": (
            "Define and document a proportionate verification or mitigation "
            "action for this concern."
        ),
    },
}


VALID_SEVERITIES = {"Unassessed", "Low", "Moderate", "High", "Critical"}
VALID_LIKELIHOODS = {"Unassessed", "Unlikely", "Possible", "Likely"}
VALID_FINDING_STATUSES = {
    "Needs review",
    "Under review",
    "Reviewed",
    "Resolved",
    "Accepted risk",
}

SEVERITY_SCORE = {
    "Low": 1,
    "Moderate": 2,
    "High": 3,
    "Critical": 4,
}
LIKELIHOOD_SCORE = {
    "Unlikely": 1,
    "Possible": 2,
    "Likely": 3,
}


@dataclass
class RiskFinding:
    """One explainable security risk finding."""

    finding_id: str
    vendor_id: str
    vendor_name: str
    theme: str
    title: str
    description: str
    severity: str
    likelihood: str
    rationale: str
    evidence_ids: list[str] = field(default_factory=list)
    recommended_action: str = ""
    status: str = "Needs review"
    reviewer: str = ""
    reviewed_at: str = ""


def _text(value: Any) -> str:
    """Return a trimmed string."""
    if value is None:
        return ""

    return str(value).strip()


def create_risk_finding(
    *,
    vendor_id: str,
    vendor_name: str,
    theme: str,
    rationale: str,
    severity: str = "Moderate",
    likelihood: str = "Unassessed",
    evidence_ids: list[str] | None = None,
    finding_id: str | None = None,
    description: str | None = None,
    recommended_action: str | None = None,
    status: str = "Needs review",
    reviewer: str = "",
    reviewed_at: str | None = None,
) -> RiskFinding:
    """Create a validated, traceable security risk finding.

    A finding must identify a known risk theme and explain its rationale.
    Severity and likelihood are assessment inputs, not automatically
    inferred from AI-use classification.
    """
    if theme not in RISK_THEMES:
        raise ValueError(
            f"Unknown risk theme: {theme}. "
            f"Choose from: {', '.join(RISK_THEMES)}"
        )

    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity: {severity}. "
            f"Choose from: {', '.join(sorted(VALID_SEVERITIES))}"
        )

    if likelihood not in VALID_LIKELIHOODS:
        raise ValueError(
            f"Invalid likelihood: {likelihood}. "
            f"Choose from: {', '.join(sorted(VALID_LIKELIHOODS))}"
        )

    if status not in VALID_FINDING_STATUSES:
        raise ValueError(
            f"Invalid finding status: {status}. "
            f"Choose from: {', '.join(sorted(VALID_FINDING_STATUSES))}"
        )

    if not _text(vendor_id) or not _text(vendor_name):
        raise ValueError("Vendor ID and vendor name are required.")

    if not _text(rationale):
        raise ValueError(
            "A rationale is required so the finding can be reviewed."
        )

    theme_details = RISK_THEMES[theme]

    return RiskFinding(
        finding_id=finding_id or f"RISK-{_text(vendor_id)}-{theme.upper()}",
        vendor_id=_text(vendor_id),
        vendor_name=_text(vendor_name),
        theme=theme,
        title=theme_details["label"],
        description=_text(description) or theme_details["description"],
        severity=severity,
        likelihood=likelihood,
        rationale=_text(rationale),
        evidence_ids=list(evidence_ids or []),
        recommended_action=(
            _text(recommended_action) or theme_details["follow_up"]
        ),
        status=_text(status) or "Needs review",
        reviewer=_text(reviewer),
        reviewed_at=_text(reviewed_at) or "",
    )


def findings_as_records(
    findings: Iterable[RiskFinding],
) -> list[dict[str, Any]]:
    """Convert findings into records suitable for a table or CSV export."""
    records = []

    for finding in findings:
        records.append({
            "Finding ID": finding.finding_id,
            "Vendor ID": finding.vendor_id,
            "Vendor Name": finding.vendor_name,
            "Risk Theme": finding.title,
            "Theme Key": finding.theme,
            "Description": finding.description,
            "Severity": finding.severity,
            "Likelihood": finding.likelihood,
            "Rationale": finding.rationale,
            "Evidence IDs": "; ".join(finding.evidence_ids),
            "Recommended Action": finding.recommended_action,
            "Status": finding.status,
            "Reviewer": finding.reviewer,
            "Reviewed At (UTC)": finding.reviewed_at,
        })

    return records


def evidence_gap_finding(
    *,
    vendor_id: str,
    vendor_name: str,
    rationale: str,
    evidence_ids: list[str] | None = None,
) -> RiskFinding:
    """Record an evidence gap without claiming a control has failed."""
    return create_risk_finding(
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        theme="evidence_gaps",
        rationale=rationale,
        severity="Unassessed",
        likelihood="Unassessed",
        evidence_ids=evidence_ids,
    )


def calculate_ai_cyber_risk_score(
    findings: Iterable[Any],
    evidence_records: Iterable[Any] = (),
):
    """Return a prioritization score from reviewer-rated active findings.

    The score is the highest assessed finding normalized across the explicit
    4x3 severity/likelihood matrix, provided it links to accepted evidence for
    the same vendor. It is an index, not a probability, and AI-use
    classification alone never creates a risk rating.
    """
    evidence_by_vendor_and_id = {
        (
            _text(_get_evidence(record, "vendor_id")).casefold(),
            _text(_get_evidence(record, "evidence_id")),
        ): _text(_get_evidence(record, "review_status")).casefold()
        for record in evidence_records or []
    }
    records = []
    unassessed = 0
    unsupported = 0
    for finding in findings or []:
        if isinstance(finding, dict):
            record = dict(finding)
        elif is_dataclass(finding) and not isinstance(finding, type):
            record = asdict(finding)
        else:
            record = vars(finding).copy()

        status = _text(
            record.get("finding_status", record.get("status", "Needs review"))
        ).casefold()
        if status == "resolved":
            continue
        vendor_id = _text(record.get("vendor_id", record.get("Vendor ID")))
        evidence_ids = record.get("evidence_ids", record.get("Evidence IDs", []))
        if isinstance(evidence_ids, str):
            evidence_ids = [
                item.strip()
                for item in evidence_ids.replace(",", ";").split(";")
                if item.strip()
            ]
        supported = any(
            evidence_by_vendor_and_id.get(
                (vendor_id.casefold(), _text(evidence_id))
            ) == "accepted"
            for evidence_id in evidence_ids or []
        )
        if not supported:
            unsupported += 1
            continue
        severity = _text(record.get("severity")).casefold()
        likelihood = _text(record.get("likelihood")).casefold()
        severity_value = next(
            (
                score for label, score in SEVERITY_SCORE.items()
                if label.casefold() == severity
            ),
            None,
        )
        likelihood_value = next(
            (
                score for label, score in LIKELIHOOD_SCORE.items()
                if label.casefold() == likelihood
            ),
            None,
        )
        if severity_value is None or likelihood_value is None:
            unassessed += 1
            continue
        record["_risk_index"] = round(
            severity_value * likelihood_value / 12 * 100,
            1,
        )
        records.append(record)

    if records:
        highest = max(records, key=lambda record: record["_risk_index"])
        return {
            "score": highest["_risk_index"],
            "status": "Assessed — reviewer-rated prioritization index",
            "scored_findings": len(records),
            "unassessed_findings": unassessed,
            "unsupported_findings": unsupported,
            "driving_finding_id": highest.get(
                "finding_id",
                highest.get("Finding ID", ""),
            ),
            "rationale": (
                "Score is the highest active finding's severity rating "
                "(Low=1, Moderate=2, High=3, Critical=4) multiplied by "
                "likelihood (Unlikely=1, Possible=2, Likely=3), divided "
                "by 12 and expressed on a 0–100 index. Only findings "
                "linked to accepted evidence for that vendor are scored. "
                "It is not a probability or an automated finding."
            ),
        }

    if unassessed or unsupported:
        return {
            "score": None,
            "status": "Unassessed — reviewer ratings required",
            "scored_findings": 0,
            "unassessed_findings": unassessed,
            "unsupported_findings": unsupported,
            "driving_finding_id": "",
            "rationale": (
                "No active finding has both a rated severity and likelihood "
                "and accepted evidence linked to the same vendor. A missing "
                "score does not indicate low risk."
            ),
        }

    return {
        "score": None,
        "status": "No active risk findings",
        "scored_findings": 0,
        "unassessed_findings": 0,
        "unsupported_findings": 0,
        "driving_finding_id": "",
        "rationale": (
            "No active risk finding is available to score. This is not a "
            "finding of no cybersecurity risk."
        ),
    }


def _get_evidence(item, key):
    if isinstance(item, dict):
        return item.get(key, "")
    return getattr(item, key, "")
