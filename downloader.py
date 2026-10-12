import os
import re
import io
import sys
import time
import uuid
import shutil
import asyncio
import logging
import platform
import urllib.parse
import urllib.request
import aiohttp
import yt_dlp

logger = logging.getLogger(__name__)

# ─── Paths & Directories ──────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
BIN_DIR = os.path.join(BASE_DIR, "bin")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(BIN_DIR, exist_ok=True)
os.environ["PATH"] = BIN_DIR + os.pathsep + DOWNLOAD_DIR + os.pathsep + os.environ.get("PATH", "")

COOKIES_FILE = os.path.join(BASE_DIR, "cookies.txt")

# ─── FFmpeg ───────────────────────────────────────────────
FFMPEG_PATH = None
try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        logger.info(f"FFmpeg detected via imageio_ffmpeg at: {FFMPEG_PATH}")
    else:
        FFMPEG_PATH = None
except Exception as e:
    logger.warning(f"imageio_ffmpeg check failed: {e}")

if not FFMPEG_PATH:
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        FFMPEG_PATH = sys_ffmpeg
        logger.info(f"FFmpeg detected in system PATH at: {FFMPEG_PATH}")
    else:
        logger.warning("FFmpeg executable not found! Single-format pre-merged fallback will be prioritized.")

# ─── JavaScript runtime (required by yt-dlp for YouTube) ──
DENO_PATH = shutil.which("deno")
if not DENO_PATH:
    try:
        import deno as _deno_pkg
        DENO_PATH = _deno_pkg.find_deno_bin()
    except Exception as e:
        logger.warning(f"Deno (pip package) not available: {e}")
if DENO_PATH and os.path.exists(DENO_PATH):
    logger.info(f"Deno JS runtime detected at: {DENO_PATH}")
else:
    DENO_PATH = None
    logger.warning("No Deno JS runtime found! YouTube downloads may fail.")


# ─── BotGuard PO Token Provider (rustypipe-botguard) ──────
def _ensure_rustypipe_botguard() -> str | None:
    """Auto-downloads the standalone rustypipe-botguard binary for YouTube PO token generation."""
    bin_name = "rustypipe-botguard.exe" if os.name == "nt" else "rustypipe-botguard"
    for folder in (BIN_DIR, DOWNLOAD_DIR):
        candidate = os.path.join(folder, bin_name)
        if os.path.exists(candidate) and os.path.getsize(candidate) > 1024:
            try:
                if os.name != "nt":
                    os.chmod(candidate, 0o755)
            except Exception:
                pass
            return candidate

    existing = shutil.which("rustypipe-botguard")
    if existing:
        return existing

    machine = platform.machine().lower()
    if os.name == "nt":
        url = "https://codeberg.org/ThetaDev/rustypipe-botguard/releases/download/v0.1.2/rustypipe-botguard-v0.1.2-x86_64-pc-windows-msvc.zip"
    elif "aarch64" in machine or "arm64" in machine:
        url = "https://codeberg.org/ThetaDev/rustypipe-botguard/releases/download/v0.1.2/rustypipe-botguard-v0.1.2-aarch64-unknown-linux-gnu.tar.xz"
    else:
        url = "https://codeberg.org/ThetaDev/rustypipe-botguard/releases/download/v0.1.2/rustypipe-botguard-v0.1.2-x86_64-unknown-linux-gnu.tar.xz"

    target_path = os.path.join(BIN_DIR, bin_name)
    try:
        logger.info(f"Downloading rustypipe-botguard PO token generator from {url}...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        if url.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                zf.extract(bin_name, BIN_DIR)
        else:
            import tarfile
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:xz") as tf:
                tf.extract(bin_name, BIN_DIR)
        if os.path.exists(target_path):
            if os.name != "nt":
                os.chmod(target_path, 0o755)
            logger.info(f"rustypipe-botguard installed at: {target_path}")
            return target_path
    except Exception as e:
        logger.warning(f"Could not auto-install rustypipe-botguard: {e}")
    return None


RUSTYPIPE_BG_PATH = _ensure_rustypipe_botguard()

# ─── Cookies from Environment Variables ───────────────────
_cookie_parts = [os.getenv(k, "").strip() for k in ("COOKIES", "YOUTUBE_COOKIES", "INSTAGRAM_COOKIES")]
_cookie_parts = [p for p in _cookie_parts if p]
if _cookie_parts:
    try:
        with open(COOKIES_FILE, "w", encoding="utf-8") as cf:
            cf.write("# Netscape HTTP Cookie File\n")
            for part in _cookie_parts:
                for line in part.replace("\\n", "\n").splitlines():
                    if line.strip() and not line.startswith("# Netscape"):
                        cf.write(line.rstrip() + "\n")
        logger.info("Created cookies.txt from environment variables.")
    except Exception as ce:
        logger.warning(f"Could not write cookies to cookies.txt: {ce}")

# ─── Last error per URL (to show the real reason to the user) ─
LAST_ERRORS: dict[str, str] = {}


def _set_error(url: str, err) -> None:
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(err)).replace("ERROR: ", "").strip()
    # Strip verbose yt-dlp bug report boilerplate so it doesn't clutter Telegram messages
    msg = msg.split("; please report this issue")[0].strip()
    LAST_ERRORS[clean_url(url)] = msg[:300]


