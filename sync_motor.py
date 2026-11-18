
import json
import re
import time
import urllib.request
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

BASE_URL = "https://shop.2motor.tw"
COLLECTION = "/collections/allmotor"
MAX_PAGES = 3  # 測試成功後再擴充全部頁面


class MotorcycleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self.current = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a":
            href = attrs.get("href", "")

            if "/products/" in href and self.current is None:
                url = urljoin(BASE_URL, href)
                parts = urlsplit(url)

                if parts.netloc != urlsplit(BASE_URL).netloc:
                    return

                self.current = {
                    "source_url": urlunsplit((
                        parts.scheme, parts.netloc,
                        parts.path, "", ""
                    )),
                    "raw_text": "",
                    "image_url": ""
                }
                self.depth = 1

            elif self.current is not None:
                self.depth += 1

        if tag == "img" and self.current is not None:
            image = (
                attrs.get("src")
                or attrs.get("data-src")
                or ""
            )

            if image and not self.current["image_url"]:
                self.current["image_url"] = urljoin(
                    BASE_URL, image
                )

    def handle_data(self, data):
        if self.current is not None:
            value = data.strip()
            if value:
                self.current["raw_text"] += value + " "

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.depth -= 1

            if self.depth == 0:
                self.items.append(self.current)
                self.current = None


def clean_text(value):
    return re.sub(
        r"\s+", " ", unescape(value)
    ).strip()


def parse_motorcycle(item):
    text = clean_text(item["raw_text"])

    # 將價格區塊與車輛名稱分開
    name = re.split(
        r"Regular price|Sale price",
        text,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0].strip()

    # 擷取門市名稱
    store_match = re.search(r"【([^】]+)】", name)
    store = (
        store_match.group(1).strip()
        if store_match else "未分類門市"
    )

    # 擷取年份
    year_match = re.search(
        r"\b(?:19|20)\d{2}\b", name
    )
    year = (
        int(year_match.group())
        if year_match else None
    )

    # 擷取車輛編號
    number_match = re.search(
        r"#\s*([A-Za-z0-9_-]+)", name
    )
    stock_number = (
        number_match.group(1)
        if number_match else ""
    )

    # 取最後一個 Sale price 作為候選售價
    sale_matches = re.findall(
        r"Sale price\s*NT\$\s*([\d,]+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE
    )

    regular_matches = re.findall(
        r"Regular price\s*NT\$\s*([\d,]+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE
    )

    price_text = (
        sale_matches[-1]
        if sale_matches else
        regular_matches[0]
        if regular_matches else None
    )

    price = (
        int(float(price_text.replace(",", "")))
        if price_text else None
    )

    # 去除門市、年份、編號，留下車型
    model = re.sub(r"【[^】]+】", "", name)
    model = re.sub(r"\b(?:19|20)\d{2}\b", "", model)
    model = re.sub(
        r"#\s*[A-Za-z0-9_-]+", "", model
    )
    model = clean_text(model)

    return {
        "store": store,
        "year": year,
        "model": model,
        "stock_number": stock_number,
        "price": price,
        "image_url": item["image_url"],
        "source_url": item["source_url"],
        "original_name": name
    }


def fetch_page(page):
    url = f"{BASE_URL}{COLLECTION}?page={page}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "RenMotorSyncTest/1.0"
        }
    )

    with urllib.request.urlopen(
        request, timeout=25
    ) as response:
        html = response.read().decode(
            "utf-8", errors="replace"
        )

    parser = MotorcycleParser()
    parser.feed(html)

    unique = {}
    for item in parser.items:
        unique[item["source_url"]] = item

    return list(unique.values())


all_items = {}

for page in range(1, MAX_PAGES + 1):
    print(f"正在讀取第 {page} 頁...")

    items = fetch_page(page)
    print(f"本頁找到 {len(items)} 筆商品連結")

    if not items:
        break

    for item in items:
        all_items[item["source_url"]] = item

    if page < MAX_PAGES:
        time.sleep(2)


vehicles = [
    parse_motorcycle(item)
    for item in all_items.values()
]

stores = sorted({
    bike["store"]
    for bike in vehicles
})

print("\n========== 測試結果 ==========")
print("商品總數：", len(vehicles))
print("辨識到的門市：", len(stores))

print("\n門市清單：")
for store in stores:
    count = sum(
        bike["store"] == store
        for bike in vehicles
    )
    print(f"- {store}：{count} 台")

print("\n前 10 台車輛：")
for bike in vehicles[:10]:
    print(json.dumps(
        bike, ensure_ascii=False
    ))

# 僅輸出測試檔，不寫入 Supabase
with open(
    "vehicles_preview.json",
    "w",
    encoding="utf-8"
) as file:
    json.dump(
        vehicles,
        file,
        ensure_ascii=False,
        indent=2
    )

print("\n測試完成！")
print("已產生 vehicles_preview.json")
print("尚未修改 Supabase。")
