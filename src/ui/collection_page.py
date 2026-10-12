"""Public-page collection interface for Project BlindSpot."""

from datetime import datetime, timezone
from uuid import uuid4

import streamlit as st

from src.collection.fetcher import PublicPageFetcher
from src.collection.extractor import extract_evidence_candidates
from src.assessment.evidence import create_evidence_record


def _get(item, field, default=None):
    """Read a value from a dictionary or an object."""
    if isinstance(item, dict):
        return item.get(field, default)

    return getattr(item, field, default)


def _record_to_dict(record):
    """Convert an evidence record into a session-friendly dictionary."""
    grade = _get(record, "grade")

    if isinstance(grade, dict):
        grade_data = dict(grade)
    elif grade is not None:
        grade_data = {
            "score": _get(grade, "score"),
            "grade": _get(grade, "grade"),
            "source_authority": _get(grade, "source_authority"),
            "directness": _get(grade, "directness"),
            "service_relevance": _get(grade, "service_relevance"),
            "source_type": _get(grade, "source_type"),
            "recency": _get(grade, "recency"),
            "corroboration": _get(grade, "corroboration"),
            "rationale": _get(grade, "rationale"),
        }
    else:
        grade_data = None

    return {
        "evidence_id": _get(record, "evidence_id", ""),
        "vendor_id": _get(record, "vendor_id", ""),
        "vendor_name": _get(record, "vendor_name", ""),
        "source_url": _get(record, "source_url", ""),
        "source_title": _get(record, "source_title", ""),
        "excerpt": _get(record, "excerpt", ""),
        "matched_terms": _get(record, "matched_terms", []),
        "signal_types": _get(record, "signal_types", []),
        "classification_note": _get(record, "classification_note", ""),
        "retrieved_at": _get(record, "retrieved_at", ""),
        "data_origin": _get(record, "data_origin", ""),
        "discovery_method": _get(record, "discovery_method", ""),
        "run_id": _get(record, "run_id", ""),
        "review_status": _get(record, "review_status", "Needs review"),
        "review_reason": _get(record, "review_reason", ""),
        "reviewer": _get(record, "reviewer", ""),
        "review_notes": _get(record, "review_notes", ""),
        "reviewed_at": _get(record, "reviewed_at", ""),
        "grade": grade_data,
    }


def merge_evidence_records(existing_records, new_records):
    """Merge by vendor and stable ID, keeping the reviewed copy authoritative."""
    merged = []
    seen = set()
    added_count = 0
    duplicate_count = 0

    for record in existing_records:
        normalized = _record_to_dict(record)
        evidence_id = str(normalized.get("evidence_id", "")).strip()
        if not evidence_id:
            merged.append(normalized)
            continue

        key = (str(normalized.get("vendor_id", "")), evidence_id)
        if key not in seen:
            seen.add(key)
            merged.append(normalized)

    for record in new_records:
        normalized = _record_to_dict(record)
        evidence_id = str(normalized.get("evidence_id", "")).strip()
        if not evidence_id:
            continue

        key = (str(normalized.get("vendor_id", "")), evidence_id)
        if key in seen:
            duplicate_count += 1
            continue

        seen.add(key)
        merged.append(normalized)
        added_count += 1

    return merged, added_count, duplicate_count


