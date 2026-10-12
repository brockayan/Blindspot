<<<<<<< HEAD
"""Consolidated reporting and export for Project BlindSpot."""

from dataclasses import asdict, is_dataclass
from io import BytesIO
import json

import pandas as pd
import streamlit as st
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.assessment.risk import calculate_ai_cyber_risk_score
from src.assessment.scores import calculate_evidence_score
from src.ui.intelligence_mesh import relationship_records_for_display


def _get(item, key, default=None):
    """Read a field from a dictionary or an object."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _to_record(item):
    """Convert one dictionary/dataclass/object into a plain record."""
    if isinstance(item, dict):
        return dict(item)
    if is_dataclass(item) and not isinstance(item, type):
        return asdict(item)
    if hasattr(item, "__dict__"):
        return vars(item).copy()
    return {"Value": item}


def _spreadsheet_value(value):
    """Convert nested values into readable spreadsheet-safe strings."""
    if value is None:
        return ""
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, (dict, list, tuple, set)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(value)
    return value


def _records_to_dataframe(records):
    """Convert records into a DataFrame and flatten nested grade fields."""
    rows = []

    for item in records:
        row = _to_record(item)
        grade = row.pop("grade", None)

        if isinstance(grade, dict):
            for key, value in grade.items():
                row[f"Evidence Grade - {key}"] = _spreadsheet_value(value)
        elif is_dataclass(grade) and not isinstance(grade, type):
            for key, value in asdict(grade).items():
                row[f"Evidence Grade - {key}"] = _spreadsheet_value(value)
        elif grade is not None:
            row["Evidence Grade"] = _spreadsheet_value(grade)

        rows.append({
            key: _spreadsheet_value(value)
            for key, value in row.items()
        })

    return pd.DataFrame(rows)


def _criticality_dataframe(assessments):
    """Build a readable table from saved criticality assessments."""
    rows = []

    for vendor_id, assessment in assessments.items():
        if not isinstance(assessment, dict):
            assessment = _to_record(assessment)

        result = assessment.get("result")
        rows.append({
            "Vendor ID": vendor_id,
            "Vendor Name": assessment.get("vendor_name", ""),
            "Criticality Score": _get(result, "score"),
            "Assessment Status": _get(result, "status", "Unassessed"),
            "Coverage (%)": _get(
                result, "coverage_percent", _get(result, "coverage")
            ),
            "Ratings": _spreadsheet_value(assessment.get("ratings", {})),
            "Reviewer Notes": _spreadsheet_value(assessment.get("notes", {})),
        })

    return pd.DataFrame(rows)


def _classification_dataframe(investigations):
    """Convert saved AI-use assessments into readable export rows."""
    rows = []

    for vendor_id, assessment in investigations.items():
        row = _to_record(assessment)
        row.setdefault("vendor_id", vendor_id)

        # Ensure nested values such as evidence IDs and rationale export cleanly.
        rows.append({
            key: _spreadsheet_value(value)
            for key, value in row.items()
        })

    return pd.DataFrame(rows)


def _vendor_scores_dataframe(inventory, assessments, investigations, evidence, findings):
    columns = [
        "Vendor ID",
        "Vendor Name",
        "Business Criticality (0-100)",
        "Criticality Status",
        "Evidence Quality (0-100)",
        "Evidence Score Status",
        "Accepted Graded Evidence",
        "AI Cybersecurity Risk (0-100)",
        "Cyber Risk Status",
        "Scored Active Risk Findings",
        "AI-use Classification",
    ]
    if not isinstance(inventory, pd.DataFrame) or not {
        "Vendor ID",
        "Vendor Name",
    }.issubset(inventory.columns):
        return pd.DataFrame(columns=columns)

    rows = []
    for _, vendor in inventory.iterrows():
        vendor_id = str(vendor.get("Vendor ID", "")).strip()
        vendor_name = str(vendor.get("Vendor Name", "")).strip()
        if not vendor_id or vendor_id.casefold() == "nan":
            continue
        vendor_evidence = [
            item for item in evidence
            if str(_get(item, "vendor_id", "")).strip() == vendor_id
        ]
        vendor_findings = [
            item for item in findings
            if str(_get(item, "vendor_id", "")).strip() == vendor_id
        ]
        criticality = assessments.get(vendor_id, {})
        criticality_result = criticality.get("result")
        quality = calculate_evidence_score(vendor_evidence)
        risk = calculate_ai_cyber_risk_score(
            vendor_findings,
            evidence_records=vendor_evidence,
        )
        investigation = investigations.get(vendor_id, {})
        rows.append({
            "Vendor ID": vendor_id,
            "Vendor Name": vendor_name,
            "Business Criticality (0-100)": _get(
                criticality_result, "score"
            ),
            "Criticality Status": _get(
                criticality_result, "status", "Unassessed"
            ),
            "Evidence Quality (0-100)": quality["score"],
            "Evidence Score Status": quality["status"],
            "Accepted Graded Evidence": quality["evidence_count"],
            "AI Cybersecurity Risk (0-100)": risk["score"],
            "Cyber Risk Status": risk["status"],
            "Scored Active Risk Findings": risk["scored_findings"],
            "AI-use Classification": investigation.get(
                "status",
                "Not assessed",
            ),
        })
    return pd.DataFrame(rows, columns=columns)


def _format_workbook(buffer):
    """Apply readable formatting to the generated workbook."""
    buffer.seek(0)
    workbook = load_workbook(buffer)

    header_fill = PatternFill(fill_type="solid", fgColor="DCE6F1")

    for worksheet in workbook.worksheets:
        worksheet.freeze_panes = "A2"

        if worksheet.max_row >= 1 and worksheet.max_column >= 1:
            worksheet.auto_filter.ref = worksheet.dimensions

        for cell in worksheet[1]:
            cell.font = Font(bold=True, color="172B4D")
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="top", wrap_text=True)

        for column_cells in worksheet.columns:
            column_letter = get_column_letter(column_cells[0].column)
            max_length = 0

            for cell in list(column_cells)[:200]:
                if cell.value is not None:
                    max_length = max(max_length, min(len(str(cell.value)), 55))

            worksheet.column_dimensions[column_letter].width = min(
                max(max_length + 2, 12),
                45,
            )

        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def build_assessment_workbook():
    """Create a consolidated Excel workbook from current session data."""
    sheets = {}

    inventory = st.session_state.get("inventory_df")
    evidence = st.session_state.get("evidence_records", [])
    reviews = st.session_state.get("review_log", [])
    findings = st.session_state.get("risk_findings", [])
    collection_log = st.session_state.get("collection_log", [])
    assessments = st.session_state.get("criticality_ratings", {})
    investigations = st.session_state.get("investigation_assessments", {})
    relationships = st.session_state.get("relationship_records", [])

    # Include each sheet consistently, even when a section has no records.
    if isinstance(inventory, pd.DataFrame):
        sheets["Vendor Inventory"] = inventory.copy()
    else:
        sheets["Vendor Inventory"] = pd.DataFrame()

    sheets["Evidence Register"] = _records_to_dataframe(evidence)
    sheets["Review Log"] = _records_to_dataframe(reviews)
    sheets["Risk Findings"] = _records_to_dataframe(findings)
    sheets["Collection Log"] = _records_to_dataframe(collection_log)
    sheets["Criticality Assessments"] = _criticality_dataframe(assessments)
    sheets["AI Investigation Summary"] = _classification_dataframe(
        investigations
    )
    vendor_count = len(inventory) if isinstance(inventory, pd.DataFrame) else 0
    sheets["Assessment Overview"] = pd.DataFrame([
        {"Metric": "Vendor records", "Value": vendor_count},
        {"Metric": "Evidence records", "Value": len(evidence)},
        {"Metric": "Review decisions", "Value": len(reviews)},
        {"Metric": "Risk findings", "Value": len(findings)},
        {"Metric": "Collection attempts", "Value": len(collection_log)},
        {"Metric": "Criticality assessments", "Value": len(assessments)},
        {"Metric": "AI-use classifications", "Value": len(investigations)},
        {"Metric": "Recorded relationships", "Value": len(relationships)},
    ])
    sheets["Intelligence Mesh"] = _records_to_dataframe(
        relationship_records_for_display(relationships, evidence)
    )
    sheets["Vendor Scores"] = _vendor_scores_dataframe(
        inventory,
        assessments,
        investigations,
        evidence,
        findings,
    )

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet_name, dataframe in sheets.items():
            # Excel sheet names cannot exceed 31 characters.
            dataframe.to_excel(
                writer,
                sheet_name=sheet_name[:31],
                index=False,
            )

    return _format_workbook(buffer)


def show_report_export():
    """Render the consolidated report and export page."""
    st.title("Reports & Export")
    st.caption(
        "Generate a consolidated workbook from records in the current session."
    )

    inventory = st.session_state.get("inventory_df")
    evidence = st.session_state.get("evidence_records", [])
    reviews = st.session_state.get("review_log", [])
    findings = st.session_state.get("risk_findings", [])
    collection_log = st.session_state.get("collection_log", [])
    assessments = st.session_state.get("criticality_ratings", {})
    investigations = st.session_state.get("investigation_assessments", {})
    relationships = st.session_state.get("relationship_records", [])

    st.subheader("Assessment summary")

    metrics = [
        ("Vendors", len(inventory) if isinstance(inventory, pd.DataFrame) else 0),
        ("Evidence records", len(evidence)),
        ("Review decisions", len(reviews)),
        ("Risk findings", len(findings)),
        ("Collection attempts", len(collection_log)),
        ("Criticality assessments", len(assessments)),
        ("AI-use classifications", len(investigations)),
        ("Recorded relationships", len(relationships)),
    ]

    for start in range(0, len(metrics), 3):
        columns = st.columns(3)
        for column, (label, value) in zip(columns, metrics[start:start + 3]):
            with column:
                st.metric(label, value)

    st.divider()
    st.subheader("Consolidated assessment workbook")
    st.write(
        "The workbook includes the source inventory, evidence register, "
        "review log, risk findings, collection log, criticality assessments, "
        "AI investigation summary, Intelligence Mesh relationships, and an "
        "overview sheet. A Vendor Scores sheet keeps business criticality, "
        "evidence quality, and AI cybersecurity risk separate."
    )

    if st.button(
        "Prepare Excel workbook",
        type="primary",
        key="prepare_assessment_workbook",
    ):
        try:
            workbook = build_assessment_workbook()
            st.session_state["assessment_workbook_bytes"] = workbook.getvalue()
            st.success("The workbook is ready to download.")
        except Exception as exc:
            st.error(f"Could not prepare workbook: {exc}")

    workbook_bytes = st.session_state.get("assessment_workbook_bytes")

    if workbook_bytes:
        st.download_button(
            "Download consolidated Excel workbook",
            data=workbook_bytes,
            file_name="Project_BlindSpot_Assessment.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            key="download_assessment_workbook",
        )

    st.caption(
        "Exports contain records available in the current session. They do "
        "not prove every vendor or source has been assessed. Store the "
        "workbook securely because it may contain sensitive case-study data."
    )
=======
"""Consolidated reporting and export for Project BlindSpot."""

from dataclasses import asdict, is_dataclass
from io import BytesIO
import json

import pandas as pd
import streamlit as st
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.assessment.risk import calculate_ai_cyber_risk_score
from src.assessment.scores import calculate_evidence_score
from src.ui.intelligence_mesh import relationship_records_for_display


def _get(item, key, default=None):
    """Read a field from a dictionary or an object."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _to_record(item):
    """Convert one dictionary/dataclass/object into a plain record."""
    if isinstance(item, dict):
        return dict(item)
    if is_dataclass(item) and not isinstance(item, type):
        return asdict(item)
    if hasattr(item, "__dict__"):
        return vars(item).copy()
    return {"Value": item}


