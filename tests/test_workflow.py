"""Focused regression tests for the vendor evidence workflow."""

from io import BytesIO
import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.assessment.classifier import (
    CONFIRMED,
    INCONCLUSIVE,
    NOT_DETECTED,
    classify_ai_usage,
)
from src.assessment.evidence import grade_evidence
from src.assessment.evidence import create_evidence_record
from src.assessment.criticality import initialize_inventory_criticality
from src.assessment.risk import (
    calculate_ai_cyber_risk_score,
    create_risk_finding,
)
from src.assessment.scores import calculate_evidence_score
from src.collection.discovery import normalize_url
from src.collection.extractor import extract_evidence_candidates
from src.collection.fetcher import _is_safe_public_url
from src.collection.fetcher import PublicPageFetcher
from src.collection.fetcher import FetchResult
from src.collection.investigation import (
    discover_github_repositories,
    discover_relevant_link_records,
    discover_relevant_links,
    run_full_investigation,
)
from src.io.validation import duplicate_vendor_ids, validate_inventory
from src.io.workbook import load_inventory
from src.ui.report_export import build_assessment_workbook
from src.ui.collection_page import merge_evidence_records
from src.ui.intelligence_mesh import (
    build_relationship_graph,
    effective_relationship_status,
)
from src.ui.review_centre import (
    CORROBORATION_OPTIONS,
    RECENCY_OPTIONS,
    RELEVANCE_OPTIONS,
    REVIEW_REASONS,
)


