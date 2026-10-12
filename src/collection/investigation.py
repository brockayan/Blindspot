<<<<<<< HEAD
"""Bounded live public-source discovery and collection for the investigation lab."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.assessment.evidence import create_evidence_record
from src.collection.discovery import classify_url, normalize_url
from src.collection.extractor import extract_evidence_candidates
from src.collection.fetcher import PublicPageFetcher


MAX_DISCOVERED_LINKS = 20
MAX_GITHUB_RESULTS = 5
MAX_GITHUB_RESPONSE_BYTES = 1_000_000
PATH_CANDIDATES = (
    "/product",
    "/products",
    "/platform",
    "/docs",
    "/documentation",
    "/developers",
    "/integrations",
    "/blog",
    "/engineering",
    "/research",
    "/careers",
    "/jobs",
    "/security",
    "/trust",
    "/privacy",
    "/subprocessors",
)
LINK_HINTS = (
    "product",
    "platform",
    "docs",
    "developer",
    "integrat",
    "blog",
    "engineer",
    "research",
    "career",
    "job",
    "security",
    "trust",
    "privacy",
    "subprocessor",
    "github",
    "repository",
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _source_type(candidate):
    url = candidate["url"].casefold()
    category = candidate["category"]
    if category == "engineering_and_jobs" and any(
        term in url for term in ("career", "job", "hiring")
    ):
        return "relevant_technical_job_posting"
    if category == "product_documentation":
        return "official_product_documentation"
    if any(term in url for term in ("blog", "news", "research", "engineering")):
        return "official_technical_announcement"
    if "github.com/" in url:
        return "developer_reference"
    return "indirect_technical_signal"


def _candidate(url, vendor_name, method, *, parent_url="", crawl_depth=0):
    normalized = normalize_url(url)
    if not normalized:
        return None
    return {
        "vendor_name": vendor_name,
        "url": normalized,
        "category": classify_url(normalized),
        "discovery_method": method,
        "parent_url": parent_url,
        "crawl_depth": crawl_depth,
        "status": "Candidate — not yet fetched",
        "notes": (
            "Live candidate only; verify source ownership, context, and "
            "service relevance before drawing conclusions."
        ),
    }


def prepare_investigation_candidates(vendor_name, seed_urls):
    """Prepare explicit and bounded route candidates from analyst-provided URLs."""
    candidates = []
    seen = set()
    for raw_url in seed_urls:
        candidate = _candidate(raw_url, vendor_name, "inventory_or_analyst_url")
        if candidate and candidate["url"] not in seen:
            seen.add(candidate["url"])
            candidates.append(candidate)

        if candidate:
            parsed = urlparse(candidate["url"])
            origin = f"{parsed.scheme}://{parsed.netloc}"
            root = _candidate(
                origin + "/",
                vendor_name,
                "same_domain_root_candidate",
                parent_url=candidate["url"],
                crawl_depth=0,
            )
            if root and root["url"] not in seen:
                seen.add(root["url"])
                candidates.append(root)

            for path in PATH_CANDIDATES:
                path_candidate = _candidate(
                    urljoin(origin, path),
                    vendor_name,
                    "common_public_path_candidate",
                    parent_url=origin + "/",
                    crawl_depth=0,
                )
                if path_candidate and path_candidate["url"] not in seen:
                    seen.add(path_candidate["url"])
                    candidates.append(path_candidate)
    return candidates


def discover_github_repositories(vendor_name):
    """Search GitHub's unauthenticated public repository API for candidates.

    Returns discovered repository URLs and an explicit availability note.
    The API results are leads only; they do not establish vendor ownership.
    """
    if not vendor_name or not vendor_name.strip():
        return [], "Skipped: no vendor name."

    endpoint = "https://api.github.com/search/repositories"
    response = requests.get(
        endpoint,
        params={
            "q": vendor_name.strip(),
            "sort": "updated",
            "order": "desc",
            "per_page": MAX_GITHUB_RESULTS,
        },
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ProjectBlindSpot-public-research",
        },
        timeout=(4, 10),
        allow_redirects=False,
        stream=True,
    )
    try:
        if response.status_code != 200:
            return [], f"GitHub search returned HTTP {response.status_code}."
        content_type = response.headers.get("Content-Type", "").casefold()
        if "json" not in content_type:
            return [], "GitHub search returned an unsupported content type."
        declared_size = response.headers.get("Content-Length")
        if declared_size and int(declared_size) > MAX_GITHUB_RESPONSE_BYTES:
            return [], "GitHub search response exceeded the size limit."
        body = bytearray()
        for chunk in response.iter_content(16_384):
            body.extend(chunk)
            if len(body) > MAX_GITHUB_RESPONSE_BYTES:
                return [], "GitHub search response exceeded the size limit."
        payload = json.loads(body.decode("utf-8"))
        urls = []
        for item in payload.get("items", [])[:MAX_GITHUB_RESULTS]:
            html_url = normalize_url(item.get("html_url", ""))
            if html_url and urlparse(html_url).hostname in {
                "github.com",
                "www.github.com",
            }:
                urls.append(html_url)
        return urls, f"GitHub public repository search returned {len(urls)} candidate(s)."
    except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError) as exc:
        return [], f"GitHub search unavailable ({type(exc).__name__})."
    finally:
        response.close()


def discover_relevant_link_records(html, page_url, known_hosts):
    """Extract bounded, relevant crawler links from a fetched page."""
    soup = BeautifulSoup(html or "", "html.parser")
    links = []
    seen = set()
    normalized_hosts = [host.casefold().rstrip(".") for host in known_hosts]
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        label = anchor.get_text(" ", strip=True)
        hint = f"{href} {label}".casefold()
        if not any(token in hint for token in LINK_HINTS):
            continue
        normalized = normalize_url(urljoin(page_url, href))
        if not normalized or normalized in seen:
            continue
        hostname = (urlparse(normalized).hostname or "").casefold().rstrip(".")
        in_vendor_domain = any(
            hostname == known_host or hostname.endswith("." + known_host)
            for known_host in normalized_hosts
        )
        public_repository = hostname in {"github.com", "www.github.com"}
        if not in_vendor_domain and not public_repository:
            continue
        seen.add(normalized)
        links.append({
            "url": normalized,
            "link_text": label[:160],
            "from_url": page_url,
            "is_public_repository": public_repository,
        })
        if len(links) >= MAX_DISCOVERED_LINKS:
            break
    return links


def discover_relevant_links(html, page_url, known_hosts):
    """Return relevant link URLs for compatibility with existing callers."""
    return [
        item["url"]
        for item in discover_relevant_link_records(html, page_url, known_hosts)
    ]


def run_full_investigation(
    *,
    vendor_id,
    vendor_name,
    seed_urls,
    max_pages=12,
    max_depth=2,
    include_github=True,
    fetcher=None,
    progress_callback=None,
    github_searcher=None,
):
    """Discover and fetch public candidate pages, returning traceable records.

    This workflow never crawls outside linked vendor domains except public
    GitHub repository candidates. The existing fetcher enforces safe public
    destinations, robots permission, redirects, timeouts, and response limits.
    """
    if not str(vendor_id).strip() or not str(vendor_name).strip():
        raise ValueError("Vendor ID and vendor name are required.")
    if not 1 <= max_pages <= 30:
        raise ValueError("max_pages must be between 1 and 30.")
    if not 0 <= max_depth <= 3:
        raise ValueError("max_depth must be between 0 and 3.")

    progress_callback = progress_callback or (lambda **_: None)
    searcher = github_searcher or discover_github_repositories
    candidate_records = prepare_investigation_candidates(
        str(vendor_name).strip(),
        seed_urls,
    )
    run_id = sha256(
        f"{vendor_id}|{_now()}".encode("utf-8")
    ).hexdigest()[:12]
    known_hosts = {
        hostname
        for url in seed_urls
        if (hostname := urlparse(normalize_url(url) or "").hostname)
    }
    collection_log = []

    progress_callback(
        phase="Discovery",
        completed=0,
        total=3,
        message="Prepared explicit website and common-path candidates.",
    )
    if include_github:
        try:
            github_urls, github_note = searcher(str(vendor_name).strip())
        except (requests.RequestException, ValueError) as exc:
            github_urls, github_note = [], (
                f"GitHub search unavailable ({type(exc).__name__})."
            )
        collection_log.append({
            "run_id": run_id,
            "vendor_id": str(vendor_id),
            "vendor_name": str(vendor_name),
            "source_url": "https://api.github.com/search/repositories",
            "status": (
                "discovery_complete"
                if github_note.startswith(
                    "GitHub public repository search returned"
                )
                else "discovery_limited"
            ),
            "discovery_method": "GitHub public repository search API",
            "data_origin": "live_public_api",
            "details": github_note,
            "checked_at": _now(),
        })
        seen = {item["url"] for item in candidate_records}
        for url in github_urls:
            candidate = _candidate(
                url,
                str(vendor_name).strip(),
                "github_public_repository_search_candidate",
                crawl_depth=0,
            )
            if candidate and candidate["url"] not in seen:
                seen.add(candidate["url"])
                candidate_records.append(candidate)
        candidate_records.sort(
            key=lambda item: (
                item["discovery_method"] == "common_public_path_candidate",
                item["discovery_method"]
                == "github_public_repository_search_candidate",
            )
        )

    progress_callback(
        phase="Discovery",
        completed=1,
        total=3,
        message="Starting permitted public-page collection.",
    )
    client = fetcher or PublicPageFetcher()
    owns_fetcher = fetcher is None
    evidence_records = []
    attempted_urls = set()
    cursor = 0

    try:
        while cursor < len(candidate_records) and len(attempted_urls) < max_pages:
            candidate = candidate_records[cursor]
            cursor += 1
            url = candidate["url"]
            if url in attempted_urls:
                continue
            attempted_urls.add(url)
            progress_callback(
                phase="Collection",
                completed=len(attempted_urls),
                total=max_pages,
                message=f"Checking candidate {len(attempted_urls)} of {max_pages}.",
            )
            fetched = client.fetch_page(url)
            status = str(getattr(fetched, "status", "failed")).casefold()
            fetched_url = str(getattr(fetched, "url", url))
            html = str(getattr(fetched, "html", "") or "")
            candidate["status"] = status
            candidate["source_title"] = str(
                getattr(fetched, "title", "") or ""
            )
            candidate["retrieved_at"] = str(
                getattr(fetched, "retrieved_at", "") or ""
            )
            collection_log.append({
                "run_id": run_id,
                "vendor_id": str(vendor_id),
                "vendor_name": str(vendor_name),
                "source_url": fetched_url,
                "source_title": str(getattr(fetched, "title", "") or ""),
                "status": status,
                "http_status": getattr(fetched, "http_status", None),
                "error_category": str(
                    getattr(fetched, "error_category", "") or ""
                ),
                "discovery_method": candidate["discovery_method"],
                "data_origin": "live_public_web",
                "details": str(getattr(fetched, "error_message", "") or ""),
                "checked_at": str(
                    getattr(fetched, "retrieved_at", "") or _now()
                ),
            })
            if status != "success":
                continue

            for extracted in extract_evidence_candidates(fetched):
                evidence = create_evidence_record(
                    candidate=extracted,
                    vendor_id=str(vendor_id),
                    vendor_name=str(vendor_name),
                    source_type=_source_type(candidate),
                )
                evidence_record = evidence.to_dict()
                evidence_record["discovery_method"] = candidate["discovery_method"]
                evidence_record["data_origin"] = "live_public_web"
                evidence_record["run_id"] = run_id
                evidence_records.append(evidence_record)

            current_depth = int(candidate.get("crawl_depth", 0) or 0)
            if current_depth >= max_depth:
                continue

            linked_records = discover_relevant_link_records(
                html,
                fetched_url,
                known_hosts,
            )
            seen = {item["url"] for item in candidate_records}
            for linked in linked_records:
                linked_url = linked["url"]
                if linked_url in seen:
                    continue
                seen.add(linked_url)
                method = (
                    "github_public_repository_link_candidate"
                    if linked["is_public_repository"]
                    else "linked_public_page_candidate"
                )
                candidate_records.append(
                    _candidate(
                        linked_url,
                        str(vendor_name),
                        method,
                        parent_url=linked["from_url"],
                        crawl_depth=current_depth + 1,
                    )
                )
    finally:
        if owns_fetcher:
            client.close()

    progress_callback(
        phase="Complete",
        completed=3,
        total=3,
        message="Public-source collection finished.",
    )
    for candidate in candidate_records:
        candidate["fetched"] = candidate["url"] in attempted_urls
    return {
        "run_id": run_id,
        "vendor_id": str(vendor_id),
        "vendor_name": str(vendor_name),
        "candidates": candidate_records,
        "evidence_records": evidence_records,
        "collection_log": collection_log,
        "pages_attempted": len(attempted_urls),
        "pages_fetched": sum(
            1 for record in collection_log if record.get("status") == "success"
        ),
        "evidence_candidates_found": len(evidence_records),
        "link_candidates_discovered": sum(
            1 for item in candidate_records
            if str(item.get("discovery_method", "")).startswith("linked_")
            or str(item.get("discovery_method", "")).startswith(
                "github_public_repository_link"
            )
        ),
        "crawl_depth_limit": max_depth,
        "search_scope_complete": False,
        "origin": "live_public_web_and_optional_public_GitHub_API",
    }
=======
"""Bounded live public-source discovery and collection for the investigation lab."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.assessment.evidence import create_evidence_record
from src.collection.discovery import classify_url, normalize_url
from src.collection.extractor import extract_evidence_candidates
from src.collection.fetcher import PublicPageFetcher


