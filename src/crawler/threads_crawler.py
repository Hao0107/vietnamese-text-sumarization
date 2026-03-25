"""
threads_crawler.py — Crawl Vietnamese public Threads.net posts via Playwright.

Strategy: CDP Network intercept (more reliable than response events) +
          aggressive anti-ban measures.

Anti-ban measures implemented:
  1. Rotating user-agent pool (desktop + mobile Chrome)
  2. Random viewport sizes per session
  3. Human-like mouse movement before scrolling
  4. Random scroll amounts and pauses
  5. Exponential backoff on failure / HTTP 429
  6. Context rotation after N pages (fresh fingerprint)
  7. Stealth JS injection (navigator.webdriver, plugins, languages)
  8. Random extra browser headers
  9. CDP Network.enable + requestPaused for low-level intercept
  10. Realistic browser timing (domcontentloaded vs networkidle)

Setup:
  pip install playwright pymongo apscheduler
  playwright install chromium

Usage:
  python threads_crawler.py --once --limit 1000
  python threads_crawler.py --limit 500 --hour 6
"""
import json
import logging
import time
import random
import threading
import argparse
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

from pymongo import MongoClient
from apscheduler.schedulers.blocking import BlockingScheduler

from threads_source import (
    THREADS_ACCOUNTS,
    THREADS_HASHTAGS,
    THREADS_MIN_CHARS,
    THREADS_MAX_PER_USER,
    THREADS_SCROLL_DELAY_MIN,
    THREADS_SCROLL_DELAY_MAX,
    THREADS_PAGE_DELAY_MIN,
    THREADS_PAGE_DELAY_MAX,
    THREADS_SESSION_MAX_PAGES,
    THREADS_MAX_SCROLLS_USER,
    THREADS_MAX_SCROLLS_TAG,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            Path(__file__).resolve().parents[2] / "logs" / "threads_crawler.log",
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)   

# ── MongoDB ────────────────────────────────────────────────────────────────────
mongo = MongoClient("mongodb://mongodb:27017/")
db    = mongo["nlp_database"]
col   = db["social_posts"]
col.create_index([("post_id", 1), ("platform", 1)], unique=True)

# ── Global counters ────────────────────────────────────────────────────────────
_lock  = threading.Lock()
_saved = 0

def inc() -> int:
    global _saved
    with _lock:
        _saved += 1
        return _saved

def reset():
    global _saved
    with _lock:
        _saved = 0

# ── Anti-ban: User-agent pool ─────────────────────────────────────────────────
# Mix of desktop Chrome versions and one Android UA for variety
USER_AGENTS = [
    # Desktop Chrome — Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Desktop Chrome — macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Desktop Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:123.0) Gecko/20100101 Firefox/123.0",
    # Mobile Chrome — Android (Threads is primarily mobile)
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
]

# ── Anti-ban: Viewport pool ────────────────────────────────────────────────────
VIEWPORTS = [
    {"width": 1280, "height": 800},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
    {"width": 390,  "height": 844},   # iPhone 14
    {"width": 412,  "height": 915},   # Pixel 7
]

# ── Anti-ban: Stealth JS ───────────────────────────────────────────────────────
STEALTH_JS = """
// Mask automation flags
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', {
    get: () => ['vi-VN', 'vi', 'en-US', 'en']
});
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// Mask Playwright-specific chrome object gaps
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {},
};

// Prevent detection via permission query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);

// Randomise canvas fingerprint slightly
const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {
    const ctx = this.getContext('2d');
    if (ctx) {
        const imgData = ctx.getImageData(0, 0, this.width, this.height);
        for (let i = 0; i < 10; i++) {
            const idx = Math.floor(Math.random() * imgData.data.length / 4) * 4;
            imgData.data[idx]     = imgData.data[idx]     ^ (Math.random() * 5 | 0);
            imgData.data[idx + 1] = imgData.data[idx + 1] ^ (Math.random() * 5 | 0);
        }
        ctx.putImageData(imgData, 0, 0);
    }
    return origToDataURL.apply(this, arguments);
};
"""

# ── Anti-ban: Extra headers ────────────────────────────────────────────────────
def random_extra_headers() -> dict:
    """Return a plausible set of browser-like extra headers."""
    return {
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Sec-Ch-Ua": (
            '"Chromium";v="123", "Not:A-Brand";v="8", "Google Chrome";v="123"'
        ),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": random.choice(["max-age=0", "no-cache"]),
    }

