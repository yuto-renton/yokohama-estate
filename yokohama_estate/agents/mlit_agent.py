"""
国土交通省 不動産取引価格情報API を使った横浜市 3LDK 中古マンションデータ収集
API: https://www.land.mlit.go.jp/webland/api/TradeListSearch
認証不要・無料・公式データ（成約価格）
"""

import requests
import json
import re
import time
from datetime import date
from typing import List, Dict, Optional

# 横浜市の全18区コード
YOKOHAMA_WARDS = {
    "14101": "鶴見区",
    "14102": "神奈川区",
    "14103": "西区",
    "14104": "中区",
    "14105": "南区",
    "14106": "港南区",
    "14107": "保土ケ谷区",
    "14108": "旭区",
    "14109": "磯子区",
    "14110": "金沢区",
    "14111": "港北区",
    "14112": "戸塚区",
    "14113": "栄区",
    "14114": "泉区",
    "14115": "瀬谷区",
    "14116": "緑区",
    "14117": "青葉区",
    "14118": "都筑区",
}

BASE_URL = "https://www.land.mlit.go.jp/webland/api/TradeListSearch"

# 和暦 → 西暦変換テーブル
ERA_TABLE = {
    "令和": 2018,
    "平成": 1988,
    "昭和": 1925,
    "大正": 1911,
    "明治": 1868,
}


def get_query_periods(n_quarters: int = 8) -> tuple:
    """直近n四半期の from/to を返す（APIデータは約1四半期遅延）"""
    today = date.today()
    year = today.year
    q = (today.month - 1) // 3  # 0-3
    # 1四半期前から遡る
    if q == 0:
        q = 3
        year -= 1
    else:
        q -= 1

    periods = []
    for _ in range(n_quarters):
        periods.append(f"{year}{q}")
        if q == 1:
            q = 4
            year -= 1
        else:
            q -= 1

    return periods[-1], periods[0]  # from, to


def parse_build_year(raw: str) -> str:
    """建築年を西暦4桁文字列に変換（例: '令和3年' → '2021'）"""
    if not raw:
        return ""
    # 西暦がそのまま入っている場合
    m = re.search(r"(\d{4})", raw)
    if m:
        return m.group(1)
    # 和暦
    for era, base in ERA_TABLE.items():
        m = re.search(rf"{era}(\d+)年", raw)
        if m:
            return str(base + int(m.group(1)))
    return ""


def parse_price_man(raw) -> int:
    """取引価格（円）→ 万円（int）"""
    try:
        return int(str(raw).replace(",", "")) // 10000
    except (ValueError, TypeError):
        return 0


def parse_area(raw) -> float:
    try:
        return float(str(raw).replace("㎡", "").strip())
    except (ValueError, TypeError):
        return 0.0


def fetch_ward(city_code: str, from_period: str, to_period: str) -> List[dict]:
    params = {
        "from": from_period,
        "to": to_period,
        "area": "14",        # 神奈川県
        "city": city_code,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as e:
        print(f"  取得失敗 ({city_code}): {e}")
        return []


def normalize_floor_plan(raw: str) -> str:
    """全角数字・英字を半角に正規化"""
    table = str.maketrans("０１２３４５６７８９ＬＤＫＳＲＡＢＣＤＥＦＧＨＩＪＫＭＮＯＰＱＲＳＴＵＶＷＸＹＺ",
                          "0123456789LDKSRABCDEFGHIJKMNOPQRSTUVWXYZldk")
    return raw.translate(table)


def is_3ldk(floor_plan: str) -> bool:
    normalized = normalize_floor_plan(floor_plan)
    return "3LDK" in normalized


def run() -> List[Dict]:
    from_period, to_period = get_query_periods(8)
    print(f"[MLIT] 国土交通省API 収集開始: {from_period}〜{to_period}")
    print(f"[MLIT] 対象: 横浜市全18区 / 3LDK / 6,000万以下\n")

    all_props = []

    for city_code, ward_name in YOKOHAMA_WARDS.items():
        print(f"  [{ward_name}] 取得中...", end="", flush=True)
        raw_list = fetch_ward(city_code, from_period, to_period)

        count = 0
        for item in raw_list:
            # 中古マンション等のみ
            if item.get("Type") != "中古マンション等":
                continue
            # 3LDKフィルタ
            if not is_3ldk(item.get("FloorPlan", "")):
                continue

            price_man = parse_price_man(item.get("TradePrice", 0))
            if price_man <= 0 or price_man > 6000:
                continue

            area_m2 = parse_area(item.get("Area", 0))

            # ㎡単価: APIのUnitPriceは万円/㎡単位
            unit_price_raw = item.get("UnitPrice", "")
            if unit_price_raw:
                try:
                    price_per_m2 = float(str(unit_price_raw).replace(",", ""))
                except (ValueError, TypeError):
                    price_per_m2 = round(price_man / area_m2, 1) if area_m2 > 0 else 0
            else:
                price_per_m2 = round(price_man / area_m2, 1) if area_m2 > 0 else 0

            build_year = parse_build_year(item.get("BuildingYear", ""))
            district = item.get("DistrictName", "")

            all_props.append({
                "source": "国土交通省",
                "period": item.get("Period", ""),
                "date": str(date.today()),
                "name": f"{ward_name} {district}".strip(),
                "price_man": price_man,
                "address": f"横浜市{ward_name}{district}",
                "ward": ward_name,
                "area_m2": area_m2,
                "price_per_m2": price_per_m2,
                "build_year": build_year,
                "floor_plan": item.get("FloorPlan", ""),
                "structure": item.get("Structure", ""),
                "renovation": item.get("Renovation", ""),
                "remarks": item.get("Remarks", ""),
                "url": "",
                "walk_min": None,
                "transport": "",
            })
            count += 1

        print(f" {count}件")
        time.sleep(0.3)

    print(f"\n[MLIT] 収集完了: 合計 {len(all_props)} 件")
    return all_props


if __name__ == "__main__":
    results = run()
    output_path = "data/mlit_latest.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[MLIT] → {output_path} に保存完了")