def _spreadsheet_value(value):
    """Convert nested values into readable spreadsheet-safe strings."""
    if value is None:
        return ""
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, (dict, list, tuple, set)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(value)
    return value


def _records_to_dataframe(records):
    """Convert records into a DataFrame and flatten nested grade fields."""
    rows = []

    for item in records:
        row = _to_record(item)
        grade = row.pop("grade", None)

        if isinstance(grade, dict):
            for key, value in grade.items():
                row[f"Evidence Grade - {key}"] = _spreadsheet_value(value)
        elif is_dataclass(grade) and not isinstance(grade, type):
            for key, value in asdict(grade).items():
                row[f"Evidence Grade - {key}"] = _spreadsheet_value(value)
        elif grade is not None:
            row["Evidence Grade"] = _spreadsheet_value(grade)

        rows.append({
            key: _spreadsheet_value(value)
            for key, value in row.items()
        })

    return pd.DataFrame(rows)


def _criticality_dataframe(assessments):
    """Build a readable table from saved criticality assessments."""
    rows = []

    for vendor_id, assessment in assessments.items():
        if not isinstance(assessment, dict):
            assessment = _to_record(assessment)

        result = assessment.get("result")
        rows.append({
            "Vendor ID": vendor_id,
            "Vendor Name": assessment.get("vendor_name", ""),
            "Criticality Score": _get(result, "score"),
            "Assessment Status": _get(result, "status", "Unassessed"),
            "Coverage (%)": _get(
                result, "coverage_percent", _get(result, "coverage")
            ),
            "Ratings": _spreadsheet_value(assessment.get("ratings", {})),
            "Reviewer Notes": _spreadsheet_value(assessment.get("notes", {})),
        })

    return pd.DataFrame(rows)


