from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import quote

import requests

CAB_BASE_URL = "https://cab.brown.edu"
FOSE_URL = f"{CAB_BASE_URL}/api/?page=fose"

DEFAULT_HEADERS = {
    # jQuery sends this combo; the server checks X-Requested-With.
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json",
    "Referer": "https://cab.brown.edu/",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
}

# srcdb value for "Any Term (2025-26)" from foseConfig.srcDBs in the page HTML.
ANY_TERM_2025_26 = "999999"
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1.5


def _encode_body(payload: dict[str, Any]) -> str:
    """jQuery sends encodeURIComponent(JSON.stringify(data)) as the POST body.

    The server-side PHP router checks for this exact encoding — raw JSON
    returns {"fatal": "No route specified"}.
    """
    return quote(json.dumps(payload, separators=(",", ":")), safe="")


class CABClient:
    """HTTP client for the Brown CAB FOSE JSON API.

    Uses a persistent requests.Session for cookie/keep-alive reuse.
    All I/O is synchronous; wrap calls in a thread pool for concurrency.

    API notes (discovered from fose.js source):
    - Route is passed as a query-string param: ``?page=fose&route=<name>``
    - POST body must be URL-encoded JSON (encodeURIComponent of JSON.stringify)
    - Route names: ``search``, ``details``, ``promoted``
    """

    def __init__(self, delay_ms: int = 150, timeout: int = 30) -> None:
        self._delay_s = delay_ms / 1000.0
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        # Seed session cookies via a GET to the homepage.
        try:
            self._session.get(CAB_BASE_URL, timeout=self._timeout)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_all(self, srcdb: str = ANY_TERM_2025_26) -> list[dict[str, Any]]:
        """Return every section-level result for the given term.

        The FOSE API returns all matching records in a single response (no
        server-side pagination).  Callers should deduplicate by ``code`` if
        they want one record per unique course.
        """
        payload: dict[str, Any] = {
            "other": {"srcdb": srcdb},
            "criteria": [],
        }
        data = self._post_fose("search", payload)
        return list(data.get("results") or [])

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------

    def fetch_detail(
        self,
        crn: str,
        srcdb: str,
        group_code: str,
    ) -> dict[str, Any]:
        """Fetch the full detail record for one course section.

        Returns the raw JSON dict from the ``details`` route.  Key fields:
        ``code``, ``title``, ``description``, ``registration_restrictions``,
        ``meeting_html``, ``instructordetail_html``.

        Args:
            crn: Course Registration Number (e.g. ``"18181"``).
            srcdb: Specific term code (e.g. ``"202510"`` — NOT the combined
                ``"999999"``; the detail endpoint requires a real term).
            group_code: The course code string (e.g. ``"CSCI 0150"``).
        """
        payload: dict[str, Any] = {
            "group": f"code:{group_code}",
            "key": f"crn:{crn}",
            "srcdb": srcdb,
            "matched": f"crn:{crn}",
        }
        return self._post_fose("details", payload)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _post_fose(
        self,
        route: str,
        payload: dict[str, Any],
        *,
        retries: int = MAX_RETRIES,
    ) -> Any:
        url = f"{FOSE_URL}&route={route}"
        body = _encode_body(payload)
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                response = self._session.post(url, data=body, timeout=self._timeout)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and data.get("fatal"):
                    raise RuntimeError(f"FOSE fatal error: {data['fatal']}")
                return data
            except Exception as exc:
                last_exc = exc
                if attempt < retries - 1:
                    time.sleep(BACKOFF_BASE_SECONDS * (attempt + 1))
        raise RuntimeError(
            f"FOSE {route} request failed after {retries} attempts: {last_exc}"
        )

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "CABClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
