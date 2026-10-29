#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重要イベントNEWS通知アプリ
毎朝08:30 JSTに、本日・明日・明後日の重要イベントをLINEへ1通で通知する。
データ取得元:
- Forex Factory 公開カレンダーJSON: 高重要度の経済指標・予定イベント
- Traders Web: 日本株の決算発表予定
- Nasdaq 公開カレンダーAPI: 米国企業の決算発表予定
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

JST = ZoneInfo("Asia/Tokyo")
ET = ZoneInfo("America/New_York")
UTC = timezone.utc
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("important-events-news")

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_TO = os.getenv("LINE_TO", "").strip()

# 重要企業の対象: 超大型株＋相場への影響が大きい半導体・金融・大型テック等
US_PRIORITY_TICKERS = {
    # mega-cap / platforms
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO",
    "ORCL", "BRK.B", "BRK-B", "LLY", "JPM", "V", "MA", "WMT", "COST", "NFLX",
    "AMD", "QCOM", "TXN", "MU", "AMAT", "LRCX", "KLAC", "ASML", "INTC", "TSM",
    # major financials
    "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP",
    # major industrial / energy / consumer
    "XOM", "CVX", "CAT", "GE", "HON", "UNH", "JNJ", "PG", "HD", "DIS", "CRM",
    "ADBE", "IBM", "NOW", "UBER", "PLTR", "COIN", "SMCI", "ARM", "MRVL",
}
JP_PRIORITY_NAME_TERMS = (
    "半導体", "東京エレクトロン", "アドバンテスト", "ディスコ", "レーザーテック",
    "ルネサス", "SCREEN", "ＳＣＲＥＥＮ", "ソフトバンク", "トヨタ", "ホンダ",
    "日産", "三菱ＵＦＪ", "三井住友", "みずほ", "野村", "東京海上", "キーエンス",
    "ファナック", "日立", "ソニー", "任天堂", "信越化学", "リクルート",
    "三菱重工", "川崎重工", "ＩＨＩ", "ＮＴＴ", "ＫＤＤＩ", "日本製鉄",
)
JP_MARKET_CAP_MIN_100M_YEN = 5000  # Traders Webの時価総額表示は「億円」

HTTP = requests.Session()
HTTP.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; ImportantEventsNews/1.0; +https://github.com/)",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
})


def jst_now() -> datetime:
    return datetime.now(JST)


def parse_iso_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Unix timestamps are UTC.
        try:
            return datetime.fromtimestamp(value, UTC).astimezone(JST)
        except (ValueError, OSError, OverflowError):
            return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(JST)
    except ValueError:
        return None


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def fetch_forex_factory_events(today: date) -> list[dict[str, Any]]:
    """高重要度のUSD/JPY/GBP/CNYイベントを公開JSONから取得。"""
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    response = HTTP.get(url, timeout=25)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"経済カレンダーの応答形式が想定外です: {type(payload).__name__}")

    allowed_currencies = {"USD", "JPY", "GBP", "CNY"}
    events: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        impact = normalize_text(row.get("impact") or row.get("importance")).lower()
        currency = normalize_text(row.get("country") or row.get("currency")).upper()
        if currency not in allowed_currencies:
            continue
        if impact not in {"high", "holiday"}:
            continue
        title = normalize_text(row.get("title") or row.get("event"))
        if not title:
            continue
        dt = parse_iso_datetime(row.get("date") or row.get("datetime") or row.get("timestamp"))
        if not dt:
            # 日付だけのレコードは時刻不明としてJST 00:00に置く
            raw_date = str(row.get("date") or "").strip()[:10]
            try:
                dt = datetime.combine(date.fromisoformat(raw_date), dt_time(0, 0), JST)
            except ValueError:
                continue
        event_day = dt.date()
        if not (today <= event_day <= today + timedelta(days=2)):
            continue

        actual = normalize_text(row.get("actual"))
        forecast = normalize_text(row.get("forecast"))
        previous = normalize_text(row.get("previous"))
        detail = []
        if forecast:
            detail.append(f"予想 {forecast}")
        if previous:
            detail.append(f"前回 {previous}")
        events.append({
            "date": event_day.isoformat(),
            "time": dt.strftime("%H:%M") if dt.time() != dt_time(0, 0) else "時刻未確認",
            "category": "経済指標・予定イベント",
            "region": currency,
            "title": title,
            "detail": " / ".join(detail),
            "source": "Forex Factory",
            "url": "https://www.forexfactory.com/calendar",
            "sort_dt": dt.isoformat(),
        })
    return events


