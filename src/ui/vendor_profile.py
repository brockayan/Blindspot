
"""Unified vendor profile for Project BlindSpot."""

import pandas as pd
import streamlit as st

from src.assessment.risk import calculate_ai_cyber_risk_score
from src.assessment.scores import calculate_evidence_score
from src.io.validation import duplicate_vendor_ids
from src.ui.intelligence_mesh import relationship_records_for_display


def _get(item, field, default=None):
    """Read a value from a dictionary or an object."""
    if isinstance(item, dict):
        return item.get(field, default)

    return getattr(item, field, default)


def _as_dataframe(records):
    """Convert records into a displayable DataFrame."""
    rows = []

    for item in records:
        if isinstance(item, dict):
            rows.append(dict(item))
        elif hasattr(item, "__dataclass_fields__"):
            from dataclasses import asdict
            rows.append(asdict(item))
        else:
            rows.append(vars(item).copy())

    return pd.DataFrame(rows)


def show_vendor_profile():
    """Display the combined assessment for one vendor."""

    st.title("Vendor Profile")
    st.caption(
        "A consolidated view of business criticality, AI-use evidence, "
        "human review, and security risk."
    )

    inventory = st.session_state.get("inventory_df")

    if not isinstance(inventory, pd.DataFrame) or inventory.empty:
        st.info("Load the vendor inventory to view vendor profiles.")
        return

    required_columns = {"Vendor ID", "Vendor Name"}

    if not required_columns.issubset(inventory.columns):
        st.error("Vendor ID and Vendor Name columns are required.")
        return
    if duplicate_vendor_ids(inventory):
        st.error(
            "Resolve duplicate Vendor IDs before viewing vendor profiles."
        )
        return

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
        key="profile_vendor_selector",
    )

    vendor_id, vendor_name = vendor_options[selected_label]

    st.divider()

    st.header(vendor_name)
    st.caption(f"Vendor ID: {vendor_id}")

    # --------------------------------------------------------
    # Retrieve available assessments
    # --------------------------------------------------------

    criticality = st.session_state.get(
        "criticality_ratings", {}
    ).get(vendor_id)

    investigation = st.session_state.get(
        "investigation_assessments", {}
    ).get(vendor_id)

    all_evidence = st.session_state.get("evidence_records", [])

    vendor_evidence = [
        item
        for item in all_evidence
        if str(_get(item, "vendor_id", "")) == vendor_id
    ]

    all_findings = st.session_state.get("risk_findings", [])

    vendor_findings = [
        item
        for item in all_findings
        if str(_get(item, "vendor_id", "")) == vendor_id
    ]

    all_relationships = st.session_state.get(
        "relationship_records", []
    )

    vendor_relationships = [
        item
        for item in all_relationships
        if (
            str(_get(item, "vendor_id", "")) == vendor_id
            or (
                not _get(item, "vendor_id")
                and (
                    str(_get(item, "source_name", "")).casefold()
                    == vendor_name.casefold()
                    or str(_get(item, "target_name", "")).casefold()
                    == vendor_name.casefold()
                )
            )
        )
    ]
    vendor_relationships = relationship_records_for_display(
        [
            dict(item) if isinstance(item, dict) else vars(item).copy()
            for item in vendor_relationships
        ],
        all_evidence,
    )
    evidence_score = calculate_evidence_score(vendor_evidence)
    cyber_risk_score = calculate_ai_cyber_risk_score(
        vendor_findings,
        evidence_records=vendor_evidence,
    )

    # --------------------------------------------------------
    # Overview metrics
    # --------------------------------------------------------

    st.subheader("Assessment overview")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        score = (
            _get(criticality.get("result"), "score")
            if criticality else None
        )

        st.metric(
            "Criticality",
            f"{score:.1f}/100"
            if isinstance(score, (int, float))
            else "Unassessed",
        )

    with col2:
        st.metric(
            "AI-use status",
            investigation.get("status", "Not assessed")
            if investigation else "Not assessed",
        )

    with col3:
        st.metric("Evidence records", len(vendor_evidence))

    with col4:
        st.metric("Risk findings", len(vendor_findings))

    score_col1, score_col2 = st.columns(2)
    score_col1.metric(
        "Evidence quality score",
        f"{evidence_score['score']:.1f}/100"
        if evidence_score["score"] is not None
        else "Unassessed",
        help="Accepted, relevant source quality; not AI-use confidence.",
    )
    score_col2.metric(
        "AI cybersecurity risk score",
        f"{cyber_risk_score['score']:.1f}/100"
        if cyber_risk_score["score"] is not None
        else "Unassessed",
        help="Reviewer-rated index based on accepted-evidence-supported findings.",
    )

    # --------------------------------------------------------
    # Business criticality
    # --------------------------------------------------------

    st.divider()
    st.subheader("1. Business criticality")

    if criticality:
        result = criticality.get("result")

        st.write(
            f"**Assessment status:** "
            f"{_get(result, 'status', 'Unassessed')}"
        )

        coverage = _get(result, "coverage")
        if coverage is None:
            coverage = _get(result, "coverage_percent")

        if isinstance(coverage, (int, float)):
            st.write(f"**Factor coverage:** {coverage:.0%}")

        ratings = criticality.get("ratings", {})
        notes = criticality.get("notes", {})

        rows = []

        for factor, rating in ratings.items():
            rows.append({
                "Factor": factor.replace("_", " ").title(),
                "Rating": (
                    rating if rating is not None else "Unassessed"
                ),
                "Reviewer notes": notes.get(factor, ""),
            })

        if rows:
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )

        rationale = _get(result, "rationale", [])

        if rationale:
            st.markdown("**Assessment rationale**")

            if isinstance(rationale, (list, tuple)):
                for item in rationale:
                    st.write(f"- {item}")
            else:
                st.write(rationale)

    else:
        st.info(
            "No saved criticality assessment exists for this vendor. "
            "Use the Vendor Inventory page to assess it."
        )

    # --------------------------------------------------------
    # AI-use classification
    # --------------------------------------------------------

    st.divider()
    st.subheader("2. AI-use classification")

    if investigation:
        st.markdown(f"**Status:** {investigation.get('status', 'Unknown')}")
        st.markdown(
            f"**Confidence:** {investigation.get('confidence', 'Unknown')}"
        )

        st.write(investigation.get("summary", ""))

        st.markdown("**Rationale**")

        for item in investigation.get("rationale", []):
            st.write(f"- {item}")

        st.markdown("**Recommended follow-up**")

        for item in investigation.get("follow_up", []):
            st.write(f"- {item}")

        if investigation.get("review_required"):
            st.warning("Additional human review is required.")
        if investigation.get("scope_notes"):
            st.markdown("**Completed search scope and limitations**")
            st.write(investigation["scope_notes"])

    else:
        st.info(
            "No AI-use classification has been saved. Run the vendor "
            "investigation and classification workflow first."
        )

    # --------------------------------------------------------
    # Evidence register
    # --------------------------------------------------------

    st.divider()
    st.subheader("3. Evidence register")

    if vendor_evidence:
        evidence_rows = []

        for item in vendor_evidence:
            grade = _get(item, "grade")

            evidence_rows.append({
                "Evidence ID": _get(item, "evidence_id", ""),
                "Source": _get(item, "source_url", ""),
                "Source title": _get(item, "source_title", ""),
                "Data origin": _get(
                    item,
                    "data_origin",
                    "Provenance not recorded (legacy)",
                ),
                "Discovery method": _get(item, "discovery_method", ""),
                "Investigation run ID": _get(item, "run_id", ""),
                "Retrieved at (UTC)": _get(item, "retrieved_at", ""),
                "Excerpt": _get(item, "excerpt", ""),
                "Review status": _get(
                    item, "review_status", "Needs review"
                ),
                "Evidence score": _get(grade, "score"),
            })

        evidence_df = pd.DataFrame(evidence_rows)

        st.dataframe(
            evidence_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Export this vendor's evidence",
            data=evidence_df.to_csv(index=False).encode("utf-8"),
            file_name=f"blindspot_evidence_{vendor_id}.csv",
            mime="text/csv",
            key=f"export_profile_evidence_{vendor_id}",
        )

    else:
        st.info("No evidence records are linked to this vendor yet.")

    # --------------------------------------------------------
    # Risk findings
    # --------------------------------------------------------

    st.divider()
    st.subheader("4. Security risk findings")

    if vendor_findings:
        findings_df = _as_dataframe(vendor_findings)

        st.dataframe(
            findings_df,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.info(
            "No risk findings have been recorded for this vendor. "
            "This does not establish that the vendor has no security risks."
        )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    st.divider()
    st.subheader("5. Related entities")

    if vendor_relationships:
        st.dataframe(
            _as_dataframe(vendor_relationships),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.info(
            "No relationships have been recorded for this vendor."
        )

    # --------------------------------------------------------
    # Evidence and coverage notes
    # --------------------------------------------------------

    st.divider()
    st.subheader("6. Investigation coverage")

    collection_log = st.session_state.get("collection_log", [])

    vendor_log = [
        item
        for item in collection_log
        if str(_get(item, "vendor_id", "")) == vendor_id
    ]

    successful = sum(
        1
        for item in vendor_log
        if str(_get(item, "status", "")).lower() == "success"
    )

    failed = sum(
        1
        for item in vendor_log
        if str(_get(item, "status", "")).lower() == "failed"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Collection attempts", len(vendor_log))

    with col2:
        st.metric("Successful fetches", successful)

    with col3:
        st.metric("Failed fetches", failed)

    if vendor_log:
        with st.expander("View collection log"):
            st.dataframe(
                _as_dataframe(vendor_log),
                use_container_width=True,
                hide_index=True,
            )

    st.caption(
        "This profile combines records currently available in the "
        "application session. Missing assessments and evidence gaps "
        "must not be interpreted as proof of safety or absence of AI use."
    )
