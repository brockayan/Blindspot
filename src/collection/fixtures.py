"""Meridian Case Study Fixtures and Safeguards.

Separates Meridian-specific case-study reference disclosures from the general-purpose
assessment engine to prevent them from being silently applied to unrelated vendor inventories.
"""

from typing import Any, Dict, Optional
from src.assessment.classifier import CONFIRMED, INCONCLUSIVE, NOT_DETECTED

MERIDIAN_CASE_STUDY_VENDORS = {
    "V-000": ["larkspur"],
    "V-001": ["automworx"],
    "V-002": ["fiserv"],
    "V-003": ["financial statement services", "fssi"],
    "V-004": ["terrapin"],
    "V-005": ["bny", "bank of new york", "mellon"],
    "V-006": ["clearing house", "the clearing house"],
}

MERIDIAN_CASE_STUDY_FIXTURES: Dict[str, Dict[str, Any]] = {
    "V-001": {
        "vendor_id": "V-001",
        "vendor_name": "AutomWorx",
        "primary_url": "https://www.automworx.com/services/workload-automation",
        "source_title": "AutomWorx Enterprise Workload Automation Services",
        "source_type": "official_product_documentation",
        "excerpt": (
            "Specialized consulting and managed support for Automic, AppWorx, and UC4 "
            "workload automation engines, enterprise job scheduling, and batch script migration."
        ),
        "ai_usage_detected": "No",
        "preliminary_classification": NOT_DETECTED,
        "how_vendor_may_be_using_ai": (
            "No qualifying AI-use evidence was detected within the batch scheduling and workload automation managed "
            "services provided to Meridian. Vendor documentation describes deterministic rule-based scheduling engines; "
            "absence of public evidence does not constitute definitive proof of no AI deployment in uninspected systems."
        ),
        "named_subprocessors": "None named — Not Detected / No AI subprocessors identified in public service descriptions.",
        "ai_security_risk": "Low",
        "risk_rationale": (
            "Privileged access to production job schedules and service credentials represents "
            "high operational criticality, but no qualifying evidence was identified of AI model integration "
            "or generative AI processing Meridian workloads. AI-specific cybersecurity risk is not indicated "
            "within the investigated public scope, though absence of public evidence does not prove absence of AI."
        ),
        "recommended_action": (
            "Standard vendor oversight. Include standard AI disclosure clause in annual vendor attestation "
            "requiring 30-day prior written notification if automated AI-based scheduling or predictive optimization is introduced."
        ),
    },
    "V-002": {
        "vendor_id": "V-002",
        "vendor_name": "Fiserv, Inc.",
        "primary_url": "https://www.fiserv.com/en/solutions/banking/dna.html",
        "source_title": "Fiserv DNA Core Account Processing Platform",
        "source_type": "official_product_documentation",
        "excerpt": (
            "Fiserv DNA integrates predictive analytics and machine learning capabilities for transaction pattern "
            "analysis, real-time automated fraud scoring, and conversational banking interfaces."
        ),
        "ai_usage_detected": "Yes",
        "preliminary_classification": CONFIRMED,
        "how_vendor_may_be_using_ai": (
            "DNA incorporates machine learning models for real-time transaction monitoring, behavioral fraud "
            "detection, predictive cash forecasting, and conversational customer-service integration across core banking workflows."
        ),
        "named_subprocessors": (
            "None named in public evidence excerpt — Unverified / Inconclusive. "
            "Case study context suggests Microsoft Azure AI partnership, but public documentation "
            "does not confirm Azure AI subprocessor integration in DNA; require verification via questionnaire."
        ),
        "ai_security_risk": "Critical",
        "risk_rationale": (
            "Core platform holding full customer master (1.4M customers) and processing 240M transactions annually. "
            "Embedded ML models process live transaction streams; model drift, unauthorized data retention by cloud infrastructure "
            "providers, or algorithmic false positives could disrupt core banking transactions."
        ),
        "recommended_action": (
            "Issue targeted AI security questionnaire within 15 business days. Request SOC 2 Type II with AI-specific "
            "controls, verify Azure AI tenant isolation, validate data retention and non-training commitments for core "
            "banking transactions, and review human-in-the-loop oversight over automated fraud hold decisions."
        ),
    },
    "V-003": {
        "vendor_id": "V-003",
        "vendor_name": "Financial Statement Services, Inc. (FSSI)",
        "primary_url": "https://www.fssi-ca.com/document-outsourcing/",
        "source_title": "FSSI Document Outsourcing & Electronic Presentment",
        "source_type": "official_product_documentation",
        "excerpt": (
            "FSSI utilizes automated document processing, intelligent optical recognition, and data transformation "
            "engines to format, validate, and dynamically render variable-data transactional customer statements and tax notices."
        ),
        "ai_usage_detected": "Inconclusive",
        "preliminary_classification": INCONCLUSIVE,
        "how_vendor_may_be_using_ai": (
            "Intelligent document processing and automated data classification used for statement layout generation, "
            "optical character parsing, and address hygiene verification; no external generative AI or autonomous decision-making identified."
        ),
        "named_subprocessors": "None named — Inconclusive. Uses on-premises and private cloud print/mail composition systems without public disclosure of third-party foundation model APIs.",
        "ai_security_risk": "Medium",
        "risk_rationale": (
            "High data sensitivity (names, account balances, tax IDs) processed across 19M annual documents. "
            "If automated document processing and layout formatting utilize external cloud-based machine learning/AI APIs, "
            "customer tax identifiers and financial statements could face unauthorized subprocessor retention or exposure. "
            "Conversely, if document formatting is restricted to internal, deterministic optical composition without third-party model routing, "
            "AI-specific cybersecurity risks are minimal. In the absence of published subprocessor registers, external AI exposure "
            "remains unconfirmed pending direct questionnaire verification."
        ),
        "recommended_action": (
            "Issue vendor inquiry requesting written confirmation of subprocessor register. Verify that optical parsing engines "
            "operate entirely within isolated boundaries without routing tax identifiers or customer statements through third-party generative AI models."
        ),
    },
    "V-004": {
        "vendor_id": "V-004",
        "vendor_name": "Terrapin Technologies, Inc.",
        "primary_url": "https://www.terrapintech.com/platform",
        "source_title": "Terrapin Wealth Data Management Platform",
        "source_type": "official_product_documentation",
        "excerpt": (
            "Terrapin Wealth Data Platform provides automated multi-source data consolidation, reconciliation algorithms, "
            "and predictive business volume analytics for wealth management firms and broker-dealers."
        ),
        "ai_usage_detected": "Inconclusive",
        "preliminary_classification": INCONCLUSIVE,
        "how_vendor_may_be_using_ai": (
            "Predictive analytics and automated data reconciliation algorithms applied to consolidated wealth management transactions "
            "and advisor compensation modeling (live web collection blocked by vendor robots.txt policy; derived from curated case-study platform disclosure)."
        ),
        "named_subprocessors": "None named — Inconclusive. No third-party LLM or external AI API providers disclosed in public materials.",
        "ai_security_risk": "Medium",
        "risk_rationale": (
            "Confidential wealth portfolio holdings and advisor compensation records for 38,000 clients. "
            "If predictive volume analytics and reconciliation features integrate external commercial AI/ML services or third-party foundation models, "
            "customer financial data could face unverified model training or data-retention risks. "
            "Conversely, if analytics rely strictly on internal statistical heuristics, rule-based algorithms, or local math engines without external AI API routing, "
            "AI-specific exposure does not apply. In the absence of published architecture documentation, external AI exposure "
            "remains unconfirmed pending direct questionnaire verification."
        ),
        "recommended_action": (
            "Require Terrapin to provide an architecture and data flow diagram for its predictive analytics features at the next "
            "scheduled vendor review. Require confirmation that wealth portfolio data is never used to train shared external models."
        ),
    },
    "V-005": {
        "vendor_id": "V-005",
        "vendor_name": "BNY",
        "primary_url": "https://www.bny.com/us/en/about-us/newsroom/press-releases/bny-ai-hub.html",
        "source_title": "BNY Enterprise AI Hub & Virtual Assistant Deployment",
        "source_type": "official_technical_announcement",
        "excerpt": (
            "BNY has deployed its enterprise Artificial Intelligence Hub and proprietary 'Eliza' virtual assistant across custody, "
            "clearance, and payment operations, leveraging Microsoft Azure OpenAI Service and custom machine learning models for "
            "predictive payment routing and anomaly detection."
        ),
        "ai_usage_detected": "Yes",
        "preliminary_classification": CONFIRMED,
        "how_vendor_may_be_using_ai": (
            "BNY uses generative AI and predictive ML models for intelligent payment routing, liquidity forecasting, sanctions and "
            "payment anomaly detection, and automated customer operations support via its Eliza AI platform."
        ),
        "named_subprocessors": "Microsoft Azure OpenAI Service (disclosed foundation model and infrastructure provider).",
        "ai_security_risk": "High",
        "risk_rationale": (
            "High-value wholesale payment messaging (2.1M transactions annually). Public confirmation of Azure OpenAI Service "
            "integration indicates prompt and payment metadata exposure risk unless zero-data-retention and dedicated tenant isolation "
            "are legally and technically enforced."
        ),
        "recommended_action": (
            "Engage BNY vendor management team within 15 business days. Request verification of Azure OpenAI private tenant configuration, "
            "zero-data-retention agreements, prompt isolation guarantees, and model governance audit attestations for payment routing algorithms."
        ),
    },
    "V-006": {
        "vendor_id": "V-006",
        "vendor_name": "The Clearing House Payments Company L.L.C.",
        "primary_url": "https://www.theclearinghouse.org/payment-systems/rtp",
        "source_title": "The Clearing House RTP Network Systems & Operations",
        "source_type": "official_product_documentation",
        "excerpt": (
            "The Clearing House implements advanced machine learning algorithms and real-time behavioral analytics across the RTP network "
            "to evaluate transaction risk, detect anomalous payment flows, and deliver instant fraud-scoring signals to participating financial institutions."
        ),
        "ai_usage_detected": "Yes",
        "preliminary_classification": CONFIRMED,
        "how_vendor_may_be_using_ai": (
            "Machine learning models perform in-line real-time payment anomaly detection and automated fraud risk scoring across "
            "high-throughput RTP payment message streams."
        ),
        "named_subprocessors": "None named publicly — Inconclusive (operates proprietary infrastructure with specialized fraud risk partners; no public generative foundation model subprocessors disclosed).",
        "ai_security_risk": "High",
        "risk_rationale": (
            "Systemically critical financial infrastructure processing 14M payment messages. In-line ML fraud scoring could cause "
            "false-positive payment blocks, disrupting real-time settlement. Lack of public subprocessor disclosures leaves external analytics dependencies unverified."
        ),
        "recommended_action": (
            "Conduct formal third-party risk review via the Payments Operations Committee. Request The Clearing House's AI risk management "
            "framework (NIST AI RMF alignment), RTP model validation reports, and confirmation of subprocessor oversight."
        ),
    },
}


