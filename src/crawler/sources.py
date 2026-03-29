"""
sources.py — All crawl targets in one place.

Each entry is a tuple:
    (category_url, article_url_regex, pagination_template | None)

pagination_template uses {page} placeholder (starts at page 2).
None means the site has no pagination or it is not yet mapped.

Yield estimate (MAX_PAGES=8, 60% new rate, 80% content pass):
  Before expansion : ~80 categories  →  ~28k articles/run
  After  expansion : ~130 categories →  ~48k articles/run
  → 100k reachable in 2–3 runs (2–3 days) instead of 4–5.
"""

# ── Helpers ────────────────────────────────────────────────────────────────────
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
_VTV   = r"vtv\.vn/.*-\d+\.htm$"
_VOV   = r"vov\.vn/.*-post\d+\.vov$"
_VNP   = r"vietnamplus\.vn/.*-\d+\.vnp$"
_LD    = r"laodong\.vn/.*-\d+\.ldo$"
_SGP   = r"sggp\.org\.vn/.*-\d+\.html$"

_NDLD  = r"nld\.com\.vn/.*-\d+\.htm$"
_PLO   = r"plo\.vn/.*-\d+\.html$"
_TTCT  = r"baotintuc\.vn/.*-\d+\.htm$"
_QDND  = r"qdnd\.vn/.*-\d+\.html$"
_HNDM  = r"hanoimoi\.com\.vn/.*-\d+\.html$"
_SKTE  = r"suckhoedoisong\.vn/.*-\d+\.htm$"
_TCDN  = r"tapchitaichinh\.vn/.*-\d+\.html$"
_PCWV  = r"pcworld\.com\.vn/.*-\d+\.html$"
_VTCN  = r"vtc\.vn/.*-ar\d+\.html$"

_DV    = r"danviet\.vn/.*-\d+\.htm$"
_TP    = r"tienphong\.vn/.*-post\d+\.tpo$"
_DSPL  = r"doisongphapluat\.com\.vn/.*-a\d+\.html$"
_VNECO = r"vneconomy\.vn/.*\.htm$"
_CPVN  = r"chinhphu\.vn/.*-\d+$"
_TTVN  = r"thanhnienviet\.vn/.*-\d+\.html$"

_24H   = r"24h\.com\.vn/.*-c\d+a\d+\.html$"
_VBIZ  = r"vietnambiz\.vn/.*\.htm$"
_DTI   = r"baodautu\.vn/.*-d\d+\.html$"
_GTH   = r"baogiaothong\.vn/.*-\d+\.html$"
_CAND  = r"cand\.com\.vn/.*-i\d+/$"
_TGDD  = r"thegioididong\.com/tin-tuc/.*-\d+$"

