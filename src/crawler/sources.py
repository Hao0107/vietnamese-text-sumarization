"""
sources.py — All crawl targets in one place.

Each entry is a tuple:
    (category_url, article_url_regex, pagination_template | None)

pagination_template uses {page} placeholder (starts at page 2).
None means the site has no pagination or it is not yet mapped.

To add a new source, just append a tuple to the relevant section.
"""

# ── Helpers ────────────────────────────────────────────────────────────────────
# Common regex fragments reused across sites
_VNE   = r"vnexpress\.net/.*-\d+\.html$"
_TTR   = r"tuoitre\.vn/.*-\d+\.htm$"
_TN    = r"thanhnien\.vn/.*-\d+\.html$"
_DTR   = r"dantri\.com\.vn/.*-\d+\.htm$"
_VNN   = r"vietnamnet\.vn/.*-\d+\.html$"
_ZN    = r"znews\.vn/.*-post\d+\.html$"
_ND    = r"nhandan\.vn/.*-post\d+\.html$"
_CF    = r"cafef\.vn/.*-\d+\.chn$"
_CB    = r"cafebiz\.vn/.*-\d+\.chn$"
_GNK   = r"genk\.vn/.*\.chn$"
_K14   = r"kenh14\.vn/.*\.chn$"
_BM    = r"baomoi\.com/[a-z0-9\-]+\.epi$"
_SOHA  = r"soha\.vn/.*-\d+\.htm$"
_ICT   = r"ictnews\.vietnamplus\.vn/.*\.htm$"
_BN    = r"bnews\.vn/.*-\d+\.html$"