MAX_DISCOVERED_LINKS = 20
MAX_GITHUB_RESULTS = 5
MAX_GITHUB_RESPONSE_BYTES = 1_000_000
PATH_CANDIDATES = (
    "/product",
    "/products",
    "/platform",
    "/docs",
    "/documentation",
    "/developers",
    "/integrations",
    "/blog",
    "/engineering",
    "/research",
    "/careers",
    "/jobs",
    "/security",
    "/trust",
    "/privacy",
    "/subprocessors",
)
LINK_HINTS = (
    "product",
    "platform",
    "docs",
    "developer",
    "integrat",
    "blog",
    "engineer",
    "research",
    "career",
    "job",
    "security",
    "trust",
    "privacy",
    "subprocessor",
    "github",
    "repository",
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _source_type(candidate):
    url = candidate["url"].casefold()
    category = candidate["category"]
    if category == "engineering_and_jobs" and any(
        term in url for term in ("career", "job", "hiring")
    ):
        return "relevant_technical_job_posting"
    if category == "product_documentation":
        return "official_product_documentation"
    if any(term in url for term in ("blog", "news", "research", "engineering")):
        return "official_technical_announcement"
    if "github.com/" in url:
        return "developer_reference"
    return "indirect_technical_signal"


def _candidate(url, vendor_name, method):
    normalized = normalize_url(url)
    if not normalized:
        return None
    return {
        "vendor_name": vendor_name,
        "url": normalized,
        "category": classify_url(normalized),
        "discovery_method": method,
        "status": "Candidate — not yet fetched",
        "notes": (
            "Live candidate only; verify source ownership, context, and "
            "service relevance before drawing conclusions."
        ),
    }


def prepare_investigation_candidates(vendor_name, seed_urls):
    """Prepare explicit and bounded route candidates from analyst-provided URLs."""
    candidates = []
    seen = set()
    for raw_url in seed_urls:
        candidate = _candidate(raw_url, vendor_name, "inventory_or_analyst_url")
        if candidate and candidate["url"] not in seen:
            seen.add(candidate["url"])
            candidates.append(candidate)

        if candidate:
            parsed = urlparse(candidate["url"])
            origin = f"{parsed.scheme}://{parsed.netloc}"
            root = _candidate(
                origin + "/",
                vendor_name,
                "same_domain_root_candidate",
            )
            if root and root["url"] not in seen:
                seen.add(root["url"])
                candidates.append(root)

            for path in PATH_CANDIDATES:
                path_candidate = _candidate(
                    urljoin(origin, path),
                    vendor_name,
                    "common_public_path_candidate",
                )
                if path_candidate and path_candidate["url"] not in seen:
                    seen.add(path_candidate["url"])
                    candidates.append(path_candidate)
    return candidates


def discover_github_repositories(vendor_name):
    """Search GitHub's unauthenticated public repository API for candidates.

    Returns discovered repository URLs and an explicit availability note.
    The API results are leads only; they do not establish vendor ownership.
    """
    if not vendor_name or not vendor_name.strip():
        return [], "Skipped: no vendor name."

    endpoint = "https://api.github.com/search/repositories"
    response = requests.get(
        endpoint,
        params={
            "q": vendor_name.strip(),
            "sort": "updated",
            "order": "desc",
            "per_page": MAX_GITHUB_RESULTS,
        },
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ProjectBlindSpot-public-research",
        },
        timeout=(4, 10),
        allow_redirects=False,
        stream=True,
    )
    try:
        if response.status_code != 200:
            return [], f"GitHub search returned HTTP {response.status_code}."
        content_type = response.headers.get("Content-Type", "").casefold()
        if "json" not in content_type:
            return [], "GitHub search returned an unsupported content type."
        declared_size = response.headers.get("Content-Length")
        if declared_size and int(declared_size) > MAX_GITHUB_RESPONSE_BYTES:
            return [], "GitHub search response exceeded the size limit."
        body = bytearray()
        for chunk in response.iter_content(16_384):
            body.extend(chunk)
            if len(body) > MAX_GITHUB_RESPONSE_BYTES:
                return [], "GitHub search response exceeded the size limit."
        payload = json.loads(body.decode("utf-8"))
        urls = []
        for item in payload.get("items", [])[:MAX_GITHUB_RESULTS]:
            html_url = normalize_url(item.get("html_url", ""))
            if html_url and urlparse(html_url).hostname in {
                "github.com",
                "www.github.com",
            }:
                urls.append(html_url)
        return urls, f"GitHub public repository search returned {len(urls)} candidate(s)."
    except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError) as exc:
        return [], f"GitHub search unavailable ({type(exc).__name__})."
    finally:
        response.close()


