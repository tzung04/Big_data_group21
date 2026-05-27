# 🚀 Full Deploy Guide — k3d | Mac Monterey Intel | RAM 8GB
> Kappa Architecture | Spark + Kafka + Elasticsearch + MinIO + k3d

---

## 0. Kiến trúc & RAM budget

```
[Crawler/HuggingFace] → Kafka:raw-documents → Spark Streaming
                                               ↓
                                        Elasticsearch:vn-documents
                                               ↓
                                          FastAPI :8000
                                               ↓
                                          React UI :80
```

| Service | RAM limit | Ghi chú |
|---------|-----------|---------|
| Elasticsearch | 1 GB | Heap 512m |
| Kafka | 512 MB | KRaft mode, emptyDir |
| Spark Streaming | 1.4 GB | local[1], /tmp checkpoint |
| MinIO | 256 MB | PVC 2GB |
| API | 256 MB | FastAPI |
| Prometheus | 256 MB | |
| Grafana | 256 MB | |
| **k3d cluster** | **4 GB** | |
| macOS + Docker | ~3.5 GB | |
| **Tổng máy** | **~7.5 GB** | Vừa đủ 8GB |

---

## 1. Chuẩn bị — Copy files vào repo

Tải tất cả files trong thư mục này, copy vào đúng vị trí:

```
services/api/Dockerfile          ← Dockerfile.api (đã tải)
services/spark-jobs/Dockerfile   ← Dockerfile.spark (đã tải)
k8s/namespace.yaml
k8s/configmap.yaml
k8s/secret.yaml
k8s/kafka.yaml                   ← đã fix QUORUM_VOTERS + timeout
k8s/elasticsearch.yaml
k8s/minio.yaml
k8s/spark-master.yaml
k8s/spark-streaming.yaml         ← đã fix OOM: 1400Mi + local[1]
k8s/api.yaml
k8s/prometheus.yaml
k8s/grafana.yaml
k8s/init-es-job.yaml
k8s/load-dataset-job.yaml        ← dùng tdtunlp/binhvq_news_vi
```

---

## 2. Tạo k3d cluster

```bash
k3d cluster create text-search \
  --agents 1 \
  --k3s-arg "--disable=traefik@server:0"

kubectl get nodes
# k3d-text-search-agent-0    Ready   <none>   ...
# k3d-text-search-server-0   Ready   control-plane   ...
```

---

## 3. Build Docker images

```bash
# Build API image
docker build -t vn-text-search/api:latest \
  -f services/api/Dockerfile services/api/

# Build Spark Jobs image (mất 5-10 phút lần đầu)
docker build -t vn-text-search/spark-jobs:latest \
  -f services/spark-jobs/Dockerfile services/spark-jobs/

# Import vào k3d registry (BẮT BUỘC)
k3d image import vn-text-search/api:latest -c text-search
k3d image import vn-text-search/spark-jobs:latest -c text-search

# Verify
docker images | grep vn-text-search
```

---

## 4. Deploy infrastructure (theo đúng thứ tự)

```bash
# 4.1 Namespace + config
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

# 4.2 MinIO (Spark cần để lưu state)
kubectl apply -f k8s/minio.yaml
kubectl wait --for=condition=ready pod -l app=minio \
  -n text-search --timeout=120s

# 4.3 Elasticsearch
kubectl apply -f k8s/elasticsearch.yaml
kubectl wait --for=condition=ready pod -l app=elasticsearch \
  -n text-search --timeout=180s

# 4.4 Kafka
kubectl apply -f k8s/kafka.yaml
kubectl wait --for=condition=ready pod -l app=kafka \
  -n text-search --timeout=180s

# 4.5 Spark Master + Monitoring
kubectl apply -f k8s/spark-master.yaml
kubectl apply -f k8s/prometheus.yaml
kubectl apply -f k8s/grafana.yaml

# Kiểm tra
kubectl get pods -n text-search
```

---

## 5. Chạy init jobs

