"""core/procedure.py 的程序審查（§77）純規則測試（不呼叫 LLM）。"""
from __future__ import annotations

from core import procedure
from core import timeline as tl


def _timeline(service_method="本人收受",
              service_date="民國114年3月1日",
              filed_date="民國114年3月10日",
              act_date="民國114年1月1日"):
    fields = {
        "original_disposition": {
            "act_date": act_date,
            "date": "民國114年2月1日",
            "service_date": service_date,
            "service_method": service_method,
        },
        "petition_filed_date": filed_date,
    }
    return tl.build_timeline(fields), fields


def test_within_period_is_admissible():
    timeline, fields = _timeline(filed_date="民國114年3月10日")
    out = procedure.procedure_check(timeline, fields)
    assert out["is_inadmissible"] is False
    assert out["clause"] is None


def test_overdue_triggers_77_2():
    # 生效日 3/1 + 30 = 3/31（週一），提起日 5/1 明顯逾期
    timeline, fields = _timeline(filed_date="民國114年5月1日")
    out = procedure.procedure_check(timeline, fields)
    assert out["is_inadmissible"] is True
    assert out["clause"] == procedure.CLAUSE_OVERDUE
    assert out["computed_dates"]["overdue_days"] > 0


def test_revoked_disposition_triggers_77_6():
    timeline, fields = _timeline()
    fields["original_disposition"]["revoked"] = True
    out = procedure.procedure_check(timeline, fields)
    assert out["is_inadmissible"] is True
    assert out["clause"] == procedure.CLAUSE_NO_DISPOSITION


def test_previously_decided_triggers_77_7():
    timeline, fields = _timeline()
    fields["previously_decided"] = "是"
    out = procedure.procedure_check(timeline, fields)
    assert out["is_inadmissible"] is True
    assert out["clause"] == procedure.CLAUSE_DUPLICATE


def test_missing_dates_defaults_admissible():
    # 缺送達/提起日 → 無法判逾期，保守放行
    timeline = tl.build_timeline({"original_disposition": {}})
    out = procedure.procedure_check(timeline, {})
    assert out["is_inadmissible"] is False


def test_truthy_helper():
    assert procedure._truthy(True) is True
    assert procedure._truthy("是") is True
    assert procedure._truthy("已撤銷") is True
    assert procedure._truthy("false") is False
    assert procedure._truthy(None) is False
    assert procedure._truthy("") is False
