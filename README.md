# BTL Big Data Kỳ 20252 — VN Text Search

**Group 21**

| STT | Thành viên | MSSV | Vai trò |
|-----|-----------|------|---------|
| 1 | Bùi Anh Đức | 20225285 | Spark Streaming |
| 2 | Vũ Viết Dũng | 20220023 | Spark ML |
| 3 | Lê Hồng Sơn | 20225389 | Crawler / API |
| 4 | Ngô Hồng Phúc | 20225376 | Frontend / Monitoring  |
| 5 | Phan Trí Dũng | 20225295 | DevOps / K8s|

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

## Deploy 

## Yeu cau
- Docker + Docker Compose (local dev)
- k3d >= 5.x, kubectl (production)
- RAM toi thieu: 8GB

---

## Kien truc dich vu

| Dich vu | Nhiem vu |
|---|---|
| kafka | Hang doi tin nhan. Nhan bai viet tho tu crawler, chuyen sang Spark xu ly. Topic: raw-documents, processed-documents |
| elasticsearch | Luu tru va tim kiem full-text. Chua index vn-documents voi toan bo bai viet da tokenize |
| minio | Object storage S3-compatible. Luu checkpoint Spark Streaming va output cac batch job (parquet) |
| spark-master | Quan ly Spark cluster, phan phoi task cho worker |
| spark-worker | Thuc thi task Spark duoc giao tu master |
| spark-streaming | Deployment chay lien tuc: doc Kafka, tokenize, ghi ES va Kafka processed-documents |
| spark-batch-cronjob | 6 CronJob batch chay theo lich dem: enricher, pivot, optimized, ml, time-series, graph |
| crawler | Thu thap bai viet tu VnExpress, day vao Kafka raw-documents moi 5 phut |
| api | FastAPI phuc vu /search, /stats, /health, /metrics cho frontend va Prometheus |
| frontend | React SPA: tim kiem full-text, xem thong ke theo category |
| prometheus | Thu thap metrics tu API (/metrics) va Spark master |
| grafana | Dashboard giam sat: request rate, latency P95/P99, error rate, memory, CPU |

---

## 1. Local dev — Docker Compose

```bash
cp .env.example .env
docker compose up -d kafka elasticsearch minio
# Cho healthy (~60s)
docker compose up -d api crawler frontend spark-master spark-worker
```

Build Spark jobs image truoc khi chay streaming:
```bash
cd services/spark-jobs
docker build -t vn-text-search/spark-jobs:latest .
cd ../..
```

Nap 2000 bai tu HuggingFace dataset vao Kafka:
```bash
docker compose run --rm crawler python load_dataset.py
```

Chay Spark Streaming (tokenize + index vao ES):
```bash
docker run --rm --network host \
  -e KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  -e ES_HOST=localhost \
  -e MINIO_ENDPOINT=http://localhost:9000 \
  -e CHECKPOINT_BASE=s3a://spark-checkpoints \
  vn-text-search/spark-jobs:latest \
  /opt/spark-jobs/streaming_indexer.py
```

Truy cap:
- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Spark UI: http://localhost:8080
- MinIO console: http://localhost:9001 (minioadmin/minioadmin)

---

## 2. Production — Kubernetes (k3d)

### Tao cluster va registry

Registry duoc tao kem cluster. Tu host machine phai dung `localhost:5000` de push
image, con ben trong cluster K8s dung `k3d-myregistry:5000` de pull — ca hai tro
ve cung registry, chi khac ten goi. Khong can sua /etc/hosts hay insecure-registries.

```bash
k3d cluster create vn-text-search \
  --registry-create k3d-myregistry:5000 \
  --port "30080:30080@loadbalancer" \
  -a 2

optional!!
  k3d cluster create vn-text-search \
  --registry-create k3d-myregistry:5000 \
  --port "30080:30080@loadbalancer" \
  -a 2 \
  --k3s-arg "--resolv-conf=/etc/resolv.conf@server:*"
```

Kiem tra registry da chay:
```bash

kubectl get nodes
k3d registry list
```

### Build va push image

