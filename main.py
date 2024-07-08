from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import aiohttp
import asyncio
import io
import zipfile
import logging
from pytube import YouTube
import hashlib

app = FastAPI()

logging.basicConfig(level=logging.INFO)

CONTENT_TYPE_EXTENSION_MAP = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/svg+xml": "svg",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/ogg": "ogg"
}


async def fetch_html(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                logging.error(f"Failed to fetch content from {url}. Status: {response.status}")
                raise HTTPException(status_code=500, detail=f"Failed to fetch content from {url}")
            return await response.text()


def parse_media(html: str, base_url: str) -> list:
    soup = BeautifulSoup(html, 'html.parser')
    media_urls = []

    #  images
    images = soup.find_all('img')
    for image in images:
        src = image.get('data-srcset') or image.get('data-src') or image.get('data-fallback-src') or image.get('src')
        if src:
            image_url = urljoin(base_url, src)
            media_urls.append((image_url, 'image'))

    # Videos
    videos = soup.find_all('video')
    for video in videos:
        src = video.get('data-src') or video.get('src')
        if src and not src.startswith('blob:'):
            video_url = urljoin(base_url, src)
            media_urls.append((video_url, 'video'))

        # Check for <source> tags inside <video>
        sources = video.find_all('source')
        for source in sources:
            src = source.get('data-src') or source.get('src')
            if src and not src.startswith('blob:'):
                source_url = urljoin(base_url, src)
                media_urls.append((source_url, 'video'))

    return media_urls


async def download_media(session: aiohttp.ClientSession, url: str, media_type: str, index: int) -> tuple:
    try:
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                content_type = response.headers.get('Content-Type', '').lower()
                extension = CONTENT_TYPE_EXTENSION_MAP.get(content_type, 'bin')

                return f"{media_type}_{index + 1}.{extension}", content
            else:
                logging.warning(f"Failed to download {url}. Status: {response.status}")
    except Exception as e:
        logging.error(f"Failed to download {url}: {e}")
    return None


async def download_all_media(media_urls: list) -> list:
    async with aiohttp.ClientSession() as session:
        tasks = [download_media(session, url, media_type, index) for index, (url, media_type) in enumerate(media_urls)]
        return await asyncio.gather(*tasks)


def download_youtube_video(url: str, index: int) -> tuple:
    try:
        yt = YouTube(url)
        stream = yt.streams.filter(progressive=True, file_extension='mp4').first()
        if stream:
            video_bytes = io.BytesIO()
            stream.stream_to_buffer(video_bytes)
            video_bytes.seek(0)
            return f"video_{index + 1}.mp4", video_bytes.read()
    except Exception as e:
        logging.error(f"Failed to download YouTube video {url}: {e}")
    return None


def generate_zip_filename(url: str) -> str:
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.replace('.', '_')
    unique_id = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{domain}_{unique_id}.zip"


@app.get("/scrape")
async def scrape_images_and_videos_api(url: str = Query(..., title="Target URL")):
    if 'youtube.com' in url:
        media_files = [download_youtube_video(url, 0)]
    else:
        html = await fetch_html(url)
        media_urls = parse_media(html, url)
        logging.info(f"Found {len(media_urls)} media files")

        media_files = await download_all_media(media_urls)
        media_files = [file for file in media_files if file]  # Filter out None values

    if not media_files:
        raise HTTPException(status_code=404, detail="No media files found")

    # Create a zip file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for filename, content in media_files:
            zip_file.writestr(filename, content)

    zip_buffer.seek(0)
    zip_filename = generate_zip_filename(url)

    return StreamingResponse(zip_buffer, media_type='application/zip',
                             headers={'Content-Disposition': f'attachment; filename="{zip_filename}"'})


@app.get("/health", status_code=200)
async def health_check():
    return JSONResponse(content={"status": "ok"})