class TestEvidenceWorkflow(unittest.TestCase):
    def test_aggregate_evidence_score_uses_only_accepted_relevant_grades(self):
        score = calculate_evidence_score([
            {
                "review_status": "Accepted",
                "grade": {"score": 5, "service_relevance": "relevant"},
            },
            {
                "review_status": "Accepted",
                "grade": {"score": 3, "service_relevance": "unclear"},
            },
            {
                "review_status": "Needs review",
                "grade": {"score": 5, "service_relevance": "relevant"},
            },
            {
                "review_status": "Accepted",
                "grade": {"score": 5, "service_relevance": "not_relevant"},
            },
        ])
        self.assertEqual(score["score"], 80.0)
        self.assertEqual(score["evidence_count"], 2)

    def test_ai_cyber_risk_score_requires_accepted_same_vendor_evidence(self):
        finding = {
            "finding_id": "RF-1",
            "vendor_id": "V-1",
            "severity": "Critical",
            "likelihood": "Likely",
            "status": "Needs review",
            "evidence_ids": ["E-1"],
        }
        unsupported = calculate_ai_cyber_risk_score(
            [finding],
            evidence_records=[{
                "vendor_id": "V-2",
                "evidence_id": "E-1",
                "review_status": "Accepted",
            }],
        )
        self.assertIsNone(unsupported["score"])
        self.assertEqual(unsupported["unsupported_findings"], 1)

        scored = calculate_ai_cyber_risk_score(
            [finding],
            evidence_records=[{
                "vendor_id": "V-1",
                "evidence_id": "E-1",
                "review_status": "Accepted",
            }],
        )
        self.assertEqual(scored["score"], 100.0)

    def test_live_investigation_collects_traceable_candidate_records(self):
        class FakeFetcher:
            def fetch_page(self, url):
                return FetchResult(
                    url=url,
                    status="success",
                    retrieved_at="2026-10-12T00:00:00+00:00",
                    http_status=200,
                    content_type="text/html",
                    title="Vendor technical post",
                    html=(
                        "<html><body><a href='/careers'>Careers</a>"
                        "<p>Our generative AI assistant uses a model.</p>"
                        "</body></html>"
                    ),
                )

        progress = []
        result = run_full_investigation(
            vendor_id="V-1",
            vendor_name="Example Vendor",
            seed_urls=["https://vendor.example"],
            max_pages=1,
            include_github=False,
            fetcher=FakeFetcher(),
            progress_callback=lambda **event: progress.append(event),
        )
        self.assertEqual(result["pages_attempted"], 1)
        self.assertEqual(result["pages_fetched"], 1)
        self.assertEqual(len(result["evidence_records"]), 1)
        evidence = result["evidence_records"][0]
        self.assertEqual(evidence["vendor_id"], "V-1")
        self.assertEqual(evidence["review_status"], "Needs review")
        self.assertEqual(evidence["data_origin"], "live_public_web")
        self.assertTrue(evidence["source_url"].startswith("https://"))
        self.assertTrue(evidence["excerpt"])
        self.assertEqual(
            result["collection_log"][0]["data_origin"],
            "live_public_web",
        )
        self.assertTrue(progress)
        self.assertFalse(result["search_scope_complete"])

    def test_link_discovery_stays_with_vendor_domain_or_public_github(self):
        urls = discover_relevant_links(
            """
            <a href="https://docs.vendor.example/ai">Docs</a>
            <a href="https://attacker.example/careers">Careers</a>
            <a href="https://github.com/vendor/repo">Public repository</a>
            """,
            "https://vendor.example/",
            {"vendor.example"},
        )
        self.assertIn("https://docs.vendor.example/ai", urls)
        self.assertIn("https://github.com/vendor/repo", urls)
        self.assertNotIn("https://attacker.example/careers", urls)

    def test_link_discovery_records_crawl_provenance(self):
        records = discover_relevant_link_records(
            """
            <a href="/docs/ai">AI docs</a>
            <a href="https://github.com/vendor/repo">Public repository</a>
            """,
            "https://vendor.example/blog/post",
            {"vendor.example"},
        )
        self.assertEqual(records[0]["url"], "https://vendor.example/docs/ai")
        self.assertEqual(
            records[0]["from_url"],
            "https://vendor.example/blog/post",
        )
        self.assertFalse(records[0]["is_public_repository"])
        self.assertTrue(records[1]["is_public_repository"])

    def test_live_investigation_honors_crawl_depth(self):
        class FakeFetcher:
            def fetch_page(self, url):
                html = "<html><body><a href='/docs/ai'>AI docs</a></body></html>"
                if url.endswith("/docs/ai"):
                    html = (
                        "<html><body><p>Our generative AI assistant helps "
                        "analysts.</p></body></html>"
                    )
                return FetchResult(
                    url=url,
                    status="success",
                    retrieved_at="2026-10-12T00:00:00+00:00",
                    http_status=200,
                    content_type="text/html",
                    title="Vendor page",
                    html=html,
                )

        result = run_full_investigation(
            vendor_id="V-1",
            vendor_name="Example Vendor",
            seed_urls=["https://vendor.example"],
            max_pages=2,
            max_depth=1,
            include_github=False,
            fetcher=FakeFetcher(),
        )
        linked = [
            item for item in result["candidates"]
            if item["discovery_method"] == "linked_public_page_candidate"
        ]
        self.assertEqual(result["crawl_depth_limit"], 1)
        self.assertGreaterEqual(result["link_candidates_discovered"], 1)
        self.assertEqual(linked[0]["crawl_depth"], 1)
        self.assertEqual(linked[0]["parent_url"], "https://vendor.example/")

    def test_github_search_uses_bounded_public_api(self):
        response = MagicMock()
        response.status_code = 200
        response.headers = {
            "Content-Type": "application/json",
            "Content-Length": "100",
        }
        response.iter_content.return_value = [
            json.dumps({
                "items": [{
                    "html_url": "https://github.com/example/project",
                }]
            }).encode()
        ]
        with patch(
            "src.collection.investigation.requests.get",
            return_value=response,
        ) as request:
            urls, note = discover_github_repositories("Example Vendor")

        self.assertEqual(urls, ["https://github.com/example/project"])
        self.assertIn("candidate", note)
        self.assertFalse(request.call_args.kwargs["allow_redirects"])
        self.assertEqual(request.call_args.kwargs["timeout"], (4, 10))

    def test_grade_is_not_a_probability_and_requires_valid_url(self):
        grade = grade_evidence(
            "official_product_documentation",
            "https://vendor.example/product",
            "direct",
            "relevant",
            "current",
            "independent",
        )

        self.assertEqual(grade.score, 5)
        self.assertIn("proposed points", grade.rationale)
        self.assertIsNone(
            grade_evidence(
                "official_product_documentation",
                "file:///private",
                "direct",
                "relevant",
            ).score
        )

    def test_classifier_requires_accepted_direct_relevant_evidence(self):
        accepted = {
            "evidence_id": "E-1",
            "review_status": "Accepted",
            "grade": {
                "score": 5,
                "directness": "direct",
                "service_relevance": "relevant",
                "recency": "current",
            },
        }
        self.assertEqual(
            classify_ai_usage([accepted]).status,
            CONFIRMED,
        )

        rejected = dict(accepted, review_status="Rejected")
        self.assertEqual(
            classify_ai_usage([rejected], collection_complete=True).status,
            NOT_DETECTED,
        )

    def test_dated_direct_evidence_cannot_establish_confirmed_status(self):
        evidence = {
            "evidence_id": "E-DATED",
            "review_status": "Accepted",
            "grade": {
                "score": 5,
                "directness": "direct",
                "service_relevance": "relevant",
                "recency": "dated",
            },
        }
        self.assertEqual(classify_ai_usage([evidence]).status, "Suspected")

    def test_classifier_does_not_skip_pending_or_incomplete_scope(self):
        accepted = {
            "evidence_id": "E-1",
            "review_status": "Accepted",
            "grade": {
                "score": 5,
                "directness": "direct",
                "service_relevance": "relevant",
                "recency": "current",
            },
        }
        pending = {
            "evidence_id": "E-2",
            "review_status": "Needs review",
            "grade": {},
        }

        self.assertEqual(
            classify_ai_usage([accepted, pending]).status,
            INCONCLUSIVE,
        )
        self.assertEqual(classify_ai_usage([]).status, INCONCLUSIVE)
        self.assertEqual(
            classify_ai_usage([], collection_complete=True).status,
            NOT_DETECTED,
        )

    def test_extraction_records_candidate_only_with_stable_source_id(self):
        fetch_result = {
            "status": "success",
            "url": "https://vendor.example/docs",
            "title": "Product docs",
            "retrieved_at": "2026-10-12T00:00:00+00:00",
            "html": "<html><body><p>Our generative AI assistant helps teams.</p></body></html>",
        }
        first = extract_evidence_candidates(fetch_result)
        second = extract_evidence_candidates(fetch_result)

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].evidence_id, second[0].evidence_id)
        self.assertEqual(first[0].review_status, "Needs review")
        self.assertEqual(first[0].source_url, fetch_result["url"])

    def test_deduplication_preserves_existing_review_and_grade(self):
        existing = {
            "evidence_id": "E-1",
            "vendor_id": "V-1",
            "review_status": "Accepted",
            "reviewer": "Analyst",
            "review_notes": "Verified against source context.",
            "data_origin": "live_public_web",
            "discovery_method": "linked_public_page_candidate",
            "run_id": "RUN-1",
            "grade": {"score": 5, "directness": "direct"},
        }
        recaptured = {
            "evidence_id": "E-1",
            "vendor_id": "V-1",
            "review_status": "Needs review",
            "reviewer": "",
            "grade": {"score": 2},
        }

        merged, added, duplicates = merge_evidence_records(
            [existing], [recaptured]
        )

        self.assertEqual((added, duplicates), (0, 1))
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["review_status"], "Accepted")
        self.assertEqual(merged[0]["review_notes"], "Verified against source context.")
        self.assertEqual(merged[0]["grade"]["score"], 5)
        self.assertEqual(merged[0]["data_origin"], "live_public_web")
        self.assertEqual(
            merged[0]["discovery_method"],
            "linked_public_page_candidate",
        )
        self.assertEqual(merged[0]["run_id"], "RUN-1")

    def test_url_normalization_rejects_invalid_ports(self):
        self.assertIsNone(normalize_url("https://vendor.example:bad/path"))

    def test_review_options_match_the_grade_api(self):
        for relevance in RELEVANCE_OPTIONS:
            for recency in RECENCY_OPTIONS:
                for corroboration in CORROBORATION_OPTIONS:
                    grade = grade_evidence(
                        "official_product_documentation",
                        "https://vendor.example/docs",
                        "unclear",
                        relevance,
                        recency,
                        corroboration,
                    )
                    self.assertIsNotNone(grade.score)

        self.assertTrue(REVIEW_REASONS)

    def test_evidence_ids_are_stable_and_vendor_scoped(self):
        candidate = {
            "evidence_id": "E-ABC",
            "source_url": "https://vendor.example/docs",
            "excerpt": "AI assistant product detail",
        }
        first = create_evidence_record(
            candidate,
            "V-1",
            "Vendor One",
            "official_product_documentation",
        )
        repeated = create_evidence_record(
            candidate,
            "V-1",
            "Vendor One",
            "official_product_documentation",
        )
        other_vendor = create_evidence_record(
            candidate,
            "V-2",
            "Vendor Two",
            "official_product_documentation",
        )

        self.assertEqual(first.evidence_id, repeated.evidence_id)
        self.assertNotEqual(first.evidence_id, other_vendor.evidence_id)
        self.assertEqual(first.review_status, "Needs review")

    def test_fetcher_blocks_non_public_destinations(self):
        self.assertFalse(_is_safe_public_url("http://127.0.0.1/"))
        self.assertFalse(_is_safe_public_url("http://169.254.169.254/"))
        self.assertFalse(_is_safe_public_url("http://10.0.0.1/"))
        self.assertFalse(_is_safe_public_url("https://8.8.8.8:8443/"))
        self.assertTrue(_is_safe_public_url("https://8.8.8.8/"))

    def test_dns_names_resolving_to_private_addresses_are_blocked(self):
        with patch(
            "src.collection.fetcher.socket.getaddrinfo",
            return_value=[
                (2, 1, 6, "", ("192.168.1.5", 443)),
            ],
        ):
            self.assertFalse(_is_safe_public_url("https://vendor.example/"))

    def test_redirect_to_private_destination_is_blocked(self):
        fetcher = PublicPageFetcher(delay_seconds=0)
        fetcher._robots_cache["https://example.com/robots.txt"] = True
        response = MagicMock()
        response.is_redirect = True
        response.headers = {"Location": "http://127.0.0.1/admin"}
        fetcher.session.get = MagicMock(return_value=response)

        with patch(
            "src.collection.fetcher._is_safe_public_url",
            side_effect=[True, True, True, False],
        ):
            result = fetcher.fetch_page("https://example.com/")

        fetcher.close()
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.error_category, "unsafe_redirect")
        fetcher.session.get.assert_called_once()

    def test_risk_findings_keep_vendor_rationale_and_review_metadata(self):
        finding = create_risk_finding(
            vendor_id="V-1",
            vendor_name="Example Vendor",
            theme="evidence_gaps",
            rationale="No public assurance evidence was collected.",
            severity="Unassessed",
            evidence_ids=["E-1"],
            reviewer="Reviewer",
            reviewed_at="2026-10-12T00:00:00+00:00",
        )

        self.assertEqual(finding.vendor_id, "V-1")
        self.assertEqual(finding.evidence_ids, ["E-1"])
        self.assertEqual(finding.reviewer, "Reviewer")
        self.assertEqual(finding.status, "Needs review")


