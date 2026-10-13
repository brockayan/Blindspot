
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
        r"\bAI agents?\b",
        r"\bconversational ai\b",
        r"\bprompt engineering\b",
        r"\brag\b",
        r"\bretrieval[- ]augmented generation\b",
        r"\bgenerative model(?:s)?\b",
    ],
    "machine_learning": [
        r"\bmachine learning\b",
        r"\bML models?\b",
        r"\bpredictive model(?:s|ing)?\b",
        r"\bneural networks?\b",
        r"\bdeep learning\b",
        r"\bnatural language processing\b",
        r"\bNLP\b",
        r"\bcomputer vision\b",
        r"\banomaly detection\b",
    ],
    "automated_decisioning": [
        r"\bautomated decision(?:s|ing)?\b",
        r"\bAI-powered decision(?:s|ing)?\b",
        r"\bintelligent automation\b",
        r"\bautomated scoring\b",
        r"\bintelligent document processing\b",
        r"\bidp\b",
        r"\brobotic process automation\b",
        r"\brpa\b",
        r"\bautomated underwriting\b",
    ],
    "model_provider": [
        r"\bOpenAI\b",
        r"\bAzure OpenAI\b",
        r"\bMicrosoft Azure AI\b",
        r"\bAnthropic\b",
        r"\bClaude\b",
        r"\bGoogle Gemini\b",
        r"\bGoogle Cloud Vertex AI\b",
        r"\bVertex AI\b",
        r"\bAmazon Bedrock\b",
        r"\bAWS Bedrock\b",
        r"\bAWS SageMaker\b",
        r"\bCohere\b",
        r"\bMistral AI\b",
        r"\bMeta Llama\b",
        r"\bDatabricks\b",
        r"\bSnowflake Cortex\b",
        r"\bIBM watsonx\b",
        r"\bHugging Face\b",
    ],
    "data_handling": [
        r"\bprompts?\b",
        r"\btraining data\b",
        r"\bmodel training\b",
        r"\bdata retention\b",
        r"\bAI subprocessors?\b",
        r"\bdata governance\b",
        r"\bzero[- ]retention\b",
        r"\bopt[- ]out of training\b",
        r"\bprivacy policy\b",
        r"\bdata processing agreement\b",
        r"\bprompt logging\b",
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

        # Deduplicate repeated passages from the same URL:
        # Cap at 1 candidate for repository URLs and at most 2 for other pages.
        url_lower = source_url.casefold()
        is_repo = "github.com/" in url_lower
        max_per_url = 1 if is_repo else 2
        same_url_count = sum(1 for c in candidates if c.source_url == source_url)
        if same_url_count >= max_per_url:
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


def extract_disclosed_model_providers(evidence_items) -> list[str]:
    """Extract distinct disclosed AI model/infrastructure providers from evidence.

    Does not infer providers from vendor names or general industry reputation.
    Does not infer direct OpenAI integration solely from a reference to Azure OpenAI Service.
    """
    providers = set()

    texts = []
    for item in evidence_items or []:
        if isinstance(item, str):
            texts.append(item)
        elif hasattr(item, "excerpt"):
            texts.append(str(item.excerpt))
        elif isinstance(item, dict):
            texts.append(str(item.get("excerpt", "")))

    combined = "\n".join(texts)

    # 1. Identify Azure OpenAI / Microsoft Azure AI
    has_azure_openai = bool(
        re.search(
            r"\bAzure OpenAI\b|\bMicrosoft Azure AI\b|\bAzure AI\b",
            combined,
            flags=re.IGNORECASE,
        )
    )
    if has_azure_openai:
        providers.add("Microsoft Azure OpenAI Service")

    # 2. Check for standalone OpenAI (excluding Azure OpenAI references)
    sanitized_for_openai = re.sub(
        r"\b(?:Microsoft\s+)?Azure\s+(?:OpenAI(?:\s+Service)?|AI)\b",
        "",
        combined,
        flags=re.IGNORECASE,
    )
    if re.search(
        r"\bOpenAI\b|\bChatGPT\b|\bGPT-4\b|\bGPT-3\b",
        sanitized_for_openai,
        flags=re.IGNORECASE,
    ):
        providers.add("OpenAI")

    other_patterns = {
        "Anthropic": r"\bAnthropic\b|\bClaude\b",
        "Google Cloud / Gemini": r"\bGoogle Gemini\b|\bVertex AI\b|\bGoogle Cloud AI\b",
        "Amazon Bedrock / AWS": r"\bAmazon Bedrock\b|\bAWS Bedrock\b|\bAWS SageMaker\b",
        "Cohere": r"\bCohere\b",
        "Mistral AI": r"\bMistral AI\b|\bMistral\b",
        "Meta Llama": r"\bMeta Llama\b|\bLlama 2\b|\bLlama 3\b",
        "Databricks": r"\bDatabricks\b|\bMosaicML\b",
        "Snowflake Cortex": r"\bSnowflake Cortex\b|\bSnowflake AI\b",
        "IBM watsonx": r"\bIBM watsonx\b|\bwatsonx\b",
        "Hugging Face": r"\bHugging Face\b",
    }

    for canonical_name, pattern in other_patterns.items():
        if re.search(pattern, combined, flags=re.IGNORECASE):
            providers.add(canonical_name)

    return sorted(providers)


def summarize_how_vendor_uses_ai(evidence_items, service_name: str = "") -> str:
    """Summarize how the vendor may be using AI based on extracted evidence."""
    signal_counts = {}
    matched_all = set()

    for item in evidence_items or []:
        signals = []
        terms = []
        if hasattr(item, "signal_types"):
            signals = item.signal_types or []
            terms = item.matched_terms or []
        elif isinstance(item, dict):
            signals = item.get("signal_types", []) or []
            terms = item.get("matched_terms", []) or []

        for sig in signals:
            signal_counts[sig] = signal_counts.get(sig, 0) + 1
        for t in terms:
            matched_all.add(str(t).strip())

    if not signal_counts:
        return "No public evidence of AI use was detected in the investigated sources."

    usages = []
    if signal_counts.get("generative_ai"):
        usages.append(
            "Generative AI / LLM capabilities (e.g. conversational assistant, automated text generation, or contextual search)"
        )
    if signal_counts.get("machine_learning"):
        usages.append(
            "Machine learning models for predictive analytics, pattern recognition, or automated classification"
        )
    if signal_counts.get("automated_decisioning"):
        usages.append(
            "Automated decisioning, intelligent document processing, or workflow automation"
        )
    if signal_counts.get("data_handling"):
        usages.append(
            "Disclosed AI data processing, prompt handling, or subprocessor data flows"
        )

    summary = "; ".join(usages)
    if service_name:
        summary = f"Within {service_name}: " + summary

    if matched_all:
        key_terms = sorted(matched_all, key=len, reverse=True)[:5]
        summary += f" (Keywords: {', '.join(key_terms)})"

    return summary

