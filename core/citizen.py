"""民眾版核心邏輯：把民眾填的表單轉成自助檢查結果。[純規則，不呼叫 LLM / 不連 AWS]

設計原則（見 citizen-checker-plan.md §4）：
  - 規則優先：期限、瑕疵一律用確定性規則（timeline / defects 的純規則項），
    不交給會幻覺的模型。
  - 保守提醒：拿不準一律建議提早寄出、諮詢專業；絕不顯示「你還有時間」這類保證。
  - 可追溯：每個結果附計算說明與法條依據。
  - 不落地：本函式只吃 dict、吐 dict，不讀寫檔案、不記錄任何輸入。

這支模組刻意只依賴 core.timeline / core.defects 的純規則，不 import bedrock_client，
因此在未安裝 boto3 的民眾版環境可直接使用。
"""

from __future__ import annotations

import datetime as _dt

from . import timeline as _tl
from . import holidays as _hol
from . import defects as _defects


# 送達方式選項（對應計畫 §4 的 service_method 列舉）
SERVICE_PERSONAL = "本人收受"
SERVICE_AGENT = "家人／管理員代收"
SERVICE_DEPOSIT = "寄存送達（郵局／派出所）"
SERVICE_UNKNOWN = "不確定"

# urgency 門檻（天）
URGENT_DAYS = 7
SOON_DAYS = 14


# ---------------------------------------------------------------------------
# 表單 → 內部 fields（timeline / defects 契約）
# ---------------------------------------------------------------------------
def _form_to_fields(form: dict) -> dict:
    """把民眾表單（扁平 key）轉成 timeline/defects 用的巢狀 fields。

    送達方式對應到 timeline 的寄存判斷：只有「寄存送達」會 +10 日生效；
    「不確定」比照本人收受（最早可能日期，最保守），另在 warnings 提醒。
    """
    method_raw = (form.get("service_method") or "").strip()
    # timeline 以字串是否含「寄存」判斷；此處轉成內部一致用語
    if method_raw == SERVICE_DEPOSIT or "寄存" in method_raw:
        tl_method = "寄存送達"
    else:
        # 本人 / 代收 / 不確定：皆當日生效（不確定採最早可能日期，最保守）
        tl_method = "本人收受"

    legal_basis = form.get("legal_basis")
    if isinstance(legal_basis, str):
        legal_basis = [legal_basis] if legal_basis.strip() else []
    elif not isinstance(legal_basis, list):
        legal_basis = []

    od = {
        "agency": (form.get("agency") or "").strip(),
        "date": (form.get("disposition_date") or "").strip(),
        "doc_no": (form.get("doc_no") or "").strip(),
        "legal_basis": legal_basis,
        "service_date": (form.get("service_date") or "").strip(),
        "service_method": tl_method,
        "act_date": (form.get("act_date") or "").strip(),
        "penalty_amount": form.get("penalty_amount") or 0,
    }

    fields = {"original_disposition": od}

    # 已寄出訴願 → 帶入提起日，供程序逾期判斷參考
    already = form.get("already_filed")
    if isinstance(already, dict):
        filed = already.get("date") or already.get("filed_date")
        if filed:
            fields["petition_filed_date"] = str(filed).strip()
    elif isinstance(already, str) and already.strip():
        fields["petition_filed_date"] = already.strip()

    return fields


# ---------------------------------------------------------------------------
# 期限與急迫度
# ---------------------------------------------------------------------------
def _urgency(days_left: int | None) -> str:
    if days_left is None:
        return "unknown"
    if days_left < 0:
        return "overdue"
    if days_left <= URGENT_DAYS:
        return "urgent"
    if days_left <= SOON_DAYS:
        return "soon"
    return "ok"


def _days_between(today: _dt.date, deadline: _dt.date) -> int:
    """剩餘天數：期限末日當天仍可提起，故含末日（deadline - today）。"""
    return (deadline - today).days


# ---------------------------------------------------------------------------
# 瑕疵白話化（D 規則 → 民眾看得懂的說法）
# ---------------------------------------------------------------------------
# 一律用「可能」「建議確認」，不保證結果（計畫 §4.5）。
_FINDING_PLAIN = {
    "D1": {
        "title": "處分書記載事項可能不完備",
        "plain": ("處分書上似乎缺少應記載的事項（例如依據的法條）。"
                  "這可能是可以主張的瑕疵，建議對照處分書再次確認。"),
    },
    "D2": {
        "title": "可能已超過裁處期限（裁處權時效）",
        "plain": ("從違規行為日到作成處分的時間，可能已超過法律規定的裁處期限。"
                  "若屬實，這是重要的可主張事由，建議諮詢專業人士確認。"),
    },
    "D6": {
        "title": "送達日期可能不明確",
        "plain": ("處分書的送達日期不明確，會影響訴願期限的起算。"
                  "建議保留信封、掛號收據等可證明收到日期的資料。"),
    },
}

