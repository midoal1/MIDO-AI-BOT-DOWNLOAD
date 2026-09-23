import os
import uuid
import asyncio
import logging
import urllib.parse
import aiohttp
import yt_dlp

logger = logging.getLogger(__name__)

# ─── FFmpeg ───────────────────────────────────────────────
FFMPEG_PATH = None
try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
    logger.info(f"FFmpeg detected at: {FFMPEG_PATH}")
except Exception as e:
    logger.warning(f"imageio_ffmpeg not available: {e}")

# ─── Paths ────────────────────────────────────────────────
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")

# ─── Shared Headers ───────────────────────────────────────
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
def _base_ydl_opts(extra: dict = None) -> dict:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'user_agent': BROWSER_HEADERS['User-Agent'],
        'http_headers': BROWSER_HEADERS,
        # إعادة المحاولة
        'retries': 5,
        'fragment_retries': 5,
        'socket_timeout': 30,
        # تجاوز القيود الجغرافية
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        # تجاوز قيود العمر
        'age_limit': 99,
        # تجاهل الأخطاء غير الحرجة
        'ignoreerrors': False,
        # دعم المواقع الغير معروفة عن طريق Generic extractor
        'default_search': 'auto',
        # SSL
        'nocheckcertificate': True,
    }

    # Cookies لو موجودة
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
        logger.info("Using cookies.txt")

    # FFmpeg
    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        opts['ffmpeg_location'] = FFMPEG_PATH

    if extra:
        opts.update(extra)
    return opts


# ─── URL Cleaner ──────────────────────────────────────────
def clean_url(url: str) -> str:
    if "redirect_url=" in url:
        try:
            parsed = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed.query)
            if "redirect_url" in query and query["redirect_url"]:
                return urllib.parse.unquote(query["redirect_url"][0])
        except Exception:
            pass
    return url.strip()


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


# ─── extract_info ─────────────────────────────────────────
async def extract_info(url: str) -> dict | None:
    url = clean_url(url)

    # TikTok fast path
    if "tiktok.com" in url.lower() or "douyin.com" in url.lower():
        res = await _tikwm_info(url)
        if res:
            return res

    ydl_opts = _base_ydl_opts({'skip_download': True})

    def _get():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _get)
    except Exception as e:
        logger.error(f"extract_info failed for {url}: {e}")
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


# ─── Audio Download ───────────────────────────────────────
async def download_audio(url: str) -> dict | None:
    url = clean_url(url)

    if "tiktok.com" in url.lower() or "douyin.com" in url.lower():
        res = await download_tiktok_watermark_free(url)
        if res and res.get("type") in ["audio", "photos"] and res.get("music_path"):
            return {"type": "audio", "file_path": res["music_path"],
                    "title": res.get("title", "صوت TikTok"),
                    "author": res.get("author", ""), "platform": "TikTok MP3 🎵"}

    fid = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_DIR, f"audio_{fid}.%(ext)s")

    extra = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': output_template,
        'concurrent_fragment_downloads': 4,
    }
    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        extra['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    ydl_opts = _base_ydl_opts(extra)

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _extract)
    except Exception as e:
        logger.error(f"Audio download error: {e}")
    return None


# ─── Video Download (with quality fallback chain) ─────────
async def download_video_quality(url: str, quality: str) -> dict | None:
    url = clean_url(url)

    # TikTok fast path
    if "tiktok.com" in url.lower() or "douyin.com" in url.lower():
        res = await download_tiktok_watermark_free(url)
        if res:
            return res

    fid = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_DIR, f"video_{fid}.%(ext)s")

    # سلسلة جودة مرنة — تنزل أحسن جودة متاحة حسب الاختيار
    quality_formats = {
        "720": (
            'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]'
            '/bestvideo[height<=720]+bestaudio'
            '/best[height<=720]'
            '/best'
        ),
        "480": (
            'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]'
            '/bestvideo[height<=480]+bestaudio'
            '/best[height<=480]'
            '/best'
        ),
        "360": (
            'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]'
            '/bestvideo[height<=360]+bestaudio'
            '/best[height<=360]'
            '/best'
        ),
    }
    fmt_spec = quality_formats.get(quality, quality_formats["720"])

    extra = {
        'format': fmt_spec,
        'outtmpl': output_template,
        'concurrent_fragment_downloads': 4,
        # دمج الفيديو والصوت تلقائياً لو ffmpeg موجود
        'merge_output_format': 'mp4',
    }
    ydl_opts = _base_ydl_opts(extra)

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(filename)
            actual = filename
            if not os.path.exists(filename):
                for ext in ['.mp4', '.mkv', '.webm', '.mov']:
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

    try:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, _extract)

        if res and res.get("file_path") and os.path.exists(res["file_path"]):
            size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
            res["file_size_mb"] = size_mb
            res["requested_quality"] = quality
            return res

    except Exception as e:
        logger.error(f"Video download error ({quality}p): {e}")

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
