#!/usr/bin/env python3
"""
Builds the daily meme coin report website into the docs/ folder.

Runs once a day on GitHub's servers (see .github/workflows/daily.yml), so it
works even when your PC is off. GitHub Pages then shows docs/ as a website.

You can also run it by hand to preview:   py build_site.py
then open docs\\index.html in your browser.

Public market data only. No keys. NOT financial advice.
"""
import html
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

import memecoin_screener as ms

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs")
TOP = 30


def today_and_stamp():
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
        return now.date().isoformat(), now.strftime("%Y-%m-%d %I:%M %p New York time")
    except Exception:
        now = datetime.now(timezone.utc)
        return now.date().isoformat(), now.strftime("%Y-%m-%d %H:%M UTC")


# ---------------------------------------------------------------- data
def fetch(top):
    url = ("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
           "&category=meme-token&order=market_cap_desc"
           f"&per_page={top}&page=1&price_change_percentage=24h,7d,30d")
    for attempt in range(4):
        try:
            data = ms.http_json(url, retries=0)
            if isinstance(data, list) and data:
                return data
        except SystemExit as e:
            print(f"Attempt {attempt + 1} failed: {e.code}")
        if attempt < 3:
            time.sleep(30 * (attempt + 1))
    sys.exit("Could not get data from CoinGecko after several tries.")


def build_rows(coins):
    rows = []
    for c in coins:
        r = ms.score_gecko(c)
        rows.append({
            "id": c.get("id"),
            "sym": ms.ascii_name(c.get("symbol"), c.get("id")).upper()[:9],
            "name": ms.ascii_name(c.get("name"), c.get("id"))[:24],
            "mcap": ms.num(c.get("market_cap")),
            "c7": c.get("price_change_percentage_7d_in_currency"),
            "c30": c.get("price_change_percentage_30d_in_currency"),
            "score": r.score, "verdict": r.verdict, "hard": list(r.hard),
            "notes": [(p, t) for p, t in sorted(r.notes, key=lambda n: n[0])],
        })
    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows


# ------------------------------------------------------------- history
def load_history(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_history(path, hist):
    hist = {k: hist[k] for k in sorted(hist)[-60:]}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hist, f)


def snapshot(rows):
    return {r["id"]: {"sym": r["sym"], "name": r["name"], "v": r["verdict"],
                      "s": r["score"], "m": r["mcap"]} for r in rows}


def changes(prev, cur):
    lab = lambda d: f"{d['sym']} ({d['name']})"
    moved, new, dropped, other = [], [], [], []
    for cid, now in cur.items():
        old = prev.get(cid)
        if old is None:
            new.append(f"NEW in the list: {lab(now)} -> {now['v']} (score {now['s']})")
            continue
        if old["v"] != now["v"]:
            word = "UPGRADED" if ms.RANK[now["v"]] > ms.RANK[old["v"]] else "DOWNGRADED"
            moved.append(f"{word}: {lab(now)}: {old['v']} -> {now['v']} "
                         f"(score {old['s']} -> {now['s']})")
        elif abs(now["s"] - old["s"]) >= 8:
            other.append(f"SCORE MOVE: {lab(now)}: {old['s']} -> {now['s']} (still {now['v']})")
        if old.get("m") and now.get("m") and abs(now["m"] / old["m"] - 1) >= 0.20:
            other.append(f"BIG MOVE: {lab(now)} market cap {now['m'] / old['m'] - 1:+.0%} "
                         f"({ms.usd(old['m'])} -> {ms.usd(now['m'])})")
    for cid, old in prev.items():
        if cid not in cur:
            dropped.append(f"LEFT the list: {lab(old)} (was {old['v']})")
    return moved + new + dropped + other


# ---------------------------------------------------------------- html
CSS = """
:root{--bg:#fff;--fg:#1c1c1e;--mut:#6b6b70;--line:#e3e3e8;--card:#f6f6f8}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececf0;--mut:#9a9aa3;--line:#2c2c31;--card:#1c1c20}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:20px 14px 60px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:26px 0 8px}
.mut{color:var(--mut)}a{color:inherit}.warn{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:12px 0}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%}th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;color:var(--mut);font-weight:600;white-space:nowrap}td.n{text-align:right;white-space:nowrap}
.pos{color:#1a8f4c}.neg{color:#d1383d}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600;white-space:nowrap}
.WATCHLIST{background:#fdf1c8;color:#6b5200}.HIGH-RISK{background:#ffe0c2;color:#7a3a00}.AVOID{background:#ffd4d6;color:#8a1118}
summary{cursor:pointer}ul{margin:6px 0 4px 18px;padding:0}.hard{color:#d1383d;font-weight:600}
.arch a{display:inline-block;margin:2px 10px 2px 0}
"""