# ── Anti-ban: Human-like behaviour helpers ─────────────────────────────────────
def human_pause(min_s: float = 0.4, max_s: float = 1.2) -> None:
    """Short unpredictable pause to mimic human reaction time."""
    time.sleep(random.uniform(min_s, max_s))

def human_scroll(page, n_scrolls: int) -> None:
    """
    Scroll with randomised amounts and pauses.
    Occasionally scrolls back up slightly to mimic reading behaviour.
    """
    for i in range(n_scrolls):
        # Vary scroll distance: 60-120% of viewport height
        amount = int(random.uniform(0.6, 1.2) * 900)
        page.evaluate(f"window.scrollBy(0, {amount})")
        time.sleep(random.uniform(THREADS_SCROLL_DELAY_MIN, THREADS_SCROLL_DELAY_MAX))

        # Every ~5 scrolls, pause a bit longer as if reading
        if i % 5 == 4:
            time.sleep(random.uniform(1.5, 3.0))

        # Occasionally scroll back slightly
        if random.random() < 0.15:
            page.evaluate(f"window.scrollBy(0, {-random.randint(80, 250)})")
            time.sleep(random.uniform(0.5, 1.2))

    # Scroll back to a mid-point to trigger any sticky lazy-loaders
    if n_scrolls > 3:
        page.evaluate("window.scrollBy(0, -500)")
        time.sleep(0.6)
        page.evaluate("window.scrollBy(0, 800)")

def move_mouse_randomly(page) -> None:
    """
    Move the mouse to a few random positions.
    Playwright's mouse API works even in headless mode.
    """
    vp = page.viewport_size or {"width": 1280, "height": 800}
    for _ in range(random.randint(2, 5)):
        x = random.randint(100, vp["width"]  - 100)
        y = random.randint(100, vp["height"] - 100)
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.05, 0.2))

# ── Anti-ban: Exponential backoff ─────────────────────────────────────────────
def backoff(attempt: int, base: float = 4.0, cap: float = 120.0) -> None:
    """Sleep with jittered exponential backoff."""
    delay = min(base * (2 ** attempt) + random.uniform(0, 3), cap)
    log.warning("Backoff attempt %d — sleeping %.1fs", attempt + 1, delay)
    time.sleep(delay)

# ── XHR / CDP data extraction ─────────────────────────────────────────────────
def extract_posts_from_xhr(xhr_data: dict) -> list[dict]:
    """
    Walk nested Threads API response JSON and extract post objects.
    Threads uses several response shapes depending on endpoint; this walks
    all common paths defensively.
    """
    posts: list[dict] = []

    def walk(obj):
        if isinstance(obj, dict):
            text    = obj.get("text") or obj.get("caption") or obj.get("body") or ""
            post_id = (
                obj.get("pk") or obj.get("id") or obj.get("post_id") or ""
            )
            taken_at = obj.get("taken_at") or obj.get("timestamp") or 0
            username = ""
            user_node = obj.get("user") or obj.get("owner") or {}
            if isinstance(user_node, dict):
                username = (
                    user_node.get("username")
                    or user_node.get("screen_name")
                    or ""
                )
            if (
                text
                and post_id
                and len(str(text).strip()) >= THREADS_MIN_CHARS
            ):
                posts.append({
                    "post_id":  str(post_id),
                    "text":     str(text).strip(),
                    "username": username,
                    "taken_at": taken_at,
                })
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(xhr_data)

    # Deduplicate
    seen: set[str] = set()
    unique = []
    for p in posts:
        if p["post_id"] not in seen:
            seen.add(p["post_id"])
            unique.append(p)
    return unique


def already_saved(post_id: str) -> bool:
    return col.count_documents(
        {"post_id": post_id, "platform": "threads"}, limit=1
    ) == 1


def save_post(raw: dict, source: str, source_type: str) -> bool:
    doc = {
        "platform":      "threads",
        "post_id":       raw["post_id"],
        "url":           f"https://www.threads.net/@{raw['username']}/post/{raw['post_id']}",
        "username":      raw["username"],
        "source":        source,
        "source_type":   source_type,
        "content":       raw["text"],
        "publish_date":  (
            datetime.fromtimestamp(raw["taken_at"], tz=timezone.utc)
            if raw["taken_at"] else None
        ),
        "crawl_date":    datetime.now(tz=timezone.utc),
        "is_summarized": False,
        "language_hint": "vi",
    }
    result = col.update_one(
        {"post_id": raw["post_id"], "platform": "threads"},
        {"$setOnInsert": doc},
        upsert=True,
    )
    return result.upserted_id is not None

