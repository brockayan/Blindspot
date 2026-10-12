<<<<<<< HEAD
"""AI Investigation page for Project BlindSpot."""

import pandas as pd
import streamlit as st

from src.collection.discovery import (
    discover_sources,
    candidates_as_records,
)
from src.io.validation import duplicate_vendor_ids


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


def show_ai_investigation():
    """Render the vendor AI investigation workspace."""
    st.title("AI Investigation")
    st.caption(
        "Prepare vendor-specific public-source investigations and "
        "maintain a transparent record of discovery."
    )

    inventory = st.session_state.get("inventory_df")

    if not isinstance(inventory, pd.DataFrame) or inventory.empty:
        st.info(
            "Load the vendor inventory first from the Vendor Inventory page."
        )
        return

    name_col, id_col, url_candidates = _get_vendor_columns(inventory)

    if not name_col or not id_col:
        st.error(
            "The inventory must contain Vendor ID and Vendor Name columns."
        )
        return
    duplicate_ids = duplicate_vendor_ids(inventory)
    if duplicate_ids:
        st.error(
            "Resolve duplicate Vendor IDs in the inventory before "
            "starting vendor investigations."
        )
        return

    vendor_options = {}

    for index, row in inventory.iterrows():
        if pd.isna(row.get(id_col)) or not str(row.get(id_col)).strip():
            continue
        if pd.isna(row.get(name_col)) or not str(row.get(name_col)).strip():
            continue
        vendor_id = str(row.get(id_col, "")).strip()
        vendor_name = str(row.get(name_col, "")).strip()
        label = f"{vendor_name} ({vendor_id})"
        vendor_options[label] = index

    if not vendor_options:
        st.info("No vendor with a usable Vendor ID is available to investigate.")
        return

    selected_label = st.selectbox(
        "Select vendor to investigate",
        list(vendor_options.keys()),
        key="investigation_vendor",
    )

    vendor = inventory.loc[vendor_options[selected_label]]
    vendor_id = str(vendor.get(id_col, "")).strip()
    vendor_name = str(vendor.get(name_col, "")).strip()

    st.subheader("Vendor profile")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Vendor name**")
        st.write(vendor_name)

    with col2:
        st.write("**Vendor ID**")
        st.write(vendor_id)

    st.divider()
    st.subheader("Source discovery")

    st.markdown(
        """
        Add public URLs that may contain evidence of AI use. The discovery
        module normalises and categorises supplied URLs; it does not
        independently search the internet.
        """
    )

    supplied_url = ""

    if url_candidates:
        selected_url_column = st.selectbox(
            "Website or URL column",
            ["None"] + url_candidates,
            key="investigation_url_column",
        )

        if selected_url_column != "None":
            supplied_url = str(
                vendor.get(selected_url_column, "") or ""
            ).strip()

    if supplied_url:
        st.caption(f"URL from inventory: {supplied_url}")

    manual_urls = st.text_area(
        "Additional public URLs",
        placeholder=(
            "Enter one URL per line, for example:\n"
            "https://vendor.example/product\n"
            "https://vendor.example/security"
        ),
        key="manual_investigation_urls",
    )

    if st.button(
        "Prepare source list",
        type="primary",
        key="prepare_sources",
    ):
        supplied_urls = []

        if supplied_url:
            supplied_urls.append(supplied_url)

        supplied_urls.extend(
            line.strip()
            for line in manual_urls.splitlines()
            if line.strip()
        )

        try:
            candidates = discover_sources(
                vendor_name=vendor_name,
                supplied_urls=supplied_urls,
            )

            candidate_records = candidates_as_records(candidates)

            # Preserve sources discovered for other vendors.
            all_discovered_sources = st.session_state.setdefault(
                "discovered_sources",
                {},
            )

            # Update only the selected vendor's source list.
            all_discovered_sources[str(vendor_id)] = candidate_records

            st.session_state["discovered_sources"] = (
                all_discovered_sources
            )

            st.session_state["investigation_vendor_id"] = vendor_id
            st.session_state["investigation_vendor_name"] = vendor_name

            st.success(
                f"Prepared {len(candidate_records)} source candidate(s)."
            )

        except Exception as exc:
            st.error(f"Could not prepare source list: {exc}")

    st.divider()
    st.subheader("Prepared sources")

    discovered = st.session_state.get("discovered_sources", {})
    source_records = discovered.get(vendor_id, [])

    if not source_records:
        st.info(
            "No source list has been prepared for this vendor yet."
        )
        return

    source_df = pd.DataFrame(source_records)

    if not source_df.empty:
        st.dataframe(
            source_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Export source list",
            data=source_df.to_csv(index=False).encode("utf-8"),
            file_name=f"blindspot_sources_{vendor_id}.csv",
            mime="text/csv",
        )

    st.warning(
        "These are candidate sources only. No pages have been fetched "
        "or verified by this page. Do not interpret a prepared source "
        "list as evidence that the vendor uses AI."
=======
"""AI Investigation page for Project BlindSpot."""

import pandas as pd
import streamlit as st

from src.collection.discovery import (
    discover_sources,
    candidates_as_records,
)
from src.io.validation import duplicate_vendor_ids


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


def show_ai_investigation():
    """Render the vendor AI investigation workspace."""
    st.title("AI Investigation")
    st.caption(
        "Prepare vendor-specific public-source investigations and "
        "maintain a transparent record of discovery."
    )

    inventory = st.session_state.get("inventory_df")

    if not isinstance(inventory, pd.DataFrame) or inventory.empty:
        st.info(
            "Load the vendor inventory first from the Vendor Inventory page."
        )
        return

    name_col, id_col, url_candidates = _get_vendor_columns(inventory)

    if not name_col or not id_col:
        st.error(
            "The inventory must contain Vendor ID and Vendor Name columns."
        )
        return
    duplicate_ids = duplicate_vendor_ids(inventory)
    if duplicate_ids:
        st.error(
            "Resolve duplicate Vendor IDs in the inventory before "
            "starting vendor investigations."
        )
        return

    vendor_options = {}

    for index, row in inventory.iterrows():
        if pd.isna(row.get(id_col)) or not str(row.get(id_col)).strip():
            continue
        if pd.isna(row.get(name_col)) or not str(row.get(name_col)).strip():
            continue
        vendor_id = str(row.get(id_col, "")).strip()
        vendor_name = str(row.get(name_col, "")).strip()
        label = f"{vendor_name} ({vendor_id})"
        vendor_options[label] = index

    if not vendor_options:
        st.info("No vendor with a usable Vendor ID is available to investigate.")
        return

    selected_label = st.selectbox(
        "Select vendor to investigate",
        list(vendor_options.keys()),
        key="investigation_vendor",
    )

    vendor = inventory.loc[vendor_options[selected_label]]
    vendor_id = str(vendor.get(id_col, "")).strip()
    vendor_name = str(vendor.get(name_col, "")).strip()

    st.subheader("Vendor profile")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Vendor name**")
        st.write(vendor_name)

    with col2:
        st.write("**Vendor ID**")
        st.write(vendor_id)

    st.divider()
    st.subheader("Source discovery")

    st.markdown(
        """
        Add public URLs that may contain evidence of AI use. The discovery
        module normalises and categorises supplied URLs; it does not
        independently search the internet.
        """
    )

    supplied_url = ""

    if url_candidates:
        selected_url_column = st.selectbox(
            "Website or URL column",
            ["None"] + url_candidates,
            key="investigation_url_column",
        )

        if selected_url_column != "None":
            supplied_url = str(
                vendor.get(selected_url_column, "") or ""
            ).strip()

    if supplied_url:
        st.caption(f"URL from inventory: {supplied_url}")

    manual_urls = st.text_area(
        "Additional public URLs",
        placeholder=(
            "Enter one URL per line, for example:\n"
            "https://vendor.example/product\n"
            "https://vendor.example/security"
        ),
        key="manual_investigation_urls",
    )

    if st.button(
        "Prepare source list",
        type="primary",
        key="prepare_sources",
    ):
        supplied_urls = []

        if supplied_url:
            supplied_urls.append(supplied_url)

        supplied_urls.extend(
            line.strip()
            for line in manual_urls.splitlines()
            if line.strip()
        )

        try:
            candidates = discover_sources(
                vendor_name=vendor_name,
                supplied_urls=supplied_urls,
            )

            candidate_records = candidates_as_records(candidates)

            # Preserve sources discovered for other vendors.
            all_discovered_sources = st.session_state.setdefault(
                "discovered_sources",
                {},
            )

            # Update only the selected vendor's source list.
            all_discovered_sources[str(vendor_id)] = candidate_records

            st.session_state["discovered_sources"] = (
                all_discovered_sources
            )

            st.session_state["investigation_vendor_id"] = vendor_id
            st.session_state["investigation_vendor_name"] = vendor_name

            st.success(
                f"Prepared {len(candidate_records)} source candidate(s)."
            )

        except Exception as exc:
            st.error(f"Could not prepare source list: {exc}")

    st.divider()
    st.subheader("Prepared sources")

    discovered = st.session_state.get("discovered_sources", {})
    source_records = discovered.get(vendor_id, [])

    if not source_records:
        st.info(
            "No source list has been prepared for this vendor yet."
        )
        return

    source_df = pd.DataFrame(source_records)

    if not source_df.empty:
        st.dataframe(
            source_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Export source list",
            data=source_df.to_csv(index=False).encode("utf-8"),
            file_name=f"blindspot_sources_{vendor_id}.csv",
            mime="text/csv",
        )

    st.warning(
        "These are candidate sources only. No pages have been fetched "
        "or verified by this page. Do not interpret a prepared source "
        "list as evidence that the vendor uses AI."
>>>>>>> origin/main
    )