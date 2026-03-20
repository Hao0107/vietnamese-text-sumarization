"""
Vietnamese news crawler — deep + scheduled daily runs.

Features:
  - Relaxed URL regexes (catch more articles)
  - 30+ category sources across 12+ sites
  - Pagination support (page 2, 3, ... up to MAX_PAGES)
  - APScheduler for daily auto-runs (acts like RSS polling)
  - Two-level ThreadPoolExecutor (sources + articles)
  - Per-domain semaphore (anti-ban)
  - Thread-local sessions, MongoDB dedup via unique index
"""
import re
import time
import random
import logging
import threading
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse, urlencode, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import newspaper
from newspaper import Article
from pymongo import MongoClient
from apscheduler.schedulers.blocking import BlockingScheduler

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

# ── Concurrency ────────────────────────────────────────────────────────────────
SOURCE_WORKERS     = 5    # sources in parallel
ARTICLE_WORKERS    = 8    # articles in parallel per source
DOMAIN_CONCURRENCY = 2    # max simultaneous requests to one domain
MAX_PAGES          = 5    # how many pagination pages to crawl per category
PER_SOURCE_LIMIT   = 200  # max articles per source per run
_domain_sems: dict = defaultdict(lambda: threading.Semaphore(DOMAIN_CONCURRENCY))

