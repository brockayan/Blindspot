<<<<<<< HEAD

"""Public-source URL discovery for Project BlindSpot.

This module prepares candidate URLs. It does not crawl pages itself.
It uses supplied vendor URLs and optional analyst-provided search results.
It does not bypass access controls or scrape search-engine result pages.
"""

from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse
from typing import Optional


SOURCE_CATEGORIES = {
    "official_website": [
        "official website",
        "website",
        "homepage",
    ],
    "product_documentation": [
        "product",
        "documentation",
        "docs",
        "developer",
        "api",
    ],
    "trust_and_privacy": [
        "trust",
        "privacy",
        "security",
        "subprocessor",
        "data processing",
    ],
    "engineering_and_jobs": [
        "engineering",
        "careers",
        "jobs",
        "research",
        "technology",
    ],
}


@dataclass
class SourceCandidate:
    vendor_name: str
    url: str
    category: str
    discovery_method: str
    status: str = "Candidate — not yet fetched"
    notes: str = ""

    def to_dict(self):
        return {
            "vendor_name": self.vendor_name,
            "url": self.url,
            "category": self.category,
            "discovery_method": self.discovery_method,
            "status": self.status,
            "notes": self.notes,
        }


def normalize_url(url: str) -> Optional[str]:
    """Normalize an HTTP(S) URL and reject unsupported URL schemes."""

    if not url or not isinstance(url, str):
        return None

    url = url.strip()

    if not url:
        return None

    if "://" not in url:
        url = "https://" + url

    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    if parsed.scheme.lower() not in {"http", "https"}:
        return None

    if not parsed.hostname:
        return None

    # Do not accept URLs containing embedded credentials.
    if parsed.username or parsed.password:
        return None

    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    except (UnicodeError, AttributeError):
        return None

    try:
        port = parsed.port
    except ValueError:
        return None

    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        hostname = f"{hostname}:{port}"

    path = parsed.path or "/"

    # Remove trailing slash except for the domain root.
    if path != "/":
        path = path.rstrip("/")

    return urlunparse(
        (
            parsed.scheme.lower(),
            hostname,
            path,
            "",
            parsed.query,
            "",
        )
    )


def classify_url(url: str) -> str:
    """Assign a simple investigation category based on the URL."""

    parsed = urlparse(url)
    text = f"{parsed.netloc} {parsed.path}".lower()

    for category, keywords in SOURCE_CATEGORIES.items():
        if any(keyword in text for keyword in keywords):
            return category

    return "general_public_source"


def discover_sources(
    vendor_name: str,
    supplied_urls=None,
    discovered_urls=None,
):
    """Prepare and deduplicate candidate URLs for one vendor.

    Args:
        vendor_name: Vendor name from the inventory.
        supplied_urls: URLs explicitly supplied in the vendor workbook.
        discovered_urls: URLs provided by an approved search/API adapter
            or manually verified by an analyst.

    Returns:
        List of SourceCandidate objects.

    Important:
        This function does not search the web on its own. A search/API
        integration will be added separately. A vendor name alone is
        never treated as proof that a URL belongs to that vendor.
    """

    if not vendor_name or not str(vendor_name).strip():
        return []

    supplied_urls = supplied_urls or []
    discovered_urls = discovered_urls or []

    candidates = []
    seen = set()

    sources = [
        (url, "vendor_inventory")
        for url in supplied_urls
    ] + [
        (url, "approved_search_or_manual_discovery")
        for url in discovered_urls
    ]

    for raw_url, method in sources:
        normalized = normalize_url(raw_url)

        if not normalized or normalized in seen:
            continue

        seen.add(normalized)

        candidates.append(
            SourceCandidate(
                vendor_name=str(vendor_name).strip(),
                url=normalized,
                category=classify_url(normalized),
                discovery_method=method,
                notes=(
                    "Candidate URL only. Vendor ownership and relevance "
                    "must be verified before drawing conclusions."
                ),
            )
        )

    return candidates


def candidates_as_records(candidates):
    """Convert candidate objects into records for a table or export."""

    return [candidate.to_dict() for candidate in candidates]
