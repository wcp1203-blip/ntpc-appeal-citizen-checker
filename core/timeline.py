"""案件時間軸引擎（亮點 B，§6）。[純規則，不呼叫 LLM]

一條時間軸同時支援：程序期間、裁處權時效、行為時法比對、教示版本。
確定性計算全部在此，不消耗 Bedrock 配額。

日期一律以西元 date 內部運算，對外欄位保留原字串來源可追溯。
支援民國年（「民國114年3月5日」/「114.3.5」/「114/03/05」）與西元（「2025-03-05」）。
"""

from __future__ import annotations

import datetime as _dt
import re

from . import holidays as _hol

# 訴願法期間（日）
APPEAL_PERIOD_DAYS = 30          # §14：自處分達到次日起 30 日內提起
DEPOSIT_SERVICE_EFFECTIVE_DAYS = 10  # §47 III：寄存送達自寄存之日起經 10 日生效
PENALTY_LIMITATION_YEARS = 3     # 行政罰法§27：裁處權時效 3 年


# ---------- 日期解析 ----------
_ROC_RE = re.compile(r"(?:民國)?\s*(\d{2,3})\s*[年./\-]\s*(\d{1,2})\s*[月./\-]\s*(\d{1,2})\s*日?")
_AD_RE = re.compile(r"(\d{4})\s*[年./\-]\s*(\d{1,2})\s*[月./\-]\s*(\d{1,2})\s*日?")


