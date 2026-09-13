import os
import uuid
import asyncio
import logging
import urllib.parse
import aiohttp
import yt_dlp

logger = logging.getLogger(__name__)

# Find ffmpeg binary path from imageio_ffmpeg
FFMPEG_PATH = None
try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
    logger.info(f"FFmpeg binary detected at: {FFMPEG_PATH}")
except Exception as e:
    logger.warning(f"Could not load imageio_ffmpeg: {e}")

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def clean_url(url: str) -> str:
    """Unquote and clean URL if containing redirect_url or login parameters."""
    if "redirect_url=" in url:
        try:
            parsed = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed.query)
            if "redirect_url" in query and query["redirect_url"]:
                return urllib.parse.unquote(query["redirect_url"][0])
        except Exception:
            pass
    return url


async def extract_info(url: str) -> dict | None:
    """Extract metadata and thumbnail fast without downloading full video."""
    url = clean_url(url)
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
    }
    
    # Fast check for TikTok using TikWM
    if "tiktok.com" in url.lower() or "douyin.com" in url.lower():
        try:
            async with aiohttp.ClientSession() as session:
                final_url = url
                try:
                    async with session.get(url, headers=headers, allow_redirects=True, timeout=5) as head_resp:
                        final_url = clean_url(str(head_resp.url))
                except Exception:
                    pass
                
                payload = {"url": final_url}
                async with session.post("https://www.tikwm.com/api/", data=payload, headers=headers, timeout=6) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("code") == 0 and "data" in data:
                            vdata = data["data"]
                            is_photo = bool(vdata.get("images"))
                            cover = vdata.get("cover") or vdata.get("origin_cover")
                            if is_photo and vdata.get("images"):
                                cover = vdata["images"][0]
                            return {
                                "title": vdata.get("title", "TikTok Post")[:80],
                                "author": vdata.get("author", {}).get("nickname", "TikTok User"),
                                "duration": vdata.get("duration", 0),
                                "platform": "TikTok (صور 📸)" if is_photo else "TikTok",
                                "url": final_url,
                                "is_photo": is_photo,
                                "thumbnail": cover
                            }
        except Exception as e:
            logger.warning(f"TikWM info extract failed: {e}")

    # Fast yt-dlp info extract
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'user_agent': headers['User-Agent'],
    }
    
    def _get():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            thumb = info.get("thumbnail")
            if not thumb and info.get("thumbnails"):
                thumb = info["thumbnails"][-1].get("url")
            return {
                "title": info.get("title", "فيديو")[:80],
                "author": info.get("uploader", "") or info.get("uploader_id", "") or info.get("extractor", ""),
                "duration": info.get("duration", 0),
                "platform": info.get("extractor_key", "Video"),
                "url": url,
                "is_photo": False,
                "thumbnail": thumb
            }

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _get)
    except Exception as e:
        logger.error(f"Failed to extract info for {url}: {e}")
        return None


