"""
メインオーケストレーター
国土交通省 不動産取引価格情報API から横浜市3LDK中古マンションデータを収集し、
投資家目線のHTMLレポートを生成する。
"""

import json
import csv
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

# ============================================================
# データ収集
# ============================================================

def run_mlit_agent() -> list:
    """MLITエージェントを直接呼び出し（サブプロセス不要）"""
    sys.path.insert(0, str(Path(__file__).parent))
    from agents.mlit_agent import run
    return run()


# ============================================================
# 集計・分析
# ============================================================

def calc_stats(props: list) -> dict:
    if not props:
        return {}

    prices = [p["price_man"] for p in props if p["price_man"] > 0]
    prices_per_m2 = [p["price_per_m2"] for p in props if p.get("price_per_m2", 0) > 0]

    prices_sorted = sorted(prices)
    n = len(prices_sorted)
    median = (
        prices_sorted[n // 2]
        if n % 2 == 1
        else (prices_sorted[n // 2 - 1] + prices_sorted[n // 2]) / 2
    )

    avg_price = sum(prices) / len(prices)

    # 表面利回り試算（横浜3LDK賃料想定: 20万円/月）
    ASSUMED_RENT_MAN = 20
    yield_rate = round((ASSUMED_RENT_MAN * 12) / avg_price * 100, 2) if avg_price > 0 else 0

    # 価格帯分布
    brackets = {
        "〜3000万": 0,
        "3000〜4000万": 0,
        "4000〜5000万": 0,
        "5000〜6000万": 0,
        "6000万〜": 0,
    }
    for price in prices:
        if price < 3000:
            brackets["〜3000万"] += 1
        elif price < 4000:
            brackets["3000〜4000万"] += 1
        elif price < 5000:
            brackets["4000〜5000万"] += 1
        elif price < 6000:
            brackets["5000〜6000万"] += 1
        else:
            brackets["6000万〜"] += 1

    # 区別平均
    ward_prices: dict = {}
    for p in props:
        ward = p.get("ward", "")
        if ward:
            ward_prices.setdefault(ward, []).append(p["price_man"])
    ward_avg = {w: round(sum(v) / len(v)) for w, v in ward_prices.items() if v}
    ward_ranking = sorted(ward_avg.items(), key=lambda x: x[1])

    # 築年別分布（築年不明を除く）
    year_brackets = {"〜1990年": 0, "1991〜2000年": 0, "2001〜2010年": 0, "2011〜2020年": 0, "2021年〜": 0}
    for p in props:
        by = p.get("build_year", "")
        try:
            yr = int(by)
            if yr <= 1990:
                year_brackets["〜1990年"] += 1
            elif yr <= 2000:
                year_brackets["1991〜2000年"] += 1
            elif yr <= 2010:
                year_brackets["2001〜2010年"] += 1
            elif yr <= 2020:
                year_brackets["2011〜2020年"] += 1
            else:
                year_brackets["2021年〜"] += 1
        except (ValueError, TypeError):
            pass

    # 取引時期の範囲
    periods = sorted({p["period"] for p in props if p.get("period")})
    period_range = f"{periods[0]}〜{periods[-1]}" if periods else "不明"

    return {
        "count": len(props),
        "avg_price": round(avg_price),
        "median_price": round(median),
        "min_price": min(prices),
        "max_price": max(prices),
        "avg_price_per_m2": round(sum(prices_per_m2) / len(prices_per_m2), 1) if prices_per_m2 else 0,
        "yield_estimate_pct": yield_rate,
        "price_brackets": brackets,
        "year_brackets": year_brackets,
        "ward_ranking": ward_ranking,
        "period_range": period_range,
    }


def load_prev_week_avg() -> Optional[int]:
    path = "data/history.csv"
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    today = str(date.today())
    prev_rows = [r for r in rows if r["date"] != today]
    if not prev_rows:
        return None
    try:
        return int(prev_rows[-1]["avg_price"])
    except (ValueError, KeyError):
        return None


def append_to_history(stats: dict):
    path = "data/history.csv"
    today = str(date.today())
    file_exists = os.path.exists(path)
    fieldnames = ["date", "count", "avg_price", "median_price",
                  "min_price", "max_price", "avg_price_per_m2", "yield_estimate_pct"]
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "date": today,
            "count": stats["count"],
            "avg_price": stats["avg_price"],
            "median_price": stats["median_price"],
            "min_price": stats["min_price"],
            "max_price": stats["max_price"],
            "avg_price_per_m2": stats["avg_price_per_m2"],
            "yield_estimate_pct": stats["yield_estimate_pct"],
        })
    print(f"[main] history.csv に追記完了")


# ============================================================
# HTMLレポート生成
# ============================================================

def generate_html_report(props: list, stats: dict) -> str:
    today = str(date.today())
    prev_avg = load_prev_week_avg()

    if prev_avg and stats.get("avg_price"):
        diff = stats["avg_price"] - prev_avg
        diff_pct = round(diff / prev_avg * 100, 1)
        trend_html = f"""
        <div class="trend {'up' if diff > 0 else 'down'}">
            前回比: {'▲' if diff > 0 else '▼'} {abs(diff):,}万円 ({'+' if diff > 0 else ''}{diff_pct}%)
        </div>"""
    else:
        trend_html = "<div class='trend neutral'>前回比: 初回収集（比較データなし）</div>"

    # 物件テーブル（安い順 上位60件）
    rows_html = ""
    sorted_props = sorted(props, key=lambda x: x["price_man"])
    for p in sorted_props[:60]:
        ASSUMED_RENT_MAN = 20
        yield_est = round((ASSUMED_RENT_MAN * 12) / p["price_man"] * 100, 1) if p["price_man"] > 0 else 0
        renovation_badge = '<span class="badge-renov">リノベ</span>' if p.get("renovation") else ""
        rows_html += f"""
        <tr>
            <td>{p['name'][:20]}{renovation_badge}</td>
            <td class="num">{p['price_man']:,}万円</td>
            <td>{p['area_m2']}㎡</td>
            <td class="num">{p['price_per_m2']}万/㎡</td>
            <td>{p.get('build_year', '')}</td>
            <td class="yield">{yield_est}%</td>
            <td class="period">{p.get('period', '')}</td>
        </tr>"""

    # 区別ランキング
    ward_rows = ""
    for rank, (ward, avg) in enumerate(stats.get("ward_ranking", []), 1):
        ward_rows += f"<tr><td>{rank}</td><td>{ward}</td><td class='num'>{avg:,}万円</td></tr>"

    # 価格帯分布
    bracket_rows = "".join(
        f"<tr><td>{k}</td><td class='num'>{v}件</td></tr>"
        for k, v in stats.get("price_brackets", {}).items()
    )

    # 築年別分布
    year_rows = "".join(
        f"<tr><td>{k}</td><td class='num'>{v}件</td></tr>"
        for k, v in stats.get("year_brackets", {}).items()
    )

    period_range = stats.get("period_range", "不明")
    tsubo_price = round(stats.get("avg_price_per_m2", 0) * 3.305785)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>横浜中古マンション 相場レポート {today}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Helvetica Neue', 'Hiragino Sans', sans-serif; background: #0f1117; color: #e0e0e0; padding: 24px; }}
  h1 {{ font-size: 1.4em; color: #7eb8f7; margin-bottom: 4px; }}
  .subtitle {{ color: #888; font-size: 0.82em; margin-bottom: 8px; }}
  .source-note {{ color: #555; font-size: 0.75em; margin-bottom: 20px; padding: 6px 10px; background: #1a1d27; border-radius: 4px; display: inline-block; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(155px, 1fr)); gap: 12px; margin-bottom: 24px; }}
  .card {{ background: #1a1d27; border-radius: 10px; padding: 16px; border: 1px solid #2a2d3e; }}
  .card-label {{ font-size: 0.72em; color: #888; margin-bottom: 6px; }}
  .card-value {{ font-size: 1.5em; font-weight: bold; color: #7eb8f7; }}
  .card-sub {{ font-size: 0.78em; color: #aaa; margin-top: 4px; }}
  .trend {{ margin: 0 0 20px; font-size: 0.88em; padding: 8px 14px; border-radius: 6px; display: inline-block; }}
  .trend.up {{ background: #3d1a1a; color: #ff8080; }}
  .trend.down {{ background: #1a3d1a; color: #80ff80; }}
  .trend.neutral {{ background: #1e2130; color: #888; }}
  h2 {{ font-size: 1.05em; color: #aaa; margin: 28px 0 10px; border-left: 3px solid #7eb8f7; padding-left: 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.82em; }}
  th {{ background: #1a1d27; color: #888; padding: 8px; text-align: left; border-bottom: 1px solid #2a2d3e; }}
  td {{ padding: 7px 8px; border-bottom: 1px solid #1e2130; vertical-align: middle; }}
  tr:hover {{ background: #1a1d27; }}
  td.num {{ text-align: right; color: #7eb8f7; font-weight: bold; }}
  td.yield {{ text-align: right; color: #80d080; }}
  td.period {{ color: #666; font-size: 0.78em; }}
  .badge-renov {{ font-size: 0.65em; background: #2a3d2a; color: #80d080; padding: 1px 5px; border-radius: 3px; margin-left: 4px; }}
  .grid3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }}
  .note {{ background: #1a1d27; border-radius: 8px; padding: 16px; font-size: 0.82em; color: #888; margin-top: 28px; line-height: 1.7; }}
  .note strong {{ color: #aaa; }}
  @media (max-width: 768px) {{ .grid3 {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>

<h1>🏙 横浜 中古マンション 相場レポート</h1>
<p class="subtitle">{today} 生成 ／ 条件: 3LDK・6,000万円以下・横浜市全18区</p>
<span class="source-note">データソース: 国土交通省 不動産取引価格情報（{period_range}の成約データ）</span>

{trend_html}

<div class="cards">
  <div class="card">
    <div class="card-label">収集件数</div>
    <div class="card-value">{stats.get('count', 0):,}<span style="font-size:0.5em">件</span></div>
    <div class="card-sub">成約済み実績データ</div>
  </div>
  <div class="card">
    <div class="card-label">平均成約価格</div>
    <div class="card-value">{stats.get('avg_price', 0):,}<span style="font-size:0.5em">万</span></div>
    <div class="card-sub">中央値: {stats.get('median_price', 0):,}万</div>
  </div>
  <div class="card">
    <div class="card-label">最安値</div>
    <div class="card-value">{stats.get('min_price', 0):,}<span style="font-size:0.5em">万</span></div>
  </div>
  <div class="card">
    <div class="card-label">最高値</div>
    <div class="card-value">{stats.get('max_price', 0):,}<span style="font-size:0.5em">万</span></div>
  </div>
  <div class="card">
    <div class="card-label">平均㎡単価</div>
    <div class="card-value">{stats.get('avg_price_per_m2', 0)}<span style="font-size:0.4em">万/㎡</span></div>
    <div class="card-sub">坪単価: {tsubo_price:,}万/坪</div>
  </div>
  <div class="card">
    <div class="card-label">表面利回り試算</div>
    <div class="card-value" style="color:#80d080">{stats.get('yield_estimate_pct', 0)}<span style="font-size:0.5em">%</span></div>
    <div class="card-sub">賃料想定: 20万/月</div>
  </div>
</div>

<div class="grid3">
  <div>
    <h2>区別 平均価格ランキング（安い順）</h2>
    <table>
      <tr><th>順位</th><th>区</th><th>平均成約価格</th></tr>
      {ward_rows}
    </table>
  </div>
  <div>
    <h2>価格帯分布</h2>
    <table>
      <tr><th>価格帯</th><th>件数</th></tr>
      {bracket_rows}
    </table>
  </div>
  <div>
    <h2>築年別分布</h2>
    <table>
      <tr><th>築年</th><th>件数</th></tr>
      {year_rows}
    </table>
  </div>
</div>

<h2>成約物件一覧（価格安い順 上位60件）</h2>
<table>
  <tr>
    <th>エリア</th><th>成約価格</th><th>面積</th><th>㎡単価</th>
    <th>築年</th><th>利回り試算</th><th>取引時期</th>
  </tr>
  {rows_html}
</table>

<div class="note">
  <strong>📌 ゆーとメモ</strong><br>
  住宅補助: 月4万円 × 残り約8年 ＝ 計384万円（頭金に積み上げ可）<br>
  現賃料: 12.2万円 ／ 購入検討: 3年以内<br>
  利回り試算は横浜3LDK賃料想定20万/月の概算。あくまで参考値。<br>
  <br>
  <strong>⚠️ データ注記</strong><br>
  このレポートは「成約済み取引価格」であり、現在の売出し物件の相場とは異なる場合があります。<br>
  国土交通省データは公表まで1〜2四半期の遅延があります。
</div>

</body>
</html>"""
    return html


# ============================================================
# メイン実行
# ============================================================

def main():
    os.chdir(Path(__file__).parent)

    # ステップ1: 国交省APIからデータ収集
    props = run_mlit_agent()

    # ステップ2: JSONに保存
    os.makedirs("data", exist_ok=True)
    with open("data/mlit_latest.json", "w", encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False, indent=2)

    print(f"\n[main] 取得件数: {len(props)} 件")

    if not props:
        print("[main] データが取得できませんでした。ネットワーク接続を確認してください。")
        return

    # ステップ3: 統計計算
    stats = calc_stats(props)
    print(f"[main] 平均: {stats['avg_price']:,}万円 / 中央値: {stats['median_price']:,}万円")
    print(f"[main] 対象期間: {stats.get('period_range', '不明')}")

    # ステップ4: history.csv に追記
    append_to_history(stats)

    # ステップ5: HTMLレポート生成
    os.makedirs("reports", exist_ok=True)
    today = str(date.today())
    report_path = f"reports/{today}.html"
    html = generate_html_report(props, stats)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n{'='*55}")
    print(f"[main] ✅ 完了！")
    print(f"[main] レポート: {report_path}")
    print(f"[main] ブラウザで開く: open {report_path}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
