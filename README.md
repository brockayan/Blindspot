# Project BlindSpot

**Automated Vendor AI Intelligence & Cybersecurity Risk Assessment System**

Project BlindSpot is an evidence-driven vendor AI intelligence and cybersecurity risk assessment platform with human review. Designed for third-party risk management (TPRM), it automates the end-to-end ingestion, criticality tiering, public OSINT investigation, evidence extraction, AI-use classification, explainable security risk modeling, and relationship mesh mapping for third-party vendors.

> **Human-in-the-Loop Architecture:** BlindSpot combines automated intelligence generation with analyst review. Automated discovery and risk generation establish traceable, defensible preliminary baselines without manual assessment overhead, while final classifications, evidence grading, and scored findings are governed through human review.

## Key Capabilities

- **Automated Intelligence Pipeline:** Ingests vendor workbooks and automatically executes criticality calculation, tier-driven investigation depth scoping, bounded public OSINT, evidence candidate extraction, preliminary AI classification, explainable risk finding generation, and relationship mesh construction in a single orchestrated flow.
- **Explainable Business Criticality:** Evaluates five business factors (Data Sensitivity 30%, Operational Dependency 25%, Regulatory Exposure 20%, Payment Involvement 15%, Annual Volume 10%) with strict factor coverage tracking and tier mapping (Tier 1 Critical to Tier 4 Low).
- **Safe & Bounded Live OSINT:** Crawls permitted public vendor sources with destination IP validation (SSRF/private IP filtering), robots.txt policy enforcement, crawl depth controls, timeout and size safeguards, and bounded GitHub API querying.
- **Evidence Extraction & Provenance Tracking:** Extracts qualifying AI signals into candidate records with stable IDs, excerpts, source URLs, timestamps, and explicit data-origin provenance (clearly separating curated simulation disclosures from independently retrieved live web OSINT).
- **Calibrated AI-Use Classification:** Classifies vendors as *Confirmed*, *Suspected*, *Not Detected*, or *Inconclusive/Needs Review* using explicit evidence grading (source type, directness, service relevance, recency, and corroboration) and qualifying AI signal filters.
- **Substantiated AI Cybersecurity Risk Engine:** Computes a normalized 0–100 risk prioritization index using an explicit 4×3 Severity × Likelihood matrix. Enforces strict evidence-substantiation gating—a finding only scores when accepted evidence directly validates its risk theme.
- **Taxonomy of Risk Findings:** Generates evidence-supported findings, conditional architectural risks, and assurance gaps/baseline monitoring recommendations across 7 core risk themes.
- **Presentation-Readiness & Unscored Status Clarity:** Strictly distinguishes "No validated AI-specific risk findings" (unscored, `score=None`) from "Assessment incomplete / unassessed". Unsupported baseline findings (e.g., AutomWorx) remain visible for governance without manufacturing misleading numeric zero scores.
- **Intelligence Mesh:** Maps vendor dependencies and AI model provider relationships (e.g., Azure OpenAI, AWS Bedrock), gated by accepted evidence and named entity detection.
- **Authoritative Synchronized Reporting:** Exports a comprehensive 10-sheet audit workbook (`Project_BlindSpot_Assessment.xlsx`) and synchronized CSV registers derived from a single unified assessment state.

## Requirements

- Windows, macOS, or Linux
- Python 3.10 or newer recommended
- Internet access for the optional live public-source investigation

Dependencies are listed in [`requirements.txt`](requirements.txt). No search API key is required. The optional public GitHub repository search sends the selected vendor name to GitHub; it can be disabled in the Live Vendor Investigation Lab.

## Setup

### Windows PowerShell