def fetch_japan_earnings(today: date) -> list[dict[str, Any]]:
    """
    Traders Webの公開決算カレンダーから、時価総額5,000億円以上、
    または半導体・金融等の指定重要企業を抽出する。
    """
    url = "https://www.traders.co.jp/market_jp/earnings_calendar/all/all/1"
    response = HTTP.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    events: list[dict[str, Any]] = []
    target_dates = {today + timedelta(days=i) for i in range(3)}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for tr in rows:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 6:
                continue
            values = [normalize_text(c.get_text(" ", strip=True)) for c in cells]
            row_text = " | ".join(values)
            # Rows typically contain date, time, name(code/market), type, sector, market cap.
            match = re.search(r"(\d{1,2})/(\d{1,2})", row_text)
            if not match:
                continue
            month, day_num = int(match.group(1)), int(match.group(2))
            year = today.year
            try:
                event_day = date(year, month, day_num)
                # Year boundary handling for the next three days.
                if event_day < today - timedelta(days=180):
                    event_day = date(year + 1, month, day_num)
                elif event_day > today + timedelta(days=180):
                    event_day = date(year - 1, month, day_num)
            except ValueError:
                continue
            if event_day not in target_dates:
                continue

            time_text = values[1] if len(values) > 1 else "-"
            if not re.fullmatch(r"\d{1,2}:\d{2}", time_text or ""):
                time_text = "時刻未確認"
            name_cell = cells[2] if len(cells) > 2 else cells[0]
            name_text = normalize_text(name_cell.get_text(" ", strip=True))
            code_match = re.search(r"\(([0-9A-Z]{4,5})/", name_text)
            code = code_match.group(1) if code_match else ""
            company = re.sub(r"\s*\([0-9A-Z]{4,5}/.*$", "", name_text).strip()
            sector = values[4] if len(values) > 4 else ""
            cap_text = values[5] if len(values) > 5 else ""
            cap_match = re.search(r"([\d,]+)", cap_text)
            cap = int(cap_match.group(1).replace(",", "")) if cap_match else 0
            priority_name = any(term.lower() in company.lower() for term in JP_PRIORITY_NAME_TERMS)
            if cap < JP_MARKET_CAP_MIN_100M_YEN and not priority_name:
                continue
            if not company:
                continue
            if time_text != "時刻未確認":
                hh, mm = map(int, time_text.split(":"))
                event_dt = datetime.combine(event_day, dt_time(hh, mm), JST)
            else:
                event_dt = datetime.combine(event_day, dt_time(0, 0), JST)
            events.append({
                "date": event_day.isoformat(),
                "time": time_text,
                "category": "日本企業決算",
                "region": "日本",
                "title": f"{company}（{code}）決算発表" if code else f"{company} 決算発表",
                "detail": f"{sector} / 時価総額 約{cap:,}億円" if cap else sector,
                "source": "Traders Web",
                "url": url,
                "sort_dt": event_dt.isoformat(),
            })
    # De-duplicate by date+title
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in events:
        unique[(item["date"], item["title"])] = item
    return list(unique.values())


