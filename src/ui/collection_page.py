"""Public-page collection interface for Project BlindSpot."""

from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd
import streamlit as st

from src.assessment.evidence import create_evidence_record
from src.collection.discovery import (
    candidates_as_records,
    discover_sources,
    normalize_url,
)
from src.collection.extractor import extract_evidence_candidates
from src.collection.fetcher import PublicPageFetcher
from src.collection.investigation import prepare_investigation_candidates
from src.io.validation import duplicate_vendor_ids


def _get(item, field, default=None):
    """Read a value from a dictionary or an object."""
    if isinstance(item, dict):
        return item.get(field, default)

    return getattr(item, field, default)


def _get_vendor_columns(df):
    """Identify useful vendor columns without assuming optional fields."""
    columns = list(df.columns)

    name_col = "Vendor Name" if "Vendor Name" in columns else None
    id_col = "Vendor ID" if "Vendor ID" in columns else None

    url_candidates = [
        column
        for column in columns
        if any(
            word in str(column).lower()
            for word in ["url", "website", "domain", "web address"]
        )
    ]

    return name_col, id_col, url_candidates


def _determine_source_type(source, url):
    """Determine the source type from candidate category and URL."""
    url_lower = str(url or "").casefold()
    category = str(_get(source, "category", "") or "").casefold()
    if category == "engineering_and_jobs" and any(
        term in url_lower for term in ("career", "job", "hiring")
    ):
        return "relevant_technical_job_posting"
    if category == "product_documentation" or any(
        term in url_lower for term in ("docs", "documentation", "api", "developer")
    ):
        return "official_product_documentation"
    if any(
        term in url_lower for term in ("blog", "news", "research", "engineering")
    ):
        return "official_technical_announcement"
    if "github.com" in url_lower:
        return "developer_reference"
    return "indirect_technical_signal"


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

    name_col, id_col, url_candidates = _get_vendor_columns(inventory)
    if not name_col or not id_col:
        st.error(
            "The inventory must contain Vendor ID and Vendor Name columns."
        )
        return

    if duplicate_vendor_ids(inventory):
        st.error(
            "Resolve duplicate Vendor IDs in the inventory before "
            "collecting public evidence."
        )
        return

    vendor_options = {}
    for index, row in inventory.iterrows():
        raw_id = row.get(id_col)
        raw_name = row.get(name_col)
        if pd.isna(raw_id) or not str(raw_id).strip():
            continue
        if pd.isna(raw_name) or not str(raw_name).strip():
            continue
        v_id = str(raw_id).strip()
        v_name = str(raw_name).strip()
        if v_id.casefold() == "nan" or v_name.casefold() == "nan":
            continue
        label = f"{v_name} ({v_id})"
        vendor_options[label] = (v_id, v_name, row)

    if not vendor_options:
        st.info("No vendor with a usable Vendor ID is available to investigate.")
        return

    current_vendor_id = st.session_state.get("investigation_vendor_id")
    option_keys = list(vendor_options.keys())
    default_idx = 0
    if current_vendor_id:
        for i, key in enumerate(option_keys):
            if vendor_options[key][0] == str(current_vendor_id).strip():
                default_idx = i
                break

    selected_label = st.selectbox(
        "Select vendor to investigate",
        option_keys,
        index=default_idx,
        key="collection_vendor_selector",
    )

    vendor_id, vendor_name, vendor_row = vendor_options[selected_label]
    st.session_state["investigation_vendor_id"] = vendor_id
    st.session_state["investigation_vendor_name"] = vendor_name

    col_meta1, col_meta2 = st.columns(2)
    with col_meta1:
        st.markdown(f"**Vendor:** {vendor_name}")
    with col_meta2:
        st.markdown(f"**Vendor ID:** {vendor_id}")

    # Discover seed URLs from inventory columns
    seed_urls = []
    for col in url_candidates:
        val = vendor_row.get(col)
        if pd.notna(val) and str(val).strip():
            val_clean = str(val).strip()
            if val_clean and val_clean not in seed_urls:
                seed_urls.append(val_clean)

    discovered_sources = st.session_state.setdefault("discovered_sources", {})
    source_records = discovered_sources.get(vendor_id, [])

    # Auto-prepare candidate sources from inventory URLs if not yet prepared
    if not source_records and seed_urls:
        candidates = discover_sources(
            vendor_name=vendor_name,
            supplied_urls=seed_urls,
        )
        source_records = candidates_as_records(candidates)
        discovered_sources[vendor_id] = source_records
        st.session_state["discovered_sources"] = discovered_sources

    # Manage / expand source URLs
    with st.expander("Manage source URLs for this vendor", expanded=not source_records):
        st.caption(
            "Add public website URLs or discover common candidate paths."
        )
        if seed_urls:
            st.write(f"**Inventory website URL(s):** {', '.join(seed_urls)}")

        manual_urls = st.text_area(
            "Additional public URLs (one per line)",
            placeholder="https://vendor.example/security\nhttps://vendor.example/docs",
            key=f"collection_manual_urls_{vendor_id}",
        )
        include_common_paths = st.checkbox(
            "Include common public paths (e.g. /product, /docs, /careers, /security)",
            value=False,
            key=f"collection_common_paths_{vendor_id}",
        )

        if st.button("Update candidate sources", key=f"update_sources_{vendor_id}"):
            all_seeds = list(seed_urls)
            for line in manual_urls.splitlines():
                if line.strip():
                    all_seeds.append(line.strip())

            if include_common_paths:
                candidates = prepare_investigation_candidates(
                    vendor_name=vendor_name,
                    seed_urls=all_seeds,
                )
                source_records = candidates
            else:
                candidates = discover_sources(
                    vendor_name=vendor_name,
                    supplied_urls=all_seeds,
                )
                source_records = candidates_as_records(candidates)

            discovered_sources[vendor_id] = source_records
            st.session_state["discovered_sources"] = discovered_sources
            st.success(
                f"Updated candidate sources: {len(source_records)} URL(s) prepared."
            )
            st.rerun()

    if not source_records:
        st.warning(
            "No prepared source URLs were found for this vendor. "
            "Add a public URL above to begin evidence collection."
        )
        return

    st.subheader("Sources available for collection")
    st.dataframe(
        pd.DataFrame(source_records),
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
        max_value=max(2, min(30, len(source_records))),
        value=min(5, max(1, len(source_records))),
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

        targets = source_records[:max_pages]
        total_targets = len(targets)

        status_container = st.status(
            "Checking the prepared public sources...",
            expanded=True,
        )
        progress_bar = st.progress(0)

        for idx, source in enumerate(targets):
            raw_url = (
                source.get("url")
                if isinstance(source, dict)
                else getattr(source, "url", None)
            ) or (
                source.get("normalized_url")
                if isinstance(source, dict)
                else getattr(source, "normalized_url", None)
            ) or (
                source.get("source_url")
                if isinstance(source, dict)
                else getattr(source, "source_url", None)
            )

            progress_bar.progress(
                (idx + 1) / total_targets,
                text=f"Checking source {idx + 1} of {total_targets}...",
            )

            if not raw_url:
                collection_log.append({
                    "run_id": run_id,
                    "vendor_id": vendor_id,
                    "vendor_name": vendor_name,
                    "source_url": "",
                    "status": "Skipped",
                    "details": "Source record contains no URL.",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                })
                continue

            url = normalize_url(str(raw_url).strip()) or str(raw_url).strip()
            status_container.write(f"Fetching: `{url}`")

            try:
                result = fetcher.fetch_page(url)
                result_status = str(_get(result, "status", "failed")).lower()
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
                    "error_category": _get(result, "error_category", ""),
                    "details": error or (
                        "Page retrieved." if success
                        else "Page could not be retrieved."
                    ),
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                })

                if not success:
                    status_container.write(
                        f"⚠️ `{url}`: {result_status} ({error or 'no response'})"
                    )
                    continue

                candidates = extract_evidence_candidates(result)
                source_type = _determine_source_type(source, url)

                for candidate in candidates:
                    evidence_record = create_evidence_record(
                        candidate=candidate,
                        vendor_id=vendor_id,
                        vendor_name=vendor_name,
                        source_type=source_type,
                    )
                    evidence_data = _record_to_dict(evidence_record)
                    evidence_data["data_origin"] = "live_public_web"
                    evidence_data["run_id"] = run_id
                    discovery_method = (
                        source.get("discovery_method")
                        if isinstance(source, dict)
                        else getattr(source, "discovery_method", None)
                    ) or "prepared_inventory_or_analyst_url"
                    evidence_data["discovery_method"] = discovery_method
                    new_evidence.append(evidence_data)

                status_container.write(
                    f"✅ `{url}`: retrieved, found {len(candidates)} candidate passage(s)"
                )

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
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                })
                status_container.write(f"❌ `{url}`: error {type(exc).__name__}")

        status_container.update(
            label="Public evidence collection finished.",
            state="complete",
            expanded=False,
        )

        # Merge newly collected evidence without overwriting existing reviews.
        existing_records = st.session_state.setdefault("evidence_records", [])

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

        st.success(
            f"Collection complete: {added_count} new record(s) added; "
            f"{duplicate_count} duplicate record(s) skipped."
        )

        previous_log = list(st.session_state.get("collection_log", []))
        st.session_state["collection_log"] = previous_log + collection_log

        st.session_state["last_collection_summary"] = {
            "run_id": run_id,
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "pages_attempted": total_targets,
            "pages_fetched": sum(
                1 for item in collection_log if item["status"] == "success"
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

    # Display collected evidence records for this vendor
    all_evidence = st.session_state.get("evidence_records", [])
    vendor_evidence = [
        item for item in all_evidence
        if str(_get(item, "vendor_id", "")) == vendor_id
    ]

    st.subheader(f"Collected Evidence Records ({len(vendor_evidence)})")
    if vendor_evidence:
        evidence_display_rows = []
        for item in vendor_evidence:
            record_dict = _record_to_dict(item)
            grade = record_dict.get("grade") or {}
            score_val = (
                grade.get("score") if isinstance(grade, dict) else "Unassessed"
            )
            evidence_display_rows.append({
                "Evidence ID": record_dict.get("evidence_id"),
                "Source URL": record_dict.get("source_url"),
                "Excerpt": record_dict.get("excerpt", "")[:150] + (
                    "..." if len(record_dict.get("excerpt", "")) > 150 else ""
                ),
                "Signal Types": ", ".join(record_dict.get("signal_types", [])),
                "Matched Terms": ", ".join(record_dict.get("matched_terms", [])),
                "Review Status": record_dict.get("review_status", "Needs review"),
                "Score": score_val if score_val is not None else "Unassessed",
            })

        st.dataframe(
            pd.DataFrame(evidence_display_rows),
            use_container_width=True,
            hide_index=True,
        )
        st.info(
            "Go to the **Evidence Review Centre** to review excerpts, assign "
            "rationale, and grade evidence quality."
        )
    else:
        st.caption(
            "No evidence records have been collected or recorded for this vendor yet."
        )

    st.divider()
    st.subheader("Collection log")

    log = [
        item
        for item in st.session_state.get("collection_log", [])
        if item.get("vendor_id") == vendor_id
    ]

    if log:
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