def show_collection_page():
    """Render the public-page collection interface."""

    st.title("Public Evidence Collection")
    st.caption(
        "Fetch permitted public web pages, identify AI-related passages, "
        "and prepare evidence for human review."
    )

    inventory = st.session_state.get("inventory_df")
    if not isinstance(inventory, pd.DataFrame) or inventory.empty:
        st.info("Load the vendor inventory before collecting public evidence.")
        return

    vendor_id = st.session_state.get("investigation_vendor_id")
    vendor_name = st.session_state.get("investigation_vendor_name")

    discovered_sources = st.session_state.get("discovered_sources", {})
    source_records = discovered_sources.get(vendor_id, [])

    if not vendor_id or not vendor_name:
        st.info(
            "Open AI Investigation, select a vendor, and prepare its "
            "source list before collecting pages."
        )
        return

    st.markdown(f"**Vendor:** {vendor_name}")
    st.markdown(f"**Vendor ID:** {vendor_id}")

    if not source_records:
        st.info("No prepared source URLs were found for this vendor.")
        return

    st.subheader("Sources available for collection")

    st.dataframe(
        source_records,
        use_container_width=True,
        hide_index=True,
    )

    st.warning(
        "Collection is limited to permitted public pages. The fetcher "
        "must respect robots.txt, request limits, and access restrictions. "
        "Do not bypass authentication, CAPTCHAs, or paywalls."
    )

    max_pages = st.slider(
        "Maximum pages to attempt",
        min_value=1,
        max_value=20,
        value=min(5, len(source_records)),
    )

    if st.button(
        "Collect public evidence",
        type="primary",
        key="collect_public_evidence",
    ):
        fetcher = PublicPageFetcher()

        new_evidence = []
        collection_log = []
        run_id = f"COLLECT-{uuid4().hex[:12].upper()}"

        with st.spinner("Checking the prepared public sources..."):
            for source in source_records[:max_pages]:
                url = (
                    source.get("url")
                    or source.get("normalized_url")
                    or source.get("source_url")
                )

                if not url:
                    collection_log.append({
                        "run_id": run_id,
                        "vendor_id": vendor_id,
                        "vendor_name": vendor_name,
                        "source_url": "",
                        "status": "Skipped",
                        "details": "Source record contains no URL.",
                        "checked_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                    })
                    continue

                try:
                    result = fetcher.fetch_page(url)
                    result_status = str(
                        _get(result, "status", "failed")
                    ).lower()
                    success = result_status == "success"
                    status_code = _get(result, "http_status")
                    error = _get(result, "error_message", "")

                    collection_log.append({
                        "run_id": run_id,
                        "vendor_id": vendor_id,
                        "vendor_name": vendor_name,
                        "source_url": url,
                        "status": result_status,
                        "status_code": status_code,
                        "error_category": _get(
                            result, "error_category", ""
                        ),
                        "details": error or (
                            "Page retrieved." if success
                            else "Page could not be retrieved."
                        ),
                        "checked_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                    })

                    if not success:
                        continue

                    candidates = extract_evidence_candidates(result)

                    for candidate in candidates:
                        evidence_record = create_evidence_record(
                            candidate=candidate,
                            vendor_id=vendor_id,
                            vendor_name=vendor_name,
                            source_type="indirect_technical_signal",
                        )
                        evidence_data = _record_to_dict(evidence_record)
                        evidence_data["data_origin"] = "live_public_web"
                        evidence_data["run_id"] = run_id
                        evidence_data["discovery_method"] = source.get(
                            "discovery_method",
                            "prepared_inventory_or_analyst_url",
                        )
                        new_evidence.append(evidence_data)

                except Exception as exc:
                    collection_log.append({
                        "run_id": run_id,
                        "vendor_id": vendor_id,
                        "vendor_name": vendor_name,
                        "source_url": url,
                        "status": "failed",
                        "details": (
                            f"Collection failed ({type(exc).__name__}). "
                            "Verify the URL and retry later."
                        ),
                        "checked_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                    })

        # Merge newly collected evidence without overwriting existing reviews.
        existing_records = st.session_state.setdefault(
            "evidence_records", []
        )

        merged_records, added_count, duplicate_count = merge_evidence_records(
            existing_records,
            new_evidence,
        )
        st.session_state["evidence_records"] = merged_records

        fetcher.close()

        if added_count:
            st.session_state.get(
                "investigation_assessments", {}
            ).pop(vendor_id, None)
            st.session_state["assessment_workbook_bytes"] = None

        st.info(
            f"Collection complete: {added_count} new record(s) added; "
            f"{duplicate_count} duplicate record(s) skipped."
        )

        previous_log = list(
            st.session_state.get("collection_log", [])
        )
        st.session_state["collection_log"] = (
            previous_log + collection_log
        )

        st.session_state["last_collection_summary"] = {
            "run_id": run_id,
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "pages_attempted": min(max_pages, len(source_records)),
            "pages_fetched": sum(
                1 for item in collection_log
                if item["status"] == "success"
            ),
            "evidence_added": added_count,
        }

    summary = st.session_state.get("last_collection_summary")

    if summary and summary.get("vendor_id") == vendor_id:
        st.subheader("Latest collection summary")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Pages attempted",
                summary["pages_attempted"],
            )

        with col2:
            st.metric(
                "Pages fetched",
                summary["pages_fetched"],
            )

        with col3:
            st.metric(
                "New evidence records",
                summary["evidence_added"],
            )

    st.divider()
    st.subheader("Collection log")

    log = [
        item
        for item in st.session_state.get("collection_log", [])
        if item.get("vendor_id") == vendor_id
    ]

    if log:
        import pandas as pd

        log_df = pd.DataFrame(log)

        st.dataframe(
            log_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Export collection log",
            data=log_df.to_csv(index=False).encode("utf-8"),
            file_name=f"blindspot_collection_{vendor_id}.csv",
            mime="text/csv",
        )
    else:
        st.caption(
            "No collection attempts have been recorded for this vendor."
        )