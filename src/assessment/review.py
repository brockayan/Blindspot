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


def sync_vendor_after_review(
    vendor_id: str,
    *,
    evidence_records: list[Any],
    inventory_df: Any = None,
    criticality_ratings: dict[str, Any] | None = None,
    investigation_assessments: dict[str, Any] | None = None,
    risk_findings: list[Any] | None = None,
    relationships: list[Any] | None = None,
    collection_log: list[Any] | None = None,
    reviewer_name: str = "Reviewer",
    collection_complete: bool | None = None,
    collection_failed: bool | None = None,
    failure_reason: str = "",
    enable_case_study_fixtures: bool = True,
) -> dict[str, Any]:
    """Synchronize AI classification, inventory fields, and risk findings for a vendor following reviewer decisions."""
    import pandas as pd
    from src.assessment.classifier import (
        NOT_DETECTED,
        classify_ai_usage,
        status_to_detected_flag,
    )
    from src.assessment.risk import (
        calculate_ai_cyber_risk_score,
        generate_preliminary_risk_assessment,
    )
    from src.assessment.scores import calculate_evidence_score
    from src.collection.fixtures import get_curated_case_study_disclosure

    clean_vid = str(vendor_id or "").strip()
    if not clean_vid:
        return {}

    vendor_ev = [
        e for e in (evidence_records or [])
        if str(_get(e, "vendor_id", "")).strip() == clean_vid
    ]

    # Resolve vendor name
    vendor_name = ""
    if vendor_ev:
        vendor_name = str(_get(vendor_ev[0], "vendor_name", "")).strip()
    if not vendor_name and investigation_assessments and clean_vid in investigation_assessments:
        vendor_name = str(investigation_assessments[clean_vid].get("vendor_name", "")).strip()
    if not vendor_name and criticality_ratings and clean_vid in criticality_ratings:
        vendor_name = str(criticality_ratings[clean_vid].get("vendor_name", "")).strip()
    if not vendor_name and inventory_df is not None and hasattr(inventory_df, "iterrows"):
        for _, r in inventory_df.iterrows():
            if str(r.get("Vendor ID", "")).strip() == clean_vid:
                vendor_name = str(r.get("Vendor Name", "")).strip()
                break
    if not vendor_name:
        vendor_name = clean_vid

    # Resolve collection completeness and failure state
    inv_ass = (investigation_assessments or {}).get(clean_vid, {})
    if collection_complete is None:
        if "collection_complete" in inv_ass:
            collection_complete = bool(inv_ass["collection_complete"])
        else:
            v_logs = [l for l in (collection_log or []) if str(_get(l, "vendor_id", "")).strip() == clean_vid]
            has_fatal_failure = any(
                str(_get(l, "status", "")).lower() in {"failed", "blocked"}
                or "robots" in str(_get(l, "details", "")).lower()
                for l in v_logs
            )
            has_success = any(str(_get(l, "status", "")).lower() == "success" for l in v_logs)
            if has_fatal_failure and not has_success:
                collection_complete = False
            else:
                collection_complete = len(vendor_ev) > 0

    if collection_failed is None:
        if "collection_failed" in inv_ass:
            collection_failed = bool(inv_ass["collection_failed"])
        else:
            v_logs = [l for l in (collection_log or []) if str(_get(l, "vendor_id", "")).strip() == clean_vid]
            collection_failed = any(
                str(_get(l, "status", "")).lower() in {"failed", "blocked"}
                or "robots" in str(_get(l, "details", "")).lower()
                for l in v_logs
            )

    if not failure_reason:
        if "failure_reason" in inv_ass:
            failure_reason = str(inv_ass["failure_reason"])
        else:
            v_logs = [l for l in (collection_log or []) if str(_get(l, "vendor_id", "")).strip() == clean_vid]
            for l in v_logs:
                det = str(_get(l, "details", ""))
                if "robots" in det.lower() or str(_get(l, "status", "")).lower() in {"failed", "blocked"}:
                    failure_reason = det
                    break

    # Authoritative AI-use classification based on reviewed evidence and actual collection status
    ai_ass = classify_ai_usage(
        vendor_ev,
        collection_complete=collection_complete,
        collection_failed=collection_failed,
        failure_reason=failure_reason,
    )
    status = ai_ass.status
    detected_flag = status_to_detected_flag(status)

    if investigation_assessments is not None:
        investigation_assessments[clean_vid] = {
            "vendor_id": clean_vid,
            "vendor_name": vendor_name,
            "status": status,
            "confidence": ai_ass.confidence,
            "summary": ai_ass.summary,
            "evidence_ids": ai_ass.evidence_ids,
            "rationale": ai_ass.rationale,
            "follow_up": ai_ass.follow_up,
            "review_required": ai_ass.review_required,
            "collection_complete": collection_complete,
            "collection_failed": collection_failed,
            "failure_reason": failure_reason,
        }

    # Resolve tier and vendor inventory row
    vendor_row = None
    tier = "High"
    if criticality_ratings and clean_vid in criticality_ratings:
        crit_info = criticality_ratings[clean_vid]
        res = crit_info.get("result")
        if res and hasattr(res, "tier"):
            tier = res.tier
        elif isinstance(crit_info, dict) and "tier" in crit_info:
            tier = crit_info["tier"]

    if inventory_df is not None and hasattr(inventory_df, "iterrows"):
        for _, r in inventory_df.iterrows():
            if str(r.get("Vendor ID", "")).strip() == clean_vid:
                vendor_row = r
                row_tier = r.get("Criticality Tier")
                if row_tier and not pd.isna(row_tier) and str(row_tier).strip():
                    tier = str(row_tier).strip()
                break

    # Resolve source-backed model providers
    named_providers = []
    for r in (relationships or []):
        if str(_get(r, "vendor_id", "")).strip() == clean_vid:
            if "unverified" not in str(_get(r, "status", "")).casefold():
                pname = _get(r, "entity_name")
                if pname and pname not in named_providers:
                    named_providers.append(pname)

    curated = get_curated_case_study_disclosure(
        clean_vid,
        vendor_name=vendor_name,
        enable_fixtures=enable_case_study_fixtures,
    )
    if not named_providers and curated:
        if "azure openai" in curated.get("named_subprocessors", "").casefold():
            named_providers.append("Microsoft Azure OpenAI Service")

    # Authoritative risk findings generation based on updated AI status and evidence
    risk_assessment_res = generate_preliminary_risk_assessment(
        vendor_id=clean_vid,
        vendor_name=vendor_name,
        vendor_row=vendor_row,
        evidence_records=vendor_ev,
        ai_status=status,
        criticality_tier=tier,
        named_providers=named_providers,
    )

    new_findings_objs = risk_assessment_res.get("findings", [])
    new_findings_dicts = [f.to_dict() for f in new_findings_objs]

    if risk_findings is not None:
        retained = [
            f for f in risk_findings
            if str(_get(f, "vendor_id", "")).strip() != clean_vid
        ]
        risk_findings.clear()
        risk_findings.extend(retained + new_findings_dicts)

    ev_score = calculate_evidence_score(vendor_ev)
    cyber_risk_eval = calculate_ai_cyber_risk_score(
        new_findings_dicts,
        evidence_records=vendor_ev,
    )

    # Synchronize inventory DataFrame columns L-V in place
    if inventory_df is not None and hasattr(inventory_df, "iterrows"):
        for idx, r in inventory_df.iterrows():
            if str(r.get("Vendor ID", "")).strip() == clean_vid:
                inventory_df.at[idx, "AI Usage Detected (Y/N)"] = detected_flag
                if "How Vendor May Be Using AI" in inventory_df.columns:
                    inventory_df.at[idx, "How Vendor May Be Using AI"] = (
                        ai_ass.summary or ("No AI usage detected in scope." if status == NOT_DETECTED else "Inconclusive AI signals.")
                    )
                if "AI Security Risk Classification" in inventory_df.columns:
                    inventory_df.at[idx, "AI Security Risk Classification"] = risk_assessment_res["risk_classification"]
                if "Risk Rationale" in inventory_df.columns:
                    inventory_df.at[idx, "Risk Rationale"] = risk_assessment_res["risk_rationale"]
                if "Recommended Action" in inventory_df.columns:
                    inventory_df.at[idx, "Recommended Action"] = risk_assessment_res["recommended_action"]
                if "Assessedd By / Date" in inventory_df.columns:
                    inventory_df.at[idx, "Assessedd By / Date"] = (
                        f"Reviewer ({reviewer_name}) / {datetime.now(timezone.utc).strftime('%d-%m-%Y')}"
                    )
                break

    return {
        "vendor_id": clean_vid,
        "vendor_name": vendor_name,
        "ai_status": status,
        "detected_flag": detected_flag,
        "evidence_score": ev_score,
        "cyber_risk_score": cyber_risk_eval,
        "risk_assessment": risk_assessment_res,
        "new_findings": new_findings_dicts,
    }