def fetch_us_earnings(day: date) -> list[dict[str, Any]]:
    """Nasdaq公開カレンダーから日付ごとに取得し、重要銘柄のみ残す。"""
    url = "https://api.nasdaq.com/api/calendar/earnings"
    response = HTTP.get(
        url,
        params={"date": day.isoformat()},
        headers={
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/",
        },
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError(f"Nasdaq決算カレンダーの応答形式が想定外です: {str(payload)[:200]}")
    events: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = normalize_text(row.get("symbol") or row.get("ticker")).upper()
        if symbol not in US_PRIORITY_TICKERS:
            continue
        name = normalize_text(row.get("name") or row.get("companyName") or symbol)
        market_time = normalize_text(row.get("time") or row.get("timeOfDay") or row.get("time-of-day")).lower()
        # Nasdaq reports pre-market / after-hours in the company's local earnings date.
        # Convert representative times in America/New_York to JST so AMC correctly moves to the next JST day.
        if any(token in market_time for token in ("after", "post", "amc", "after-hours")):
            local_dt = datetime.combine(day, dt_time(16, 15), ET)
            time_label = "翌朝（米国引け後）"
        elif any(token in market_time for token in ("before", "pre", "bmo", "pre-market")):
            local_dt = datetime.combine(day, dt_time(8, 0), ET)
            time_label = "夜（米国寄り前）"
        else:
            local_dt = datetime.combine(day, dt_time(12, 0), ET)
            time_label = "時刻未確認"
        jst_dt = local_dt.astimezone(JST)
        # If Nasdaq marks an after-hours release, the event belongs to the next JST date.
        events.append({
            "date": jst_dt.date().isoformat(),
            "time": jst_dt.strftime("%H:%M") if time_label != "時刻未確認" else time_label,
            "category": "米国企業決算",
            "region": "米国",
            "title": f"{name}（{symbol}）決算発表",
            "detail": time_label,
            "source": "Nasdaq",
            "url": f"https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/earnings",
            "sort_dt": jst_dt.isoformat(),
        })
    return events


def fetch_all_events(today: date) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    failures: list[str] = []

    for label, fn in (
        ("経済指標・予定イベント", lambda: fetch_forex_factory_events(today)),
        ("日本企業決算", lambda: fetch_japan_earnings(today)),
    ):
        try:
            part = fn()
            log.info("%s: %d件取得", label, len(part))
            events.extend(part)
        except Exception as exc:
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
            log.exception("%sの取得に失敗", label)

    # 米国の引け後決算は日本時間では翌日にずれ込むため、米国日付を前日から取得する。
    for offset in range(-1, 3):
        day = today + timedelta(days=offset)
        try:
            part = fetch_us_earnings(day)
            log.info("米国企業決算（米国日付）%s: %d件取得", day.isoformat(), len(part))
            events.extend(part)
        except Exception as exc:
            failures.append(f"米国企業決算（米国日付）{day.isoformat()}: {type(exc).__name__}: {exc}")
            log.exception("米国企業決算（米国日付）%sの取得に失敗", day.isoformat())

    if not events and failures:
        raise RuntimeError("すべてのイベントソースからデータを取得できませんでした: " + " / ".join(failures))
    if failures:
        log.warning("一部データソースに失敗があります: %s", " / ".join(failures))
    return events


def format_line_message(events: list[dict[str, Any]], today: date) -> str:
    """LINE向けに短く整形。ヘッダー・注記・出典は表示しない。"""
    lines: list[str] = []
    day_labels = ["本日", "明日", "明後日"]

    region_labels = {
        "USD": "米",
        "JPY": "日",
        "GBP": "英",
        "CNY": "中",
        "米国": "米",
        "日本": "日",
    }

    for offset, label in enumerate(day_labels):
        day = today + timedelta(days=offset)
        weekday_ja = "月火水木金土日"[day.weekday()]
        if lines:
            lines.append("")
        lines.append(f"【{label} {day:%m/%d（{weekday_ja}）}】")
        day_events = [e for e in events if e.get("date") == day.isoformat()]
        day_events.sort(key=lambda e: (e.get("sort_dt", ""), e.get("category", ""), e.get("title", "")))
        if not day_events:
            lines.append("・重要イベントの登録なし")
            continue

        for event in day_events:
            time_text = str(event.get("time", "時刻未確認"))
            # 先頭のゼロを外して 03:00 -> 3:00 にする。
            if re.fullmatch(r"\d{1,2}:\d{2}", time_text):
                hour, minute = time_text.split(":")
                time_text = f"{int(hour)}:{minute}"

            category = str(event.get("category", ""))
            title = str(event.get("title", "")).strip()

            if category in {"日本企業決算", "米国企業決算"}:
                # 決算は「時刻【決算】コード 企業名」だけを表示する。
                jp_match = re.match(r"^(.*?)（([0-9A-Z]{4,5})）決算発表$", title)
                us_match = re.match(r"^(.*?)（([A-Z.\-]{1,6})）決算発表$", title)
                match = jp_match or us_match
                if match:
                    company, code = match.group(1).strip(), match.group(2).strip()
                    line = f"{time_text}【決算】{code} {company}"
                else:
                    line = f"{time_text}【決算】{title.replace(' 決算発表', '').replace('決算発表', '').strip()}"
            else:
                region = str(event.get("region", ""))
                region_label = region_labels.get(region, region)
                detail = str(event.get("detail", "")).strip()
                line = f"{time_text} 【{region_label}】{title}"
                if detail:
                    line += f" — {detail}"
            lines.append("・" + line)

    message = "\n".join(lines)
    # LINEのテキスト上限に収まらない場合は末尾のイベントから省く。
    if len(message) > 4900:
        lines = message.split("\n")
        while len("\n".join(lines)) > 4900:
            # 日付見出しは残し、最後のイベント行を末尾から削る。
            removable = next((i for i in range(len(lines) - 1, -1, -1)
                              if lines[i].startswith("・") and "重要イベントの登録なし" not in lines[i]), None)
            if removable is None:
                break
            lines.pop(removable)
        message = "\n".join(lines)
    return message


def send_line(message: str) -> None:
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_TO:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN と LINE_TO を環境変数に設定してください。")
    url = "https://api.line.me/v2/bot/message/push"
    response = HTTP.post(
        url,
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "to": LINE_TO,
            "messages": [{"type": "text", "text": message[:5000]}],
        },
        timeout=25,
    )
    if response.status_code >= 300:
        raise RuntimeError(f"LINE Messaging API送信失敗: HTTP {response.status_code} {response.text[:500]}")
    log.info("LINE通知成功")


def main() -> int:
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "notify"
    now = jst_now()
    today = now.date()
    log.info("開始: mode=%s, JST=%s", mode, now.isoformat())
    events = fetch_all_events(today)
    message = format_line_message(events, today)

    if mode == "calculate":
        print(message)
        log.info("計算テスト成功: イベント件数=%d", len(events))
        return 0
    if mode not in {"notify", "send"}:
        raise ValueError("使用方法: python app.py [calculate|notify]")
    send_line(message)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log.exception("処理に失敗しました: %s", exc)
        raise SystemExit(1)