def get_last_error(url: str) -> str:
    """Returns a short, user-friendly explanation of the last failure for url."""
    raw = LAST_ERRORS.get(clean_url(url), "")
    low = raw.lower()
    if not raw:
        return ""
    if "sign in to confirm" in low or "not a bot" in low:
        return "YouTube blocked the server IP (bot check). Add YouTube cookies (COOKIES env var)."
    if "login required" in low or "rate-limit" in low or ("login" in low and "instagram" in low):
        return "Instagram requires login from the server. Add Instagram cookies (COOKIES env var)."
    if "private" in low:
        return "This video is private."
    if "unavailable" in low:
        return "This video is unavailable or removed."
    if "unsupported url" in low:
        return "Unsupported URL."
    if "age" in low and ("restricted" in low or "confirm your age" in low):
        return "Age-restricted video: needs cookies of a logged-in account (COOKIES env var)."
    return raw[:200]


# ─── Shared Headers for Web requests (TikWM, SaveNow, etc.) ─
BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://www.google.com/',
}


# ─── yt-dlp base options ──────────────────────────────────
def _base_ydl_opts(extra: dict = None, use_cookies: bool = True) -> dict:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'retries': 5,
        'fragment_retries': 5,
        'socket_timeout': 30,
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'ignoreerrors': False,
        'default_search': 'auto',
        'nocheckcertificate': True,
        'concurrent_fragment_downloads': 4,
        'extractor_args': {
            'youtube': {
                'player_client': ['tv_samsung', 'mweb', 'web_embedded', 'visionos'],
                'fetch_pot': ['always'],
            }
        },
    }

    # JavaScript runtime for YouTube signature/n-challenge solving
    if DENO_PATH:
        opts['js_runtimes'] = {'deno': {'path': DENO_PATH}}

    # Cookies if available and requested
    if use_cookies and os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE

    # FFmpeg
    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        opts['ffmpeg_location'] = FFMPEG_PATH

    if extra:
        opts.update(extra)
    return opts


# ─── URL Cleaner & Share Link Resolver ───────────────────
def clean_url(url: str) -> str:
    url = url.strip().rstrip(").,]>\"'")
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        for key in ("redirect_url", "next", "u"):
            if key in query and query[key]:
                inner = urllib.parse.unquote(query[key][0]).strip().rstrip(").,]>\"'")
                if inner.startswith("http"):
                    url = inner
                    parsed = urllib.parse.urlparse(url)
                    break
        # Strip tracking query params from Instagram post/reel links
        if "instagram.com" in parsed.netloc.lower() and any(
            seg in parsed.path for seg in ("/reel/", "/reels/", "/p/", "/tv/")
        ):
            clean_path = parsed.path.replace("/reels/", "/reel/")
            url = urllib.parse.urlunparse((parsed.scheme or "https", parsed.netloc, clean_path, "", "", ""))
    except Exception:
        pass
    return url


async def resolve_url(url: str) -> str:
    """Unwraps mobile share links (facebook.com/share/..., fb.watch/..., instagram.com/share/...)."""
    url = clean_url(url)
    low = url.lower()
    needs_resolve = (
        "/share/" in low
        or "fb.watch" in low
        or "fb.gg" in low
        or "vt.tiktok.com" in low
        or "vm.tiktok.com" in low
    )
    if not needs_resolve:
        return url

    headers = dict(BROWSER_HEADERS)
    if "facebook.com" in low or "fb.watch" in low or "instagram.com" in low:
        headers["User-Agent"] = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"

    try:
        async with aiohttp.ClientSession() as session:
            cur = url
            for _ in range(6):
                async with session.get(
                    cur, headers=headers, allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=6)
                ) as resp:
                    loc = resp.headers.get("Location")
                    if not loc:
                        break
                    loc = urllib.parse.urljoin(cur, loc)
                    cleaned = clean_url(loc)
                    if cleaned != loc and ("/reel/" in cleaned or "/watch" in cleaned or "/videos/" in cleaned or "/p/" in cleaned):
                        return cleaned
                    if "/login" in loc.lower():
                        break
                    cur = cleaned
            return clean_url(cur)
    except Exception as e:
        logger.debug(f"resolve_url skipped for {url}: {e}")
    return url


