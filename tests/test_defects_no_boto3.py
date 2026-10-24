"""驗證 core/defects.py 的 D1–D6 規則不依賴 boto3（任務 3.2）。

民眾版部署環境不會安裝 boto3（見 requirements-citizen.txt）。本測試以
「攔截 boto3 import」模擬無 boto3 的乾淨環境，確認：
  1. 能成功 import core.defects 與 RULE_CHECKS
  2. 每條規則 rule_d1–d6 都能被呼叫、回傳 None 或合法 CheckResult dict

注意：這裡刻意不呼叫 health_check()（它才會延遲 import bedrock_client/boto3）。
民眾版只用 RULE_CHECKS 裡的純規則。
"""
from __future__ import annotations

import builtins
import importlib
import sys

import pytest

from core import timeline as tl


@pytest.fixture
def no_boto3(monkeypatch):
    """讓 `import boto3`（及 botocore）失敗，並清掉已載入的相關模組快取。"""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "boto3" or name.startswith("boto3.") \
                or name == "botocore" or name.startswith("botocore."):
            raise ImportError(f"模擬無 {name} 環境")
        return real_import(name, *args, **kwargs)

    # 移除可能已匯入的 AWS 模組與 bedrock_client，確保重新 import 時走 fake_import
    for mod in list(sys.modules):
        if mod == "boto3" or mod.startswith("boto3.") \
                or mod == "botocore" or mod.startswith("botocore.") \
                or mod == "core.bedrock_client":
            monkeypatch.delitem(sys.modules, mod, raising=False)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    yield


def _sample_fields():
    return {
        "original_disposition": {
            "agency": "新北市政府環境保護局",
            "date": "民國114年2月1日",
            "doc_no": "北環稽字第1140000001號",
            "legal_basis": [],                       # 故意缺法令依據 → D1 紅燈
            "act_date": "民國114年1月1日",
            "service_date": "民國114年3月1日",
            "service_method": "本人收受",
            "penalty_amount": 6000,
            "violation_count": 3,                    # D3 提示
            "requires_prior_order": True,
            "prior_order_done": False,               # D5 紅燈
        },
    }


def test_defects_importable_without_boto3(no_boto3):
    # 確認無 boto3 時 import core.defects 不會爆
    defects = importlib.reload(importlib.import_module("core.defects"))
    assert hasattr(defects, "RULE_CHECKS")
    assert len(defects.RULE_CHECKS) == 6


def test_rule_checks_run_without_boto3(no_boto3):
    defects = importlib.reload(importlib.import_module("core.defects"))
    fields = _sample_fields()
    timeline = tl.build_timeline(fields)

    results = []
    for check in defects.RULE_CHECKS:
        r = check(fields, timeline)
        # 每條規則要嘛回 None，要嘛回合法的 CheckResult dict
        if r is not None:
            assert isinstance(r, dict)
            assert {"id", "level", "title"} <= set(r)
            results.append(r)

    ids = {r["id"] for r in results}
    # D1（缺法令依據，紅燈）與 D5（未完成前置程序）至少要觸發
    assert "D1" in ids
    assert "D5" in ids


def test_boto3_truly_blocked(no_boto3):
    # 驗證測試夾具確實讓 boto3 不可用（避免假綠燈）
    with pytest.raises(ImportError):
        importlib.import_module("boto3")


@pytest.fixture(autouse=True)
def _restore_defects():
    """測試後把 core.defects / bedrock_client 還原成正常（有 boto3）狀態，
    避免污染其他測試。"""
    yield
    for mod in ("core.defects", "core.bedrock_client"):
        sys.modules.pop(mod, None)
    importlib.import_module("core.defects")
