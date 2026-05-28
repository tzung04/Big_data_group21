# Hướng dẫn demo — Đối chiếu yêu cầu đề bài

Mỗi mục demo ghi rõ: yêu cầu đề bài, file thực thi, lệnh kiểm tra, kết quả cần thấy.

---

## Kiến trúc Kappa — Pipeline end-to-end

Luồng dữ liệu: VnExpress / HuggingFace dataset → Kafka (raw-documents) → Spark Streaming → Elasticsearch → FastAPI → React Frontend

Kiểm tra pipeline đang chạy:
```bash
kubectl logs -n text-search deployment/spark-streaming --tail=30
# Thấy: [Batch N] ES: X ok, 0 errors
```

---

## Yêu cầu Spark — 6 nhóm kỹ năng

### 1. Tổng hợp phức tạp

**1a. Hàm cửa sổ + tổng hợp nâng cao**
File: `services/spark-jobs/custom_agg.py`
```bash
kubectl create job --from=cronjob/spark-batch-pivot custom-agg-demo -n text-search
```
Kết quả thấy: rank_by_avg_tokens, pct_rank_docs, stddev_tokens, long_doc_pct theo từng category.

**1b. Pivot + Unpivot**
File: `services/spark-jobs/batch_pivot.py`
```bash
kubectl create job --from=cronjob/spark-batch-pivot pivot-demo -n text-search
kubectl logs -n text-search job/pivot-demo -f
```
Kết quả thấy: bảng PIVOT (ngay x category), bảng UNPIVOT (long format date/category/doc_count).

**1c. UDAF tùy biến (User Defined Aggregate Function)**
File: `services/spark-jobs/custom_agg.py` — hàm `_register_weighted_avg_udaf`
Kết quả thấy: weighted_avg_tokens > simple avg vì bài dài được trọng số log(token+1).

---

### 2. Biến đổi nâng cao

**2a. UDF tokenize tiếng Việt**
File: `services/spark-jobs/udfs.py` — hàm `get_vi_tokenize_udf`
Dùng thư viện `underthesea`, fallback về split khi không có. Loại stopword tiếng Việt.

**2b. Multi-stage transform trong Streaming**
File: `services/spark-jobs/streaming_indexer.py`
Pipeline: parse JSON → filter null → watermark → tokenize (UDF) → enrich → 2 sink song song.

Kiểm tra:
```bash
kubectl logs -n text-search deployment/spark-streaming --tail=50
```

---

### 3. Thao tác Join

**3a. Sort-merge join + Broadcast join (chain nhiều join)**
File: `services/spark-jobs/enricher.py`
```bash
kubectl create job --from=cronjob/spark-batch-enricher enricher-demo -n text-search
kubectl logs -n text-search job/enricher-demo -f
```
Kết quả thấy trong log:
- `SortMergeJoin` — df_docs x df_daily_stats (large x large, autoBroadcast=-1)
- `BroadcastHashJoin` — result x df_category_meta (large x small, broadcast())
- Query plan in bởi `explain(mode="formatted")`

**3b. Broadcast join riêng trong batch optimized**
File: `services/spark-jobs/batch_optimized.py`
```bash
kubectl create job --from=cronjob/spark-batch-optimized opt-demo -n text-search
```

---

### 4. Tối ưu hiệu năng

**4a. Partition pruning**
File: `services/spark-jobs/batch_optimized.py` dòng filter `published_at >= DATE_CUTOFF`
Log thấy: "Doc count sau pruning (2024-01-01): X"

**4b. Bucketing**
File: `services/spark-jobs/batch_optimized.py`
Kết quả: table `vn_search.docs_bucketed` với 5 bucket theo category.
Log thấy: "=== Plan tren bucketed table (khong Exchange/Shuffle) ==="

**4c. Cache + unpersist**
File: `services/spark-jobs/enricher.py` — `df_prepared.cache()` trước 2 lần dùng, `unpersist()` sau.
File: `services/spark-jobs/batch_optimized.py` — `df_categories.cache()` trước broadcast join.

**4d. AQE (Adaptive Query Execution)**
File: `services/spark-jobs/batch_optimized.py`
3 config: `adaptive.enabled`, `coalescePartitions.enabled`, `skewJoin.enabled`.

**4e. Query plan explain**
Cả `enricher.py` và `batch_optimized.py` đều gọi `explain(mode="formatted")`.

---

### 5. Xử lý luồng (Streaming)

