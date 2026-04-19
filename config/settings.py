import os

# ── Kafka ──────────────────────────────────────────────
KAFKA_BOOTSTRAP        = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC_RAW        = "raw-docs"
KAFKA_TOPIC_PROCESSED  = "processed-docs"
KAFKA_GROUP_BATCH      = "spark-batch-consumer"
KAFKA_GROUP_STREAM     = "spark-stream-consumer"

# ── MinIO (S3-compatible) ──────────────────────────────
MINIO_ENDPOINT         = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY       = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY       = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET           = "text-search-bucket"
MINIO_RAW_PREFIX       = "raw/"
MINIO_PROC_PREFIX      = "processed/"
MINIO_CKPT_PREFIX      = "checkpoints/"

# Spark đọc MinIO qua S3A
SPARK_S3A_ENDPOINT     = f"http://{MINIO_ENDPOINT}"
SPARK_S3A_PATH_STYLE   = "true"

# ── Elasticsearch ──────────────────────────────────────
ES_HOST                = os.getenv("ES_HOST", "localhost:9200")
ES_INDEX               = "documents"        # alias
ES_INDEX_V1            = "documents_v1"     # index thật

# ── MongoDB ────────────────────────────────────────────
MONGO_URI              = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB               = "textsearch"
MONGO_COL_DOCS         = "documents"
MONGO_COL_SESSIONS     = "sessions"
MONGO_COL_KEYWORDS     = "keywords"

# ── Redis ──────────────────────────────────────────────
REDIS_HOST             = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT             = int(os.getenv("REDIS_PORT", "6379"))
REDIS_TTL_SECONDS      = 300               # cache 5 phút

# ── Spark ──────────────────────────────────────────────
SPARK_APP_BATCH        = "text-search-batch"
SPARK_APP_STREAM       = "text-search-streaming"
SPARK_EXECUTOR_MEM     = "1g"
SPARK_DRIVER_MEM       = "512m"
SPARK_MASTER           = os.getenv("SPARK_MASTER", "local[2]")

# ── Streaming ──────────────────────────────────────────
WATERMARK_DELAY        = "10 minutes"
WINDOW_DURATION        = "1 hour"
SLIDE_DURATION         = "15 minutes"
CHECKPOINT_PATH        = f"s3a://{MINIO_BUCKET}/{MINIO_CKPT_PREFIX}streaming"

# ── Crawler ────────────────────────────────────────────
CRAWLER_SOURCES = [
    "https://vnexpress.net/rss/tin-moi-nhat.rss",
    "https://tuoitre.vn/rss/tin-moi-nhat.rss",
]
CRAWLER_BATCH_SIZE     = 100               # gửi Kafka mỗi 100 bài
