"""core/holidays.py 與 timeline 國定假日順延的純規則測試（不呼叫 LLM）。

涵蓋計畫任務 1.5 要求的案例：
  - 末日落在週日 → 順延到週一
  - 寄存送達 → 生效 +10 日 → 期限正確
  - 末日落在國定假日 → 順延到假期後第一個上班日
  - 末日落在補班日（週六上班）→ 不順延
  - 日曆未涵蓋年份 → 退回週末判斷並標示日曆不完整
"""
from __future__ import annotations

import datetime as dt

from core import holidays as hol
from core import timeline as tl


# ---------- holidays 基本判斷 ----------
def test_national_holiday_is_non_business_day():
    # 2026-10-10 國慶日（週六，本就放假）；2026-02-18 春節（週三，平日放假）
    assert hol.is_non_business_day(dt.date(2026, 2, 18)) is True
    assert hol.describe_day(dt.date(2026, 2, 18)) == "春節"


def test_makeup_workday_is_business_day():
    # 2025-02-08 補行上班（週六，但要上班）→ 非放假日
    assert hol.is_non_business_day(dt.date(2025, 2, 8)) is False
    assert hol.describe_day(dt.date(2025, 2, 8)) == "補行上班"


def test_ordinary_weekday_is_business_day():
    # 2026-10-05 週一，無特別標記 → 上班日
    assert hol.is_non_business_day(dt.date(2026, 10, 5)) is False


def test_ordinary_weekend_is_non_business_day():
    # 2026-10-03 週六，無特別標記 → 放假日
    assert hol.is_non_business_day(dt.date(2026, 10, 3)) is True


def test_calendar_complete_flag():
    assert hol.calendar_complete(dt.date(2026, 1, 1)) is True
    # 日曆未涵蓋的年份（例如 2099）→ 不完整
    assert hol.calendar_complete(dt.date(2099, 1, 1)) is False


def test_uncovered_year_falls_back_to_weekend():
    # 2099 無日曆：週日仍判放假、週一仍判上班
    assert hol.is_non_business_day(dt.date(2099, 1, 4)) is True   # 週日
    assert hol.is_non_business_day(dt.date(2099, 1, 5)) is False  # 週一


# ---------- timeline 順延整合 ----------
def _fields(service_date, method="本人收受", act_date="民國114年1月1日"):
    return {
        "original_disposition": {
            "act_date": act_date,
            "date": "民國115年9月1日",
            "service_date": service_date,
            "service_method": method,
        },
        "petition_filed_date": "",
    }


def test_deadline_rolls_over_sunday():
    # 計畫範例：本人送達 2026-10-02 → 生效 10-02 → +30 = 11-01（週日）→ 順延 11-02（週一）
    out = tl.build_timeline(_fields("2026-10-02"))
    assert out["_parsed"]["appeal_deadline"] == dt.date(2026, 11, 2)


def test_deposit_service_deadline():
    # 計畫範例：寄存送達 2026-09-01 → 生效 2026-09-11 → 期限 2026-10-12
    out = tl.build_timeline(_fields("2026-09-01", method="寄存送達"))
    assert out["_parsed"]["service_effective_date"] == dt.date(2026, 9, 11)
    assert out["_parsed"]["appeal_deadline"] == dt.date(2026, 10, 12)


def test_deadline_rolls_over_national_holiday():
    # 讓原末日落在國定假日：生效日 + 30 = 2026-10-10（國慶日，週六）
    # 2026-10-09 補假、10-10 國慶、10-11 週日 → 順延到 10-12（週一）
    # 生效日需為 2026-09-10（+30 = 10-10）
    out = tl.build_timeline(_fields("2026-09-10"))
    assert out["_parsed"]["appeal_deadline"] == dt.date(2026, 10, 12)


def test_deadline_not_rolled_on_makeup_workday():
    # 2025-02-08 是補班日（週六上班）。讓原末日正好落在 2025-02-08 → 不順延。
    # 生效日 2025-01-09 → +30 = 2025-02-08
    out = tl.build_timeline(_fields("2025-01-09"))
    assert out["_parsed"]["appeal_deadline"] == dt.date(2025, 2, 8)


def test_deadline_explanation_present_and_mentions_rollover():
    out = tl.build_timeline(_fields("2026-10-02"))
    exp = out["deadline_explanation"]
    assert exp is not None
    assert "順延" in exp
    assert "民國115年11月2日" in exp


def test_deadline_explanation_none_when_no_service_date():
    out = tl.build_timeline(_fields(""))
    assert out["deadline_explanation"] is None
