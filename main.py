import logging
import os
import io
import asyncio
import aiohttp
from fastapi import FastAPI, HTTPException, Query
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser
import zipfile
import uuid
from fastapi.responses import StreamingResponse
from PIL import Image

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)


class ImageVideoParser(HTMLParser):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.downloaded_files = []

    def handle_starttag(self, tag, attrs):
        if tag in ('img', 'video'):
            for attr_tuple in attrs:
                if len(attr_tuple) == 2:
                    attr, value = attr_tuple
                    # Consider multiple attributes that may contain the source URL
                    if attr in ('src', 'poster', 'data-src'):
                        media_url = urljoin(self.url, value)
                        self.add_downloaded_file(os.path.basename(urlparse(media_url).path), media_url)

    def add_downloaded_file(self, filename, url):
        self.downloaded_files.append((filename, url))


async def download_and_validate_media(session, filename, url):
    try:
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                if is_valid_media(content):
                    logging.debug(f"Downloaded and validated media: {filename}")
                    return filename, content
            else:
                logging.warning(f"Failed to download {url}. Status: {response.status}")
    except Exception as e:
        logging.error(f"Failed to download {url}: {e}")
    return None


async def scrape_images_and_videos(url):
    async with aiohttp.ClientSession() as session:
        logging.info(f"Fetching content from: {url}")
        response = await session.get(url)
        if response.status == 200:
            content = await response.text()
            parser = ImageVideoParser(url)
            parser.feed(content)

            tasks = [download_and_validate_media(session, f"{str(uuid.uuid4())}_{filename}", url) for filename, url in parser.downloaded_files]
            downloaded_media = await asyncio.gather(*tasks, return_exceptions=True)

            # Create a zip file in memory
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                for result in downloaded_media:
                    if isinstance(result, tuple):
                        filename, content = result
                        zip_file.writestr(filename, content)

            # Rewind the buffer to the beginning
            zip_buffer.seek(0)

            logging.info("Scraping and processing completed.")
            return StreamingResponse(zip_buffer, media_type='application/zip',
                                     headers={'Content-Disposition': 'attachment; filename=downloaded_files.zip'})
        else:
            logging.error(f"Failed to fetch content from {url}. Status: {response.status}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch content from {url}")




@app.get("/scrape")
async def scrape_images_and_videos_api(url: str = Query(..., title="Target URL")):
    return await scrape_images_and_videos(url)

