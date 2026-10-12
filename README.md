# Project BlindSpot

**Unmasking Hidden Vendor AI**

Project BlindSpot is a Streamlit prototype for third-party vendor AI due diligence. It helps analysts organize a vendor inventory, review public-source evidence of AI use, document potential cybersecurity concerns, and export a traceable assessment.

> **Prototype notice:** This tool is an analyst aid, not a security certification, legal determination, or substitute for vendor due diligence. Automated discovery results are leads, not verified facts. Human review is required before evidence supports a conclusion.

## Features

- Load and validate an Excel vendor inventory.
- Calculate an explainable business-criticality assessment from recognized inventory ratings and categories.
- Run a bounded Live Vendor Investigation Lab for a selected vendor.
- Crawl relevant same-domain public links from analyst-approved vendor seeds with a configurable depth limit and parent-URL provenance.
- Fetch permitted public HTML pages using URL, destination, redirect, robots.txt, timeout, response-size, and content-type checks.
- Optionally search public GitHub repositories using the unauthenticated GitHub API.
- Extract AI-related passages as evidence candidates with stable IDs, excerpts, source URLs, timestamps, and collection provenance.
- Review evidence, record analyst decisions, and grade source type, directness, service relevance, recency, and corroboration.
- Classify reviewed AI-use evidence as Confirmed, Suspected, Not Detected, or Inconclusive/Needs Review.
- Record vendor-specific cybersecurity findings with rationales, supporting evidence IDs, severity, likelihood, review status, and recommended actions.
- Display vendor profiles and an evidence-linked relationship graph.
- Export a consolidated Excel workbook with inventory, evidence, review, risk, collection, criticality, investigation, mesh, overview, and separate vendor-score sheets.

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

## Run the application

1. Open **Vendor Inventory** and upload an `.xlsx` or `.xlsm` workbook.
2. Use a worksheet named **Vendor Inventory** containing at least **Vendor ID** and **Vendor Name**. Website or URL columns can seed live research. Recognized criticality columns can be supplied as explicit 1–5 ratings or supported descriptive categories.
3. Review inventory validation results and resolve missing or duplicate IDs.
4. Review the initial criticality assessment. It is calculated on upload when recognized fields provide enough information; missing ratings remain unassessed. Use the criticality controls to update or override ratings as needed.
5. Open **Live Vendor Investigation Lab**, select a vendor, check its seed URLs, optionally add analyst-verified public URLs, and click **Run Full Investigation**.
6. Inspect the source candidates, collection log, and extracted passages. Open **Review Centre** to grade and accept, reject, or leave each evidence candidate for review.
7. Use **Investigation Summary** to classify AI usage. Mark a public-source scope complete only after documenting the sources checked and access limitations.
8. In **Risk Assessment**, record reviewer-assessed cybersecurity concerns and link accepted evidence where applicable.
9. Review the vendor-specific findings and evidence-backed relationships in **Vendor Profile** and **Intelligence Mesh**.
10. Open **Reports & Export**, prepare the workbook, and download the consolidated assessment.

## Live investigation scope and safety

The Live Vendor Investigation Lab is bounded public-source research, not a general-purpose search engine:

- It uses vendor URLs from the inventory and analyst-entered URLs as seeds.
- From each seeded site, it proposes common product, documentation, developer, integration, blog, engineering, research, careers, security, trust, privacy, and subprocessor paths.
- It crawls relevant links found on successfully fetched pages, stays within the seeded vendor domain and subdomains, records the parent URL for each linked candidate, and stops at the configured page and depth limits.
- If enabled, GitHub search returns public repository candidates; a matching repository name does not prove vendor ownership.
- It fetches only HTML/XHTML pages. It does not execute JavaScript, enumerate arbitrary subdomains, use search-engine pages, or infer website ownership from a vendor name.
- Candidate URLs and AI-related keyword matches are not evidence of vendor AI use until their context and relevance have been reviewed.
- Fetches do not bypass authentication, paywalls, CAPTCHAs, or access controls. The fetcher fails closed when robots permission cannot be established, rechecks redirect destinations, restricts destinations to public IP addresses and standard HTTP(S) ports, and applies timeouts, content-type checks, and response-size limits.
- External services such as vendor sites or GitHub may be unavailable, rate-limit requests, or disallow collection. The collection log records outcomes; a failed or blocked fetch does not establish that no evidence exists.

## Scores and interpretation

The application keeps three measures separate:

### Business criticality

Criticality measures business importance, not AI use or cybersecurity risk. It uses proposed weights:

| Factor | Weight |
|---|---:|
| Data sensitivity | 30% |
| Operational dependency | 25% |
| Regulatory exposure | 20% |
| Payment involvement | 15% |
| Annual data volume | 10% |

Ratings are 1–5. The score is the weighted average normalized to 0–100. A missing or unrecognized factor leaves the assessment incomplete; the application does not silently redistribute its weight. Numeric annual-volume values are not mapped unless an explicit 1–5 rating is provided, because approved numeric volume bands are not configured. The proposed weights and category mappings should be validated against the case-study rubric before operational use.

### Evidence quality

Evidence quality is the arithmetic mean of source-type points for evidence that has been accepted, has a valid grade, and has not been explicitly marked irrelevant to the assessed service. Source points are normalized from 1–5 to 0–100. This is a **source-quality index**, not a probability that AI is used, an AI-use confidence score, or a security-risk score.

### AI cybersecurity risk

Cybersecurity risk is based on reviewer-entered, active findings with both a rated severity and likelihood and at least one linked evidence record accepted for the same vendor. For each qualifying finding, the prioritization index is:

```text
severity rating × likelihood rating ÷ 12 × 100
```

Severity ratings are Low=1, Moderate=2, High=3, Critical=4; likelihood ratings are Unlikely=1, Possible=2, Likely=3. The displayed vendor score is the highest qualifying finding index. It is a prioritization index, **not a probability**, and AI-use evidence alone does not create or confirm a cybersecurity risk. No qualifying supported finding means “Unassessed” or “No active risk findings,” not “no risk.”

## Evidence classification

- **Confirmed:** At least one accepted, current, direct, service-relevant evidence record with a source score of at least 4.
- **Suspected:** Accepted, service-relevant evidence with a source score of at least 2 that does not meet the Confirmed criteria.
- **Not Detected:** No qualifying evidence was found within a reviewer-defined scope marked complete, with scope notes recorded. This is not proof of absence.
- **Inconclusive/Needs Review:** Evidence is pending, unresolved, insufficient, or the collection scope is incomplete.

Extracted candidates start in **Needs review**. The application does not automatically accept evidence.

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