def _classification_dataframe(investigations):
    """Convert saved AI-use assessments into readable export rows."""
    rows = []

    for vendor_id, assessment in investigations.items():
        row = _to_record(assessment)
        row.setdefault("vendor_id", vendor_id)

        # Ensure nested values such as evidence IDs and rationale export cleanly.
        rows.append({
            key: _spreadsheet_value(value)
            for key, value in row.items()
        })

    return pd.DataFrame(rows)


def _vendor_scores_dataframe(inventory, assessments, investigations, evidence, findings):
    columns = [
        "Vendor ID",
        "Vendor Name",
        "Business Criticality (0-100)",
        "Criticality Status",
        "Evidence Quality (0-100)",
        "Evidence Score Status",
        "Accepted Graded Evidence",
        "AI Cybersecurity Risk (0-100)",
        "Cyber Risk Status",
        "Scored Active Risk Findings",
        "AI-use Classification",
    ]
    if not isinstance(inventory, pd.DataFrame) or not {
        "Vendor ID",
        "Vendor Name",
    }.issubset(inventory.columns):
        return pd.DataFrame(columns=columns)

    rows = []
    for _, vendor in inventory.iterrows():
        vendor_id = str(vendor.get("Vendor ID", "")).strip()
        vendor_name = str(vendor.get("Vendor Name", "")).strip()
        if not vendor_id or vendor_id.casefold() == "nan":
            continue
        vendor_evidence = [
            item for item in evidence
            if str(_get(item, "vendor_id", "")).strip() == vendor_id
        ]
        vendor_findings = [
            item for item in findings
            if str(_get(item, "vendor_id", "")).strip() == vendor_id
        ]
        criticality = assessments.get(vendor_id, {})
        criticality_result = criticality.get("result")
        quality = calculate_evidence_score(vendor_evidence)
        risk = calculate_ai_cyber_risk_score(
            vendor_findings,
            evidence_records=vendor_evidence,
        )
        investigation = investigations.get(vendor_id, {})
        rows.append({
            "Vendor ID": vendor_id,
            "Vendor Name": vendor_name,
            "Business Criticality (0-100)": _get(
                criticality_result, "score"
            ),
            "Criticality Status": _get(
                criticality_result, "status", "Unassessed"
            ),
            "Evidence Quality (0-100)": quality["score"],
            "Evidence Score Status": quality["status"],
            "Accepted Graded Evidence": quality["evidence_count"],
            "AI Cybersecurity Risk (0-100)": risk["score"],
            "Cyber Risk Status": risk["status"],
            "Scored Active Risk Findings": risk["scored_findings"],
            "AI-use Classification": investigation.get(
                "status",
                "Not assessed",
            ),
        })
    return pd.DataFrame(rows, columns=columns)