```bash
# 5.1 Tạo ES index vn-documents
kubectl apply -f k8s/init-es-job.yaml
kubectl wait --for=condition=complete job/init-es \
  -n text-search --timeout=180s
kubectl logs job/init-es -n text-search
# → "Created index: vn-documents"

# 5.2 Load 2000 bài báo vào Kafka (mất 5-10 phút)
kubectl apply -f k8s/load-dataset-job.yaml
kubectl logs -f job/load-dataset -n text-search
# → "Done! Pushed 2000 articles to raw-documents"
```

---

## 6. Deploy ứng dụng

```bash
kubectl apply -f k8s/api.yaml
kubectl apply -f k8s/spark-streaming.yaml

# Kiểm tra toàn bộ
kubectl get pods -n text-search
```

Output mong đợi:
```
NAME                          READY   STATUS      RESTARTS
elasticsearch-xxx             1/1     Running     0
kafka-xxx                     1/1     Running     0
minio-xxx                     1/1     Running     0
spark-master-xxx              1/1     Running     0
spark-streaming-xxx           1/1     Running     0
api-xxx                       1/1     Running     0
prometheus-xxx                1/1     Running     0
grafana-xxx                   1/1     Running     0
init-es-xxx                   0/1     Completed   0
load-dataset-xxx              0/1     Completed   0
```

---

## 7. Port-forward để truy cập

```bash
kubectl port-forward svc/api           8000:8000 -n text-search &
kubectl port-forward svc/elasticsearch 9200:9200 -n text-search &
kubectl port-forward svc/spark-master  8080:8080 -n text-search &
kubectl port-forward svc/minio         9001:9001 -n text-search &
kubectl port-forward svc/grafana       3001:3000 -n text-search &
```

| Service | URL | Login |
|---------|-----|-------|
| API Docs | http://localhost:8000/docs | — |
| Elasticsearch | http://localhost:9200 | — |
| Spark UI | http://localhost:8080 | — |
| MinIO | http://localhost:9001 | minioadmin/minioadmin |
| Grafana | http://localhost:3001 | admin/admin |

---

## 8. Verify pipeline

```bash
# Đợi ~3 phút sau khi Spark start, rồi:

# ES có data chưa?
curl http://localhost:9200/vn-documents/_count
# → {"count": N > 0}

# API hoạt động?
curl http://localhost:8000/health
# → {"status":"ok","es":true}

# Tìm kiếm?
curl "http://localhost:8000/search?q=Việt+Nam"
# → {"total": N, "results": [...]}

# Spark logs (bỏ qua WARN KafkaDataConsumer)
kubectl logs deploy/spark-streaming -n text-search \
  | grep -v "KafkaDataConsumer" | tail -10
```

---

## Xử lý lỗi

### Kafka CrashLoopBackOff (sau restart Mac)
```bash
kubectl delete deployment kafka -n text-search
kubectl delete service kafka -n text-search
kubectl apply -f k8s/kafka.yaml
```

### Spark OOMKilled
```bash
# Đã fix trong spark-streaming.yaml (1400Mi)
# Nếu vẫn OOM, tắt prometheus + grafana tạm:
kubectl scale deployment prometheus grafana --replicas=0 -n text-search
kubectl rollout restart deployment/spark-streaming -n text-search
```

### Image pull error (ErrImageNeverPull)
```bash
k3d image import vn-text-search/api:latest -c text-search
k3d image import vn-text-search/spark-jobs:latest -c text-search
kubectl rollout restart deployment/api -n text-search
kubectl rollout restart deployment/spark-streaming -n text-search
```

### ES count = 0 sau 5 phút
```bash
kubectl logs deploy/spark-streaming -n text-search \
  | grep -v "KafkaDataConsumer\|Fetching\|copied\|Adding" | tail -20
```

---

## Quản lý cluster

```bash
# Dừng (giải phóng RAM, giữ data)
k3d cluster stop text-search

# Bật lại
k3d cluster start text-search

# Xóa hoàn toàn
k3d cluster delete text-search
```