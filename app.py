<<<<<<< HEAD
"""Project BlindSpot — Unmasking Hidden Vendor AI."""



import os
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from textwrap import dedent

import tempfile



import pandas as pd

import streamlit as st

from src.ui.collection_page import show_collection_page

from src.io.workbook import load_inventory

from src.ui.report_export import show_report_export

from src.assessment.criticality import (

    WEIGHTS,

    calculate_criticality,

    rate_data_sensitivity,
    initialize_inventory_criticality,
    rate_operational_dependency,
    rate_numeric_factor,
)
from src.assessment.risk import (
    RISK_THEMES,
    calculate_ai_cyber_risk_score,
    create_risk_finding,
)
from src.assessment.scores import calculate_evidence_score

from src.ui.ai_investigation import show_ai_investigation

from src.ui.review_centre import show_review_centre

from src.ui.intelligence_mesh import show_intelligence_mesh as show_intelligence_mesh_page

from src.ui.investigation_summary import show_investigation_summary

from src.ui.vendor_profile import show_vendor_profile
from src.ui.live_investigation_lab import show_live_investigation_lab

from src.io.validation import (
    duplicate_vendor_ids,
    validate_inventory,
    validation_issues_as_records,
)








# ============================================================

# PAGE CONFIGURATION

# ============================================================



st.set_page_config(

    page_title="Project BlindSpot",

    page_icon="🔎",

    layout="wide",

    initial_sidebar_state="expanded",

)





# ============================================================

# SESSION STATE

# ============================================================



DEFAULTS = {

    "inventory_df": None,

    "inventory_messages": [],

    "inventory_metadata": {},

    "inventory_filename": None,
    "inventory_fingerprint": None,

    "evidence_records": [],

    "review_log": [],

    "risk_findings": [],

    "collection_log": [],

    "criticality_ratings": {},
    "investigation_assessments": {},

    "discovered_sources": {},

    "investigation_vendor_id": None,

    "investigation_vendor_name": None,
    "investigation_assessments": {},
    "relationship_records": [],
    "last_collection_summary": None,
    "live_investigation_results": {},
    "assessment_workbook_bytes": None,
}


APP_DIR = os.path.dirname(os.path.abspath(__file__))
MERIDIAN_CASE_STUDY_PATH = os.path.join(
    APP_DIR,
    "req",
    "Meridian_Vendor_Input.xlsx",
)



for key, value in DEFAULTS.items():

    if key not in st.session_state:

        st.session_state[key] = value





# ============================================================

# STYLING

# ============================================================



st.markdown(

    """

    <style>
    .stApp {
        background-color: #F1F5F9 !important;
        color: var(--text-color, #172B4D);
    }


    [data-testid="stHeader"] {
        background-color: #F1F5F9;
    }


    [data-testid="stSidebar"] {
        background-color: #FFFFFF !important;
        border-right: 1px solid #E2E8F0;
    }


    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"],
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: var(--text-color, #172B4D);
    }



    .block-container {

        padding-top: 1.8rem;

        padding-bottom: 2rem;

    }



    h1, h2, h3 {
        color: var(--text-color, #172B4D);
    }



    .bs-subtitle {

        color: #64748B;

        font-size: 0.95rem;

        margin-top: -0.5rem;

        margin-bottom: 1.4rem;

    }



    .bs-card {
        padding: 1rem 1.1rem;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        background: #FFFFFF;
        min-height: 105px;
    }



    .bs-card-label {

        font-size: 0.82rem;

        color: #52647A;

        margin-bottom: 0.45rem;

    }



    .bs-card-value {

        font-size: 1.65rem;

        font-weight: 650;

        color: var(--text-color, #172B4D);
    }

    div[data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        padding: 12px 14px;
        border-radius: 10px;
    }

    [data-testid="stWidgetLabel"],
    [data-testid="stMarkdownContainer"],
    [data-testid="stCaptionContainer"] {
        color: var(--text-color, #172B4D);
    }

    [data-baseweb="input"] input,
    [data-baseweb="textarea"] textarea,
    [data-baseweb="select"] > div,
    [data-baseweb="tag"] {
        color: var(--text-color, #172B4D);
        background-color: #FFFFFF;
    }

    [role="listbox"],
    [role="option"] {
        color: var(--text-color, #172B4D);
        background-color: #FFFFFF;
    }

    div.stButton > button[kind="primary"] {
        background-color: #2457C5;
        border-color: #2457C5;
        color: #FFFFFF;
    }

    div.stButton > button:not([kind="primary"]),
    [data-testid="stDownloadButton"] button {
        color: var(--text-color, #172B4D);
        border-color: #CBD5E1;
    }



    hr {

        border-color: #E2E8F0;

    }

    </style>

    """,

    unsafe_allow_html=True,

)





# ============================================================

# SHARED HELPERS

# ============================================================



def page_header(title, description):

    st.title(title)

    st.markdown(

        f'<div class="bs-subtitle">{description}</div>',

        unsafe_allow_html=True,

    )





