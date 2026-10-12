<<<<<<< HEAD

import pandas as pd
import streamlit as st

from src.assessment.evidence import grade_evidence
from src.assessment.review import (
    VALID_DECISIONS,
    REVIEW_REASONS,
    review_evidence,
    apply_review_status,
    review_as_record,
)


SOURCE_TYPES = {
    "Official product documentation": "official_product_documentation",
    "Official technical announcement": "official_technical_announcement",
    "Relevant technical job posting": "relevant_technical_job_posting",
    "Developer reference": "developer_reference",
    "Indirect technical signal": "indirect_technical_signal",
    "Generic marketing": "generic_marketing",
}

DIRECTNESS_OPTIONS = ["direct", "indirect", "unclear"]
RELEVANCE_OPTIONS = ["relevant", "not_relevant", "unclear"]
RECENCY_OPTIONS = ["current", "dated", "unknown"]
CORROBORATION_OPTIONS = ["independent", "not_corroborated", "unknown"]


def _get(record, key, default=None):
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _evidence_dict(record):
    if isinstance(record, dict):
        return record
    return {
        "evidence_id": _get(record, "evidence_id", ""),
        "vendor_id": _get(record, "vendor_id", ""),
        "vendor_name": _get(record, "vendor_name", ""),
        "source_url": _get(record, "source_url", ""),
        "excerpt": _get(record, "excerpt", ""),
        "review_status": _get(record, "review_status", "Needs review"),
        "grade": {},
    }