# 只對民眾說明這幾項較能自行理解、且不需要法律專業判斷的瑕疵。
# D3（累犯金額）、D4（從新從輕）、D5（前置程序）涉及較深的專業判斷，
# 保守起見不改寫成「可主張」字眼對民眾顯示，避免誤導。
_CITIZEN_FINDING_IDS = ("D1", "D2", "D6")


def _plain_findings(fields: dict, timeline: dict) -> list[dict]:
    """跑純規則 D1–D6，挑選可對民眾說明的項目並改寫成白話。"""
    findings: list[dict] = []
    for check in _defects.RULE_CHECKS:
        r = check(fields, timeline)
        if not r:
            continue
        cid = r.get("id")
        if cid not in _CITIZEN_FINDING_IDS:
            continue
        plain = _FINDING_PLAIN.get(cid, {})
        findings.append({
            "id": cid,
            "level": r.get("level"),            # red / amber（僅供內部排序，不對民眾講「紅燈」）
            "title": plain.get("title", r.get("title", "")),
            "plain": plain.get("plain", ""),
            "basis": r.get("basis", ""),
            "evidence": r.get("evidence", ""),
        })
    # 重大的（red）排前面
    findings.sort(key=lambda f: 0 if f.get("level") == "red" else 1)
    return findings


# ---------------------------------------------------------------------------
# 主函式
# ---------------------------------------------------------------------------
def check_case(form: dict, today: _dt.date | None = None) -> dict:
    """把民眾填的表單轉成檢查結果（見 citizen-checker-plan.md §4）。

    參數：
        form   民眾表單（欄位見計畫 §4，全部選填）
        today  今天日期（預設系統今日；測試可注入固定日期）

    回傳 dict：deadline / urgency / findings / next_steps / warnings。
    """
    form = form or {}
    today = today or _dt.date.today()

    fields = _form_to_fields(form)
    timeline = _tl.build_timeline(fields)
    parsed = timeline["_parsed"]

    warnings: list[str] = []
    next_steps: list[str] = []

    service_method_raw = (form.get("service_method") or "").strip()
    has_remedy_notice = form.get("has_remedy_notice")

    # --- 送達方式不確定：用最早可能日期（本人收受）計算，並提醒（§4.2）---
    if service_method_raw == SERVICE_UNKNOWN or not service_method_raw:
        if parsed.get("service_date") is not None:
            warnings.append(
                "您未確定送達方式，本試算以「最早可能生效日」（當天收受）計算期限，"
                "屬最保守估計。若實際為寄存送達，生效日會往後 10 日、期限也會順延；"
                "請以實際情形為準。"
            )

    # --- 日期無法解析提醒 ---
    if (form.get("service_date") or "").strip() and parsed.get("service_date") is None:
        warnings.append("您輸入的「收到（送達）日期」無法辨識，請確認格式（例如 115/10/02 或 民國115年10月2日）。")
    if (form.get("act_date") or "").strip() and parsed.get("act_date") is None:
        warnings.append("您輸入的「違規行為日期」無法辨識，請確認格式。")

    # --- 期限計算 ---
    deadline_date = parsed.get("appeal_deadline")
    deadline_info = _build_deadline_info(
        parsed, timeline, today, has_remedy_notice, warnings)

    days_left = None
    if deadline_date is not None:
        days_left = _days_between(today, deadline_date)
    urgency = _urgency(days_left)

    # --- 日曆不完整提醒 ---
    if deadline_date is not None and not _hol.calendar_complete(deadline_date):
        warnings.append(
            "期限末日所在年份不在內建假日曆涵蓋範圍，順延僅以週末估算，"
            "未計入國定假日；請自行確認國定假日並提早寄出。"
        )

    # --- 瑕疵檢查（白話） ---
    findings = _plain_findings(fields, timeline)

    # --- 下一步待辦 ---
    next_steps = _build_next_steps(form, fields, parsed, urgency, deadline_info, findings)

    return {
        "deadline": deadline_info,
        "urgency": urgency,
        "days_left": days_left,
        "findings": findings,
        "next_steps": next_steps,
        "warnings": warnings,
    }