From the project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```

If PowerShell blocks activation, call the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

Streamlit prints the local dashboard URL when the app starts.

## Automated Pipeline System

BlindSpot provides an automated, evidence-driven pipeline (`run_batch_automated_pipeline`) that transforms a raw vendor inventory into an initial risk assessment before human review:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Automated Batch Pipeline                        │
└────────────────────────────────────────────────────────────────────────┘
                                    │
    ┌───────────────────────────────┴───────────────────────────────┐
    ▼                                                               ▼
1. Ingestion & Validation                               2. Criticality Calculation
   • Excel schema check                                    • 5 business factors
   • Duplicate ID resolution                               • Weighted score (0–100)
   • Seed URL extraction                                   • Tier 1–4 assignment
    │                                                       │
    └───────────────────────────────┬───────────────────────┘
                                    ▼
                        3. Scoping & Investigation
                           • Tier-driven depth (Full vs. Standard)
                           • Bounded OSINT (Safe Fetcher & robots.txt)
                           • Candidate evidence extraction
                           • Case-study simulation disclosure isolation
                                    │
                                    ▼
                        4. Automated Analysis & Risk Engine
                           • Preliminary AI-use classification
                           • Risk findings generation (7 themes)
                           • Evidence-supported, conditional & assurance gaps
                           • Intelligence mesh entity mapping
                                    │
                                    ▼
                        5. Human-in-the-Loop Review
                           • Review Centre evidence grading & decisions
                           • State synchronization (`sync_vendor_after_review`)
                           • Consistent UI metrics & multi-sheet exports
```

### Pipeline Workflow Stages

1. **Vendor Ingestion & Schema Validation (`src/io/workbook.py`):**
   - Validates `.xlsx` / `.xlsm` input workbooks (such as `Meridian_Vendor_Input.xlsx`).
   - Enforces required columns (`Vendor ID`, `Vendor Name`), sanitizes whitespace, and checks for duplicate IDs.
   - Normalizes website URLs and categorizes service descriptions.

2. **Criticality Calculation & Depth Determination (`src/assessment/criticality.py`):**
   - Calculates a preliminary weighted business criticality score (0–100) across 5 business factors.
   - Evaluates explicit factor coverage ($ coverage = \frac{\text{Assessed Factors}}{5} \times 100\% $). Unknown or unprovided factors remain unassessed without artificial imputation.
   - Assigns criticality tiers:
     - **Tier 1 — Critical:** Score ≥ 80 or Critical Operational Dependency with High Sensitivity.
     - **Tier 2 — High:** Score ≥ 60.
     - **Tier 3 — Medium:** Score ≥ 40.
     - **Tier 4 — Low:** Score < 40.
   - Establishes tier-driven investigation depth: Critical vendors trigger deep review, while High/Medium/Low follow standard bounded review.

3. **Bounded OSINT Collection & Extraction (`src/collection/`):**
   - **Safe Fetcher (`fetcher.py`):** Restricts outbound HTTP requests to safe public destinations. Resolves DNS records to block private, loopback, and cloud metadata IP ranges (RFC 1918, RFC 3927, RFC 5735, RFC 6598). Re-verifies redirect destinations, enforces robots.txt permissions, restricts content-type to HTML, and caps responses at 5 MB with strict timeouts.
   - **Link Discovery (`investigation.py`):** Scans vendor root domains for common product, security, developer, trust, privacy, subprocessor, and blog paths up to bounded page and depth limits.
   - **Candidate Extraction (`extractor.py`):** Parses text for qualifying AI signals (`machine_learning`, `generative_ai`, `deep_learning`, `nlp`, `computer_vision`). Captures exact excerpts, source URLs, timestamps, and generates deterministic evidence IDs (`E-{VENDOR}-{HASH}`).
   - **Curated Case-Study Isolation (`fixtures.py`):** Preserves Meridian-specific case study disclosures with distinct provenance (`data_origin="curated_case_study_disclosure"`). They are never applied to unrelated vendor inventories and are explicitly distinguished from independently retrieved live OSINT.

4. **Preliminary AI-Use Classification (`src/assessment/classifier.py`):**
   - Evaluates collected evidence candidates using signal validation and source grading:
     - **Confirmed:** Accepted, current, direct, service-relevant evidence with a source score ≥ 4.
     - **Suspected:** Service-relevant qualifying evidence with a source score ≥ 2.
     - **Not Detected:** Investigation scope complete with qualifying negative disclosures (e.g. deterministic rule-based workload automation) and absence of affirmative AI signals.
     - **Inconclusive/Needs Review:** Incomplete collection scope, blocked fetches (e.g., robots.txt), or unreviewed candidates.

