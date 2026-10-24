# 民眾版部署指南（Streamlit Community Cloud）

民眾版 `app/citizen_app.py` 第一階段**不連 AWS、不需 `boto3`**，最適合用免費的
[Streamlit Community Cloud](https://streamlit.io/cloud) 部署。

## 一、前置

1. 把本 repo 推上 GitHub（公開或你有權限的私有 repo）。
2. 以 GitHub 帳號登入 Streamlit Community Cloud。

## 二、建立 App

在 Streamlit Community Cloud 按 **New app**，填入：

| 欄位 | 值 |
|---|---|
| Repository | 你的 repo |
| Branch | `main`（或你要部署的分支） |
| Main file path | `app/citizen_app.py` |
| Python version | 3.12（或 3.10–3.12 皆可） |

## 三、相依套件：只裝民眾版（不含 boto3）

本 repo 根目錄的 `requirements.txt` 是**承辦人版**的完整相依（含 `boto3`、
`pymupdf`、`scikit-learn`），民眾版用不到，裝了只是拖慢部署。民眾版專用相依在
`requirements-citizen.txt`。

Streamlit Community Cloud 預設會讀 repo 根目錄的 `requirements.txt`。要改用
`requirements-citizen.txt`，擇一：

- **方法 A（推薦）**：在 App 的 **Advanced settings → Python → requirements file**
  指定 `requirements-citizen.txt`（若該版本介面支援自訂 requirements 路徑）。
- **方法 B**：另開一個只放民眾版的分支，在該分支把 `requirements-citizen.txt`
  的內容覆蓋成根目錄 `requirements.txt`，部署時指向該分支。這樣部署環境就乾淨、
  不含 boto3。
- **方法 C（本機 / 自架）**：
  ```bash
  pip install -r requirements-citizen.txt
  python -m streamlit run app/citizen_app.py
  ```

> 為什麼要刻意不裝 boto3：這正是「完成標準」之一——在沒安裝 boto3 的乾淨環境裡，
> 只用 `requirements-citizen.txt` 就能跑起民眾版。CI 的 `citizen-no-boto3` 工作會
> 自動驗證這點（斷言 boto3 不存在、import 核心模組、跑民眾版測試）。

## 四、不需要任何 Secrets

民眾版不呼叫 Bedrock、不連 AWS，因此**不需要**在 Streamlit 的 Secrets 設定任何
AWS 金鑰或 KB id。請勿把任何憑證貼進部署設定（競賽規範：憑證不得進公開 repo）。

## 五、主題

`.streamlit/config.toml` 已鎖定淺色主題，民眾版的期限顏色橫幅（紅／橘／黃／綠）
在淺色底下對比清楚。手機瀏覽為單欄窄版（`layout="centered"`），無需額外設定。

## 六、部署後檢查清單

- [ ] 首頁載入，頂端與底部都看得到免責聲明
- [ ] 填入送達日期後，步驟二顯示大字期限與剩餘天數
- [ ] 可展開「期限是怎麼算出來的？」看到計算過程
- [ ] 步驟三可下載 `.md`；若環境有 `python-docx` 亦可下載 `.docx`
- [ ] 手機瀏覽器開啟，版面為單欄、欄位與按鈕可正常操作
