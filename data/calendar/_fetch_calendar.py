"""一次性下載腳本：抓取台灣政府行政機關辦公日曆表並存成精簡 JSON。

資料來源（DGPA 人事行政總處原始開放資料的社群 JSON 鏡像）：
    https://github.com/ruyut/TaiwanCalendar

原始政府資料：政府資料開放平臺「中華民國政府行政機關辦公日曆表」
    https://data.gov.tw/dataset/14718

用法：
    python data/calendar/_fetch_calendar.py

輸出：data/calendar/<year>.json，格式為
    {"year": 2026, "days": {"YYYY-MM-DD": {"holiday": true, "desc": "開國紀念日"}, ...}}
只收錄「與預設週末規則不同」或「有名稱的假日」之日子，讓檔案精簡且可人工核對。
但為求完整與可追溯，補班日（週末上班）一定收錄。
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

YEARS = (2024, 2025, 2026, 2027)
BASE = "https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json"
OUT_DIR = Path(__file__).resolve().parent


def _is_weekend(week_cn: str) -> bool:
    return week_cn in ("六", "日")


def fetch_year(year: int) -> dict:
    url = BASE.format(year=year)
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (trusted host)
        raw = json.loads(resp.read().decode("utf-8"))

    days: dict[str, dict] = {}
    for rec in raw:
        ymd = rec["date"]                      # "20260101"
        iso = f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"
        is_holiday = bool(rec.get("isHoliday"))
        week = rec.get("week", "")
        desc = (rec.get("description") or "").strip()
        weekend = _is_weekend(week)

        # 只收錄「與預設週末規則不同」或有名稱的日子：
        #   - 平日放假（彈性放假/國定假日落平日）：weekend=False, holiday=True
        #   - 週末上班（補班日）：weekend=True, holiday=False
        #   - 有名稱的國定假日（即使落在週末也記，方便核對）
        if is_holiday != weekend or desc:
            days[iso] = {"holiday": is_holiday, "desc": desc}

    return {"year": year, "source": url, "days": days}


def main() -> int:
    for year in YEARS:
        data = fetch_year(year)
        out = OUT_DIR / f"{year}.json"
        out.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"wrote {out} ({len(data['days'])} special days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
