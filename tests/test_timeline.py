"""core/timeline.py 的純規則測試（不呼叫 LLM）。

涵蓋：民國／西元日期解析、寄存送達 +10 日生效、訴願期間末日逢週末順延、
裁處權時效 3 年、以及 build_timeline 的整合輸出。
"""
from __future__ import annotations

import datetime as dt

import pytest

from core import timeline as tl


# ---------- parse_date ----------
@pytest.mark.parametrize(
    "value,expected",
    [
        ("民國114年3月5日", dt.date(2025, 3, 5)),
        ("114.3.5", dt.date(2025, 3, 5)),
        ("114/03/05", dt.date(2025, 3, 5)),
        ("2025-03-05", dt.date(2025, 3, 5)),
        ("2025年3月5日", dt.date(2025, 3, 5)),
    ],
)
def test_parse_date_variants(value, expected):
    assert tl.parse_date(value) == expected


def test_parse_date_passthrough_date_and_datetime():
    d = dt.date(2024, 1, 2)
    assert tl.parse_date(d) == d
    assert tl.parse_date(dt.datetime(2024, 1, 2, 10, 30)) == d


@pytest.mark.parametrize("value", [None, "", "不是日期", "2025-13-99"])
def test_parse_date_invalid_returns_none(value):
    assert tl.parse_date(value) is None


def test_format_roc_roundtrip():
    assert tl.format_roc(dt.date(2025, 3, 5)) == "民國114年3月5日"
    assert tl.format_roc(None) is None


# ---------- 送達生效日 ----------
def test_service_effective_deposit_adds_10_days():
    # 寄存送達：自寄存日起經 10 日生效
    out = tl.compute_service_effective_date("民國114年3月1日", "寄存送達")
    assert out == tl.format_roc(dt.date(2025, 3, 11))


def test_service_effective_personal_same_day():
    out = tl.compute_service_effective_date("民國114年3月1日", "本人收受")
    assert out == tl.format_roc(dt.date(2025, 3, 1))


# ---------- 期間計算 ----------
def test_next_business_day_skips_weekend():
    # 2025-03-08 是週六 → 應順延到 2025-03-10 週一
    assert tl.next_business_day(dt.date(2025, 3, 8)) == dt.date(2025, 3, 10)
    # 平日不動
    assert tl.next_business_day(dt.date(2025, 3, 10)) == dt.date(2025, 3, 10)


def test_add_days_from_next_day_rolls_over_holiday():
    # 起算 2025-03-05 + 30 日 = 2025-04-04，但該日為兒童節及民族掃墓節（國定假日），
    # 04-05/06 為週末 → 順延至 2025-04-07（週一）。
    # （導入國定假日表前此處原為 04-04；現以日曆為準。）
    assert tl.add_days_from_next_day(dt.date(2025, 3, 5), 30) == dt.date(2025, 4, 7)


# ---------- build_timeline 整合 ----------
def _fields(**over):
    base = {
        "original_disposition": {
            "act_date": "民國114年1月1日",
            "date": "民國114年2月1日",
            "service_date": "民國114年3月1日",
            "service_method": "本人收受",
        },
        "petition_filed_date": "民國114年3月10日",
    }
    base["original_disposition"].update(over.get("original_disposition", {}))
    for k, v in over.items():
        if k != "original_disposition":
            base[k] = v
    return base


def test_build_timeline_core_fields():
    out = tl.build_timeline(_fields())
    parsed = out["_parsed"]
    assert parsed["act_date"] == dt.date(2025, 1, 1)
    assert parsed["service_date"] == dt.date(2025, 3, 1)
    # 本人收受 → 生效日即送達日
    assert parsed["service_effective_date"] == dt.date(2025, 3, 1)
    # 訴願期間末日 = 生效日 + 30，逢假順延
    assert parsed["appeal_deadline"] == tl.add_days_from_next_day(dt.date(2025, 3, 1), 30)
    # 裁處權時效 = 行為日 + 3 年
    assert parsed["penalty_limitation_date"] == dt.date(2028, 1, 1)


def test_build_timeline_deposit_service_shifts_deadline():
    out = tl.build_timeline(_fields(original_disposition={"service_method": "寄存送達"}))
    parsed = out["_parsed"]
    # 寄存 → 生效日 = 送達日 + 10
    assert parsed["service_effective_date"] == dt.date(2025, 3, 11)


def test_penalty_limitation_leap_day_act_date():
    # 任務 2.1：行為日 2024-02-29（閏日），+3 年 = 2027 非閏年。
    # 依民法§121 II，無相當日時以該月末日（2/28）為末日，不可回傳 None。
    out = tl.build_timeline(_fields(original_disposition={"act_date": "2024-02-29"}))
    assert out["_parsed"]["penalty_limitation_date"] == dt.date(2027, 2, 28)


def test_penalty_limitation_leap_day_to_leap_year():
    # 行為日 2020-02-29 + 3 年 = 2023（非閏年）→ 2/28
    out = tl.build_timeline(_fields(original_disposition={"act_date": "2020-02-29"}))
    assert out["_parsed"]["penalty_limitation_date"] == dt.date(2023, 2, 28)


def test_add_years_normal_date():
    assert tl._add_years(dt.date(2025, 1, 1), 3) == dt.date(2028, 1, 1)
    # 閏年對閏年（+4 年剛好落在閏年）→ 維持 2/29
    assert tl._add_years(dt.date(2024, 2, 29), 4) == dt.date(2028, 2, 29)


def test_build_timeline_handles_missing_dates():
    out = tl.build_timeline({"original_disposition": {}})
    parsed = out["_parsed"]
    assert parsed["service_effective_date"] is None
    assert parsed["appeal_deadline"] is None
    assert parsed["penalty_limitation_date"] is None