class TestInventoryAndExport(unittest.TestCase):
    def test_inventory_upload_criticality_uses_explicit_rating_columns(self):
        inventory = pd.DataFrame([{
            "Vendor ID": "V-1",
            "Vendor Name": "Example",
            "Data Sensitivity Rating": 5,
            "Operational Dependency Rating": 4,
            "Regulatory Exposure Rating": 3,
            "Payment Involvement Rating": 2,
            "Annual Data Volume Rating": 1,
        }])
        assessment = initialize_inventory_criticality(inventory)["V-1"]
        self.assertEqual(assessment["result"].score, 70.0)
        self.assertEqual(assessment["result"].coverage_percent, 100.0)
        self.assertTrue(assessment["auto_calculated"])

    def test_inventory_criticality_does_not_invent_numeric_volume_bands(self):
        inventory = pd.DataFrame([{
            "Vendor ID": "V-1",
            "Vendor Name": "Example",
            "Data Sensitivity": "High",
            "Operational Dependency": "Critical",
            "Regulatory Exposure": "High",
            "Payment Involvement": "Yes",
            "Annual Data Volume": 50000,
        }])
        result = initialize_inventory_criticality(inventory)["V-1"]["result"]
        self.assertIsNone(result.score)
        self.assertIn("annual_data_volume", result.missing_factors)

    def test_vendor_score_export_keeps_three_scores_separate(self):
        inventory = pd.DataFrame([{
            "Vendor ID": "V-1",
            "Vendor Name": "Example",
            "Data Sensitivity Rating": 5,
            "Operational Dependency Rating": 4,
            "Regulatory Exposure Rating": 3,
            "Payment Involvement Rating": 2,
            "Annual Data Volume Rating": 1,
        }])
        criticality = initialize_inventory_criticality(inventory)
        evidence = [{
            "vendor_id": "V-1",
            "evidence_id": "E-1",
            "review_status": "Accepted",
            "grade": {
                "score": 4,
                "service_relevance": "relevant",
            },
        }]
        finding = {
            "vendor_id": "V-1",
            "finding_id": "RF-1",
            "severity": "High",
            "likelihood": "Likely",
            "status": "Needs review",
            "evidence_ids": ["E-1"],
        }
        state = {
            "inventory_df": inventory,
            "evidence_records": evidence,
            "review_log": [],
            "risk_findings": [finding],
            "collection_log": [],
            "criticality_ratings": criticality,
            "investigation_assessments": {},
            "relationship_records": [],
        }
        with patch("streamlit.session_state", state):
            exported = build_assessment_workbook()

        workbook = load_workbook(BytesIO(exported.getvalue()), read_only=True)
        scores = workbook["Vendor Scores"]
        columns = {cell.value: cell.column for cell in scores[1]}
        row = {
            name: scores.cell(2, column).value
            for name, column in columns.items()
        }
        self.assertEqual(row["Business Criticality (0-100)"], 70.0)
        self.assertEqual(row["Evidence Quality (0-100)"], 80.0)
        self.assertEqual(row["AI Cybersecurity Risk (0-100)"], 75.0)
        self.assertNotEqual(
            row["Business Criticality (0-100)"],
            row["AI Cybersecurity Risk (0-100)"],
        )
        workbook.close()

    def test_every_sidebar_route_has_one_page_branch(self):
        app_tree = ast.parse((PROJECT_ROOT / "app.py").read_text(encoding="utf-8"))
        route = next(
            node for node in app_tree.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "selected_page"
        )

        labels = []
        current = route
        while isinstance(current, ast.If):
            if (
                isinstance(current.test, ast.Compare)
                and current.test.comparators
                and isinstance(current.test.comparators[0], ast.Constant)
            ):
                labels.append(current.test.comparators[0].value)
            current = current.orelse[0] if current.orelse else None

        expected = {
            "Overview",
            "Vendor Inventory",
            "AI Investigation",
            "Live Vendor Investigation Lab",
            "Public Evidence Collection",
            "Evidence Register",
            "Review Centre",
            "Investigation Summary",
            "Risk Assessment",
            "Intelligence Mesh",
            "Vendor Profile",
            "Reports & Export",
        }
        self.assertEqual(set(labels), expected)
        self.assertEqual(len(labels), len(set(labels)))

    def test_inventory_validation_catches_duplicates_and_missing_values(self):
        inventory = pd.DataFrame(
            {
                "Vendor ID": [" v-1 ", "V-1", None],
                "Vendor Name": ["One", "Two", " "],
                "Website URL": ["vendor.example", "bad url", ""],
            }
        )

        report = validate_inventory(inventory)
        codes = {issue.code for issue in report.issues}

        self.assertIn("DUPLICATE_VENDOR_ID", codes)
        self.assertIn("MISSING_VENDOR_ID", codes)
        self.assertIn("MISSING_VENDOR_NAME", codes)
        self.assertIn("INVALID_URL_FORMAT", codes)
        self.assertEqual(len(inventory), report.total_rows)
        self.assertEqual(duplicate_vendor_ids(inventory), ["v-1"])

    def test_workbook_loader_finds_header_and_rejects_missing_sheet(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Vendor Inventory"
        sheet.append(["Inventory extract"])
        sheet.append(["vendor id", "vendor name", "Website"])
        sheet.append(["V-1", "Example", "https://example.com"])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.xlsx"
            workbook.save(path)
            loaded, _, metadata = load_inventory(path)
            self.assertEqual(loaded.iloc[0]["Vendor ID"], "V-1")
            self.assertEqual(metadata["header_row"], 2)
            with self.assertRaises(ValueError):
                load_inventory(path, sheet_name="Missing")
            corrupt_path = Path(directory) / "corrupt.xlsx"
            corrupt_path.write_text("not an Excel workbook")
            with self.assertRaises(BadZipFile):
                load_inventory(corrupt_path)

    def test_export_has_all_sheets_and_does_not_mutate_inventory(self):
        inventory = pd.DataFrame(
            {"Vendor ID": ["V-1"], "Vendor Name": ["Example"]}
        )
        original = inventory.copy(deep=True)
        state = {
            "inventory_df": inventory,
            "evidence_records": [
                {
                    "evidence_id": "E-1",
                    "vendor_id": "V-1",
                    "grade": {
                        "score": 4,
                        "rationale": "Reviewer explanation",
                    },
                }
            ],
            "review_log": [],
            "risk_findings": [],
            "collection_log": [],
            "criticality_ratings": {},
            "investigation_assessments": {},
        }

        with patch("streamlit.session_state", state):
            exported = build_assessment_workbook()

        workbook = load_workbook(BytesIO(exported.getvalue()), read_only=True)
        self.assertEqual(
            workbook.sheetnames,
            [
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
            ],
        )
        self.assertEqual(
            workbook["Evidence Register"]["C1"].value,
            "Evidence Grade - score",
        )
        self.assertEqual(
            workbook["Evidence Register"]["D1"].value,
            "Evidence Grade - rationale",
        )
        workbook.close()
        pd.testing.assert_frame_equal(inventory, original)

    def test_empty_export_still_contains_all_sheets(self):
        state = {
            "inventory_df": None,
            "evidence_records": [],
            "review_log": [],
            "risk_findings": [],
            "collection_log": [],
            "criticality_ratings": {},
            "investigation_assessments": {},
        }

        with patch("streamlit.session_state", state):
            exported = build_assessment_workbook()

        workbook = load_workbook(BytesIO(exported.getvalue()), read_only=True)
        self.assertEqual(len(workbook.sheetnames), 10)
        workbook.close()

    def test_mesh_status_requires_accepted_evidence_for_the_same_vendor(self):
        relationship = {
            "vendor_id": "V-1",
            "reviewer_status": "Confirmed",
            "status": "Needs review",
            "evidence_id": "E-1",
        }

        self.assertEqual(
            effective_relationship_status(
                relationship,
                [{
                    "vendor_id": "V-1",
                    "evidence_id": "E-1",
                    "review_status": "Needs review",
                }],
            ),
            "Needs review",
        )
        self.assertEqual(
            effective_relationship_status(
                relationship,
                [{
                    "vendor_id": "V-2",
                    "evidence_id": "E-1",
                    "review_status": "Accepted",
                }],
            ),
            "Needs review",
        )
        self.assertEqual(
            effective_relationship_status(
                relationship,
                [{
                    "vendor_id": "V-1",
                    "evidence_id": "E-1",
                    "review_status": "Accepted",
                }],
            ),
            "Confirmed",
        )
        self.assertEqual(
            effective_relationship_status(
                {
                    "vendor_id": "V-1",
                    "reviewer_status": "Confirmed",
                    "status": "Confirmed",
                },
                [],
            ),
            "Needs review",
        )
        self.assertEqual(
            effective_relationship_status(
                {
                    "vendor_id": "V-1",
                    "reviewer_status": "Hypothesis — needs review",
                    "status": "Hypothesis — needs review",
                },
                [],
            ),
            "Hypothesis — needs review",
        )

    def test_mesh_graph_uses_vendor_ids_and_separates_entity_types(self):
        inventory = pd.DataFrame({
            "Vendor ID": ["V-1", "V-2"],
            "Vendor Name": ["Shared display name", "Shared display name"],
        })
        relationships = [
            {
                "relationship_id": "REL-1",
                "vendor_id": "V-1",
                "vendor_name": "Shared display name",
                "target_name": "Example",
                "target_type": "AI Provider",
                "relationship_type": "Uses AI service",
                "reviewer_status": "Confirmed",
                "evidence_id": "E-1",
            },
            {
                "relationship_id": "REL-2",
                "vendor_id": "V-2",
                "vendor_name": "Shared display name",
                "target_name": "Example",
                "target_type": "Cloud Provider",
                "relationship_type": "Uses cloud service",
                "reviewer_status": "Confirmed",
                "evidence_id": "E-2",
            },
        ]
        graph = build_relationship_graph(
            inventory,
            relationships,
            [
                {
                    "vendor_id": "V-1",
                    "evidence_id": "E-1",
                    "review_status": "Accepted",
                },
                {
                    "vendor_id": "V-2",
                    "evidence_id": "E-2",
                    "review_status": "Rejected",
                },
            ],
        )

        self.assertIn("vendor:v-1", graph)
        self.assertIn("vendor:v-2", graph)
        self.assertEqual(graph.number_of_nodes(), 4)
        self.assertEqual(graph.number_of_edges(), 2)
        statuses = {
            attributes["evidence_id"]: attributes["status"]
            for _, _, attributes in graph.edges(data=True)
        }
        self.assertEqual(statuses, {"E-1": "Confirmed", "E-2": "Needs review"})

    def test_mesh_relationships_are_exported_with_effective_status(self):
        state = {
            "inventory_df": pd.DataFrame(
                {"Vendor ID": ["V-1"], "Vendor Name": ["Example"]}
            ),
            "evidence_records": [],
            "review_log": [],
            "risk_findings": [],
            "collection_log": [],
            "criticality_ratings": {},
            "investigation_assessments": {},
            "relationship_records": [{
                "relationship_id": "REL-1",
                "vendor_id": "V-1",
                "vendor_name": "Example",
                "target_name": "AI Service",
                "target_type": "AI Provider",
                "relationship_type": "Uses AI service",
                "reviewer_status": "Confirmed",
                "status": "Confirmed",
                "evidence_id": "E-MISSING",
                "rationale": "Source is awaiting review.",
            }],
        }

        with patch("streamlit.session_state", state):
            exported = build_assessment_workbook()

        workbook = load_workbook(BytesIO(exported.getvalue()), read_only=True)
        self.assertEqual(workbook.sheetnames[8], "Intelligence Mesh")
        mesh = workbook["Intelligence Mesh"]
        self.assertEqual(mesh["A1"].value, "relationship_id")
        headings = {
            cell.value: cell.column
            for cell in mesh[1]
        }
        self.assertEqual(
            mesh.cell(2, headings["status"]).value,
            "Needs review",
        )
        workbook.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