5. **Automated Risk Finding Generation (`src/assessment/risk.py`):**
   - Evaluates vendor data access, service type, and preliminary AI status to generate structured findings across 7 core themes.
   - Classifies findings into three distinct categories:
     - **Evidence-Supported:** Affirmative risks backed by validated positive evidence.
     - **Conditional Findings:** Applied when AI use is suspected or inconclusive; explicitly conditioned on technical architecture (e.g., whether external foundation models process customer records).
     - **Assurance Gaps / Baseline Monitoring:** Recorded when public evidence is absent or inconclusive, recommending due-diligence questionnaires or 30-day advance notification clauses rather than asserting unverified compliance violations.

6. **Intelligence Mesh & Entity Linking (`src/assessment/relationships.py`):**
   - Identifies named AI model providers (Microsoft Azure OpenAI, AWS Bedrock, Google Cloud, Anthropic) explicitly grounded in source text.
   - Establishes relationship records linking vendors to technologies and subprocessors, gated by evidence acceptance.

7. **Review Centre & Output Synchronization (`src/assessment/review.py`):**
   - Analysts inspect evidence, grade quality dimensions, and assign review decisions (`Accepted`, `Rejected`, `Needs review`).
   - Supports individual or batch approvals.
   - `sync_vendor_after_review()` guarantees that reviewer actions update dependent UI metrics, relationship mesh statuses, risk calculations, and export sheets synchronously from one authoritative state.

---

## Risk Calculation Mechanisms & Scoring Methodology

BlindSpot enforces an explainable separation of concerns across four independent dimensions:

| Dimension | Range / Values | Primary Focus | Independent Separation Rationale |
|---|---|---|---|
| **Business Criticality** | 0–100 & Tiers 1–4 | Operational & data importance to the enterprise | High operational criticality does not imply a vendor uses AI or has high cyber risk. |
| **Evidence Quality** | 0–100 | Credibility and relevance of accepted source citations | Measures source reliability, not AI adoption probability or threat level. |
| **AI-Use Classification** | Categorical | Evidence-backed deployment status | Presence of AI does not automatically constitute a vulnerability. |
| **AI Cybersecurity Risk** | 0–100 (or `None`) | Active risk prioritization index | Grounded strictly in validated findings supported by accepted evidence. |

### 1. Business Criticality Scoring

Criticality reflects the operational and data importance of the vendor relationship:

$$\text{Criticality Score} = \sum_{i=1}^5 (\text{Factor Rating}_i \times \text{Factor Weight}_i) \times 20$$

Where factor ratings are on a 1–5 scale:
- **Data Sensitivity (30%):** Sensitivity of data accessed or processed.
- **Operational Dependency (25%):** Dependency of core business operations.
- **Regulatory Exposure (20%):** Direct or indirect regulatory scrutiny.
- **Payment Involvement (15%):** Exposure to funds transfer or payment infrastructure.
- **Annual Data Volume (10%):** Volume of transaction or customer records.

A factor is scored only when explicitly rated (1–5) or mapped from recognized descriptive categories. Factor coverage tracks the proportion of evaluated factors ($ coverage = \frac{N}{5} \times 100\% $). Missing factors are never artificially assumed.

### 2. Evidence Quality Scoring

Evidence Quality is the arithmetic mean of source-type points for evidence that has been accepted, has a valid grade, and is relevant to the delivered service:

$$\text{Evidence Quality} = \frac{\sum \text{Source Points for Accepted, Relevant Records}}{\text{Count of Accepted, Relevant Records}} \times 20$$

Source points are allocated by credibility:
- **Official Product Documentation / Trust Center:** 5 points
- **Security Whitepaper / Vendor Architecture:** 4 points
- **Engineering / Tech Blog:** 3 points
- **Marketing Overview / Press Release:** 2 points
- **Third-Party Directory / Community Post:** 1 point

