"""
子エージェント②：LIFULL HOME'S 横浜中古マンション収集
条件：3LDK / 6000万以内 / 駅徒歩5分以内 / 横浜市
"""

import requests
from bs4 import BeautifulSoup
import time
import json
import re
from datetime import date

SEARCH_CONFIG = {
    "source": "HOMES",
    "area": "横浜市",
    "madori": "3LDK",
    "price_max": 6000,
    "walk_max": 5,
}

# LIFULL HOME'S 中古マンション 横浜市検索URL
BASE_URL = "https://www.homes.co.jp/mansion/b-yokohama-city/price-6000/"
# クエリパラメータで絞り込む
PARAMS = {
    "room_plan": "07",     # 3LDK
    "walk": "5",           # 駅徒歩5分
    "page": 1,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}

def fetch_page(page_num: int) -> "BeautifulSoup | None":
    params = {**PARAMS, "page": page_num}
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        time.sleep(2)
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"[HOMES] ページ{page_num}取得失敗: {e}")
        return None

def parse_properties(soup: BeautifulSoup) -> list[dict]:
    properties = []
    items = soup.select("article.mod-mergeBuilding--sale")

    for item in items:
        try:
            # 物件名
            name_el = item.select_one("p.heading")
            name = name_el.get_text(strip=True) if name_el else ""

            # 価格
            price_el = item.select_one("span.price")
            price_text = price_el.get_text(strip=True) if price_el else "0"
            price = int(re.sub(r"[^\d]", "", price_text.split("万")[0]) or 0)

            # 所在地
            addr_el = item.select_one("p.location")
            address = addr_el.get_text(strip=True) if addr_el else ""

            # 交通
            transport_el = item.select_one("p.traffic")
            transport = transport_el.get_text(strip=True) if transport_el else ""
            walk_match = re.search(r"徒歩(\d+)分", transport)
            walk_min = int(walk_match.group(1)) if walk_match else 99

            # 専有面積
            area_el = item.select_one("span.detail-mansion-area")
            area_m2 = 0.0
            if area_el:
                m = re.search(r"([\d.]+)", area_el.get_text())
                if m:
                    area_m2 = float(m.group(1))

            # 築年
            build_el = item.select_one("span.detail-mansion-age")
            build_year = ""
            if build_el:
                m = re.search(r"(\d{4})年", build_el.get_text())
                if m:
                    build_year = m.group(1)

            # ㎡単価
            price_per_m2 = round(price / area_m2, 1) if area_m2 > 0 else 0

            # URL
            link_el = item.select_one("a[href*='/mansion/']")
            detail_url = "https://www.homes.co.jp" + link_el["href"] if link_el else ""

            if price > 0 and walk_min <= 5:
                properties.append({
                    "source": "HOMES",
                    "date": str(date.today()),
                    "name": name,
                    "price_man": price,
                    "address": address,
                    "transport": transport,
                    "walk_min": walk_min,
                    "area_m2": area_m2,
                    "price_per_m2": price_per_m2,
                    "build_year": build_year,
                    "url": detail_url,
                })
        except Exception as e:
            print(f"[HOMES] パースエラー: {e}")
            continue

    return properties

def get_total_pages(soup: BeautifulSoup) -> int:
    pager = soup.select_one("ul.pagination")
    if not pager:
        return 1
    nums = [int(a.get_text()) for a in pager.select("a") if a.get_text().isdigit()]
    return max(nums) if nums else 1

def run() -> list[dict]:
    print("[HOMES] 収集開始...")
    all_props = []

    first_soup = fetch_page(1)
    if not first_soup:
        return []

    total = min(get_total_pages(first_soup), 10)
    print(f"[HOMES] 総ページ数: {total}")
    all_props.extend(parse_properties(first_soup))

    for page in range(2, total + 1):
        soup = fetch_page(page)
        if soup:
            props = parse_properties(soup)
            all_props.extend(props)
            print(f"[HOMES] {page}/{total}ページ完了 (+{len(props)}件)")

    print(f"[HOMES] 収集完了: 合計 {len(all_props)} 件")
    return all_props

if __name__ == "__main__":
    results = run()
    output_path = "data/homes_latest.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[HOMES] → {output_path} に保存完了")
