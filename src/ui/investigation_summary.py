
"""Vendor AI-use investigation summary for Project BlindSpot."""

import pandas as pd
import streamlit as st

from src.assessment.classifier import classify_ai_usage
from src.io.validation import duplicate_vendor_ids


def _get(item, field, default=None):
    """Read a field from a dictionary or an object."""
    if isinstance(item, dict):
        return item.get(field, default)

    return getattr(item, field, default)


def show_investigation_summary():
    """Display evidence-led AI-use classifications by vendor."""

    st.title("Investigation Summary")
    st.caption(
        "Explainable AI-use classifications based on reviewed evidence "
        "and recorded investigation coverage."
    )

    inventory = st.session_state.get("inventory_df")
    evidence_records = st.session_state.get("evidence_records", [])
    collection_log = st.session_state.get("collection_log", [])

    if not isinstance(inventory, pd.DataFrame) or inventory.empty:
        st.info("Load the vendor inventory before assessing AI usage.")
        return

    if not {"Vendor ID", "Vendor Name"}.issubset(inventory.columns):
        st.error("Vendor ID and Vendor Name columns are required.")
        return
    if duplicate_vendor_ids(inventory):
        st.error(
            "Resolve duplicate Vendor IDs before creating vendor "
            "investigation summaries."
        )
        return

    st.warning(
        "Not Detected means no qualifying evidence was found within the "
        "assessed scope. It does not prove that the vendor never uses AI."
    )

    vendor_options = {}

    for _, row in inventory.iterrows():
        if pd.isna(row["Vendor ID"]) or not str(row["Vendor ID"]).strip():
            continue
        if pd.isna(row["Vendor Name"]) or not str(row["Vendor Name"]).strip():
            continue
        vendor_id = str(row["Vendor ID"])
        vendor_name = str(row["Vendor Name"])
        label = f"{vendor_name} ({vendor_id})"
        vendor_options[label] = (vendor_id, vendor_name)

    if not vendor_options:
        st.info("No vendor with a usable Vendor ID is available.")
        return

    selected_label = st.selectbox(
        "Select vendor",
        list(vendor_options.keys()),
        key="summary_vendor",
    )

    vendor_id, vendor_name = vendor_options[selected_label]

    vendor_evidence = [
        item
        for item in evidence_records
        if str(_get(item, "vendor_id", "")) == vendor_id
    ]

    vendor_collection_log = [
        item
        for item in collection_log
        if str(_get(item, "vendor_id", "")) == vendor_id
    ]

    st.subheader("Investigation coverage")

    attempts = len(vendor_collection_log)

    successful_fetches = sum(
        1
        for item in vendor_collection_log
        if str(_get(item, "status", "")).lower() == "success"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Evidence records", len(vendor_evidence))

    with col2:
        st.metric("Collection attempts", attempts)

    with col3:
        st.metric("Successful fetches", successful_fetches)

    # A successful fetch count alone does not establish that the intended
    # investigation scope is complete. Completion must be explicitly marked.
    st.subheader("Scope completion")

    scope_key = f"scope_complete_{vendor_id}"

    scope_complete = st.checkbox(
        "I have completed the intended public-source checks for this vendor.",
        key=scope_key,
        help=(
            "Select only after checking the intended sources and recording "
            "relevant collection failures. This is not a claim that every "
            "possible public source has been searched."
        ),
    )
    scope_notes = st.text_area(
        "Completed scope and access limitations",
        key=f"scope_notes_{vendor_id}",
        help=(
            "Record the source categories checked and any inaccessible, "
            "unavailable, or out-of-scope sources."
        ),
    )

    if st.button(
        "Classify AI usage",
        type="primary",
        key=f"classify_vendor_{vendor_id}",
    ):
        if scope_complete and not scope_notes.strip():
            st.error(
                "Document the completed search scope and access limitations "
                "before recording Not Detected."
            )
        else:
            assessment = classify_ai_usage(
                evidence_records=vendor_evidence,
                collection_complete=scope_complete,
            )

            st.session_state.setdefault("investigation_assessments", {})
            st.session_state["investigation_assessments"][vendor_id] = {
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "status": assessment.status,
                "confidence": assessment.confidence,
                "summary": assessment.summary,
                "evidence_ids": assessment.evidence_ids,
                "rationale": assessment.rationale,
                "follow_up": assessment.follow_up,
                "review_required": assessment.review_required,
                "scope_complete": scope_complete,
                "scope_notes": scope_notes.strip(),
            }
            st.session_state["assessment_workbook_bytes"] = None

    assessment = st.session_state.get(
        "investigation_assessments", {}
    ).get(vendor_id)

    if not assessment:
        st.info(
            "No classification has been recorded for this vendor yet."
        )
        return

    st.divider()
    st.subheader("AI-use classification")

    st.markdown(f"### {assessment['status']}")
    st.write(assessment["summary"])

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Confidence", assessment["confidence"])

    with col2:
        st.metric(
            "Human review required",
            "Yes" if assessment["review_required"] else "No",
        )

    st.markdown("**Rationale**")

    for item in assessment["rationale"]:
        st.write(f"- {item}")

    st.markdown("**Supporting evidence IDs**")

    if assessment["evidence_ids"]:
        st.write(", ".join(assessment["evidence_ids"]))
    else:
        st.caption("No qualifying evidence IDs were attached.")

    st.markdown("**Recommended follow-up**")

    for item in assessment["follow_up"]:
        st.write(f"- {item}")

    st.caption(
        "This classification reflects the current evidence records and "
        "review statuses. It is not an independent security certification."
    )

    st.divider()
    st.subheader("Export investigation summary")

    all_assessments = list(
        st.session_state.get("investigation_assessments", {}).values()
    )

    if all_assessments:
        summary_df = pd.DataFrame(all_assessments)

        st.dataframe(
            summary_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Export AI investigation summary",
            data=summary_df.to_csv(index=False).encode("utf-8"),
            file_name="blindspot_ai_investigation_summary.csv",
            mime="text/csv",
        )