Push dung `localhost:5000` tu host. K8s manifest dung `k3d-myregistry:5000`.

```bash
# Spark jobs
docker build -t localhost:5000/vn-text-search/spark-jobs:latest services/spark-jobs/
docker push localhost:5000/vn-text-search/spark-jobs:latest

# API
docker build -t localhost:5000/vn-text-search/api:latest services/api/
docker push localhost:5000/vn-text-search/api:latest

# Crawler
docker build -t localhost:5000/vn-text-search/crawler:latest services/crawler/
docker push localhost:5000/vn-text-search/crawler:latest

# Frontend
docker build -t localhost:5000/vn-text-search/frontend:latest services/frontend/
docker push localhost:5000/vn-text-search/frontend:latest
```

Kiem tra image da co trong registry:
```bash
curl http://localhost:5000/v2/_catalog
# {"repositories":["vn-text-search/api","vn-text-search/crawler","vn-text-search/frontend","vn-text-search/spark-jobs"]}
```

### Deploy theo thu tu

```bash
# 1. Namespace va config
# namespace.yaml: tao namespace text-search de co lap toan bo du an
# configmap.yaml: env chung (ES_HOST, KAFKA_BOOTSTRAP_SERVERS, CHECKPOINT_BASE...)
# secret.yaml: MINIO_SECRET_KEY
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

# 2. Infrastructure — phai len truoc tat ca cac service khac
# kafka.yaml: broker KRaft mode, tao san topic raw-documents va processed-documents
# elasticsearch.yaml: single-node, index vn-documents se duoc tao o buoc 4
# minio.yaml: tao PVC 2Gi, dung cho checkpoint Spark va parquet output
kubectl apply -f k8s/kafka.yaml
kubectl apply -f k8s/elasticsearch.yaml
kubectl apply -f k8s/minio.yaml

# 3. Cho infrastructure san sang (~2-3 phut)
kubectl wait --namespace text-search \
  --for=condition=ready pod --selector=app=kafka --timeout=180s
kubectl wait --namespace text-search \
  --for=condition=ready pod --selector=app=elasticsearch --timeout=180s

# 4. Init Elasticsearch
# init-es-job.yaml: tao index vn-documents voi mapping dung (keyword, text, date, integer)
kubectl apply -f k8s/init-es-job.yaml
kubectl wait --namespace text-search \
  --for=condition=complete job/init-es --timeout=120s

# 4b. Init MinIO buckets
# init-minio-job.yaml: tao bucket spark-checkpoints va spark-output
# Spark Streaming se loi NoSuchBucket neu 2 bucket nay chua ton tai
# Neu da chay truoc do: kubectl delete job init-minio -n text-search
kubectl apply -f k8s/init-minio-job.yaml
kubectl wait --namespace text-search \
  --for=condition=complete job/init-minio --timeout=120s

# 5. Nap du lieu ban dau
# load-dataset-job.yaml: tai 2000 bai tu HuggingFace tdtunlp/binhvq_news_vi, day vao Kafka
kubectl apply -f k8s/load-dataset-job.yaml
kubectl wait --namespace text-search \
  --for=condition=complete job/load-dataset --timeout=300s

# 6. Spark cluster
# spark-master.yaml: Spark Master + Service (port 7077 RPC, 8080 WebUI)
# spark-worker.yaml: 1 Worker, 800m memory, 2 core
kubectl apply -f k8s/spark-master.yaml
kubectl apply -f k8s/spark-worker.yaml

# 7. Spark Streaming — chay lien tuc, khong dung
# spark-streaming.yaml: Deployment chay streaming_indexer.py
# Doc Kafka raw-documents -> tokenize -> ghi ES + Kafka processed-documents
# Checkpoint luu tren MinIO s3a://spark-checkpoints/streaming/
kubectl apply -f k8s/spark-streaming.yaml

# 8. Batch CronJobs — chi dang ky lich, khong chay ngay
# Cac job tu chay theo lich dem: enricher 1AM, pivot 2AM, optimized 3AM,
# ml-classifier 4AM, time-series 5AM, graph-analysis 6AM Chu nhat
# De chay ngay khi demo, xem phan "Chay batch job de demo" ben duoi
kubectl apply -f k8s/spark-batch-cronjob.yaml

# 9. Application services
# api.yaml: FastAPI /search /stats /health /metrics, ket noi ES
# crawler.yaml: crawl VnExpress moi 5 phut, day Kafka raw-documents
# frontend.yaml: React SPA, NodePort 30080
kubectl apply -f k8s/api.yaml
kubectl apply -f k8s/crawler.yaml
kubectl apply -f k8s/frontend.yaml

# 10. Monitoring
# prometheus.yaml: scrape API /metrics va Spark master moi 15s
# grafana.yaml: dashboard VnTextSearch API voi datasource Prometheus tu dong
kubectl apply -f k8s/prometheus.yaml
kubectl apply -f k8s/grafana.yaml
```

