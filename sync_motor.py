"""RenMotor 公開商城同步：只讀取公開商品，不使用任何帳號或私有 API。"""
import gzip
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

BASE = "https://shop.2motor.tw"
COLLECTION = "/collections/allmotor"
CATEGORY_COLLECTIONS = {
    "electric": "/collections/allemotor",
    "green-50": "/collections/all50motor",
    "up-to-125": "/collections/all125motor",
    "126-150": "/collections/all150motor",
    "151-249": "/collections/all151motor",
    "heavy": "/collections/all-heavymotor",
    "white-manual": "/collections/allbike",
    "vespa": "/collections/allvespa",
}
MAX_PAGES = 100  # 直到遇到沒有新商品的頁面，設上限避免無限迴圈
OUTPUT = Path(__file__).with_name("vehicles.json")

BRANDS = {
    "YAMAHA": ("山葉", "YAMAHA"),
    "SYM": ("三陽", "SYM"),
    "KYMCO": ("光陽", "KYMCO"),
    "HONDA": ("本田", "HONDA"),
    "SUZUKI": ("台鈴", "鈴木", "SUZUKI"),
    "KAWASAKI": ("川崎", "KAWASAKI"),
    "GOGORO": ("睿能", "GOGORO"),
    "AEON": ("宏佳騰", "AEON"),
    "BMW": ("BMW", "寶馬"),
    "HARTFORD": ("哈特佛", "HARTFORD"),
    "PGO": ("PGO", "摩特動力"),
    "VESPA": ("VESPA", "偉士牌"),
}
BRAND_MODELS = {
    "YAMAHA": ("勁戰", "FORCE", "AUGUR", "BWS", "MT-", "YZF"),
    "SYM": ("JET", "DRG", "MMBCU"),
    "KYMCO": ("LIKE", "RACING", "KRV", "MANY"),
    "HONDA": ("CBR", "CB650"),
    "SUZUKI": ("GSX",),
    "KAWASAKI": ("NINJA", "Z900"),
}
# Model names may omit the displacement or use a shorter model code.
MODEL_CC = {
    "YAMAHA": (
        (r"MT[- ]?0?3|YZF[- ]?R3", 321),
        (r"MT[- ]?15|\bR15|FORCE|AUGUR", 155),
        (r"勁戰|BWS|VINOORA", 125),
        (r"RS\s*NEO", 115),
    ),
    "SYM": (
        (r"DRG|MMBCU|JET\s*SL\s*(?:\+|PLUS|SUPER\s*C)", 158),
        (r"CLBCU|迪爵|JET\s*(?:SL|SR|S)\b", 125),
    ),
    "KYMCO": ((r"KRV", 180), (r"\bGP\b", 125)),
    "SUZUKI": ((r"SALUTO", 125),),
}
CC_VALUE = r"(?<![\d.])([1-9]\d{1,3})(?:\.\d+)?\s*(?:c\.?c\.?|cubic\s+centimeters?|cm[³3]|㏄)"
NO_WARRANTY = re.compile(r"(?:不(?:另行|予|再)?(?:提供|含|附|享有)|未提供|沒有|無)\s*(?:任何)?\s*(?:原廠)?\s*保固")
WITH_WARRANTY = re.compile(r"保固車款?|保固項目|(?:提供|享有|附有)\s*(?:.{0,16})保固")


def vehicle_brand(model, fallback="其他"):
    upper = model.upper()
    for groups in (BRANDS, BRAND_MODELS):
        for label, terms in groups.items():
            if any(term in upper for term in terms):
                return label
    return fallback


def engine_cc(model, brand, description=""):
    if brand == "GOGORO" or re.search(r"\b(?:EC-?0[25]|EMOVING|IONEX|UR1|AI-?[134])\b|電動車", model, re.I):
        return None
    explicit = re.search(r"排氣量\s*[:：]?\s*" + CC_VALUE, description, re.I)
    explicit = explicit or re.search(CC_VALUE, model, re.I)
    if explicit:
        return int(explicit.group(1))
    for match in re.finditer(r"(?<![\d.])(50|[1-9]\d{2,3})(?![\d.]|\s*代)", model):
        cc = int(match.group(1))
        if cc <= 1800:
            return cc
    for pattern, cc in MODEL_CC.get(brand, ()):
        if re.search(pattern, model, re.I):
            return cc
    return None


def update_vehicle_details(vehicle, description):
    model = vehicle["model"]
    brand = vehicle_brand(model, vehicle["brand"])
    text = f'{vehicle["original_name"]} {description}'
    as_is = "現況" in text
    warranty = None
    if as_is or NO_WARRANTY.search(text):
        warranty = False
    elif WITH_WARRANTY.search(text):
        warranty = True
    vehicle.update(
        brand=brand,
        cc=engine_cc(model, brand, description),
        as_is=as_is,
        warranty=warranty,
    )


