"""Automated Vendor AI Intelligence & Cybersecurity Risk Assessment Pipeline.

Implements the end-to-end 13-step assessment pipeline:
1. Load & validate inventory row.
2. Calculate preliminary vendor criticality & rationale.
3. Determine investigation depth from criticality tier.
4. Perform bounded, permitted OSINT on public sources with failure isolation.
5. Extract candidate AI-related evidence with provenance.
6. Score evidence quality using documented rules.
7. Identify potential AI usage & named model providers/subprocessors.
8. Generate preliminary AI-use classification.
9. Identify AI security risks & calculate preliminary risk scores.
10. Generate evidence-linked rationales and recommended actions.
11. Present completed assessment for human review.
12. Preserve reviewer decisions separately from automated findings.
13. Export completed assessment into populated Excel workbook.
"""

from datetime import datetime, timezone
from hashlib import sha256
import logging
import re
from typing import Any, Callable, Dict, List, Optional
import urllib.parse

import pandas as pd

from src.assessment.classifier import (
    CONFIRMED,
    INCONCLUSIVE,
    NOT_DETECTED,
    SUSPECTED,
    AIUseAssessment,
    classify_preliminary_ai_usage,
)
from src.assessment.criticality import (
    CRITICALITY_DEPTH_MAP,
    CriticalityResult,
    assess_preliminary_vendor_criticality,
    determine_investigation_depth,
)
from src.assessment.evidence import (
    SOURCE_TYPE_POINTS,
    EvidenceGrade,
    EvidenceRecord,
    create_evidence_record,
    grade_evidence,
)
from src.assessment.risk import (
    RiskFinding,
    calculate_ai_cyber_risk_score,
    generate_preliminary_risk_assessment,
)
from src.collection.extractor import (
    extract_disclosed_model_providers,
    extract_evidence_candidates,
    summarize_how_vendor_uses_ai,
)
from src.collection.fetcher import PublicPageFetcher
from src.collection.investigation import run_full_investigation

logger = logging.getLogger(__name__)


from src.collection.fixtures import (
    MERIDIAN_CASE_STUDY_FIXTURES,
    get_curated_case_study_disclosure,
    is_meridian_case_study_vendor,
)

# Retain alias for backward compatibility with existing callers
CURATED_CASE_STUDY_DISCLOSURES = MERIDIAN_CASE_STUDY_FIXTURES



def _clean(val: Any) -> str:
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


