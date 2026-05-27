# 🚀 Full Deploy Guide — k3d + Local Registry
> Mac Monterey Intel | RAM 8GB | Kappa Architecture

---

## Tổng quan thay đổi quan trọng

**Vấn đề cũ:** `k3d image import` làm máy đơ vì copy toàn bộ image (~2GB)
vào cluster container bằng `docker cp` → ngốn RAM + CPU cùng lúc.

**Giải pháp mới:** Dùng **k3d local registry** — push image qua HTTP localhost:5000,
k3d cluster pull từ registry đó. Nhẹ hơn nhiều, không làm máy đơ.

---

## BƯỚC 0 — Copy files vào repo

```
deploy_v2/
├── k8s/                    → copy toàn bộ vào k8s/ trong repo
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── elasticsearch.yaml
│   ├── kafka.yaml
│   ├── minio.yaml
│   ├── spark-master.yaml
│   ├── spark-streaming.yaml  ← image: k3d-myregistry:5000/...
│   ├── api.yaml              ← image: k3d-myregistry:5000/...
│   ├── prometheus.yaml
│   ├── grafana.yaml
│   ├── init-es-job.yaml
│   └── load-dataset-job.yaml
└── services/
    ├── api/Dockerfile
    └── spark-jobs/Dockerfile
```

---

k3d cluster delete text-search
## BƯỚC 1 — Tạo registry và cluster

```bash
# Tạo local registry trước
k3d registry create myregistry --port 5000

# Tạo cluster sử dụng registry đó
k3d cluster create text-search \
  --agents 1 \
  --registry-use k3d-myregistry:5000 \
  --k3s-arg "--disable=traefik@server:0"

# Verify
kubectl get nodes
k3d registry list
# NAME              ROLE      CLUSTER       STATUS
# k3d-myregistry    registry  text-search   running
```

---

## BƯỚC 2 — Build và push images

```bash
# Build API
docker build -t vn-text-search/api:latest \
  -f services/api/Dockerfile services/api/

docker tag vn-text-search/api:latest localhost:5000/vn-text-search/api:latest

docker push localhost:5000/vn-text-search/api:latest

# Build Spark Jobs (mất 5-10 phút lần đầu do tải underthesea)
docker build -t vn-text-search/spark-jobs:latest \
  -f services/spark-jobs/Dockerfile services/spark-jobs/

docker tag vn-text-search/spark-jobs:latest \
  localhost:5000/vn-text-search/spark-jobs:latest

docker push localhost:5000/vn-text-search/spark-jobs:latest
```

---

## BƯỚC 3 — Deploy infrastructure (theo thứ tự)

```bash
# 3.1 Config
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

# 3.2 MinIO (Spark cần để lưu checkpoint)
kubectl apply -f k8s/minio.yaml
kubectl wait --for=condition=ready pod -l app=minio \
  -n text-search --timeout=120s

# 3.3 Elasticsearch
kubectl apply -f k8s/elasticsearch.yaml
kubectl wait --for=condition=ready pod -l app=elasticsearch \
  -n text-search --timeout=180s

# 3.4 Kafka
kubectl apply -f k8s/kafka.yaml
kubectl wait --for=condition=ready pod -l app=kafka \
  -n text-search --timeout=180s

# 3.5 Spark Master + Monitoring
kubectl apply -f k8s/spark-master.yaml
kubectl apply -f k8s/prometheus.yaml
kubectl apply -f k8s/grafana.yaml

# Kiểm tra
kubectl get pods -n text-search
```

---

## BƯỚC 4 — Init jobs

```bash
# 4.1 Tạo ES index
kubectl apply -f k8s/init-es-job.yaml
kubectl wait --for=condition=complete job/init-es \
  -n text-search --timeout=180s
kubectl logs job/init-es -n text-search
# → "Created index: vn-documents"

# 4.2 Load 2000 bài báo vào Kafka (5-10 phút)
kubectl apply -f k8s/load-dataset-job.yaml
kubectl logs -f job/load-dataset -n text-search
# → "Done! Pushed 2000 articles to raw-documents"
```

---

## BƯỚC 5 — Deploy app

```bash
kubectl apply -f k8s/api.yaml
kubectl apply -f k8s/spark-streaming.yaml

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
```

| URL | Service | Login |
|-----|---------|-------|
| http://localhost:8000/docs | API | — |
| http://localhost:9200 | Elasticsearch | — |
| http://localhost:8080 | Spark UI | — |
| http://localhost:9001 | MinIO | minioadmin/minioadmin |
| http://localhost:3001 | Grafana | admin/admin |

---

## BƯỚC 7 — Verify

```bash
# Đợi 3 phút sau khi Spark start
curl http://localhost:9200/vn-documents/_count
# → {"count": N > 0}

curl http://localhost:8000/health
# → {"status":"ok","es":true}

curl "http://localhost:8000/search?q=Việt+Nam"
# → {"total": N, "results": [...]}
```

---

## XỬ LÝ LỖI

### Kafka CrashLoopBackOff
```bash
kubectl delete deployment kafka -n text-search
kubectl delete service kafka -n text-search
kubectl apply -f k8s/kafka.yaml
```

### Spark OOMKilled
```bash
# Tắt monitoring tạm để nhường RAM
kubectl scale deployment prometheus grafana --replicas=0 -n text-search
kubectl rollout restart deployment/spark-streaming -n text-search
```

### ES count = 0 sau 5 phút
```bash
kubectl logs deploy/spark-streaming -n text-search \
  | grep -v "KafkaDataConsumer\|Fetching\|copied" | tail -20
```

### Rebuild image sau khi sửa code
```bash
docker build -t vn-text-search/spark-jobs:latest \
  -f services/spark-jobs/Dockerfile services/spark-jobs/
docker tag vn-text-search/spark-jobs:latest \
  k3d-myregistry:5000/vn-text-search/spark-jobs:latest
docker push k3d-myregistry:5000/vn-text-search/spark-jobs:latest
kubectl rollout restart deployment/spark-streaming -n text-search
```

---

## Quản lý

```bash
k3d cluster stop text-search    # dừng, giữ data
k3d cluster start text-search   # bật lại
k3d cluster delete text-search  # xóa hoàn toàn
# 1. Start registry trước (nếu exited)
docker start k3d-myregistry

# 2. Nếu kubectl không kết nối được, restart serverlb
docker restart k3d-text-search-serverlb
```