def show_review_centre():
    st.title("Evidence Review Centre")
    st.caption(
        "Review public evidence, record your rationale, and grade "
        "source quality before using it in vendor AI assessments."
    )

    evidence_records = st.session_state.setdefault(
        "evidence_records", []
    )
    review_log = st.session_state.setdefault("review_log", [])

    if not evidence_records:
        st.info(
            "No evidence is available yet. Collect public evidence "
            "or add evidence records before reviewing."
        )
        return

    st.subheader("Review queue")

    rows = []
    for record in evidence_records:
        item = _evidence_dict(record)
        grade = item.get("grade") or {}

        rows.append({
            "Evidence ID": item.get("evidence_id", ""),
            "Vendor": item.get("vendor_name", ""),
            "Source URL": item.get("source_url", ""),
            "Review status": item.get("review_status", "Needs review"),
            "Evidence score": grade.get("score", "Not graded")
            if isinstance(grade, dict) else "Not graded",
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )

    evidence_ids = [
        str(_get(record, "evidence_id", f"Evidence {index + 1}"))
        for index, record in enumerate(evidence_records)
    ]

    selected_id = st.selectbox(
        "Select evidence to review",
        options=evidence_ids,
    )

    selected_index = evidence_ids.index(selected_id)
    original = _evidence_dict(evidence_records[selected_index])
    current_grade = original.get("grade") or {}

    if not isinstance(current_grade, dict):
        current_grade = {}

    if current_grade.get("rationale"):
        st.caption(f"Current grade rationale: {current_grade['rationale']}")

    st.markdown("### Evidence details")
    st.write("**Vendor:**", original.get("vendor_name", "Unknown"))
    st.write("**Source:**", original.get("source_url", "Not provided"))
    st.write("**Excerpt:**", original.get("excerpt", "No excerpt available"))

    if original.get("matched_terms"):
        st.write(
            "**Matched terms:**",
            ", ".join(original["matched_terms"]),
        )

    st.markdown("### Grade the evidence")

    existing_source_type = current_grade.get(
        "source_type", "indirect_technical_signal"
    )
    source_labels = list(SOURCE_TYPES.keys())
    default_source_label = next(
        (
            label for label, value in SOURCE_TYPES.items()
            if value == existing_source_type
        ),
        "Indirect technical signal",
    )

    with st.form("evidence_review_form"):
        source_label = st.selectbox(
            "Source type",
            source_labels,
            index=source_labels.index(default_source_label),
        )

        directness = st.selectbox(
            "How directly does the source establish AI use?",
            DIRECTNESS_OPTIONS,
            index=(
                DIRECTNESS_OPTIONS.index(current_grade["directness"])
                if current_grade.get("directness") in DIRECTNESS_OPTIONS
                else DIRECTNESS_OPTIONS.index("unclear")
            ),
        )

        service_relevance = st.selectbox(
            "Is the evidence relevant to the vendor's service?",
            RELEVANCE_OPTIONS,
            index=(
                RELEVANCE_OPTIONS.index(
                    current_grade["service_relevance"]
                )
                if current_grade.get("service_relevance")
                in RELEVANCE_OPTIONS
                else RELEVANCE_OPTIONS.index("unclear")
            ),
        )

        recency = st.selectbox(
            "Evidence recency",
            RECENCY_OPTIONS,
            index=(
                RECENCY_OPTIONS.index(current_grade["recency"])
                if current_grade.get("recency") in RECENCY_OPTIONS
                else RECENCY_OPTIONS.index("unknown")
            ),
        )

        corroboration = st.selectbox(
            "Corroboration",
            CORROBORATION_OPTIONS,
            index=(
                CORROBORATION_OPTIONS.index(
                    current_grade["corroboration"]
                )
                if current_grade.get("corroboration")
                in CORROBORATION_OPTIONS
                else CORROBORATION_OPTIONS.index("unknown")
            ),
        )

        decision = st.selectbox(
            "Review decision",
            sorted(VALID_DECISIONS),
            index=(
                sorted(VALID_DECISIONS).index(
                    original.get("review_status", "Needs review")
                )
                if original.get("review_status", "Needs review")
                in VALID_DECISIONS
                else sorted(VALID_DECISIONS).index("Needs review")
            ),
        )

        reason = st.selectbox(
            "Review reason",
            sorted(REVIEW_REASONS),
        )

        reviewer = st.text_input(
            "Reviewer",
        )

        notes = st.text_area(
            "Notes / justification",
            help="Required when rejecting evidence.",
        )

        submitted = st.form_submit_button("Save review")

    if submitted:
        source_type = SOURCE_TYPES[source_label]
        source_url = original.get("source_url", "")

        try:
            grade = grade_evidence(
                source_type=source_type,
                source_url=source_url,
                directness=directness,
                service_relevance=service_relevance,
                recency=recency,
                corroboration=corroboration,
            )

            grade_record = {
                "source_type": source_type,
                "directness": directness,
                "service_relevance": service_relevance,
                "recency": recency,
                "corroboration": corroboration,
                "score": _get(grade, "score", 0),
                "grade": _get(grade, "grade", "Unrated"),
                "source_authority": _get(
                    grade, "source_authority", "Unclassified"
                ),
                "rationale": _get(grade, "rationale", ""),
            }

            review = review_evidence(
                evidence=original,
                decision=decision,
                reviewer=reviewer.strip(),
                reason=reason,
                notes=notes.strip(),
            )

            updated = apply_review_status(original, review)
            updated["grade"] = grade_record

            evidence_records[selected_index] = updated
            review_log.append(review_as_record(review))

            st.session_state["evidence_records"] = evidence_records
            st.session_state["review_log"] = review_log
            vendor_id = original.get("vendor_id")
            st.session_state.get(
                "investigation_assessments", {}
            ).pop(vendor_id, None)
            st.session_state["assessment_workbook_bytes"] = None

            st.success(
                "Evidence grade and review decision saved."
            )
            st.rerun()

        except Exception as exc:
            st.error(f"Could not save the review: {exc}")

    st.subheader("Review history")

    if review_log:
        st.dataframe(
            pd.DataFrame(review_log),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No review decisions have been recorded yet.")
=======

import pandas as pd
import streamlit as st

from src.assessment.evidence import grade_evidence
from src.assessment.review import (
    VALID_DECISIONS,
    REVIEW_REASONS,
    review_evidence,
    apply_review_status,
    review_as_record,
)


SOURCE_TYPES = {
    "Official product documentation": "official_product_documentation",
    "Official technical announcement": "official_technical_announcement",
    "Relevant technical job posting": "relevant_technical_job_posting",
    "Developer reference": "developer_reference",
    "Indirect technical signal": "indirect_technical_signal",
    "Generic marketing": "generic_marketing",
}

DIRECTNESS_OPTIONS = ["direct", "indirect", "unclear"]
RELEVANCE_OPTIONS = ["relevant", "not_relevant", "unclear"]
RECENCY_OPTIONS = ["current", "dated", "unknown"]
CORROBORATION_OPTIONS = ["independent", "not_corroborated", "unknown"]


def _get(record, key, default=None):
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _evidence_dict(record):
    if isinstance(record, dict):
        return record
    return {
        "evidence_id": _get(record, "evidence_id", ""),
        "vendor_id": _get(record, "vendor_id", ""),
        "vendor_name": _get(record, "vendor_name", ""),
        "source_url": _get(record, "source_url", ""),
        "excerpt": _get(record, "excerpt", ""),
        "review_status": _get(record, "review_status", "Needs review"),
        "grade": {},
    }


def show_review_centre():
    st.title("Evidence Review Centre")
    st.caption(
        "Review public evidence, record your rationale, and grade "
        "source quality before using it in vendor AI assessments."
    )

    evidence_records = st.session_state.setdefault(
        "evidence_records", []
    )
    review_log = st.session_state.setdefault("review_log", [])

    if not evidence_records:
        st.info(
            "No evidence is available yet. Collect public evidence "
            "or add evidence records before reviewing."
        )
        return

    st.subheader("Review queue")

    rows = []
    for record in evidence_records:
        item = _evidence_dict(record)
        grade = item.get("grade") or {}

        rows.append({
            "Evidence ID": item.get("evidence_id", ""),
            "Vendor": item.get("vendor_name", ""),
            "Source URL": item.get("source_url", ""),
            "Review status": item.get("review_status", "Needs review"),
            "Evidence score": grade.get("score", "Not graded")
            if isinstance(grade, dict) else "Not graded",
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )

    evidence_ids = [
        str(_get(record, "evidence_id", f"Evidence {index + 1}"))
        for index, record in enumerate(evidence_records)
    ]

    selected_id = st.selectbox(
        "Select evidence to review",
        options=evidence_ids,
    )

    selected_index = evidence_ids.index(selected_id)
    original = _evidence_dict(evidence_records[selected_index])
    current_grade = original.get("grade") or {}

    if not isinstance(current_grade, dict):
        current_grade = {}

    if current_grade.get("rationale"):
        st.caption(f"Current grade rationale: {current_grade['rationale']}")

    st.markdown("### Evidence details")
    st.write("**Vendor:**", original.get("vendor_name", "Unknown"))
    st.write("**Source:**", original.get("source_url", "Not provided"))
    st.write("**Excerpt:**", original.get("excerpt", "No excerpt available"))

    if original.get("matched_terms"):
        st.write(
            "**Matched terms:**",
            ", ".join(original["matched_terms"]),
        )

    st.markdown("### Grade the evidence")

    existing_source_type = current_grade.get(
        "source_type", "indirect_technical_signal"
    )
    source_labels = list(SOURCE_TYPES.keys())
    default_source_label = next(
        (
            label for label, value in SOURCE_TYPES.items()
            if value == existing_source_type
        ),
        "Indirect technical signal",
    )

    with st.form("evidence_review_form"):
        source_label = st.selectbox(
            "Source type",
            source_labels,
            index=source_labels.index(default_source_label),
        )

        directness = st.selectbox(
            "How directly does the source establish AI use?",
            DIRECTNESS_OPTIONS,
            index=(
                DIRECTNESS_OPTIONS.index(current_grade["directness"])
                if current_grade.get("directness") in DIRECTNESS_OPTIONS
                else DIRECTNESS_OPTIONS.index("unclear")
            ),
        )

        service_relevance = st.selectbox(
            "Is the evidence relevant to the vendor's service?",
            RELEVANCE_OPTIONS,
            index=(
                RELEVANCE_OPTIONS.index(
                    current_grade["service_relevance"]
                )
                if current_grade.get("service_relevance")
                in RELEVANCE_OPTIONS
                else RELEVANCE_OPTIONS.index("unclear")
            ),
        )

        recency = st.selectbox(
            "Evidence recency",
            RECENCY_OPTIONS,
            index=(
                RECENCY_OPTIONS.index(current_grade["recency"])
                if current_grade.get("recency") in RECENCY_OPTIONS
                else RECENCY_OPTIONS.index("unknown")
            ),
        )

        corroboration = st.selectbox(
            "Corroboration",
            CORROBORATION_OPTIONS,
            index=(
                CORROBORATION_OPTIONS.index(
                    current_grade["corroboration"]
                )
                if current_grade.get("corroboration")
                in CORROBORATION_OPTIONS
                else CORROBORATION_OPTIONS.index("unknown")
            ),
        )

        decision = st.selectbox(
            "Review decision",
            sorted(VALID_DECISIONS),
            index=(
                sorted(VALID_DECISIONS).index(
                    original.get("review_status", "Needs review")
                )
                if original.get("review_status", "Needs review")
                in VALID_DECISIONS
                else sorted(VALID_DECISIONS).index("Needs review")
            ),
        )

        reason = st.selectbox(
            "Review reason",
            sorted(REVIEW_REASONS),
        )

        reviewer = st.text_input(
            "Reviewer",
        )

        notes = st.text_area(
            "Notes / justification",
            help="Required when rejecting evidence.",
        )

        submitted = st.form_submit_button("Save review")

    if submitted:
        source_type = SOURCE_TYPES[source_label]
        source_url = original.get("source_url", "")

        try:
            grade = grade_evidence(
                source_type=source_type,
                source_url=source_url,
                directness=directness,
                service_relevance=service_relevance,
                recency=recency,
                corroboration=corroboration,
            )

            grade_record = {
                "source_type": source_type,
                "directness": directness,
                "service_relevance": service_relevance,
                "recency": recency,
                "corroboration": corroboration,
                "score": _get(grade, "score", 0),
                "grade": _get(grade, "grade", "Unrated"),
                "source_authority": _get(
                    grade, "source_authority", "Unclassified"
                ),
                "rationale": _get(grade, "rationale", ""),
            }

            review = review_evidence(
                evidence=original,
                decision=decision,
                reviewer=reviewer.strip(),
                reason=reason,
                notes=notes.strip(),
            )

            updated = apply_review_status(original, review)
            updated["grade"] = grade_record

            evidence_records[selected_index] = updated
            review_log.append(review_as_record(review))

            st.session_state["evidence_records"] = evidence_records
            st.session_state["review_log"] = review_log
            vendor_id = original.get("vendor_id")
            st.session_state.get(
                "investigation_assessments", {}
            ).pop(vendor_id, None)
            st.session_state["assessment_workbook_bytes"] = None

            st.success(
                "Evidence grade and review decision saved."
            )
            st.rerun()

        except Exception as exc:
            st.error(f"Could not save the review: {exc}")

    st.subheader("Review history")

    if review_log:
        st.dataframe(
            pd.DataFrame(review_log),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No review decisions have been recorded yet.")
>>>>>>> origin/main
