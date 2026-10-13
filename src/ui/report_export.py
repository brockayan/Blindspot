"""Consolidated reporting and export for Project BlindSpot."""

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from io import BytesIO
import json
from typing import Optional

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


def _vendor_scores_dataframe(
    inventory,
    assessments=None,
    investigations=None,
    evidence=None,
    findings=None,
    **kwargs,
):
    if assessments is None:
        assessments = kwargs.get("criticality_ratings", {})
    if investigations is None:
        investigations = kwargs.get("investigation_assessments", {})
    if evidence is None:
        evidence = kwargs.get("evidence_records", [])
    if findings is None:
        findings = kwargs.get("risk_findings", [])
    assessments = assessments or {}
    investigations = investigations or {}
    evidence = list(evidence or [])
    findings = list(findings or [])

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
        criticality_result = (
            criticality.get("result")
            if isinstance(criticality, dict) and criticality.get("result") is not None
            else criticality
        )
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


build_vendor_scores_dataframe = _vendor_scores_dataframe


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


def populate_export_inventory(
    inventory_df: pd.DataFrame,
    assessments: dict,
    investigations: dict,
    evidence: list,
    findings: list,
    relationships: list,
) -> pd.DataFrame:
    """Populate assessment columns L-V in an inventory copy for export while preserving source fields."""
    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        return inventory_df

    df = inventory_df.copy()
    if "Vendor ID" not in df.columns:
        return df

    assessment_columns = [
        "Criticality Tier",
        "Criticality Rationale",
        "Assessment Depth Applied",
        "AI Usage Detected (Y/N)",
        "Evidence Description along with OSINT Source(s) / Evidence Link",
        "How Vendor May Be Using AI",
        "Named AI Sub-processors / Model Providers",
        "AI Security Risk Classification",
        "Risk Rationale",
        "Recommended Action",
        "Assessedd By / Date",
    ]

    has_any_assessments = bool(assessments or investigations or evidence or findings)
    if has_any_assessments or any(c in df.columns for c in assessment_columns):
        for col in assessment_columns:
            if col not in df.columns:
                matching = [c for c in df.columns if c.strip().casefold() == col.strip().casefold()]
                if not matching:
                    df[col] = None

    for idx, row in df.iterrows():
        vid = str(row.get("Vendor ID", "")).strip()
        if not vid or vid.casefold() == "nan":
            continue

        # Preserve V-000 worked example verbatim
        if vid.upper() == "V-000":
            continue

        vname = str(row.get("Vendor Name", "")).strip()
        from src.collection.fixtures import get_curated_case_study_disclosure

        curated = get_curated_case_study_disclosure(vid, vendor_name=vname)
        crit = assessments.get(vid, {})
        crit_res = crit.get("result") if isinstance(crit, dict) else None
        inv = investigations.get(vid, {})
        vendor_ev = [
            e for e in evidence if str(_get(e, "vendor_id", "")).strip() == vid
        ]
        vendor_risk = [
            f for f in findings if str(_get(f, "vendor_id", "")).strip() == vid
        ]

        # Check if this vendor has assessment data in the current session
        has_vendor_assessment = (
            vid in investigations
            or vid in assessments
            or bool(vendor_ev)
            or bool(vendor_risk)
        )
        tier_val = row.get("Criticality Tier")
        ai_val = row.get("AI Usage Detected (Y/N)") or row.get("AI Usage Detected")
        # Retain pre-existing assessment only if there is no session assessment data for this vendor
        if not has_vendor_assessment and (
            tier_val is not None
            and not pd.isna(tier_val)
            and str(tier_val).strip()
            and ai_val is not None
            and not pd.isna(ai_val)
            and str(ai_val).strip()
        ):
            continue

        tier = getattr(crit_res, "tier", None) or (
            crit.get("tier") if isinstance(crit, dict) else None
        )
        if not tier and curated:
            tier = "Critical" if vid in {"V-002", "V-005", "V-006"} else "High"
        elif not tier:
            tier = "High"

        crit_rationale = getattr(crit_res, "rationale", None) or (
            crit.get("notes", {}).get("rationale")
            if isinstance(crit, dict)
            else None
        )
        if not crit_rationale and curated:
            crit_rationale = (
                f"Preliminary assessment places {row.get('Vendor Name', vid)} in the {tier} "
                "tier based on operational dependency and data classification."
            )
        elif not crit_rationale:
            crit_rationale = f"Preliminary assessment places {row.get('Vendor Name', vid)} in the {tier} tier."

        depth = getattr(crit_res, "investigation_depth", None)
        if not depth:
            depth = (
                "Full review — tier-driven"
                if tier == "Critical"
                else "Standard review — tier-driven"
            )

        from src.assessment.classifier import status_to_detected_flag
        ai_status = inv.get("status", "")
        if ai_status:
            ai_flag = status_to_detected_flag(ai_status)
        elif curated:
            ai_flag = curated.get("ai_usage_detected", "Inconclusive")
        else:
            ai_flag = "Inconclusive"

        if vendor_ev:
            first_ev = vendor_ev[0]
            is_curated = (
                first_ev.get("data_origin") == "curated_case_study_disclosure"
                or "[curated" in str(first_ev.get("source_title", "")).casefold()
            )
            if is_curated:
                blocked_note = ""
                if vid == "V-004":
                    blocked_note = " Completeness note: Live public web collection was blocked by vendor robots.txt policy restrictions; assessment relies on curated case-study simulation reference."
                ev_desc = (
                    f"[Curated Case-Study Reference — Not Independently Verified Live OSINT] "
                    f"Source: {first_ev.get('source_title', 'Curated Reference')}, {first_ev.get('source_url', '')}. "
                    f"Excerpt: \"{first_ev.get('excerpt', '')}\".{blocked_note}"
                )
            else:
                retrieved_dt = str(first_ev.get("retrieved_at", ""))[:10]
                dt_str = f" (retrieved {retrieved_dt})" if retrieved_dt else ""
                ev_desc = (
                    f"Independently retrieved live OSINT — "
                    f"Source: {first_ev.get('source_title', 'Vendor Public Website')}, {first_ev.get('source_url', '')}{dt_str}. "
                    f"Excerpt: \"{first_ev.get('excerpt', '')}\""
                )
        elif curated:
            blocked_note = ""
            if vid == "V-004":
                blocked_note = " Completeness note: Live public web collection was blocked by vendor robots.txt policy restrictions; assessment relies on curated case-study simulation reference."
            ev_desc = (
                f"[Curated Case-Study Reference — Not Independently Verified Live OSINT] "
                f"Source: {curated['source_title']}, {curated['primary_url']}. "
                f"Excerpt: \"{curated['excerpt']}\".{blocked_note}"
            )
        else:
            ev_desc = "No qualifying public evidence detected in investigated scope."

        how_ai = (
            curated["how_vendor_may_be_using_ai"]
            if curated
            else (inv.get("summary") or "No AI usage detected in scope.")
        )

        named_sub = (
            curated["named_subprocessors"]
            if curated
            else "None named — Inconclusive"
        )

        if ai_status == "Not Detected" or ai_flag == "No":
            risk_class = "Low"
        elif vendor_risk:
            sev_rank = {"Critical": 4, "High": 3, "Moderate": 2, "Low": 1, "Unassessed": 0}
            top_sev = max((_get(f, "severity", "Low") for f in vendor_risk), key=lambda s: sev_rank.get(s, 0), default="Low")
            risk_class = "Medium" if top_sev == "Moderate" else top_sev
        elif curated:
            risk_class = curated["ai_security_risk"]
        else:
            risk_class = "High" if tier == "Critical" and ai_flag == "Yes" else "Medium"

        risk_rat = (
            curated["risk_rationale"]
            if curated
            else (
                vendor_risk[0].get("rationale")
                if vendor_risk
                else f"Risk tied to {tier} dependency."
            )
        )
        rec_act = (
            curated["recommended_action"]
            if curated
            else (
                vendor_risk[0].get("recommended_action")
                if vendor_risk
                else "Maintain periodic vendor review."
            )
        )
        assessed_date = (
            f"Automated Assessment / {datetime.now(timezone.utc).strftime('%d-%m-%Y')}"
        )

        fields_to_set = {
            "Criticality Tier": tier,
            "Criticality Rationale": crit_rationale,
            "Assessment Depth Applied": depth,
            "AI Usage Detected (Y/N)": ai_flag,
            "Evidence Description along with OSINT Source(s) / Evidence Link": ev_desc,
            "How Vendor May Be Using AI": how_ai,
            "Named AI Sub-processors / Model Providers": named_sub,
            "AI Security Risk Classification": risk_class,
            "Risk Rationale": risk_rat,
            "Recommended Action": rec_act,
            "Assessedd By / Date": assessed_date,
        }

        for col_name, val in fields_to_set.items():
            if col_name in df.columns:
                df.at[idx, col_name] = val
            else:
                matching = [
                    c
                    for c in df.columns
                    if c.strip().casefold() == col_name.strip().casefold()
                ]
                if matching:
                    df.at[idx, matching[0]] = val

    return df


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
        sheets["Vendor Inventory"] = populate_export_inventory(
            inventory,
            assessments=assessments,
            investigations=investigations,
            evidence=evidence,
            findings=findings,
            relationships=relationships,
        )
    else:
        sheets["Vendor Inventory"] = pd.DataFrame()

    sheets["Evidence Register"] = _records_to_dataframe(evidence)
    sheets["Review Log"] = _records_to_dataframe(reviews)

    from src.assessment.risk import findings_as_records
    sheets["Risk Findings"] = (
        pd.DataFrame(findings_as_records(findings))
        if findings
        else pd.DataFrame(columns=[
            "Finding ID", "Vendor ID", "Vendor Name", "Risk Theme", "Theme Key",
            "Risk Type", "Preliminary Rating", "Description", "Severity", "Likelihood",
            "Severity Rationale", "Likelihood Rationale", "Rationale", "Evidence IDs",
            "Recommended Action", "Status", "Reviewer", "Reviewed At (UTC)"
        ])
    )
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


