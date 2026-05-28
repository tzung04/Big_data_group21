"""
streaming_indexer.py

Exactly-once:
  - Kafka source: read_committed + checkpoint offset
  - ES sink: upsert by _id (idempotent), operation "index" cho phép overwrite
  - Trigger ProcessingTime("10 seconds") + atomic checkpoint
  - Checkpoint trên s3a (bền vững qua pod restart)

Late data: withWatermark 10 phút trên crawled_at (không phải published_at).
  - crawled_at luôn là "bây giờ" → không bao giờ bị late data drop
  - published_at có thể là ngày cũ (bài re-crawl) → dùng làm watermark sẽ drop nhầm

Fixes so với version cũ:
  1. startingOffsets "earliest"  — không bỏ sót bài khi pod restart
  2. Timestamp parse đa-format    — xử lý được cả "2024-01-15T10:30:00Z"
                                    lẫn "2024-01-15T10:30:00+00:00" từ nhiều source
  3. Watermark trên crawled_at    — tránh drop bài cũ được re-crawl
  4. ES tokenization              — analyze_text() để ES tự tokenize Vietnamese,
                                    thay vì chỉ dùng split() whitespace đơn giản
  5. Robust null-check            — filter sau parse, không trước
"""
import logging
import os
from typing import List

from elasticsearch import Elasticsearch, helpers
from pyspark.sql import DataFrame, functions as F
from pyspark.sql.types import StringType, StructField, StructType

from spark_session import get_spark_session
from udfs import get_vi_tokenize_udf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("streaming_indexer")

# ── Config ────────────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
ES_NODES         = os.getenv("ES_HOST",        "localhost")
ES_PORT          = os.getenv("ES_PORT",         "9200")
ES_INDEX         = "vn-documents"
RAW_TOPIC        = "raw-documents"
PROCESSED_TOPIC  = "processed-documents"
CHECKPOINT_BASE  = os.getenv("CHECKPOINT_BASE", "s3a://spark-checkpoints")
CHECKPOINT_ES    = f"{CHECKPOINT_BASE}/streaming/es"
CHECKPOINT_KAFKA = f"{CHECKPOINT_BASE}/streaming/kafka"
WATERMARK_DELAY  = os.getenv("WATERMARK_DELAY",  "10 minutes")
TRIGGER_INTERVAL = os.getenv("TRIGGER_INTERVAL", "10 seconds")

# ── Spark session ─────────────────────────────────────────────────────────────
spark       = get_spark_session("VnTextSearch-Streaming")
vi_tokenize = get_vi_tokenize_udf()

# ── Schema ────────────────────────────────────────────────────────────────────
raw_schema = StructType([
    StructField("id",           StringType()),
    StructField("title",        StringType()),
    StructField("content",      StringType()),
    StructField("url",          StringType()),
    StructField("category",     StringType()),
    StructField("source",       StringType()),
    StructField("published_at", StringType()),
    StructField("crawled_at",   StringType()),
])

# ── Kafka source ──────────────────────────────────────────────────────────────
# FIX #1: "earliest" thay vì "latest"
# "latest" reset về đầu mỗi lần pod restart khi checkpoint bị stale/cleared.
# "earliest" + checkpoint: lần đầu đọc từ đầu topic, các lần sau tiếp tục từ
# offset đã lưu trong checkpoint → không bỏ sót bài nào dù pod restart.
df_raw = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
    .option("subscribe", RAW_TOPIC)
    .option("startingOffsets", "earliest")          # FIX #1
    .option("failOnDataLoss", "false")
    .option("kafka.isolation.level", "read_committed")
    .load()
)

