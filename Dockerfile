# ============================================================================
# 訴願審理 AI 輔助工作台 — Streamlit 單體應用容器映像
#
# 多階段 build：
#   builder 階段把相依套件裝進 venv，runtime 階段只複製 venv 與原始碼，
#   讓最終 image 不帶編譯工具鏈，體積較小、受攻擊面較小。
#
# 執行環境以非 root 使用者啟動，符合容器最小權限原則。
# 不內嵌任何 AWS 憑證：執行時由環境變數或掛載的 credential chain 提供。
# ============================================================================

# ---------- 第一階段：依賴建置 ----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# 先只複製 requirements，利用 Docker layer cache：相依沒變就不重裝
COPY requirements.txt .

# 建一個獨立 venv，方便整包複製到 runtime 階段
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ---------- 第二階段：執行環境 ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Streamlit：headless、固定埠、監聽所有介面（容器內需對外）
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    # 預設以離線 dry-run 啟動，避免未設定 AWS 時誤打真實 Bedrock；
    # 正式 Demo 由 compose / K8s 覆寫為 0。
    BEDROCK_DRY_RUN=1

# 從 builder 複製已裝好的 venv
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# 建立非 root 使用者執行（最小權限）
RUN useradd --create-home --uid 10001 appuser

# 複製應用原始碼（.dockerignore 已排除機密、資料與版控檔）
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8501

# 容器健康檢查：打 Streamlit 內建健康端點
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=3).status==200 else 1)"

ENTRYPOINT ["streamlit", "run", "app/streamlit_app.py"]
