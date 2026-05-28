# 🚀 Full Deploy Guide — k3d + Local Registry
> Mac Monterey Intel | RAM 8GB | Kappa Architecture

---

## Tổng quan

**Dùng k3d local registry** thay vì `k3d image import` — push image qua HTTP `localhost:5000`,
cluster pull từ `k3d-myregistry:5000`. Nhẹ hơn nhiều, không làm máy đơ.

**Lưu ý quan trọng:**
- `docker push` từ host Mac → dùng `localhost:5000/...`
- `image:` trong k8s YAML → dùng `k3d-myregistry:5000/...`
- Spark executor memory phải set qua env var `SPARK_EXECUTOR_MEMORY` trong yaml (không phải SparkConf)

---

## BƯỚC 1 — Tạo registry và cluster

```bash
k3d registry create myregistry --port 5000

k3d cluster create text-search \
  --agents 1 \
  --registry-use k3d-myregistry:5000 \
  --k3s-arg "--disable=traefik@server:0"

kubectl get nodes
k3d registry list
```

---

## BƯỚC 2 — Build và push images

```bash
# API
docker build -t vn-text-search/api:latest -f services/api/Dockerfile services/api/
docker tag vn-text-search/api:latest localhost:5000/vn-text-search/api:latest
docker push localhost:5000/vn-text-search/api:latest

# frontend
docker build -t vn-text-search/frontend:latest -f services/frontend/Dockerfile services/frontend/
docker tag vn-text-search/frontend:latest localhost:5000/vn-text-search/frontend:latest
docker push localhost:5000/vn-text-search/frontend:latest

# crawler
docker build -t vn-text-search/crawler:latest -f services/crawler/Dockerfile services/crawler/
docker tag vn-text-search/crawler:latest localhost:5000/vn-text-search/crawler:latest
docker push localhost:5000/vn-text-search/crawler:latest

# Spark Jobs (mất 5-10 phút lần đầu)
docker build -t vn-text-search/spark-jobs:latest -f services/spark-jobs/Dockerfile services/spark-jobs/
docker tag vn-text-search/spark-jobs:latest localhost:5000/vn-text-search/spark-jobs:latest
docker push localhost:5000/vn-text-search/spark-jobs:latest
```

---

## BƯỚC 3 — Deploy infrastructure (theo thứ tự)

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

kubectl apply -f k8s/minio.yaml
kubectl wait --for=condition=ready pod -l app=minio -n text-search --timeout=120s

kubectl apply -f k8s/elasticsearch.yaml
kubectl wait --for=condition=ready pod -l app=elasticsearch -n text-search --timeout=180s

kubectl apply -f k8s/kafka.yaml
kubectl wait --for=condition=ready pod -l app=kafka -n text-search --timeout=180s

kubectl apply -f k8s/spark-master.yaml
kubectl apply -f k8s/prometheus.yaml
kubectl apply -f k8s/grafana.yaml

kubectl get pods -n text-search
```

---

## BƯỚC 4 — Init jobs

```bash
kubectl apply -f k8s/init-es-job.yaml
kubectl wait --for=condition=complete job/init-es -n text-search --timeout=180s
kubectl logs job/init-es -n text-search
# → "Created index: vn-documents"

# hoặc
kubectl apply -f k8s/load-dataset-job.yaml
kubectl logs -f job/load-dataset -n text-search
# → "Done! Pushed 2000 articles to raw-documents"
# hoặc
kubectl apply -f k8s/crawler.yaml
kubectl logs -f deploy/crawler -n text-search
```

---

## BƯỚC 5 — Deploy app

```bash
kubectl apply -f k8s/api.yaml
kubectl apply -f k8s/spark-streaming.yaml
kubectl apply -f k8s/frontend.yaml