# ── Sources ────────────────────────────────────────────────────────────────────
# (category_url, article_url_regex, pagination_template_or_None)
# pagination_template: use {page} placeholder; None = no pagination
SOURCES = [
    # ── VnExpress ──────────────────────────────────────────────────────────────
    ("https://vnexpress.net/khoa-hoc-cong-nghe",
     r"vnexpress\.net/.*-\d+\.html$",
     "https://vnexpress.net/khoa-hoc-cong-nghe-p{page}"),
    ("https://vnexpress.net/kinh-doanh",
     r"vnexpress\.net/.*-\d+\.html$",
     "https://vnexpress.net/kinh-doanh-p{page}"),
    ("https://vnexpress.net/thoi-su",
     r"vnexpress\.net/.*-\d+\.html$",
     "https://vnexpress.net/thoi-su-p{page}"),
    ("https://vnexpress.net/the-gioi",
     r"vnexpress\.net/.*-\d+\.html$",
     "https://vnexpress.net/the-gioi-p{page}"),
    ("https://vnexpress.net/phap-luat",
     r"vnexpress\.net/.*-\d+\.html$",
     "https://vnexpress.net/phap-luat-p{page}"),
    ("https://vnexpress.net/suc-khoe",
     r"vnexpress\.net/.*-\d+\.html$",
     "https://vnexpress.net/suc-khoe-p{page}"),
    ("https://vnexpress.net/giao-duc",
     r"vnexpress\.net/.*-\d+\.html$",
     "https://vnexpress.net/giao-duc-p{page}"),

    # ── Tuổi Trẻ ──────────────────────────────────────────────────────────────
    ("https://tuoitre.vn/khoa-hoc.htm",
     r"tuoitre\.vn/.*-\d+\.htm$",
     "https://tuoitre.vn/khoa-hoc.htm?page={page}"),
    ("https://tuoitre.vn/kinh-te.htm",
     r"tuoitre\.vn/.*-\d+\.htm$",
     "https://tuoitre.vn/kinh-te.htm?page={page}"),
    ("https://tuoitre.vn/the-gioi.htm",
     r"tuoitre\.vn/.*-\d+\.htm$",
     "https://tuoitre.vn/the-gioi.htm?page={page}"),
    ("https://tuoitre.vn/thoi-su.htm",
     r"tuoitre\.vn/.*-\d+\.htm$",
     "https://tuoitre.vn/thoi-su.htm?page={page}"),
    ("https://tuoitre.vn/giao-duc.htm",
     r"tuoitre\.vn/.*-\d+\.htm$",
     "https://tuoitre.vn/giao-duc.htm?page={page}"),

    # ── Thanh Niên ─────────────────────────────────────────────────────────────
    ("https://thanhnien.vn/cong-nghe-game.htm",
     r"thanhnien\.vn/.*-\d+\.html$",
     "https://thanhnien.vn/cong-nghe-game.htm?page={page}"),
    ("https://thanhnien.vn/kinh-te",
     r"thanhnien\.vn/.*-\d+\.html$",
     "https://thanhnien.vn/kinh-te?page={page}"),
    ("https://thanhnien.vn/thoi-su",
     r"thanhnien\.vn/.*-\d+\.html$",
     "https://thanhnien.vn/thoi-su?page={page}"),
    ("https://thanhnien.vn/the-gioi",
     r"thanhnien\.vn/.*-\d+\.html$",
     "https://thanhnien.vn/the-gioi?page={page}"),

    # ── Dân Trí ────────────────────────────────────────────────────────────────
    ("https://dantri.com.vn/suc-manh-so.htm",
     r"dantri\.com\.vn/.*-\d+\.htm$",
     "https://dantri.com.vn/suc-manh-so.htm?page={page}"),
    ("https://dantri.com.vn/kinh-doanh.htm",
     r"dantri\.com\.vn/.*-\d+\.htm$",
     "https://dantri.com.vn/kinh-doanh.htm?page={page}"),
    ("https://dantri.com.vn/the-gioi.htm",
     r"dantri\.com\.vn/.*-\d+\.htm$",
     "https://dantri.com.vn/the-gioi.htm?page={page}"),
    ("https://dantri.com.vn/suc-khoe.htm",
     r"dantri\.com\.vn/.*-\d+\.htm$",
     "https://dantri.com.vn/suc-khoe.htm?page={page}"),
    ("https://dantri.com.vn/giao-duc.htm",
     r"dantri\.com\.vn/.*-\d+\.htm$",
     "https://dantri.com.vn/giao-duc.htm?page={page}"),

    # ── VietnamNet ─────────────────────────────────────────────────────────────
    ("https://vietnamnet.vn/cong-nghe",
     r"vietnamnet\.vn/.*-\d+\.html$",
     "https://vietnamnet.vn/cong-nghe?page={page}"),
    ("https://vietnamnet.vn/kinh-doanh",
     r"vietnamnet\.vn/.*-\d+\.html$",
     "https://vietnamnet.vn/kinh-doanh?page={page}"),
    ("https://vietnamnet.vn/the-gioi",
     r"vietnamnet\.vn/.*-\d+\.html$",
     "https://vietnamnet.vn/the-gioi?page={page}"),
    ("https://vietnamnet.vn/phap-luat",
     r"vietnamnet\.vn/.*-\d+\.html$",
     "https://vietnamnet.vn/phap-luat?page={page}"),

    # ── Znews ──────────────────────────────────────────────────────────────────
    ("https://znews.vn/cong-nghe.html",
     r"znews\.vn/.*-post\d+\.html$",
     None),
    ("https://znews.vn/kinh-doanh.html",
     r"znews\.vn/.*-post\d+\.html$",
     None),

    # ── Nhân Dân ───────────────────────────────────────────────────────────────
    ("https://nhandan.vn/cong-nghe",
     r"nhandan\.vn/.*-post\d+\.html$",
     "https://nhandan.vn/cong-nghe?page={page}"),
    ("https://nhandan.vn/kinhte",
     r"nhandan\.vn/.*-post\d+\.html$",
     "https://nhandan.vn/kinhte?page={page}"),

    # ── CafeF ──────────────────────────────────────────────────────────────────
    ("https://cafef.vn/thi-truong-chung-khoan.html",
     r"cafef\.vn/.*-\d+\.chn$",
     "https://cafef.vn/thi-truong-chung-khoan/trang{page}.chn"),
    ("https://cafef.vn/doanh-nghiep.html",
     r"cafef\.vn/.*-\d+\.chn$",
     "https://cafef.vn/doanh-nghiep/trang{page}.chn"),
    ("https://cafef.vn/bat-dong-san.html",
     r"cafef\.vn/.*-\d+\.chn$",
     "https://cafef.vn/bat-dong-san/trang{page}.chn"),

    # ── CafeBiz ────────────────────────────────────────────────────────────────
    ("https://cafebiz.vn/kinh-doanh.chn",
     r"cafebiz\.vn/.*-\d+\.chn$",
     "https://cafebiz.vn/kinh-doanh/trang{page}.chn"),
    ("https://cafebiz.vn/startup.chn",
     r"cafebiz\.vn/.*-\d+\.chn$",
     "https://cafebiz.vn/startup/trang{page}.chn"),

    # ── Genk ───────────────────────────────────────────────────────────────────
    ("https://genk.vn/cong-nghe.chn",
     r"genk\.vn/.*\.chn$",
     "https://genk.vn/cong-nghe/trang{page}.chn"),
    ("https://genk.vn/khoa-hoc.chn",
     r"genk\.vn/.*\.chn$",
     "https://genk.vn/khoa-hoc/trang{page}.chn"),

    # ── Kenh14 ─────────────────────────────────────────────────────────────────
    ("https://kenh14.vn/cong-nghe.chn",
     r"kenh14\.vn/.*\.chn$",
     "https://kenh14.vn/cong-nghe/trang{page}.chn"),

    # ── Báo Mới (aggregator, wide coverage) ───────────────────────────────────
    ("https://baomoi.com/cong-nghe.epi",
     r"baomoi\.com/[a-z0-9\-]+\.epi$",
     "https://baomoi.com/cong-nghe.epi?page={page}"),
    ("https://baomoi.com/kinh-doanh.epi",
     r"baomoi\.com/[a-z0-9\-]+\.epi$",
     "https://baomoi.com/kinh-doanh.epi?page={page}"),

    # ── Soha ───────────────────────────────────────────────────────────────────
    ("https://soha.vn/cong-nghe.htm",
     r"soha\.vn/.*-\d+\.htm$",
     "https://soha.vn/cong-nghe/trang{page}.htm"),
    ("https://soha.vn/kinh-doanh.htm",
     r"soha\.vn/.*-\d+\.htm$",
     "https://soha.vn/kinh-doanh/trang{page}.htm"),

    # ── ICT News ───────────────────────────────────────────────────────────────
    ("https://ictnews.vietnamplus.vn/cong-nghe-thong-tin",
     r"ictnews\.vietnamplus\.vn/.*\.htm$",
     None),

    # ── Bnews (Vietnam News Agency business) ──────────────────────────────────
    ("https://bnews.vn/kinh-te",
     r"bnews\.vn/.*-\d+\.html$",
     "https://bnews.vn/kinh-te?page={page}"),
    ("https://bnews.vn/cong-nghe",
     r"bnews\.vn/.*-\d+\.html$",
     "https://bnews.vn/cong-nghe?page={page}"),
]

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
PROXY_POOL: list = []