def metric_card(label, value):
    st.markdown(
        dedent(
            f"""
            <div class="bs-card">
                <div class="bs-card-label">{label}</div>
                <div class="bs-card-value">{value}</div>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )





def get_field(item, field, default=None):

    if isinstance(item, dict):

        return item.get(field, default)

    return getattr(item, field, default)





def inventory_is_loaded():

    return (

        isinstance(st.session_state.inventory_df, pd.DataFrame)

        and not st.session_state.inventory_df.empty

    )


def reset_assessment_state_for_inventory(inventory):
    """Clear downstream records when a different inventory is loaded."""
    for key, value in {
        "evidence_records": [],
        "review_log": [],
        "risk_findings": [],
        "collection_log": [],
        "criticality_ratings": {},
        "investigation_assessments": {},
        "discovered_sources": {},
        "investigation_vendor_id": None,
        "investigation_vendor_name": None,
        "relationship_records": [],
        "last_collection_summary": None,
        "live_investigation_results": {},
        "assessment_workbook_bytes": None,
    }.items():
        st.session_state[key] = value

    if not duplicate_vendor_ids(inventory):
        st.session_state["criticality_ratings"] = (
            initialize_inventory_criticality(inventory)
        )

    for key in list(st.session_state.keys()):
        if key.startswith(("scope_complete_", "scope_notes_")):
            del st.session_state[key]

    for key in (
        "criticality_vendor",
        "investigation_vendor",
        "summary_vendor",
        "profile_vendor_selector",
        "risk_assessment_vendor",
        "manual_investigation_urls",
    ):
        st.session_state.pop(key, None)


def load_inventory_into_session(
    inventory,
    messages,
    metadata,
    *,
    filename,
    fingerprint,
):
    """Store a loaded inventory and reset dependent assessment state."""
    st.session_state.inventory_df = inventory
    st.session_state.inventory_messages = messages
    st.session_state.inventory_metadata = metadata
    st.session_state.inventory_filename = filename
    st.session_state.inventory_fingerprint = fingerprint
    reset_assessment_state_for_inventory(inventory)





# ============================================================

# OVERVIEW

# ============================================================



def show_overview():

    page_header(

        "Project BlindSpot",

        "Unmasking Hidden Vendor AI | Third-party AI due diligence",

    )



    st.write(

        "Investigate public evidence of vendor AI usage, understand "

        "potential security implications, and maintain a traceable "

        "assessment for human review."

    )



    df = st.session_state.inventory_df

    vendor_count = len(df) if isinstance(df, pd.DataFrame) else 0



    col1, col2, col3, col4 = st.columns(4)



    with col1:

        metric_card("Vendors loaded", vendor_count)

    with col2:

        metric_card(

            "Evidence records",

            len(st.session_state.evidence_records),

        )

    with col3:

        metric_card(

            "Review decisions",

            len(st.session_state.review_log),

        )

    with col4:

        metric_card(

            "Risk findings",

            len(st.session_state.risk_findings),

        )



    st.subheader("Assessment workflow")



    workflow = [
        ("01", "Vendor inventory", "Load and validate the supplied workbook."),
        (
            "02",
            "Criticality",
            "Calculate supported inventory ratings; review unknown factors.",
        ),
        (
            "03",
            "Live Vendor Investigation Lab",
            "Run bounded public-source research with visible progress.",
        ),
        ("04", "Evidence review", "Validate evidence and record decisions."),
        ("05", "Risk assessment", "Score only reviewer-rated, evidence-backed findings."),
        ("06", "Vendor profile and mesh", "Review vendor-specific evidence and relationships."),
        ("07", "Reports", "Export separate criticality, evidence, and risk scores."),
    ]



    for number, title, description in workflow:

        with st.container(border=True):

            left, right = st.columns([1, 12])

            with left:

                st.markdown(f"### {number}")

            with right:

                st.markdown(f"**{title}**")

                st.caption(description)



    st.subheader("Assessment principles")



    st.markdown(

        """

        - AI-related keywords are signals, not proof.

        - Missing public evidence does not prove that a vendor does not use AI.

        - Vendor criticality, AI-use classification, and security risk

          are assessed separately.

        - Human reviewers retain responsibility for final decisions.

        """

    )





# ============================================================

# VENDOR INVENTORY

# ============================================================



def show_inventory():

    page_header(

        "Vendor Inventory",

        "Load and inspect the Meridian case-study workbook without modifying it.",

    )

    st.info(
        "For the demo, use the supplied Meridian workbook from the req folder. "
        "Upload remains available for ad-hoc validation."
    )

    if os.path.exists(MERIDIAN_CASE_STUDY_PATH):
        if st.button(
            "Load Meridian case study inventory",
            type="primary",
            key="load_meridian_case_study",
        ):
            try:
                with open(MERIDIAN_CASE_STUDY_PATH, "rb") as workbook:
                    workbook_bytes = workbook.read()
                workbook_fingerprint = sha256(workbook_bytes).hexdigest()
                if workbook_fingerprint != st.session_state.inventory_fingerprint:
                    inventory, messages, metadata = load_inventory(
                        MERIDIAN_CASE_STUDY_PATH,
                        sheet_name="Vendor Inventory",
                    )
                    metadata["case_study"] = "Meridian"
                    load_inventory_into_session(
                        inventory,
                        messages,
                        metadata,
                        filename=os.path.basename(MERIDIAN_CASE_STUDY_PATH),
                        fingerprint=workbook_fingerprint,
                    )
                st.rerun()
            except Exception as exc:
                st.error(f"Could not load Meridian workbook: {exc}")
    else:
        st.warning(
            "The Meridian case-study workbook was not found at "
            f"{MERIDIAN_CASE_STUDY_PATH}."
        )



    uploaded_file = st.file_uploader(

        "Upload vendor inventory workbook",

        type=["xlsx", "xlsm"],

        key="inventory_uploader",

    )



    if uploaded_file is not None:
        workbook_bytes = uploaded_file.getvalue()
        workbook_fingerprint = sha256(workbook_bytes).hexdigest()

        if workbook_fingerprint != st.session_state.inventory_fingerprint:
            temp_path = None
            loaded_new_workbook = False

            try:

                suffix = os.path.splitext(uploaded_file.name)[1]



                with tempfile.NamedTemporaryFile(

                    delete=False,

                    suffix=suffix,

                ) as temp_file:

                    temp_file.write(workbook_bytes)

                    temp_path = temp_file.name



                inventory, messages, metadata = load_inventory(

                    temp_path,

                    sheet_name="Vendor Inventory",

                )



                load_inventory_into_session(
                    inventory,
                    messages,
                    metadata,
                    filename=uploaded_file.name,
                    fingerprint=workbook_fingerprint,
                )

                loaded_new_workbook = True

            except Exception as exc:
                st.error(f"Could not load workbook: {exc}")



            finally:

                if temp_path and os.path.exists(temp_path):

                    os.remove(temp_path)

            if loaded_new_workbook:
                st.rerun()



    df = st.session_state.inventory_df



    if not isinstance(df, pd.DataFrame):

        st.info("Upload the vendor inventory to begin.")

        return





    if df.empty:

        st.warning("The workbook contains no vendor records.")

        return



    # Validate the loaded inventory without modifying the source data.

    st.subheader("Inventory validation")



    try:

        validation_report = validate_inventory(df)



        col1, col2, col3 = st.columns(3)



        with col1:

            st.metric("Rows checked", validation_report.total_rows)



        with col2:

            st.metric("Errors", validation_report.error_count)



        with col3:

            st.metric("Warnings", validation_report.warning_count)



        if validation_report.issues:

            issues_df = pd.DataFrame(

                validation_issues_as_records(validation_report)

            )



            st.dataframe(

                issues_df,

                use_container_width=True,

                hide_index=True,

            )



            st.download_button(

                "Export validation report",

                data=issues_df.to_csv(index=False).encode("utf-8"),

                file_name="blindspot_validation_report.csv",

                mime="text/csv",

                key="inventory_validation_export",

            )

        else:

            st.success("No inventory validation issues were found.")



        if not validation_report.is_valid:

            st.warning(

                "Resolve the inventory errors before relying on downstream "

                "assessments. The uploaded data has not been modified."

            )

    except Exception as exc:
        st.error(f"Inventory validation could not be completed: {exc}")





    for message in st.session_state.inventory_messages:

        if isinstance(message, dict):

            text = str(message.get("message", message))

            level = str(message.get("level", "info")).lower()

        else:

            text = str(message)

            level = "info"



        if level in {"error", "critical"}:

            st.error(text)

        elif level in {"warning", "warn"}:

            st.warning(text)

        else:

            st.info(text)



    col1, col2, col3 = st.columns(3)



    with col1:

        st.metric("Vendor records", len(df))

    with col2:

        st.metric("Columns detected", len(df.columns))

    with col3:

        st.metric(

            "Vendor IDs present",

            int(df["Vendor ID"].notna().sum())

            if "Vendor ID" in df.columns else 0,

        )



    st.subheader("Source inventory")

    st.dataframe(df, use_container_width=True, hide_index=True)



    st.download_button(

        "Download inventory copy",

        data=df.to_csv(index=False).encode("utf-8"),

        file_name="blindspot_inventory.csv",

        mime="text/csv",

    )



    if "Vendor ID" not in df.columns or "Vendor Name" not in df.columns:
        st.error("Vendor ID and Vendor Name columns are required.")
        return

    duplicate_ids = duplicate_vendor_ids(df)
    if duplicate_ids:
        st.warning(
            "Resolve duplicate Vendor IDs before assessing criticality. "
            "Downstream assessments are keyed by Vendor ID."
        )
        return



    st.divider()

    st.subheader("Vendor criticality assessment")



    vendor_options = {}



    for index, row in df.iterrows():
        if pd.isna(row["Vendor ID"]) or not str(row["Vendor ID"]).strip():
            continue
        if pd.isna(row["Vendor Name"]) or not str(row["Vendor Name"]).strip():
            continue

        label = (
            f"{row['Vendor Name']} "
            f"({row['Vendor ID']}) — row {index + 1}"
        )
        vendor_options[label] = index

    if not vendor_options:
        st.warning("No vendor with a usable Vendor ID is available to assess.")
        return



    selected_label = st.selectbox(

        "Select vendor",

        list(vendor_options.keys()),

        key="criticality_vendor",

    )



    selected_index = vendor_options[selected_label]

    vendor = df.loc[selected_index]



    st.write(f"**Vendor:** {vendor['Vendor Name']}")

    st.write(f"**Vendor ID:** {vendor['Vendor ID']}")



    factors = [

        ("data_sensitivity", "Data sensitivity", rate_data_sensitivity),

        (

            "operational_dependency",

            "Operational dependency",

            rate_operational_dependency,

        ),

        ("regulatory_exposure", "Regulatory exposure", None),

        ("payment_involvement", "Payment involvement", None),

        ("annual_data_volume", "Annual data volume", None),

    ]



    factor_ratings = {}

    factor_notes = {}



    rating_options = [

        "Unassessed",

        "1 - Very low",

        "2 - Low",

        "3 - Moderate",

        "4 - High",

        "5 - Very high",

    ]



    for factor_key, label, rating_function in factors:

        with st.container(border=True):

            st.markdown(f"**{label}**")



            column = st.selectbox(

                f"Workbook column for {label}",

                ["Not mapped"] + list(df.columns),

                key=f"column_{factor_key}",

            )



            raw_value = (

                None if column == "Not mapped"

                else vendor.get(column)

            )



            if rating_function:
                suggested_rating, suggestion_note = rating_function(raw_value)
            else:
                suggested_rating, suggestion_note = rate_numeric_factor(raw_value)

            st.caption(f"Source value: {raw_value!s}")
            st.caption(suggestion_note)



            if suggested_rating is not None:

                suggestion = int(suggested_rating)

                st.caption(

                    f"Suggested rating: {suggestion}/5. "

                    "Verify it before using it."

                )



            rating = st.selectbox(

                f"Reviewed rating — {label}",

                rating_options,

                key=f"rating_{factor_key}_{selected_index}",

            )



            if rating == "Unassessed":

                factor_ratings[factor_key] = None

                factor_notes[factor_key] = "Not assessed"

            else:

                factor_ratings[factor_key] = int(rating[0])

                factor_notes[factor_key] = (

                    f"Reviewer-selected rating {rating}; "

                    f"source value: {raw_value!s}"

                )



    st.caption("Draft criticality weights")



    st.dataframe(

        pd.DataFrame([

            {

                "Factor": factor,

                "Weight (%)": round(weight * 100, 1),

            }

            for factor, weight in WEIGHTS.items()

        ]),

        use_container_width=True,

        hide_index=True,

    )



    st.caption(

        "These are proposed weights. Validate them against the case-study "

        "guidance before relying on the resulting scores."

    )



    if st.button(

        "Calculate criticality",

        type="primary",

        key=f"calculate_{selected_index}",

    ):

        try:

            result = calculate_criticality(factor_ratings)



            st.session_state.criticality_ratings[
                str(vendor["Vendor ID"])
            ] = {
                "vendor_name": str(vendor["Vendor Name"]),
                "ratings": factor_ratings.copy(),
                "notes": factor_notes.copy(),
                "result": result,
                "auto_calculated": False,
            }

            st.session_state.assessment_workbook_bytes = None

        except (ValueError, TypeError) as exc:

            st.error(f"Could not calculate criticality: {exc}")



    saved = st.session_state.criticality_ratings.get(

        str(vendor["Vendor ID"])

    )



    if saved:

        result = saved["result"]

        score = get_field(result, "score")

        status = get_field(result, "status", "Unassessed")

        coverage = get_field(result, "coverage_percent")



        st.subheader("Criticality result")
        st.caption(
            "Initial scores are calculated on inventory upload from explicit "
            "rating fields and recognized categories. Unknown values remain "
            "unassessed; numeric annual-volume bands are not inferred. "
            "Reviewer-selected ratings below replace the automatic assessment."
            if saved.get("auto_calculated")
            else "Reviewer-entered criticality assessment using the displayed "
            "factor ratings and proposed weights."
        )



        col1, col2, col3 = st.columns(3)



        with col1:

            st.metric(

                "Score",

                f"{score:.1f}/100" if score is not None else "Unassessed",

            )



        with col2:

            st.metric("Status", str(status))



        with col3:

            st.metric(

                "Coverage",

                f"{coverage:.1f}%"
                if isinstance(coverage, (int, float))
                else str(coverage or "Not available"),

            )



        rationale = get_field(result, "rationale", [])



        if rationale:

            st.markdown("**Rationale**")

            if isinstance(rationale, (list, tuple)):

                for item in rationale:

                    st.write(f"- {item}")

            else:

                st.write(rationale)





# ============================================================

# EVIDENCE REGISTER

# ============================================================



def show_evidence_register():

    page_header(

        "Evidence Register",

        "Search and inspect collected evidence records.",

    )



    records = st.session_state.evidence_records



    if not records:

        st.info("No evidence records have been collected yet.")

        return



    rows = []



    for item in records:

        rows.append({

            "Evidence ID": get_field(item, "evidence_id", ""),

            "Vendor ID": get_field(item, "vendor_id", ""),

            "Vendor Name": get_field(item, "vendor_name", ""),
            "Source URL": get_field(item, "source_url", ""),
            "Source Title": get_field(item, "source_title", ""),
            "Retrieved At (UTC)": get_field(item, "retrieved_at", ""),
            "Data Origin": get_field(
                item,
                "data_origin",
                "Provenance not recorded (legacy)",
            ),
            "Discovery Method": get_field(item, "discovery_method", ""),
            "Investigation Run ID": get_field(item, "run_id", ""),
            "Excerpt": get_field(item, "excerpt", ""),

            "Review Status": get_field(

                item, "review_status", "Needs review"

            ),

        })



    evidence_df = pd.DataFrame(rows)



    search = st.text_input("Search evidence")



    if search:

        mask = evidence_df.astype(str).apply(

            lambda col: col.str.contains(

                search,

                case=False,

                na=False,

                regex=False,

            )

        ).any(axis=1)

        evidence_df = evidence_df[mask]



    status = st.selectbox(

        "Filter review status",

        ["All", "Needs review", "Accepted", "Rejected"],

    )



    if status != "All":

        evidence_df = evidence_df[

            evidence_df["Review Status"].astype(str).str.lower()

            == status.lower()

        ]



    st.dataframe(

        evidence_df,

        use_container_width=True,

        hide_index=True,

    )



    st.download_button(

        "Export evidence register",

        data=evidence_df.to_csv(index=False).encode("utf-8"),

        file_name="blindspot_evidence_register.csv",

        mime="text/csv",

    )





# ============================================================

# RISK ASSESSMENT

# ============================================================



def show_risk_assessment():
    page_header(
        "Risk Assessment",
        "Record vendor-specific security concerns, supporting evidence, severity, and recommended actions.",
    )
    inventory = st.session_state.get("inventory_df")
    findings = st.session_state.setdefault("risk_findings", [])
    evidence_records = st.session_state.setdefault("evidence_records", [])

    if not isinstance(inventory, pd.DataFrame) or inventory.empty:
        st.warning("Upload a vendor inventory before assessing risks.")
        return
    if not {"Vendor ID", "Vendor Name"}.issubset(inventory.columns):
        st.error("The inventory must contain Vendor ID and Vendor Name.")
        return
    if duplicate_vendor_ids(inventory):
        st.error(
            "Resolve duplicate Vendor IDs before recording vendor-specific "
            "risk findings."
        )
        return

    vendors = {}
    for _, row in inventory.iterrows():
        vendor_id = str(row["Vendor ID"]).strip()
        vendor_name = str(row["Vendor Name"]).strip()
        if (
            vendor_id
            and vendor_id.lower() != "nan"
            and vendor_name
            and vendor_name.lower() != "nan"
        ):
            vendors[f"{vendor_name} ({vendor_id})"] = {
                "vendor_id": vendor_id, "vendor_name": vendor_name
            }
    if not vendors:
        st.warning("No valid vendors were found in the inventory.")
        return

    selected_label = st.selectbox(
        "Vendor to assess", list(vendors.keys()), key="risk_assessment_vendor"
    )
    selected_vendor = vendors[selected_label]
    vendor_id = selected_vendor["vendor_id"]
    vendor_name = selected_vendor["vendor_name"]

    def field(item, name, default=""):
        return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)

    vendor_findings = [item for item in findings if str(field(item, "vendor_id")) == vendor_id]
    vendor_evidence = [item for item in evidence_records if str(field(item, "vendor_id")) == vendor_id]
    evidence_score = calculate_evidence_score(vendor_evidence)
    cyber_risk_score = calculate_ai_cyber_risk_score(
        vendor_findings,
        evidence_records=vendor_evidence,
    )

    score_col1, score_col2 = st.columns(2)
    score_col1.metric(
        "Evidence quality score",
        f"{evidence_score['score']:.1f}/100"
        if evidence_score["score"] is not None
        else "Unassessed",
        help="Accepted, relevant source quality only; not a probability.",
    )
    score_col2.metric(
        "AI cybersecurity risk score",
        f"{cyber_risk_score['score']:.1f}/100"
        if cyber_risk_score["score"] is not None
        else "Unassessed",
        help="Reviewer-rated, evidence-supported prioritization index.",
    )
    st.caption(
        f"Evidence score: {evidence_score['status']}. Cyber risk score: "
        f"{cyber_risk_score['status']}. No score is inferred from AI-use "
        "classification alone."
    )
    with st.expander("How these two scores are calculated"):
        st.write(evidence_score["rationale"])
        st.write(cyber_risk_score["rationale"])
        st.write(
            f"Cyber risk coverage: {cyber_risk_score['scored_findings']} "
            "evidence-supported active finding(s); "
            f"{cyber_risk_score['unassessed_findings']} unassessed and "
            f"{cyber_risk_score['unsupported_findings']} without accepted "
            "evidence for this vendor."
        )

    st.subheader(f"Risk register — {vendor_name}")
    if vendor_findings:
        rows = []
        for item in vendor_findings:
            record = item if isinstance(item, dict) else vars(item)
            rows.append({
                "Finding ID": record.get("finding_id", ""),
                "Risk theme": record.get(
                    "risk_theme", record.get("title", "")
                ),
                "Severity": record.get("severity", "Unassessed"),
                "Status": record.get(
                    "finding_status", record.get("status", "Needs review")
                ),
                "Description": record.get("description", ""),
                "Rationale": record.get("rationale", ""),
                "Likelihood": record.get("likelihood", "Unassessed"),
                "Evidence IDs": ", ".join(map(str, record.get("evidence_ids", []))),
                "Recommendation": record.get(
                    "recommendation",
                    record.get("recommended_action", ""),
                ),
                "Reviewer": record.get("reviewer", ""),
                "Reviewed At (UTC)": record.get("reviewed_at", ""),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Findings", len(rows))
        c2.metric("High / Critical", sum(str(r["Severity"]).lower() in {"high", "critical"} for r in rows))
        c3.metric(
            "Open findings",
            sum(
                str(r["Status"]).lower()
                not in {"resolved", "accepted risk"}
                for r in rows
            ),
        )
    else:
        st.info("No risk findings have been recorded for this vendor.")

    st.divider()
    st.subheader("Record a risk finding")
    theme_options = {
        details["label"]: theme
        for theme, details in RISK_THEMES.items()
    }
    evidence_options = {}
    for item in vendor_evidence:
        evidence_id = str(field(item, "evidence_id", ""))
        source_url = str(field(item, "source_url", ""))
        excerpt = str(field(item, "excerpt", ""))
        if evidence_id:
            evidence_options[f"{evidence_id} — {source_url or excerpt[:70]}"] = evidence_id

    with st.form("create_vendor_risk_finding"):
        theme_label = st.selectbox(
            "Risk theme", list(theme_options.keys())
        )
        theme = theme_options[theme_label]
        severity = st.selectbox("Severity", ["Low", "Moderate", "High", "Critical", "Unassessed"])
        likelihood = st.selectbox(
            "Likelihood", ["Unassessed", "Unlikely", "Possible", "Likely"]
        )
        description = st.text_area("Risk description", placeholder="Explain the concern and what the evidence does or does not establish.")
        rationale = st.text_area(
            "Assessment rationale",
            placeholder="Explain what is known, what remains unverified, and why this finding is recorded.",
        )
        selected_evidence = st.multiselect("Supporting evidence", list(evidence_options.keys()))
        recommendation = st.text_area("Recommended action", placeholder="Describe the next verification or mitigation step.")
        status = st.selectbox(
            "Review status",
            ["Needs review", "Under review", "Reviewed", "Resolved", "Accepted risk"],
        )
        reviewer = st.text_input("Reviewer")
        submitted = st.form_submit_button("Save risk finding", type="primary")

    if submitted:
        if not description.strip() or not rationale.strip() or not recommendation.strip():
            st.error("Enter the risk description, rationale, and recommended action.")
        elif not reviewer.strip():
            st.error("Enter the reviewer responsible for this finding.")
        else:
            try:
                finding = create_risk_finding(
                    vendor_id=vendor_id,
                    vendor_name=vendor_name,
                    theme=theme,
                    rationale=rationale,
                    severity=severity,
                    likelihood=likelihood,
                    evidence_ids=[
                        evidence_options[label]
                        for label in selected_evidence
                    ],
                    finding_id=f"RF-{vendor_id}-{len(findings) + 1:03d}",
                    description=description,
                    recommended_action=recommendation,
                    status=status,
                    reviewer=reviewer,
                    reviewed_at=datetime.now(timezone.utc).isoformat(),
                )
                record = asdict(finding)
                record["risk_theme"] = finding.title
                record["finding_status"] = finding.status
                record["recommendation"] = finding.recommended_action
                record["created_at"] = finding.reviewed_at
                findings.append(record)
                st.session_state["risk_findings"] = findings
                st.session_state["assessment_workbook_bytes"] = None
                st.success(
                    "Risk finding saved as a reviewer assessment. "
                    "AI-related evidence alone does not confirm a security risk."
                )
                st.rerun()
            except ValueError as exc:
                st.error(f"Could not save the risk finding: {exc}")

    st.caption("Reviewer-entered findings are assessments, not automatically verified conclusions. An evidence gap alone does not prove a vendor is insecure.")


# ============================================================
# REPORTS & EXPORT
# ============================================================





# ============================================================

# SIDEBAR

# ============================================================



with st.sidebar:

    st.markdown("## 🔎 BlindSpot")

    st.caption("Vendor AI due diligence")

    st.divider()



    selected_page = st.radio(

        "Navigation",

        [

            "Overview",

            "Vendor Inventory",

            "AI Investigation",
            "Live Vendor Investigation Lab",
            "Evidence Register",

            "Risk Assessment",

            "Intelligence Mesh",

            "Review Centre",

            "Reports & Export",

            "Public Evidence Collection",

            "Vendor Profile",

            "Investigation Summary",

        ],

        key="main_navigation",

        label_visibility="collapsed",

    )



    st.divider()



    if inventory_is_loaded():

        st.success("Inventory loaded")

        st.caption(

            f"{len(st.session_state.inventory_df)} vendor records"

        )

    else:

        st.info("Upload the vendor inventory to begin.")



    st.divider()

    st.caption("Project BlindSpot | Internal case-study prototype")





# ============================================================

# PAGE ROUTING
# ============================================================

if selected_page == "Overview":
    show_overview()
elif selected_page == "Vendor Inventory":
    show_inventory()
elif selected_page == "AI Investigation":
    show_ai_investigation()
elif selected_page == "Live Vendor Investigation Lab":
    show_live_investigation_lab()
elif selected_page == "Evidence Register":
    show_evidence_register()
elif selected_page == "Risk Assessment":
    show_risk_assessment()
elif selected_page == "Intelligence Mesh":
    show_intelligence_mesh_page()
elif selected_page == "Review Centre":
    show_review_centre()
elif selected_page == "Reports & Export":
    show_report_export()
elif selected_page == "Public Evidence Collection":
    show_collection_page()
elif selected_page == "Vendor Profile":
    show_vendor_profile()
elif selected_page == "Investigation Summary":
    show_investigation_summary()
=======
"""Project BlindSpot — Unmasking Hidden Vendor AI."""



import os
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from textwrap import dedent

import tempfile



import pandas as pd

import streamlit as st

from src.ui.collection_page import show_collection_page

from src.io.workbook import load_inventory

from src.ui.report_export import show_report_export

from src.assessment.criticality import (

    WEIGHTS,

    calculate_criticality,

    rate_data_sensitivity,
    initialize_inventory_criticality,
    rate_operational_dependency,
    rate_numeric_factor,
)
from src.assessment.risk import (
    RISK_THEMES,
    calculate_ai_cyber_risk_score,
    create_risk_finding,
)
from src.assessment.scores import calculate_evidence_score

from src.ui.ai_investigation import show_ai_investigation

from src.ui.review_centre import show_review_centre

from src.ui.intelligence_mesh import show_intelligence_mesh as show_intelligence_mesh_page

from src.ui.investigation_summary import show_investigation_summary

from src.ui.vendor_profile import show_vendor_profile
from src.ui.live_investigation_lab import show_live_investigation_lab

from src.io.validation import (
    duplicate_vendor_ids,
    validate_inventory,
    validation_issues_as_records,
)








# ============================================================

# PAGE CONFIGURATION

# ============================================================



st.set_page_config(

    page_title="Project BlindSpot",

    page_icon="🔎",

    layout="wide",

    initial_sidebar_state="expanded",

)





# ============================================================

# SESSION STATE

# ============================================================



DEFAULTS = {

    "inventory_df": None,

    "inventory_messages": [],

    "inventory_metadata": {},

    "inventory_filename": None,
    "inventory_fingerprint": None,

    "evidence_records": [],

    "review_log": [],

    "risk_findings": [],

    "collection_log": [],

    "criticality_ratings": {},
    "investigation_assessments": {},

    "discovered_sources": {},

    "investigation_vendor_id": None,

    "investigation_vendor_name": None,
    "investigation_assessments": {},
    "relationship_records": [],
    "last_collection_summary": None,
    "live_investigation_results": {},
    "assessment_workbook_bytes": None,
}



for key, value in DEFAULTS.items():

    if key not in st.session_state:

        st.session_state[key] = value





# ============================================================

# STYLING

# ============================================================



st.markdown(

    """

    <style>
    .stApp {
        background-color: #F1F5F9 !important;
        color: var(--text-color, #172B4D);
    }


    [data-testid="stHeader"] {
        background-color: #F1F5F9;
    }


    [data-testid="stSidebar"] {
        background-color: #FFFFFF !important;
        border-right: 1px solid #E2E8F0;
    }


    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"],
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: var(--text-color, #172B4D);
    }



    .block-container {

        padding-top: 1.8rem;

        padding-bottom: 2rem;

    }



    h1, h2, h3 {
        color: var(--text-color, #172B4D);
    }



    .bs-subtitle {

        color: #64748B;

        font-size: 0.95rem;

        margin-top: -0.5rem;

        margin-bottom: 1.4rem;

    }



    .bs-card {
        padding: 1rem 1.1rem;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        background: #FFFFFF;
        min-height: 105px;
    }



    .bs-card-label {

        font-size: 0.82rem;

        color: #52647A;

        margin-bottom: 0.45rem;

    }



    .bs-card-value {

        font-size: 1.65rem;

        font-weight: 650;

        color: var(--text-color, #172B4D);
    }

    div[data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        padding: 12px 14px;
        border-radius: 10px;
    }

    [data-testid="stWidgetLabel"],
    [data-testid="stMarkdownContainer"],
    [data-testid="stCaptionContainer"] {
        color: var(--text-color, #172B4D);
    }

    [data-baseweb="input"] input,
    [data-baseweb="textarea"] textarea,
    [data-baseweb="select"] > div,
    [data-baseweb="tag"] {
        color: var(--text-color, #172B4D);
        background-color: #FFFFFF;
    }

    [role="listbox"],
    [role="option"] {
        color: var(--text-color, #172B4D);
        background-color: #FFFFFF;
    }

    div.stButton > button[kind="primary"] {
        background-color: #2457C5;
        border-color: #2457C5;
        color: #FFFFFF;
    }

    div.stButton > button:not([kind="primary"]),
    [data-testid="stDownloadButton"] button {
        color: var(--text-color, #172B4D);
        border-color: #CBD5E1;
    }



    hr {

        border-color: #E2E8F0;

    }

    </style>

    """,

    unsafe_allow_html=True,

)





# ============================================================

# SHARED HELPERS

# ============================================================



def page_header(title, description):

    st.title(title)

    st.markdown(

        f'<div class="bs-subtitle">{description}</div>',

        unsafe_allow_html=True,

    )





def metric_card(label, value):
    st.markdown(
        dedent(
            f"""
            <div class="bs-card">
                <div class="bs-card-label">{label}</div>
                <div class="bs-card-value">{value}</div>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )





def get_field(item, field, default=None):

    if isinstance(item, dict):

        return item.get(field, default)

    return getattr(item, field, default)





def inventory_is_loaded():

    return (

        isinstance(st.session_state.inventory_df, pd.DataFrame)

        and not st.session_state.inventory_df.empty

    )





# ============================================================

# OVERVIEW

# ============================================================



def show_overview():

    page_header(

        "Project BlindSpot",

        "Unmasking Hidden Vendor AI | Third-party AI due diligence",

    )



    st.write(

        "Investigate public evidence of vendor AI usage, understand "

        "potential security implications, and maintain a traceable "

        "assessment for human review."

    )



    df = st.session_state.inventory_df

    vendor_count = len(df) if isinstance(df, pd.DataFrame) else 0



    col1, col2, col3, col4 = st.columns(4)



    with col1:

        metric_card("Vendors loaded", vendor_count)

    with col2:

        metric_card(

            "Evidence records",

            len(st.session_state.evidence_records),

        )

    with col3:

        metric_card(

            "Review decisions",

            len(st.session_state.review_log),

        )

    with col4:

        metric_card(

            "Risk findings",

            len(st.session_state.risk_findings),

        )



    st.subheader("Assessment workflow")



    workflow = [
        ("01", "Vendor inventory", "Load and validate the supplied workbook."),
        (
            "02",
            "Criticality",
            "Calculate supported inventory ratings; review unknown factors.",
        ),
        (
            "03",
            "Live Vendor Investigation Lab",
            "Run bounded public-source research with visible progress.",
        ),
        ("04", "Evidence review", "Validate evidence and record decisions."),
        ("05", "Risk assessment", "Score only reviewer-rated, evidence-backed findings."),
        ("06", "Vendor profile and mesh", "Review vendor-specific evidence and relationships."),
        ("07", "Reports", "Export separate criticality, evidence, and risk scores."),
    ]



    for number, title, description in workflow:

        with st.container(border=True):

            left, right = st.columns([1, 12])

            with left:

                st.markdown(f"### {number}")

            with right:

                st.markdown(f"**{title}**")

                st.caption(description)



    st.subheader("Assessment principles")



    st.markdown(

        """

        - AI-related keywords are signals, not proof.

        - Missing public evidence does not prove that a vendor does not use AI.

        - Vendor criticality, AI-use classification, and security risk

          are assessed separately.

        - Human reviewers retain responsibility for final decisions.

        """

    )





# ============================================================

# VENDOR INVENTORY

# ============================================================



def show_inventory():

    page_header(

        "Vendor Inventory",

        "Upload and inspect the source workbook without modifying it.",

    )



    uploaded_file = st.file_uploader(

        "Upload vendor inventory workbook",

        type=["xlsx", "xlsm"],

        key="inventory_uploader",

    )



    if uploaded_file is not None:
        workbook_bytes = uploaded_file.getvalue()
        workbook_fingerprint = sha256(workbook_bytes).hexdigest()

        if workbook_fingerprint != st.session_state.inventory_fingerprint:
            temp_path = None
            loaded_new_workbook = False

            try:

                suffix = os.path.splitext(uploaded_file.name)[1]



                with tempfile.NamedTemporaryFile(

                    delete=False,

                    suffix=suffix,

                ) as temp_file:

                    temp_file.write(workbook_bytes)

                    temp_path = temp_file.name



                inventory, messages, metadata = load_inventory(

                    temp_path,

                    sheet_name="Vendor Inventory",

                )



                st.session_state.inventory_df = inventory

                st.session_state.inventory_messages = messages

                st.session_state.inventory_metadata = metadata
                st.session_state.inventory_filename = uploaded_file.name
                st.session_state.inventory_fingerprint = workbook_fingerprint

                # Clear assessments associated with the previous workbook.
                for key, value in {
                    "evidence_records": [],
                    "review_log": [],
                    "risk_findings": [],
                    "collection_log": [],
                    "criticality_ratings": {},
                    "investigation_assessments": {},
                    "discovered_sources": {},
                    "investigation_vendor_id": None,
                    "investigation_vendor_name": None,
                    "relationship_records": [],
                    "last_collection_summary": None,
                    "live_investigation_results": {},
                    "assessment_workbook_bytes": None,
                }.items():
                    st.session_state[key] = value

                if not duplicate_vendor_ids(inventory):
                    st.session_state["criticality_ratings"] = (
                        initialize_inventory_criticality(inventory)
                    )

                for key in list(st.session_state.keys()):
                    if key.startswith(("scope_complete_", "scope_notes_")):
                        del st.session_state[key]

                for key in (
                    "criticality_vendor",
                    "investigation_vendor",
                    "summary_vendor",
                    "profile_vendor_selector",
                    "risk_assessment_vendor",
                    "manual_investigation_urls",
                ):
                    st.session_state.pop(key, None)

                loaded_new_workbook = True

            except Exception as exc:
                st.error(f"Could not load workbook: {exc}")



            finally:

                if temp_path and os.path.exists(temp_path):

                    os.remove(temp_path)

            if loaded_new_workbook:
                st.rerun()



    df = st.session_state.inventory_df



    if not isinstance(df, pd.DataFrame):

        st.info("Upload the vendor inventory to begin.")

        return





    if df.empty:

        st.warning("The workbook contains no vendor records.")

        return



    # Validate the loaded inventory without modifying the source data.

    st.subheader("Inventory validation")



    try:

        validation_report = validate_inventory(df)



        col1, col2, col3 = st.columns(3)



        with col1:

            st.metric("Rows checked", validation_report.total_rows)



        with col2:

            st.metric("Errors", validation_report.error_count)



        with col3:

            st.metric("Warnings", validation_report.warning_count)



        if validation_report.issues:

            issues_df = pd.DataFrame(

                validation_issues_as_records(validation_report)

            )



            st.dataframe(

                issues_df,

                use_container_width=True,

                hide_index=True,

            )



            st.download_button(

                "Export validation report",

                data=issues_df.to_csv(index=False).encode("utf-8"),

                file_name="blindspot_validation_report.csv",

                mime="text/csv",

                key="inventory_validation_export",

            )

        else:

            st.success("No inventory validation issues were found.")



        if not validation_report.is_valid:

            st.warning(

                "Resolve the inventory errors before relying on downstream "

                "assessments. The uploaded data has not been modified."

            )

    except Exception as exc:
        st.error(f"Inventory validation could not be completed: {exc}")





    for message in st.session_state.inventory_messages:

        if isinstance(message, dict):

            text = str(message.get("message", message))

            level = str(message.get("level", "info")).lower()

        else:

            text = str(message)

            level = "info"



        if level in {"error", "critical"}:

            st.error(text)

        elif level in {"warning", "warn"}:

            st.warning(text)

        else:

            st.info(text)



    col1, col2, col3 = st.columns(3)



    with col1:

        st.metric("Vendor records", len(df))

    with col2:

        st.metric("Columns detected", len(df.columns))

    with col3:

        st.metric(

            "Vendor IDs present",

            int(df["Vendor ID"].notna().sum())

            if "Vendor ID" in df.columns else 0,

        )



    st.subheader("Source inventory")

    st.dataframe(df, use_container_width=True, hide_index=True)



    st.download_button(

        "Download inventory copy",

        data=df.to_csv(index=False).encode("utf-8"),

        file_name="blindspot_inventory.csv",

        mime="text/csv",

    )



    if "Vendor ID" not in df.columns or "Vendor Name" not in df.columns:
        st.error("Vendor ID and Vendor Name columns are required.")
        return

    duplicate_ids = duplicate_vendor_ids(df)
    if duplicate_ids:
        st.warning(
            "Resolve duplicate Vendor IDs before assessing criticality. "
            "Downstream assessments are keyed by Vendor ID."
        )
        return



    st.divider()

    st.subheader("Vendor criticality assessment")



    vendor_options = {}



    for index, row in df.iterrows():
        if pd.isna(row["Vendor ID"]) or not str(row["Vendor ID"]).strip():
            continue
        if pd.isna(row["Vendor Name"]) or not str(row["Vendor Name"]).strip():
            continue

        label = (
            f"{row['Vendor Name']} "
            f"({row['Vendor ID']}) — row {index + 1}"
        )
        vendor_options[label] = index

    if not vendor_options:
        st.warning("No vendor with a usable Vendor ID is available to assess.")
        return



    selected_label = st.selectbox(

        "Select vendor",

        list(vendor_options.keys()),

        key="criticality_vendor",

    )



    selected_index = vendor_options[selected_label]

    vendor = df.loc[selected_index]



    st.write(f"**Vendor:** {vendor['Vendor Name']}")

    st.write(f"**Vendor ID:** {vendor['Vendor ID']}")



    factors = [

        ("data_sensitivity", "Data sensitivity", rate_data_sensitivity),

        (

            "operational_dependency",

            "Operational dependency",

            rate_operational_dependency,

        ),

        ("regulatory_exposure", "Regulatory exposure", None),

        ("payment_involvement", "Payment involvement", None),

        ("annual_data_volume", "Annual data volume", None),

    ]



    factor_ratings = {}

    factor_notes = {}



    rating_options = [

        "Unassessed",

        "1 - Very low",

        "2 - Low",

        "3 - Moderate",

        "4 - High",

        "5 - Very high",

    ]



    for factor_key, label, rating_function in factors:

        with st.container(border=True):

            st.markdown(f"**{label}**")



            column = st.selectbox(

                f"Workbook column for {label}",

                ["Not mapped"] + list(df.columns),

                key=f"column_{factor_key}",

            )



            raw_value = (

                None if column == "Not mapped"

                else vendor.get(column)

            )



            if rating_function:
                suggested_rating, suggestion_note = rating_function(raw_value)
            else:
                suggested_rating, suggestion_note = rate_numeric_factor(raw_value)

            st.caption(f"Source value: {raw_value!s}")
            st.caption(suggestion_note)



            if suggested_rating is not None:

                suggestion = int(suggested_rating)

                st.caption(

                    f"Suggested rating: {suggestion}/5. "

                    "Verify it before using it."

                )



            rating = st.selectbox(

                f"Reviewed rating — {label}",

                rating_options,

                key=f"rating_{factor_key}_{selected_index}",

            )



            if rating == "Unassessed":

                factor_ratings[factor_key] = None

                factor_notes[factor_key] = "Not assessed"

            else:

                factor_ratings[factor_key] = int(rating[0])

                factor_notes[factor_key] = (

                    f"Reviewer-selected rating {rating}; "

                    f"source value: {raw_value!s}"

                )



    st.caption("Draft criticality weights")



    st.dataframe(

        pd.DataFrame([

            {

                "Factor": factor,

                "Weight (%)": round(weight * 100, 1),

            }

            for factor, weight in WEIGHTS.items()

        ]),

        use_container_width=True,

        hide_index=True,

    )



    st.caption(

        "These are proposed weights. Validate them against the case-study "

        "guidance before relying on the resulting scores."

    )



    if st.button(

        "Calculate criticality",

        type="primary",

        key=f"calculate_{selected_index}",

    ):

        try:

            result = calculate_criticality(factor_ratings)



            st.session_state.criticality_ratings[
                str(vendor["Vendor ID"])
            ] = {
                "vendor_name": str(vendor["Vendor Name"]),
                "ratings": factor_ratings.copy(),
                "notes": factor_notes.copy(),
                "result": result,
                "auto_calculated": False,
            }

            st.session_state.assessment_workbook_bytes = None

        except (ValueError, TypeError) as exc:

            st.error(f"Could not calculate criticality: {exc}")



    saved = st.session_state.criticality_ratings.get(

        str(vendor["Vendor ID"])

    )



    if saved:

        result = saved["result"]

        score = get_field(result, "score")

        status = get_field(result, "status", "Unassessed")

        coverage = get_field(result, "coverage_percent")



        st.subheader("Criticality result")
        st.caption(
            "Initial scores are calculated on inventory upload from explicit "
            "rating fields and recognized categories. Unknown values remain "
            "unassessed; numeric annual-volume bands are not inferred. "
            "Reviewer-selected ratings below replace the automatic assessment."
            if saved.get("auto_calculated")
            else "Reviewer-entered criticality assessment using the displayed "
            "factor ratings and proposed weights."
        )



        col1, col2, col3 = st.columns(3)



        with col1:

            st.metric(

                "Score",

                f"{score:.1f}/100" if score is not None else "Unassessed",

            )



        with col2:

            st.metric("Status", str(status))



        with col3:

            st.metric(

                "Coverage",

                f"{coverage:.1f}%"
                if isinstance(coverage, (int, float))
                else str(coverage or "Not available"),

            )



        rationale = get_field(result, "rationale", [])



        if rationale:

            st.markdown("**Rationale**")

            if isinstance(rationale, (list, tuple)):

                for item in rationale:

                    st.write(f"- {item}")

            else:

                st.write(rationale)





# ============================================================

# EVIDENCE REGISTER

# ============================================================



def show_evidence_register():

    page_header(

        "Evidence Register",

        "Search and inspect collected evidence records.",

    )



    records = st.session_state.evidence_records



    if not records:

        st.info("No evidence records have been collected yet.")

        return



    rows = []



    for item in records:

        rows.append({

            "Evidence ID": get_field(item, "evidence_id", ""),

            "Vendor ID": get_field(item, "vendor_id", ""),

            "Vendor Name": get_field(item, "vendor_name", ""),
            "Source URL": get_field(item, "source_url", ""),
            "Source Title": get_field(item, "source_title", ""),
            "Retrieved At (UTC)": get_field(item, "retrieved_at", ""),
            "Data Origin": get_field(
                item,
                "data_origin",
                "Provenance not recorded (legacy)",
            ),
            "Discovery Method": get_field(item, "discovery_method", ""),
            "Investigation Run ID": get_field(item, "run_id", ""),
            "Excerpt": get_field(item, "excerpt", ""),

            "Review Status": get_field(

                item, "review_status", "Needs review"

            ),

        })



    evidence_df = pd.DataFrame(rows)



    search = st.text_input("Search evidence")



    if search:

        mask = evidence_df.astype(str).apply(

            lambda col: col.str.contains(

                search,

                case=False,

                na=False,

                regex=False,

            )

        ).any(axis=1)

        evidence_df = evidence_df[mask]



    status = st.selectbox(

        "Filter review status",

        ["All", "Needs review", "Accepted", "Rejected"],

    )



    if status != "All":

        evidence_df = evidence_df[

            evidence_df["Review Status"].astype(str).str.lower()

            == status.lower()

        ]



    st.dataframe(

        evidence_df,

        use_container_width=True,

        hide_index=True,

    )



    st.download_button(

        "Export evidence register",

        data=evidence_df.to_csv(index=False).encode("utf-8"),

        file_name="blindspot_evidence_register.csv",

        mime="text/csv",

    )





# ============================================================

# RISK ASSESSMENT

# ============================================================



def show_risk_assessment():
    page_header(
        "Risk Assessment",
        "Record vendor-specific security concerns, supporting evidence, severity, and recommended actions.",
    )
    inventory = st.session_state.get("inventory_df")
    findings = st.session_state.setdefault("risk_findings", [])
    evidence_records = st.session_state.setdefault("evidence_records", [])

    if not isinstance(inventory, pd.DataFrame) or inventory.empty:
        st.warning("Upload a vendor inventory before assessing risks.")
        return
    if not {"Vendor ID", "Vendor Name"}.issubset(inventory.columns):
        st.error("The inventory must contain Vendor ID and Vendor Name.")
        return
    if duplicate_vendor_ids(inventory):
        st.error(
            "Resolve duplicate Vendor IDs before recording vendor-specific "
            "risk findings."
        )
        return

    vendors = {}
    for _, row in inventory.iterrows():
        vendor_id = str(row["Vendor ID"]).strip()
        vendor_name = str(row["Vendor Name"]).strip()
        if (
            vendor_id
            and vendor_id.lower() != "nan"
            and vendor_name
            and vendor_name.lower() != "nan"
        ):
            vendors[f"{vendor_name} ({vendor_id})"] = {
                "vendor_id": vendor_id, "vendor_name": vendor_name
            }
    if not vendors:
        st.warning("No valid vendors were found in the inventory.")
        return

    selected_label = st.selectbox(
        "Vendor to assess", list(vendors.keys()), key="risk_assessment_vendor"
    )
    selected_vendor = vendors[selected_label]
    vendor_id = selected_vendor["vendor_id"]
    vendor_name = selected_vendor["vendor_name"]

    def field(item, name, default=""):
        return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)

    vendor_findings = [item for item in findings if str(field(item, "vendor_id")) == vendor_id]
    vendor_evidence = [item for item in evidence_records if str(field(item, "vendor_id")) == vendor_id]
    evidence_score = calculate_evidence_score(vendor_evidence)
    cyber_risk_score = calculate_ai_cyber_risk_score(
        vendor_findings,
        evidence_records=vendor_evidence,
    )

    score_col1, score_col2 = st.columns(2)
    score_col1.metric(
        "Evidence quality score",
        f"{evidence_score['score']:.1f}/100"
        if evidence_score["score"] is not None
        else "Unassessed",
        help="Accepted, relevant source quality only; not a probability.",
    )
    score_col2.metric(
        "AI cybersecurity risk score",
        f"{cyber_risk_score['score']:.1f}/100"
        if cyber_risk_score["score"] is not None
        else "Unassessed",
        help="Reviewer-rated, evidence-supported prioritization index.",
    )
    st.caption(
        f"Evidence score: {evidence_score['status']}. Cyber risk score: "
        f"{cyber_risk_score['status']}. No score is inferred from AI-use "
        "classification alone."
    )
    with st.expander("How these two scores are calculated"):
        st.write(evidence_score["rationale"])
        st.write(cyber_risk_score["rationale"])
        st.write(
            f"Cyber risk coverage: {cyber_risk_score['scored_findings']} "
            "evidence-supported active finding(s); "
            f"{cyber_risk_score['unassessed_findings']} unassessed and "
            f"{cyber_risk_score['unsupported_findings']} without accepted "
            "evidence for this vendor."
        )

    st.subheader(f"Risk register — {vendor_name}")
    if vendor_findings:
        rows = []
        for item in vendor_findings:
            record = item if isinstance(item, dict) else vars(item)
            rows.append({
                "Finding ID": record.get("finding_id", ""),
                "Risk theme": record.get(
                    "risk_theme", record.get("title", "")
                ),
                "Severity": record.get("severity", "Unassessed"),
                "Status": record.get(
                    "finding_status", record.get("status", "Needs review")
                ),
                "Description": record.get("description", ""),
                "Rationale": record.get("rationale", ""),
                "Likelihood": record.get("likelihood", "Unassessed"),
                "Evidence IDs": ", ".join(map(str, record.get("evidence_ids", []))),
                "Recommendation": record.get(
                    "recommendation",
                    record.get("recommended_action", ""),
                ),
                "Reviewer": record.get("reviewer", ""),
                "Reviewed At (UTC)": record.get("reviewed_at", ""),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Findings", len(rows))
        c2.metric("High / Critical", sum(str(r["Severity"]).lower() in {"high", "critical"} for r in rows))
        c3.metric(
            "Open findings",
            sum(
                str(r["Status"]).lower()
                not in {"resolved", "accepted risk"}
                for r in rows
            ),
        )
    else:
        st.info("No risk findings have been recorded for this vendor.")

    st.divider()
    st.subheader("Record a risk finding")
    theme_options = {
        details["label"]: theme
        for theme, details in RISK_THEMES.items()
    }
    evidence_options = {}
    for item in vendor_evidence:
        evidence_id = str(field(item, "evidence_id", ""))
        source_url = str(field(item, "source_url", ""))
        excerpt = str(field(item, "excerpt", ""))
        if evidence_id:
            evidence_options[f"{evidence_id} — {source_url or excerpt[:70]}"] = evidence_id

    with st.form("create_vendor_risk_finding"):
        theme_label = st.selectbox(
            "Risk theme", list(theme_options.keys())
        )
        theme = theme_options[theme_label]
        severity = st.selectbox("Severity", ["Low", "Moderate", "High", "Critical", "Unassessed"])
        likelihood = st.selectbox(
            "Likelihood", ["Unassessed", "Unlikely", "Possible", "Likely"]
        )
        description = st.text_area("Risk description", placeholder="Explain the concern and what the evidence does or does not establish.")
        rationale = st.text_area(
            "Assessment rationale",
            placeholder="Explain what is known, what remains unverified, and why this finding is recorded.",
        )
        selected_evidence = st.multiselect("Supporting evidence", list(evidence_options.keys()))
        recommendation = st.text_area("Recommended action", placeholder="Describe the next verification or mitigation step.")
        status = st.selectbox(
            "Review status",
            ["Needs review", "Under review", "Reviewed", "Resolved", "Accepted risk"],
        )
        reviewer = st.text_input("Reviewer")
        submitted = st.form_submit_button("Save risk finding", type="primary")

    if submitted:
        if not description.strip() or not rationale.strip() or not recommendation.strip():
            st.error("Enter the risk description, rationale, and recommended action.")
        elif not reviewer.strip():
            st.error("Enter the reviewer responsible for this finding.")
        else:
            try:
                finding = create_risk_finding(
                    vendor_id=vendor_id,
                    vendor_name=vendor_name,
                    theme=theme,
                    rationale=rationale,
                    severity=severity,
                    likelihood=likelihood,
                    evidence_ids=[
                        evidence_options[label]
                        for label in selected_evidence
                    ],
                    finding_id=f"RF-{vendor_id}-{len(findings) + 1:03d}",
                    description=description,
                    recommended_action=recommendation,
                    status=status,
                    reviewer=reviewer,
                    reviewed_at=datetime.now(timezone.utc).isoformat(),
                )
                record = asdict(finding)
                record["risk_theme"] = finding.title
                record["finding_status"] = finding.status
                record["recommendation"] = finding.recommended_action
                record["created_at"] = finding.reviewed_at
                findings.append(record)
                st.session_state["risk_findings"] = findings
                st.session_state["assessment_workbook_bytes"] = None
                st.success(
                    "Risk finding saved as a reviewer assessment. "
                    "AI-related evidence alone does not confirm a security risk."
                )
                st.rerun()
            except ValueError as exc:
                st.error(f"Could not save the risk finding: {exc}")

    st.caption("Reviewer-entered findings are assessments, not automatically verified conclusions. An evidence gap alone does not prove a vendor is insecure.")


# ============================================================
# REPORTS & EXPORT
# ============================================================





# ============================================================

# SIDEBAR

# ============================================================



with st.sidebar:

    st.markdown("## 🔎 BlindSpot")

    st.caption("Vendor AI due diligence")

    st.divider()



    selected_page = st.radio(

        "Navigation",

        [

            "Overview",

            "Vendor Inventory",

            "AI Investigation",
            "Live Vendor Investigation Lab",
            "Evidence Register",

            "Risk Assessment",

            "Intelligence Mesh",

            "Review Centre",

            "Reports & Export",

            "Public Evidence Collection",

            "Vendor Profile",

            "Investigation Summary",

        ],

        key="main_navigation",

        label_visibility="collapsed",

    )



    st.divider()



    if inventory_is_loaded():

        st.success("Inventory loaded")

        st.caption(

            f"{len(st.session_state.inventory_df)} vendor records"

        )

    else:

        st.info("Upload the vendor inventory to begin.")



    st.divider()

    st.caption("Project BlindSpot | Internal case-study prototype")





# ============================================================

# PAGE ROUTING
# ============================================================

if selected_page == "Overview":
    show_overview()
elif selected_page == "Vendor Inventory":
    show_inventory()
elif selected_page == "AI Investigation":
    show_ai_investigation()
elif selected_page == "Live Vendor Investigation Lab":
    show_live_investigation_lab()
elif selected_page == "Evidence Register":
    show_evidence_register()
elif selected_page == "Risk Assessment":
    show_risk_assessment()
elif selected_page == "Intelligence Mesh":
    show_intelligence_mesh_page()
elif selected_page == "Review Centre":
    show_review_centre()
elif selected_page == "Reports & Export":
    show_report_export()
elif selected_page == "Public Evidence Collection":
    show_collection_page()
elif selected_page == "Vendor Profile":
    show_vendor_profile()
elif selected_page == "Investigation Summary":
    show_investigation_summary()
>>>>>>> origin/main