=======

"""Public-source URL discovery for Project BlindSpot.

This module prepares candidate URLs. It does not crawl pages itself.
It uses supplied vendor URLs and optional analyst-provided search results.
It does not bypass access controls or scrape search-engine result pages.
"""

from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse
from typing import Optional


SOURCE_CATEGORIES = {
    "official_website": [
        "official website",
        "website",
        "homepage",
    ],
    "product_documentation": [
        "product",
        "documentation",
        "docs",
        "developer",
        "api",
    ],
    "trust_and_privacy": [
        "trust",
        "privacy",
        "security",
        "subprocessor",
        "data processing",
    ],
    "engineering_and_jobs": [
        "engineering",
        "careers",
        "jobs",
        "research",
        "technology",
    ],
}


@dataclass
class SourceCandidate:
    vendor_name: str
    url: str
    category: str
    discovery_method: str
    status: str = "Candidate — not yet fetched"
    notes: str = ""

    def to_dict(self):
        return {
            "vendor_name": self.vendor_name,
            "url": self.url,
            "category": self.category,
            "discovery_method": self.discovery_method,
            "status": self.status,
            "notes": self.notes,
        }


def normalize_url(url: str) -> Optional[str]:
    """Normalize an HTTP(S) URL and reject unsupported URL schemes."""

    if not url or not isinstance(url, str):
        return None

    url = url.strip()

    if not url:
        return None

    if "://" not in url:
        url = "https://" + url

    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    if parsed.scheme.lower() not in {"http", "https"}:
        return None

    if not parsed.hostname:
        return None

    # Do not accept URLs containing embedded credentials.
    if parsed.username or parsed.password:
        return None

    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    except (UnicodeError, AttributeError):
        return None

    try:
        port = parsed.port
    except ValueError:
        return None

    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        hostname = f"{hostname}:{port}"

    path = parsed.path or "/"

    # Remove trailing slash except for the domain root.
    if path != "/":
        path = path.rstrip("/")

    return urlunparse(
        (
            parsed.scheme.lower(),
            hostname,
            path,
            "",
            parsed.query,
            "",
        )
    )


def classify_url(url: str) -> str:
    """Assign a simple investigation category based on the URL."""

    parsed = urlparse(url)
    text = f"{parsed.netloc} {parsed.path}".lower()

    for category, keywords in SOURCE_CATEGORIES.items():
        if any(keyword in text for keyword in keywords):
            return category

    return "general_public_source"


def discover_sources(
    vendor_name: str,
    supplied_urls=None,
    discovered_urls=None,
):
    """Prepare and deduplicate candidate URLs for one vendor.

    Args:
        vendor_name: Vendor name from the inventory.
        supplied_urls: URLs explicitly supplied in the vendor workbook.
        discovered_urls: URLs provided by an approved search/API adapter
            or manually verified by an analyst.

    Returns:
        List of SourceCandidate objects.

    Important:
        This function does not search the web on its own. A search/API
        integration will be added separately. A vendor name alone is
        never treated as proof that a URL belongs to that vendor.
    """

    if not vendor_name or not str(vendor_name).strip():
        return []

    supplied_urls = supplied_urls or []
    discovered_urls = discovered_urls or []

    candidates = []
    seen = set()

    sources = [
        (url, "vendor_inventory")
        for url in supplied_urls
    ] + [
        (url, "approved_search_or_manual_discovery")
        for url in discovered_urls
    ]

    for raw_url, method in sources:
        normalized = normalize_url(raw_url)

        if not normalized or normalized in seen:
            continue

        seen.add(normalized)

        candidates.append(
            SourceCandidate(
                vendor_name=str(vendor_name).strip(),
                url=normalized,
                category=classify_url(normalized),
                discovery_method=method,
                notes=(
                    "Candidate URL only. Vendor ownership and relevance "
                    "must be verified before drawing conclusions."
                ),
            )
        )

    return candidates


def candidates_as_records(candidates):
    """Convert candidate objects into records for a table or export."""

    return [candidate.to_dict() for candidate in candidates]
>>>>>>> origin/main