def _format_workbook(buffer):
    """Apply readable formatting to the generated workbook."""
    buffer.seek(0)
    workbook = load_workbook(buffer)

    header_fill = PatternFill(fill_type="solid", fgColor="DCE6F1")

    for worksheet in workbook.worksheets:
        worksheet.freeze_panes = "A2"

        if worksheet.max_row >= 1 and worksheet.max_column >= 1:
            worksheet.auto_filter.ref = worksheet.dimensions

        for cell in worksheet[1]:
            cell.font = Font(bold=True, color="172B4D")
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="top", wrap_text=True)

        for column_cells in worksheet.columns:
            column_letter = get_column_letter(column_cells[0].column)
            max_length = 0

            for cell in list(column_cells)[:200]:
                if cell.value is not None:
                    max_length = max(max_length, min(len(str(cell.value)), 55))

            worksheet.column_dimensions[column_letter].width = min(
                max(max_length + 2, 12),
                45,
            )

        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def build_assessment_workbook():
    """Create a consolidated Excel workbook from current session data."""
    sheets = {}

    inventory = st.session_state.get("inventory_df")
    evidence = st.session_state.get("evidence_records", [])
    reviews = st.session_state.get("review_log", [])
    findings = st.session_state.get("risk_findings", [])
    collection_log = st.session_state.get("collection_log", [])
    assessments = st.session_state.get("criticality_ratings", {})
    investigations = st.session_state.get("investigation_assessments", {})
    relationships = st.session_state.get("relationship_records", [])

    # Include each sheet consistently, even when a section has no records.
    if isinstance(inventory, pd.DataFrame):
        sheets["Vendor Inventory"] = inventory.copy()
    else:
        sheets["Vendor Inventory"] = pd.DataFrame()

    sheets["Evidence Register"] = _records_to_dataframe(evidence)
    sheets["Review Log"] = _records_to_dataframe(reviews)
    sheets["Risk Findings"] = _records_to_dataframe(findings)
    sheets["Collection Log"] = _records_to_dataframe(collection_log)
    sheets["Criticality Assessments"] = _criticality_dataframe(assessments)
    sheets["AI Investigation Summary"] = _classification_dataframe(
        investigations
    )
    vendor_count = len(inventory) if isinstance(inventory, pd.DataFrame) else 0
    sheets["Assessment Overview"] = pd.DataFrame([
        {"Metric": "Vendor records", "Value": vendor_count},
        {"Metric": "Evidence records", "Value": len(evidence)},
        {"Metric": "Review decisions", "Value": len(reviews)},
        {"Metric": "Risk findings", "Value": len(findings)},
        {"Metric": "Collection attempts", "Value": len(collection_log)},
        {"Metric": "Criticality assessments", "Value": len(assessments)},
        {"Metric": "AI-use classifications", "Value": len(investigations)},
        {"Metric": "Recorded relationships", "Value": len(relationships)},
    ])
    sheets["Intelligence Mesh"] = _records_to_dataframe(
        relationship_records_for_display(relationships, evidence)
    )
    sheets["Vendor Scores"] = _vendor_scores_dataframe(
        inventory,
        assessments,
        investigations,
        evidence,
        findings,
    )

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet_name, dataframe in sheets.items():
            # Excel sheet names cannot exceed 31 characters.
            dataframe.to_excel(
                writer,
                sheet_name=sheet_name[:31],
                index=False,
            )

    return _format_workbook(buffer)


