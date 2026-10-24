"""國定假日 / 補班日判斷（供 timeline 期限順延）。[純規則，不呼叫 LLM]

資料來源為行政院人事行政總處「政府行政機關辦公日曆表」，存於 data/calendar/<year>.json
（下載方式與來源見 data/calendar/README.md）。

設計原則（呼應民眾版「保守提醒」）：
- **補班日視為上班日**：期限末日落在補班日（週末上班）不順延。
- **彈性放假 / 國定假日視為放假日**：期限末日落在這些日子會順延。
- **日曆未涵蓋的年份退回只判斷週末**，並透過 calendar_complete() 回報「日曆不完整」，
  讓介面能提醒使用者自行確認國定假日，避免因資料缺漏而誤算。

對外介面：
    is_non_business_day(d) -> bool      該日是否為非上班日（放假日）
    calendar_complete(d)   -> bool      該日所屬年份是否有日曆資料
    describe_day(d)         -> str|None  該日的假日名稱（若有，供追溯顯示）
"""

from __future__ import annotations

import datetime as _dt
import json
from functools import lru_cache
from pathlib import Path

#: 日曆資料夾。放在 repo 內（公開政府資料、無個資），隨程式一起部署。
_CALENDAR_DIR = Path(__file__).resolve().parents[1] / "data" / "calendar"


@lru_cache(maxsize=None)
def _load_year(year: int) -> dict[str, dict] | None:
    """載入某年度日曆的 days 對照表；無資料回傳 None（供退回週末判斷）。"""
    path = _CALENDAR_DIR / f"{year}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    days = data.get("days")
    return days if isinstance(days, dict) else None


def _is_weekend(d: _dt.date) -> bool:
    return d.weekday() >= 5          # 5=六 6=日


def calendar_complete(d: _dt.date) -> bool:
    """該日所屬年份是否有日曆資料。False 表示只能退回週末判斷。"""
    return _load_year(d.year) is not None


def is_non_business_day(d: _dt.date) -> bool:
    """該日是否為非上班日（放假日）。

    有日曆資料時以日曆為準（補班日→上班、彈性放假/國定假日→放假）；
    沒有資料時退回只判斷週末（保守：可能低估順延，故搭配 calendar_complete 提醒）。
    """
    days = _load_year(d.year)
    if days is None:
        return _is_weekend(d)

    rec = days.get(d.isoformat())
    if rec is not None:
        # 日曆明確標記：補班日 holiday=False（即使是週末也算上班），
        # 國定假日/彈性放假 holiday=True。
        return bool(rec.get("holiday"))

    # 日曆有該年度但沒特別標記這天 → 依預設週末規則。
    return _is_weekend(d)


def describe_day(d: _dt.date) -> str | None:
    """回傳該日的假日/補班名稱（若日曆有標記），供計算說明追溯。"""
    days = _load_year(d.year)
    if not days:
        return None
    rec = days.get(d.isoformat())
    if not rec:
        return None
    desc = (rec.get("desc") or "").strip()
    return desc or None
