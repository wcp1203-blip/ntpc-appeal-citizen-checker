"""core/citizen.py 的民眾版核心邏輯純規則測試（不呼叫 LLM / 不連 AWS）。

涵蓋計畫任務 4.6：每種 urgency、已逾期、送達方式不確定、沒有救濟教示、欄位全空。
所有期限均以 build_timeline 為準，不另算一套。今天日期以參數注入，確保可重現。
"""
from __future__ import annotations

import datetime as dt

from core import citizen


# 固定一組基準表單：本人收受、送達 2026-10-02 → 期限 2026-11-02（週日順延後）
def _form(**over):
    base = {
        "agency": "新北市政府交通事件裁決處",
        "doc_no": "北監裁字第1140000001號",
        "disposition_date": "2026-09-28",
        "service_date": "2026-10-02",
        "service_method": citizen.SERVICE_PERSONAL,
        "act_date": "2026-08-01",
        "legal_basis": "道路交通管理處罰條例第56條",
        "penalty_amount": 900,
        "has_remedy_notice": True,
    }
    base.update(over)
    return base


# ---------- urgency 各級 ----------
def test_urgency_ok():
    # 期限 2026-11-02，今天 2026-10-02 → 約 31 天 → ok
    out = citizen.check_case(_form(), today=dt.date(2026, 10, 2))
    assert out["urgency"] == "ok"
    assert out["days_left"] == (dt.date(2026, 11, 2) - dt.date(2026, 10, 2)).days
    assert out["deadline"]["deadline_roc"] == "民國115年11月2日"


def test_urgency_soon():
    # 今天 2026-10-22 → 剩 11 天 → soon（<=14）
    out = citizen.check_case(_form(), today=dt.date(2026, 10, 22))
    assert out["urgency"] == "soon"


def test_urgency_urgent():
    # 今天 2026-10-28 → 剩 5 天 → urgent（<=7）
    out = citizen.check_case(_form(), today=dt.date(2026, 10, 28))
    assert out["urgency"] == "urgent"


def test_urgency_overdue():
    # 今天 2026-11-10 → 期限 11-02 已過 → overdue
    out = citizen.check_case(_form(), today=dt.date(2026, 11, 10))
    assert out["urgency"] == "overdue"
    assert out["days_left"] < 0
    # 逾期時 next_steps 要有「諮詢」字樣，且不得出現「你還有時間」這類保證
    joined = "".join(out["next_steps"])
    assert "諮詢" in joined


def test_urgency_unknown_when_no_service_date():
    out = citizen.check_case(_form(service_date=""), today=dt.date(2026, 10, 2))
    assert out["urgency"] == "unknown"
    assert out["days_left"] is None
    assert out["deadline"]["deadline_roc"] is None


# ---------- 送達方式不確定（§4.2）----------
def test_uncertain_service_method_uses_earliest_and_warns():
    out = citizen.check_case(
        _form(service_method=citizen.SERVICE_UNKNOWN), today=dt.date(2026, 10, 2))
    # 比照本人收受（當日生效）→ 期限仍 2026-11-02
    assert out["deadline"]["deadline_roc"] == "民國115年11月2日"
    assert any("最早可能" in w for w in out["warnings"])


def test_deposit_service_shifts_deadline():
    # 寄存送達 2026-09-01 → 生效 2026-09-11 → 期限 2026-10-12
    out = citizen.check_case(
        _form(service_date="2026-09-01", service_method=citizen.SERVICE_DEPOSIT),
        today=dt.date(2026, 9, 11))
    assert out["deadline"]["deadline_roc"] == "民國115年10月12日"


# ---------- 無救濟教示（§4.3）----------
def test_no_remedy_notice_shows_one_year_but_recommends_30_days():
    out = citizen.check_case(
        _form(has_remedy_notice=False), today=dt.date(2026, 10, 2))
    dl = out["deadline"]
    # 仍顯示 30 天期限
    assert dl["deadline_roc"] == "民國115年11月2日"
    # 另顯示一年延長期限
    assert dl["extended_one_year"] is not None
    assert dl["extended_one_year"]["deadline_roc"] is not None
    # 警告要提醒以 30 天為準
    assert any("30 天" in w for w in out["warnings"])


# ---------- 瑕疵白話化（§4.5）----------
def test_missing_legal_basis_triggers_d1_finding_in_plain_language():
    out = citizen.check_case(
        _form(legal_basis=""), today=dt.date(2026, 10, 2))
    ids = {f["id"] for f in out["findings"]}
    assert "D1" in ids
    d1 = next(f for f in out["findings"] if f["id"] == "D1")
    # 白話、用「可能」而非保證
    assert "可能" in d1["plain"]
    assert "紅燈" not in d1["plain"]


# ---------- §14 III 郵戳提醒 ----------
def test_next_steps_mentions_received_date_rule():
    out = citizen.check_case(_form(), today=dt.date(2026, 10, 2))
    joined = "".join(out["next_steps"])
    assert "收到的日期" in joined or "收到日" in joined
    assert "掛號" in joined


# ---------- 已寄出訴願 ----------
def test_already_filed_changes_next_steps():
    out = citizen.check_case(
        _form(already_filed={"date": "2026-10-20"}), today=dt.date(2026, 10, 25))
    joined = "".join(out["next_steps"])
    assert "已寄出" in joined


# ---------- 欄位全空 ----------
def test_empty_form_is_safe():
    out = citizen.check_case({}, today=dt.date(2026, 10, 2))
    assert out["urgency"] == "unknown"
    assert out["days_left"] is None
    assert out["deadline"]["deadline_roc"] is None
    assert isinstance(out["findings"], list)
    assert isinstance(out["next_steps"], list)
    assert isinstance(out["warnings"], list)


def test_check_case_none_form():
    out = citizen.check_case(None, today=dt.date(2026, 10, 2))
    assert out["urgency"] == "unknown"


# ---------- 不解析的日期 ----------
def test_unparseable_service_date_warns():
    out = citizen.check_case(_form(service_date="亂寫的日期"), today=dt.date(2026, 10, 2))
    assert any("無法辨識" in w for w in out["warnings"])
    assert out["urgency"] == "unknown"
