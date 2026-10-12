"""Judge-facing live vendor investigation workflow."""

import pandas as pd
import requests
import streamlit as st

from src.assessment.classifier import classify_ai_usage
from src.assessment.scores import calculate_evidence_score
from src.assessment.risk import calculate_ai_cyber_risk_score
from src.collection.investigation import run_full_investigation
from src.io.validation import duplicate_vendor_ids
from src.ui.collection_page import merge_evidence_records


def _get(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _vendor_url_columns(inventory):
    return [
        column
        for column in inventory.columns
        if any(
            token in str(column).casefold()
            for token in ("url", "website", "domain", "web address")
        )
    ]


def _display_scores(vendor_id):
    evidence = [
        item for item in st.session_state.get("evidence_records", [])
        if str(_get(item, "vendor_id", "")) == vendor_id
    ]
    findings = [
        item for item in st.session_state.get("risk_findings", [])
        if str(_get(item, "vendor_id", "")) == vendor_id
    ]
    evidence_score = calculate_evidence_score(evidence)
    risk_score = calculate_ai_cyber_risk_score(
        findings,
        evidence_records=evidence,
    )
    criticality_assessment = st.session_state.get(
        "criticality_ratings", {}
    ).get(vendor_id, {})
    criticality_result = criticality_assessment.get("result")
    criticality_score = _get(criticality_result, "score")
    criticality_status = _get(
        criticality_result,
        "status",
        "Unassessed",
    )

    columns = st.columns(3)
    columns[0].metric(
        "Business criticality",
        f"{criticality_score:.1f}/100"
        if isinstance(criticality_score, (int, float))
        else "Unassessed",
        help=f"{criticality_status}. Business importance, not AI risk.",
    )
    columns[1].metric(
        "Evidence quality",
        f"{evidence_score['score']:.1f}/100"
        if evidence_score["score"] is not None
        else "Unassessed",
        help=(
            "Mean accepted, relevant source-grade points normalized to "
            "0–100; not AI-use confidence or a probability."
        ),
    )
    columns[2].metric(
        "AI cybersecurity risk",
        f"{risk_score['score']:.1f}/100"
        if risk_score["score"] is not None
        else "Unassessed",
        help=(
            "Highest active reviewer-rated severity/likelihood index "
            "supported by accepted evidence; not a probability."
        ),
    )
    with st.expander("Score methodology and coverage"):
        st.write(
            "**Criticality:** weighted score from the five business factors; "
            "unknowns remain incomplete and numeric volume bands are not "
            "invented."
        )
        st.write(f"**Criticality status:** {criticality_status}")
        st.write(f"**Evidence quality:** {evidence_score['rationale']}")
        st.write(f"Accepted graded evidence count: {evidence_score['evidence_count']}")
        st.write(f"**AI cybersecurity risk:** {risk_score['rationale']}")
        st.write(
            "Risk score coverage: "
            f"{risk_score['scored_findings']} scored finding(s), "
            f"{risk_score['unassessed_findings']} unassessed, "
            f"{risk_score['unsupported_findings']} without accepted linked "
            "evidence."
        )


def show_live_investigation_lab():
    """Render one-click, observable live public-source investigation."""
    st.title("Live Vendor Investigation Lab")
    st.caption(
        "Run a bounded, traceable public-source investigation for one vendor."
    )
    st.warning(
        "The lab performs real network requests to public websites and, only "
        "when enabled, the public GitHub API. Results are source candidates, "
        "not verified claims. It does not bypass robots rules, access controls, "
        "CAPTCHAs, authentication, or paywalls."
    )
    st.info(
        "Public website discovery starts from the inventory URL and analyst "
        "URLs, checks common same-domain paths, and follows relevant linked "
        "pages within the seeded vendor domain. Public repository search uses "
        "GitHub's unauthenticated API and submits the selected vendor name."
    )

    inventory = st.session_state.get("inventory_df")
    if not isinstance(inventory, pd.DataFrame) or inventory.empty:
        st.info("Upload the vendor inventory before running an investigation.")
        return
    if not {"Vendor ID", "Vendor Name"}.issubset(inventory.columns):
        st.error("The inventory must contain Vendor ID and Vendor Name.")
        return
    if duplicate_vendor_ids(inventory):
        st.error(
            "Resolve duplicate Vendor IDs before running an investigation."
        )
        return

    vendor_options = {}
    for _, row in inventory.iterrows():
        raw_vendor_id = row.get("Vendor ID", "")
        raw_vendor_name = row.get("Vendor Name", "")
        if pd.isna(raw_vendor_id) or pd.isna(raw_vendor_name):
            continue
        vendor_id = str(raw_vendor_id).strip()
        vendor_name = str(raw_vendor_name).strip()
        if (
            vendor_id
            and vendor_id.casefold() != "nan"
            and vendor_name
            and vendor_name.casefold() != "nan"
        ):
            vendor_options[f"{vendor_name} ({vendor_id})"] = (vendor_id, row)
    if not vendor_options:
        st.info("No vendor with a usable ID and name is available.")
        return

    selected_label = st.selectbox(
        "Select vendor",
        list(vendor_options),
        key="live_lab_vendor",
    )
    vendor_id, vendor_row = vendor_options[selected_label]
    vendor_name = str(vendor_row["Vendor Name"]).strip()
    url_columns = _vendor_url_columns(inventory)
    seed_urls = []
    for column in url_columns:
        value = vendor_row.get(column)
        if pd.notna(value) and str(value).strip():
            seed_urls.append(str(value).strip())

    if seed_urls:
        st.write("**Inventory source URL(s):**")
        st.write(", ".join(seed_urls))
    else:
        st.warning(
            "No website URL was found in the inventory. Add one or more "
            "analyst-verified URLs below; vendor-name guessing is not used."
        )

    manual_urls = st.text_area(
        "Additional analyst-verified public URLs",
        placeholder="Enter one public HTTP(S) URL per line",
        key=f"live_lab_manual_urls_{vendor_id}",
    )
    seed_urls.extend(
        line.strip()
        for line in manual_urls.splitlines()
        if line.strip()
    )
    include_github = st.checkbox(
        "Search public GitHub repositories (sends this vendor name to GitHub)",
        value=False,
        key=f"live_lab_github_{vendor_id}",
    )
    max_pages = st.slider(
        "Maximum public HTML pages to fetch",
        min_value=1,
        max_value=30,
        value=8,
        key=f"live_lab_max_pages_{vendor_id}",
        help=(
            "Every page remains subject to destination safety checks, "
            "robots.txt, request timeouts, and size/content limits."
        ),
    )

    can_run = bool(seed_urls or include_github)
    if st.button(
        "Run Full Investigation",
        type="primary",
        key=f"run_full_investigation_{vendor_id}",
        disabled=not can_run,
    ):
        status_container = st.status(
            "Starting live vendor investigation...",
            expanded=True,
        )
        progress_bar = st.progress(0)

        def update_progress(*, phase, completed, total, message):
            fraction = min(1.0, completed / total) if total else 0.0
            progress_bar.progress(fraction, text=f"{phase}: {message}")
            status_container.write(f"**{phase}:** {message}")

        try:
            result = run_full_investigation(
                vendor_id=vendor_id,
                vendor_name=vendor_name,
                seed_urls=seed_urls,
                max_pages=max_pages,
                include_github=include_github,
                progress_callback=update_progress,
            )
            evidence, added_count, duplicate_count = merge_evidence_records(
                st.session_state.get("evidence_records", []),
                result["evidence_records"],
            )
            st.session_state["evidence_records"] = evidence
            st.session_state["collection_log"] = (
                list(st.session_state.get("collection_log", []))
                + result["collection_log"]
            )
            st.session_state.setdefault("discovered_sources", {})[
                vendor_id
            ] = result["candidates"]
            st.session_state["investigation_vendor_id"] = vendor_id
            st.session_state["investigation_vendor_name"] = vendor_name
            st.session_state.setdefault("live_investigation_results", {})[
                vendor_id
            ] = {
                **result,
                "evidence_added": added_count,
                "duplicate_evidence": duplicate_count,
                "completed_at": pd.Timestamp.now(tz="UTC").isoformat(),
            }
            classification = classify_ai_usage(
                [
                    item for item in evidence
                    if str(_get(item, "vendor_id", "")) == vendor_id
                ],
                collection_complete=False,
            )
            st.session_state.setdefault(
                "investigation_assessments", {}
            )[vendor_id] = {
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "status": classification.status,
                "confidence": classification.confidence,
                "summary": classification.summary,
                "evidence_ids": classification.evidence_ids,
                "rationale": classification.rationale,
                "follow_up": classification.follow_up,
                "review_required": classification.review_required,
                "scope_complete": False,
                "scope_notes": (
                    "Live Lab run completed; public-source scope is not "
                    "reviewer-certified complete. Review all candidates."
                ),
            }
            st.session_state["assessment_workbook_bytes"] = None
            status_container.update(
                label="Live investigation finished.",
                state="complete",
                expanded=False,
            )
        except (ValueError, requests.RequestException) as exc:
            status_container.update(
                label="Investigation did not complete.",
                state="error",
                expanded=True,
            )
            st.error(
                f"Live investigation failed ({type(exc).__name__}). "
                "Check the URL, network access, and application logs, then retry."
            )

    prior_result = st.session_state.get(
        "live_investigation_results", {}
    ).get(vendor_id)
    if prior_result:
        st.divider()
        st.subheader("Latest live investigation results")
        st.caption(
            f"Run ID: {prior_result['run_id']} | Origin: live public sources | "
            f"Pages fetched: {prior_result['pages_fetched']}/"
            f"{prior_result['pages_attempted']}"
        )
        st.metric(
            "New evidence records",
            prior_result.get("evidence_added", 0),
        )
        st.write(
            "AI-use classification:",
            st.session_state.get(
                "investigation_assessments", {}
            ).get(vendor_id, {}).get("status", "Inconclusive/Needs Review"),
        )
        _display_scores(vendor_id)

        st.subheader("Discovered public-source candidates")
        st.dataframe(
            pd.DataFrame(prior_result["candidates"]),
            use_container_width=True,
            hide_index=True,
        )
        st.subheader("Traceable evidence candidates")
        vendor_evidence = [
            item for item in st.session_state.get("evidence_records", [])
            if str(_get(item, "vendor_id", "")) == vendor_id
        ]
        if vendor_evidence:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Evidence ID": _get(item, "evidence_id", ""),
                        "Source URL": _get(item, "source_url", ""),
                        "Title": _get(item, "source_title", ""),
                        "Retrieved At (UTC)": _get(item, "retrieved_at", ""),
                        "Excerpt": _get(item, "excerpt", ""),
                        "Review status": _get(item, "review_status", "Needs review"),
                    }
                    for item in vendor_evidence
                ]),
                use_container_width=True,
                hide_index=True,
            )
            st.info(
                "Review each candidate in Review Centre. The lab never accepts "
                "evidence automatically; unresolved candidates keep the AI-use "
                "classification inconclusive."
            )
        else:
            st.info(
                "No AI-related passage candidates were extracted from fetched "
                "pages. This does not establish that the vendor does not use AI."
            )

        run_logs = [
            item for item in prior_result["collection_log"]
            if item.get("run_id") == prior_result["run_id"]
        ]
        if run_logs:
            st.subheader("Live collection log")
            st.dataframe(
                pd.DataFrame(run_logs),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info(
            "No Live Lab run has been recorded for this vendor. Existing "
            "assessments and manual collection remain available in their "
            "current workflow pages."
        )
