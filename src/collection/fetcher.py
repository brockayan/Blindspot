<<<<<<< HEAD

"""Respectful public webpage fetching for Project BlindSpot."""

import ipaddress
import socket
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests


USER_AGENT = (
    "ProjectBlindSpotResearch/1.0 "
    "(public vendor due diligence; contact: research@example.invalid)"
)

DEFAULT_TIMEOUT = (5, 15)
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_DELAY_SECONDS = 1.5

# Avoid fetching content that is unnecessary for this text-based prototype.
ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
}


def _is_safe_public_url(url):
    """Reject non-public destinations before any network request is made."""
    try:
        parsed = urlparse(url)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return False

        port = parsed.port
        expected_port = 443 if parsed.scheme.lower() == "https" else 80
        if port not in {None, expected_port}:
            return False

        hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii")
        try:
            addresses = [ipaddress.ip_address(hostname)]
        except ValueError:
            resolved = socket.getaddrinfo(
                hostname,
                port or (443 if parsed.scheme.lower() == "https" else 80),
                type=socket.SOCK_STREAM,
            )
            addresses = [
                ipaddress.ip_address(result[4][0])
                for result in resolved
            ]

        return bool(addresses) and all(
            address.is_global for address in addresses
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        return False


@dataclass
class FetchResult:
    url: str
    status: str
    retrieved_at: str
    http_status: int | None = None
    content_type: str = ""
    html: str = ""
    title: str = ""
    error_category: str = ""
    error_message: str = ""
    elapsed_seconds: float = 0.0

    def to_dict(self):
        return asdict(self)


class PublicPageFetcher:
    """Fetch accessible public HTML pages with basic safeguards.

    One instance should be reused for a collection run so that request
    delays and robots.txt decisions can be reused.

    This is not a browser. It does not execute JavaScript, bypass access
    controls, solve CAPTCHAs, or access authenticated content.
    """

    def __init__(
        self,
        timeout=DEFAULT_TIMEOUT,
        delay_seconds=DEFAULT_DELAY_SECONDS,
        max_bytes=DEFAULT_MAX_BYTES,
        user_agent=USER_AGENT,
    ):
        self.timeout = timeout
        self.delay_seconds = max(0.0, delay_seconds)
        self.max_bytes = max_bytes
        self.user_agent = user_agent

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml",
            }
        )

        self._last_request_by_host = {}
        self._robots_cache = {}

    @staticmethod
    def _timestamp():
        return datetime.now(timezone.utc).isoformat()

    def _wait_for_host(self, hostname):
        previous = self._last_request_by_host.get(hostname)

        if previous is not None:
            elapsed = time.monotonic() - previous
            remaining = self.delay_seconds - elapsed

            if remaining > 0:
                time.sleep(remaining)

        self._last_request_by_host[hostname] = time.monotonic()

    def _robots_allows(self, url):
        """Return whether robots.txt permits fetching this URL.

        If robots.txt cannot be retrieved or parsed, fail closed and
        leave the page uncollected for manual review.
        """
        if not _is_safe_public_url(url):
            return False

        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{origin}/robots.txt"

        if robots_url in self._robots_cache:
            return self._robots_cache[robots_url]

        try:
            response = self.session.get(
                robots_url,
                timeout=self.timeout,
                allow_redirects=False,
                stream=True,
            )

            try:
                if response.status_code != 200:
                    self._robots_cache[robots_url] = False
                    return False

                content = response.raw.read(256_000, decode_content=True)
                text = content.decode("utf-8", errors="replace")

            finally:
                response.close()

            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(text.splitlines())

            allowed = parser.can_fetch(self.user_agent, url)
            self._robots_cache[robots_url] = allowed
            return allowed

        except requests.RequestException:
            self._robots_cache[robots_url] = False
            return False

    def fetch_page(self, url):
        """Fetch one public HTML page and return a structured result."""

        started = time.monotonic()
        timestamp = self._timestamp()

        if not _is_safe_public_url(url):
            return FetchResult(
                url=url,
                status="blocked",
                retrieved_at=timestamp,
                error_category="unsafe_destination",
                error_message=(
                    "Only public HTTP(S) destinations on standard web "
                    "ports can be collected."
                ),
            )

        # Prevent requests from following redirects to arbitrary hosts.
        current_url = url

        try:
            for _ in range(4):
                parsed_current = urlparse(current_url)

                if not _is_safe_public_url(current_url):
                    return FetchResult(
                        url=url,
                        status="blocked",
                        retrieved_at=timestamp,
                        error_category="unsafe_redirect",
                        error_message="Redirect destination was rejected.",
                    )

                if not self._robots_allows(current_url):
                    return FetchResult(
                        url=url,
                        status="not_collected",
                        retrieved_at=timestamp,
                        error_category="robots_or_policy",
                        error_message=(
                            "Robots permission could not be established "
                            "or the URL was disallowed. No page was fetched."
                        ),
                    )

                self._wait_for_host(parsed_current.hostname.lower())

                response = self.session.get(
                    current_url,
                    timeout=self.timeout,
                    allow_redirects=False,
                    stream=True,
                )

                if response.is_redirect:
                    location = response.headers.get("Location")
                    response.close()

                    if not location:
                        return FetchResult(
                            url=url,
                            status="failed",
                            retrieved_at=timestamp,
                            error_category="redirect_error",
                            error_message="Redirect had no destination.",
                        )

                    current_url = urljoin(current_url, location)
                    continue

                with response:
                    http_status = response.status_code
                    content_type = (
                        response.headers.get("Content-Type", "")
                        .split(";")[0]
                        .strip()
                        .lower()
                    )

                    if http_status in {401, 403, 429}:
                        return FetchResult(
                            url=url,
                            status="not_collected",
                            retrieved_at=timestamp,
                            http_status=http_status,
                            content_type=content_type,
                            error_category="access_restricted",
                            error_message=(
                                "The source restricted access or requested "
                                "that automated collection slow down."
                            ),
                        )

                    if http_status >= 400:
                        return FetchResult(
                            url=url,
                            status="failed",
                            retrieved_at=timestamp,
                            http_status=http_status,
                            content_type=content_type,
                            error_category="http_error",
                            error_message=f"HTTP status {http_status}.",
                        )

                    if content_type not in ALLOWED_CONTENT_TYPES:
                        return FetchResult(
                            url=url,
                            status="unsupported",
                            retrieved_at=timestamp,
                            http_status=http_status,
                            content_type=content_type,
                            error_category="unsupported_content",
                            error_message=(
                                "This prototype fetches HTML pages only."
                            ),
                        )

                    declared_size = response.headers.get("Content-Length")
                    if declared_size:
                        try:
                            if int(declared_size) > self.max_bytes:
                                return FetchResult(
                                    url=url,
                                    status="unsupported",
                                    retrieved_at=timestamp,
                                    http_status=http_status,
                                    content_type=content_type,
                                    error_category="page_too_large",
                                    error_message=(
                                        "The page exceeds the configured "
                                        "maximum size."
                                    ),
                                )
                        except ValueError:
                            pass

                    body = bytearray()

                    for chunk in response.iter_content(chunk_size=16_384):
                        if not chunk:
                            continue

                        body.extend(chunk)

                        if len(body) > self.max_bytes:
                            return FetchResult(
                                url=url,
                                status="unsupported",
                                retrieved_at=timestamp,
                                http_status=http_status,
                                content_type=content_type,
                                error_category="page_too_large",
                                error_message=(
                                    "The page exceeded the configured "
                                    "maximum size while downloading."
                                ),
                            )

                    encoding = response.encoding or "utf-8"
                    html = body.decode(encoding, errors="replace")

                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, "html.parser")
                    title = (
                        soup.title.get_text(" ", strip=True)
                        if soup.title
                        else ""
                    )

                    return FetchResult(
                        url=current_url,
                        status="success",
                        retrieved_at=timestamp,
                        http_status=http_status,
                        content_type=content_type,
                        html=html,
                        title=title,
                        elapsed_seconds=round(
                            time.monotonic() - started, 3
                        ),
                    )

            return FetchResult(
                url=url,
                status="failed",
                retrieved_at=timestamp,
                error_category="redirect_limit",
                error_message="Too many redirects.",
            )

        except requests.Timeout:
            return FetchResult(
                url=url,
                status="failed",
                retrieved_at=timestamp,
                error_category="timeout",
                error_message="The source did not respond in time.",
                elapsed_seconds=round(time.monotonic() - started, 3),
            )

        except requests.RequestException:
            return FetchResult(
                url=url,
                status="failed",
                retrieved_at=timestamp,
                error_category="network_error",
                error_message=(
                    "The network request failed. Check the public source "
                    "URL and retry later."
                ),
                elapsed_seconds=round(time.monotonic() - started, 3),
            )

    def close(self):
        """Close the underlying HTTP session."""
        self.session.close()
