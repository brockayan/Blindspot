"""Evidence-linked vendor relationship register and interactive graph."""

from hashlib import sha256
from urllib.parse import urlparse

import networkx as nx
import pandas as pd
import streamlit as st
from pyvis.network import Network

from src.io.validation import duplicate_vendor_ids


ENTITY_TYPES = (
    "AI Provider",
    "Subprocessor",
    "Cloud Provider",
    "Other Service",
)
RELATIONSHIP_TYPES = (
    "Uses AI service",
    "Uses cloud service",
    "Uses subprocessor",
    "Provides AI technology",
    "Other documented relationship",
)
VALID_STATUSES = (
    "Confirmed",
    "Suspected",
    "Needs review",
    "Hypothesis — needs review",
)


def _get(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _clean(value):
    return str(value or "").strip()


def _safe_public_source_url(url):
    """Validate a source URL for recording; collection applies stronger checks."""
    if not url:
        return ""

    try:
        parsed = urlparse(url.strip())
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Source URL must be a public HTTP(S) URL.")
        parsed.port
    except ValueError as exc:
        raise ValueError("Source URL must be a valid public HTTP(S) URL.") from exc

    return url.strip()


def _vendor_node_id(vendor_id):
    return f"vendor:{_clean(vendor_id).casefold()}"


def _entity_node_id(entity_type, name):
    normalized = f"{_clean(entity_type).casefold()}|{_clean(name).casefold()}"
    return "entity:" + sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _relationship_id(vendor_id, target_type, target_name, relationship_type):
    identity = "|".join(
        (
            _clean(vendor_id).casefold(),
            "vendor",
            _clean(target_type).casefold(),
            _clean(target_name).casefold(),
            _clean(relationship_type).casefold(),
        )
    )
    return "REL-" + sha256(identity.encode("utf-8")).hexdigest()[:12].upper()


def effective_relationship_status(record, evidence_records):
    """Never display a relationship as verified without accepted linked evidence."""
    requested = _clean(
        record.get("reviewer_status", record.get("status", "Needs review"))
    )
    if requested == "Hypothesis — needs review":
        return requested

    evidence_id = _clean(record.get("evidence_id"))
    vendor_id = _clean(record.get("vendor_id"))
    if not evidence_id or not vendor_id:
        return "Needs review"
    evidence = next(
        (
            item for item in evidence_records
            if _clean(_get(item, "evidence_id")) == evidence_id
            and _clean(_get(item, "vendor_id")) == vendor_id
        ),
        None,
    )
    if evidence is None or _clean(_get(evidence, "review_status")).casefold() != "accepted":
        return "Needs review"

    if requested not in {"Confirmed", "Suspected"}:
        return "Needs review"
    return requested


def build_relationship_graph(inventory, relationships, evidence_records):
    """Build a directed multigraph with stable IDs and visible verification state."""
    graph = nx.MultiDiGraph()

    if isinstance(inventory, pd.DataFrame) and {
        "Vendor ID",
        "Vendor Name",
    }.issubset(inventory.columns):
        for _, row in inventory.iterrows():
            vendor_id = _clean(row.get("Vendor ID"))
            vendor_name = _clean(row.get("Vendor Name"))
            if not vendor_id or vendor_id.casefold() == "nan" or not vendor_name:
                continue
            graph.add_node(
                _vendor_node_id(vendor_id),
                label=vendor_name,
                title=f"Vendor: {vendor_name}\nVendor ID: {vendor_id}",
                entity_type="Vendor",
                vendor_id=vendor_id,
            )

    for record in relationships:
        vendor_id = _clean(record.get("vendor_id"))
        vendor_name = _clean(record.get("vendor_name"))
        target_name = _clean(record.get("target_name"))
        target_type = _clean(record.get("target_type"))
        if not vendor_id or not target_name or not target_type:
            continue

        source_id = _vendor_node_id(vendor_id)
        target_id = _entity_node_id(target_type, target_name)
        if source_id not in graph:
            graph.add_node(
                source_id,
                label=vendor_name or vendor_id,
                title=f"Vendor: {vendor_name or vendor_id}\nVendor ID: {vendor_id}",
                entity_type="Vendor",
                vendor_id=vendor_id,
            )
        graph.add_node(
            target_id,
            label=target_name,
            title=f"{target_type}: {target_name}",
            entity_type=target_type,
        )

        status = effective_relationship_status(record, evidence_records)
        evidence_id = _clean(record.get("evidence_id"))
        graph.add_edge(
            source_id,
            target_id,
            key=_clean(record.get("relationship_id")),
            label=_clean(record.get("relationship_type")),
            title=(
                f"Status: {status}\n"
                f"Relationship: {_clean(record.get('relationship_type'))}\n"
                f"Evidence ID: {evidence_id or 'None — hypothesis or source URL'}\n"
                f"Source URL: {_clean(record.get('source_url')) or 'Not provided'}\n"
                f"Rationale: {_clean(record.get('rationale'))}"
            ),
            status=status,
            vendor_id=vendor_id,
            evidence_id=evidence_id,
        )
    return graph


def relationship_records_for_display(relationships, evidence_records):
    output = []
    for record in relationships:
        row = dict(record)
        row["requested_status"] = row.pop(
            "reviewer_status",
            row.get("status", "Needs review"),
        )
        row["status"] = effective_relationship_status(record, evidence_records)
        output.append(row)
    return output


def _vendor_options(inventory):
    options = {}
    if not isinstance(inventory, pd.DataFrame) or not {
        "Vendor ID",
        "Vendor Name",
    }.issubset(inventory.columns):
        return options

    for index, row in inventory.iterrows():
        vendor_id = _clean(row.get("Vendor ID"))
        vendor_name = _clean(row.get("Vendor Name"))
        if (
            vendor_id
            and vendor_id.casefold() != "nan"
            and vendor_name
            and vendor_name.casefold() != "nan"
        ):
            options[f"{vendor_name} ({vendor_id}) — row {index + 1}"] = (
                vendor_id,
                vendor_name,
            )
    return options


def show_intelligence_mesh():
    """Render relationship authoring, management, export, and graph views."""
    st.title("Intelligence Mesh")
    st.caption(
        "Record and explore vendor relationships grounded in accepted "
        "evidence, or explicitly label unverified hypotheses."
    )
    st.info(
        "The mesh does not perform automatic entity discovery. A keyword match "
        "or an unreviewed source cannot establish a confirmed relationship."
    )

    inventory = st.session_state.get("inventory_df")
    evidence_records = st.session_state.get("evidence_records", [])
    relationships = st.session_state.setdefault("relationship_records", [])

    if not isinstance(inventory, pd.DataFrame) or inventory.empty:
        st.warning("Load a vendor inventory before creating vendor relationships.")
        return
    if not {"Vendor ID", "Vendor Name"}.issubset(inventory.columns):
        st.error("The inventory must contain Vendor ID and Vendor Name columns.")
        return
    if duplicate_vendor_ids(inventory):
        st.error(
            "Resolve duplicate Vendor IDs before using the Intelligence Mesh."
        )
        return

    vendors = _vendor_options(inventory)
    if not vendors:
        st.info("No vendor with a usable Vendor ID and name is available.")
        return

    vendor_labels = list(vendors)
    record_by_id = {
        _clean(item.get("relationship_id")): item
        for item in relationships
        if _clean(item.get("relationship_id"))
    }
    record_ids = list(record_by_id)

    st.subheader("Relationship register")
    if relationships:
        st.dataframe(
            pd.DataFrame(
                relationship_records_for_display(
                    relationships,
                    evidence_records,
                )
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption(
            "No relationships recorded yet. Add a relationship or a clearly "
            "marked hypothesis below."
        )

    action = st.radio(
        "Relationship action",
        ["Add relationship", "Edit relationship"],
        horizontal=True,
        key="mesh_action",
        disabled=not relationships,
    )

    edit_id = None
    original = {}
    if action == "Edit relationship" and record_ids:
        edit_labels = {
            (
                f"{record_by_id[record_id].get('vendor_name', '')} — "
                f"{record_by_id[record_id].get('target_name', '')} "
                f"({record_by_id[record_id].get('relationship_type', '')})"
            ): record_id
            for record_id in record_ids
        }
        selected_edit = st.selectbox(
            "Select relationship to edit",
            list(edit_labels),
            key="mesh_edit_selection",
        )
        edit_id = edit_labels[selected_edit]
        original = record_by_id[edit_id]

    st.subheader("Edit relationship" if edit_id else "Add relationship")
    vendor_label_by_id = {
        vendor_id: label
        for label, (vendor_id, _) in vendors.items()
    }
    existing_vendor_id = _clean(original.get("vendor_id"))
    default_vendor_label = vendor_label_by_id.get(
        existing_vendor_id,
        vendor_labels[0],
    )
    vendor_default_index = vendor_labels.index(default_vendor_label)
    default_target_type = original.get("target_type", ENTITY_TYPES[0])
    if default_target_type not in ENTITY_TYPES:
        default_target_type = ENTITY_TYPES[-1]
    default_relation = original.get("relationship_type", RELATIONSHIP_TYPES[0])
    if default_relation not in RELATIONSHIP_TYPES:
        default_relation = RELATIONSHIP_TYPES[-1]
    default_status = original.get(
        "reviewer_status",
        original.get("status", "Needs review"),
    )
    if default_status not in VALID_STATUSES:
        default_status = "Needs review"
    editing_suffix = edit_id or "new"

    vendor_label = st.selectbox(
        "Inventory vendor",
        vendor_labels,
        index=vendor_default_index,
        key=f"mesh_vendor_{editing_suffix}",
    )
    vendor_id, vendor_name = vendors[vendor_label]

    evidence_by_label = {}
    current_vendor_id = vendor_id
    for item in evidence_records:
        if _clean(_get(item, "vendor_id")) != current_vendor_id:
            continue
        evidence_id = _clean(_get(item, "evidence_id"))
        if evidence_id:
            excerpt = _clean(_get(item, "excerpt"))
            label = f"{evidence_id} — {excerpt[:80]}"
            evidence_by_label[label] = evidence_id
    matching_label = next(
        (
            label for label, evidence_id in evidence_by_label.items()
            if evidence_id == _clean(original.get("evidence_id"))
        ),
        "No evidence selected",
    )
    evidence_choices = ["No evidence selected"] + list(evidence_by_label)
    evidence_index = (
        evidence_choices.index(matching_label)
        if matching_label in evidence_choices
        else 0
    )
    existing_status = _clean(original.get("status"))
    is_hypothesis = (
        existing_status == "Hypothesis — needs review"
        or (
            not original.get("evidence_id")
            and not original.get("source_url")
            and bool(original)
        )
    )

    with st.form(f"mesh_relationship_form_{editing_suffix}"):
        target_type = st.selectbox(
            "Related entity type",
            ENTITY_TYPES,
            index=ENTITY_TYPES.index(default_target_type),
        )
        target_name = st.text_input(
            "Related entity or service",
            value=_clean(original.get("target_name")),
            placeholder="e.g. Example AI Platform",
        )
        relationship_type = st.selectbox(
            "Relationship",
            RELATIONSHIP_TYPES,
            index=RELATIONSHIP_TYPES.index(default_relation),
        )
        evidence_choice = st.selectbox(
            "Supporting evidence for this vendor",
            evidence_choices,
            index=evidence_index,
            help=(
                "Only evidence already accepted in Review Centre can support "
                "a Confirmed relationship."
            ),
        )
        source_url = st.text_input(
            "Public source URL (optional when evidence is selected)",
            value=_clean(original.get("source_url")),
            placeholder="https://...",
        )
        rationale = st.text_area(
            "Relationship rationale",
            value=_clean(original.get("rationale")),
            placeholder="State what the source supports and what remains unverified.",
        )
        status = st.selectbox(
            "Assessment status",
            VALID_STATUSES,
            index=VALID_STATUSES.index(default_status),
            help=(
                "Confirmed is saved only when a linked evidence record for this "
                "vendor has been accepted by a reviewer."
            ),
        )
        hypothesis = st.checkbox(
            "Record as an unverified hypothesis (no evidence or URL yet)",
            value=is_hypothesis,
        )
        submitted = st.form_submit_button(
            "Save changes" if edit_id else "Add relationship",
            type="primary",
        )

    if submitted:
        selected_evidence_id = evidence_by_label.get(evidence_choice, "")
        selected_evidence = next(
            (
                item for item in evidence_records
                if _clean(_get(item, "evidence_id")) == selected_evidence_id
                and _clean(_get(item, "vendor_id")) == vendor_id
            ),
            None,
        )

        if not target_name.strip() or not rationale.strip():
            st.error("Enter the related entity and a rationale.")
        elif not hypothesis and not selected_evidence_id and not source_url.strip():
            st.error(
                "Select evidence, provide a public source URL, or mark this "
                "relationship as an unverified hypothesis."
            )
        else:
            try:
                clean_url = _safe_public_source_url(source_url)
                if selected_evidence and not clean_url:
                    clean_url = _clean(_get(selected_evidence, "source_url"))

                linked_accepted = (
                    selected_evidence is not None
                    and _clean(_get(selected_evidence, "review_status")).casefold()
                    == "accepted"
                )
                requested_status = (
                    "Hypothesis — needs review"
                    if hypothesis
                    else status
                )
                effective_status = (
                    requested_status
                    if linked_accepted and not hypothesis
                    else (
                        requested_status
                        if hypothesis
                        else "Needs review"
                    )
                )
                new_record = {
                    "relationship_id": _relationship_id(
                        vendor_id,
                        target_type,
                        target_name,
                        relationship_type,
                    ),
                    "vendor_id": vendor_id,
                    "vendor_name": vendor_name,
                    "source_name": vendor_name,
                    "source_type": "Vendor",
                    "target_name": target_name.strip(),
                    "target_type": target_type,
                    "relationship_type": relationship_type,
                    "status": effective_status,
                    "reviewer_status": requested_status,
                    "evidence_id": selected_evidence_id,
                    "source_url": clean_url,
                    "rationale": rationale.strip(),
                }
                duplicates = [
                    item for item in relationships
                    if item.get("relationship_id") == new_record["relationship_id"]
                    and item.get("relationship_id") != edit_id
                ]
                if duplicates:
                    st.error(
                        "This vendor relationship is already recorded. Edit "
                        "the existing record instead."
                    )
                elif edit_id:
                    index = next(
                        index for index, item in enumerate(relationships)
                        if item.get("relationship_id") == edit_id
                    )
                    relationships[index] = new_record
                    st.session_state["relationship_records"] = relationships
                    st.session_state["assessment_workbook_bytes"] = None
                    st.success("Relationship updated.")
                    st.rerun()
                else:
                    relationships.append(new_record)
                    st.session_state["relationship_records"] = relationships
                    st.session_state["assessment_workbook_bytes"] = None
                    st.success(
                        "Relationship added. Its displayed status is "
                        f"{effective_status}."
                    )
                    st.rerun()
            except ValueError as exc:
                st.error(f"Could not save relationship: {exc}")

    st.divider()
    graph = build_relationship_graph(
        inventory,
        relationships,
        evidence_records,
    )

    if relationships:
        st.subheader("Relationship graph")
        st.caption(
            "Edge status: green = Confirmed, amber = Suspected, gray = Needs "
            "review, purple = unverified hypothesis. Hover an edge for its "
            "evidence ID, source URL, and rationale."
        )
        network = Network(
            height="580px",
            width="100%",
            directed=True,
            bgcolor="#FFFFFF",
            font_color="#172B4D",
        )
        network.barnes_hut()
        status_colors = {
            "Confirmed": "#2E8B57",
            "Suspected": "#D99A00",
            "Needs review": "#64748B",
            "Hypothesis — needs review": "#8B5CF6",
        }
        for node_id, attributes in graph.nodes(data=True):
            network.add_node(
                node_id,
                label=attributes.get("label", node_id),
                title=attributes.get("title", ""),
                color="#2457C5" if attributes.get("entity_type") == "Vendor" else "#5B8DEF",
                shape="dot",
            )
        for source, target, key, attributes in graph.edges(
            keys=True,
            data=True,
        ):
            network.add_edge(
                source,
                target,
                key=key,
                label=attributes.get("label", ""),
                title=attributes.get("title", ""),
                color=status_colors.get(
                    attributes.get("status"),
                    "#64748B",
                ),
                arrows="to",
            )
        st.components.v1.html(
            network.generate_html(),
            height=600,
            scrolling=True,
        )
    else:
        st.info("Add a relationship to render the vendor intelligence graph.")

    if relationships:
        st.download_button(
            "Export relationship register (CSV)",
            data=pd.DataFrame(
                relationship_records_for_display(
                    relationships,
                    evidence_records,
                )
            ).to_csv(index=False).encode("utf-8"),
            file_name="blindspot_relationships.csv",
            mime="text/csv",
            key="mesh_relationship_export",
        )

        st.subheader("Manage relationships")
        management_labels = {
            (
                f"{item.get('vendor_name', item.get('vendor_id', 'Vendor'))} — "
                f"{item.get('target_name', 'Entity')} "
                f"({item.get('relationship_type', 'Relationship')})"
            ): item.get("relationship_id")
            for item in relationships
        }
        remove_label = st.selectbox(
            "Relationship to remove",
            list(management_labels),
            key="mesh_remove_selection",
        )
        if st.button("Remove selected relationship", key="mesh_remove"):
            relationship_id = management_labels[remove_label]
            st.session_state["relationship_records"] = [
                item for item in relationships
                if item.get("relationship_id") != relationship_id
            ]
            st.session_state["assessment_workbook_bytes"] = None
            st.rerun()

    st.caption(
        "Confirmed edges require an accepted evidence record tied to the same "
        "Vendor ID. If evidence is later rejected or changed, the graph "
        "automatically downgrades the edge to Needs review."
    )