# ── Context factory ────────────────────────────────────────────────────────────
def new_context(browser):
    """
    Create a fresh browser context with a randomised fingerprint.
    Call this every THREADS_SESSION_MAX_PAGES pages to rotate identity.
    """
    ua       = random.choice(USER_AGENTS)
    viewport = random.choice(VIEWPORTS)
    context  = browser.new_context(
        user_agent=ua,
        viewport=viewport,
        locale="vi-VN",
        timezone_id="Asia/Ho_Chi_Minh",
        java_script_enabled=True,
        extra_http_headers=random_extra_headers(),
        # Slightly randomise colour depth and pixel ratio
        device_scale_factor=random.choice([1, 1, 1, 2]),
        has_touch=random.random() < 0.3,
    )
    context.add_init_script(STEALTH_JS)
    log.debug("New context — UA: %s | VP: %s", ua[:60], viewport)
    return context

# ── CDP-based XHR capture ─────────────────────────────────────────────────────
def make_cdp_capture(page) -> tuple[list[dict], callable]:
    """
    Use CDP (Chrome DevTools Protocol) Network interception.
    Returns (captured_list, cleanup_fn).
    This is lower-level and harder to detect than Playwright response events.
    """
    captured: list[dict] = []
    lock = threading.Lock()
    client = page.context.new_cdp_session(page)

    def on_response(event):
        try:
            resp = client.send("Network.getResponseBody",
                               {"requestId": event["requestId"]})
            body_text = resp.get("body", "")
            if not body_text:
                return
            data = json.loads(body_text)
            posts = extract_posts_from_xhr(data)
            if posts:
                with lock:
                    captured.extend(posts)
        except Exception:
            pass

    client.send("Network.enable")
    client.on("Network.responseReceived", lambda e: (
        threading.Thread(target=on_response, args=(e,), daemon=True).start()
        if "threads.net" in e.get("response", {}).get("url", "")
           and e.get("type") == "XHR"
        else None
    ))

    def cleanup():
        try:
            client.detach()
        except Exception:
            pass

    return captured, cleanup