=======

"""Respectful public webpage fetching for Project BlindSpot."""

import ipaddress
import socket
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests


USER_AGENT = (
    "ProjectBlindSpotResearch/1.0 "
    "(public vendor due diligence; contact: research@example.invalid)"
)

DEFAULT_TIMEOUT = (5, 15)
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_DELAY_SECONDS = 1.5

# Avoid fetching content that is unnecessary for this text-based prototype.
ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
}


def _is_safe_public_url(url):
    """Reject non-public destinations before any network request is made."""
    try:
        parsed = urlparse(url)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return False

        port = parsed.port
        expected_port = 443 if parsed.scheme.lower() == "https" else 80
        if port not in {None, expected_port}:
            return False

        hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii")
        try:
            addresses = [ipaddress.ip_address(hostname)]
        except ValueError:
            resolved = socket.getaddrinfo(
                hostname,
                port or (443 if parsed.scheme.lower() == "https" else 80),
                type=socket.SOCK_STREAM,
            )
            addresses = [
                ipaddress.ip_address(result[4][0])
                for result in resolved
            ]

        return bool(addresses) and all(
            address.is_global for address in addresses
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        return False


@dataclass
class FetchResult:
    url: str
    status: str
    retrieved_at: str
    http_status: int | None = None
    content_type: str = ""
    html: str = ""
    title: str = ""
    error_category: str = ""
    error_message: str = ""
    elapsed_seconds: float = 0.0

    def to_dict(self):
        return asdict(self)


class PublicPageFetcher:
    """Fetch accessible public HTML pages with basic safeguards.

    One instance should be reused for a collection run so that request
    delays and robots.txt decisions can be reused.

    This is not a browser. It does not execute JavaScript, bypass access
    controls, solve CAPTCHAs, or access authenticated content.
    """

    def __init__(
        self,
        timeout=DEFAULT_TIMEOUT,
        delay_seconds=DEFAULT_DELAY_SECONDS,
        max_bytes=DEFAULT_MAX_BYTES,
        user_agent=USER_AGENT,
    ):
        self.timeout = timeout
        self.delay_seconds = max(0.0, delay_seconds)
        self.max_bytes = max_bytes
        self.user_agent = user_agent

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml",
            }
        )

        self._last_request_by_host = {}
        self._robots_cache = {}

    @staticmethod
    def _timestamp():
        return datetime.now(timezone.utc).isoformat()

    def _wait_for_host(self, hostname):
        previous = self._last_request_by_host.get(hostname)

        if previous is not None:
            elapsed = time.monotonic() - previous
            remaining = self.delay_seconds - elapsed

            if remaining > 0:
                time.sleep(remaining)

        self._last_request_by_host[hostname] = time.monotonic()

    def _robots_allows(self, url):
        """Return whether robots.txt permits fetching this URL.

        If robots.txt cannot be retrieved or parsed, fail closed and
        leave the page uncollected for manual review.
        """
        if not _is_safe_public_url(url):
            return False

        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{origin}/robots.txt"

        if robots_url in self._robots_cache:
            return self._robots_cache[robots_url]

        try:
            response = self.session.get(
                robots_url,
                timeout=self.timeout,
                allow_redirects=False,
                stream=True,
            )

            try:
                if response.status_code != 200:
                    self._robots_cache[robots_url] = False
                    return False

                content = response.raw.read(256_000, decode_content=True)
                text = content.decode("utf-8", errors="replace")

            finally:
                response.close()

            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(text.splitlines())

            allowed = parser.can_fetch(self.user_agent, url)
            self._robots_cache[robots_url] = allowed
            return allowed

        except requests.RequestException:
            self._robots_cache[robots_url] = False
            return False

    def fetch_page(self, url):
        """Fetch one public HTML page and return a structured result."""

        started = time.monotonic()
        timestamp = self._timestamp()

        if not _is_safe_public_url(url):
            return FetchResult(
                url=url,
                status="blocked",
                retrieved_at=timestamp,
                error_category="unsafe_destination",
                error_message=(
                    "Only public HTTP(S) destinations on standard web "
                    "ports can be collected."
                ),
            )

        # Prevent requests from following redirects to arbitrary hosts.
        current_url = url

        try:
            for _ in range(4):
                parsed_current = urlparse(current_url)

                if not _is_safe_public_url(current_url):
                    return FetchResult(
                        url=url,
                        status="blocked",
                        retrieved_at=timestamp,
                        error_category="unsafe_redirect",
                        error_message="Redirect destination was rejected.",
                    )

                if not self._robots_allows(current_url):
                    return FetchResult(
                        url=url,
                        status="not_collected",
                        retrieved_at=timestamp,
                        error_category="robots_or_policy",
                        error_message=(
                            "Robots permission could not be established "
                            "or the URL was disallowed. No page was fetched."
                        ),
                    )

                self._wait_for_host(parsed_current.hostname.lower())

                response = self.session.get(
                    current_url,
                    timeout=self.timeout,
                    allow_redirects=False,
                    stream=True,
                )

                if response.is_redirect:
                    location = response.headers.get("Location")
                    response.close()

                    if not location:
                        return FetchResult(
                            url=url,
                            status="failed",
                            retrieved_at=timestamp,
                            error_category="redirect_error",
                            error_message="Redirect had no destination.",
                        )

                    current_url = urljoin(current_url, location)
                    continue

                with response:
                    http_status = response.status_code
                    content_type = (
                        response.headers.get("Content-Type", "")
                        .split(";")[0]
                        .strip()
                        .lower()
                    )

                    if http_status in {401, 403, 429}:
                        return FetchResult(
                            url=url,
                            status="not_collected",
                            retrieved_at=timestamp,
                            http_status=http_status,
                            content_type=content_type,
                            error_category="access_restricted",
                            error_message=(
                                "The source restricted access or requested "
                                "that automated collection slow down."
                            ),
                        )

                    if http_status >= 400:
                        return FetchResult(
                            url=url,
                            status="failed",
                            retrieved_at=timestamp,
                            http_status=http_status,
                            content_type=content_type,
                            error_category="http_error",
                            error_message=f"HTTP status {http_status}.",
                        )

                    if content_type not in ALLOWED_CONTENT_TYPES:
                        return FetchResult(
                            url=url,
                            status="unsupported",
                            retrieved_at=timestamp,
                            http_status=http_status,
                            content_type=content_type,
                            error_category="unsupported_content",
                            error_message=(
                                "This prototype fetches HTML pages only."
                            ),
                        )

                    declared_size = response.headers.get("Content-Length")
                    if declared_size:
                        try:
                            if int(declared_size) > self.max_bytes:
                                return FetchResult(
                                    url=url,
                                    status="unsupported",
                                    retrieved_at=timestamp,
                                    http_status=http_status,
                                    content_type=content_type,
                                    error_category="page_too_large",
                                    error_message=(
                                        "The page exceeds the configured "
                                        "maximum size."
                                    ),
                                )
                        except ValueError:
                            pass

                    body = bytearray()

                    for chunk in response.iter_content(chunk_size=16_384):
                        if not chunk:
                            continue

                        body.extend(chunk)

                        if len(body) > self.max_bytes:
                            return FetchResult(
                                url=url,
                                status="unsupported",
                                retrieved_at=timestamp,
                                http_status=http_status,
                                content_type=content_type,
                                error_category="page_too_large",
                                error_message=(
                                    "The page exceeded the configured "
                                    "maximum size while downloading."
                                ),
                            )

                    encoding = response.encoding or "utf-8"
                    html = body.decode(encoding, errors="replace")

                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, "html.parser")
                    title = (
                        soup.title.get_text(" ", strip=True)
                        if soup.title
                        else ""
                    )

                    return FetchResult(
                        url=current_url,
                        status="success",
                        retrieved_at=timestamp,
                        http_status=http_status,
                        content_type=content_type,
                        html=html,
                        title=title,
                        elapsed_seconds=round(
                            time.monotonic() - started, 3
                        ),
                    )

            return FetchResult(
                url=url,
                status="failed",
                retrieved_at=timestamp,
                error_category="redirect_limit",
                error_message="Too many redirects.",
            )

        except requests.Timeout:
            return FetchResult(
                url=url,
                status="failed",
                retrieved_at=timestamp,
                error_category="timeout",
                error_message="The source did not respond in time.",
                elapsed_seconds=round(time.monotonic() - started, 3),
            )

        except requests.RequestException:
            return FetchResult(
                url=url,
                status="failed",
                retrieved_at=timestamp,
                error_category="network_error",
                error_message=(
                    "The network request failed. Check the public source "
                    "URL and retry later."
                ),
                elapsed_seconds=round(time.monotonic() - started, 3),
            )

    def close(self):
        """Close the underlying HTTP session."""
        self.session.close()
>>>>>>> origin/main
