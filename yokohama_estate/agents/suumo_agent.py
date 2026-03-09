"""
子エージェント①：SUUMO 横浜中古マンション収集
条件：3LDK / 6000万以内 / 駅徒歩5分以内 / 横浜市
"""

import requests
from bs4 import BeautifulSoup
import time
import json
import re
from datetime import date

# ============================================================
# 検索条件
# ============================================================
SEARCH_CONFIG = {
    "area": "横浜市",
    "madori": "3LDK",
    "price_max": 6000,          # 万円
    "walk_max": 5,              # 分以内
    "build_year_min": 1999,     # 築25年以内目安（2024基準）
    "source": "SUUMO",
}

BASE_URL = "https://suumo.jp/jj/bukken/ichiran/JJ012FC001/"
PARAMS = {
    "ar": "030",           # 神奈川エリアコード
    "bs": "040",           # 中古マンション
    "ta": "14",            # 神奈川県
    "sc": "14100",         # 横浜市（市区町村コード群、実際はもっと細かく指定）
    "cb": "0.0",
    "ct": "60.0",          # 6000万円上限
    "md": "07",            # 3LDK
    "et": "5",             # 駅徒歩5分以内
    "cn": "25",            # 築年数25年以内
    "page": 1,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

def fetch_page(page_num: int) -> "BeautifulSoup | None":
    """指定ページをフェッチしてBeautifulSoupを返す"""
    params = {**PARAMS, "page": page_num}
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        time.sleep(2)  # サーバー負荷配慮
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"[SUUMO] ページ{page_num}取得失敗: {e}")
        return None

def parse_properties(soup: BeautifulSoup) -> list[dict]:
    """物件リストをパース"""
    properties = []
    items = soup.select("div.cassette_innerbox")  # SUUMOの物件カード

    for item in items:
        try:
            # 物件名
            name_el = item.select_one("h2.property_unit-title")
            name = name_el.get_text(strip=True) if name_el else ""

            # 価格（万円）
            price_el = item.select_one("span.dottable-value")
            price_text = price_el.get_text(strip=True) if price_el else "0"
            price = int(re.sub(r"[^\d]", "", price_text.split("万")[0]) or 0)

            # 所在地
            address_els = item.select("td.dottable-value")
            address = address_els[0].get_text(strip=True) if address_els else ""

            # 交通（駅名・徒歩）
            transport_els = item.select("li.property_unit-detail-transportation")
            transport = transport_els[0].get_text(strip=True) if transport_els else ""

            # 駅徒歩分数を抽出
            walk_match = re.search(r"徒歩(\d+)分", transport)
            walk_min = int(walk_match.group(1)) if walk_match else 99

            # 専有面積
            area_el = item.select_one("span.dottable-value:-soup-contains('m²')")
            # SUUMOはtdで取得する方が安定
            all_tds = item.select("td.dottable-value")
            area_m2 = 0.0
            for td in all_tds:
                m = re.search(r"([\d.]+)m²", td.get_text())
                if m:
                    area_m2 = float(m.group(1))
                    break

            # 築年数
            build_year = ""
            for td in all_tds:
                m = re.search(r"(\d{4})年", td.get_text())
                if m:
                    build_year = m.group(1)
                    break

            # ㎡単価計算
            price_per_m2 = round(price / area_m2, 1) if area_m2 > 0 else 0

            # 詳細URL
            link_el = item.select_one("a[href*='/ms/mansion/']")
            detail_url = "https://suumo.jp" + link_el["href"] if link_el else ""

            if price > 0 and walk_min <= 5:
                properties.append({
                    "source": "SUUMO",
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
            print(f"[SUUMO] パースエラー: {e}")
            continue

    return properties

def get_total_pages(soup: BeautifulSoup) -> int:
    """総ページ数を取得"""
    pager = soup.select_one("div.pagination")
    if not pager:
        return 1
    page_links = pager.select("a")
    nums = [int(a.get_text()) for a in page_links if a.get_text().isdigit()]
    return max(nums) if nums else 1

def run() -> list[dict]:
    """メイン実行：全ページ収集"""
    print("[SUUMO] 収集開始...")
    all_props = []

    # 1ページ目で総ページ数を確認
    first_soup = fetch_page(1)
    if not first_soup:
        return []

    total = min(get_total_pages(first_soup), 10)  # 最大10ページ（礼儀として）
    print(f"[SUUMO] 総ページ数: {total}")

    all_props.extend(parse_properties(first_soup))

    for page in range(2, total + 1):
        soup = fetch_page(page)
        if soup:
            props = parse_properties(soup)
            all_props.extend(props)
            print(f"[SUUMO] {page}/{total}ページ完了 (+{len(props)}件)")

    print(f"[SUUMO] 収集完了: 合計 {len(all_props)} 件")
    return all_props

if __name__ == "__main__":
    results = run()
    # 結果をJSONで出力（親エージェントが読み取る）
    output_path = "data/suumo_latest.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[SUUMO] → {output_path} に保存完了")
