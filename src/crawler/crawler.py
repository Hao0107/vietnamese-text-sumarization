"""
crawler.py — Vietnamese news crawler: pagination + sitemap, deep + scheduled.

Run modes:
  python crawler.py --once --limit 100000          # one-shot backfill (both lanes)
  python crawler.py --sitemap-only --limit 100000  # sitemap lane only (fastest backfill)
  python crawler.py --limit 15000 --hour 3         # daily scheduler (both lanes)

Architecture — two parallel URL-discovery lanes feed the SAME processing pipeline:

  ┌─────────────────────┐     ┌──────────────────────────────┐
  │  Lane A: Pagination │     │  Lane B: Sitemap             │
  │  (sources.py)       │     │  (sitemap_sources.py)        │
  │  ~130 categories    │     │  ~20 sitemaps → tens of      │
  │  paginated scrape   │     │  thousands URLs per fetch    │
  └────────┬────────────┘     └──────────────┬───────────────┘
           │                                 │
           └──────────┬──────────────────────┘
                      ▼
         mark_seen() → filter_unsaved() → process_article()
                      ▼
                   MongoDB

Sitemap advantages over pagination:
  • 1 HTTP request → 10k-50k article URLs  (vs ~30 per paginated page)
  • Robots-friendly — sitemaps are made for bots, much less likely to be blocked
  • Reaches historical articles that pagination can never get to
  • Carries <lastmod> timestamps — lets us do true incremental updates
"""
import re
import gzip
import time
import random
import logging
import threading
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from xml.etree import ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import newspaper
from newspaper import Article
from pymongo import MongoClient
import pymongo
from apscheduler.schedulers.blocking import BlockingScheduler

from sources import SOURCES
from sitemap_sources import SITEMAP_SOURCES

# ── Logging ───────────────────────────────────────────────────────────────────
for _lib in ("newspaper", "urllib3", "requests", "chardet", "apscheduler"):
    logging.getLogger(_lib).setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("crawler.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── MongoDB ────────────────────────────────────────────────────────────────────
client = MongoClient(
    "mongodb://mongodb:27017/",
    maxPoolSize=32,
    serverSelectionTimeoutMS=5000,
)
db         = client["nlp_database"]
collection = db["raw_articles"]
collection.create_index("url", unique=True)
collection.create_index("crawl_date")

# ── Concurrency knobs ──────────────────────────────────────────────────────────
SOURCE_WORKERS     = 10
ARTICLE_WORKERS    = 20
DOMAIN_CONCURRENCY = 4
MAX_PAGES          = 8
PER_SOURCE_LIMIT   = 500
URL_BATCH_SIZE     = 200

_domain_sems: dict = defaultdict(lambda: threading.Semaphore(DOMAIN_CONCURRENCY))

# ── Per-run stats ──────────────────────────────────────────────────────────────
class RunStats:
    def __init__(self):
        self._lock     = threading.Lock()
        self.saved     = 0
        self.skipped   = 0
        self.errors    = 0
        self.attempted = 0

    def inc(self, field: str, n: int = 1):
        with self._lock:
            setattr(self, field, getattr(self, field) + n)

    def summary(self) -> str:
        return (f"attempted={self.attempted} saved={self.saved} "
                f"skipped={self.skipped} errors={self.errors}")

_stats = RunStats()

# ── User-Agent ─────────────────────────────────────────────────────────────────
try:
    from fake_useragent import UserAgent as _FUA
    _fua = _FUA()
    def random_ua() -> str:
        return _fua.random
except Exception:
    _UA_POOL = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    ]
    def random_ua() -> str:
        return random.choice(_UA_POOL)

_GOOGLEBOT_UA = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)

# ── Thread-local HTTP session ──────────────────────────────────────────────────
_local     = threading.local()
PROXY_POOL: list = []