### Kiem tra trang thai
```bash
kubectl get all -n text-search
kubectl logs -n text-search deployment/spark-streaming -f
```

### Truy cap
```bash
# Frontend - API - Grafana (admin/admin) - Spark UI
kubectl port-forward -n text-search svc/frontend 3000:80 &
kubectl port-forward -n text-search svc/api 8000:8000 &
kubectl port-forward -n text-search svc/grafana 3001:3000 &
kubectl port-forward -n text-search svc/spark-master 8080:8080 &
```

### Chay batch job de demo (khong cho CronJob schedule)

Cac CronJob trong spark-batch-cronjob.yaml chi dang ky lich khi apply, khong chay ngay.
Dung lenh duoi de trigger thu cong ngay lap tuc khi demo, ket qua giong het khi tu chay theo lich.

```bash
# enricher.py: sort-merge join + broadcast join, ghi parquet enriched-documents
kubectl create job --from=cronjob/spark-batch-enricher enricher-manual -n text-search

# batch_pivot.py: pivot ngay x category + unpivot stack()
kubectl create job --from=cronjob/spark-batch-pivot pivot-manual -n text-search

# batch_optimized.py: partition pruning + bucketing + AQE + explain plan
kubectl create job --from=cronjob/spark-batch-optimized optimized-manual -n text-search

# ml_classifier.py: train NaiveBayes, update topic_label ve ES
kubectl create job --from=cronjob/spark-ml-classifier ml-manual -n text-search

# time_series.py: MA7/MA14, growth rate, trend, anomaly detection
kubectl create job --from=cronjob/spark-time-series ts-manual -n text-search

# graph_analysis.py: PageRank, Connected Components, Triangle Count, BFS
kubectl create job --from=cronjob/spark-graph-analysis graph-manual -n text-search

# Xem log job dang chay
kubectl logs -n text-search job/enricher-manual -f
```

### Chay unit test
```bash
cd services/spark-jobs
pip install pyspark==3.5.1 pytest
pytest test_jobs.py -v
# 13 test cases: enricher, UDF, custom_agg/UDAF, pivot/unpivot, time_series
```

## 3. Quản lý hàng ngày

```bash
# Dừng (giữ data)
k3d cluster stop vn-text-search

# Bật lại
docker start k3d-myregistry          # registry hay bị exited sau Docker Desktop restart
k3d cluster start vn-text-search
docker restart k3d-vn-text-search-serverlb  # nếu kubectl báo "connection reset"
# restart streaming
kubectl rollout restart deployment/spark-streaming -n text-search
# Xóa hoàn toàn
k3d cluster delete vn-text-search
# restart deployment
kubectl rollout restart deployment -n text-search

```

**Checklist sau khi `cluster start`:**
```bash
docker ps --filter name=k3d --format "table {{.Names}}\t{{.Status}}"
# Tất cả phải "Up", không có "Exited"
kubectl get nodes   # cả 2 node phải Ready
kubectl get pods -n text-search   # không có CrashLoopBackOff
```
xem tin trong kafka
kubectl exec -n text-search deployment/kafka -- kafka-run-class kafka.tools.GetOffsetShell --broker-list localhost:9092 --topic raw-documents
