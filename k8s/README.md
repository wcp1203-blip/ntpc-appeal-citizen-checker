# Kubernetes 部署 manifests

把訴願審理 Streamlit 工作台部署到 Kubernetes 叢集的範例 manifests，示範「可擴充容器應用管理平台」的標準做法：資源限制、健康探針、設定／機密分離、水平自動擴充（HPA）與最小權限安全脈絡。

## 檔案

| 檔案 | 用途 |
|---|---|
| `namespace.yaml` | 專屬 namespace，隔離資源 |
| `configmap.yaml` | 非機密設定：區域、模型 inference profile、限流參數 |
| `secret.example.yaml` | Secret 結構範本（不含真實值，勿把填好的版本提交） |
| `deployment.yaml` | Pod 規格：映像、資源 requests/limits、liveness/readiness、安全脈絡 |
| `service.yaml` | 叢集內部 ClusterIP 服務 |
| `hpa.yaml` | 水平自動擴充設定（示範能力，預設鎖在單副本） |

## 快速部署（本機 kind / minikube）

```bash
# 1. 先 build 映像並載入叢集（kind 範例）
docker build -t ntpc-appeal-workbench:latest .
kind load docker-image ntpc-appeal-workbench:latest

# 2. 建立 namespace 與設定
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml

# 3. 建立 Secret（勿用範本檔的假值；下例用 CLI 直接建）
kubectl create secret generic appeal-workbench-secret \
  --namespace appeal-workbench \
  --from-literal=BEDROCK_KB_ID=<你的KB_ID>

# 4. 部署應用
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml

# 5. 本機轉埠檢視
kubectl -n appeal-workbench port-forward svc/appeal-workbench 8501:80
# 瀏覽 http://localhost:8501
```

## ★ 關於 ≤1 RPS 與水平擴充（重要設計取捨）

競賽規範要求 Bedrock 呼叫 ≤ 1 RPS。本專案的節流（`core/bedrock_client.py`）是**行程內 Lock + 單機檔案鎖**，只在**單一 Pod**內有效。

因此：

- `deployment.yaml` 的 `replicas` 與 `hpa.yaml` 的 `minReplicas/maxReplicas` **刻意固定為 1**。
- HPA 設定完整保留，用來**證明平台具備水平擴充能力**，但目前**刻意不開**，因為多副本會讓每個 Pod 各自守 1 RPS，帳號層級總和超標。
- 要真正啟用多副本，必須先把節流換成**集中式分散限流**（例如 Redis 令牌桶、DynamoDB 全域 timestamp 條件寫入），才能在跨 Pod 情況下仍守住帳號層級 1 RPS。

這是「正確性（守規範）優先於規模」的刻意取捨，不是遺漏。

## AWS 憑證

Pod **不**透過 ConfigMap/Secret 注入長期 AWS 金鑰。正式環境建議使用 **IRSA（IAM Roles for Service Accounts）**，讓 Pod 經由 ServiceAccount 取得臨時憑證，符合「憑證不落地、不進版控」原則。