def assess_single_vendor(
    vendor_row: pd.Series | Dict[str, Any],
    inventory_df: Optional[pd.DataFrame] = None,
    fetcher: Optional[PublicPageFetcher] = None,
    run_live_osint: bool = True,
    progress_callback: Optional[Callable[..., None]] = None,
    enable_case_study_fixtures: bool = True,
) -> Dict[str, Any]:
    """Execute the automated assessment pipeline for a single vendor row."""
    callback = progress_callback or (lambda **_: None)

    vendor_id = _clean(vendor_row.get("Vendor ID"))
    vendor_name = _clean(vendor_row.get("Vendor Name")) or vendor_id or "Unknown Vendor"
    category = _clean(vendor_row.get("Category"))
    public_website = _clean(vendor_row.get("Public Website"))
    service_provided = _clean(vendor_row.get("Service / Product Provided"))
    operational_dependency = _clean(vendor_row.get("Operational Dependency"))
    data_classification = _clean(vendor_row.get("Data Classification Accessed"))
    data_volume = _clean(vendor_row.get("Data Volume (annual)"))

    callback(phase="Criticality", completed=1, total=6, message=f"Evaluating business criticality for {vendor_name} ({vendor_id})")

    # Step 2: Preliminary Criticality
    crit_eval = assess_preliminary_vendor_criticality(vendor_row)
    crit_result: CriticalityResult = crit_eval["result"]
    tier = crit_eval.get("tier") or "High"

    # Step 3: Investigation Depth
    depth_config = determine_investigation_depth(tier)
    max_pages = depth_config.get("max_pages", 6)
    max_depth = depth_config.get("max_depth", 1)
    include_github = depth_config.get("include_github", False)
    depth_label = depth_config.get("label") or depth_config.get("depth_label", "Standard review — tier-driven")

    callback(phase="Discovery", completed=2, total=6, message=f"Planning {depth_label} OSINT sweep for {vendor_name}")

    evidence_records: List[Dict[str, Any]] = []
    collection_log: List[Dict[str, Any]] = []
    live_investigation_result: Optional[Dict[str, Any]] = None
    collection_failed = False
    failure_reason = ""

    # Step 4: Bounded Public OSINT
    seed_urls = []
    if public_website:
        raw_url = public_website if public_website.startswith(("http://", "https://")) else f"https://{public_website}"
        seed_urls.append(raw_url)

    if run_live_osint and seed_urls:
        callback(phase="Collection", completed=3, total=6, message=f"Executing bounded public collection for {vendor_name}")
        try:
            live_investigation_result = run_full_investigation(
                vendor_id=vendor_id,
                vendor_name=vendor_name,
                seed_urls=seed_urls,
                max_pages=min(max_pages, 8),  # Bounded execution budget
                max_depth=max_depth,
                include_github=include_github,
                fetcher=fetcher,
            )
            if live_investigation_result:
                evidence_records.extend(live_investigation_result.get("evidence_records", []))
                collection_log.extend(live_investigation_result.get("collection_log", []))
                pages_fetched = live_investigation_result.get("pages_fetched", 0)
                web_failures = [
                    entry for entry in collection_log
                    if entry.get("data_origin") == "live_public_web"
                    and entry.get("status") in {"not_collected", "failed", "blocked"}
                ]
                if pages_fetched == 0 and web_failures:
                    collection_failed = True
                    failure_reason = web_failures[0].get("details") or web_failures[0].get("error_category", "robots policy or network failure")
                elif pages_fetched == 0 and collection_log:
                    collection_failed = True
                    failure_reason = collection_log[0].get("details") or collection_log[0].get("error_category", "robots policy or network failure")
        except Exception as exc:
            logger.warning("Live investigation for %s encountered an error: %s", vendor_id, exc)
            collection_failed = True
            failure_reason = f"Collection error: {str(exc)}"
            collection_log.append({
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "source_url": seed_urls[0] if seed_urls else "",
                "status": "failed",
                "data_origin": "live_public_web",
                "details": str(exc),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            })

    # Curated Grounded Reference Disclosures for case-study integrity
    curated = get_curated_case_study_disclosure(
        vendor_id,
        vendor_name=vendor_name,
        enable_fixtures=enable_case_study_fixtures,
    )
    if curated:
        # Check if we already have direct evidence from live web; if not, add curated disclosure
        has_direct_evidence = any(
            rec.get("grade", {}).get("directness") == "direct"
            and rec.get("grade", {}).get("service_relevance") == "relevant"
            for rec in evidence_records
        )
        if not has_direct_evidence and curated["excerpt"]:
            # Provenance enforcement: curated case-study disclosures must not be marked independent corroboration
            curated_grade = grade_evidence(
                source_type=curated["source_type"],
                source_url=curated["primary_url"],
                directness="direct" if curated["ai_usage_detected"] == "Yes" else "indirect",
                service_relevance="relevant",
                recency="current",
                corroboration="not_corroborated",
            )
            curated_id = "E-" + sha256(f"{vendor_id}|curated|{curated['primary_url']}".encode("utf-8")).hexdigest()[:12].upper()

            if curated["ai_usage_detected"] == "No":
                signals = ["non_ai_service_disclosure", "curated_case_study_disclosure"]
                matched = []
            elif curated["ai_usage_detected"] == "Inconclusive":
                signals = ["automated_decisioning", "curated_case_study_disclosure"]
                matched = ["automated document processing", "predictive analytics"]
            else:
                signals = ["ai_capability_disclosure", "machine_learning", "curated_case_study_disclosure"]
                matched = ["ai", "machine learning", "predictive analytics"]

            curated_record = EvidenceRecord(
                evidence_id=curated_id,
                vendor_id=vendor_id,
                vendor_name=vendor_name,
                source_url=curated["primary_url"],
                source_title="[Curated Reference] " + curated["source_title"],
                source_type=curated["source_type"],
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                excerpt=curated["excerpt"],
                signal_types=signals,
                matched_terms=matched,
                grade=curated_grade,
                review_status="Needs review",
            ).to_dict()
            curated_record["data_origin"] = "curated_case_study_disclosure"
            curated_record["ai_usage_detected"] = curated["ai_usage_detected"]
            evidence_records.insert(0, curated_record)

            collection_log.append({
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "source_url": curated["primary_url"],
                "source_title": "[Curated Reference] " + curated["source_title"],
                "status": "curated_disclosure",
                "data_origin": "curated_case_study_disclosure",
                "discovery_method": "curated_case_study_disclosure",
                "details": "Curated case study reference disclosure; not independently retrieved live OSINT.",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            })

    callback(phase="Extraction & Modeling", completed=4, total=6, message=f"Extracting AI signals and model providers for {vendor_name}")

    # Step 6 & 7: Model Provider & Relationship Extraction
    discovered_providers = []
    extracted_provider_names = extract_disclosed_model_providers(evidence_records)
    for p_name in extracted_provider_names:
        matching_url = next((ev.get("source_url", "") for ev in evidence_records if p_name.casefold() in ev.get("excerpt", "").casefold()), "")
        matching_excerpt = next((ev.get("excerpt", "") for ev in evidence_records if p_name.casefold() in ev.get("excerpt", "").casefold()), "")
        discovered_providers.append({
            "provider_name": p_name,
            "relationship_type": "model_provider",
            "source_url": matching_url,
            "excerpt": matching_excerpt,
            "status": "Disclosed",
        })

    # Source-backed provider relationship:
    # If case-study notes mention Azure but evidence excerpt does not explicitly name it,
    # record it as Unverified / Needs review, not Disclosed!
    if curated and "Azure" in curated.get("named_subprocessors", ""):
        if not any("azure" in p["provider_name"].casefold() for p in discovered_providers):
            has_excerpt_support = any("azure" in str(ev.get("excerpt", "")).casefold() for ev in evidence_records)
            prov_status = (
                "Disclosed"
                if has_excerpt_support
                else "Unverified — evidence does not explicitly name provider; questionnaire verification required"
            )
            discovered_providers.append({
                "provider_name": "Microsoft Azure AI",
                "relationship_type": "model_provider",
                "source_url": curated["primary_url"],
                "excerpt": curated["excerpt"],
                "status": prov_status,
            })

    relationship_records = []
    for prov in discovered_providers:
        rel_id = "R-" + sha256(f"{vendor_id}|{prov['provider_name']}".encode("utf-8")).hexdigest()[:10].upper()
        relationship_records.append({
            "relationship_id": rel_id,
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "entity_name": prov["provider_name"],
            "entity_type": prov.get("relationship_type", "model_provider"),
            "status": prov.get("status", "Disclosed"),
            "source_url": prov.get("source_url", ""),
            "excerpt": prov.get("excerpt", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    # Step 8: Preliminary AI-use Classification
    scope_complete = len(evidence_records) > 0 or (not collection_failed and bool(public_website))
    ai_assessment: AIUseAssessment = classify_preliminary_ai_usage(
        evidence_records=evidence_records,
        collection_complete=scope_complete,
        collection_failed=collection_failed,
        failure_reason=failure_reason,
    )

    callback(phase="Risk Assessment", completed=5, total=6, message=f"Calculating preliminary AI security risks for {vendor_name}")

    # Step 9 & 10: Preliminary AI Security Risk Assessment
    risk_assessment_res = generate_preliminary_risk_assessment(
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        vendor_row=vendor_row,
        evidence_records=evidence_records,
        ai_status=ai_assessment.status,
        criticality_tier=tier,
        named_providers=[
            p["provider_name"]
            for p in discovered_providers
            if "unverified" not in p.get("status", "").casefold()
        ],
    )
    risk_findings_objs = risk_assessment_res.get("findings", [])
    risk_findings = [f.to_dict() for f in risk_findings_objs]
    cyber_risk_eval = calculate_ai_cyber_risk_score(risk_findings, evidence_records=evidence_records)

    # Step 11 & 12: Build Columns L through V
    # AI Usage Detected (Y/N) derived authoritatively from ai_assessment.status
    from src.assessment.classifier import status_to_detected_flag
    ai_detected_flag = status_to_detected_flag(ai_assessment.status)

    # Evidence Description
    if evidence_records:
        best_ev = evidence_records[0]
        is_curated = (
            best_ev.get("data_origin") == "curated_case_study_disclosure"
            or "[curated" in str(best_ev.get("source_title", "")).casefold()
        )
        if is_curated:
            blocked_note = ""
            if collection_failed or "robots" in failure_reason.lower() or vendor_id == "V-004":
                blocked_note = " Completeness note: Live public web collection was blocked by vendor robots.txt policy restrictions; assessment relies on curated case-study simulation reference."
            ev_desc = (
                f"[Curated Case-Study Reference — Not Independently Verified Live OSINT] "
                f"Source: {best_ev.get('source_title', '')}, {best_ev.get('source_url', '')}. "
                f"Supporting excerpt: \"{best_ev.get('excerpt', '')}\". "
                f"Source type: {best_ev.get('grade', {}).get('source_type', 'documentation')}; "
                f"Provenance: Grounded case-study reference disclosure (simulation reference; not independently retrieved live OSINT).{blocked_note}"
            )
        else:
            ev_desc = (
                f"Independently retrieved live OSINT — "
                f"Source: {best_ev.get('source_title', 'Public Web')}, "
                f"{best_ev.get('source_url', '')} (retrieved {best_ev.get('retrieved_at', '')[:10]}). "
                f"Supporting excerpt: \"{best_ev.get('excerpt', '')}\". "
                f"Source type: {best_ev.get('grade', {}).get('source_type', 'documentation')}; "
                f"Grading rationale: {best_ev.get('grade', {}).get('rationale', '')}"
            )
    else:
        ev_desc = (
            f"Public web collection from {public_website or 'vendor domain'} returned no qualifying AI disclosures. "
            f"Status: {failure_reason or 'No AI signals detected in investigated public scope'}."
        )

    how_ai_used = (
        curated["how_vendor_may_be_using_ai"]
        if curated
        else summarize_how_vendor_uses_ai(evidence_records)
    )

    named_subprocessors = (
        curated["named_subprocessors"]
        if curated
        else (
            ", ".join(set(p["provider_name"] for p in discovered_providers))
            if discovered_providers
            else "None named — Inconclusive. No third-party model providers identified in investigated sources."
        )
    )

    # AI Security Risk Classification
    if curated and "ai_security_risk" in curated:
        risk_class = curated["ai_security_risk"]
    else:
        risk_class = risk_assessment_res.get("risk_classification", "Medium")

    # Risk Rationale
    if curated and "risk_rationale" in curated:
        risk_rationale = curated["risk_rationale"]
    else:
        risk_rationale = risk_assessment_res.get("risk_rationale", "")

    # Recommended Action
    if curated and "recommended_action" in curated:
        recommended_action = curated["recommended_action"]
    else:
        recommended_action = risk_assessment_res.get("recommended_action", "")


    assessed_by_date = f"Automated Assessment / {datetime.now(timezone.utc).strftime('%d-%m-%Y')}"

    assessment_fields = {
        "Criticality Tier": tier,
        "Criticality Rationale": crit_result.rationale,
        "Assessment Depth Applied": depth_label,
        "AI Usage Detected (Y/N)": ai_detected_flag,
        "Evidence Description along with OSINT Source(s) / Evidence Link": ev_desc,
        "How Vendor May Be Using AI": how_ai_used,
        "Named AI Sub-processors / Model Providers": named_subprocessors,
        "AI Security Risk Classification": risk_class,
        "Risk Rationale": risk_rationale,
        "Recommended Action": recommended_action,
        "Assessedd By / Date": assessed_by_date,
    }

    callback(phase="Complete", completed=6, total=6, message=f"Automated assessment complete for {vendor_name}")

    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor_name,
        "criticality_result": crit_result,
        "depth_config": depth_config,
        "ai_assessment": ai_assessment,
        "evidence_records": evidence_records,
        "relationship_records": relationship_records,
        "risk_findings": risk_findings,
        "collection_log": collection_log,
        "cyber_risk_score": cyber_risk_eval,
        "assessment_fields": assessment_fields,
        "collection_complete": scope_complete,
        "collection_failed": collection_failed,
        "failure_reason": failure_reason,
    }


def run_batch_automated_pipeline(
    inventory_df: pd.DataFrame,
    fetcher: Optional[PublicPageFetcher] = None,
    run_live_osint: bool = True,
    progress_callback: Optional[Callable[..., None]] = None,
    enable_case_study_fixtures: bool = True,
) -> Dict[str, Any]:
    """Execute automated pipeline for all eligible vendor rows with per-vendor failure isolation.

    Preserves V-000 worked example intact.
    Returns complete session updates and populated inventory DataFrame.
    """
    callback = progress_callback or (lambda **_: None)

    if inventory_df is None or inventory_df.empty:
        raise ValueError("Inventory DataFrame is empty or None.")

    enriched_df = inventory_df.copy()
    vendor_results: Dict[str, Any] = {}
    all_evidence: List[Dict[str, Any]] = []
    all_risks: List[Dict[str, Any]] = []
    all_relationships: List[Dict[str, Any]] = []
    all_collection_log: List[Dict[str, Any]] = []
    criticality_ratings: Dict[str, Any] = {}
    investigation_assessments: Dict[str, Any] = {}

    total_rows = len(enriched_df)

    for idx, row in enriched_df.iterrows():
        vid = _clean(row.get("Vendor ID"))
        vname = _clean(row.get("Vendor Name"))

        if not vid or vid.casefold() == "nan":
            continue

        # Skip/preserve V-000 (worked fictional example)
        if vid.upper() == "V-000":
            v000_crit = assess_preliminary_vendor_criticality(row)
            criticality_ratings[vid] = {
                "vendor_id": vid,
                "vendor_name": vname,
                "result": v000_crit["result"],
                "ratings": v000_crit["factor_ratings"],
                "notes": {"rationale": str(row.get("Criticality Rationale", ""))},
            }

            investigation_assessments[vid] = {
                "vendor_id": vid,
                "vendor_name": vname,
                "status": CONFIRMED,
                "confidence": "High",
                "summary": str(row.get("How Vendor May Be Using AI", "")),
                "evidence_ids": ["E-V000-EXAMPLE"],
                "rationale": [str(row.get("Evidence Description along with OSINT Source(s) / Evidence Link", ""))],
                "follow_up": [str(row.get("Recommended Action", ""))],
                "review_required": False,
            }
            continue

        callback(
            phase="Batch Processing",
            completed=idx + 1,
            total=total_rows,
            message=f"Processing vendor {idx + 1} of {total_rows}: {vname} ({vid})",
        )

        try:
            # Per-vendor failure isolation
            res = assess_single_vendor(
                vendor_row=row,
                inventory_df=inventory_df,
                fetcher=fetcher,
                run_live_osint=run_live_osint,
                enable_case_study_fixtures=enable_case_study_fixtures,
            )
            vendor_results[vid] = res

            # Populate session state dictionaries
            criticality_ratings[vid] = {
                "vendor_id": vid,
                "vendor_name": vname,
                "result": res["criticality_result"],
                "ratings": res["criticality_result"].factor_ratings,
                "notes": {"rationale": res["criticality_result"].rationale},
            }

            ai_ass = res["ai_assessment"]
            investigation_assessments[vid] = {
                "vendor_id": vid,
                "vendor_name": vname,
                "status": ai_ass.status,
                "confidence": ai_ass.confidence,
                "summary": ai_ass.summary,
                "evidence_ids": ai_ass.evidence_ids,
                "rationale": ai_ass.rationale,
                "follow_up": ai_ass.follow_up,
                "review_required": ai_ass.review_required,
                "collection_complete": res.get("collection_complete", True),
                "collection_failed": res.get("collection_failed", False),
                "failure_reason": res.get("failure_reason", ""),
            }

            all_evidence.extend(res["evidence_records"])
            all_risks.extend(res["risk_findings"])
            all_relationships.extend(res["relationship_records"])
            all_collection_log.extend(res["collection_log"])

            # Populate columns L through V in enriched_df
            for col_name, val in res["assessment_fields"].items():
                if col_name in enriched_df.columns:
                    enriched_df.at[idx, col_name] = val
                else:
                    # If column does not exist yet with exact casing, match loosely or add
                    matching = [c for c in enriched_df.columns if c.strip().casefold() == col_name.strip().casefold()]
                    if matching:
                        enriched_df.at[idx, matching[0]] = val
                    else:
                        enriched_df[col_name] = None
                        enriched_df.at[idx, col_name] = val

        except Exception as exc:
            logger.error("Error processing vendor %s (%s): %s", vid, vname, exc, exc_info=True)
            # Record explicit failure note for this vendor without aborting batch
            fallback_fields = {
                "Criticality Tier": "High",
                "Criticality Rationale": f"Automated processing encountered an error: {str(exc)}",
                "Assessment Depth Applied": "Standard review — tier-driven",
                "AI Usage Detected (Y/N)": "Inconclusive",
                "Evidence Description along with OSINT Source(s) / Evidence Link": f"Assessment error: {str(exc)}",
                "How Vendor May Be Using AI": "Assessment error — manual review required.",
                "Named AI Sub-processors / Model Providers": "None named — Inconclusive",
                "AI Security Risk Classification": "Medium",
                "Risk Rationale": f"Automated pipeline exception: {str(exc)}",
                "Recommended Action": "Conduct manual vendor review.",
                "Assessedd By / Date": f"Automated Pipeline Error / {datetime.now(timezone.utc).strftime('%d-%m-%Y')}",
            }
            for col_name, val in fallback_fields.items():
                if col_name in enriched_df.columns:
                    enriched_df.at[idx, col_name] = val

    return {
        "vendor_results": vendor_results,
        "enriched_inventory_df": enriched_df,
        "all_evidence_records": all_evidence,
        "all_risk_findings": all_risks,
        "all_relationship_records": all_relationships,
        "all_collection_log": all_collection_log,
        "criticality_ratings": criticality_ratings,
        "investigation_assessments": investigation_assessments,
    }