**5a. Structured Streaming — 2 output mode**
File: `services/spark-jobs/streaming_indexer.py` — outputMode `append`
File: `services/spark-jobs/window_stats.py` — outputMode `complete` (window) + `append` (stateful)

**5b. Watermark + late data**
File: `services/spark-jobs/streaming_indexer.py` dòng `withWatermark("published_at", "10 minutes")`
File: `services/spark-jobs/window_stats.py` — watermark 10 phút cho sliding window

**5c. Stateful streaming**
File: `services/spark-jobs/window_stats.py` — `_category_state` dict tích lũy qua từng batch
Log thấy mỗi 30s: bảng state snapshot với total_docs, total_tokens, last_seen mỗi category.

**5d. Exactly-once**
- Kafka source: `isolation.level=read_committed` + checkpoint offset
- ES sink: `_op_type=index` với `_id=document_id` (upsert idempotent)
- Trigger: `ProcessingTime("10 seconds")` — checkpoint atomic sau mỗi trigger

Kiểm tra:
```bash
kubectl logs -n text-search deployment/spark-streaming | grep "Batch"
# Thấy: [Batch N] ES: X ok, 0 errors
```

---

### 6. Phân tích nâng cao

**6a. Machine Learning — Spark MLlib**
File: `services/spark-jobs/ml_classifier.py`
Pipeline: StringIndexer → Tokenizer → StopWordsRemover → HashingTF → IDF → NaiveBayes
```bash
kubectl create job --from=cronjob/spark-ml-classifier ml-demo -n text-search
kubectl logs -n text-search job/ml-demo -f
```
Kết quả thấy: `Accuracy: 0.XXXX`, model lưu vào MinIO, topic_label được update về ES.

**6b. GraphFrames**
File: `services/spark-jobs/graph_analysis.py`
Vertices: mỗi bài viết. Edges: 2 bài cùng category có >= 3 token chung.
```bash
kubectl create job --from=cronjob/spark-graph-analysis graph-demo -n text-search
kubectl logs -n text-search job/graph-demo -f
```
Kết quả thấy: Degrees, PageRank top 20, Connected Components, Triangle Count, BFS path.

**6c. Thống kê chuỗi thời gian**
File: `services/spark-jobs/time_series.py`
```bash
kubectl create job --from=cronjob/spark-time-series ts-demo -n text-search
kubectl logs -n text-search job/ts-demo -f
```
Kết quả thấy: MA7, MA14, DoD%, WoW%, trend (up/down/stable), is_anomaly, z_score.

---

## Frontend + API demo

Mở http://localhost:3000 (hoặc http://localhost:30080 trên K8s):

Tab Search:
- Nhập từ khóa tiếng Việt, nhấn Tìm kiếm
- Chọn chuyên mục để lọc theo category
- Kết quả highlight từ khóa trong title và content

Tab Stats:
- Tổng số văn bản đã index
- Số bài theo từng category

API trực tiếp:
```bash
curl "http://localhost:8000/search?q=kinh+te&category=kinh-doanh&size=5"
curl "http://localhost:8000/stats"
curl "http://localhost:8000/health"
# Metrics Prometheus
curl "http://localhost:8000/metrics"
```

---

## Monitoring — Grafana

Mở http://localhost:3001, đăng nhập admin/admin.

Dashboard "VnTextSearch API Dashboard" hiển thị:
- Tổng request, Latency P95/P99, Error rate, Request rate
- HTTP traffic theo endpoint, status code, response size
- Memory RSS, CPU usage, GC collections, open file descriptors

---

## Unit test

```bash
cd services/spark-jobs
pytest test_jobs.py -v
```

13 test cases bao phủ:
- enricher: join logic, filter invalid, daily_count chính xác
- udfs: tokenize cơ bản, input rỗng, lọc ký tự đơn
- custom_agg: window rank, UDAF weighted > simple avg
- batch_pivot: số cột pivot đúng, unpivot round-trip đúng row count
- time_series: MA7 ngày đầu, anomaly detection spike, DoD growth rate

---

## Checkpoint MinIO

Kiểm tra checkpoint đang được ghi:
```bash
kubectl port-forward -n text-search svc/minio 9001:9001
```
Mở http://localhost:9001 (minioadmin/minioadmin), xem bucket `spark-checkpoints`.
Thấy thư mục: `streaming/es/`, `streaming/kafka/`, `window-stats/`, `stateful-category/`.