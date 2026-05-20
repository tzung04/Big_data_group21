# BTL Big Data Kỳ 20252 — VN Text Search

**Group 21**

| STT | Thành viên | MSSV | Vai trò |
|-----|-----------|------|---------|
| 1 | Bùi Anh Đức | 20225285 | DevOps / K8s |
| 2 | Vũ Viết Dũng | 20220023 | Spark Streaming |
| 3 | Lê Hồng Sơn | 20225389 | Spark ML |
| 4 | Ngô Hồng Phúc | 20225376 | Crawler / API |
| 5 | Phan Trí Dũng | 20225295 | Frontend / Monitoring |

---

## Kiến trúc

```
VnExpress Crawler (M4)
    │  Kafka topic: raw-documents
    ▼
Spark Structured Streaming (M2)
    ├─ tokenize (underthesea UDF) + watermark 10 phút
    ├─ Elasticsearch index: vn-documents  (upsert, exactly-once)
    └─ Kafka topic: processed-documents
          │
          ├─▶ Window Stats streaming (M2) — sliding window 1h/30m
          └─▶ NaiveBayes ML Classifier (M3) — batch hàng ngày

FastAPI /search /stats (M4) ◀── React Frontend (M5)
Prometheus + Grafana (M5)
MinIO: raw-data / spark-checkpoints / spark-output
```

---

## Deploy trên Minikube

### Yêu cầu

- minikube ≥ 1.32, kubectl ≥ 1.28, Docker
- RAM khuyến nghị: 6GB cho minikube

```bash
minikube start --memory=6144 --cpus=4
```

### Bước 1 — Build images trong môi trường minikube

```bash
# Trỏ Docker CLI vào Docker daemon của minikube
eval $(minikube docker-env)

# Build từng image
docker build -t vn-text-search/api:latest         services/api/
docker build -t vn-text-search/crawler:latest      services/crawler/
docker build -t vn-text-search/spark-jobs:latest   services/spark-jobs/
docker build -t vn-text-search/frontend:latest     services/frontend/
```

### Bước 2 — Apply namespace và config

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
```

### Bước 3 — Deploy infrastructure (thứ tự quan trọng)

```bash
kubectl apply -f k8s/kafka.yaml
kubectl apply -f k8s/elasticsearch.yaml
kubectl apply -f k8s/minio.yaml

# Chờ Elasticsearch sẵn sàng (khoảng 60 giây)
kubectl wait --for=condition=ready pod -l app=elasticsearch -n text-search --timeout=120s
```

### Bước 4 — Khởi tạo index ES và MinIO buckets

```bash
# Tạo index vn-documents
kubectl apply -f k8s/init-es-job.yaml
kubectl wait --for=condition=complete job/init-es -n text-search --timeout=120s

# Buckets được tạo tự động bởi minio-init Job trong minio.yaml
kubectl wait --for=condition=complete job/minio-init -n text-search --timeout=120s
```

### Bước 5 — Deploy Spark

```bash
kubectl apply -f k8s/spark-master.yaml
kubectl wait --for=condition=ready pod -l app=spark-master -n text-search --timeout=60s
kubectl apply -f k8s/spark-worker.yaml
```

### Bước 6 — Deploy ứng dụng

```bash
kubectl apply -f k8s/spark-streaming.yaml   # pipeline chính (liên tục)
kubectl apply -f k8s/crawler.yaml           # VnExpress crawler (liên tục)
kubectl apply -f k8s/api.yaml               # FastAPI search/stats
kubectl apply -f k8s/frontend.yaml          # React UI (NodePort 30080)
```

### Bước 7 — Deploy monitoring

```bash
kubectl apply -f k8s/prometheus.yaml        # NodePort 30090
kubectl apply -f k8s/grafana.yaml           # NodePort 30301
```

### Bước 8 — Batch jobs (CronJob)

```bash
kubectl apply -f k8s/spark-batch-cronjob.yaml
# Chạy thủ công để test ngay:
kubectl create job --from=cronjob/spark-batch-pivot spark-batch-pivot-manual -n text-search
```

### Truy cập UI

```bash
MINIKUBE_IP=$(minikube ip)

echo "Frontend:   http://$MINIKUBE_IP:30080"
echo "Prometheus: http://$MINIKUBE_IP:30090"
echo "Grafana:    http://$MINIKUBE_IP:30301  (admin/admin)"
echo "Spark UI:   $(minikube service spark-master -n text-search --url | head -2 | tail -1)"
echo "MinIO:      $(minikube service minio -n text-search --url | head -2 | tail -1)"
```

### Kiểm tra trạng thái

```bash
kubectl get pods -n text-search
kubectl logs -f deployment/spark-streaming -n text-search
kubectl logs -f deployment/crawler -n text-search
```

---

## Chạy local với Docker Compose

```bash
docker compose up -d
source venv/bin/activate
python services/crawler/init_es.py
python services/crawler/load_dataset.py   # bơm 2000 bài test
python services/spark-jobs/streaming_indexer.py &
cd services/frontend && npm install && npm run dev
```

---

## Cấu trúc thư mục

```
vn-text-search-fn/
├── k8s/                    # Kubernetes manifests
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── kafka.yaml
│   ├── elasticsearch.yaml
│   ├── minio.yaml
│   ├── spark-master.yaml
│   ├── spark-worker.yaml
│   ├── spark-streaming.yaml
│   ├── spark-batch-cronjob.yaml
│   ├── init-es-job.yaml
│   ├── api.yaml
│   ├── crawler.yaml
│   ├── frontend.yaml
│   ├── prometheus.yaml
│   └── grafana.yaml
├── services/
│   ├── api/                # FastAPI search/stats
│   ├── crawler/            # VnExpress crawler + dataset loader
│   ├── frontend/           # React + Vite UI
│   └── spark-jobs/         # PySpark streaming + batch + ML
├── monitoring/             # Grafana/Prometheus config files
├── docs/                   # Tài liệu từng thành viên
├── scripts/                # init ES, MinIO
└── docker-compose.yml      # Local development
```
