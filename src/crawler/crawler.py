"""
crawler.py — Vietnamese news crawler, deep + scheduled.

Run modes:
  python crawler.py --once --limit 10000   # one-shot backfill
  python crawler.py --limit 5000 --hour 3  # daily at 03:00 UTC
"""
import re
import time
import random
import logging
import threading
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

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

# ── Logging ────────────────────────────────────────────────────────────────────
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
client = MongoClient("mongodb://mongodb:27017/")
db = client["nlp_database"]
collection = db["raw_articles"]
collection.create_index("url", unique=True)

# ── Concurrency knobs ──────────────────────────────────────────────────────────
SOURCE_WORKERS     = 5    # sources crawled in parallel
ARTICLE_WORKERS    = 8    # articles fetched in parallel per source
DOMAIN_CONCURRENCY = 2    # max simultaneous requests to one domain
MAX_PAGES          = 5    # pagination depth per category
PER_SOURCE_LIMIT   = 200  # max articles per source per run

_domain_sems: dict = defaultdict(lambda: threading.Semaphore(DOMAIN_CONCURRENCY))

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

# ── Thread-local session ───────────────────────────────────────────────────────
_local = threading.local()
PROXY_POOL: list = []  # fill with "http://user:pass@host:port" strings

def get_session() -> requests.Session:
    """One requests.Session per thread, created lazily."""
    if not hasattr(_local, "session"):
        s = requests.Session()
        s.headers.update({
            "User-Agent": random_ua(),
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.google.com/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
        retry = Retry(total=2, backoff_factor=1,
                      status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET"], raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        if PROXY_POOL:
            p = random.choice(PROXY_POOL)
            s.proxies = {"http": p, "https": p}
        _local.session = s
    return _local.session

# ── Thread-safe saved counter ──────────────────────────────────────────────────
_counter_lock = threading.Lock()
_run_saved = 0

def increment_saved() -> int:
    global _run_saved
    with _counter_lock:
        _run_saved += 1
        return _run_saved

def reset_counter() -> None:
    global _run_saved
    with _counter_lock:
        _run_saved = 0

# ── HTTP ───────────────────────────────────────────────────────────────────────
def get_domain(url: str) -> str:
    return urlparse(url).netloc

def fetch_html(url: str) -> Optional[str]:
    """Fetch with per-domain concurrency cap and a small random delay."""
    with _domain_sems[get_domain(url)]:
        time.sleep(random.uniform(0.4, 1.2))
        try:
            resp = get_session().get(url, timeout=15)
            return resp.text if resp.status_code == 200 else None
        except Exception as exc:
            log.debug("Fetch error %s: %s", url, exc)
            return None

# ── Link discovery ─────────────────────────────────────────────────────────────
def discover_links(category_url: str, pattern: str,
                   pagination_tpl: Optional[str],
                   max_links: int = 300) -> list:
    """
    Scrape category page + paginated pages up to MAX_PAGES.
    Stops early if a page returns no new matching links.
    """
    parsed = urlparse(category_url)
    base   = f"{parsed.scheme}://{parsed.netloc}"
    rx     = re.compile(pattern)
    seen: set  = set()
    links: list = []

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
            break  # no more articles deeper

    log.info("Discovered %d links | %s", len(links), category_url)
    return links

# ── Article processing ─────────────────────────────────────────────────────────
def already_saved(url: str) -> bool:
    return collection.count_documents({"url": url}, limit=1) == 1

def parse_article(url: str, html: str) -> Optional[Article]:
    """Inject pre-fetched HTML into newspaper — no second HTTP call."""
    config = newspaper.Config()
    config.language    = "vi"
    config.fetch_images = False
    art = Article(url, config=config)
    art.set_html(html)
    art.parse()
    try:
        art.nlp()
    except Exception:
        pass
    return art

def get_next_post_id() -> int:
    """Atomically increment and return the next post_id using a counters collection."""
    result = db["counters"].find_one_and_update(
        {"_id": "post_id"},
        {"$inc": {"seq": 1}},
        return_document=pymongo.ReturnDocument.AFTER,
        upsert=True
    )
    return result["seq"]

def save_article(art: Article, source: str) -> bool:
    post_id = get_next_post_id()
    doc = {
        "post_id":       post_id,           # ← assigned at insert time
        "title":         art.title,
        "content":       art.text,
        "url":           art.url,
        "publish_date":  art.publish_date,
        "crawl_date":    datetime.now(),
        "source":        source,
        "keywords":      art.keywords,
        "summary":       art.summary,
        "is_summarized": False,
    }
    result = collection.update_one(
        {"url": art.url}, {"$setOnInsert": doc}, upsert=True
    )
    if result.upserted_id is not None:
        return True
    else:
        db["counters"].update_one({"_id": "post_id"}, {"$inc": {"seq": -1}})
        return False

def process_article(url: str, source: str) -> bool:
    """Full pipeline for one article. Returns True if newly saved."""
    if already_saved(url):
        return False
    html = fetch_html(url)
    if not html:
        return False
    try:
        art = parse_article(url, html)
        if not art or not art.title or len(art.text) < 150:
            log.debug("Thin content: %s", url)
            return False
        if save_article(art, source):
            n = increment_saved()
            log.info("[+%d] %s", n, art.title[:80])
            return True
    except Exception as exc:
        log.warning("Parse error %s: %s", url, exc)
    return False

# ── Source + job orchestration ─────────────────────────────────────────────────
def crawl_source(category_url: str, pattern: str,
                 pagination_tpl: Optional[str], limit: int) -> int:
    links = discover_links(category_url, pattern, pagination_tpl)
    if not links:
        return 0
    random.shuffle(links)
    links = links[:limit]
    saved = 0
    with ThreadPoolExecutor(max_workers=ARTICLE_WORKERS,
                            thread_name_prefix="art") as pool:
        for ok in as_completed(
            pool.submit(process_article, url, category_url) for url in links
        ):
            if ok.result():
                saved += 1
    return saved

def crawl_job(total_limit: int = 5000, per_source: int = PER_SOURCE_LIMIT) -> None:
    reset_counter()
    before = collection.count_documents({})
    log.info("=== Job start | DB: %d articles ===", before)

    sources   = random.sample(SOURCES, len(SOURCES))  # shuffle order each run
    saved_ref = {"n": 0}
    lock      = threading.Lock()

    def source_task(entry):
        cat_url, pattern, pag_tpl = entry
        with lock:
            if saved_ref["n"] >= total_limit:
                return 0
            remaining = min(per_source, total_limit - saved_ref["n"])
        n = crawl_source(cat_url, pattern, pag_tpl, remaining)
        with lock:
            saved_ref["n"] += n
        log.info("Done %-50s +%-3d | session %d", cat_url, n, saved_ref["n"])
        return n

    with ThreadPoolExecutor(max_workers=SOURCE_WORKERS,
                            thread_name_prefix="src") as pool:
        list(pool.map(source_task, sources))

    after = collection.count_documents({})
    log.info("=== Job done | +%d new | DB total: %d ===", after - before, after)

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Vietnamese news crawler")
    ap.add_argument("--once",  action="store_true", help="Single run then exit")
    ap.add_argument("--limit", type=int, default=5000,  help="New articles per run")
    ap.add_argument("--hour",  type=int, default=3,     help="Daily run hour (UTC)")
    args = ap.parse_args()

    log.info("Sources loaded: %d categories across %d domains",
             len(SOURCES),
             len({urlparse(s[0]).netloc for s in SOURCES}))

    if args.once:
        crawl_job(total_limit=args.limit)
    else:
        log.info("Scheduler mode — running now, then daily at %02d:00 UTC", args.hour)
        crawl_job(total_limit=args.limit)
        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(
            crawl_job,
            trigger="cron",
            hour=args.hour, minute=0,
            kwargs={"total_limit": args.limit},
            id="daily_crawl",
            max_instances=1,
            coalesce=True,
        )
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("Scheduler stopped.")