### 3. AI Cybersecurity Risk Scoring

The AI Cybersecurity Risk Score is an **explainable risk prioritization index** (0–100), not a probability of security compromise. It evaluates active findings across an explicit 4×3 Severity × Likelihood matrix:

$$\text{Finding Risk Index} = \frac{\text{Severity Score} \times \text{Likelihood Score}}{12} \times 100$$

#### Severity Scale
- **Critical (4):** Direct processing of customer master records, credentials, or core settlement data by unverified models.
- **High (3):** Subprocessor opacity or unverified model retention involving confidential banking/financial data.
- **Moderate (2):** Conditional risks, automated decisioning without documented human oversight, or indirect service integrations.
- **Low (1):** Baseline assurance monitoring, routine deterministic workloads, or minor visibility gaps.

#### Likelihood Scale
- **Likely (3):** Verified external commercial AI deployment without confirmed zero-retention or non-training contractual terms.
- **Possible (2):** Automated processing deployed in high-volume services where embedded AI tools are common across the industry.
- **Unlikely (1):** Deterministic, rule-based operations or verified tenant-isolated processing.

The vendor's overall AI Cybersecurity Risk Score is driven by the **highest qualifying active finding**:

$$\text{Vendor Cyber Risk Score} = \max(\{\text{Finding Risk Index}_i \mid \text{Finding}_i \text{ is active and supported by accepted evidence}\})$$

### 4. Strict Evidence-Substantiation Gating Rule

A risk finding can contribute to the numeric AI Cybersecurity Risk Score **only when all three conditions are met**:
1. Both **Severity** and **Likelihood** are explicitly rated by a reviewer or approved rubric.
2. The finding links to an **accepted** evidence record for that vendor.
3. The accepted evidence record **substantively substantiates the finding's specific risk theme** (`_evidence_substantiates_risk_theme`).

```python
# Content and relevance gate in src/assessment/risk.py:
if ev_rel in {"not_relevant", "irrelevant"}:
    return False  # Irrelevant evidence rejected
if ev_ai in {"no", "not detected"} or "rule_based_automation" in ev_sig:
    return False  # Negative disclosures cannot validate an AI risk
if not any(term in text_corpus for term in theme_substantiation_terms):
    return False  # Content must match the risk theme
```

- **Unrelated Evidence:** An accepted cafeteria menu or generic IT record attached to a data exposure finding is rejected and will not score.
- **Negative Disclosures:** Disclosures confirming non-AI deterministic processing cannot validate an AI risk finding.

### 5. Status Hierarchy & Unscored Differentiation

BlindSpot strictly distinguishes between incomplete reviews and assessments where no AI risks qualify for scoring:

| Status Label | Condition | Numeric Score | Interpretation |
|---|---|---|---|
| **`Assessed — reviewer-rated prioritization index`** | Active findings with rated severity/likelihood and accepted, theme-substantiating evidence | `0.0`–`100.0` | Active prioritization index based on substantiated findings. |
| **`No validated AI-specific risk findings`** | Active findings exist (such as baseline monitoring), but lack accepted qualifying AI evidence | `None` (Blank in exports) | **Not a verified zero-risk result.** Baseline assurance recommendations remain active; no artificial `0.0` score is manufactured. |
| **`Assessment incomplete / unassessed — reviewer ratings required`** | Active findings exist but lack rated severity or likelihood | `None` (Blank in exports) | Reviewer ratings must be supplied before scoring can proceed. |
| **`No active risk findings`** | No active risk findings exist for the vendor | `None` (Blank in exports) | Unassessed scope or no documented findings. |

#### Presentation-Readiness: The AutomWorx Case (V-001)
For vendors with confirmed non-AI operations (e.g., AutomWorx deterministic workload automation):
- **AI-Use Status:** `Not Detected`
- **Business Criticality:** `61.0/100` (Tier 2 — High)
- **AI Cybersecurity Risk:** Displays `"No validated AI risk"` in the UI and `None` in exports.
- **Active Finding:** `RISK-V-001-BASELINE-MONITORING` (Severity: Low, Likelihood: Unlikely) remains active and visible in the risk findings table, recommending annual attestations and 30-day advance notifications without generating an artificial numeric risk score.