def discover_relevant_links(html, page_url, known_hosts):
    """Extract bounded, relevant links from a page already fetched permissibly."""
    soup = BeautifulSoup(html or "", "html.parser")
    links = []
    seen = set()
    normalized_hosts = [host.casefold().rstrip(".") for host in known_hosts]
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        label = anchor.get_text(" ", strip=True)
        hint = f"{href} {label}".casefold()
        if not any(token in hint for token in LINK_HINTS):
            continue
        normalized = normalize_url(urljoin(page_url, href))
        if not normalized or normalized in seen:
            continue
        hostname = (urlparse(normalized).hostname or "").casefold().rstrip(".")
        in_vendor_domain = any(
            hostname == known_host or hostname.endswith("." + known_host)
            for known_host in normalized_hosts
        )
        public_repository = hostname in {"github.com", "www.github.com"}
        if not in_vendor_domain and not public_repository:
            continue
        seen.add(normalized)
        links.append(normalized)
        if len(links) >= MAX_DISCOVERED_LINKS:
            break
    return links


def run_full_investigation(
    *,
    vendor_id,
    vendor_name,
    seed_urls,
    max_pages=12,
    include_github=True,
    fetcher=None,
    progress_callback=None,
    github_searcher=None,
):
    """Discover and fetch public candidate pages, returning traceable records.

    This workflow never crawls outside linked vendor domains except public
    GitHub repository candidates. The existing fetcher enforces safe public
    destinations, robots permission, redirects, timeouts, and response limits.
    """
    if not str(vendor_id).strip() or not str(vendor_name).strip():
        raise ValueError("Vendor ID and vendor name are required.")
    if not 1 <= max_pages <= 30:
        raise ValueError("max_pages must be between 1 and 30.")

    progress_callback = progress_callback or (lambda **_: None)
    searcher = github_searcher or discover_github_repositories
    candidate_records = prepare_investigation_candidates(
        str(vendor_name).strip(),
        seed_urls,
    )
    run_id = sha256(
        f"{vendor_id}|{_now()}".encode("utf-8")
    ).hexdigest()[:12]
    known_hosts = {
        hostname
        for url in seed_urls
        if (hostname := urlparse(normalize_url(url) or "").hostname)
    }
    collection_log = []

    progress_callback(
        phase="Discovery",
        completed=0,
        total=3,
        message="Prepared explicit website and common-path candidates.",
    )
    if include_github:
        try:
            github_urls, github_note = searcher(str(vendor_name).strip())
        except (requests.RequestException, ValueError) as exc:
            github_urls, github_note = [], (
                f"GitHub search unavailable ({type(exc).__name__})."
            )
        collection_log.append({
            "run_id": run_id,
            "vendor_id": str(vendor_id),
            "vendor_name": str(vendor_name),
            "source_url": "https://api.github.com/search/repositories",
            "status": (
                "discovery_complete"
                if github_note.startswith(
                    "GitHub public repository search returned"
                )
                else "discovery_limited"
            ),
            "discovery_method": "GitHub public repository search API",
            "data_origin": "live_public_api",
            "details": github_note,
            "checked_at": _now(),
        })
        seen = {item["url"] for item in candidate_records}
        for url in github_urls:
            candidate = _candidate(
                url,
                str(vendor_name).strip(),
                "github_public_repository_search_candidate",
            )
            if candidate and candidate["url"] not in seen:
                seen.add(candidate["url"])
                candidate_records.append(candidate)
        candidate_records.sort(
            key=lambda item: (
                item["discovery_method"] == "common_public_path_candidate",
                item["discovery_method"]
                == "github_public_repository_search_candidate",
            )
        )

    progress_callback(
        phase="Discovery",
        completed=1,
        total=3,
        message="Starting permitted public-page collection.",
    )
    client = fetcher or PublicPageFetcher()
    owns_fetcher = fetcher is None
    evidence_records = []
    attempted_urls = set()
    cursor = 0

    try:
        while cursor < len(candidate_records) and len(attempted_urls) < max_pages:
            candidate = candidate_records[cursor]
            cursor += 1
            url = candidate["url"]
            if url in attempted_urls:
                continue
            attempted_urls.add(url)
            progress_callback(
                phase="Collection",
                completed=len(attempted_urls),
                total=max_pages,
                message=f"Checking candidate {len(attempted_urls)} of {max_pages}.",
            )
            fetched = client.fetch_page(url)
            status = str(getattr(fetched, "status", "failed")).casefold()
            fetched_url = str(getattr(fetched, "url", url))
            html = str(getattr(fetched, "html", "") or "")
            candidate["status"] = status
            candidate["source_title"] = str(
                getattr(fetched, "title", "") or ""
            )
            candidate["retrieved_at"] = str(
                getattr(fetched, "retrieved_at", "") or ""
            )
            collection_log.append({
                "run_id": run_id,
                "vendor_id": str(vendor_id),
                "vendor_name": str(vendor_name),
                "source_url": fetched_url,
                "source_title": str(getattr(fetched, "title", "") or ""),
                "status": status,
                "http_status": getattr(fetched, "http_status", None),
                "error_category": str(
                    getattr(fetched, "error_category", "") or ""
                ),
                "discovery_method": candidate["discovery_method"],
                "data_origin": "live_public_web",
                "details": str(getattr(fetched, "error_message", "") or ""),
                "checked_at": str(
                    getattr(fetched, "retrieved_at", "") or _now()
                ),
            })
            if status != "success":
                continue

            for extracted in extract_evidence_candidates(fetched):
                evidence = create_evidence_record(
                    candidate=extracted,
                    vendor_id=str(vendor_id),
                    vendor_name=str(vendor_name),
                    source_type=_source_type(candidate),
                )
                evidence_record = evidence.to_dict()
                evidence_record["discovery_method"] = candidate["discovery_method"]
                evidence_record["data_origin"] = "live_public_web"
                evidence_record["run_id"] = run_id
                evidence_records.append(evidence_record)

            linked_urls = discover_relevant_links(
                html,
                fetched_url,
                known_hosts,
            )
            seen = {item["url"] for item in candidate_records}
            for linked_url in linked_urls:
                if linked_url in seen:
                    continue
                seen.add(linked_url)
                candidate_records.append(
                    _candidate(
                        linked_url,
                        str(vendor_name),
                        "linked_public_page_candidate",
                    )
                )
    finally:
        if owns_fetcher:
            client.close()

    progress_callback(
        phase="Complete",
        completed=3,
        total=3,
        message="Public-source collection finished.",
    )
    for candidate in candidate_records:
        candidate["fetched"] = candidate["url"] in attempted_urls
    return {
        "run_id": run_id,
        "vendor_id": str(vendor_id),
        "vendor_name": str(vendor_name),
        "candidates": candidate_records,
        "evidence_records": evidence_records,
        "collection_log": collection_log,
        "pages_attempted": len(attempted_urls),
        "pages_fetched": sum(
            1 for record in collection_log if record.get("status") == "success"
        ),
        "evidence_candidates_found": len(evidence_records),
        "search_scope_complete": False,
        "origin": "live_public_web_and_optional_public_GitHub_API",
    }
>>>>>>> origin/main