async def download_tiktok_watermark_free(url: str) -> dict | None:
    """Download TikTok video or photo post without watermark using TikWM API."""
    url = clean_url(url)
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            final_url = url
            try:
                async with session.get(url, headers=headers, allow_redirects=True, timeout=8) as head_resp:
                    final_url = clean_url(str(head_resp.url))
            except Exception:
                pass

            payload = {"url": final_url, "hd": 1}
            async with session.post("https://www.tikwm.com/api/", data=payload, headers=headers, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == 0 and "data" in data:
                        video_info = data["data"]
                        video_url = video_info.get("hdplay") or video_info.get("play")
                        images = video_info.get("images")
                        music_url = video_info.get("music")
                        title = video_info.get("title", "TikTok Post")
                        author = video_info.get("author", {}).get("nickname", "")
                        
                        # 1. Video Post
                        if video_url:
                            file_id = str(uuid.uuid4())
                            file_path = os.path.join(DOWNLOAD_DIR, f"tiktok_{file_id}.mp4")
                            async with session.get(video_url, headers=headers, timeout=60) as vid_resp:
                                if vid_resp.status == 200:
                                    with open(file_path, "wb") as f:
                                        while chunk := await vid_resp.content.read(1024 * 1024):
                                            f.write(chunk)
                                    return {
                                        "type": "video",
                                        "file_path": file_path,
                                        "title": title,
                                        "author": author,
                                        "platform": "TikTok (بدون علامة مائية ✨)"
                                    }
                        
                        # 2. Photo Post (Slideshow)
                        elif images:
                            image_paths = []
                            file_id = str(uuid.uuid4())[:8]
                            for idx, img_url in enumerate(images[:10]):
                                img_path = os.path.join(DOWNLOAD_DIR, f"tiktok_photo_{file_id}_{idx}.jpg")
                                async with session.get(img_url, headers=headers, timeout=30) as img_resp:
                                    if img_resp.status == 200:
                                        with open(img_path, "wb") as f:
                                            f.write(await img_resp.read())
                                        image_paths.append(img_path)
                            
                            music_path = None
                            if music_url:
                                music_path = os.path.join(DOWNLOAD_DIR, f"tiktok_music_{file_id}.mp3")
                                async with session.get(music_url, headers=headers, timeout=30) as mus_resp:
                                    if mus_resp.status == 200:
                                        with open(music_path, "wb") as f:
                                            f.write(await mus_resp.read())

                            if image_paths:
                                return {
                                    "type": "photos",
                                    "image_paths": image_paths,
                                    "music_path": music_path,
                                    "title": title,
                                    "author": author,
                                    "platform": "TikTok (صور 📸)"
                                }
                        
                        # 3. Audio only
                        elif music_url:
                            file_id = str(uuid.uuid4())
                            music_path = os.path.join(DOWNLOAD_DIR, f"tiktok_music_{file_id}.mp3")
                            async with session.get(music_url, headers=headers, timeout=30) as mus_resp:
                                if mus_resp.status == 200:
                                    with open(music_path, "wb") as f:
                                        f.write(await mus_resp.read())
                                    return {
                                        "type": "audio",
                                        "file_path": music_path,
                                        "title": title,
                                        "author": author,
                                        "platform": "TikTok (صوت 🎵)"
                                    }
    except Exception as e:
        logger.warning(f"TikWM API failed, using yt-dlp fallback: {e}")
    return None


async def download_audio(url: str) -> dict | None:
    """Download audio only as MP3."""
    url = clean_url(url)
    
    if "tiktok.com" in url.lower() or "douyin.com" in url.lower():
        res = await download_tiktok_watermark_free(url)
        if res and res.get("type") in ["audio", "photos"] and res.get("music_path"):
            return {
                "type": "audio",
                "file_path": res["music_path"],
                "title": res.get("title", "صوت TikTok"),
                "author": res.get("author", ""),
                "platform": "TikTok MP3 🎵"
            }

    file_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_DIR, f"audio_{file_id}.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'concurrent_fragment_downloads': 5,
        'user_agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
    }

    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        ydl_opts['ffmpeg_location'] = FFMPEG_PATH
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            base_name, _ = os.path.splitext(filename)
            actual_file = base_name + ".mp3"
            if not os.path.exists(actual_file):
                actual_file = filename
            
            title = info.get("title", "صوت")
            uploader = info.get("uploader", "") or info.get("uploader_id", "")
            return {
                "type": "audio",
                "file_path": actual_file,
                "title": title,
                "author": uploader,
                "platform": "صوت MP3 🎵"
            }

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _extract)
    except Exception as e:
        logger.error(f"Audio download error: {e}")
        return None


async def download_video_quality(url: str, quality: str) -> dict | None:
    """Download video with target quality (720p, 480p, or best)."""
    url = clean_url(url)
    
    if "tiktok.com" in url.lower() or "douyin.com" in url.lower():
        res = await download_tiktok_watermark_free(url)
        if res:
            return res

    file_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_DIR, f"video_{file_id}.%(ext)s")
    
    if quality == "720":
        fmt_spec = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best'
    elif quality == "480":
        fmt_spec = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/best'
    else:
        fmt_spec = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=720]/best'

    ydl_opts = {
        'format': fmt_spec,
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'concurrent_fragment_downloads': 5,
        'user_agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
    }

    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        ydl_opts['ffmpeg_location'] = FFMPEG_PATH

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            base_name, _ = os.path.splitext(filename)
            actual_file = filename
            if not os.path.exists(filename):
                for ext in ['.mp4', '.mkv', '.webm']:
                    if os.path.exists(base_name + ext):
                        actual_file = base_name + ext
                        break
            
            title = info.get("title", "فيديو")
            uploader = info.get("uploader", "") or info.get("uploader_id", "")
            extractor = info.get("extractor_key", "Video")
            return {
                "type": "video",
                "file_path": actual_file,
                "title": title,
                "author": uploader,
                "platform": extractor
            }

    try:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, _extract)
        if res and res.get("file_path") and os.path.exists(res["file_path"]):
            file_size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
            if file_size_mb <= 49.5:
                return res
            else:
                logger.info(f"Downloaded file was {file_size_mb:.1f} MB (>49.5MB). Retrying lower resolution...")
                cleanup_file(res["file_path"])
                if quality != "480":
                    return await download_video_quality(url, "480")
    except Exception as e:
        logger.error(f"Video download error ({quality}): {e}")
        
    return None


def cleanup_file(file_path: str):
    """Safely delete temporary download file."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.error(f"Failed to remove file {file_path}: {e}")
