from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urljoin

import requests

from etl.cab_scraper_1.cab_extract import parse_course_html, parse_course_payload
from etl.cab_scraper_1.cab_io import atomic_write_json, load_checkpoint, save_checkpoint

CAB_BASE_URL = "https://cab.brown.edu/"
CAB_HOME_URL = "https://cab.brown.edu/#"
CAB_SEARCH_API_URL = "https://cab.brown.edu/api/?page=fose&route=search"
CAB_DETAILS_API_URL = "https://cab.brown.edu/api/?page=fose&route=details"
CHECKPOINT_PATH = Path("data/cab_checkpoint.json")
SUMMARY_PATH = Path("data/cab_run_summary.json")
DEFAULT_OUTPUT_PATH = Path("data/courses.json")

FIND_COURSES_SELECTORS = [
    "button:has-text('FIND COURSES')",
    "button:has-text('Find Courses')",
    "input[value='FIND COURSES']",
    "input[value='Find Courses']",
    "button[data-action='search']",
    "input[data-action='search']",
    "#search-button",
    "text=Find Courses",
]
NEXT_PAGE_SELECTORS = [
    "button:has-text('Next')",
    "a:has-text('Next')",
    "[aria-label='Next']",
    "[aria-label*='next']",
    ".next a",
]
COURSE_LINK_PATTERNS = (
    "crse_id=",
    "crse=",
    "crn=",
    "courseid=",
    "coursesection=",
    "#/course/",
    "#/courses/",
)
FALLBACK_SEARCH_URLS = [
    "https://cab.brown.edu/?srcdb=999999",
    "https://cab.brown.edu/?srcdb=999999&keyword=",
]
MAX_STAGNANT_DISCOVERY_STEPS = 5
MAX_STAGNANT_IN_PAGE_STEPS = 3
RESULT_ROW_HEADLINE = "h"
RESULT_ROW_PART = "p"
GROUP_URL_PREFIX = "cab://group/"
ANY_TERM_SRCDB = "999999"
REQUEST_HEADERS = {
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
MODAL_CLOSE_SELECTORS = [
    "button:has-text('Close')",
    "button:has-text('CLOSE')",
    "button[aria-label*='Close']",
    "button[aria-label*='close']",
    ".modal .close",
    ".close",
    ".btn-close",
]
COURSE_CODE_TEXT_PATTERN = re.compile(r"\b[A-Z]{2,6}\s+\d{3,4}[A-Z]?\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape CAB course data into JSON")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT_PATH)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--headless", type=parse_bool, default=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", type=parse_bool, default=True)
    parser.add_argument("--max-courses", type=int, default=0)
    parser.add_argument("--delay-ms", type=int, default=250)
    parser.add_argument("--discovery-page-limit", type=int, default=0)
    return parser.parse_args()


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    lowered = value.strip().lower()
    if lowered in {"1", "true", "t", "yes", "y"}:
        return True
    if lowered in {"0", "false", "f", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Could not parse boolean value: {value}")


def frame_targets(page: Any) -> list[Any]:
    targets = [page.main_frame]
    for frame in page.frames:
        if frame is page.main_frame:
            continue
        targets.append(frame)
    return targets


async def estimate_result_item_count(page: Any) -> int:
    total = 0
    for target in frame_targets(page):
        try:
            count = await target.evaluate(
                """() => {
                    const pattern = /\\b[A-Z]{2,6}\\s+\\d{3,4}[A-Z]?\\b/;
                    const nodes = document.querySelectorAll("a, button, tr, li, .result, .search-result");
                    let matched = 0;
                    for (const node of nodes) {
                      const text = (node.textContent || "").replace(/\\s+/g, " ").trim();
                      if (!text || text.length > 220) continue;
                      if (pattern.test(text)) matched += 1;
                    }
                    return matched;
                }"""
            )
            total += int(count or 0)
        except Exception:
            continue
    return total


def synthetic_in_page_url(seed: str) -> str:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"cab://in-page/{digest}"


async def click_first(page: Any, selectors: list[str]) -> bool:
    for target in frame_targets(page):
        for selector in selectors:
            locator = target.locator(selector)
            count = await locator.count()
            if count == 0:
                continue
            for index in range(min(count, 3)):
                candidate = locator.nth(index)
                try:
                    if not await candidate.is_visible():
                        continue
                    if not await candidate.is_enabled():
                        continue
                    await candidate.scroll_into_view_if_needed(timeout=2_000)
                    await candidate.click(timeout=1_500)
                    return True
                except Exception:
                    continue
    return False


async def set_keyword_empty(page: Any) -> None:
    keyword_selectors = [
        "input[placeholder*='Keyword']",
        "input[name*='keyword']",
        "input[type='search']",
    ]
    for target in frame_targets(page):
        for selector in keyword_selectors:
            locator = target.locator(selector).first
            if await locator.count():
                await locator.fill("")
                return


async def try_select(page: Any, option_label: str, selector_candidates: list[str]) -> bool:
    for target in frame_targets(page):
        for selector in selector_candidates:
            locator = target.locator(selector).first
            if not await locator.count():
                continue
            try:
                options = await locator.evaluate(
                    "el => Array.from(el.options || []).map(opt => (opt.textContent || '').trim())"
                )
                if option_label not in options:
                    continue
                await locator.select_option(label=option_label, timeout=2_000)
                return True
            except Exception:
                continue
    return False


async def configure_cab_search(page: Any) -> None:
    await page.goto(CAB_HOME_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(1_500)
    await set_keyword_empty(page)

    term_selected = await try_select(
        page,
        "Any Term (2025-26)",
        ["select[name='srcdb']", "select[id*='srcdb']"],
    )
    mode_selected = await try_select(
        page,
        "All Modes of Instruction",
        ["#crit-camp", "select[id*='camp']", "select[name*='camp']"],
    )
    scope_selected = await try_select(
        page,
        "All Courses",
        ["#crit-coursetype", "select[id*='coursetype']", "select[name*='coursetype']"],
    )
    print(
        "[run] filter selection",
        f"term_selected={term_selected}",
        f"mode_selected={mode_selected}",
        f"scope_selected={scope_selected}",
    )

    baseline_items = await estimate_result_item_count(page)
    print("[run] result-item baseline", baseline_items)

    for _ in range(6):
        clicked = await click_first(page, FIND_COURSES_SELECTORS)
        if clicked:
            await page.wait_for_timeout(1_200)
            after_click_items = await estimate_result_item_count(page)
            print("[run] search click attempt", f"clicked={clicked}", f"result_items={after_click_items}")
            if after_click_items > max(baseline_items, 0):
                return
        else:
            await page.wait_for_timeout(400)

    for target in frame_targets(page):
        keyword_input = target.locator("input[placeholder*='Keyword'], input[name*='keyword'], input[type='search']").first
        if not await keyword_input.count():
            continue
        try:
            await keyword_input.click(timeout=2_000)
            await target.keyboard.press("Enter")
            await page.wait_for_timeout(1_000)
            after_enter_items = await estimate_result_item_count(page)
            print("[run] enter-key search attempt", f"result_items={after_enter_items}")
            if after_enter_items > max(baseline_items, 0):
                return
            break
        except Exception:
            continue

    js_clicked = await page.evaluate(
        """() => {
            const byId = ["search-button", "search-button-sticky"];
            for (const id of byId) {
              const node = document.getElementById(id);
              if (!node) continue;
              node.click();
              return true;
            }
            const nodes = Array.from(document.querySelectorAll("button, input[type='button'], input[type='submit']"));
            const searchNode = nodes.find((node) => /find courses/i.test((node.value || node.textContent || "").trim()));
            if (searchNode) {
              searchNode.click();
              return true;
            }
            return false;
        }"""
    )
    if js_clicked:
        await page.wait_for_timeout(1_000)
        after_js_items = await estimate_result_item_count(page)
        print("[run] js search attempt", f"result_items={after_js_items}")
        if after_js_items > max(baseline_items, 0):
            return

    # Fallback when the dynamic search UI fails to render interactable controls.
    for fallback_url in FALLBACK_SEARCH_URLS:
        await page.goto(fallback_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1_500)
        if await click_first(page, FIND_COURSES_SELECTORS):
            await page.wait_for_timeout(1_000)
            item_count = await estimate_result_item_count(page)
            print("[run] fallback search click", f"url={fallback_url}", f"result_items={item_count}")
            if item_count > 0:
                return

        links = await collect_course_links(page)
        if links:
            return
        in_page_items = await estimate_result_item_count(page)
        if in_page_items > 0:
            return

    raise RuntimeError(
        "Could not find FIND COURSES controls or course links on CAB. "
        "Try --headless false and verify CAB loads in your browser profile."
    )


def is_course_link(url: str) -> bool:
    lowered = url.lower()
    if any(pattern in lowered for pattern in COURSE_LINK_PATTERNS):
        return True
    if "srcdb=" in lowered and ("crse=" in lowered or "crn=" in lowered):
        return True
    return False


def normalize_url(url: str) -> str:
    raw = url.strip()
    if not raw:
        return raw
    if raw.startswith("#/"):
        return f"{CAB_BASE_URL}{raw}"
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return urljoin(CAB_BASE_URL, raw)


async def collect_course_links(page: Any) -> list[str]:
    raw_values: list[str] = []
    for target in frame_targets(page):
        frame_values = await target.eval_on_selector_all(
            "a[href], [data-href], [data-url], [data-course-url], [data-link], [onclick]",
            """nodes => {
              const values = [];
              for (const node of nodes) {
                for (const attr of ["href", "data-href", "data-url", "data-course-url", "data-link", "onclick"]) {
                  const value = node.getAttribute(attr);
                  if (value) values.push(value);
                }
              }
              return values;
            }""",
        )
        raw_values.extend(frame_values)

    potential_links: list[str] = []
    for raw in raw_values:
        if "javascript:" in raw.lower():
            continue
        normalized = normalize_url(raw)
        if normalized:
            potential_links.append(normalized)

    links = [value for value in potential_links if is_course_link(value)]
    # Preserve order while deduping.
    ordered: list[str] = []
    seen: set[str] = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        ordered.append(link)

    if not ordered and potential_links:
        sample = potential_links[:10]
        print("[discovery] no course-pattern matches. candidate link sample:", sample)

    return ordered


async def try_go_next_page(page: Any) -> bool:
    for target in frame_targets(page):
        for selector in NEXT_PAGE_SELECTORS:
            locator = target.locator(selector).first
            if not await locator.count():
                continue

            disabled_attr = await locator.get_attribute("disabled")
            class_attr = (await locator.get_attribute("class")) or ""
            if disabled_attr is not None or "disabled" in class_attr.lower():
                continue

            try:
                await locator.click()
                await page.wait_for_timeout(700)
                return True
            except Exception:
                continue
    return False


async def discover_course_urls(
    page: Any,
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
    page_limit: int,
) -> list[str]:
    discovered = checkpoint.get("discovered_urls", [])
    seen = set(discovered)
    discovered_urls = list(discovered)

    pages_visited = 0
    stagnant_steps = 0
    last_signature: tuple[int, str | None, str | None] | None = None
    while True:
        page_links = await collect_course_links(page)
        before_count = len(discovered_urls)
        for link in page_links:
            if link in seen:
                continue
            seen.add(link)
            discovered_urls.append(link)

        added = len(discovered_urls) - before_count
        checkpoint["discovered_urls"] = discovered_urls
        save_checkpoint(checkpoint_path, checkpoint)

        pages_visited += 1
        signature = (
            len(page_links),
            page_links[0] if page_links else None,
            page_links[-1] if page_links else None,
        )
        if signature == last_signature and added == 0:
            stagnant_steps += 1
        else:
            stagnant_steps = 0
        last_signature = signature

        print(
            "[discovery]",
            f"page={pages_visited}",
            f"links_on_page={len(page_links)}",
            f"new_links={added}",
            f"total_discovered={len(discovered_urls)}",
            f"stagnant_steps={stagnant_steps}",
        )

        if page_limit > 0 and pages_visited >= page_limit:
            print("[discovery] hit discovery page limit, stopping pagination")
            break
        if stagnant_steps >= MAX_STAGNANT_DISCOVERY_STEPS:
            print("[discovery] pagination appears stagnant, stopping pagination")
            break
        moved = await try_go_next_page(page)
        if not moved:
            print("[discovery] next-page control not available, stopping pagination")
            break

    return discovered_urls


def build_group_course_url(srcdb: str, group: str, key: str, matched: str) -> str:
    encoded = {
        "srcdb": quote(srcdb, safe=""),
        "group": quote(group, safe=""),
        "key": quote(key, safe=""),
        "matched": quote(matched, safe=""),
    }
    return (
        f"{GROUP_URL_PREFIX}"
        f"{encoded['srcdb']}/{encoded['group']}/{encoded['key']}/{encoded['matched']}"
    )


def parse_group_course_url(course_url: str) -> dict[str, str] | None:
    if not course_url.startswith(GROUP_URL_PREFIX):
        return None
    raw = course_url[len(GROUP_URL_PREFIX) :]
    parts = raw.split("/")
    if len(parts) < 4:
        return None
    srcdb, group, key, matched = parts[:4]
    return {
        "srcdb": unquote(srcdb),
        "group": unquote(group),
        "key": unquote(key),
        "matched": unquote(matched),
    }


def normalize_result_rows(rows: Any, srcdb_fallback: str = "") -> list[dict[str, str]]:
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_type = str(row.get("type") or "").strip()
        if row_type not in {RESULT_ROW_HEADLINE, RESULT_ROW_PART}:
            continue
        row_data = row.get("data")
        row_data = row_data if isinstance(row_data, dict) else {}
        srcdb = str(row_data.get("srcdb") or srcdb_fallback or "").strip()
        group = str(row.get("group") or "").strip()
        if not srcdb or not group:
            continue
        normalized.append(
            {
                "type": row_type,
                "srcdb": srcdb,
                "group": group,
                "key": str(row.get("key") or "").strip(),
                "matched": str(row.get("matched") or "").strip(),
                "code": str(row_data.get("code") or "").strip(),
                "title": str(row_data.get("title") or "").strip(),
            }
        )
    return normalized


def build_detail_targets(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    headlines = [row for row in rows if row.get("type") == RESULT_ROW_HEADLINE]
    parts = [row for row in rows if row.get("type") == RESULT_ROW_PART]
    source = headlines if headlines else parts
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in source:
        srcdb = (row.get("srcdb") or "").strip()
        group = (row.get("group") or "").strip()
        key = (row.get("key") or "").strip()
        matched = (row.get("matched") or "").strip()
        if not srcdb or not group:
            continue
        course_url = build_group_course_url(srcdb=srcdb, group=group, key=key, matched=matched)
        if course_url in seen:
            continue
        seen.add(course_url)
        deduped.append(
            {
                "course_url": course_url,
                "srcdb": srcdb,
                "group": group,
                "key": key,
                "matched": matched,
                "code": (row.get("code") or "").strip(),
                "title": (row.get("title") or "").strip(),
            }
        )
    return deduped


async def wait_for_results_panel(page: Any, timeout_ms: int = 20_000) -> dict[str, Any]:
    try:
        await page.wait_for_function(
            """() => {
                const panel = window.fose && fose.panels && fose.panels.last && fose.panels.last();
                if (!(panel && panel.isKind && panel.isKind('results') && panel.data)) return false;
                const data = panel.data() || {};
                const server = data.server || {};
                if (Number(server.count || 0) === 0) return true;
                return Array.isArray(server.results) && server.results.length > 0;
            }""",
            timeout=timeout_ms,
        )
    except Exception:
        pass

    state = await page.evaluate(
        """() => {
            const panel = window.fose && fose.panels && fose.panels.last && fose.panels.last();
            if (!panel || !panel.data) {
                return {has_panel: false, is_results: false, count: 0, row_count: 0};
            }
            const data = panel.data() || {};
            const server = data.server || {};
            const results = server.results || [];
            return {
                has_panel: true,
                is_results: !!(panel.isKind && panel.isKind('results')),
                count: Number(server.count || 0),
                row_count: Array.isArray(results) ? results.length : 0,
            };
        }"""
    )
    return state if isinstance(state, dict) else {}


async def collect_detail_targets_from_results_panel(page: Any) -> list[dict[str, str]]:
    panel_state = await page.evaluate(
        """() => {
            const panel = window.fose && fose.panels && fose.panels.last && fose.panels.last();
            if (!panel || !panel.isKind || !panel.isKind('results') || !panel.data) {
                return {rows: [], srcdb: ''};
            }
            const data = panel.data() || {};
            const results = (data.server || {}).results || [];
            const srcdb = String((data.client || {}).srcdb || '').trim();
            return {rows: results, srcdb};
        }"""
    )

    if not isinstance(panel_state, dict):
        return []
    rows = normalize_result_rows(panel_state.get("rows"), srcdb_fallback=str(panel_state.get("srcdb") or ""))
    return build_detail_targets(rows)


def create_http_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    try:
        session.get(CAB_BASE_URL, timeout=20)
    except Exception:
        # Session cookies are helpful but not strictly required.
        pass
    return session


def post_fose_json(
    route_url: str,
    payload: dict[str, Any],
    timeout_s: int = 30,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    body = quote(json.dumps(payload, separators=(",", ":")), safe="")
    client = session or requests
    response = client.post(
        route_url,
        data=body,
        headers=REQUEST_HEADERS if session is None else None,
        timeout=timeout_s,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and data.get("fatal"):
        raise RuntimeError(str(data["fatal"]))
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected API response shape from CAB.")
    return data


def fetch_search_targets_from_api(
    srcdb: str = ANY_TERM_SRCDB,
    session: requests.Session | None = None,
) -> list[dict[str, str]]:
    payload = {
        "other": {
            "srcdb": srcdb,
        },
        "criteria": [],
    }
    response = post_fose_json(CAB_SEARCH_API_URL, payload=payload, session=session)
    rows = normalize_result_rows(response.get("results"), srcdb_fallback=srcdb)
    return build_detail_targets(rows)


def fetch_course_record_from_detail_api(
    course_url: str,
    detail_target: dict[str, str],
    session: requests.Session | None = None,
) -> dict[str, Any]:
    payload = {
        "group": detail_target.get("group", ""),
        "key": detail_target.get("key", ""),
        "srcdb": detail_target.get("srcdb", ""),
        "matched": detail_target.get("matched", ""),
    }
    details = post_fose_json(CAB_DETAILS_API_URL, payload=payload, session=session)
    return parse_course_payload(details, course_url=course_url).to_dict()


async def collect_in_page_course_candidates(page: Any) -> list[dict[str, Any]]:
    script = """() => {
        const pattern = /\\b[A-Z]{2,6}\\s+\\d{3,4}[A-Z]?\\b/;
        const maxCandidates = 300;
        function normalize(value) {
          return (value || "").replace(/\\s+/g, " ").trim();
        }
        function xpathFor(el) {
          if (!el || el.nodeType !== 1) return "";
          if (el.id) return `//*[@id="${String(el.id).replace(/"/g, '\\"')}"]`;
          const parts = [];
          let cursor = el;
          while (cursor && cursor.nodeType === 1 && parts.length < 10) {
            let index = 1;
            let sibling = cursor.previousElementSibling;
            while (sibling) {
              if (sibling.tagName === cursor.tagName) index += 1;
              sibling = sibling.previousElementSibling;
            }
            parts.unshift(`${cursor.tagName.toLowerCase()}[${index}]`);
            cursor = cursor.parentElement;
          }
          return "/" + parts.join("/");
        }
        const roots = Array.from(
          document.querySelectorAll(
            "[id*='search-result'], [class*='search-result'], [id*='results'], [class*='results'], [id*='course'], [class*='course']"
          )
        );
        if (roots.length === 0) roots.push(document.body);

        const out = [];
        const seen = new Set();
        for (const root of roots) {
          const nodes = Array.from(root.querySelectorAll("a,button,[role='button'],[onclick],tr,li,div"));
          for (const node of nodes) {
            const text = normalize(node.innerText || node.textContent);
            if (!text || text.length > 1600) continue;
            const match = text.match(pattern);
            if (!match) continue;
            const courseCode = normalize(match[0]);
            if (!courseCode) continue;

            let clickable = null;
            if (node.matches("a,button,[role='button'],[onclick]")) {
              clickable = node;
            } else {
              clickable = node.querySelector("a,button,[role='button'],[onclick]") || node.closest("a,button,[role='button'],[onclick]");
            }
            if (!clickable) {
              clickable = node;
            }

            const rect = clickable.getBoundingClientRect();
            if (!rect || rect.width < 2 || rect.height < 2) continue;
            const style = window.getComputedStyle(clickable);
            if (!style || style.visibility === "hidden" || style.display === "none") continue;

            const href = normalize(
              clickable.getAttribute("href") ||
              clickable.getAttribute("data-href") ||
              clickable.getAttribute("data-url") ||
              clickable.getAttribute("data-course-url")
            );
            const key = href || `${courseCode}|${text.slice(0, 100)}`;
            if (seen.has(key)) continue;
            seen.add(key);

            out.push({
              key,
              code: courseCode,
              text: text.slice(0, 220),
              href,
              xpath: xpathFor(clickable),
            });
            if (out.length >= maxCandidates) break;
          }
          if (out.length >= maxCandidates) break;
        }
        return out;
    }"""

    deduped: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    frames = frame_targets(page)
    for frame_index, target in enumerate(frames):
        try:
            entries = await target.evaluate(script)
        except Exception:
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            key = (entry.get("key") or entry.get("text") or "").strip()
            xpath = (entry.get("xpath") or "").strip()
            if not key or not xpath or key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(
                {
                    "key": key,
                    "text": (entry.get("text") or "").strip(),
                    "href": (entry.get("href") or "").strip(),
                    "xpath": xpath,
                    "frame_index": frame_index,
                }
            )
    return deduped


async def wait_for_detail_frame(page: Any, timeout_ms: int = 8_000) -> Any | None:
    attempts = max(1, timeout_ms // 250)
    for _ in range(attempts):
        for target in frame_targets(page):
            locator = target.locator(".dtl-course-code").first
            if not await locator.count():
                continue
            text = await locator.text_content()
            if text and text.strip():
                return target
        await page.wait_for_timeout(250)
    return None


async def close_course_detail(page: Any) -> None:
    for target in frame_targets(page):
        for selector in MODAL_CLOSE_SELECTORS:
            locator = target.locator(selector)
            count = await locator.count()
            if count == 0:
                continue
            for index in range(min(count, 6)):
                candidate = locator.nth(index)
                try:
                    if not await candidate.is_visible():
                        continue
                    await candidate.click(timeout=2_000)
                    await page.wait_for_timeout(250)
                    return
                except Exception:
                    continue
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(250)
    except Exception:
        return


async def open_candidate_detail(page: Any, candidate: dict[str, Any]) -> bool:
    frames = frame_targets(page)
    frame_index = int(candidate.get("frame_index", 0))
    if frame_index >= len(frames):
        return False
    target = frames[frame_index]
    xpath = candidate.get("xpath", "")
    if not xpath:
        return False
    locator = target.locator(f"xpath={xpath}").first
    if not await locator.count():
        return False
    try:
        if not await locator.is_visible():
            return False
        await locator.scroll_into_view_if_needed(timeout=2_000)
        await locator.click(timeout=4_000, force=True)
        return True
    except Exception:
        try:
            clicked = await target.evaluate(
                """xpath => {
                    const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                    const node = result.singleNodeValue;
                    if (!node) return false;
                    node.click();
                    return true;
                }""",
                xpath,
            )
            return bool(clicked)
        except Exception:
            return False


async def scrape_in_page_modal_courses(
    page: Any,
    args: argparse.Namespace,
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
    records_by_url: dict[str, dict[str, Any]],
) -> tuple[list[str], set[str], dict[str, str], dict[str, dict[str, Any]]]:
    discovered_urls = list(checkpoint.get("discovered_urls", []))
    discovered_set = set(discovered_urls)
    completed_urls = set(checkpoint.get("completed_urls", []))
    failed_urls = dict(checkpoint.get("failed_urls", {}))

    page_number = 0
    stagnant_steps = 0
    last_signature: tuple[int, str | None, str | None] | None = None

    while True:
        page_number += 1
        candidates = await collect_in_page_course_candidates(page)
        signature = (
            len(candidates),
            candidates[0]["key"] if candidates else None,
            candidates[-1]["key"] if candidates else None,
        )
        if signature == last_signature:
            stagnant_steps += 1
        else:
            stagnant_steps = 0
        last_signature = signature

        print(
            "[in-page]",
            f"page={page_number}",
            f"candidates={len(candidates)}",
            f"stagnant_steps={stagnant_steps}",
        )
        if candidates:
            sample = [f"{row.get('code','?')}::{row.get('text','')[:80]}" for row in candidates[:5]]
            print("[in-page] candidate sample:", sample)

        if not candidates and stagnant_steps >= MAX_STAGNANT_IN_PAGE_STEPS:
            break

        for index, candidate in enumerate(candidates, start=1):
            seed = candidate.get("href") or candidate.get("key") or f"{page_number}-{index}"
            normalized_href = normalize_url(candidate.get("href", "")) if candidate.get("href") else ""
            course_url = normalized_href if (normalized_href and is_course_link(normalized_href)) else synthetic_in_page_url(seed)

            if course_url not in discovered_set:
                discovered_set.add(course_url)
                discovered_urls.append(course_url)

            if course_url in completed_urls:
                continue

            if args.max_courses > 0 and len(completed_urls) >= args.max_courses:
                break

            opened = await open_candidate_detail(page, candidate)
            if not opened:
                failed_urls[course_url] = f"Could not open result row: {candidate.get('text', '')[:120]}"
                continue

            detail_frame = await wait_for_detail_frame(page)
            if not detail_frame:
                failed_urls[course_url] = "Detail modal did not appear after click."
                await close_course_detail(page)
                continue

            try:
                html = await detail_frame.content()
                record = parse_course_html(html=html, course_url=course_url).to_dict()
                if not record.get("course_code"):
                    code_match = COURSE_CODE_TEXT_PATTERN.search(candidate.get("text", ""))
                    if code_match:
                        record["course_code"] = code_match.group(0)
                records_by_url[course_url] = record
                completed_urls.add(course_url)
                failed_urls.pop(course_url, None)
            except Exception as exc:
                failed_urls[course_url] = f"Modal parse failure: {exc}"
            finally:
                await close_course_detail(page)
                await page.wait_for_timeout(args.delay_ms + random.randint(0, 150))

            checkpoint["discovered_urls"] = discovered_urls
            checkpoint["completed_urls"] = sorted(completed_urls)
            checkpoint["failed_urls"] = failed_urls
            save_checkpoint(checkpoint_path, checkpoint)

        checkpoint["discovered_urls"] = discovered_urls
        checkpoint["completed_urls"] = sorted(completed_urls)
        checkpoint["failed_urls"] = failed_urls
        save_checkpoint(checkpoint_path, checkpoint)

        if args.max_courses > 0 and len(completed_urls) >= args.max_courses:
            break
        if stagnant_steps >= MAX_STAGNANT_IN_PAGE_STEPS:
            break
        moved = await try_go_next_page(page)
        if not moved:
            break
        await page.wait_for_timeout(800)

    return discovered_urls, completed_urls, failed_urls, records_by_url


async def fetch_course_record(context: Any, course_url: str, delay_ms: int) -> dict[str, Any]:
    page = await context.new_page()
    try:
        await page.goto(course_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(delay_ms + random.randint(0, 150))
        html = await page.content()
        course = parse_course_html(html=html, course_url=course_url)
        return course.to_dict()
    finally:
        await page.close()


async def run_scraper(args: argparse.Namespace) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    print("[run] starting CAB scrape")
    print(
        "[run]",
        f"out={args.out}",
        f"checkpoint={args.checkpoint}",
        f"workers={args.workers}",
        f"resume={args.resume}",
        f"headless={args.headless}",
    )

    checkpoint = load_checkpoint(args.checkpoint) if args.resume else {
        "discovered_urls": [],
        "completed_urls": [],
        "failed_urls": {},
        "detail_targets": {},
    }
    discovered_urls = list(checkpoint.get("discovered_urls", []))
    completed_urls = set(checkpoint.get("completed_urls", []))
    failed_urls = dict(checkpoint.get("failed_urls", {}))
    detail_targets: dict[str, dict[str, str]] = dict(checkpoint.get("detail_targets", {}))
    legacy_in_page_urls = [url for url in discovered_urls if url.startswith("cab://in-page/")]
    if legacy_in_page_urls:
        print(
            "[run] dropping legacy in-page checkpoint URLs",
            f"count={len(legacy_in_page_urls)}",
        )
        discovered_urls = [url for url in discovered_urls if not url.startswith("cab://in-page/")]
        completed_urls = {url for url in completed_urls if url in discovered_urls}
        failed_urls = {url: err for url, err in failed_urls.items() if url in discovered_urls}
        checkpoint["discovered_urls"] = discovered_urls
        checkpoint["completed_urls"] = sorted(completed_urls)
        checkpoint["failed_urls"] = failed_urls
        save_checkpoint(args.checkpoint, checkpoint)

    is_group_checkpoint = discovered_urls and all(url.startswith(GROUP_URL_PREFIX) for url in discovered_urls)
    if args.resume and is_group_checkpoint and detail_targets and len(discovered_urls) < 50:
        print(
            "[run] checkpoint target list appears incomplete; forcing API rediscovery",
            f"checkpoint_targets={len(discovered_urls)}",
        )
        discovered_urls = []
        detail_targets = {}
        checkpoint["discovered_urls"] = []
        checkpoint["detail_targets"] = {}
        save_checkpoint(args.checkpoint, checkpoint)

    existing_by_url: dict[str, dict[str, Any]] = {}
    if args.resume and args.out.exists():
        payload = json_safe_list(args.out)
        existing_by_url = {
            row.get("course_url"): row for row in payload if isinstance(row, dict) and row.get("course_url")
        }
    records_by_url = dict(existing_by_url)

    browser = None
    context = None
    playwright = None
    http_session = create_http_session()
    try:
        if discovered_urls:
            print("[run] using URLs from checkpoint", f"urls={len(discovered_urls)}")
        else:
            print("[run] discovering courses via CAB search API")
            try:
                result_targets = await asyncio.to_thread(
                    fetch_search_targets_from_api,
                    ANY_TERM_SRCDB,
                    http_session,
                )
            except Exception as exc:
                result_targets = []
                print("[run] API discovery failed", f"error={exc}")
            if result_targets:
                detail_targets = {
                    target["course_url"]: {
                        "srcdb": target.get("srcdb", ""),
                        "group": target.get("group", ""),
                        "key": target.get("key", ""),
                        "matched": target.get("matched", ""),
                    }
                    for target in result_targets
                }
                discovered_urls = list(detail_targets.keys())
                checkpoint["discovered_urls"] = discovered_urls
                checkpoint["detail_targets"] = detail_targets
                save_checkpoint(args.checkpoint, checkpoint)
                sample = [f"{row.get('code', '?')}::{row.get('title', '')[:72]}" for row in result_targets[:5]]
                print("[run] API discovery complete", f"targets={len(discovered_urls)}")
                if sample:
                    print("[run] API target sample:", sample)

        if discovered_urls and not detail_targets and any(
            url.startswith(GROUP_URL_PREFIX) for url in discovered_urls
        ):
            print("[run] rebuilding missing detail targets via CAB search API")
            try:
                result_targets = await asyncio.to_thread(
                    fetch_search_targets_from_api,
                    ANY_TERM_SRCDB,
                    http_session,
                )
            except Exception as exc:
                result_targets = []
                print("[run] target rebuild failed", f"error={exc}")
            if result_targets:
                detail_targets = {
                    target["course_url"]: {
                        "srcdb": target.get("srcdb", ""),
                        "group": target.get("group", ""),
                        "key": target.get("key", ""),
                        "matched": target.get("matched", ""),
                    }
                    for target in result_targets
                }
                discovered_urls = list(detail_targets.keys())
                checkpoint["discovered_urls"] = discovered_urls
                checkpoint["detail_targets"] = detail_targets
                save_checkpoint(args.checkpoint, checkpoint)
                print("[run] rebuilt detail targets", f"targets={len(discovered_urls)}")

        if not discovered_urls:
            print("[run] API discovery yielded 0 results, using browser fallback")
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise RuntimeError(
                    "playwright is required for browser fallback discovery. Install dependencies and run "
                    "`python -m playwright install chromium`."
                ) from exc

            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=args.headless)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                print("[run] configuring CAB search filters")
                await configure_cab_search(page)
                results_state = await wait_for_results_panel(page)
                print(
                    "[run] results panel",
                    f"is_results={results_state.get('is_results', False)}",
                    f"count={results_state.get('count', 0)}",
                    f"rows={results_state.get('row_count', 0)}",
                )

                result_targets = await collect_detail_targets_from_results_panel(page)
                if result_targets:
                    detail_targets = {
                        target["course_url"]: {
                            "srcdb": target.get("srcdb", ""),
                            "group": target.get("group", ""),
                            "key": target.get("key", ""),
                            "matched": target.get("matched", ""),
                        }
                        for target in result_targets
                    }
                    discovered_urls = list(detail_targets.keys())
                    checkpoint["detail_targets"] = detail_targets
                    checkpoint["discovered_urls"] = discovered_urls
                    save_checkpoint(args.checkpoint, checkpoint)
                    print("[run] collected detail targets from browser panel", f"targets={len(discovered_urls)}")
                else:
                    print("[run] no detail targets from panel model, trying URL discovery fallback")
                    discovered_urls = await discover_course_urls(
                        page=page,
                        checkpoint=checkpoint,
                        checkpoint_path=args.checkpoint,
                        page_limit=args.discovery_page_limit,
                    )
                    print("[run] URL discovery complete", f"urls={len(discovered_urls)}")
                    if not discovered_urls:
                        print("[run] switching to in-page modal crawl mode")
                        discovered_urls, completed_urls, failed_urls, records_by_url = await scrape_in_page_modal_courses(
                            page=page,
                            args=args,
                            checkpoint=checkpoint,
                            checkpoint_path=args.checkpoint,
                            records_by_url=records_by_url,
                        )
                        print(
                            "[run] in-page crawl complete",
                            f"discovered={len(discovered_urls)}",
                            f"completed={len(completed_urls)}",
                            f"failed={len(failed_urls)}",
                        )
            finally:
                await page.close()

        if not discovered_urls and not records_by_url:
            raise RuntimeError(
                "CAB search completed but no course data was discovered. "
                "Try --headless false and verify the results list appears after FIND COURSES."
            )

        pending = [url for url in discovered_urls if url not in completed_urls]
        if args.max_courses > 0:
            pending = pending[: args.max_courses]
        print(
            "[run]",
            f"pending={len(pending)}",
            f"already_completed={len(completed_urls)}",
            f"failed_so_far={len(failed_urls)}",
        )

        needs_browser_fetch = any(
            not detail_targets.get(url) and not parse_group_course_url(url)
            for url in pending
        )
        if needs_browser_fetch and context is None:
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise RuntimeError(
                    "playwright is required for URL-based course fetch fallback. Install dependencies and run "
                    "`python -m playwright install chromium`."
                ) from exc
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=args.headless)
            context = await browser.new_context()

        semaphore = asyncio.Semaphore(max(args.workers, 1))

        async def bounded_fetch(url: str) -> tuple[str, dict[str, Any] | None, str | None]:
            async with semaphore:
                for attempt in range(3):
                    try:
                        target = detail_targets.get(url)
                        if not target:
                            parsed_target = parse_group_course_url(url)
                            if parsed_target:
                                target = parsed_target
                        if target:
                            record = await asyncio.to_thread(
                                fetch_course_record_from_detail_api,
                                url,
                                target,
                            )
                        else:
                            if context is None:
                                raise RuntimeError("No browser context available for URL fetch fallback.")
                            record = await fetch_course_record(
                                context=context,
                                course_url=url,
                                delay_ms=args.delay_ms,
                            )
                        return url, record, None
                    except Exception as exc:  # noqa: PERF203
                        if attempt == 2:
                            return url, None, str(exc)
                        await asyncio.sleep(1.2 * (attempt + 1))
            return url, None, "Unreachable"

        tasks = [asyncio.create_task(bounded_fetch(url)) for url in pending]
        processed_count = 0
        if not tasks:
            print("[run] no pending courses to scrape")
        for task in asyncio.as_completed(tasks):
            url, record, error = await task
            processed_count += 1
            if record:
                records_by_url[url] = record
                completed_urls.add(url)
                failed_urls.pop(url, None)
            else:
                failed_urls[url] = error or "Unknown extraction failure"

            checkpoint["completed_urls"] = sorted(completed_urls)
            checkpoint["failed_urls"] = failed_urls
            checkpoint["discovered_urls"] = discovered_urls
            checkpoint["detail_targets"] = detail_targets
            save_checkpoint(args.checkpoint, checkpoint)

            if processed_count % 25 == 0 or processed_count == len(tasks):
                ordered_records = ordered_records_from_urls(
                    records_by_url=records_by_url,
                    discovered_urls=discovered_urls,
                )
                atomic_write_json(args.out, ordered_records)
                print(
                    "[scrape]",
                    f"processed={processed_count}/{len(tasks)}",
                    f"success={len(completed_urls)}",
                    f"failed={len(failed_urls)}",
                )
    finally:
        http_session.close()
        if context is not None:
            await context.close()
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()

    checkpoint["discovered_urls"] = discovered_urls
    checkpoint["detail_targets"] = detail_targets
    checkpoint["completed_urls"] = sorted(completed_urls)
    checkpoint["failed_urls"] = failed_urls
    save_checkpoint(args.checkpoint, checkpoint)
    final_records = ordered_records_from_urls(records_by_url=records_by_url, discovered_urls=discovered_urls)
    atomic_write_json(args.out, final_records)

    ended_at = datetime.now(UTC).isoformat()
    summary = {
        "started_at": started_at,
        "ended_at": ended_at,
        "filters": {
            "course_scope": "All Courses",
            "term": "Any Term (2025-26)",
            "mode_of_instruction": "All Modes of Instruction",
            "keyword": "",
        },
        "counts": {
            "discovered_urls": len(discovered_urls),
            "completed_urls": len(completed_urls),
            "failed_urls": len(failed_urls),
            "output_records": len(final_records),
        },
        "failed_urls": failed_urls,
        "output_path": str(args.out),
        "checkpoint_path": str(args.checkpoint),
    }
    atomic_write_json(args.summary, summary)
    return summary


def ordered_records_from_urls(
    records_by_url: dict[str, dict[str, Any]],
    discovered_urls: list[str],
) -> list[dict[str, Any]]:
    ordered_records = []
    seen: set[str] = set()
    for url in discovered_urls:
        record = records_by_url.get(url)
        if not record or url in seen:
            continue
        ordered_records.append(record)
        seen.add(url)
    return ordered_records


def json_safe_list(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, list):
        return []
    return [item for item in loaded if isinstance(item, dict)]


def main() -> None:
    args = parse_args()
    summary = asyncio.run(run_scraper(args))
    print(
        "Completed CAB scrape:",
        f"records={summary['counts']['output_records']}",
        f"failed={summary['counts']['failed_urls']}",
        f"out={summary['output_path']}",
    )


if __name__ == "__main__":
    main()