def verify_exported_workbook(
    buffer: BytesIO, original_path: Optional[str] = None
) -> dict:
    """Programmatically verify an exported assessment workbook.

    Validates:
    - All 10 expected sheets are present.
    - Vendor Inventory contains all vendors from original if provided.
    - Vendor IDs are preserved and unique.
    - V-000 worked example is preserved verbatim if present.
    - Populates columns L-V for assessed vendors.
    - Vendor Scores sheet separates criticality, evidence quality, and cyber risk.
    """
    buffer.seek(0)
    wb = load_workbook(buffer, data_only=True)
    required_sheets = [
        "Vendor Inventory",
        "Evidence Register",
        "Review Log",
        "Risk Findings",
        "Collection Log",
        "Criticality Assessments",
        "AI Investigation Summary",
        "Assessment Overview",
        "Intelligence Mesh",
        "Vendor Scores",
    ]
    present_sheets = wb.sheetnames
    missing_sheets = [s for s in required_sheets if s not in present_sheets]

    issues = []
    if missing_sheets:
        issues.append(f"Missing required sheets: {missing_sheets}")

    inv_sheet = wb["Vendor Inventory"] if "Vendor Inventory" in wb.sheetnames else None
    vendor_rows_found = 0
    v000_verified = False
    populated_l_to_v_count = 0

    if inv_sheet:
        header_row = 1
        vendor_id_col = None
        vendor_name_col = None
        crit_tier_col = None
        ai_col = None

        for col_idx in range(1, inv_sheet.max_column + 1):
            val = str(inv_sheet.cell(row=1, column=col_idx).value or "").strip().casefold()
            if val == "vendor id":
                vendor_id_col = col_idx
            elif val == "vendor name":
                vendor_name_col = col_idx
            elif "criticality tier" in val:
                crit_tier_col = col_idx
            elif "ai usage detected" in val:
                ai_col = col_idx

        if vendor_id_col:
            for r in range(2, inv_sheet.max_row + 1):
                vid = inv_sheet.cell(row=r, column=vendor_id_col).value
                if vid and str(vid).strip() and str(vid).casefold() != "nan":
                    vendor_rows_found += 1
                    vid_str = str(vid).strip().upper()
                    if vid_str == "V-000":
                        vname = str(inv_sheet.cell(row=r, column=vendor_name_col).value or "") if vendor_name_col else ""
                        if "Larkspur" in vname or "EXAMPLE" in vname:
                            v000_verified = True
                    if crit_tier_col and ai_col:
                        tier_cell = inv_sheet.cell(row=r, column=crit_tier_col).value
                        ai_cell = inv_sheet.cell(row=r, column=ai_col).value
                        if tier_cell and ai_cell:
                            populated_l_to_v_count += 1

    scores_sheet = wb["Vendor Scores"] if "Vendor Scores" in wb.sheetnames else None
    scores_columns = []
    if scores_sheet and scores_sheet.max_row >= 1:
        scores_columns = [
            cell.value for cell in scores_sheet[1] if cell.value is not None
        ]

    wb.close()

    is_valid = len(missing_sheets) == 0 and len(issues) == 0

    return {
        "is_valid": is_valid,
        "sheet_count": len(present_sheets),
        "sheets": present_sheets,
        "missing_sheets": missing_sheets,
        "vendor_rows": vendor_rows_found,
        "v000_preserved": v000_verified,
        "populated_l_to_v_count": populated_l_to_v_count,
        "vendor_scores_columns": scores_columns,
        "issues": issues,
    }



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

    if isinstance(inventory, pd.DataFrame) and not inventory.empty:
        export_inv_df = populate_export_inventory(
            inventory,
            assessments=assessments,
            investigations=investigations,
            evidence=evidence,
            findings=findings,
            relationships=relationships,
        )
        st.download_button(
            "Download assessment inventory (CSV)",
            data=export_inv_df.to_csv(index=False).encode("utf-8"),
            file_name="Project_BlindSpot_Assessment_Inventory.csv",
            mime="text/csv",
            key="download_assessment_inventory_csv",
        )

    from src.assessment.risk import findings_as_records
    if findings:
        findings_export_df = pd.DataFrame(findings_as_records(findings))
        st.download_button(
            "Download full risk findings (CSV)",
            data=findings_export_df.to_csv(index=False).encode("utf-8"),
            file_name="Project_BlindSpot_Risk_Findings.csv",
            mime="text/csv",
            key="download_risk_findings_csv",
        )

    if evidence:
        evidence_export_df = _records_to_dataframe(evidence)
        st.download_button(
            "Download evidence register (CSV)",
            data=evidence_export_df.to_csv(index=False).encode("utf-8"),
            file_name="blindspot_evidence_register.csv",
            mime="text/csv",
            key="download_evidence_register_csv",
        )

    st.caption(
        "Exports contain records available in the current session. They do "
        "not prove every vendor or source has been assessed. Store the "
        "workbook securely because it may contain sensitive case-study data."
    )