# ─── TikTok via TikWM ─────────────────────────────────────
async def _tikwm_info(url: str) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            final_url = url
            try:
                async with session.get(url, headers=BROWSER_HEADERS, allow_redirects=True,
                                       timeout=aiohttp.ClientTimeout(total=5)) as r:
                    final_url = clean_url(str(r.url))
            except Exception:
                pass

            async with session.post("https://www.tikwm.com/api/",
                                    data={"url": final_url},
                                    headers=BROWSER_HEADERS,
                                    timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == 0 and "data" in data:
                        vd = data["data"]
                        is_photo = bool(vd.get("images"))
                        cover = vd.get("cover") or vd.get("origin_cover")
                        if is_photo and vd.get("images"):
                            cover = vd["images"][0]
                        return {
                            "title": vd.get("title", "TikTok Post")[:80],
                            "author": vd.get("author", {}).get("nickname", "TikTok User"),
                            "duration": vd.get("duration", 0),
                            "platform": "TikTok (صور 📸)" if is_photo else "TikTok",
                            "url": final_url,
                            "is_photo": is_photo,
                            "thumbnail": cover,
                            "_tikwm_data": vd,
                        }
    except Exception as e:
        logger.warning(f"TikWM info failed: {e}")
    return None


# ─── YouTube oEmbed Info Fallback ─────────────────────────
async def _youtube_oembed_info(url: str) -> dict | None:
    """Fast, unblocked metadata fallback for YouTube links via official oEmbed API."""
    if not any(d in url.lower() for d in ("youtube.com", "youtu.be")):
        return None
    try:
        oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(url, safe='')}&format=json"
        async with aiohttp.ClientSession(headers=BROWSER_HEADERS) as session:
            async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "title": (data.get("title") or "YouTube Video")[:80],
                        "author": data.get("author_name") or "YouTube",
                        "duration": 0,
                        "platform": "Youtube",
                        "url": url,
                        "is_photo": False,
                        "thumbnail": data.get("thumbnail_url"),
                    }
    except Exception as e:
        logger.debug(f"YouTube oEmbed fallback failed for {url}: {e}")
    return None


# ─── extract_info ─────────────────────────────────────────
async def extract_info(url: str) -> dict | None:
    url = await resolve_url(url)

    # TikTok fast path
    if "tiktok.com" in url.lower() or "douyin.com" in url.lower():
        res = await _tikwm_info(url)
        if res:
            return res

    ydl_opts = _base_ydl_opts({
        'skip_download': True,
        'socket_timeout': 15,
        'retries': 3,
    })

    def _get(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            thumb = info.get("thumbnail")
            if not thumb and info.get("thumbnails"):
                thumb = info["thumbnails"][-1].get("url")
            return {
                "title": info.get("title", "فيديو")[:80],
                "author": (info.get("uploader") or info.get("uploader_id")
                           or info.get("channel") or info.get("extractor", "")),
                "duration": info.get("duration", 0),
                "platform": info.get("extractor_key", "Video"),
                "url": url,
                "is_photo": False,
                "thumbnail": thumb,
            }

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, lambda: _get(ydl_opts))
    except Exception as e:
        logger.warning(f"Primary extract_info failed for {url}: {e}")
        _set_error(url, e)
        try:
            fallback_opts = _base_ydl_opts({
                'skip_download': True,
                'socket_timeout': 15,
                'retries': 3,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['tv_samsung', 'tv', 'web_embedded', 'mweb', 'tv_downgraded', 'visionos'],
                        'player_skip': ['webpage'],
                        'fetch_pot': ['always'],
                    }
                }
            }, use_cookies=False)
            return await loop.run_in_executor(None, lambda: _get(fallback_opts))
        except Exception as fe:
            logger.error(f"Fallback extract_info failed for {url}: {fe}")

    # YouTube oEmbed fallback for title & thumbnail
    yt_meta = await _youtube_oembed_info(url)
    if yt_meta:
        return yt_meta

    # Ultimate fallback guarantee: Always return valid metadata container so user receives download card!
    return {
        "title": "فيديو / Video",
        "author": "Online",
        "duration": 0,
        "platform": "Video Link",
        "url": url,
        "is_photo": False,
        "thumbnail": None
    }


# ─── Search Video by Query (Chat Direct Search) ──────────
async def search_video_by_query(query: str) -> dict | None:
    query = query.strip()
    if not query:
        return None

    ydl_opts = _base_ydl_opts({
        'skip_download': True,
        'default_search': 'ytsearch1',
        'extract_flat': 'in_playlist'
    })

    def _search():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if not info or "entries" not in info or len(info.get("entries", [])) == 0:
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)

            if info and "entries" in info and len(info["entries"]) > 0:
                entry = info["entries"][0]
                if not entry:
                    return None
                vid = entry.get("id") or entry.get("url")
                v_url = entry.get("webpage_url") or entry.get("url")
                if not v_url or not v_url.startswith("http"):
                    v_url = f"https://www.youtube.com/watch?v={vid}"

                thumb = entry.get("thumbnail")
                if not thumb and entry.get("thumbnails"):
                    thumb = entry["thumbnails"][-1].get("url")
                return {
                    "title": entry.get("title", query)[:80],
                    "author": (entry.get("uploader") or entry.get("channel") or "YouTube"),
                    "duration": entry.get("duration", 0),
                    "platform": "YouTube Search",
                    "url": v_url,
                    "thumbnail": thumb,
                }
            return None

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _search)
    except Exception as e:
        logger.error(f"search_video_by_query failed for {query}: {e}")
        return None