kubectl get pods -n text-search
```

Tất cả phải Running:
```
elasticsearch-xxx    1/1  Running
kafka-xxx            1/1  Running
minio-xxx            1/1  Running
spark-master-xxx     1/1  Running
spark-streaming-xxx  1/1  Running
api-xxx              1/1  Running
frontend-xxx         1/1  Running
prometheus-xxx       1/1  Running
grafana-xxx          1/1  Running
init-es-xxx          0/1  Completed
load-dataset-xxx     0/1  Completed
```

---

## BƯỚC 6 — Port-forward

```bash
kubectl port-forward svc/api           8000:8000 -n text-search &
kubectl port-forward svc/elasticsearch 9200:9200 -n text-search &
kubectl port-forward svc/spark-master  8080:8080 -n text-search &
kubectl port-forward svc/minio         9001:9001 -n text-search &
kubectl port-forward svc/grafana       3001:3000 -n text-search &
kubectl port-forward svc/prometheus 9090:9090 -n text-search &
kubectl port-forward svc/frontend      3000:80   -n text-search &
```

| URL | Service | Login |
|-----|---------|-------|
| http://localhost:3000 | Frontend | — |
| http://localhost:8000/docs | API Swagger | — |
| http://localhost:9200 | Elasticsearch | — |
| http://localhost:8080 | Spark UI | — |
| http://localhost:9001 | MinIO | minioadmin / minioadmin |
| http://localhost:3001 | Grafana | admin / admin |

---

## BƯỚC 7 — Verify

```bash
# Đợi ~3 phút sau khi Spark start
curl http://localhost:9200/vn-documents/_count
# → {"count": 2000, ...}

curl http://localhost:8000/health
# → {"status":"ok","es":true}

curl "http://localhost:8000/search?q=Vi%E1%BB%87t+Nam"
# → {"total": N, "results": [...]}
# Lưu ý: encode UTF-8 khi dùng curl, hoặc test qua http://localhost:8000/docs
```

---

## Quản lý hàng ngày

```bash
# Dừng (giữ data)
k3d cluster stop text-search

# Bật lại
docker start k3d-myregistry          # registry hay bị exited sau Docker Desktop restart
k3d cluster start text-search
docker restart k3d-text-search-serverlb  # nếu kubectl báo "connection reset"

# Xóa hoàn toàn
k3d cluster delete text-search
```

**Checklist sau khi `cluster start`:**
```bash
docker ps --filter name=k3d --format "table {{.Names}}\t{{.Status}}"
# Tất cả phải "Up", không có "Exited"
kubectl get nodes   # cả 2 node phải Ready
kubectl get pods -n text-search   # không có CrashLoopBackOff
```

---

## XỬ LÝ LỖI

### kubectl: "connection reset by peer"
```bash
docker restart k3d-text-search-serverlb
# Nguyên nhân: nginx proxy chết sau Docker Desktop restart
```

### Spark: "Executor memory must be at least 471MB"
```bash
# Đảm bảo spark-streaming.yaml có env vars:
# - name: SPARK_EXECUTOR_MEMORY
#   value: "512m"
# - name: SPARK_DRIVER_MEMORY
#   value: "512m"
kubectl apply -f k8s/spark-streaming.yaml
kubectl rollout restart deployment/spark-streaming -n text-search
```

### ES count = 0 sau 5 phút
```bash
kubectl logs deploy/spark-streaming -n text-search \
  | grep -v "KafkaDataConsumer\|Fetching\|copied" | tail -30
```

### Kafka CrashLoopBackOff
```bash
kubectl delete deployment kafka -n text-search
kubectl delete service kafka -n text-search
kubectl apply -f k8s/kafka.yaml
```

### Spark OOMKilled (RAM quá thấp)
```bash
kubectl scale deployment prometheus grafana --replicas=0 -n text-search
kubectl rollout restart deployment/spark-streaming -n text-search
```

### Rebuild image sau khi sửa code
```bash
docker build -t vn-text-search/spark-jobs:latest \
  -f services/spark-jobs/Dockerfile services/spark-jobs/
docker tag vn-text-search/spark-jobs:latest localhost:5000/vn-text-search/spark-jobs:latest
docker push localhost:5000/vn-text-search/spark-jobs:latest
kubectl rollout restart deployment/spark-streaming -n text-search
```