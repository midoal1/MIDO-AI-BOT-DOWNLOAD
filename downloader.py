import os
import sys
import uuid
import asyncio
import logging
import urllib.parse
import shutil
import aiohttp
import yt_dlp

logger = logging.getLogger(__name__)

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
        # تجاوز القيود الجغرافية وقيود العمر والمواقع البالغة
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'age_limit': 0,
        'allow_unplayable_formats': True,
        'ignoreerrors': True,
        # دعم المواقع الغير معروفة عن طريق Generic extractor
        'default_search': 'auto',
        # SSL
        'nocheckcertificate': True,
        'concurrent_fragment_downloads': 4,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'visionos'],
                'player_skip': ['webpage']
            }
        }
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
    url = url.strip().rstrip(").,]>\"'")
    if "redirect_url=" in url:
        try:
            parsed = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed.query)
            if "redirect_url" in query and query["redirect_url"]:
                return urllib.parse.unquote(query["redirect_url"][0]).strip().rstrip(").,]>\"'")
        except Exception:
            pass
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


# ─── extract_info ─────────────────────────────────────────
async def extract_info(url: str) -> dict | None:
    url = clean_url(url)

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
        try:
            fallback_opts = _base_ydl_opts({
                'skip_download': True,
                'socket_timeout': 15,
                'retries': 3,
                'extractor_args': {
                    'youtube': {
                        'player_skip': ['webpage']
                    }
                }
            })
            return await loop.run_in_executor(None, lambda: _get(fallback_opts))
        except Exception as fe:
            logger.error(f"Fallback extract_info failed for {url}: {fe}")

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
        try:
            fallback_opts = _base_ydl_opts({
                'format': 'best',
                'outtmpl': output_template,
                'concurrent_fragment_downloads': 4,
            })
            if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
                fallback_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            return await loop.run_in_executor(None, lambda: _extract(fallback_opts))
        except Exception as fe:
            logger.error(f"Fallback audio download error on {url}: {fe}")
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
            '/b[height<=720]'
            '/best'
            '/b'
        ),
        "480": (
            'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]'
            '/bestvideo[height<=480]+bestaudio'
            '/best[height<=480]'
            '/b[height<=480]'
            '/best'
            '/b'
        ),
        "360": (
            'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]'
            '/bestvideo[height<=360]+bestaudio'
            '/best[height<=360]'
            '/b[height<=360]'
            '/best'
            '/b'
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

    # Attempt 1: Requested quality format spec
    try:
        res = await loop.run_in_executor(None, lambda: _extract(ydl_opts))
        if res and res.get("file_path") and os.path.exists(res["file_path"]):
            size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
            if size_mb > 49.5:
                logger.info(f"File size {size_mb:.1f}MB > 49.5MB. Compressing for Telegram...")
                comp_path = await compress_video_for_telegram(res["file_path"])
                if comp_path and os.path.exists(comp_path):
                    cleanup_file(res["file_path"])
                    res["file_path"] = comp_path
                    size_mb = os.path.getsize(comp_path) / (1024 * 1024)

            res["file_size_mb"] = size_mb
            res["requested_quality"] = quality
            return res
    except Exception as e:
        logger.warning(f"Primary video format download failed for {quality}p on {url}: {e}")

    # Attempt 2: General fallback format spec ('b/best/bestvideo+bestaudio')
    try:
        fallback_opts = _base_ydl_opts({
            'format': 'b/best/bestvideo+bestaudio',
            'outtmpl': output_template,
            'concurrent_fragment_downloads': 4,
            'merge_output_format': 'mp4',
        })
        res = await loop.run_in_executor(None, lambda: _extract(fallback_opts))
        if res and res.get("file_path") and os.path.exists(res["file_path"]):
            size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
            if size_mb > 49.5:
                logger.info(f"Fallback file size {size_mb:.1f}MB > 49.5MB. Compressing for Telegram...")
                comp_path = await compress_video_for_telegram(res["file_path"])
                if comp_path and os.path.exists(comp_path):
                    cleanup_file(res["file_path"])
                    res["file_path"] = comp_path
                    size_mb = os.path.getsize(comp_path) / (1024 * 1024)

            res["file_size_mb"] = size_mb
            res["requested_quality"] = quality
            return res
    except Exception as e:
        logger.error(f"Fallback video download error on {url}: {e}")

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
        target_audio_bitrate_bps = 96 * 1024
        target_video_bitrate_bps = max(int((target_total_bits / duration) - target_audio_bitrate_bps), 100 * 1024)
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
            "-vf", "scale='min(720,iw)':-2",
            "-c:a", "aac",
            "-b:a", "96k",
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