def get_session() -> requests.Session:
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

# ── Thread-safe counter ────────────────────────────────────────────────────────
_counter_lock = threading.Lock()
_run_saved = 0

def increment_saved() -> int:
    global _run_saved
    with _counter_lock:
        _run_saved += 1
        return _run_saved

def reset_counter():
    global _run_saved
    with _counter_lock:
        _run_saved = 0

# ── HTTP helpers ───────────────────────────────────────────────────────────────
def get_domain(url: str) -> str:
    return urlparse(url).netloc

def fetch_html(url: str) -> Optional[str]:
    sem = _domain_sems[get_domain(url)]
    with sem:
        time.sleep(random.uniform(0.4, 1.2))
        try:
            resp = get_session().get(url, timeout=15)
            return resp.text if resp.status_code == 200 else None
        except Exception as exc:
            log.debug("Fetch error %s: %s", url, exc)
            return None

# ── Link discovery with pagination ────────────────────────────────────────────
def discover_links(category_url: str, pattern: str,
                   pagination_tpl: Optional[str],
                   max_links: int = 300) -> list:
    """
    Scrape category page + up to MAX_PAGES paginated pages.
    Returns deduplicated article URLs matching pattern.
    """
    parsed = urlparse(category_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    rx = re.compile(pattern)
    seen: set = set()
    links: list = []

    pages_to_fetch = [category_url]
    if pagination_tpl:
        for p in range(2, MAX_PAGES + 1):
            pages_to_fetch.append(pagination_tpl.format(page=p))

    for page_url in pages_to_fetch:
        if len(links) >= max_links:
            break
        html = fetch_html(page_url)
        if not html:
            break  # stop paginating on first failure
        soup = BeautifulSoup(html, "html.parser")
        found_on_page = 0
        for a in soup.find_all("a", href=True):
            href = a["href"].strip().split("?")[0].split("#")[0]
            if href.startswith("/"):
                href = base + href
            elif not href.startswith("http"):
                continue
            if href not in seen and rx.search(href):
                seen.add(href)
                links.append(href)
                found_on_page += 1
        log.debug("  Page %s → %d new links", page_url, found_on_page)
        if found_on_page == 0:
            break  # no more articles on next pages

    log.info("Discovered %d links from %s (%d pages)",
             len(links), category_url, len(pages_to_fetch))
    return links

# ── Parse + save ───────────────────────────────────────────────────────────────
def already_saved(url: str) -> bool:
    return collection.count_documents({"url": url}, limit=1) == 1

def parse_article(url: str, html: str) -> Optional[Article]:
    config = newspaper.Config()
    config.language = "vi"
    config.fetch_images = False
    art = Article(url, config=config)
    art.set_html(html)
    art.parse()
    try:
        art.nlp()
    except Exception:
        pass
    return art

def save_article(art: Article, source: str) -> bool:
    doc = {
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
    return result.upserted_id is not None

def process_article(url: str, source: str) -> bool:
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

# ── Source crawler ─────────────────────────────────────────────────────────────
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
        futures = {pool.submit(process_article, url, category_url): url
                   for url in links}
        for fut in as_completed(futures):
            if fut.result():
                saved += 1
    return saved

# ── Main crawl job ─────────────────────────────────────────────────────────────
def crawl_job(total_limit: int = 5000, per_source: int = PER_SOURCE_LIMIT):
    reset_counter()
    total_before = collection.count_documents({})
    log.info("=== Crawl job started | DB has %d articles ===", total_before)

    sources = SOURCES[:]
    random.shuffle(sources)
    saved_ref = {"n": 0}
    lock = threading.Lock()

    def source_task(args):
        cat_url, pattern, pagination_tpl = args
        with lock:
            if saved_ref["n"] >= total_limit:
                return 0
            remaining = min(per_source, total_limit - saved_ref["n"])
        n = crawl_source(cat_url, pattern, pagination_tpl, remaining)
        with lock:
            saved_ref["n"] += n
        log.info("Done %-50s → +%-3d  session total %d",
                 cat_url, n, saved_ref["n"])
        return n

    with ThreadPoolExecutor(max_workers=SOURCE_WORKERS,
                            thread_name_prefix="src") as pool:
        list(pool.map(source_task, sources))

    total_after = collection.count_documents({})
    log.info("=== Crawl job done | +%d new | DB total: %d articles ===",
             total_after - total_before, total_after)

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true",
                        help="Run once then exit (no scheduler)")
    parser.add_argument("--limit", type=int, default=5000,
                        help="Max new articles per run (default 5000)")
    parser.add_argument("--hour", type=int, default=3,
                        help="Hour (UTC) for daily scheduled run (default 3)")
    args = parser.parse_args()

    if args.once:
        log.info("Single run mode (limit=%d)", args.limit)
        crawl_job(total_limit=args.limit)
        log.info("Done.")
    else:
        # Run immediately on startup, then daily
        log.info("Scheduler mode — daily at %02d:00 UTC, also running now",
                 args.hour)
        crawl_job(total_limit=args.limit)

        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(
            crawl_job,
            trigger="cron",
            hour=args.hour,
            minute=0,
            kwargs={"total_limit": args.limit},
            id="daily_crawl",
            max_instances=1,          # never overlap runs
            coalesce=True,
        )
        log.info("Scheduler started. Next run at %02d:00 UTC daily. Ctrl+C to stop.",
                 args.hour)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("Scheduler stopped.")