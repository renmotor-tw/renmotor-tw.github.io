"""RenMotor 公開商城同步：只讀取公開商品，不使用任何帳號或私有 API。"""
import json
import re
import sys
import time
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

BASE = "https://shop.2motor.tw"
COLLECTION = "/collections/allmotor"
MAX_PAGES = 100  # 直到遇到沒有新商品的頁面，設上限避免無限迴圈
OUTPUT = Path(__file__).with_name("vehicles.json")

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            href = attrs.get("href", "")
            if self.current is None and "/products/" in href:
                u = urlsplit(urljoin(BASE, href))
                if u.netloc != urlsplit(BASE).netloc:
                    return
                self.current = {"source_url": urlunsplit((u.scheme,u.netloc,u.path,"","")),"raw_text":"","image_url":""}
                self.depth = 1
            elif self.current is not None:
                self.depth += 1
        elif tag == "img" and self.current is not None and not self.current["image_url"]:
            image = attrs.get("src") or attrs.get("data-src") or ""
            if image and not image.startswith("data:"):
                self.current["image_url"] = urljoin(BASE, image)

    def handle_data(self, data):
        if self.current is not None and data.strip():
            self.current["raw_text"] += data.strip() + " "

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.depth -= 1
            if self.depth == 0:
                self.items.append(self.current)
                self.current = None

def parse(item):
    text = re.sub(r"\s+", " ", unescape(item["raw_text"])).strip()
    name = re.split(r"Regular price|Sale price", text, maxsplit=1, flags=re.I)[0].strip()
    store = re.search(r"【([^】]+)】", name)
    year = re.search(r"\b(?:19|20)\d{2}\b", name)
    stock = re.search(r"#\s*([A-Za-z0-9_-]+)", name)
    # 優先取售價；找不到再取原價。0 元不當作真實售價。
    sale = re.findall(r"Sale price\s*NT\$\s*([\d,]+(?:\.\d+)?)", text, flags=re.I)
    regular = re.findall(r"Regular price\s*NT\$\s*([\d,]+(?:\.\d+)?)", text, flags=re.I)
    price = None
    for candidate in (sale[-1:] + regular[:1]):
        try:
            p = int(float(candidate.replace(",", "")))
            if p > 0:
                price = p
                break
        except ValueError:
            pass
    model = re.sub(r"【[^】]+】|\b(?:19|20)\d{2}\b|#\s*[A-Za-z0-9_-]+", "", name).strip()
    brand = "其他"
    brands = {
        "YAMAHA": ["山葉", "YAMAHA", "勁戰", "FORCE", "AUGUR", "BWS", "MT-", "YZF"],
        "SYM": ["三陽", "SYM", "JET", "DRG", "MMBCU"],
        "KYMCO": ["光陽", "KYMCO", "LIKE", "RACING", "KRV"],
        "HONDA": ["本田", "HONDA", "CBR", "CB650"],
        "SUZUKI": ["鈴木", "SUZUKI", "GSX"],
        "KAWASAKI": ["川崎", "KAWASAKI", "NINJA", "Z900"],
        "PGO": ["PGO", "彪虎"],
        "VESPA": ["VESPA", "偉士牌"],
    }
    upper = model.upper()
    for label, terms in brands.items():
        if any(term.upper() in upper for term in terms):
            brand = label
            break
    return {
        "store": store.group(1).strip() if store else "門市待確認",
        "brand": brand,
        "year": int(year.group()) if year else None,
        "model": model,
        "stock_number": stock.group(1) if stock else "",
        "price": price,
        "image_url": item["image_url"],
        "source_url": item["source_url"],
        "original_name": name,
        "cc": None,
        "km": None,
        "warranty": None
    }

def fetch(page):
    url = f"{BASE}{COLLECTION}?page={page}"
    req = Request(url, headers={"User-Agent":"Mozilla/5.0 (compatible; RenMotorPublicCatalogSync/1.0)"})
    with urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", "replace")
    parser = Parser()
    parser.feed(html)
    return {item["source_url"]: item for item in parser.items}

def main():
    all_items = {}
    for page in range(1, MAX_PAGES+1):
        print(f"讀取公開商城第 {page} 頁", flush=True)
        try:
            found = fetch(page)
        except Exception as exc:
            # 中途出錯不更新，避免把完整資料誤覆蓋成部分資料
            raise RuntimeError(f"第 {page} 頁讀取失敗，保留舊資料: {exc}") from exc
        fresh = {url:item for url,item in found.items() if url not in all_items}
        print(f"本頁 {len(found)} 筆，新增 {len(fresh)} 筆", flush=True)
        if not fresh:
            break
        all_items.update(fresh)
        if page < MAX_PAGES:
            time.sleep(1.5)
    else:
        raise RuntimeError("已達頁數安全上限，無法確認全部資料，保留舊檔")
    if len(all_items) < 10:
        raise RuntimeError("商品數量異常偏少，保留舊檔")
    vehicles = [parse(item) for item in all_items.values()]
    invalid = [v for v in vehicles if not v["original_name"] or not v["source_url"]]
    if invalid:
        raise RuntimeError(f"有 {len(invalid)} 筆資料缺少車名或網址，保留舊檔")
    stores = sorted({v["store"] for v in vehicles})
    print(f"同步完成：{len(vehicles)} 筆；門市：{len(stores)} 個", flush=True)
    for store in stores:
        print(f"{store}: {sum(v['store']==store for v in vehicles)}", flush=True)
    # 首次資料須人工驗證後再上線；這裡產生 JSON，不碰 Supabase
    OUTPUT.write_text(json.dumps(vehicles, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"同步失敗：{exc}", file=sys.stderr)
        sys.exit(1)
