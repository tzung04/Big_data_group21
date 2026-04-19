# SHARED CONTRACTS — Đọc trước khi code

> Tất cả 5 người PHẢI tuân theo file này. Không tự ý đổi tên field, port, topic.

---

## 1. Kafka Topics

| Topic | Producer | Consumer | Message format |
|-------|----------|----------|----------------|
| `raw-documents` | Member 4 (crawler) | Member 2 (Spark) | JSON bên dưới |
| `processed-documents` | Member 2 (Spark) | Member 4 (API) | JSON bên dưới |

### raw-documents message schema
```json
{
  "id": "vnexpress_1234567",
  "title": "Tiêu đề bài báo",
  "content": "Nội dung bài báo...",
  "url": "https://vnexpress.net/...",
  "category": "thoi-su",
  "source": "vnexpress",
  "published_at": "2024-01-15T08:00:00Z",
  "crawled_at": "2024-01-15T08:05:00Z"
}
```

### processed-documents message schema
```json
{
  "id": "vnexpress_1234567",
  "title": "Tiêu đề bài báo",
  "content": "Nội dung bài báo...",
  "tokens": ["tiêu_đề", "bài_báo"],
  "token_count": 120,
  "category": "thoi-su",
  "topic_label": "chinh-tri",
  "url": "https://vnexpress.net/...",
  "published_at": "2024-01-15T08:00:00Z",
  "indexed_at": "2024-01-15T08:06:00Z"
}
```

---

## 2. Elasticsearch Index

**Index name:** `vn-documents`

**Mapping** (Member 4 tạo, không ai được tự tạo index khác):
```json
{
  "mappings": {
    "properties": {
      "id":           { "type": "keyword" },
      "title":        { "type": "text", "analyzer": "standard" },
      "content":      { "type": "text", "analyzer": "standard" },
      "tokens":       { "type": "keyword" },
      "token_count":  { "type": "integer" },
      "category":     { "type": "keyword" },
      "topic_label":  { "type": "keyword" },
      "url":          { "type": "keyword" },
      "published_at": { "type": "date" },
      "indexed_at":   { "type": "date" }
    }
  }
}
```

---

## 3. MinIO Buckets

| Bucket | Dùng để | Ai tạo |
|--------|---------|--------|
| `raw-data` | Lưu file parquet raw từ crawler | Member 4 |
| `spark-checkpoints` | Spark Structured Streaming checkpoint | Member 2 |
| `spark-output` | Kết quả batch job | Member 3 |

---

## 4. Ports (không được đổi)

| Service | Port | Dùng bởi |
|---------|------|----------|
| Kafka | 9092 | Tất cả |
| Elasticsearch | 9200 | Member 2, 3, 4 |
| MinIO API | 9000 | Member 2, 3 |
| MinIO Console | 9001 | Tất cả (UI) |
| Spark Master | 7077 | Member 2, 3 |
| Spark UI | 8080 | Tất cả (UI) |
| FastAPI | 8000 | Member 5 (frontend) |
| Prometheus | 9090 | Member 5 |
| Grafana | 3001 | Member 5 |

---

## 5. Python dependencies chung

```txt
# Tất cả dùng Python 3.11, cài vào venv chung
pyspark==3.5.1
kafka-python==2.0.2
elasticsearch==8.13.0
boto3==1.34.0        # MinIO client
```

## 6. Cách chạy local

```bash
# Bước 1: Bật docker
docker compose up -d

# Bước 2: Kích hoạt venv
source venv/bin/activate   # macOS/Linux
venv\Scripts\activate      # Windows

# Bước 3: Chạy service của mình (xem README trong folder)
```

---

## 7. Git workflow

```
main        ← chỉ merge khi test xong
dev         ← branch làm việc chính
feat/m2-spark-streaming   ← branch của Member 2
feat/m3-ml-jobs           ← branch của Member 3
feat/m4-crawler-api       ← branch của Member 4
feat/m5-frontend          ← branch của Member 5
```

**Quy tắc commit:**
```
feat: thêm UDF tokenize tiếng Việt
fix: sửa lỗi Kafka consumer timeout
docs: cập nhật README
```