class ProductDescription(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts = []
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("property"):
            self.meta[attrs["property"]] = attrs.get("content", "")
        if tag == "div":
            if self.depth or "product-description" in attrs.get("class", "").split():
                self.depth += 1
        if self.depth and tag in {"p", "div", "br", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag == "div" and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)

    def description(self):
        text = "".join(self.parts).strip()
        if not text and self.meta.get("og:type") == "product":
            text = self.meta.get("og:description", "")
        return re.sub(r"\s+", " ", text).strip()


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
    return {
        "store": store.group(1).strip() if store else "門市待確認",
        "brand": vehicle_brand(model),
        "year": int(year.group()) if year else None,
        "model": model,
        "stock_number": stock.group(1) if stock else "",
        "price": price,
        "image_url": item["image_url"],
        "source_url": item["source_url"],
        "original_name": name,
        "cc": None,
        "km": None,
        "warranty": None,
        "as_is": False,
    }


def fetch_description(source_url):
    # The product URL is sufficient. There is no need to download its photos.
    path = urlsplit(source_url).path
    product_path = path[path.index("/products/"):]
    url = BASE + quote(product_path, safe="/%")
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; RenMotorPublicCatalogSync/1.0)",
        "Accept-Encoding": "gzip",
    })
    with urlopen(req, timeout=12) as resp:
        body = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    parser = ProductDescription()
    parser.feed(body.decode("utf-8", "replace"))
    return parser.description()


def update_catalog_details(vehicles, previous):
    def update(vehicle):
        try:
            description = fetch_description(vehicle["source_url"])
        except HTTPError as exc:
            if exc.code not in (404, 410):
                return exc
            description = ""
        except (OSError, ValueError) as exc:
            return exc
        update_vehicle_details(vehicle, description)
        return None

    failures = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for vehicle, error in zip(vehicles, pool.map(update, vehicles)):
            if error is None:
                continue
            failures.append(error)
            update_vehicle_details(vehicle, "")
            old = previous.get(vehicle["source_url"], {})
            for field in ("cc", "warranty", "as_is"):
                if old.get(field) is not None:
                    vehicle[field] = old[field]
    if len(failures) > len(vehicles) // 2:
        raise RuntimeError(f"多數商品頁讀取失敗，保留舊檔：{failures[0]}")
    if failures:
        print(f"{len(failures)} 筆商品頁讀取失敗，沿用可取得的前次分類：{failures[0]}", flush=True)


def fetch(page, collection=COLLECTION):
    url = f"{BASE}{collection}?page={page}"
    req = Request(url, headers={"User-Agent":"Mozilla/5.0 (compatible; RenMotorPublicCatalogSync/1.0)"})
    with urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", "replace")
    parser = Parser()
    parser.feed(html)
    return {item["source_url"]: item for item in parser.items}

def fetch_collection(collection, delay):
    items = {}
    for page in range(1, MAX_PAGES + 1):
        try:
            found = fetch(page, collection)
        except Exception as exc:
            # 中途出錯不更新，避免把完整資料誤覆蓋成部分資料
            raise RuntimeError(f"{collection} 第 {page} 頁讀取失敗，保留舊資料: {exc}") from exc
        fresh = {url: item for url, item in found.items() if url not in items}
        if not fresh:
            print(f"{collection}：取得 {len(items)} 筆商品", flush=True)
            return items
        items.update(fresh)
        if page < MAX_PAGES:
            time.sleep(delay)
    raise RuntimeError(f"{collection} 已達頁數安全上限，無法確認全部資料，保留舊檔")


def product_handle(url):
    # Category links and inventory links use different collection prefixes.
    return unquote(urlsplit(url).path).split("/products/", 1)[-1].rstrip("/")


def update_vehicle_categories(vehicles):
    product_groups = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = {
            category: pool.submit(fetch_collection, collection, 0.75)
            for category, collection in CATEGORY_COLLECTIONS.items()
        }
        for category, result in pending.items():
            handles = {product_handle(url) for url in result.result()}
            for handle in handles:
                product_groups.setdefault(handle, []).append(category)
    for vehicle in vehicles:
        vehicle["categories"] = product_groups.get(product_handle(vehicle["source_url"]), [])


def main():
    all_items = fetch_collection(COLLECTION, 1.5)
    if len(all_items) < 10:
        raise RuntimeError("商品數量異常偏少，保留舊檔")
    vehicles = [parse(item) for item in all_items.values()]
    invalid = [v for v in vehicles if not v["original_name"] or not v["source_url"]]
    if invalid:
        raise RuntimeError(f"有 {len(invalid)} 筆資料缺少車名或網址，保留舊檔")
    update_vehicle_categories(vehicles)
    previous = {v["source_url"]: v for v in json.loads(OUTPUT.read_text(encoding="utf-8"))} if OUTPUT.exists() else {}
    print(f"讀取 {len(vehicles)} 筆商品描述", flush=True)
    update_catalog_details(vehicles, previous)
    stores = sorted({v["store"] for v in vehicles})
    print(f"同步完成：{len(vehicles)} 筆；門市：{len(stores)} 個", flush=True)
    for store in stores:
        print(f"{store}: {sum(v['store']==store for v in vehicles)}", flush=True)
    # 首次資料須人工驗證後再上線；這裡產生 JSON，不碰 Supabase
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(vehicles, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    temporary.replace(OUTPUT)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"同步失敗：{exc}", file=sys.stderr)
        sys.exit(1)
