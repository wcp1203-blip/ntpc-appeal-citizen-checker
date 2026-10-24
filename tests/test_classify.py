"""core/classify.py 的純規則關鍵字分類測試（不呼叫 LLM）。"""
from __future__ import annotations

import pytest

from core import classify


@pytest.mark.parametrize(
    "text,expected",
    [
        ("本件涉及洗錢防制法，交付帳戶遭書面告誡", "洗錢防制法"),
        ("違反廢棄物清理法，隨意棄置菸蒂", "廢棄物清理法"),
        ("噪音管制法，音量超過分貝標準", "噪音管制法"),
        ("空氣污染防制法，固定污染源排放標準", "空氣污染防制法"),
        ("違章建築，未依建築法申報公安", "建築法"),
    ],
)
def test_classify_hits_expected_case_type(text, expected):
    out = classify.classify_case_type({"body": text})
    assert out["case_type"] == expected
    assert 0.0 < out["confidence"] <= 1.0


def test_classify_no_match_returns_other():
    out = classify.classify_case_type({"body": "與任何案由關鍵字無關的普通文字"})
    assert out["case_type"] == "其他"
    assert out["confidence"] == 0.0


def test_classify_confidence_capped_at_one():
    # 塞入大量關鍵字，confidence 不得超過 1.0
    text = "洗錢防制法 洗錢 人頭帳戶 交付帳戶 書面告誡 警示帳戶"
    out = classify.classify_case_type({"body": text})
    assert out["case_type"] == "洗錢防制法"
    assert out["confidence"] == 1.0


def test_classify_full_law_name_outweighs_scattered_keywords():
    # 命中法規全名應勝過只命中零星通用字
    text = "空氣污染防制法的案件，另提及一個廢棄物字樣"
    out = classify.classify_case_type({"body": text})
    assert out["case_type"] == "空氣污染防制法"