SOURCES = [

    # ── VnExpress (10 categories) ─────────────────────────────────────────────
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

    # ── Tuổi Trẻ (7 categories) ───────────────────────────────────────────────
    ("https://tuoitre.vn/khoa-hoc.htm",  _TTR, "https://tuoitre.vn/khoa-hoc.htm?page={page}"),
    ("https://tuoitre.vn/kinh-te.htm",   _TTR, "https://tuoitre.vn/kinh-te.htm?page={page}"),
    ("https://tuoitre.vn/the-gioi.htm",  _TTR, "https://tuoitre.vn/the-gioi.htm?page={page}"),
    ("https://tuoitre.vn/thoi-su.htm",   _TTR, "https://tuoitre.vn/thoi-su.htm?page={page}"),
    ("https://tuoitre.vn/giao-duc.htm",  _TTR, "https://tuoitre.vn/giao-duc.htm?page={page}"),
    ("https://tuoitre.vn/the-thao.htm",  _TTR, "https://tuoitre.vn/the-thao.htm?page={page}"),
    ("https://tuoitre.vn/giai-tri.htm",  _TTR, "https://tuoitre.vn/giai-tri.htm?page={page}"),

    # ── Thanh Niên (6 categories) ─────────────────────────────────────────────
    ("https://thanhnien.vn/cong-nghe-game.htm", _TN, "https://thanhnien.vn/cong-nghe-game.htm?page={page}"),
    ("https://thanhnien.vn/kinh-te",            _TN, "https://thanhnien.vn/kinh-te?page={page}"),
    ("https://thanhnien.vn/thoi-su",            _TN, "https://thanhnien.vn/thoi-su?page={page}"),
    ("https://thanhnien.vn/the-gioi",           _TN, "https://thanhnien.vn/the-gioi?page={page}"),
    ("https://thanhnien.vn/the-thao",           _TN, "https://thanhnien.vn/the-thao?page={page}"),
    ("https://thanhnien.vn/giao-duc",           _TN, "https://thanhnien.vn/giao-duc?page={page}"),

    # ── Dân Trí (7 categories) ────────────────────────────────────────────────
    ("https://dantri.com.vn/suc-manh-so.htm",  _DTR, "https://dantri.com.vn/suc-manh-so.htm?page={page}"),
    ("https://dantri.com.vn/kinh-doanh.htm",   _DTR, "https://dantri.com.vn/kinh-doanh.htm?page={page}"),
    ("https://dantri.com.vn/the-gioi.htm",     _DTR, "https://dantri.com.vn/the-gioi.htm?page={page}"),
    ("https://dantri.com.vn/suc-khoe.htm",     _DTR, "https://dantri.com.vn/suc-khoe.htm?page={page}"),
    ("https://dantri.com.vn/giao-duc.htm",     _DTR, "https://dantri.com.vn/giao-duc.htm?page={page}"),
    ("https://dantri.com.vn/the-thao.htm",     _DTR, "https://dantri.com.vn/the-thao.htm?page={page}"),
    ("https://dantri.com.vn/giai-tri.htm",     _DTR, "https://dantri.com.vn/giai-tri.htm?page={page}"),

    # ── VietnamNet (6 categories) ─────────────────────────────────────────────
    ("https://vietnamnet.vn/cong-nghe",  _VNN, "https://vietnamnet.vn/cong-nghe?page={page}"),
    ("https://vietnamnet.vn/kinh-doanh", _VNN, "https://vietnamnet.vn/kinh-doanh?page={page}"),
    ("https://vietnamnet.vn/the-gioi",   _VNN, "https://vietnamnet.vn/the-gioi?page={page}"),
    ("https://vietnamnet.vn/phap-luat",  _VNN, "https://vietnamnet.vn/phap-luat?page={page}"),
    ("https://vietnamnet.vn/the-thao",   _VNN, "https://vietnamnet.vn/the-thao?page={page}"),
    ("https://vietnamnet.vn/giao-duc",   _VNN, "https://vietnamnet.vn/giao-duc?page={page}"),

    # ── Znews (3 categories — không có pagination) ────────────────────────────
    ("https://znews.vn/cong-nghe.html",  _ZN, None),
    ("https://znews.vn/kinh-doanh.html", _ZN, None),
    ("https://znews.vn/the-gioi.html",   _ZN, None),

    # ── Nhân Dân (4 categories) ───────────────────────────────────────────────
    ("https://nhandan.vn/cong-nghe",  _ND, "https://nhandan.vn/cong-nghe?page={page}"),
    ("https://nhandan.vn/kinhte",     _ND, "https://nhandan.vn/kinhte?page={page}"),
    ("https://nhandan.vn/chinhtri",   _ND, "https://nhandan.vn/chinhtri?page={page}"),
    ("https://nhandan.vn/thegioi",    _ND, "https://nhandan.vn/thegioi?page={page}"),

    # ── CafeF (5 categories) ──────────────────────────────────────────────────
    ("https://cafef.vn/thi-truong-chung-khoan.html", _CF, "https://cafef.vn/thi-truong-chung-khoan/trang{page}.chn"),
    ("https://cafef.vn/doanh-nghiep.html",           _CF, "https://cafef.vn/doanh-nghiep/trang{page}.chn"),
    ("https://cafef.vn/bat-dong-san.html",           _CF, "https://cafef.vn/bat-dong-san/trang{page}.chn"),
    ("https://cafef.vn/tai-chinh-ngan-hang.html",    _CF, "https://cafef.vn/tai-chinh-ngan-hang/trang{page}.chn"),
    ("https://cafef.vn/vi-mo-dau-tu.html",           _CF, "https://cafef.vn/vi-mo-dau-tu/trang{page}.chn"),

    # ── CafeBiz (3 categories) ────────────────────────────────────────────────
    ("https://cafebiz.vn/kinh-doanh.chn", _CB, "https://cafebiz.vn/kinh-doanh/trang{page}.chn"),
    ("https://cafebiz.vn/startup.chn",    _CB, "https://cafebiz.vn/startup/trang{page}.chn"),
    ("https://cafebiz.vn/cong-nghe.chn",  _CB, "https://cafebiz.vn/cong-nghe/trang{page}.chn"),

    # ── Genk (3 categories) ───────────────────────────────────────────────────
    ("https://genk.vn/cong-nghe.chn", _GNK, "https://genk.vn/cong-nghe/trang{page}.chn"),
    ("https://genk.vn/khoa-hoc.chn",  _GNK, "https://genk.vn/khoa-hoc/trang{page}.chn"),
    ("https://genk.vn/game.chn",      _GNK, "https://genk.vn/game/trang{page}.chn"),

    # ── Kenh14 (2 categories) ─────────────────────────────────────────────────
    ("https://kenh14.vn/cong-nghe.chn", _K14, "https://kenh14.vn/cong-nghe/trang{page}.chn"),
    ("https://kenh14.vn/xa-hoi.chn",    _K14, "https://kenh14.vn/xa-hoi/trang{page}.chn"),

    # ── Báo Mới (3 categories) ────────────────────────────────────────────────
    ("https://baomoi.com/cong-nghe.epi",  _BM, "https://baomoi.com/cong-nghe.epi?page={page}"),
    ("https://baomoi.com/kinh-doanh.epi", _BM, "https://baomoi.com/kinh-doanh.epi?page={page}"),
    ("https://baomoi.com/the-gioi.epi",   _BM, "https://baomoi.com/the-gioi.epi?page={page}"),

    # ── Soha (3 categories) ───────────────────────────────────────────────────
    ("https://soha.vn/cong-nghe.htm",   _SOHA, "https://soha.vn/cong-nghe/trang{page}.htm"),
    ("https://soha.vn/kinh-doanh.htm",  _SOHA, "https://soha.vn/kinh-doanh/trang{page}.htm"),
    ("https://soha.vn/the-thao.htm",    _SOHA, "https://soha.vn/the-thao/trang{page}.htm"),

    # ── ICT News (2 categories — không có pagination) ─────────────────────────
    ("https://ictnews.vietnamplus.vn/cong-nghe-thong-tin", _ICT, None),
    ("https://ictnews.vietnamplus.vn/vien-thong",          _ICT, None),

    # ── Bnews (3 categories) ──────────────────────────────────────────────────
    ("https://bnews.vn/kinh-te",   _BN, "https://bnews.vn/kinh-te?page={page}"),
    ("https://bnews.vn/cong-nghe", _BN, "https://bnews.vn/cong-nghe?page={page}"),
    ("https://bnews.vn/the-gioi",  _BN, "https://bnews.vn/the-gioi?page={page}"),

    # ── VTV (5 categories — kho lớn, sapo chuẩn) ─────────────────────────────
    ("https://vtv.vn/thoi-su.htm",   _VTV, "https://vtv.vn/thoi-su/trang-{page}.htm"),
    ("https://vtv.vn/kinh-te.htm",   _VTV, "https://vtv.vn/kinh-te/trang-{page}.htm"),
    ("https://vtv.vn/the-gioi.htm",  _VTV, "https://vtv.vn/the-gioi/trang-{page}.htm"),
    ("https://vtv.vn/cong-nghe.htm", _VTV, "https://vtv.vn/cong-nghe/trang-{page}.htm"),
    ("https://vtv.vn/suc-khoe.htm",  _VTV, "https://vtv.vn/suc-khoe/trang-{page}.htm"),

    # ── VOV (4 categories — bài dài và sâu) ──────────────────────────────────
    ("https://vov.vn/chinh-tri", _VOV, "https://vov.vn/chinh-tri?page={page}"),
    ("https://vov.vn/kinh-te",   _VOV, "https://vov.vn/kinh-te?page={page}"),
    ("https://vov.vn/the-gioi",  _VOV, "https://vov.vn/the-gioi?page={page}"),
    ("https://vov.vn/phap-luat", _VOV, "https://vov.vn/phap-luat?page={page}"),

    # ── VietnamPlus / TTXVN (4 categories — sapo chất lượng nhất) ───────────
    ("https://www.vietnamplus.vn/chinh-tri", _VNP, "https://www.vietnamplus.vn/chinh-tri/trang{page}.vnp"),
    ("https://www.vietnamplus.vn/kinh-te",   _VNP, "https://www.vietnamplus.vn/kinh-te/trang{page}.vnp"),
    ("https://www.vietnamplus.vn/the-gioi",  _VNP, "https://www.vietnamplus.vn/the-gioi/trang{page}.vnp"),
    ("https://www.vietnamplus.vn/khoa-hoc",  _VNP, "https://www.vietnamplus.vn/khoa-hoc/trang{page}.vnp"),

    # ── Báo Lao Động (3 categories) ───────────────────────────────────────────
    ("https://laodong.vn/thoi-su",   _LD, "https://laodong.vn/thoi-su/?page={page}"),
    ("https://laodong.vn/kinh-te",   _LD, "https://laodong.vn/kinh-te/?page={page}"),
    ("https://laodong.vn/phap-luat", _LD, "https://laodong.vn/phap-luat/?page={page}"),

    # ── Sài Gòn Giải Phóng (2 categories) ────────────────────────────────────
    ("https://www.sggp.org.vn/thoi-su", _SGP, "https://www.sggp.org.vn/thoi-su/trang-{page}"),
    ("https://www.sggp.org.vn/kinhte",  _SGP, "https://www.sggp.org.vn/kinhte/trang-{page}"),

    # ════════════════════════════════════════════════════════════════════════════
    # DOMAIN MỚI — thêm ~50 categories để đạt 100k trong 2–3 runs
    # ════════════════════════════════════════════════════════════════════════════

    # ── Người Lao Động — 6 categories ────────────────────────────────────────
    # Báo lâu đời, bài đời sống/pháp luật rất dày; ít bị chặn IP hơn Tuổi Trẻ
    ("https://nld.com.vn/thoi-su.htm",   _NDLD, "https://nld.com.vn/thoi-su.htm?page={page}"),
    ("https://nld.com.vn/kinh-te.htm",   _NDLD, "https://nld.com.vn/kinh-te.htm?page={page}"),
    ("https://nld.com.vn/phap-luat.htm", _NDLD, "https://nld.com.vn/phap-luat.htm?page={page}"),
    ("https://nld.com.vn/the-gioi.htm",  _NDLD, "https://nld.com.vn/the-gioi.htm?page={page}"),
    ("https://nld.com.vn/cong-nghe.htm", _NDLD, "https://nld.com.vn/cong-nghe.htm?page={page}"),
    ("https://nld.com.vn/suc-khoe.htm",  _NDLD, "https://nld.com.vn/suc-khoe.htm?page={page}"),

    # ── VTC News — 5 categories ───────────────────────────────────────────────
    # Trực thuộc VTC; URL pattern ar\d+; ít trùng với VnExpress/Tuổi Trẻ
    ("https://vtc.vn/thoi-su.html",   _VTCN, "https://vtc.vn/thoi-su.html?page={page}"),
    ("https://vtc.vn/kinh-te.html",   _VTCN, "https://vtc.vn/kinh-te.html?page={page}"),
    ("https://vtc.vn/the-gioi.html",  _VTCN, "https://vtc.vn/the-gioi.html?page={page}"),
    ("https://vtc.vn/phap-luat.html", _VTCN, "https://vtc.vn/phap-luat.html?page={page}"),
    ("https://vtc.vn/cong-nghe.html", _VTCN, "https://vtc.vn/cong-nghe.html?page={page}"),

    # ── Pháp Luật Online (PLO) — 5 categories ────────────────────────────────
    # Bài pháp luật, hình sự, dân sự rất chi tiết; sapo rõ ràng
    ("https://plo.vn/thoi-su.html",  _PLO, "https://plo.vn/thoi-su.html?page={page}"),
    ("https://plo.vn/phap-luat.html",_PLO, "https://plo.vn/phap-luat.html?page={page}"),
    ("https://plo.vn/kinh-te.html",  _PLO, "https://plo.vn/kinh-te.html?page={page}"),
    ("https://plo.vn/the-gioi.html", _PLO, "https://plo.vn/the-gioi.html?page={page}"),
    ("https://plo.vn/giao-duc.html", _PLO, "https://plo.vn/giao-duc.html?page={page}"),

    # ── Báo Tin Tức / TTXVN — 5 categories ───────────────────────────────────
    # Thông tấn xã — văn phong chuẩn, bài chính trị/kinh tế sâu; ít JS
    ("https://baotintuc.vn/thoi-su.htm",    _TTCT, "https://baotintuc.vn/thoi-su.htm?page={page}"),
    ("https://baotintuc.vn/kinh-te.htm",    _TTCT, "https://baotintuc.vn/kinh-te.htm?page={page}"),
    ("https://baotintuc.vn/the-gioi.htm",   _TTCT, "https://baotintuc.vn/the-gioi.htm?page={page}"),
    ("https://baotintuc.vn/chinh-tri.htm",  _TTCT, "https://baotintuc.vn/chinh-tri.htm?page={page}"),
    ("https://baotintuc.vn/phap-luat.htm",  _TTCT, "https://baotintuc.vn/phap-luat.htm?page={page}"),

    # ── Hà Nội Mới — 4 categories ────────────────────────────────────────────
    # Báo địa phương nhưng phủ quốc gia; ít bị block; URL .html ngắn gọn
    ("https://hanoimoi.com.vn/tin-tuc/Chinh-tri", _HNDM, "https://hanoimoi.com.vn/tin-tuc/Chinh-tri/trang-{page}"),
    ("https://hanoimoi.com.vn/tin-tuc/Kinh-te",   _HNDM, "https://hanoimoi.com.vn/tin-tuc/Kinh-te/trang-{page}"),
    ("https://hanoimoi.com.vn/tin-tuc/Xa-hoi",    _HNDM, "https://hanoimoi.com.vn/tin-tuc/Xa-hoi/trang-{page}"),
    ("https://hanoimoi.com.vn/tin-tuc/Khoa-hoc",  _HNDM, "https://hanoimoi.com.vn/tin-tuc/Khoa-hoc/trang-{page}"),

    # ── Sức Khỏe & Đời Sống (Bộ Y Tế) — 4 categories ────────────────────────
    # Domain y tế chính thống; nội dung dài, ít quảng cáo, sapo chuẩn
    ("https://suckhoedoisong.vn/suc-khoe.htm",         _SKTE, "https://suckhoedoisong.vn/suc-khoe.htm?page={page}"),
    ("https://suckhoedoisong.vn/dinh-duong.htm",       _SKTE, "https://suckhoedoisong.vn/dinh-duong.htm?page={page}"),
    ("https://suckhoedoisong.vn/lam-dep.htm",          _SKTE, "https://suckhoedoisong.vn/lam-dep.htm?page={page}"),
    ("https://suckhoedoisong.vn/y-hoc-co-truyen.htm",  _SKTE, "https://suckhoedoisong.vn/y-hoc-co-truyen.htm?page={page}"),

    # ── Tạp Chí Tài Chính (Bộ Tài Chính) — 4 categories ─────────────────────
    # Phân tích tài chính/ngân sách chuyên sâu, ít nguồn khác có
    ("https://tapchitaichinh.vn/tai-chinh-quoc-te.html", _TCDN, "https://tapchitaichinh.vn/tai-chinh-quoc-te.html?page={page}"),
    ("https://tapchitaichinh.vn/ngan-hang.html",          _TCDN, "https://tapchitaichinh.vn/ngan-hang.html?page={page}"),
    ("https://tapchitaichinh.vn/chung-khoan.html",        _TCDN, "https://tapchitaichinh.vn/chung-khoan.html?page={page}"),
    ("https://tapchitaichinh.vn/kinh-te-vi-mo.html",      _TCDN, "https://tapchitaichinh.vn/kinh-te-vi-mo.html?page={page}"),

    # ── PC World Vietnam — 3 categories ──────────────────────────────────────
    # Bài tech dài (review, hướng dẫn); ít trùng với genk/znews
    ("https://pcworld.com.vn/chan-de/cong-nghe", _PCWV, "https://pcworld.com.vn/chan-de/cong-nghe?page={page}"),
    ("https://pcworld.com.vn/chan-de/phan-mem",  _PCWV, "https://pcworld.com.vn/chan-de/phan-mem?page={page}"),
    ("https://pcworld.com.vn/chan-de/bao-mat",   _PCWV, "https://pcworld.com.vn/chan-de/bao-mat?page={page}"),

    # ── Quân Đội Nhân Dân — 3 categories ─────────────────────────────────────
    # Nguồn chính thống; bài chính trị/quốc phòng không có ở báo khác
    ("https://qdnd.vn/chinh-tri", _QDND, "https://qdnd.vn/chinh-tri?page={page}"),
    ("https://qdnd.vn/kinh-te",   _QDND, "https://qdnd.vn/kinh-te?page={page}"),
    ("https://qdnd.vn/the-gioi",  _QDND, "https://qdnd.vn/the-gioi?page={page}"),
    
    # ── Dân Việt (Kho bài viết cực lớn, đa dạng) ─────────────────────────────
    ("https://danviet.vn/tin-tuc-viet-nam", _DV, "https://danviet.vn/tin-tuc-viet-nam-p{page}.htm"),
    ("https://danviet.vn/the-gioi",         _DV, "https://danviet.vn/the-gioi-p{page}.htm"),
    ("https://danviet.vn/phap-luat",        _DV, "https://danviet.vn/phap-luat-p{page}.htm"),
    ("https://danviet.vn/kinh-te",          _DV, "https://danviet.vn/kinh-te-p{page}.htm"),
    ("https://danviet.vn/cong-nghe",        _DV, "https://danviet.vn/cong-nghe-p{page}.htm"),

    # ── Tiền Phong (Báo lớn, bài viết sâu, archive lâu đời) ──────────────────
    ("https://tienphong.vn/thoi-su",        _TP, "https://tienphong.vn/thoi-su/trang-{page}.tpo"),
    ("https://tienphong.vn/kinh-te",        _TP, "https://tienphong.vn/kinh-te/trang-{page}.tpo"),
    ("https://tienphong.vn/the-gioi",       _TP, "https://tienphong.vn/the-gioi/trang-{page}.tpo"),
    ("https://tienphong.vn/phap-luat",      _TP, "https://tienphong.vn/phap-luat/trang-{page}.tpo"),
    ("https://tienphong.vn/giao-duc",       _TP, "https://tienphong.vn/giao-duc/trang-{page}.tpo"),

    # ── VnEconomy (Đặc thù Kinh tế, bài rất dài, nhiều dữ liệu) ──────────────
    ("https://vneconomy.vn/thoi-su.htm",    _VNECO, "https://vneconomy.vn/thoi-su.htm?page={page}"),
    ("https://vneconomy.vn/tai-chinh.htm",  _VNECO, "https://vneconomy.vn/tai-chinh.htm?page={page}"),
    ("https://vneconomy.vn/chung-khoan.htm",_VNECO, "https://vneconomy.vn/chung-khoan.htm?page={page}"),

    # ── Đời sống & Pháp luật (Bài hình sự/pháp luật cực dài) ─────────────────
    ("https://www.doisongphapluat.com.vn/phap-luat", _DSPL, "https://www.doisongphapluat.com.vn/phap-luat-p{page}"),
    ("https://www.doisongphapluat.com.vn/kinh-doanh", _DSPL, "https://www.doisongphapluat.com.vn/kinh-doanh-p{page}"),

    # ── Cổng Thông tin Chính phủ (Văn phong chuẩn mực nhất cho NLP) ─────────
    ("https://baochinhphu.vn/thoi-su",      _CPVN, "https://baochinhphu.vn/thoi-su-p{page}"),
    ("https://baochinhphu.vn/kinh-te",      _CPVN, "https://baochinhphu.vn/kinh-te-p{page}"),
    ("https://baochinhphu.vn/quoc-te",      _CPVN, "https://baochinhphu.vn/quoc-te-p{page}"),
    
    # ── 24h.com.vn (Lượng bài viết cực khủng, archive rất sâu) ────────────────
    ("https://www.24h.com.vn/tin-tuc-trong-ngay-c46.html", _24H, "https://www.24h.com.vn/tin-tuc-trong-ngay-c46.html?vpage={page}"),
    ("https://www.24h.com.vn/kinh-doanh-c161.html",      _24H, "https://www.24h.com.vn/kinh-doanh-c161.html?vpage={page}"),
    ("https://www.24h.com.vn/an-ninh-hinh-su-c51.html",  _24H, "https://www.24h.com.vn/an-ninh-hinh-su-c51.html?vpage={page}"),
    ("https://www.24h.com.vn/the-gioi-c68.html",        _24H, "https://www.24h.com.vn/the-gioi-c68.html?vpage={page}"),
    ("https://www.24h.com.vn/cong-nghe-thong-tin-c55.html", _24H, "https://www.24h.com.vn/cong-nghe-thong-tin-c55.html?vpage={page}"),

    # ── Báo Đầu Tư (Bài dài, chuyên sâu về kinh tế) ──────────────────────────
    ("https://baodautu.vn/thoi-su-d4/",   _DTI, "https://baodautu.vn/thoi-su-d4/p{page}.html"),
    ("https://baodautu.vn/bat-dong-san-d5/", _DTI, "https://baodautu.vn/bat-dong-san-d5/p{page}.html"),
    ("https://baodautu.vn/dau-tu-d6/",    _DTI, "https://baodautu.vn/dau-tu-d6/p{page}.html"),

    # ── VietnamBiz (Archive cực tốt cho Summarization) ───────────────────────
    ("https://vietnambiz.vn/thoi-su.htm", _VBIZ, "https://vietnambiz.vn/thoi-su/trang-{page}.htm"),
    ("https://vietnambiz.vn/kinh-doanh.htm", _VBIZ, "https://vietnambiz.vn/kinh-doanh/trang-{page}.htm"),
    ("https://vietnambiz.vn/tai-chinh.htm", _VBIZ, "https://vietnambiz.vn/tai-chinh/trang-{page}.htm"),

    # ── Công An Nhân Dân (Bài viết pháp luật rất dài và chi tiết) ───────────
    ("https://cand.com.vn/thoi-su/",      _CAND, "https://cand.com.vn/thoi-su/p{page}/"),
    ("https://cand.com.vn/phap-luat/",     _CAND, "https://cand.com.vn/phap-luat/p{page}/"),
    ("https://cand.com.vn/the-gioi/",     _CAND, "https://cand.com.vn/the-gioi/p{page}/"),

    # ── Thế Giới Di Động (Ngách công nghệ - tin ngắn gọn, dễ train) ──────────
    ("https://www.thegioididong.com/tin-tuc/tin-moi", _TGDD, "https://www.thegioididong.com/tin-tuc/tin-moi?p={page}"),
]