def parse_date(value) -> _dt.date | None:
    """把民國/西元日期字串解析成 date。無法解析回 None。

    規則：4 位數起始年視為西元；2–3 位數視為民國（+1911）。
    已是 date/datetime 直接回傳。
    """
    if value is None or value == "":
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    s = str(value).strip()

    m = _AD_RE.search(s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return _safe_date(y, mo, d)

    m = _ROC_RE.search(s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return _safe_date(y + 1911, mo, d)
    return None


def _safe_date(y: int, mo: int, d: int) -> _dt.date | None:
    try:
        return _dt.date(y, mo, d)
    except ValueError:
        return None


def _last_day_of_month(y: int, mo: int) -> int:
    """回傳某年某月的最後一天（處理 2 月閏年）。"""
    if mo == 12:
        nxt = _dt.date(y + 1, 1, 1)
    else:
        nxt = _dt.date(y, mo + 1, 1)
    return (nxt - _dt.timedelta(days=1)).day


def _add_years(d: _dt.date, years: int) -> _dt.date:
    """日期加上 N 年。

    依民法§121 II：期間以年定者，無相當日時以最後之日為期間末日。
    故行為日為 2/29、N 年後該年非閏年時，回傳 2/28（該月末日），而非 None。
    """
    y = d.year + years
    day = d.day
    if d.month == 2 and d.day == 29:
        day = min(d.day, _last_day_of_month(y, 2))  # 非閏年 → 28
    return _dt.date(y, d.month, day)


def format_roc(d: _dt.date | None) -> str | None:
    """date → 民國年字串（供顯示/追溯）。"""
    if d is None:
        return None
    return f"民國{d.year - 1911}年{d.month}月{d.day}日"


# ---------- 期間計算 ----------
def _is_weekend(d: _dt.date) -> bool:
    return d.weekday() >= 5   # 5=六 6=日


def next_business_day(d: _dt.date) -> _dt.date:
    """末日為例假日者順延至次一非例假日（行政程序法§48 IV）。

    以 holidays.is_non_business_day 判定，認得國定假日、彈性放假與補班日
    （補班日視為上班，不順延）。日曆未涵蓋的年份退回只判斷週末。
    """
    while _hol.is_non_business_day(d):
        d += _dt.timedelta(days=1)
    return d


def add_days_from_next_day(start: _dt.date, days: int) -> _dt.date:
    """自起算日之「次日」起算 N 日的末日，末日逢例假順延。

    例：處分達到日為起算日，訴願期間自次日起 30 日 → start + 30，逢假順延。
    """
    end = start + _dt.timedelta(days=days)
    return next_business_day(end)


def _deadline_explanation(service: _dt.date | None,
                          service_effective: _dt.date | None,
                          method: str | None,
                          deadline: _dt.date | None) -> str | None:
    """產生訴願期限的計算過程說明（供民眾/承辦人追溯，呼應「可追溯」原則）。

    範例：「送達日 民國115年10月2日 → 次日起算 30 日原為 民國115年11月1日（週日），
    順延至 民國115年11月2日（星期一）。」
    """
    if service is None or service_effective is None or deadline is None:
        return None

    parts: list[str] = []
    if method and "寄存" in str(method):
        parts.append(
            f"寄存送達日 {format_roc(service)}，自寄存日起經 "
            f"{DEPOSIT_SERVICE_EFFECTIVE_DAYS} 日於 {format_roc(service_effective)} 生效"
        )
    else:
        parts.append(f"送達生效日 {format_roc(service_effective)}")

    raw_end = service_effective + _dt.timedelta(days=APPEAL_PERIOD_DAYS)
    parts.append(f"自次日起算 {APPEAL_PERIOD_DAYS} 日，原末日為 {format_roc(raw_end)}")

    if deadline != raw_end:
        # 找出原末日為何順延：列出被跳過日子的原因
        skipped = _skipped_days_reason(raw_end, deadline)
        if skipped:
            parts.append(f"因{skipped}，順延至 {format_roc(deadline)}（{_weekday_cn(deadline)}）")
        else:
            parts.append(f"順延至 {format_roc(deadline)}（{_weekday_cn(deadline)}）")
    else:
        parts.append(f"末日 {format_roc(deadline)}（{_weekday_cn(deadline)}）為上班日，不順延")

    return "；".join(parts) + "。"


_WEEKDAY_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def _weekday_cn(d: _dt.date) -> str:
    return _WEEKDAY_CN[d.weekday()]


def _skipped_days_reason(raw_end: _dt.date, deadline: _dt.date) -> str | None:
    """描述 raw_end 到 deadline 之間被跳過的放假日原因（供說明文字）。"""
    reasons: list[str] = []
    cur = raw_end
    while cur < deadline:
        if _hol.is_non_business_day(cur):
            name = _hol.describe_day(cur)
            if name:
                reasons.append(f"{format_roc(cur)} 為{name}")
            elif _is_weekend(cur):
                reasons.append(f"{format_roc(cur)} 為{_weekday_cn(cur)}")
            else:
                reasons.append(f"{format_roc(cur)} 為放假日")
        cur += _dt.timedelta(days=1)
    return "、".join(reasons) if reasons else None


def compute_service_effective_date(service_date, method: str | None) -> str | None:
    """送達生效日。

    - 寄存送達（method 含「寄存」）：自寄存之日起經 10 日發生效力（訴願法§47 III）。
    - 本人/補充/其他：當日生效。
    回傳民國年字串（與其他欄位一致），無法解析回 None。
    """
    d = parse_date(service_date)
    if d is None:
        return None
    if method and "寄存" in str(method):
        eff = d + _dt.timedelta(days=DEPOSIT_SERVICE_EFFECTIVE_DAYS)
    else:
        eff = d
    return format_roc(eff)


# ---------- 建立時間軸 ----------
def build_timeline(fields: dict) -> dict:
    """由擷取欄位建立時間軸 dict。

    含：各關鍵日期（解析後的 date 與原字串）、送達生效日、訴願期間末日、
    裁處權時效末日，供 procedure（§77 逾期判定）與 defects（時效健檢）使用。
    不呼叫 LLM。
    """
    od = fields.get("original_disposition", {}) or {}
    service_method = od.get("service_method") or fields.get("service_method")

    act = parse_date(od.get("act_date"))                    # 違規行為日
    disposition = parse_date(od.get("date"))                # 處分作成日
    service = parse_date(od.get("service_date"))            # 處分送達日
    filed = parse_date(fields.get("petition_filed_date"))   # 提起訴願日

    # 送達生效日（寄存 +10 日）
    service_effective = None
    if service is not None:
        service_effective = service + _dt.timedelta(days=DEPOSIT_SERVICE_EFFECTIVE_DAYS) \
            if service_method and "寄存" in str(service_method) else service

    # 訴願期間末日：自送達生效日之次日起 30 日，逢例假順延
    appeal_deadline = None
    if service_effective is not None:
        appeal_deadline = add_days_from_next_day(service_effective, APPEAL_PERIOD_DAYS)

    # 裁處權時效末日：自違規行為終了日起 3 年（行政罰法§27）
    penalty_limitation = None
    if act is not None:
        penalty_limitation = _add_years(act, PENALTY_LIMITATION_YEARS)

    # 期限計算過程說明（供追溯顯示）
    deadline_explanation = _deadline_explanation(
        service, service_effective, service_method, appeal_deadline)

    return {
        # 原始/解析後日期（date 物件供計算，字串供顯示追溯）
        "act_date": od.get("act_date"),
        "disposition_date": od.get("date"),
        "service_date": od.get("service_date"),
        "filed_date": fields.get("petition_filed_date"),
        "decision_date": None,
        "service_method": service_method,
        "prior_dispositions": od.get("prior_dispositions", []),
        # 解析後（None 表示原欄位缺漏或格式無法辨識）
        "_parsed": {
            "act_date": act,
            "disposition_date": disposition,
            "service_date": service,
            "service_effective_date": service_effective,
            "filed_date": filed,
            "appeal_deadline": appeal_deadline,
            "penalty_limitation_date": penalty_limitation,
        },
        # 顯示用（民國年字串）
        "service_effective_date": format_roc(service_effective),
        "appeal_deadline": format_roc(appeal_deadline),
        "penalty_limitation_date": format_roc(penalty_limitation),
        "deadline_explanation": deadline_explanation,
    }
