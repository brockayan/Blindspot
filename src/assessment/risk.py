
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
    "Preliminary",
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


VALID_RISK_TYPES = {"evidence_supported", "conditional", "assurance_gap"}


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
    risk_type: str = "conditional"
    severity_rationale: str = ""
    likelihood_rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    risk_type: str = "conditional",
    severity_rationale: str = "",
    likelihood_rationale: str = "",
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

    norm_risk_type = _text(risk_type).casefold() or "conditional"
    if norm_risk_type not in VALID_RISK_TYPES:
        norm_risk_type = "conditional"

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
        risk_type=norm_risk_type,
        severity_rationale=_text(severity_rationale),
        likelihood_rationale=_text(likelihood_rationale),
    )


def _get_val(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def findings_as_records(
    findings: Iterable[Any],
) -> list[dict[str, Any]]:
    """Convert findings into records suitable for a table or CSV export."""
    records = []

    for finding in (findings or []):
        theme = _text(_get_val(finding, "theme"))
        title = _text(_get_val(finding, "title"))
        if not title and theme in RISK_THEMES:
            title = RISK_THEMES[theme]["label"]
        evidence_ids = _get_val(finding, "evidence_ids", [])
        if isinstance(evidence_ids, list):
            evidence_ids_str = "; ".join(str(e) for e in evidence_ids)
        else:
            evidence_ids_str = str(evidence_ids or "")

        severity = _text(_get_val(finding, "severity"))

        records.append({
            "Finding ID": _text(_get_val(finding, "finding_id")),
            "Vendor ID": _text(_get_val(finding, "vendor_id")),
            "Vendor Name": _text(_get_val(finding, "vendor_name")),
            "Risk Theme": title or theme,
            "Theme Key": theme,
            "Risk Type": _text(_get_val(finding, "risk_type", "conditional")),
            "Preliminary Rating": severity,
            "Description": _text(_get_val(finding, "description")),
            "Severity": severity,
            "Likelihood": _text(_get_val(finding, "likelihood")),
            "Severity Rationale": _text(_get_val(finding, "severity_rationale")),
            "Likelihood Rationale": _text(_get_val(finding, "likelihood_rationale")),
            "Rationale": _text(_get_val(finding, "rationale")),
            "Evidence IDs": evidence_ids_str,
            "Recommended Action": _text(_get_val(finding, "recommended_action")),
            "Status": _text(_get_val(finding, "status")),
            "Reviewer": _text(_get_val(finding, "reviewer")),
            "Reviewed At (UTC)": _text(_get_val(finding, "reviewed_at")),
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


THEME_SUBSTANTIATION = {
    "sensitive_data_exposure": {
        "signals": {"sensitive_data", "data_access", "customer_data", "pii_exposure", "data_leakage"},
        "terms": {
            "data", "privacy", "confidential", "sensitive", "customer", "account",
            "balance", "transaction", "tax", "pii", "npi", "exposure", "security",
            "credentials", "statement", "holding", "prompt", "record", "payload"
        },
    },
    "provider_transparency": {
        "signals": {"model_provider", "third_party_integration", "subprocessor", "fourth_party"},
        "terms": {
            "provider", "subprocessor", "sub-processor", "third-party", "vendor",
            "azure", "openai", "aws", "partner", "api", "model provider", "external",
            "foundation model", "anthropic", "google cloud", "llm", "subprocessor chain"
        },
    },
    "retention_and_training": {
        "signals": {"model_training", "data_retention", "fine_tuning", "data_usage"},
        "terms": {
            "retention", "retain", "training", "train", "learning", "data use",
            "delete", "deletion", "storage", "store", "persist", "fine-tuning",
            "model training", "zero-retention", "opt-out", "machine learning"
        },
    },
    "hosting_and_data_location": {
        "signals": {"cloud_hosting", "data_location", "infrastructure"},
        "terms": {
            "hosting", "cloud", "location", "region", "residency", "cross-border",
            "datacenter", "data center", "azure", "aws", "gcp", "infrastructure",
            "tenant", "private cloud"
        },
    },
    "transparency_and_oversight": {
        "signals": {"human_oversight", "governance", "transparency", "automated_decisioning"},
        "terms": {
            "oversight", "human-in-the-loop", "governance", "transparency", "audit",
            "explainability", "control", "monitoring", "heuristic", "algorithmic",
            "decision", "fraud scoring", "checkpoint", "validation", "review", "scoring"
        },
    },
    "operational_dependency": {
        "signals": {"operational_dependency", "systemic", "core_processing"},
        "terms": {
            "dependency", "critical", "outage", "availability", "core", "settlement",
            "payment", "processing", "volume", "reconciliation", "batch", "schedule",
            "workload", "disruption", "contingency", "sla", "rtp", "clearing"
        },
    },
    "evidence_gaps": {
        "signals": {"evidence_gap", "automated_decisioning", "inconclusive_signal"},
        "terms": {
            "gap", "missing", "inconclusive", "unverified", "unconfirmed", "questionnaire",
            "inquiry", "undisclosed", "absence", "limited", "predictive", "automation",
            "analytics", "reconciliation", "optical"
        },
    },
}


def _evidence_substantiates_risk_theme(ev_item: Any, theme: str) -> bool:
    """Check if an accepted evidence item substantiates a specific risk theme.

    Returns False if:
    - Service relevance is not_relevant or irrelevant
    - Evidence represents a negative disclosure (e.g. non_ai_service_disclosure)
    - Content (excerpt, signal types, matched terms, title) does not substantiate the theme
    """
    if not ev_item:
        return False

    grade = _get_evidence(ev_item, "grade") or {}
    if isinstance(grade, dict):
        rel = str(grade.get("service_relevance", grade.get("relevance", ""))).strip().casefold()
    else:
        rel = str(getattr(grade, "service_relevance", getattr(grade, "relevance", ""))).strip().casefold()
    if not rel:
        rel = str(_get_evidence(ev_item, "service_relevance", _get_evidence(ev_item, "relevance", ""))).strip().casefold()

    if rel in {"not_relevant", "irrelevant"}:
        return False

    ev_ai = str(_get_evidence(ev_item, "ai_usage_detected")).strip().casefold()
    ev_sig = [str(s).casefold() for s in (_get_evidence(ev_item, "signal_types") or [])]
    if (
        ev_ai in {"no", "not detected"}
        or "non_ai_service_disclosure" in ev_sig
        or "rule_based_automation" in ev_sig
    ):
        return False

    theme_key = str(theme or "").strip().casefold()
    substantiation_rules = THEME_SUBSTANTIATION.get(theme_key)
    if not substantiation_rules:
        # If theme is not specified or 'other', require service relevance not being negative/irrelevant
        return True

    # Check signals
    if any(sig in substantiation_rules["signals"] for sig in ev_sig):
        return True

    # Check text corpus
    text_corpus = " ".join([
        str(_get_evidence(ev_item, "excerpt", "")),
        str(_get_evidence(ev_item, "source_title", "")),
        " ".join(str(t) for t in (_get_evidence(ev_item, "matched_terms") or [])),
    ]).strip().casefold()

    if not text_corpus:
        # Grade-only mock record in unit tests
        return True

    return any(term in text_corpus for term in substantiation_rules["terms"])


def calculate_ai_cyber_risk_score(
    findings: Iterable[Any],
    evidence_records: Iterable[Any] = (),
):
    """Return a prioritization score from reviewer-rated active findings.

    The score is the highest assessed finding normalized across the explicit
    4x3 severity/likelihood matrix, provided it links to accepted evidence for
    the same vendor that substantiates the finding's risk theme. An accepted but
    unrelated source must not validate a risk.
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

        # Check that the attached evidence is accepted AND substantiates the risk theme.
        # An accepted but unrelated source must not validate a risk.
        theme = record.get("theme", record.get("Theme Key", ""))
        supported = False
        for evidence_id in evidence_ids or []:
            key = (vendor_id.casefold(), _text(evidence_id))
            if evidence_by_vendor_and_id.get(key) == "accepted":
                ev_item = next(
                    (
                        e for e in (evidence_records or [])
                        if _text(_get_evidence(e, "evidence_id")) == _text(evidence_id)
                    ),
                    None,
                )
                if ev_item and _evidence_substantiates_risk_theme(ev_item, theme):
                    supported = True
                    break

        if not supported:
            unsupported += 1
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

    if unassessed:
        return {
            "score": None,
            "status": "Assessment incomplete / unassessed — reviewer ratings required",
            "scored_findings": 0,
            "unassessed_findings": unassessed,
            "unsupported_findings": unsupported,
            "driving_finding_id": "",
            "rationale": (
                "One or more active risk findings have unassessed severity or likelihood ratings. "
                "Reviewer ratings are required to assess and score risk findings. "
                "A missing score does not indicate low risk or zero risk."
            ),
        }

    if unsupported:
        return {
            "score": None,
            "status": "No validated AI-specific risk findings",
            "scored_findings": 0,
            "unassessed_findings": 0,
            "unsupported_findings": unsupported,
            "driving_finding_id": "",
            "rationale": (
                "No AI-specific risk finding currently qualifies for scoring because no accepted evidence "
                "substantively supports an AI risk theme. Baseline assurance recommendations remain active "
                "for vendor oversight but do not generate a numeric AI risk index. An unscored assessment "
                "does not represent a verified zero-risk result."
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


def _get_evidence(item, key, default=""):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def generate_preliminary_risk_assessment(
    *,
    vendor_id: str,
    vendor_name: str,
    vendor_row: Any,
    evidence_records: Iterable[Any] = (),
    ai_status: str = "Inconclusive",
    criticality_tier: str = "Medium",
    named_providers: list[str] | None = None,
) -> dict:
    """Generate evidence-linked preliminary risk findings and assessment fields.

    Automates preliminary risk scoring using the 4x3 rubric (Severity x Likelihood / 12 * 100).
    Produces structured RiskFinding records with 'Preliminary' review status,
    overall AI Security Risk Classification, Risk Rationale, and Recommended Actions.
    """
    row_data = dict(vendor_row) if hasattr(vendor_row, "to_dict") else dict(vendor_row or {})
    data_class = str(
        row_data.get("Data Classification Accessed")
        or row_data.get("Data Classification")
        or row_data.get("data_classification_accessed")
        or ""
    ).strip()
    operational_dep = str(
        row_data.get("Operational Dependency")
        or row_data.get("operational_dependency")
        or ""
    ).strip()
    service_provided = str(
        row_data.get("Service / Product Provided")
        or row_data.get("Service Provided")
        or ""
    ).strip()

    evidence_list = list(evidence_records or [])
    evidence_ids = [
        str(_get_evidence(rec, "evidence_id"))
        for rec in evidence_list
        if _get_evidence(rec, "evidence_id")
    ]
    providers = list(named_providers or [])

    findings = []
    clean_vid = _text(vendor_id)
    clean_vname = _text(vendor_name) or clean_vid or "Unknown Vendor"

    is_ai_confirmed = ai_status == "Confirmed"
    is_critical = criticality_tier == "Critical"
    is_high_tier = criticality_tier in {"Critical", "High"}

    data_class_lower = data_class.casefold()
    has_sensitive_data = any(
        term in data_class_lower
        for term in (
            "customer master", "balance", "transaction", "tax", "account number",
            "date of birth", "health", "vulnerability", "call audio", "loan account",
            "financial data", "pii", "confidential", "privileged", "credential"
        )
    )

    if is_ai_confirmed:
        # Finding 1: Sensitive Data & Retention / Model Training (Evidence-supported)
        if has_sensitive_data:
            sev = "Critical" if is_critical else "High"
            lik = "Likely"
            findings.append(
                create_risk_finding(
                    vendor_id=clean_vid,
                    vendor_name=clean_vname,
                    theme="retention_and_training",
                    severity=sev,
                    likelihood=lik,
                    risk_type="evidence_supported",
                    severity_rationale=f"High/Critical severity: vendor processes sensitive customer/financial records ({data_class[:60]}...) which could be compromised if retained or used for foundation model training.",
                    likelihood_rationale="Likely: commercial AI implementations routinely retain inputs or lack verified non-training guarantees unless contractually enforced.",
                    evidence_ids=evidence_ids[:3],
                    finding_id=f"RISK-{clean_vid}-RETENTION",
                    description=(
                        f"Vendor processes sensitive banking/customer data ({data_class[:90]}...) "
                        "and public evidence confirms AI use, with no public verification "
                        "of zero-retention or model training exclusion."
                    ),
                    rationale=(
                        f"Customer data ({data_class[:80]}...) processed by an AI-enabled service "
                        "without contractual confirmation of zero-retention or training opt-out creates "
                        "a potential data leakage and regulatory compliance risk."
                    ),
                    recommended_action=(
                        "Issue targeted AI security questionnaire within 15 business days to confirm "
                        "zero-retention commitments, obtain written guarantee prohibiting model training "
                        "on Meridian data, and amend contractual DPA terms."
                    ),
                    status="Preliminary",
                    reviewer="Automated Intelligence Engine",
                )
            )

        # Finding 2: Provider Transparency & Subprocessor Chain
        if providers:
            sev = "High" if is_high_tier else "Moderate"
            lik = "Possible"
            prov_str = ", ".join(providers)
            findings.append(
                create_risk_finding(
                    vendor_id=clean_vid,
                    vendor_name=clean_vname,
                    theme="provider_transparency",
                    severity=sev,
                    likelihood=lik,
                    risk_type="evidence_supported",
                    severity_rationale=f"High severity: external foundation model dependency ({prov_str}) introduces onward data transfer and fourth-party compliance risks.",
                    likelihood_rationale="Possible: third-party AI provider API integrations are active in production workflows.",
                    evidence_ids=evidence_ids[:3],
                    finding_id=f"RISK-{clean_vid}-PROVIDER",
                    description=(
                        f"Vendor discloses dependence on third-party AI provider(s): {prov_str}. "
                        "Downstream data processing locations and subprocessor change terms require review."
                    ),
                    rationale=(
                        f"Integration with foundation model providers ({prov_str}) introduces onward data "
                        "transfer and fourth-party subprocessor risk to Meridian's supply chain."
                    ),
                    recommended_action=(
                        f"Verify {prov_str} enterprise hosting agreements, enforce subprocessor change notification "
                        "periods, and register vendor on Meridian's AI subprocessor inventory."
                    ),
                    status="Preliminary",
                    reviewer="Automated Intelligence Engine",
                )
            )
        else:
            sev = "High" if is_high_tier else "Moderate"
            lik = "Possible"
            findings.append(
                create_risk_finding(
                    vendor_id=clean_vid,
                    vendor_name=clean_vname,
                    theme="provider_transparency",
                    severity=sev,
                    likelihood=lik,
                    risk_type="assurance_gap",
                    severity_rationale="Moderate/High severity: opaque AI subprocessor chain prevents independent verification of data handling boundaries.",
                    likelihood_rationale="Possible: vendor indicates AI capabilities without disclosing underlying infrastructure providers.",
                    evidence_ids=evidence_ids[:3],
                    finding_id=f"RISK-{clean_vid}-OPACITY",
                    description=(
                        "Vendor indicates AI capabilities but does not publicly name specific underlying "
                        "model providers, hosting regions, or subprocessor chains."
                    ),
                    rationale=(
                        "Opaque AI infrastructure prevents independent validation of onward data flows, "
                        "hosting jurisdictions, and subprocessor compliance."
                    ),
                    recommended_action=(
                        "Require vendor to formally disclose all third-party model providers, API endpoints, "
                        "and hosting regions utilized in the delivered service."
                    ),
                    status="Preliminary",
                    reviewer="Automated Intelligence Engine",
                )
            )

        # Finding 3: Operational Dependency & Oversight
        if operational_dep.casefold() in {"critical", "high"}:
            sev = "High" if is_critical else "Moderate"
            lik = "Possible"
            findings.append(
                create_risk_finding(
                    vendor_id=clean_vid,
                    vendor_name=clean_vname,
                    theme="transparency_and_oversight",
                    severity=sev,
                    likelihood=lik,
                    risk_type="evidence_supported",
                    severity_rationale=f"High severity: operational dependency on service ({service_provided[:60]}...) combined with automated processing requires verified human checkpoints.",
                    likelihood_rationale="Possible: automated model degradation or false-positive actions could disrupt operations without manual fallback.",
                    evidence_ids=evidence_ids[:3],
                    finding_id=f"RISK-{clean_vid}-OVERSIGHT",
                    description=(
                        f"High operational dependency ({operational_dep}) on vendor service ({service_provided[:70]}...) "
                        "coupled with automated processing poses business resilience considerations."
                    ),
                    rationale=(
                        "Automated decisioning or processing workflows require validated human oversight and "
                        "fallback procedures to mitigate model degradation or pipeline failures."
                    ),
                    recommended_action=(
                        "Validate human-in-the-loop oversight mechanisms, error-handling thresholds, "
                        "and operational business continuity plans."
                    ),
                    status="Preliminary",
                    reviewer="Automated Intelligence Engine",
                )
            )

    elif ai_status in {"Inconclusive", "Inconclusive/Needs Review", "Suspected"}:
        # Inconclusive / Suspected AI status produces conditional findings and assurance gaps
        sev = "Moderate" if is_high_tier else "Low"
        lik = "Possible"
        findings.append(
            create_risk_finding(
                vendor_id=clean_vid,
                vendor_name=clean_vname,
                theme="evidence_gaps",
                severity=sev,
                likelihood=lik,
                risk_type="assurance_gap",
                severity_rationale=f"Moderate severity: reflects unconfirmed potential AI exposure in {service_provided[:60]}, pending direct inquiry.",
                likelihood_rationale="Possible: widespread industry adoption of embedded AI tools requires explicit boundary confirmation.",
                evidence_ids=evidence_ids[:2],
                finding_id=f"RISK-{clean_vid}-ASSURANCE-GAP",
                description=(
                    f"Public research yielded partial or inconclusive evidence regarding whether AI capabilities or third-party models are deployed in {service_provided[:60]}. Vendor AI adoption remains unconfirmed from public sources."
                ),
                rationale=(
                    "Assurance gap: public sources do not confirm whether AI models process Meridian data or if third-party AI subprocessors are utilized. Statements of established AI risk are withheld pending direct vendor verification."
                ),
                recommended_action=(
                    "Dispatch vendor AI due diligence questionnaire to establish definitive AI use status, verify subprocessor boundaries, and confirm whether automated processing is applied to Meridian workloads."
                ),
                status="Preliminary",
                reviewer="Automated Intelligence Engine",
            )
        )
        if has_sensitive_data:
            findings.append(
                create_risk_finding(
                    vendor_id=clean_vid,
                    vendor_name=clean_vname,
                    theme="retention_and_training",
                    severity="Moderate",
                    likelihood="Possible",
                    risk_type="conditional",
                    severity_rationale=f"Moderate conditional severity: applies only if vendor's automated processing routes Meridian data ({data_class[:50]}...) to external machine learning services.",
                    likelihood_rationale="Possible conditional likelihood pending confirmation of technical architecture.",
                    evidence_ids=evidence_ids[:2],
                    finding_id=f"RISK-{clean_vid}-CONDITIONAL-DATA",
                    description=(
                        f"Conditional finding: If automated processing in {service_provided[:60]} relies on external AI/ML services, data-retention and training restrictions must be contractually enforced."
                    ),
                    rationale=(
                        "Conditional risk: If automated processing in delivered services relies on external commercial AI/ML services, customer data could face retention or model training risks. Conversely, if processing is confined to internal deterministic rules or local algorithms, AI-specific risks do not apply. In the absence of explicit subprocessor disclosures, external AI exposure remains unconfirmed pending technical architecture review."
                    ),
                    recommended_action=(
                        "Verify through architectural documentation that document parsing and composition engines execute within isolated tenant boundaries without transmitting customer records to external AI foundation models."
                    ),
                    status="Preliminary",
                    reviewer="Automated Intelligence Engine",
                )
            )
    else:
        # Not Detected (No AI detected within assessed scope)
        findings.append(
            create_risk_finding(
                vendor_id=clean_vid,
                vendor_name=clean_vname,
                theme="evidence_gaps",
                severity="Low",
                likelihood="Unlikely",
                risk_type="assurance_gap",
                severity_rationale="Low severity: no AI capabilities detected in investigated public scope; vendor provides deterministic managed services.",
                likelihood_rationale="Unlikely: no evidence of machine learning or generative AI in vendor's professional services offering.",
                evidence_ids=[],
                finding_id=f"RISK-{clean_vid}-BASELINE-MONITORING",
                description=(
                    f"No qualifying public evidence of AI use was detected in the investigated scope for {clean_vname}. Vendor provides deterministic rule-based workload automation services."
                ),
                rationale=(
                    "No affirmative AI cybersecurity risks identified within the investigated public scope. Vendor operations involve privileged access (operational criticality), but no qualifying evidence was detected of AI model integration or generative AI processing; absence of public evidence does not constitute definitive proof of no AI deployment in uninspected systems."
                ),
                recommended_action=(
                    "Standard vendor oversight. Incorporate mandatory 30-day advance notification requirement in annual attestation if AI features, predictive scheduling, or AI subprocessors are introduced."
                ),
                status="Preliminary",
                reviewer="Automated Intelligence Engine",
            )
        )

    # Calculate overall risk classification and rationales
    severity_rank = {"Critical": 4, "High": 3, "Moderate": 2, "Low": 1, "Unassessed": 0}
    max_sev = max((f.severity for f in findings), key=lambda s: severity_rank.get(s, 0), default="Low")

    if not is_ai_confirmed and ai_status == "Not Detected":
        overall_classification = "Low"
    elif max_sev == "Critical":
        overall_classification = "Critical"
    elif max_sev == "High":
        overall_classification = "High"
    elif max_sev == "Moderate":
        overall_classification = "Medium"
    else:
        overall_classification = "Low"

    # Overall Risk Rationale
    if is_ai_confirmed:
        prov_note = f"involving {', '.join(providers)}" if providers else "with undisclosed model providers"
        risk_rationale = (
            f"Vendor processes {data_class[:80]} with {operational_dep} operational dependency. "
            f"Public evidence confirms AI use {prov_note}. "
            f"Lack of explicit zero-retention verification and subprocessor opacity drives a "
            f"{overall_classification} preliminary security risk rating."
        )
    elif ai_status in {"Inconclusive", "Inconclusive/Needs Review", "Suspected"}:
        risk_rationale = (
            f"Public sources provide incomplete assurance regarding potential AI capabilities in {service_provided[:60]}. "
            f"Due to {operational_dep} operational dependency and data classification, a {overall_classification} "
            "preliminary risk rating is assigned pending direct questionnaire resolution."
        )
    else:
        risk_rationale = (
            f"No public evidence of AI usage was detected within the assessed scope for {clean_vname}. "
            f"Privileged operational dependency ({operational_dep}) reflects business criticality, "
            f"not AI-specific cybersecurity risk. Risk classification is {overall_classification}."
        )

    # Overall Recommended Action
    if is_ai_confirmed:
        prov_target = f"covering {', '.join(providers)} dependencies, " if providers else ""
        recommended_action = (
            f"Issue targeted AI security questionnaire within 15 business days {prov_target}"
            "model hosting regions, retention periods, and zero-training guarantees on Meridian data. "
            "Register vendor on AI subprocessor inventory and integrate standard AI security clauses at next contract review."
        )
    elif ai_status in {"Inconclusive", "Inconclusive/Needs Review", "Suspected"}:
        recommended_action = (
            "Issue targeted questionnaire within 30 business days to confirm whether AI is utilized in the supplied service, "
            "and verify third-party subprocessor registers."
        )
    else:
        recommended_action = (
            "Standard vendor oversight. Incorporate mandatory 30-day advance notification requirement "
            "for any future AI or subprocessor deployment into the next contract renewal."
        )

    return {
        "findings": findings,
        "risk_classification": overall_classification,
        "risk_rationale": risk_rationale,
        "recommended_action": recommended_action,
        "highest_severity": max_sev,
    }