# ── Profile scraper ────────────────────────────────────────────────────────────
def scrape_profile(username: str, limit: int, page) -> int:
    """Navigate to a profile, capture XHR posts via CDP."""
    captured, cleanup = make_cdp_capture(page)

    url = f"https://www.threads.net/@{username}"
    for attempt in range(3):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=35_000)
            # Wait a little for initial XHR to fire
            human_pause(1.5, 3.0)
            break
        except Exception as exc:
            log.warning("Profile load failed %s (attempt %d): %s", url, attempt + 1, exc)
            if attempt < 2:
                backoff(attempt)
            else:
                cleanup()
                return 0

    move_mouse_randomly(page)
    n_scrolls = min(THREADS_MAX_SCROLLS_USER, max(4, limit // 5))
    human_scroll(page, n_scrolls)

    cleanup()

    # Deduplicate across all captured
    seen: set[str] = set()
    unique = []
    for raw in captured:
        if raw["post_id"] not in seen:
            seen.add(raw["post_id"])
            unique.append(raw)

    saved = 0
    for raw in unique[:limit]:
        if already_saved(raw["post_id"]):
            continue
        if save_post(raw, username, "account"):
            n = inc()
            log.info("[+%d] @%s — %s", n, username, raw["text"][:60])
            saved += 1

    return saved


# ── Hashtag scraper ────────────────────────────────────────────────────────────
def scrape_hashtag(hashtag: str, limit: int, page) -> int:
    """Navigate to a hashtag search page, capture XHR posts via CDP."""
    # Threads uses '#' encoded or plain in search — try both patterns
    url = f"https://www.threads.net/search?q=%23{hashtag}&serp_type=default"
    captured, cleanup = make_cdp_capture(page)

    for attempt in range(3):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=35_000)
            human_pause(1.5, 3.0)
            break
        except Exception as exc:
            log.warning("Hashtag page failed %s (attempt %d): %s", hashtag, attempt + 1, exc)
            if attempt < 2:
                backoff(attempt)
            else:
                cleanup()
                return 0

    move_mouse_randomly(page)
    n_scrolls = min(THREADS_MAX_SCROLLS_TAG, max(3, limit // 5))
    human_scroll(page, n_scrolls)

    cleanup()

    seen: set[str] = set()
    unique = []
    for raw in captured:
        if raw["post_id"] not in seen:
            seen.add(raw["post_id"])
            unique.append(raw)

    saved = 0
    for raw in unique[:limit]:
        if already_saved(raw["post_id"]):
            continue
        if save_post(raw, hashtag, "hashtag"):
            n = inc()
            log.info("[+%d] #%s — %s", n, hashtag, raw["text"][:60])
            saved += 1

    return saved

# ── Main crawl job ─────────────────────────────────────────────────────────────
def crawl_job(total_limit: int = 1000) -> None:
    from playwright.sync_api import sync_playwright

    reset()
    before = col.count_documents({"platform": "threads"})
    log.info("=== Threads crawl started | platform total: %d ===", before)

    accounts = THREADS_ACCOUNTS[:]
    hashtags = THREADS_HASHTAGS[:]
    random.shuffle(accounts)
    random.shuffle(hashtags)

    saved_total = 0
    pages_this_session = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-extensions",
                "--disable-default-apps",
                # Randomise window position to vary OS-level fingerprint
                f"--window-position={random.randint(0,200)},{random.randint(0,100)}",
            ],
        )

        context = new_context(browser)

        def maybe_rotate_context():
            """Rotate context after THREADS_SESSION_MAX_PAGES pages."""
            nonlocal context, pages_this_session
            if pages_this_session >= THREADS_SESSION_MAX_PAGES:
                log.info("Rotating browser context after %d pages", pages_this_session)
                context.close()
                context = new_context(browser)
                pages_this_session = 0
                # Longer pause after context rotation
                time.sleep(random.uniform(8, 18))

        # ── Crawl accounts ────────────────────────────────────────────────────
        for username in accounts:
            if saved_total >= total_limit:
                break
            maybe_rotate_context()
            page = context.new_page()
            try:
                per_user = min(THREADS_MAX_PER_USER, total_limit - saved_total)
                n = scrape_profile(username, per_user, page)
                saved_total += n
                pages_this_session += 1
                log.info("@%s → +%d | session pages %d | total %d",
                         username, n, pages_this_session, saved_total)
            except Exception as exc:
                log.error("Unexpected error on @%s: %s", username, exc)
            finally:
                page.close()

            # Inter-profile pause (longer if we got 0 — may be rate limited)
            pause = (
                random.uniform(THREADS_PAGE_DELAY_MIN * 2, THREADS_PAGE_DELAY_MAX * 2)
                if n == 0
                else random.uniform(THREADS_PAGE_DELAY_MIN, THREADS_PAGE_DELAY_MAX)
            )
            log.debug("Waiting %.1fs before next profile", pause)
            time.sleep(pause)

        # ── Crawl hashtags ────────────────────────────────────────────────────
        for tag in hashtags:
            if saved_total >= total_limit:
                break
            maybe_rotate_context()
            page = context.new_page()
            try:
                per_tag = min(60, total_limit - saved_total)
                n = scrape_hashtag(tag, per_tag, page)
                saved_total += n
                pages_this_session += 1
                log.info("#%s → +%d | session pages %d | total %d",
                         tag, n, pages_this_session, saved_total)
            except Exception as exc:
                log.error("Unexpected error on #%s: %s", tag, exc)
            finally:
                page.close()

            pause = (
                random.uniform(THREADS_PAGE_DELAY_MIN * 2, THREADS_PAGE_DELAY_MAX * 2)
                if n == 0
                else random.uniform(THREADS_PAGE_DELAY_MIN, THREADS_PAGE_DELAY_MAX)
            )
            time.sleep(pause)

        context.close()
        browser.close()

    after = col.count_documents({"platform": "threads"})
    log.info(
        "=== Threads done | +%d new | platform total: %d ===",
        after - before, after,
    )

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once",  action="store_true",
                    help="Run once and exit (no scheduler)")
    ap.add_argument("--limit", type=int, default=1000,
                    help="Max new posts per run")
    ap.add_argument("--hour",  type=int, default=6,
                    help="UTC hour for daily scheduled run")
    args = ap.parse_args()

    if args.once:
        crawl_job(total_limit=args.limit)
    else:
        crawl_job(total_limit=args.limit)
        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(
            crawl_job,
            "cron",
            hour=args.hour,
            minute=0,
            kwargs={"total_limit": args.limit},
            max_instances=1,
            coalesce=True,
        )
        log.info("Scheduler started — daily at %02d:00 UTC", args.hour)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("Stopped.")