def esc(x):
    return html.escape(str(x), quote=True)


def cls(v):
    return "pos" if (v or 0) > 0 else "neg" if (v or 0) < 0 else ""


def render(d, home, arch_prefix):
    rows_html = []
    for r in d["rows"]:
        why = "".join(f'<li class="hard">[!!] {esc(t)}</li>' for t in r["hard"])
        why += "".join(f"<li>{'[+] ' if p > 0 else '[-] '}{esc(t)}</li>" for p, t in r["notes"])
        rows_html.append(
            f'<tr><td><details><summary><b>{esc(r["sym"])}</b> {esc(r["name"])}</summary>'
            f"<ul>{why}</ul></details></td>"
            f'<td class="n">{esc(ms.usd(r["mcap"]))}</td>'
            f'<td class="n {cls(r["c7"])}">{esc(ms.pct(r["c7"]))}</td>'
            f'<td class="n {cls(r["c30"])}">{esc(ms.pct(r["c30"]))}</td>'
            f'<td class="n">{r["score"]}</td>'
            f'<td><span class="pill {r["verdict"].replace(" ", "-")}">{esc(r["verdict"])}</span></td></tr>')

    counts = {v: sum(1 for r in d["rows"] if r["verdict"] == v)
              for v in ("WATCHLIST", "HIGH RISK", "AVOID")}
    if d["prev_date"]:
        items = "".join(f"<li>{esc(x)}</li>" for x in d["changes"]) or "<li>No rating changes.</li>"
        chg = f"<h2>What changed since {esc(d['prev_date'])}</h2><ul>{items}</ul>"
    else:
        chg = "<h2>What changed</h2><p class='mut'>First report. Changes will show from tomorrow.</p>"
    arch = "".join(f'<a href="{arch_prefix}{esc(a)}.html">{esc(a)}</a>' for a in d["archive"])
    back = f'<p><a href="{home}">Back to the latest report</a></p>' if home else ""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meme Coin Daily Report - {esc(d['date'])}</title><style>{CSS}</style></head><body><main>
{back}<h1>Meme Coin Daily Report</h1>
<div class="mut">Report for {esc(d['date'])}. Built {esc(d['stamp'])}. Data from CoinGecko.</div>
<div class="warn"><b>Read this first.</b> This rates warning signs; it does not predict prices.
WATCHLIST is not a buy signal, and meme coins can lose 90% or more at any time. Not financial advice.</div>
<h2>Market</h2><p>{esc(d['market'])}<br><span class="mut">{counts['WATCHLIST']} watchlist,
{counts['HIGH RISK']} high risk, {counts['AVOID']} avoid.</span></p>
{chg}
<h2>All coins</h2><div class="wrap"><table><thead><tr><th>Coin (tap for reasons)</th>
<th class="n">MCap</th><th class="n">7d</th><th class="n">30d</th><th class="n">Score</th><th>Verdict</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody></table></div>
<h2>Past reports</h2><div class="arch">{arch or '<span class="mut">None yet.</span>'}</div>
</main></body></html>"""


# ---------------------------------------------------------------- main
def main():
    os.makedirs(os.path.join(OUT, "reports"), exist_ok=True)
    open(os.path.join(OUT, ".nojekyll"), "a").close()
    date, stamp = today_and_stamp()

    coins = fetch(TOP)
    rows = build_rows(coins)
    ch30 = [ms.num(c.get("price_change_percentage_30d_in_currency")) for c in coins
            if c.get("price_change_percentage_30d_in_currency") is not None]
    market = (f"{sum(1 for x in ch30 if x < 0)} of {len(ch30)} coins are down over 30 days "
              f"(median {statistics.median(ch30):+.0f}%)." if ch30 else "No 30-day data.")

    hist_path = os.path.join(OUT, "data", "history.json")
    hist = load_history(hist_path)
    earlier = [k for k in hist if k < date]
    cur = snapshot(rows)
    prev_date = max(earlier) if earlier else None
    chg = changes(hist[prev_date], cur) if prev_date else []
    hist[date] = cur
    save_history(hist_path, hist)

    archive = sorted((f[:-5] for f in os.listdir(os.path.join(OUT, "reports"))
                      if f.endswith(".html") and f[:-5] != date), reverse=True)
    archive = [date] + archive
    d = {"date": date, "stamp": stamp, "market": market, "rows": rows,
         "prev_date": prev_date, "changes": chg, "archive": archive[:60]}

    with open(os.path.join(OUT, "reports", f"{date}.html"), "w", encoding="utf-8") as f:
        f.write(render(d, "../index.html", ""))
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(render(d, "", "reports/"))
    print(f"Built report for {date}: {len(rows)} coins, {len(chg)} changes.")


if __name__ == "__main__":
    main()