def _build_deadline_info(parsed: dict, timeline: dict, today: _dt.date,
                         has_remedy_notice, warnings: list[str]) -> dict:
    """組出期限資訊 dict，含 30 天期限、計算說明、法條依據。

    無救濟教示（§4.3）：依行政程序法§98 III 期間可延長為一年，
    但同時顯示 30 天期限並建議以 30 天為準，避免民眾誤解而錯過。
    """
    deadline_date = parsed.get("appeal_deadline")
    info: dict = {
        "deadline_roc": _tl.format_roc(deadline_date),
        "deadline_iso": deadline_date.isoformat() if deadline_date else None,
        "explanation": timeline.get("deadline_explanation"),
        "basis": "訴願法第14條第1項（自處分達到之次日起30日內）、第47條第3項（寄存送達經10日生效）",
        "extended_one_year": None,
    }

    # 無救濟教示 → 行政程序法§98 III
    if has_remedy_notice is False:
        service_eff = parsed.get("service_effective_date")
        one_year_date = None
        if service_eff is not None:
            # 自送達後 1 年，末日逢例假順延（與訴願期限一致的順延規則）
            one_year_date = _tl.next_business_day(_one_year_later(service_eff))
        info["extended_one_year"] = {
            "deadline_roc": _tl.format_roc(one_year_date),
            "deadline_iso": one_year_date.isoformat() if one_year_date else None,
            "basis": "行政程序法第98條第3項（未告知救濟期間，自處分書送達後1年內聲明不服，視為於法定期間內提起）",
            "note": ("處分書若未記載救濟教示，提起期間可能延長為一年。"
                     "但為避免受理機關認定不同而錯過，強烈建議仍以 30 天為準、儘早寄出。"),
        }
        warnings.append(
            "您表示處分書沒有寫救濟教示（不服可於幾日內提起訴願）。"
            "依行政程序法§98 III 期間可能延長為一年，但認定存在風險，"
            "務必以 30 天期限為準並提早寄出。"
        )

    return info


def _one_year_later(d: _dt.date) -> _dt.date:
    """送達生效日 1 年後（供無救濟教示的延長期間顯示）。2/29 比照 timeline 規則。"""
    return _tl._add_years(d, 1)


def _build_next_steps(form: dict, fields: dict, parsed: dict, urgency: str,
                      deadline_info: dict, findings: list[dict]) -> list[str]:
    """依情況產生待辦清單。"""
    steps: list[str] = []

    already = form.get("already_filed")
    already_filed = bool(
        (isinstance(already, dict) and (already.get("date") or already.get("filed_date")))
        or (isinstance(already, str) and already.strip())
    )

    if urgency == "overdue":
        steps.append(
            "試算結果顯示可能已超過 30 天的訴願期限。是否真的逾期仍以受理機關認定為準，"
            "建議立即諮詢各地方政府法律諮詢或法律扶助基金會，確認是否仍有救濟途徑。"
        )
    elif urgency in ("urgent", "soon"):
        steps.append("期限即將屆至，請盡快備妥訴願書並以掛號寄出，不要拖到最後一天。")

    if not already_filed:
        steps.append(
            "撰寫訴願書：寫明訴願人、原處分機關、不服的處分、訴願請求與理由，連同處分書影本一併提出。"
        )
        # §14 III：以機關收到日為準（§4.4）
        steps.append(
            "訴願書是以「受理機關實際收到的日期」為準，不是郵戳日期（訴願法§14 III）。"
            "請務必用掛號並提早寄出，保留收據。"
        )
        agency = fields["original_disposition"].get("agency")
        if agency:
            steps.append(
                f"訴願書應向原處分機關（{agency}）或其上級機關提出；"
                "實際受理機關與地址請以處分書上的教示或機關公告為準。"
            )
        else:
            steps.append(
                "訴願書應向原處分機關或其上級機關提出，實際受理機關與地址請以處分書記載為準。"
            )
    else:
        steps.append(
            "您已寄出訴願書。建議確認受理機關已於期限內收到（可查詢掛號送達紀錄），並留存寄件收據。"
        )

    if findings:
        steps.append(
            "本工具發現處分書可能有可主張的瑕疵（詳見上方檢查結果），"
            "建議在訴願理由中一併提出，並自行確認是否適用。"
        )

    steps.append(
        "如有疑問，可洽各地方政府提供的免費法律諮詢，或財團法人法律扶助基金會。"
    )
    return steps