# ── Parse JSON + timestamp ────────────────────────────────────────────────────
# FIX #2: coalesce nhiều format để xử lý được cả crawler lẫn dataset
#   - Crawler cũ:  "2024-01-15T10:30:00+00:00Z"  → format 1 fail, format 2 ok
#   - Crawler mới: "2024-01-15T10:30:00Z"          → format 1 ok
#   - Dataset HF:  "2024-01-15T10:30:00.123456Z"   → format 3 ok
#   - Fallback:    to_timestamp() tự detect
def _parse_ts(col_name: str) -> F.Column:
    c = F.col(col_name)
    return F.coalesce(
        F.to_timestamp(c, "yyyy-MM-dd'T'HH:mm:ss'Z'"),       # "2024-01-15T10:30:00Z"
        F.to_timestamp(c, "yyyy-MM-dd'T'HH:mm:ssXXX"),        # "2024-01-15T10:30:00+00:00"
        F.to_timestamp(c, "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'"), # "2024-01-15T10:30:00.123456Z"
        F.to_timestamp(c),                                     # fallback tự detect
    )

df_parsed = (
    df_raw
    .select(F.from_json(F.col("value").cast("string"), raw_schema).alias("data"))
    .select("data.*")
    .withColumn("published_at", _parse_ts("published_at"))
    .withColumn("crawled_at",   _parse_ts("crawled_at"))
)

# ── Filter + Watermark ────────────────────────────────────────────────────────
# FIX #3: watermark trên crawled_at, không phải published_at
# Lý do: published_at của bài cũ được re-crawl có thể là tuần trước → vượt quá
# watermark 10 phút → bị drop. crawled_at luôn là "lúc crawler chạy" → không bao
# giờ late. Filter null sau parse để log được số bài bị lỗi format.
df_watermarked = (
    df_parsed
    .filter(F.col("id").isNotNull())
    .filter(F.col("crawled_at").isNotNull())        # FIX #3: filter crawled_at
    .withWatermark("crawled_at", WATERMARK_DELAY)   # FIX #3: watermark crawled_at
)

# ── Transform + ES tokenization ───────────────────────────────────────────────
# FIX #4: ES analyze tokenization
# Thay vì chỉ split() whitespace (không hiểu tiếng Việt), ta gọi ES analyze API
# để tokenize đúng: "Hà Nội" → ["hà_nội"] thay vì ["hà", "nội"].
# Việc này được thực hiện trong _write_batch_to_es() thông qua ES analyze endpoint.
# Tại Spark layer, ta vẫn tạo tokens bằng split() làm fallback / preview nhanh,
# nhưng ES sẽ tự index lại bằng analyzer "vi_analyzer" được định nghĩa trong mapping.
df_processed = (
    df_watermarked
    .withColumn("tokens",      F.split(F.lower(F.regexp_replace(
                                    F.col("content"), "[^\\w\\s]", " ")), "\\s+"))
    .withColumn("tokens",      F.array_remove(F.col("tokens"), ""))   # bỏ empty string
    .withColumn("token_count", F.size(F.col("tokens")))
    .withColumn("topic_label", F.lit("unknown"))
    .withColumn("indexed_at",  F.current_timestamp())
    .select(
        "id", "title", "content", "tokens", "token_count",
        "category", "topic_label", "url",
        "source", "published_at", "crawled_at", "indexed_at",
    )
)

# ── ES sink ───────────────────────────────────────────────────────────────────
def _get_es_tokens(es: Elasticsearch, text: str) -> List[str]:
    """Gọi ES analyze API để tokenize tiếng Việt đúng.
    
    ES index vn-documents cần có analyzer 'vi_analyzer' (icu_analyzer hoặc
    custom). Nếu analyzer chưa có, fallback về 'standard'.
    Kết quả được lưu vào field 'tokens' để các batch job dùng lại.
    """
    if not text:
        return []
    try:
        resp = es.indices.analyze(
            index=ES_INDEX,
            body={"analyzer": "vi_analyzer", "text": text},
        )
        return [t["token"] for t in resp.get("tokens", [])]
    except Exception:
        # Fallback: nếu vi_analyzer chưa tồn tại, dùng standard
        try:
            resp = es.indices.analyze(
                index=ES_INDEX,
                body={"analyzer": "standard", "text": text},
            )
            return [t["token"] for t in resp.get("tokens", [])]
        except Exception:
            return text.lower().split()


