
"""Readable text extraction and AI-signal candidate detection.

This module finds passages for human review. A keyword match is not
proof that a vendor uses AI in a service supplied to Meridian.
"""

import re
from dataclasses import dataclass, asdict
from hashlib import sha256

from bs4 import BeautifulSoup


AI_SIGNAL_PATTERNS = {
    "generative_ai": [
        r"\bgenerative ai\b",
        r"\blarge language models?\b",
        r"\bLLMs?\b",
        r"\btext generation\b",
        r"\bAI assistant\b",
        r"\bAI copilot\b",
    ],
    "machine_learning": [
        r"\bmachine learning\b",
        r"\bML models?\b",
        r"\bpredictive model(?:s|ing)?\b",
        r"\bneural networks?\b",
    ],
    "automated_decisioning": [
        r"\bautomated decision(?:s|ing)?\b",
        r"\bAI-powered decision(?:s|ing)?\b",
        r"\bintelligent automation\b",
        r"\bautomated scoring\b",
    ],
    "model_provider": [
        r"\bOpenAI\b",
        r"\bAzure OpenAI\b",
        r"\bAnthropic\b",
        r"\bGoogle Gemini\b",
        r"\bAmazon Bedrock\b",
        r"\bCohere\b",
    ],
    "data_handling": [
        r"\bprompts?\b",
        r"\btraining data\b",
        r"\bmodel training\b",
        r"\bdata retention\b",
        r"\bAI subprocessors?\b",
    ],
}


@dataclass
class EvidenceCandidate:
    evidence_id: str
    source_url: str
    source_title: str
    retrieved_at: str
    excerpt: str
    signal_types: list
    matched_terms: list
    excerpt_hash: str
    review_status: str = "Needs review"
    classification_note: str = (
        "Automated candidate only; verify the context and service relevance."
    )

    def to_dict(self):
        return asdict(self)


def extract_page_text(html):
    """Extract readable page text while excluding non-content elements."""

    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for element in soup(
        ["script", "style", "noscript", "svg", "nav", "footer", "header"]
    ):
        element.decompose()

    text = soup.get_text(separator="\n")

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
    ]

    lines = [line for line in lines if line]

    return "\n".join(lines)


def split_into_passages(text, max_chars=1000):
    """Split text into manageable passages without inventing content."""

    if not text:
        return []

    passages = []
    current = []

    for paragraph in text.splitlines():
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        # Split exceptionally long paragraphs into bounded chunks.
        if len(paragraph) > max_chars:
            if current:
                passages.append(" ".join(current))
                current = []

            for start in range(0, len(paragraph), max_chars):
                chunk = paragraph[start:start + max_chars].strip()
                if chunk:
                    passages.append(chunk)

            continue

        current_text = " ".join(current)

        if current and len(current_text) + len(paragraph) + 1 > max_chars:
            passages.append(current_text)
            current = [paragraph]
        else:
            current.append(paragraph)

    if current:
        passages.append(" ".join(current))

    return passages


def detect_ai_signals(text):
    """Return matched signal categories and terms for one passage."""

    signal_types = []
    matched_terms = []

    for signal_type, patterns in AI_SIGNAL_PATTERNS.items():
        category_matches = []

        for pattern in patterns:
            for match in re.finditer(
                pattern,
                text,
                flags=re.IGNORECASE,
            ):
                category_matches.append(match.group(0))

        if category_matches:
            signal_types.append(signal_type)
            matched_terms.extend(category_matches)

    # Deduplicate terms without changing their original display order.
    matched_terms = list(dict.fromkeys(matched_terms))

    return signal_types, matched_terms


def extract_evidence_candidates(fetch_result, max_passages=100):
    """Extract AI-related candidate passages from a successful fetch result.

    fetch_result may be a FetchResult instance from fetcher.py or a
    dictionary with equivalent fields.

    Failed or unsupported fetches produce no evidence candidates.
    Their failure status should be recorded separately in collection logs.
    """

    if hasattr(fetch_result, "to_dict"):
        result = fetch_result.to_dict()
    else:
        result = dict(fetch_result)

    if result.get("status") != "success":
        return []

    html = result.get("html", "")
    source_url = result.get("url", "")
    source_title = result.get("title", "")
    retrieved_at = result.get("retrieved_at", "")

    text = extract_page_text(html)
    passages = split_into_passages(text)

    candidates = []
    seen_hashes = set()

    for passage in passages[:max_passages]:
        signal_types, matched_terms = detect_ai_signals(passage)

        if not signal_types:
            continue

        normalized = re.sub(r"\s+", " ", passage).strip().casefold()
        identity = f"{source_url.strip()}|{normalized}"
        excerpt_hash = sha256(identity.encode("utf-8")).hexdigest()

        if excerpt_hash in seen_hashes:
            continue

        seen_hashes.add(excerpt_hash)

        evidence_id = "E-" + excerpt_hash[:12].upper()

        candidates.append(
            EvidenceCandidate(
                evidence_id=evidence_id,
                source_url=source_url,
                source_title=source_title,
                retrieved_at=retrieved_at,
                excerpt=passage,
                signal_types=signal_types,
                matched_terms=matched_terms,
                excerpt_hash=excerpt_hash,
            )
        )

    return candidates