# ─── Search Videos Inline (Top 5 Results) ─────────────────
async def search_videos_inline(query: str, max_results: int = 5) -> list[dict]:
    query = query.strip()
    if not query:
        return []

    ydl_opts = _base_ydl_opts({
        'skip_download': True,
        'default_search': f'ytsearch{max_results}',
        'extract_flat': 'in_playlist'
    })

    def _search_multi():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            results = []
            if info and "entries" in info:
                for entry in info["entries"][:max_results]:
                    if not entry:
                        continue
                    vid = entry.get("id") or entry.get("url")
                    v_url = entry.get("webpage_url") or entry.get("url")
                    if not v_url or not v_url.startswith("http"):
                        v_url = f"https://www.youtube.com/watch?v={vid}"

                    thumb = entry.get("thumbnail")
                    if not thumb and entry.get("thumbnails"):
                        thumb = entry["thumbnails"][-1].get("url")

                    results.append({
                        "id": vid or str(uuid.uuid4())[:8],
                        "title": entry.get("title", "فيديو")[:80],
                        "author": (entry.get("uploader") or entry.get("channel") or "YouTube"),
                        "duration": entry.get("duration", 0),
                        "url": v_url,
                        "thumbnail": thumb,
                    })
            return results

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _search_multi)
    except Exception as e:
        logger.error(f"search_videos_inline failed for {query}: {e}")
        return []


# ─── Extract Playlist Info ─────────────────────────────────
async def extract_playlist_info(url: str, max_items: int = 10) -> dict | None:
    url = clean_url(url)
    ydl_opts = _base_ydl_opts({'skip_download': True, 'extract_flat': 'in_playlist'})

    def _playlist():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            entries = info.get("entries") or []
            valid_items = []
            for item in entries[:max_items]:
                if not item:
                    continue
                v_url = item.get("url") or item.get("webpage_url") or f"https://www.youtube.com/watch?v={item.get('id')}"
                valid_items.append({
                    "title": item.get("title", "فيديو")[:80],
                    "url": v_url,
                    "duration": item.get("duration", 0),
                })
            return {
                "title": info.get("title", "قائمة تشغيل")[:80],
                "item_count": len(valid_items),
                "items": valid_items,
                "url": url,
            }

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _playlist)
    except Exception as e:
        logger.error(f"extract_playlist_info failed for {url}: {e}")
        return None


