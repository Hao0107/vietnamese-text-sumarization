"""
sitemap_sources.py — Sitemap entry points for Vietnamese news sources.

Each entry is a dict with these keys:
  url          : sitemap index or leaf URL to start from
  pattern      : article URL regex (same _XXX constants as sources.py)
  name         : human label used in logs and MongoDB `source` field
  max_depth    : how many levels of <sitemapindex> to recurse (default 3)
  child_limit  : max child sitemaps to follow per index (0 = all).
                 Set a small number (e.g. 6) on huge archives to get only
                 the most-recent monthly shards and avoid 6-hour fetches.
  per_run_limit: max articles to hand off to the processing pipeline per run.
                 Prevents one giant sitemap from consuming the whole budget.

How to find a site's sitemap:
  1. Try /sitemap.xml, /sitemap_index.xml, /news-sitemap.xml
  2. Check robots.txt → "Sitemap:" directive
  3. Google: site:example.com filetype:xml sitemap

Pattern notes:
  • Reuse the same regex constants defined in sources.py where possible.
  • If the site's article URLs don't match those patterns, define a new one here.

child_limit guidance:
  • 0  (unlimited) — small archives, or when you want full history (one-shot runs)
  • 6  — recent 6 months; good for daily incremental runs
  • 12 — recent year; good for weekly runs

Yield benchmark (verified by manual inspection, 2024):
  VnExpress news sitemap  : ~1,000 URLs/month  → ~12,000/year
  Tuổi Trẻ news sitemap   : ~800  URLs/month   → ~9,600/year
  VTV news sitemap         : ~1,200 URLs/month  → ~14,400/year
  VOV news sitemap         : ~600  URLs/month   → ~7,200/year
  Total across ~20 sources : ~150k–250k historical URLs available
"""

# ── Regex patterns (keep in sync with sources.py) ─────────────────────────────
_VNE  = r"vnexpress\.net/.*-\d+\.html$"
_TTR  = r"tuoitre\.vn/.*-\d+\.htm$"
_TN   = r"thanhnien\.vn/.*-\d+\.html$"
_DTR  = r"dantri\.com\.vn/.*-\d+\.htm$"
_VNN  = r"vietnamnet\.vn/.*-\d+\.html$"
_ND   = r"nhandan\.vn/.*-post\d+\.html$"
_VTV  = r"vtv\.vn/.*-\d+\.htm$"
_VOV  = r"vov\.vn/.*-post\d+\.vov$"
_VNP  = r"vietnamplus\.vn/.*-\d+\.vnp$"
_LD   = r"laodong\.vn/.*-\d+\.ldo$"
_SGP  = r"sggp\.org\.vn/.*-\d+\.html$"
_CF   = r"cafef\.vn/.*-\d+\.chn$"
_CB   = r"cafebiz\.vn/.*-\d+\.chn$"
_GNK  = r"genk\.vn/.*\.chn$"
_K14  = r"kenh14\.vn/.*\.chn$"
_SOHA = r"soha\.vn/.*-\d+\.htm$"
_BN   = r"bnews\.vn/.*-\d+\.html$"
_NDLD = r"nld\.com\.vn/.*-\d+\.htm$"
_PLO  = r"plo\.vn/.*-\d+\.html$"
_TTCT = r"baotintuc\.vn/.*-\d+\.htm$"
_QDND = r"qdnd\.vn/.*-\d+\.html$"
_SKTE = r"suckhoedoisong\.vn/.*-\d+\.htm$"
_VTCN = r"vtc\.vn/.*-ar\d+\.html$"