SOURCES = [

    # ── VnExpress ─────────────────────────────────────────────────────────────
    ("https://vnexpress.net/khoa-hoc-cong-nghe",  _VNE, "https://vnexpress.net/khoa-hoc-cong-nghe-p{page}"),
    ("https://vnexpress.net/kinh-doanh",           _VNE, "https://vnexpress.net/kinh-doanh-p{page}"),
    ("https://vnexpress.net/thoi-su",              _VNE, "https://vnexpress.net/thoi-su-p{page}"),
    ("https://vnexpress.net/the-gioi",             _VNE, "https://vnexpress.net/the-gioi-p{page}"),
    ("https://vnexpress.net/phap-luat",            _VNE, "https://vnexpress.net/phap-luat-p{page}"),
    ("https://vnexpress.net/suc-khoe",             _VNE, "https://vnexpress.net/suc-khoe-p{page}"),
    ("https://vnexpress.net/giao-duc",             _VNE, "https://vnexpress.net/giao-duc-p{page}"),
    ("https://vnexpress.net/du-lich",              _VNE, "https://vnexpress.net/du-lich-p{page}"),
    ("https://vnexpress.net/the-thao",             _VNE, "https://vnexpress.net/the-thao-p{page}"),
    ("https://vnexpress.net/giai-tri",             _VNE, "https://vnexpress.net/giai-tri-p{page}"),

    # ── Tuổi Trẻ ──────────────────────────────────────────────────────────────
    ("https://tuoitre.vn/khoa-hoc.htm",  _TTR, "https://tuoitre.vn/khoa-hoc.htm?page={page}"),
    ("https://tuoitre.vn/kinh-te.htm",   _TTR, "https://tuoitre.vn/kinh-te.htm?page={page}"),
    ("https://tuoitre.vn/the-gioi.htm",  _TTR, "https://tuoitre.vn/the-gioi.htm?page={page}"),
    ("https://tuoitre.vn/thoi-su.htm",   _TTR, "https://tuoitre.vn/thoi-su.htm?page={page}"),
    ("https://tuoitre.vn/giao-duc.htm",  _TTR, "https://tuoitre.vn/giao-duc.htm?page={page}"),
    ("https://tuoitre.vn/the-thao.htm",  _TTR, "https://tuoitre.vn/the-thao.htm?page={page}"),
    ("https://tuoitre.vn/giai-tri.htm",  _TTR, "https://tuoitre.vn/giai-tri.htm?page={page}"),

    # ── Thanh Niên ────────────────────────────────────────────────────────────
    ("https://thanhnien.vn/cong-nghe-game.htm", _TN, "https://thanhnien.vn/cong-nghe-game.htm?page={page}"),
    ("https://thanhnien.vn/kinh-te",            _TN, "https://thanhnien.vn/kinh-te?page={page}"),
    ("https://thanhnien.vn/thoi-su",            _TN, "https://thanhnien.vn/thoi-su?page={page}"),
    ("https://thanhnien.vn/the-gioi",           _TN, "https://thanhnien.vn/the-gioi?page={page}"),
    ("https://thanhnien.vn/the-thao",           _TN, "https://thanhnien.vn/the-thao?page={page}"),
    ("https://thanhnien.vn/giao-duc",           _TN, "https://thanhnien.vn/giao-duc?page={page}"),

    # ── Dân Trí ───────────────────────────────────────────────────────────────
    ("https://dantri.com.vn/suc-manh-so.htm",  _DTR, "https://dantri.com.vn/suc-manh-so.htm?page={page}"),
    ("https://dantri.com.vn/kinh-doanh.htm",   _DTR, "https://dantri.com.vn/kinh-doanh.htm?page={page}"),
    ("https://dantri.com.vn/the-gioi.htm",     _DTR, "https://dantri.com.vn/the-gioi.htm?page={page}"),
    ("https://dantri.com.vn/suc-khoe.htm",     _DTR, "https://dantri.com.vn/suc-khoe.htm?page={page}"),
    ("https://dantri.com.vn/giao-duc.htm",     _DTR, "https://dantri.com.vn/giao-duc.htm?page={page}"),
    ("https://dantri.com.vn/the-thao.htm",     _DTR, "https://dantri.com.vn/the-thao.htm?page={page}"),
    ("https://dantri.com.vn/giai-tri.htm",     _DTR, "https://dantri.com.vn/giai-tri.htm?page={page}"),

    # ── VietnamNet ────────────────────────────────────────────────────────────
    ("https://vietnamnet.vn/cong-nghe",  _VNN, "https://vietnamnet.vn/cong-nghe?page={page}"),
    ("https://vietnamnet.vn/kinh-doanh", _VNN, "https://vietnamnet.vn/kinh-doanh?page={page}"),
    ("https://vietnamnet.vn/the-gioi",   _VNN, "https://vietnamnet.vn/the-gioi?page={page}"),
    ("https://vietnamnet.vn/phap-luat",  _VNN, "https://vietnamnet.vn/phap-luat?page={page}"),
    ("https://vietnamnet.vn/the-thao",   _VNN, "https://vietnamnet.vn/the-thao?page={page}"),
    ("https://vietnamnet.vn/giao-duc",   _VNN, "https://vietnamnet.vn/giao-duc?page={page}"),

    # ── Znews ─────────────────────────────────────────────────────────────────
    ("https://znews.vn/cong-nghe.html",  _ZN, None),
    ("https://znews.vn/kinh-doanh.html", _ZN, None),
    ("https://znews.vn/the-gioi.html",   _ZN, None),

    # ── Nhân Dân ──────────────────────────────────────────────────────────────
    ("https://nhandan.vn/cong-nghe",  _ND, "https://nhandan.vn/cong-nghe?page={page}"),
    ("https://nhandan.vn/kinhte",     _ND, "https://nhandan.vn/kinhte?page={page}"),
    ("https://nhandan.vn/chinhtri",   _ND, "https://nhandan.vn/chinhtri?page={page}"),
    ("https://nhandan.vn/thegioi",    _ND, "https://nhandan.vn/thegioi?page={page}"),

    # ── CafeF ─────────────────────────────────────────────────────────────────
    ("https://cafef.vn/thi-truong-chung-khoan.html", _CF, "https://cafef.vn/thi-truong-chung-khoan/trang{page}.chn"),
    ("https://cafef.vn/doanh-nghiep.html",           _CF, "https://cafef.vn/doanh-nghiep/trang{page}.chn"),
    ("https://cafef.vn/bat-dong-san.html",           _CF, "https://cafef.vn/bat-dong-san/trang{page}.chn"),
    ("https://cafef.vn/tai-chinh-ngan-hang.html",    _CF, "https://cafef.vn/tai-chinh-ngan-hang/trang{page}.chn"),
    ("https://cafef.vn/vi-mo-dau-tu.html",           _CF, "https://cafef.vn/vi-mo-dau-tu/trang{page}.chn"),

    # ── CafeBiz ───────────────────────────────────────────────────────────────
    ("https://cafebiz.vn/kinh-doanh.chn", _CB, "https://cafebiz.vn/kinh-doanh/trang{page}.chn"),
    ("https://cafebiz.vn/startup.chn",    _CB, "https://cafebiz.vn/startup/trang{page}.chn"),
    ("https://cafebiz.vn/cong-nghe.chn",  _CB, "https://cafebiz.vn/cong-nghe/trang{page}.chn"),

    # ── Genk ──────────────────────────────────────────────────────────────────
    ("https://genk.vn/cong-nghe.chn", _GNK, "https://genk.vn/cong-nghe/trang{page}.chn"),
    ("https://genk.vn/khoa-hoc.chn",  _GNK, "https://genk.vn/khoa-hoc/trang{page}.chn"),
    ("https://genk.vn/game.chn",      _GNK, "https://genk.vn/game/trang{page}.chn"),

    # ── Kenh14 ────────────────────────────────────────────────────────────────
    ("https://kenh14.vn/cong-nghe.chn", _K14, "https://kenh14.vn/cong-nghe/trang{page}.chn"),
    ("https://kenh14.vn/xa-hoi.chn",    _K14, "https://kenh14.vn/xa-hoi/trang{page}.chn"),

    # ── Báo Mới ───────────────────────────────────────────────────────────────
    ("https://baomoi.com/cong-nghe.epi",  _BM, "https://baomoi.com/cong-nghe.epi?page={page}"),
    ("https://baomoi.com/kinh-doanh.epi", _BM, "https://baomoi.com/kinh-doanh.epi?page={page}"),
    ("https://baomoi.com/the-gioi.epi",   _BM, "https://baomoi.com/the-gioi.epi?page={page}"),

    # ── Soha ──────────────────────────────────────────────────────────────────
    ("https://soha.vn/cong-nghe.htm",   _SOHA, "https://soha.vn/cong-nghe/trang{page}.htm"),
    ("https://soha.vn/kinh-doanh.htm",  _SOHA, "https://soha.vn/kinh-doanh/trang{page}.htm"),
    ("https://soha.vn/the-thao.htm",    _SOHA, "https://soha.vn/the-thao/trang{page}.htm"),

    # ── ICT News ──────────────────────────────────────────────────────────────
    ("https://ictnews.vietnamplus.vn/cong-nghe-thong-tin", _ICT, None),
    ("https://ictnews.vietnamplus.vn/vien-thong",          _ICT, None),

    # ── Bnews ─────────────────────────────────────────────────────────────────
    ("https://bnews.vn/kinh-te",   _BN, "https://bnews.vn/kinh-te?page={page}"),
    ("https://bnews.vn/cong-nghe", _BN, "https://bnews.vn/cong-nghe?page={page}"),
    ("https://bnews.vn/the-gioi",  _BN, "https://bnews.vn/the-gioi?page={page}"),

]