def get_session() -> requests.Session:
    if not hasattr(_local, "session"):
        s = requests.Session()
        s.headers.update({
            "User-Agent":                random_ua(),
            "Accept-Language":           "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding":           "gzip, deflate, br",
            "Referer":                   "https://www.google.com/",
            "DNT":                       "1",
            "Connection":                "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
        retry = Retry(
            total=3, backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"], raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry, pool_connections=20, pool_maxsize=40,
        )
        s.mount("https://", adapter)
        s.mount("http://",  adapter)
        if PROXY_POOL:
            p = random.choice(PROXY_POOL)
            s.proxies = {"http": p, "https": p}
        _local.session = s
    return _local.session

# ── In-process URL deduplication ──────────────────────────────────────────────
_seen_urls: set = set()
_seen_lock       = threading.Lock()

def mark_seen(urls: list[str]) -> list[str]:
    with _seen_lock:
        fresh = [u for u in urls if u not in _seen_urls]
        _seen_urls.update(fresh)
    return fresh

def reset_seen():
    with _seen_lock:
        _seen_urls.clear()

# ── Bulk DB existence check ────────────────────────────────────────────────────
def filter_unsaved(urls: list[str]) -> list[str]:
    if not urls:
        return []
    existing = {
        doc["url"]
        for doc in collection.find({"url": {"$in": urls}}, {"url": 1, "_id": 0})
    }
    return [u for u in urls if u not in existing]

# ── post_id block allocator ────────────────────────────────────────────────────
_id_lock       = threading.Lock()
_id_next: int  = 0
_id_end:  int  = 0
_ID_BLOCK      = 500

def _reserve_block():
    global _id_next, _id_end
    result = db["counters"].find_one_and_update(
        {"_id": "post_id"},
        {"$inc": {"seq": _ID_BLOCK}},
        return_document=pymongo.ReturnDocument.AFTER,
        upsert=True,
    )
    _id_end  = result["seq"]
    _id_next = _id_end - _ID_BLOCK + 1

def next_post_id() -> int:
    global _id_next
    with _id_lock:
        if _id_next >= _id_end:
            _reserve_block()
        val = _id_next
        _id_next += 1
        return val

# ── HTTP fetch ─────────────────────────────────────────────────────────────────
def get_domain(url: str) -> str:
    return urlparse(url).netloc

def fetch_html(url: str, *, delay_range=(0.2, 0.7)) -> Optional[str]:
    with _domain_sems[get_domain(url)]:
        time.sleep(random.uniform(*delay_range))
        try:
            resp = get_session().get(url, timeout=12)
            return resp.text if resp.status_code == 200 else None
        except Exception as exc:
            log.debug("Fetch error %s: %s", url, exc)
            return None

# ══════════════════════════════════════════════════════════════════════════════
# LANE B — Sitemap
# ══════════════════════════════════════════════════════════════════════════════

_SM_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _fetch_sitemap_raw(url: str) -> Optional[bytes]:
    """
    Fetch raw bytes of a sitemap URL.
    - Uses Googlebot UA so servers treat it as a well-behaved bot.
    - Decompresses gzip transparently (some servers send .xml.gz without
      setting Content-Encoding: gzip).
    - No per-domain semaphore — sitemap fetches are infrequent and heavy;
      we don't want them queued behind 20 article workers.
    """
    try:
        resp = get_session().get(
            url, timeout=20,
            headers={"User-Agent": _GOOGLEBOT_UA},
        )
        if resp.status_code != 200:
            log.debug("Sitemap HTTP %d: %s", resp.status_code, url)
            return None
        data = resp.content
        if data[:2] == b"\x1f\x8b":          # gzip magic bytes
            data = gzip.decompress(data)
        return data
    except Exception as exc:
        log.debug("Sitemap fetch error %s: %s", url, exc)
        return None


def _parse_sitemap_xml(data: bytes) -> tuple[list[str], list[str]]:
    """
    Parse one sitemap blob.
    Returns (child_sitemap_urls, article_urls).
    Handles both <sitemapindex> (parent) and <urlset> (leaf) formats.
    """
    children: list[str] = []
    articles: list[str] = []
    try:
        root = ET.fromstring(data)
        tag  = root.tag.lower()
        if "sitemapindex" in tag:
            for loc in root.findall("sm:sitemap/sm:loc", _SM_NS):
                if loc.text:
                    children.append(loc.text.strip())
        elif "urlset" in tag:
            for loc in root.findall("sm:url/sm:loc", _SM_NS):
                if loc.text:
                    articles.append(loc.text.strip())
    except ET.ParseError as exc:
        log.debug("Sitemap XML parse error: %s", exc)
    return children, articles


def fetch_sitemap_urls(
    entry_url:   str,
    article_re:  str,
    *,
    max_depth:   int = 3,
    child_limit: int = 0,   # 0 = follow all child sitemaps
) -> list[str]:
    """
    Recursively walk a sitemap tree (BFS).

    Flow:
      1. Fetch entry_url → parse XML.
      2. If <sitemapindex>: enqueue child sitemaps (most-recent first,
         capped by child_limit if set).
      3. If <urlset>: collect URLs matching article_re.
      4. Repeat until queue empty or max_depth exceeded.

    Returns a deduplicated list of article URLs, most-recent first.
    Most news sitemaps list oldest entries first, so we reverse child
    order to prioritise fresh content when child_limit is applied.
    """
    visited:  set        = set()
    all_urls: list[str]  = []
    rx = re.compile(article_re)

    # queue items: (url, depth)
    queue: list[tuple[str, int]] = [(entry_url, 0)]

    while queue:
        url, depth = queue.pop(0)
        if url in visited or depth > max_depth:
            continue
        visited.add(url)

        data = _fetch_sitemap_raw(url)
        if not data:
            continue

        children, articles = _parse_sitemap_xml(data)

        for a in articles:
            if rx.search(a):
                all_urls.append(a)

        # reverse → most-recent child sitemaps first (news sitemaps list
        # oldest month first, newest month last)
        ordered_children = list(reversed(children))
        if child_limit:
            ordered_children = ordered_children[:child_limit]
        for child in ordered_children:
            if child not in visited:
                queue.append((child, depth + 1))

        log.debug("Sitemap %-55s depth=%d children=%d articles_so_far=%d",
                  url, depth, len(children), len(all_urls))

    # deduplicate preserving order
    seen:   set        = set()
    result: list[str]  = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            result.append(u)

    log.info("Sitemap done %-50s → %d URLs", entry_url, len(result))
    return result


def crawl_sitemap_source(entry: dict, limit: int) -> int:
    """
    Process one SITEMAP_SOURCES entry dict through the shared pipeline.

    Required keys  : url, pattern, name
    Optional keys  : max_depth (default 3), child_limit (default 0)
    """
    urls = fetch_sitemap_urls(
        entry["url"],
        entry["pattern"],
        max_depth=entry.get("max_depth", 3),
        child_limit=entry.get("child_limit", 0),
    )
    if not urls:
        return 0

    random.shuffle(urls)
    urls = urls[:limit]

    fresh = mark_seen(urls)
    if not fresh:
        return 0

    to_fetch: list[str] = []
    for i in range(0, len(fresh), URL_BATCH_SIZE):
        to_fetch.extend(filter_unsaved(fresh[i: i + URL_BATCH_SIZE]))
    if not to_fetch:
        return 0

    saved        = 0
    source_label = entry.get("name", entry["url"])
    with ThreadPoolExecutor(max_workers=ARTICLE_WORKERS,
                            thread_name_prefix="sm-art") as pool:
        futs = {pool.submit(process_article, u, source_label): u
                for u in to_fetch}
        for fut in as_completed(futs):
            try:
                if fut.result():
                    saved += 1
            except Exception as exc:
                log.warning("Sitemap future error %s: %s", futs[fut], exc)
    return saved

# ══════════════════════════════════════════════════════════════════════════════
# Shared article processing (used by both lanes)
# ══════════════════════════════════════════════════════════════════════════════

_SAPO_SELECTORS = [
    "p.description",                             # VnExpress
    "div.detail-sapo",                           # Tuổi Trẻ
    "div.sapo",                                  # Thanh Niên
    "p.the-article-summary",                     # Zing / Znews
    "div.content-detail-sapo",                   # VietnamNet
    "div.article-sapo",                          # 24h
    "div.singular-sapo",                         # Dân Trí
    "h2.sapo",                                   # Kenh14 / CafeF / CafeBiz
    "div.detail-content > p.sapo",               # NLD, PLO
    "div.article__sapo",                         # VTC News
    "div.cms-desc",                              # Báo Tin Tức / TTXVN
    "div.detail__summary",                       # Hà Nội Mới
    "div.entry-sapo",                            # Tạp Chí Tài Chính, PC World VN
    "div.box-content-detail > p:first-of-type",  # QDND
    "article h2",                                # generic fallback
    "div.article-body > p:first-of-type > strong",
    "article > p:first-of-type",
    "div.article-content > p:first-of-type",
]

def extract_sapo(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        for sel in _SAPO_SELECTORS:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                if len(text) >= 30:
                    return text
    except Exception:
        pass
    return ""

def parse_article(url: str, html: str) -> Optional[Article]:
    config              = newspaper.Config()
    config.language     = "vi"
    config.fetch_images = False
    art = Article(url, config=config)
    art.set_html(html)
    art.parse()
    # art.nlp() omitted — 3-5× slower; replaced by extract_sapo()
    return art

def save_article(art: Article, html: str, source: str) -> bool:
    pid  = next_post_id()
    sapo = extract_sapo(html)
    doc  = {
        "post_id":       pid,
        "title":         art.title,
        "content":       art.text,
        "url":           art.url,
        "publish_date":  art.publish_date,
        "crawl_date":    datetime.now(),
        "source":        source,
        "sapo":          sapo,
        "is_summarized": False,
    }
    result = collection.update_one(
        {"url": art.url}, {"$setOnInsert": doc}, upsert=True
    )
    if result.upserted_id is not None:
        return True
    with _id_lock:
        global _id_next
        _id_next = max(_id_next - 1, 0)
    return False

def process_article(url: str, source: str) -> bool:
    """Shared pipeline for both lanes. Returns True if newly saved."""
    _stats.inc("attempted")
    html = fetch_html(url)
    if not html:
        _stats.inc("errors")
        return False
    try:
        art = parse_article(url, html)
        if not art or not art.title or len(art.text) < 150:
            log.debug("Thin content: %s", url)
            _stats.inc("skipped")
            return False
        if save_article(art, html, source):
            _stats.inc("saved")
            log.info("[+%d] %s", _stats.saved, art.title[:80])
            return True
        else:
            _stats.inc("skipped")
    except Exception as exc:
        log.warning("Parse error %s: %s", url, exc)
        _stats.inc("errors")
    return False

# ══════════════════════════════════════════════════════════════════════════════
# LANE A — Pagination (original flow, unchanged)
# ══════════════════════════════════════════════════════════════════════════════

def discover_links(category_url: str, pattern: str,
                   pagination_tpl: Optional[str],
                   max_links: int = 600) -> list[str]:
    parsed = urlparse(category_url)
    base   = f"{parsed.scheme}://{parsed.netloc}"
    rx     = re.compile(pattern)
    seen:  set        = set()
    links: list[str]  = []

    pages = [category_url]
    if pagination_tpl:
        pages += [pagination_tpl.format(page=p) for p in range(2, MAX_PAGES + 1)]

    for page_url in pages:
        if len(links) >= max_links:
            break
        html = fetch_html(page_url)
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        new_on_page = 0
        for a in soup.find_all("a", href=True):
            href = a["href"].strip().split("?")[0].split("#")[0]
            href = (base + href) if href.startswith("/") else href
            if not href.startswith("http"):
                continue
            if href not in seen and rx.search(href):
                seen.add(href)
                links.append(href)
                new_on_page += 1
        log.debug("  %s → %d new links", page_url, new_on_page)
        if new_on_page == 0:
            break

    log.info("Discovered %d links | %s", len(links), category_url)
    return links

def crawl_source(category_url: str, pattern: str,
                 pagination_tpl: Optional[str], limit: int) -> int:
    raw_links = discover_links(category_url, pattern, pagination_tpl)
    if not raw_links:
        return 0
    random.shuffle(raw_links)
    raw_links = raw_links[:limit]

    fresh = mark_seen(raw_links)
    if not fresh:
        return 0

    to_fetch: list[str] = []
    for i in range(0, len(fresh), URL_BATCH_SIZE):
        to_fetch.extend(filter_unsaved(fresh[i: i + URL_BATCH_SIZE]))
    if not to_fetch:
        return 0

    saved = 0
    with ThreadPoolExecutor(max_workers=ARTICLE_WORKERS,
                            thread_name_prefix="art") as pool:
        futs = {pool.submit(process_article, u, category_url): u
                for u in to_fetch}
        for fut in as_completed(futs):
            try:
                if fut.result():
                    saved += 1
            except Exception as exc:
                log.warning("Future error %s: %s", futs[fut], exc)
    return saved

# ══════════════════════════════════════════════════════════════════════════════
# Job orchestration — both lanes run concurrently, share one budget counter
# ══════════════════════════════════════════════════════════════════════════════

def crawl_job(
    total_limit:    int  = 15000,
    per_source:     int  = PER_SOURCE_LIMIT,
    sitemap_only:   bool = False,
    pagination_only:bool = False,
) -> None:
    global _stats
    _stats = RunStats()
    reset_seen()

    before = collection.count_documents({})
    log.info(
        "=== Job start | DB: %d | target: +%d | sitemap_only=%s pagination_only=%s ===",
        before, total_limit, sitemap_only, pagination_only,
    )

    saved_ref = {"n": 0}
    lock      = threading.Lock()

    def budget_remaining() -> int:
        with lock:
            return max(0, total_limit - saved_ref["n"])

    def record(n: int):
        with lock:
            saved_ref["n"] += n

    # ── build mixed task list ─────────────────────────────────────────────────
    all_tasks: list[tuple[str, object]] = []
    if not pagination_only:
        for entry in random.sample(SITEMAP_SOURCES, len(SITEMAP_SOURCES)):
            all_tasks.append(("sitemap", entry))
    if not sitemap_only:
        for entry in random.sample(SOURCES, len(SOURCES)):
            all_tasks.append(("pagn", entry))

    # Interleave so one domain isn't hammered by all its tasks at once
    random.shuffle(all_tasks)

    def sitemap_task(entry: dict) -> int:
        if budget_remaining() <= 0:
            return 0
        lim = min(entry.get("per_run_limit", 5000), budget_remaining())
        n   = crawl_sitemap_source(entry, lim)
        record(n)
        log.info("Sitemap %-40s +%-4d | total: %d",
                 entry.get("name", "?"), n, saved_ref["n"])
        return n

    def pagination_task(entry: tuple) -> int:
        if budget_remaining() <= 0:
            return 0
        cat_url, pattern, pag_tpl = entry
        lim = min(per_source, budget_remaining())
        n   = crawl_source(cat_url, pattern, pag_tpl, lim)
        record(n)
        log.info("Pagn  %-50s +%-3d | total: %d", cat_url, n, saved_ref["n"])
        return n

    with ThreadPoolExecutor(max_workers=SOURCE_WORKERS,
                            thread_name_prefix="src") as pool:
        futs = []
        for kind, entry in all_tasks:
            if kind == "sitemap":
                futs.append(pool.submit(sitemap_task, entry))
            else:
                futs.append(pool.submit(pagination_task, entry))
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as exc:
                log.warning("Task error: %s", exc)

    after = collection.count_documents({})
    log.info(
        "=== Job done | +%d new | DB total: %d | stats: [%s] ===",
        after - before, after, _stats.summary(),
    )

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Vietnamese news crawler")
    ap.add_argument("--once",            action="store_true", help="Single run then exit")
    ap.add_argument("--sitemap-only",    action="store_true", help="Skip pagination lane")
    ap.add_argument("--pagination-only", action="store_true", help="Skip sitemap lane")
    ap.add_argument("--limit", type=int, default=15000, help="Article cap per run")
    ap.add_argument("--hour",  type=int, default=3,     help="Daily run hour (UTC)")
    args = ap.parse_args()

    log.info("Sources: %d paginated categories | %d sitemap entries",
             len(SOURCES), len(SITEMAP_SOURCES))

    job_kwargs = dict(
        total_limit     = args.limit,
        sitemap_only    = args.sitemap_only,
        pagination_only = args.pagination_only,
    )

    if args.once:
        crawl_job(**job_kwargs)
    else:
        log.info("Scheduler — running now, then daily at %02d:00 UTC", args.hour)
        crawl_job(**job_kwargs)
        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(
            crawl_job, trigger="cron",
            hour=args.hour, minute=0,
            kwargs=job_kwargs,
            id="daily_crawl", max_instances=1, coalesce=True,
        )
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("Scheduler stopped.")