SITEMAP_SOURCES = [

    # ── VnExpress ──────────────────────────────────────────────────────────────
    # robots.txt: Sitemap: https://vnexpress.net/sitemap/news.rss (RSS)
    #             Sitemap: https://vnexpress.net/google-news-sitemap.xml
    # The Google News sitemap is a standard <urlset> updated every few minutes.
    # The monthly archive index holds years of history.
    {
        "name":          "VnExpress – news sitemap (recent)",
        "url":           "https://vnexpress.net/google-news-sitemap.xml",
        "pattern":       _VNE,
        "max_depth":     1,
        "child_limit":   0,
        "per_run_limit": 5000,
    },
    {
        "name":          "VnExpress – monthly archive (history)",
        "url":           "https://vnexpress.net/sitemap/sitemap-index.xml",
        "pattern":       _VNE,
        "max_depth":     2,
        "child_limit":   6,        # 6 most-recent monthly shards
        "per_run_limit": 8000,
    },

    # ── Tuổi Trẻ ──────────────────────────────────────────────────────────────
    # robots.txt: Sitemap: https://tuoitre.vn/sitemap.xml
    # Index → monthly shards → articles
    {
        "name":          "Tuổi Trẻ – recent (news sitemap)",
        "url":           "https://tuoitre.vn/google-news-sitemap.xml",
        "pattern":       _TTR,
        "max_depth":     1,
        "child_limit":   0,
        "per_run_limit": 5000,
    },
    {
        "name":          "Tuổi Trẻ – archive index",
        "url":           "https://tuoitre.vn/sitemap.xml",
        "pattern":       _TTR,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 8000,
    },

    # ── Thanh Niên ────────────────────────────────────────────────────────────
    {
        "name":          "Thanh Niên – news sitemap",
        "url":           "https://thanhnien.vn/sitemap/news-sitemap.xml",
        "pattern":       _TN,
        "max_depth":     1,
        "child_limit":   0,
        "per_run_limit": 4000,
    },
    {
        "name":          "Thanh Niên – archive index",
        "url":           "https://thanhnien.vn/sitemap/sitemap-index.xml",
        "pattern":       _TN,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 6000,
    },

    # ── Dân Trí ───────────────────────────────────────────────────────────────
    # robots.txt: Sitemap: https://dantri.com.vn/sitemap.xml
    {
        "name":          "Dân Trí – news sitemap",
        "url":           "https://dantri.com.vn/news-sitemap.xml",
        "pattern":       _DTR,
        "max_depth":     1,
        "child_limit":   0,
        "per_run_limit": 4000,
    },
    {
        "name":          "Dân Trí – archive index",
        "url":           "https://dantri.com.vn/sitemap.xml",
        "pattern":       _DTR,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 6000,
    },

    # ── VietnamNet ────────────────────────────────────────────────────────────
    {
        "name":          "VietnamNet – news sitemap",
        "url":           "https://vietnamnet.vn/sitemap/news-sitemap.xml",
        "pattern":       _VNN,
        "max_depth":     1,
        "child_limit":   0,
        "per_run_limit": 4000,
    },
    {
        "name":          "VietnamNet – archive index",
        "url":           "https://vietnamnet.vn/sitemap.xml",
        "pattern":       _VNN,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 6000,
    },

    # ── VTV ───────────────────────────────────────────────────────────────────
    # Very large archive — limit children aggressively for daily runs
    {
        "name":          "VTV – news sitemap",
        "url":           "https://vtv.vn/sitemap/news-sitemap.xml",
        "pattern":       _VTV,
        "max_depth":     1,
        "child_limit":   0,
        "per_run_limit": 5000,
    },
    {
        "name":          "VTV – archive index",
        "url":           "https://vtv.vn/sitemap.xml",
        "pattern":       _VTV,
        "max_depth":     2,
        "child_limit":   4,
        "per_run_limit": 6000,
    },

    # ── VOV (Đài Tiếng Nói Việt Nam) ─────────────────────────────────────────
    {
        "name":          "VOV – sitemap index",
        "url":           "https://vov.vn/sitemap.xml",
        "pattern":       _VOV,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 5000,
    },

    # ── VietnamPlus / TTXVN ───────────────────────────────────────────────────
    {
        "name":          "VietnamPlus – sitemap index",
        "url":           "https://www.vietnamplus.vn/sitemap.xml",
        "pattern":       _VNP,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 4000,
    },

    # ── Nhân Dân ──────────────────────────────────────────────────────────────
    {
        "name":          "Nhân Dân – sitemap index",
        "url":           "https://nhandan.vn/sitemap.xml",
        "pattern":       _ND,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 4000,
    },

    # ── Báo Lao Động ──────────────────────────────────────────────────────────
    {
        "name":          "Lao Động – sitemap index",
        "url":           "https://laodong.vn/sitemap.xml",
        "pattern":       _LD,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 4000,
    },

    # ── Sài Gòn Giải Phóng ────────────────────────────────────────────────────
    {
        "name":          "SGGP – sitemap index",
        "url":           "https://www.sggp.org.vn/sitemap.xml",
        "pattern":       _SGP,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 3000,
    },

    # ── CafeF ─────────────────────────────────────────────────────────────────
    {
        "name":          "CafeF – sitemap index",
        "url":           "https://cafef.vn/sitemap.xml",
        "pattern":       _CF,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 4000,
    },

    # ── CafeBiz ───────────────────────────────────────────────────────────────
    {
        "name":          "CafeBiz – sitemap index",
        "url":           "https://cafebiz.vn/sitemap.xml",
        "pattern":       _CB,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 3000,
    },

    # ── Genk ──────────────────────────────────────────────────────────────────
    {
        "name":          "Genk – sitemap index",
        "url":           "https://genk.vn/sitemap.xml",
        "pattern":       _GNK,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 3000,
    },

    # ── Kenh14 ────────────────────────────────────────────────────────────────
    {
        "name":          "Kenh14 – sitemap index",
        "url":           "https://kenh14.vn/sitemap.xml",
        "pattern":       _K14,
        "max_depth":     2,
        "child_limit":   4,        # Kenh14 có rất nhiều shard; giới hạn để không quá lâu
        "per_run_limit": 3000,
    },

    # ── Soha ──────────────────────────────────────────────────────────────────
    {
        "name":          "Soha – sitemap index",
        "url":           "https://soha.vn/sitemap.xml",
        "pattern":       _SOHA,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 3000,
    },

    # ── Bnews ─────────────────────────────────────────────────────────────────
    {
        "name":          "Bnews – sitemap index",
        "url":           "https://bnews.vn/sitemap.xml",
        "pattern":       _BN,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 3000,
    },

    # ── Người Lao Động ────────────────────────────────────────────────────────
    {
        "name":          "Người Lao Động – sitemap index",
        "url":           "https://nld.com.vn/sitemap.xml",
        "pattern":       _NDLD,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 4000,
    },

    # ── Pháp Luật Online ──────────────────────────────────────────────────────
    {
        "name":          "PLO – sitemap index",
        "url":           "https://plo.vn/sitemap.xml",
        "pattern":       _PLO,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 4000,
    },

    # ── Báo Tin Tức / TTXVN ───────────────────────────────────────────────────
    {
        "name":          "Báo Tin Tức – sitemap index",
        "url":           "https://baotintuc.vn/sitemap.xml",
        "pattern":       _TTCT,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 3000,
    },

    # ── Quân Đội Nhân Dân ─────────────────────────────────────────────────────
    {
        "name":          "QDND – sitemap index",
        "url":           "https://qdnd.vn/sitemap.xml",
        "pattern":       _QDND,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 3000,
    },

    # ── Sức Khỏe & Đời Sống ───────────────────────────────────────────────────
    {
        "name":          "Sức Khỏe & Đời Sống – sitemap index",
        "url":           "https://suckhoedoisong.vn/sitemap.xml",
        "pattern":       _SKTE,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 3000,
    },

    # ── VTC News ──────────────────────────────────────────────────────────────
    {
        "name":          "VTC News – sitemap index",
        "url":           "https://vtc.vn/sitemap.xml",
        "pattern":       _VTCN,
        "max_depth":     2,
        "child_limit":   6,
        "per_run_limit": 3000,
    },
]