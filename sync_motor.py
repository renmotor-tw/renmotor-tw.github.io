
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

URL = "https://shop.2motor.tw/collections/allmotor?page=1"


class MotorcycleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a":
            href = attrs.get("href", "")
            if "/products/" in href:
                self.current_link = {
                    "url": urljoin(URL, href),
                    "name": "",
                    "image": ""
                }

        if tag == "img" and self.current_link:
            image = attrs.get("src") or attrs.get("data-src", "")
            if image and not self.current_link["image"]:
                self.current_link["image"] = urljoin(URL, image)

    def handle_data(self, data):
        if self.current_link:
            text = data.strip()
            if text:
                self.current_link["name"] += text + " "

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link:
            self.links.append(self.current_link)
            self.current_link = None


request = urllib.request.Request(
    URL,
    headers={"User-Agent": "RenMotorSyncTest/1.0"}
)

with urllib.request.urlopen(request, timeout=20) as response:
    html = response.read().decode("utf-8")

parser = MotorcycleParser()
parser.feed(html)

unique = {}

for item in parser.links:
    unique[item["url"]] = item

print("找到商品連結數量：", len(unique))

for number, item in enumerate(list(unique.values())[:10], 1):
    print(f"\n第 {number} 筆")
    print("名稱：", item["name"].strip())
    print("網址：", item["url"])
    print("圖片：", item["image"])