# ─── TikTok Download ──────────────────────────────────────
async def download_tiktok_watermark_free(url: str) -> dict | None:
    url = clean_url(url)
    try:
        async with aiohttp.ClientSession() as session:
            final_url = url
            try:
                async with session.get(url, headers=BROWSER_HEADERS, allow_redirects=True,
                                       timeout=aiohttp.ClientTimeout(total=8)) as r:
                    final_url = clean_url(str(r.url))
            except Exception:
                pass

            async with session.post("https://www.tikwm.com/api/",
                                    data={"url": final_url, "hd": 1},
                                    headers=BROWSER_HEADERS,
                                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == 0 and "data" in data:
                        vi = data["data"]
                        video_url = vi.get("hdplay") or vi.get("play")
                        images = vi.get("images")
                        music_url = vi.get("music")
                        title = vi.get("title", "TikTok Post")
                        author = vi.get("author", {}).get("nickname", "")
                        fid = str(uuid.uuid4())[:8]

                        if video_url:
                            fp = os.path.join(DOWNLOAD_DIR, f"tiktok_{fid}.mp4")
                            async with session.get(video_url, headers=BROWSER_HEADERS,
                                                   timeout=aiohttp.ClientTimeout(total=60)) as vr:
                                if vr.status == 200:
                                    with open(fp, "wb") as f:
                                        async for chunk in vr.content.iter_chunked(1024 * 1024):
                                            f.write(chunk)
                                    return {"type": "video", "file_path": fp,
                                            "title": title, "author": author,
                                            "platform": "TikTok (بدون علامة مائية ✨)"}

                        elif images:
                            img_paths = []
                            for idx, img_url in enumerate(images[:10]):
                                ip = os.path.join(DOWNLOAD_DIR, f"tiktok_photo_{fid}_{idx}.jpg")
                                async with session.get(img_url, headers=BROWSER_HEADERS,
                                                       timeout=aiohttp.ClientTimeout(total=30)) as ir:
                                    if ir.status == 200:
                                        with open(ip, "wb") as f:
                                            f.write(await ir.read())
                                        img_paths.append(ip)

                            music_path = None
                            if music_url:
                                music_path = os.path.join(DOWNLOAD_DIR, f"tiktok_music_{fid}.mp3")
                                async with session.get(music_url, headers=BROWSER_HEADERS,
                                                       timeout=aiohttp.ClientTimeout(total=30)) as mr:
                                    if mr.status == 200:
                                        with open(music_path, "wb") as f:
                                            f.write(await mr.read())

                            if img_paths:
                                return {"type": "photos", "image_paths": img_paths,
                                        "music_path": music_path, "title": title,
                                        "author": author, "platform": "TikTok (صور 📸)"}
    except Exception as e:
        logger.warning(f"TikWM download failed: {e}")
    return None


# ─── External Cloud API Fallback (SaveNow / Loader.to v2) ─
SAVENOW_API_KEY = "dfcb6d76f2f6a9894gjkege8a4ab232222"
SAVENOW_DOMAINS = ("p.savenow.to", "p.lbserver.xyz")


async def _savenow_request_one(session: aiohttp.ClientSession, url: str, fmt: str, max_bytes: int = 0) -> dict | None:
    """Requests a single conversion/download from SaveNow/Loader.to API v2 and downloads the file."""
    data = None
    active_domain = SAVENOW_DOMAINS[0]
    for dom in SAVENOW_DOMAINS:
        try:
            api_url = f"https://{dom}/api/v2/download"
            params = {"format": fmt, "url": url, "apikey": SAVENOW_API_KEY}
            async with session.get(api_url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.json()
                    if data and data.get("id"):
                        active_domain = dom
                        break
        except Exception as e:
            logger.debug(f"SaveNow init failed on {dom}: {e}")

    if not data or not data.get("id"):
        return None

    dl_id = data["id"]
    prog_url = data.get("progress_url") or f"https://{active_domain}/api/progress?id={dl_id}"
    title = data.get("title") or (data.get("info") or {}).get("title") or "Video"

    dl_url = None
    for _ in range(45):
        await asyncio.sleep(1.5)
        try:
            async with session.get(
                prog_url,
                params={"_": str(int(time.time() * 1000))},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as pr:
                if pr.status == 200:
                    pdata = await pr.json()
                    if pdata.get("title") or (pdata.get("info") or {}).get("title"):
                        title = pdata.get("title") or (pdata.get("info") or {}).get("title")
                    if pdata.get("success") == 1:
                        dl_url = pdata.get("download_url")
                        break
                    if pdata.get("success") is False and pdata.get("text") == "Expired":
                        break
        except Exception:
            pass

    if not dl_url:
        return None

    ext = "mp3" if fmt in ("mp3", "m4a") else "mp4"
    fid = str(uuid.uuid4())[:8]
    dest = os.path.join(DOWNLOAD_DIR, f"cloud_{fid}.{ext}")
    try:
        async with session.get(dl_url, timeout=aiohttp.ClientTimeout(total=180)) as dr:
            if dr.status not in (200, 206):
                return None
            clen = int(dr.headers.get("Content-Length") or 0)
            if max_bytes and clen > max_bytes:
                return {"oversized": True, "title": title}
            written = 0
            with open(dest, "wb") as f:
                async for chunk in dr.content.iter_chunked(512 * 1024):
                    f.write(chunk)
                    written += len(chunk)
                    if max_bytes and written > max_bytes:
                        break
            if max_bytes and written > max_bytes:
                cleanup_file(dest)
                return {"oversized": True, "title": title}
        if os.path.exists(dest) and os.path.getsize(dest) > 1024:
            return {
                "file_path": dest,
                "title": title,
                "size_mb": os.path.getsize(dest) / (1024 * 1024),
            }
    except Exception as e:
        logger.warning(f"SaveNow stream download error: {e}")
        cleanup_file(dest)
    return None


async def _savenow_cloud_download(url: str, quality: str = "720", audio_only: bool = False) -> dict | None:
    """
    Cloud downloader fallback (SaveNow / Loader.to API v2).
    Bypasses datacenter IP blocks on Render by downloading on external cloud workers.
    Automatically steps down video resolution if a long video exceeds Telegram's 50MB limit.
    """
    headers = {
        "User-Agent": BROWSER_HEADERS["User-Agent"],
        "Referer": "https://en.loader.to/",
        "Origin": "https://en.loader.to",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        if audio_only:
            res = await _savenow_request_one(session, url, "mp3")
            if res and res.get("file_path"):
                return {
                    "type": "audio",
                    "file_path": res["file_path"],
                    "title": res.get("title", "صوت"),
                    "author": "",
                    "platform": "صوت MP3 🎵",
                }
            return None

        # Video: try requested quality first; if oversized (> 62MB), step down automatically
        chain_map = {
            "720": ["720", "360", "240", "144"],
            "480": ["480", "360", "240", "144"],
            "360": ["360", "240", "144"],
        }
        fmt_chain = chain_map.get(quality, ["720", "360", "240", "144"])
        for idx, fmt in enumerate(fmt_chain):
            # Cap intermediate qualities at 62MB (since 49.5–62MB can be audio-slimmed in 2s with -c:v copy)
            max_b = (62 * 1024 * 1024) if idx < len(fmt_chain) - 1 else 0
            res = await _savenow_request_one(session, url, fmt, max_bytes=max_b)
            if not res:
                continue
            if res.get("oversized"):
                logger.info(f"SaveNow format {fmt}p exceeded 62MB for {url}, stepping down...")
                continue
            fp = res.get("file_path")
            if fp and os.path.exists(fp):
                size_mb = res.get("size_mb", os.path.getsize(fp) / (1024 * 1024))
                if size_mb > 49.5:
                    comp_path = await compress_video_for_telegram(fp)
                    if comp_path and os.path.exists(comp_path):
                        if comp_path != fp:
                            cleanup_file(fp)
                        fp = comp_path
                        size_mb = os.path.getsize(fp) / (1024 * 1024)
                return {
                    "type": "video",
                    "file_path": fp,
                    "title": res.get("title", "فيديو"),
                    "author": "YouTube" if "youtu" in url.lower() else "",
                    "platform": "YouTube" if "youtu" in url.lower() else "Video",
                    "file_size_mb": size_mb,
                    "requested_quality": quality,
                }
    return None


# ─── Instagram Embed Fallback ─────────────────────────────
async def _instagram_embed_download(url: str) -> dict | None:
    """Fallback scraper for Instagram /p/ or /reel/ via the public /embed/captioned/ endpoint."""
    m = re.search(r"instagram\.com/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)", url)
    if not m:
        return None
    shortcode = m.group(1)
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(embed_url, headers=BROWSER_HEADERS,
                                   timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                raw_html = await resp.text()
            unescaped = raw_html.replace("\\/", "/").replace('\\"', '"').replace("\\u0026", "&")
            vid_match = re.search(r'"video_url"\s*:\s*"(https?://[^"]+)"', unescaped)
            if not vid_match:
                return None
            video_url = vid_match.group(1)
            fid = str(uuid.uuid4())[:8]
            fp = os.path.join(DOWNLOAD_DIR, f"insta_{fid}.mp4")
            async with session.get(video_url, headers=BROWSER_HEADERS,
                                   timeout=aiohttp.ClientTimeout(total=60)) as vr:
                if vr.status == 200:
                    with open(fp, "wb") as f:
                        async for chunk in vr.content.iter_chunked(1024 * 1024):
                            f.write(chunk)
                    size_mb = os.path.getsize(fp) / (1024 * 1024)
                    return {
                        "type": "video",
                        "file_path": fp,
                        "title": "Instagram Reel",
                        "author": "Instagram",
                        "platform": "Instagram",
                        "file_size_mb": size_mb,
                    }
    except Exception as e:
        logger.warning(f"Instagram embed fallback failed for {url}: {e}")
    return None


# ─── Audio Download ───────────────────────────────────────
async def download_audio(url: str) -> dict | None:
    url = await resolve_url(url)

    if "tiktok.com" in url.lower() or "douyin.com" in url.lower():
        res = await download_tiktok_watermark_free(url)
        if res and res.get("type") in ["audio", "photos"] and res.get("music_path"):
            return {"type": "audio", "file_path": res["music_path"],
                    "title": res.get("title", "صوت TikTok"),
                    "author": res.get("author", ""), "platform": "TikTok MP3 🎵"}

    fid = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_DIR, f"audio_{fid}.%(ext)s")

    extra = {
        'format': (
            'bestaudio[filesize<45M][ext=m4a]'
            '/bestaudio[filesize_approx<45M][ext=m4a]'
            '/bestaudio[filesize<45M]'
            '/bestaudio[ext=m4a]'
            '/bestaudio[protocol^=m3u8]'
            '/bestaudio/best'
        ),
        'outtmpl': output_template,
        'concurrent_fragment_downloads': 4,
    }
    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        extra['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }]

    ydl_opts = _base_ydl_opts(extra)

    def _extract(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(filename)
            actual = base + ".mp3" if os.path.exists(base + ".mp3") else filename
            return {
                "type": "audio",
                "file_path": actual,
                "title": info.get("title", "صوت"),
                "author": info.get("uploader") or info.get("uploader_id") or "",
                "platform": "صوت MP3 🎵",
            }

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, lambda: _extract(ydl_opts))
    except Exception as e:
        logger.warning(f"Primary audio download error on {url}: {e}")
        _set_error(url, e)
        try:
            fallback_opts = _base_ydl_opts({
                'format': 'bestaudio[filesize<45M]/bestaudio/best',
                'outtmpl': output_template,
                'concurrent_fragment_downloads': 4,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['tv_samsung', 'tv', 'web_embedded', 'mweb', 'tv_downgraded', 'visionos'],
                        'player_skip': ['webpage'],
                        'fetch_pot': ['always'],
                    }
                }
            }, use_cookies=False)
            if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
                fallback_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }]
            return await loop.run_in_executor(None, lambda: _extract(fallback_opts))
        except Exception as fe:
            logger.error(f"Fallback audio download error on {url}: {fe}")

    # Attempt 3: External Cloud API Fallback (SaveNow / Loader.to v2)
    cloud_res = await _savenow_cloud_download(url, audio_only=True)
    if cloud_res:
        return cloud_res

    return None


# ─── Video Download (with quality fallback chain) ─────────
async def download_video_quality(url: str, quality: str) -> dict | None:
    url = await resolve_url(url)

    # TikTok fast path
    if "tiktok.com" in url.lower() or "douyin.com" in url.lower():
        res = await download_tiktok_watermark_free(url)
        if res:
            return res

    fid = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_DIR, f"video_{fid}.%(ext)s")

    # سلسلة جودة ذكية — تفضل H.264 (vcodec^=avc) وتختار تلقائياً الجودة التي تناسب حد تليجرام (50MB) للفيديوهات الطويلة
    quality_formats = {
        "720": (
            'bestvideo[height<=720][filesize<38M][vcodec^=avc]+bestaudio[filesize<10M][ext=m4a]'
            '/bestvideo[height<=720][filesize_approx<38M][vcodec^=avc]+bestaudio[filesize_approx<10M][ext=m4a]'
            '/bestvideo[height<=480][filesize<38M][vcodec^=avc]+bestaudio[filesize<10M][ext=m4a]'
            '/bestvideo[height<=360][filesize<38M][vcodec^=avc]+bestaudio[filesize<10M][ext=m4a]'
            '/bestvideo[height<=240][filesize<38M][vcodec^=avc]+bestaudio[filesize<12M][ext=m4a]'
            '/best[height<=720][filesize<48M][ext=mp4]'
            '/best[height<=480][filesize<48M][ext=mp4]'
            '/best[height<=360][filesize<48M][ext=mp4]'
            '/bestvideo[height<=720][vcodec^=avc]+bestaudio[ext=m4a]'
            '/best[height<=720][ext=mp4]'
            '/bestvideo[height<=720][protocol^=m3u8]+bestaudio[protocol^=m3u8]'
            '/bestvideo[height<=720]+bestaudio'
            '/best[height<=720]/b[height<=720]/best/b'
        ),
        "480": (
            'bestvideo[height<=480][filesize<38M][vcodec^=avc]+bestaudio[filesize<10M][ext=m4a]'
            '/bestvideo[height<=480][filesize_approx<38M][vcodec^=avc]+bestaudio[filesize_approx<10M][ext=m4a]'
            '/bestvideo[height<=360][filesize<38M][vcodec^=avc]+bestaudio[filesize<10M][ext=m4a]'
            '/bestvideo[height<=240][filesize<38M][vcodec^=avc]+bestaudio[filesize<12M][ext=m4a]'
            '/best[height<=480][filesize<48M][ext=mp4]'
            '/best[height<=360][filesize<48M][ext=mp4]'
            '/bestvideo[height<=480][vcodec^=avc]+bestaudio[ext=m4a]'
            '/best[height<=480][ext=mp4]'
            '/bestvideo[height<=480][protocol^=m3u8]+bestaudio[protocol^=m3u8]'
            '/bestvideo[height<=480]+bestaudio'
            '/best[height<=480]/b[height<=480]/best/b'
        ),
        "360": (
            'best[height<=360][filesize<48M][ext=mp4]'
            '/bestvideo[height<=360][filesize<38M][vcodec^=avc]+bestaudio[filesize<10M][ext=m4a]'
            '/bestvideo[height<=240][filesize<38M][vcodec^=avc]+bestaudio[filesize<12M][ext=m4a]'
            '/best[height<=360][ext=mp4]'
            '/bestvideo[height<=360][vcodec^=avc]+bestaudio[ext=m4a]'
            '/bestvideo[height<=360][protocol^=m3u8]+bestaudio[protocol^=m3u8]'
            '/bestvideo[height<=360]+bestaudio'
            '/best[height<=360]/b[height<=360]/best/b'
        ),
    }
    fmt_spec = quality_formats.get(quality, quality_formats["720"])

    extra = {
        'format': fmt_spec,
        'outtmpl': output_template,
        'concurrent_fragment_downloads': 4,
        'merge_output_format': 'mp4',
    }
    ydl_opts = _base_ydl_opts(extra)

    def _extract(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(filename)
            actual = filename
            if not os.path.exists(filename):
                for ext in ['.mp4', '.mkv', '.webm', '.mov', '.flv', '.avi']:
                    if os.path.exists(base + ext):
                        actual = base + ext
                        break
            return {
                "type": "video",
                "file_path": actual,
                "title": info.get("title", "فيديو"),
                "author": (info.get("uploader") or info.get("uploader_id")
                           or info.get("channel") or ""),
                "platform": info.get("extractor_key", "Video"),
            }

    loop = asyncio.get_running_loop()

    # Attempt 1: Primary yt-dlp download with PO Token + Deno JS solver
    try:
        res = await loop.run_in_executor(None, lambda: _extract(ydl_opts))
        if res and res.get("file_path") and os.path.exists(res["file_path"]):
            size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
            if size_mb > 49.5:
                logger.info(f"File size {size_mb:.1f}MB > 49.5MB. Compressing for Telegram...")
                comp_path = await compress_video_for_telegram(res["file_path"])
                if comp_path and os.path.exists(comp_path):
                    if comp_path != res["file_path"]:
                        cleanup_file(res["file_path"])
                    res["file_path"] = comp_path
                    size_mb = os.path.getsize(comp_path) / (1024 * 1024)

            res["file_size_mb"] = size_mb
            res["requested_quality"] = quality
            return res
    except Exception as e:
        logger.warning(f"Primary video format download failed for {quality}p on {url}: {e}")
        _set_error(url, e)

    # Attempt 2: Webpage-skip & cookie-free multi-client fallback
    try:
        fallback_opts = _base_ydl_opts({
            'format': fmt_spec,
            'outtmpl': output_template,
            'concurrent_fragment_downloads': 4,
            'merge_output_format': 'mp4',
            'extractor_args': {
                'youtube': {
                    'player_client': ['tv_samsung', 'tv', 'web_embedded', 'mweb', 'tv_downgraded', 'visionos'],
                    'player_skip': ['webpage'],
                    'fetch_pot': ['always'],
                }
            }
        }, use_cookies=False)
        res = await loop.run_in_executor(None, lambda: _extract(fallback_opts))
        if res and res.get("file_path") and os.path.exists(res["file_path"]):
            size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
            if size_mb > 49.5:
                logger.info(f"Fallback file size {size_mb:.1f}MB > 49.5MB. Compressing for Telegram...")
                comp_path = await compress_video_for_telegram(res["file_path"])
                if comp_path and os.path.exists(comp_path):
                    if comp_path != res["file_path"]:
                        cleanup_file(res["file_path"])
                    res["file_path"] = comp_path
                    size_mb = os.path.getsize(comp_path) / (1024 * 1024)

            res["file_size_mb"] = size_mb
            res["requested_quality"] = quality
            return res
    except Exception as e:
        logger.error(f"Fallback video download error on {url}: {e}")

    # Attempt 3: Instagram embed fallback if applicable
    if "instagram.com" in url.lower():
        res = await _instagram_embed_download(url)
        if res:
            res["requested_quality"] = quality
            return res

    # Attempt 4: External Cloud API Fallback (SaveNow / Loader.to v2) — works even when server IP is blocked
    cloud_res = await _savenow_cloud_download(url, quality=quality, audio_only=False)
    if cloud_res:
        return cloud_res

    return None


# ─── Video Compressor ─────────────────────────────────────
async def compress_video_for_telegram(video_path: str, target_size_mb: float = 47.0) -> str | None:
    """Compresses a large video file using FFmpeg to fit under target_size_mb (Telegram 50MB limit)."""
    if not FFMPEG_PATH or not os.path.exists(FFMPEG_PATH):
        return None

    if not os.path.exists(video_path):
        return None

    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    if file_size_mb <= target_size_mb:
        return video_path

    # Fast Path: If file is between 47MB and 64MB (e.g., 20-min 360p video with 128k audio),
    # copy the video stream untouched (-c:v copy) and slim the audio to 48k mono AAC (~2 seconds!).
    if file_size_mb <= 64.0:
        fast_path = os.path.join(DOWNLOAD_DIR, f"fastcomp_{uuid.uuid4().hex[:8]}.mp4")
        fast_cmd = [
            FFMPEG_PATH, "-y",
            "-i", video_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "48k",
            "-ac", "1",
            "-movflags", "+faststart",
            fast_path,
        ]
        try:
            proc_f = await asyncio.create_subprocess_exec(
                *fast_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc_f.communicate()
            if os.path.exists(fast_path) and 0 < os.path.getsize(fast_path) <= 49.0 * 1024 * 1024:
                return fast_path
            cleanup_file(fast_path)
        except Exception as e:
            logger.debug(f"Fast audio-slim compression skipped: {e}")
            cleanup_file(fast_path)

    probe_cmd = [FFMPEG_PATH, "-i", video_path]
    try:
        proc = await asyncio.create_subprocess_exec(
            *probe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        err_out = stderr.decode('utf-8', errors='ignore')

        duration = None
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", err_out)
        if match:
            hours, mins, secs = float(match.group(1)), float(match.group(2)), float(match.group(3))
            duration = hours * 3600 + mins * 60 + secs

        if not duration or duration <= 0:
            duration = 300

        target_total_bits = target_size_mb * 8 * 1024 * 1024
        target_audio_bitrate_bps = 64 * 1024
        target_video_bitrate_bps = max(int((target_total_bits / duration) - target_audio_bitrate_bps), 80 * 1024)
        target_video_kbps = int(target_video_bitrate_bps / 1024)

        compressed_path = os.path.join(DOWNLOAD_DIR, f"compressed_{uuid.uuid4().hex[:8]}.mp4")

        cmd = [
            FFMPEG_PATH, "-y",
            "-i", video_path,
            "-c:v", "libx264",
            "-b:v", f"{target_video_kbps}k",
            "-maxrate", f"{int(target_video_kbps * 1.2)}k",
            "-bufsize", f"{int(target_video_kbps * 2)}k",
            "-preset", "ultrafast",
            "-vf", "scale='min(480,iw)':-2",
            "-c:a", "aac",
            "-b:a", "64k",
            "-ac", "1",
            "-movflags", "+faststart",
            compressed_path
        ]

        proc_c = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc_c.communicate()

        if os.path.exists(compressed_path) and os.path.getsize(compressed_path) > 0:
            return compressed_path
    except Exception as e:
        logger.error(f"Error compressing video with FFmpeg: {e}")

    return None


# ─── GIF Converter ────────────────────────────────────────
async def convert_video_to_gif(video_path: str) -> str | None:
    if not FFMPEG_PATH or not os.path.exists(FFMPEG_PATH):
        return None

    fid = str(uuid.uuid4())[:8]
    gif_path = os.path.join(DOWNLOAD_DIR, f"clip_{fid}.gif")

    cmd = [
        FFMPEG_PATH, "-y",
        "-ss", "00:00:00", "-t", "10",
        "-i", video_path,
        "-vf", "fps=10,scale=480:-1:flags=lanczos",
        gif_path
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        if os.path.exists(gif_path):
            return gif_path
    except Exception as e:
        logger.error(f"GIF conversion error: {e}")
    return None


# ─── Cleanup ──────────────────────────────────────────────
def cleanup_file(file_path: str):
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.error(f"Failed to remove {file_path}: {e}")
