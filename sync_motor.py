
import re
import time
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

BASE_URL = "https://shop.2motor.tw"
COLLECTION = "/collections/allmotor"
MAX_PAGES = 3  # 先測試前三頁


class MotorcycleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a":
            href = attrs.get("href", "")
            if "/products/" in href and self.current is None:
                full_url = urljoin(BASE_URL, href)
                parts = urlsplit(full_url)

                self.current = {
                    "url": urlunsplit((
                        parts.scheme,
                        parts.netloc,
                        parts.path,
                        "",
                        ""
                    )),
                    "name": "",
                    "image": ""
                }
                self.depth = 1
            elif self.current:
                self.depth += 1

        if tag == "img" and self.current:
            image = attrs.get("src") or attrs.get("data-src", "")
            if image and not self.current["image"]:
                self.current["image"] = urljoin(BASE_URL, image)

    def handle_data(self, data):
        if self.current:
            text = data.strip()
            if text:
                self.current["name"] += text + " "

    def handle_endtag(self, tag):
        if tag == "a" and self.current:
            self.depth -= 1
            if self.depth == 0:
                self.links.append(self.current)
                self.current = None


def fetch_page(page):
    url = f"{BASE_URL}{COLLECTION}?page={page}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "RenMotorSyncTest/1.0"}
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        html = response.read().decode("utf-8")

    parser = MotorcycleParser()
    parser.feed(html)

    unique = {}
    for item in parser.links:
        unique[item["url"]] = item

    return list(unique.values())


all_bikes = {}

for page in range(1, MAX_PAGES + 1):
    print(f"\n正在讀取第 {page} 頁...")

    items = fetch_page(page)
    print(f"第 {page} 頁找到 {len(items)} 筆商品連結")

    if not items:
        print("本頁沒有商品，停止測試。")
        break

    for item in items:
        all_bikes[item["url"]] = item

    if page < MAX_PAGES:
        time.sleep(2)

print("\n========================")
print("去除重複後商品總數：", len(all_bikes))
print("========================")

for number, item in enumerate(list(all_bikes.values())[:10], 1):
    name = re.sub(r"\s+", " ", item["name"]).strip()

    print(f"\n第 {number} 筆")
    print("名稱及價格文字：", name)
    print("商品網址：", item["url"])
    print("圖片網址：", item["image"])

print("\n測試完成：未修改 Supabase。")