def show_report_export():
    """Render the consolidated report and export page."""
    st.title("Reports & Export")
    st.caption(
        "Generate a consolidated workbook from records in the current session."
    )

    inventory = st.session_state.get("inventory_df")
    evidence = st.session_state.get("evidence_records", [])
    reviews = st.session_state.get("review_log", [])
    findings = st.session_state.get("risk_findings", [])
    collection_log = st.session_state.get("collection_log", [])
    assessments = st.session_state.get("criticality_ratings", {})
    investigations = st.session_state.get("investigation_assessments", {})
    relationships = st.session_state.get("relationship_records", [])

    st.subheader("Assessment summary")

    metrics = [
        ("Vendors", len(inventory) if isinstance(inventory, pd.DataFrame) else 0),
        ("Evidence records", len(evidence)),
        ("Review decisions", len(reviews)),
        ("Risk findings", len(findings)),
        ("Collection attempts", len(collection_log)),
        ("Criticality assessments", len(assessments)),
        ("AI-use classifications", len(investigations)),
        ("Recorded relationships", len(relationships)),
    ]

    for start in range(0, len(metrics), 3):
        columns = st.columns(3)
        for column, (label, value) in zip(columns, metrics[start:start + 3]):
            with column:
                st.metric(label, value)

    st.divider()
    st.subheader("Consolidated assessment workbook")
    st.write(
        "The workbook includes the source inventory, evidence register, "
        "review log, risk findings, collection log, criticality assessments, "
        "AI investigation summary, Intelligence Mesh relationships, and an "
        "overview sheet. A Vendor Scores sheet keeps business criticality, "
        "evidence quality, and AI cybersecurity risk separate."
    )

    if st.button(
        "Prepare Excel workbook",
        type="primary",
        key="prepare_assessment_workbook",
    ):
        try:
            workbook = build_assessment_workbook()
            st.session_state["assessment_workbook_bytes"] = workbook.getvalue()
            st.success("The workbook is ready to download.")
        except Exception as exc:
            st.error(f"Could not prepare workbook: {exc}")

    workbook_bytes = st.session_state.get("assessment_workbook_bytes")

    if workbook_bytes:
        st.download_button(
            "Download consolidated Excel workbook",
            data=workbook_bytes,
            file_name="Project_BlindSpot_Assessment.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            key="download_assessment_workbook",
        )

    st.caption(
        "Exports contain records available in the current session. They do "
        "not prove every vendor or source has been assessed. Store the "
        "workbook securely because it may contain sensitive case-study data."
    )
>>>>>>> origin/main