def is_meridian_case_study_vendor(vendor_id: str, vendor_name: str = "") -> bool:
    """Check whether a vendor ID and vendor name correspond to the Meridian case study."""
    clean_id = str(vendor_id or "").strip().upper()
    if clean_id not in MERIDIAN_CASE_STUDY_VENDORS:
        return False
    if not vendor_name:
        return True
    clean_name = str(vendor_name or "").strip().casefold()
    tokens = MERIDIAN_CASE_STUDY_VENDORS[clean_id]
    return any(t in clean_name for t in tokens)


def get_curated_case_study_disclosure(
    vendor_id: str,
    vendor_name: str = "",
    enable_fixtures: bool = True,
) -> Optional[Dict[str, Any]]:
    """Retrieve a curated case-study disclosure only when appropriate.

    Guards against silently applying Meridian-specific case-study fixtures to
    unrelated vendor inventories (e.g., matching V-001 by ID alone to an unrelated vendor).
    """
    if not enable_fixtures:
        return None
    clean_id = str(vendor_id or "").strip().upper()
    if vendor_name and not is_meridian_case_study_vendor(clean_id, vendor_name):
        return None
    fixture = MERIDIAN_CASE_STUDY_FIXTURES.get(clean_id)
    return dict(fixture) if fixture else None