### 6. Standardized Risk Themes

BlindSpot organizes findings into 7 standardized risk themes:

| Theme Key | Theme Label | Core Concerns Evaluated |
|---|---|---|
| `retention_and_training` | Retention and Model Training | Data retention periods, secondary model training on customer inputs, fine-tuning rights, and contractual zero-retention guarantees. |
| `sensitive_data_exposure` | Sensitive Data Exposure | Transmission of NPI, PII, financial transaction payloads, or credentials to third-party model endpoints. |
| `provider_transparency` | AI Provider Transparency | Subprocessor chains, fourth-party model dependencies (e.g. OpenAI via Azure), and architectural opacity. |
| `hosting_and_data_location` | Hosting and Data Location | Cross-border data flows, multi-tenant hosting, and data residency compliance. |
| `transparency_and_oversight` | Transparency and Oversight | Algorithmic explainability, human-in-the-loop checkpoints, and automated decision governance. |
| `operational_dependency` | Operational Dependency | Systemic single points of failure, vendor model deprecation, and availability risks. |
| `evidence_gaps` | Evidence and Assurance Gaps | Absence of public disclosures, blocked OSINT collection, or baseline assurance recommendations. |

---

## Live Investigation Scope & Safety Safeguards

The Live Vendor Investigation Lab conducts bounded, traceable public research:

- **Seed Gating:** Uses vendor URLs from the inventory and analyst-entered URLs as seeds.
- **Path Enumeration:** Proposes common product, documentation, developer, integration, blog, engineering, research, careers, security, trust, privacy, and subprocessor paths.
- **Crawl Boundaries:** Stays strictly within the seeded vendor domain and subdomains, records parent URLs for each candidate, and enforces page/depth limits.
- **SSRF & Network Controls:** Fails closed when robots permission cannot be established, re-verifies redirect destinations, restricts destinations to public IP addresses and standard HTTP(S) ports, and applies strict timeouts, content-type checks, and response-size limits.
- **External Dependencies:** Failed or blocked fetches (e.g., robots.txt disallow) are logged transparently and preserve uncertainty rather than claiming evidence of absence.

## Workbook format

The inventory workbook must contain a **Vendor Inventory** sheet with at least:

| Column | Required | Purpose |
|---|---|---|
| Vendor ID | Yes | Stable identifier used to associate records |
| Vendor Name | Yes | Display name |
| Website URL or similar | No | Seed URL for public-source investigation |

Additional columns are retained. Recognized criticality category fields may include data sensitivity, operational dependency, regulatory exposure, payment involvement, and annual data volume. Explicit rating fields should contain integer ratings from 1 through 5.

The consolidated output workbook includes:

1. Vendor Inventory
2. Evidence Register
3. Review Log
4. Risk Findings
5. Collection Log
6. Criticality Assessments
7. AI Investigation Summary
8. Assessment Overview
9. Intelligence Mesh
10. Vendor Scores

The source inventory is copied into the workbook; export does not modify the uploaded inventory.

## Tests

Run the test suite from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Or, on macOS/Linux:

```bash
python -m unittest discover -s tests -v
```

The tests cover criticality calculations, evidence grading and classification, inventory validation, safe fetch behavior, workflow integration, relationship evidence gating, and Excel workbook output. Live external websites are not contacted by the automated tests.

## Data handling and limitations

- The application is a Streamlit session-based prototype; assessment records are maintained in the active session and should be exported before ending it.
- Do not upload secrets, credentials, or information you are not authorized to process.
- Review URLs and evidence before relying on their stated vendor association or relevance.
- Network behavior depends on the selected source, robots policy, and runtime connectivity.
- This project does not provide authenticated vendor assessments, complete internet-wide OSINT, legal advice, or security certification.