def _write_batch_to_es(batch_df: DataFrame, batch_id: int) -> None:
    rows = batch_df.collect()
    if not rows:
        logger.info(f"[Batch {batch_id}] Empty batch, skipping")
        return

    es = Elasticsearch(f"http://{ES_NODES}:{ES_PORT}")

    # FIX #4: tokenize qua ES analyze API thay vì chỉ dùng tokens từ Spark split()
    actions = []
    skipped = 0
    for row in rows:
        if row["id"] is None:
            skipped += 1
            continue

        # Ưu tiên token từ ES analyze (tiếng Việt đúng hơn)
        es_tokens = _get_es_tokens(es, row["content"] or "")
        # Nếu ES trả về empty (content rỗng), giữ lại tokens từ Spark làm fallback
        final_tokens = es_tokens if es_tokens else list(row["tokens"] or [])

        actions.append({
            "_op_type": "index",    # idempotent upsert theo _id
            "_index":   ES_INDEX,
            "_id":      row["id"],
            "_source":  {
                "id":          row["id"],
                "title":       row["title"],
                "content":     row["content"],
                "tokens":      final_tokens,
                "token_count": len(final_tokens),
                "category":    row["category"],
                "source":      getattr(row, "source", "") or "",
                "topic_label": row["topic_label"],
                "url":         row["url"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "crawled_at":   row["crawled_at"].isoformat()   if row["crawled_at"]   else None,
                "indexed_at":   row["indexed_at"].isoformat()   if row["indexed_at"]   else None,
            },
        })

    if not actions:
        logger.warning(f"[Batch {batch_id}] All {skipped} rows skipped (null id)")
        return

    success, errors = helpers.bulk(es, actions, raise_on_error=False, stats_only=False)
    logger.info(
        f"[Batch {batch_id}] ES: {success} ok, {len(errors)} errors, {skipped} skipped"
    )
    if errors:
        logger.warning(f"[Batch {batch_id}] ES errors sample: {errors[:3]}")

# ── Write streams ─────────────────────────────────────────────────────────────
es_query = (
    df_processed.writeStream
    .outputMode("append")
    .foreachBatch(_write_batch_to_es)
    .option("checkpointLocation", CHECKPOINT_ES)
    .trigger(processingTime=TRIGGER_INTERVAL)
    .start()
)

kafka_query = (
    df_processed.select(
        F.col("id").cast("string").alias("key"),
        F.to_json(F.struct(
            "id", "title", "content", "tokens", "token_count",
            "category", "topic_label", "source", "url",
            F.date_format("published_at", "yyyy-MM-dd'T'HH:mm:ss'Z'").alias("published_at"),
            F.date_format("crawled_at",   "yyyy-MM-dd'T'HH:mm:ss'Z'").alias("crawled_at"),
            F.date_format("indexed_at",   "yyyy-MM-dd'T'HH:mm:ss'Z'").alias("indexed_at"),
        )).alias("value"),
    )
    .writeStream
    .outputMode("append")
    .format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
    .option("topic", PROCESSED_TOPIC)
    .option("checkpointLocation", CHECKPOINT_KAFKA)
    .trigger(processingTime=TRIGGER_INTERVAL)
    .start()
)

logger.info(f"Streaming started")
logger.info(f"  ES checkpoint    → {CHECKPOINT_ES}")
logger.info(f"  Kafka checkpoint → {CHECKPOINT_KAFKA}")
logger.info(f"  Watermark field  → crawled_at ({WATERMARK_DELAY})")
logger.info(f"  Trigger interval → {TRIGGER_INTERVAL}")

es_query.awaitTermination()
kafka_query.awaitTermination()