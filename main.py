import os
import urllib.request
from fastapi import FastAPI, HTTPException, Depends, Query
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser

app = FastAPI()

class ImageVideoParser(HTMLParser):
    def __init__(self, url, output_folder):
        super().__init__()
        self.url = url
        self.output_folder = output_folder

    def handle_starttag(self, tag, attrs):
        if tag == 'img' or tag == 'video':
            for attr, value in attrs:
                if attr == 'src':
                    media_url = urljoin(self.url, value)
                    self.download_file(media_url)

    def download_file(self, url):
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        request = urllib.request.Request(url, headers=headers)

        try:
            response = urllib.request.urlopen(request)
            if response.getcode() == 200:
                file_name = os.path.join(self.output_folder, os.path.basename(urlparse(url).path))
                with open(file_name, 'wb') as file:
                    file.write(response.read())
                print(f"Downloaded: {file_name}")
            else:
                print(f"Failed to download {url}")
        except Exception as e:
            print(f"Failed to download {url}: {e}")

@app.get("/scrape")
async def scrape_images_and_videos(url: str = Query(..., title="Target URL"), output_folder: str = "output_folder"):
    try:
        response = urllib.request.urlopen(url)
        if response.getcode() == 200:
            content = response.read().decode('utf-8')
            parser = ImageVideoParser(url, output_folder)
            parser.feed(content)
            return {"message": "Scraping initiated. Check console for details."}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch content from {url}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch content from {url}: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
