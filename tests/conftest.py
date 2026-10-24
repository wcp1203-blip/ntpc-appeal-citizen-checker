"""pytest 共用設定。

把 repo 根目錄加入 sys.path，讓測試能以 `from core import ...` 匯入，
不依賴安裝為套件。並強制 dry-run，確保測試過程絕不呼叫真實 Bedrock/KB。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 這些純規則測試不碰 AWS，但仍設 dry-run 作雙重保險。
os.environ.setdefault("BEDROCK_DRY_RUN", "1")
