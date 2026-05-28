"""
window_stats.py
[A] Sliding window aggregation (1h/30min) + rank
[B] Stateful per-category tracking qua foreachBatch

Exactly-once: checkpoint tren s3a + trigger ProcessingTime + ES upsert by id.
"""
import os
from datetime import datetime
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, IntegerType, StringType, StructField, StructType
from pyspark.sql.window import Window
from spark_session import get_spark_session

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
PROCESSED_TOPIC  = "processed-documents"
CHECKPOINT_BASE  = os.getenv("CHECKPOINT_BASE", "s3a://spark-checkpoints")
CHECKPOINT_WIN   = f"{CHECKPOINT_BASE}/window-stats"
CHECKPOINT_STATE = f"{CHECKPOINT_BASE}/stateful-category"

spark = get_spark_session("VnTextSearch-WindowStats")

processed_schema = StructType([
    StructField("id",          StringType()),
    StructField("title",       StringType()),
    StructField("content",     StringType()),
    StructField("tokens",      ArrayType(StringType())),
    StructField("token_count", IntegerType()),
    StructField("category",    StringType()),
    StructField("topic_label", StringType()),
    StructField("url",         StringType()),
    StructField("published_at",StringType()),
    StructField("indexed_at",  StringType()),
])

raw_stream = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
    .option("subscribe", PROCESSED_TOPIC)
    .option("startingOffsets", "latest")
    .option("failOnDataLoss", "false")
    .option("kafka.isolation.level", "read_committed")
    .load()
)

parsed_stream = (
    raw_stream
    .select(F.from_json(F.col("value").cast("string"), processed_schema).alias("data"))
    .select("data.*")
    .withColumn("published_at", F.to_timestamp("published_at"))
    .withColumn("token_count",  F.col("token_count").cast("double"))
)

watermarked = (
    parsed_stream
    .filter(F.col("published_at").isNotNull())
    .filter(F.col("category").isNotNull())
    .withWatermark("published_at", "10 minutes")
)

# [A] Sliding window 1h / buoc 30 phut
stats_df = (
    watermarked
    .groupBy(F.window("published_at", "1 hour", "30 minutes"), F.col("category"))
    .agg(
        F.count("id").alias("doc_count"),
        F.avg("token_count").alias("avg_tokens"),
        F.max("token_count").alias("max_tokens"),
    )
)

def _rank_window_batch(batch_df, batch_id):
    if batch_df.rdd.isEmpty():
        return
    window_spec = Window.partitionBy("window").orderBy(F.desc("doc_count"))
    (
        batch_df
        .withColumn("rank", F.rank().over(window_spec))
        .withColumn("window_start", F.col("window.start"))
        .withColumn("window_end",   F.col("window.end"))
        .drop("window")
        .orderBy("window_start", "rank")
        .show(truncate=False)
    )

query_window = (
    stats_df.writeStream
    .outputMode("complete")
    .foreachBatch(_rank_window_batch)
    .option("checkpointLocation", CHECKPOINT_WIN)
    .trigger(processingTime="30 seconds")
    .start()
)

# [B] Stateful: tich luy tong docs + tokens per category qua cac batch
_category_state: dict = {}

def _stateful_batch(batch_df, batch_id):
    if batch_df.rdd.isEmpty():
        return
    agg = (
        batch_df
        .withColumn("token_count", F.col("token_count").cast("long"))
        .groupBy("category")
        .agg(
            F.count("id").alias("batch_docs"),
            F.sum("token_count").alias("batch_tokens"),
            F.max("published_at").alias("batch_last_seen"),
        )
    )
    for row in agg.collect():
        cat  = row["category"]
        prev = _category_state.get(cat, {"total_docs": 0, "total_tokens": 0, "last_seen": None})
        _category_state[cat] = {
            "total_docs":   prev["total_docs"]   + (row["batch_docs"]   or 0),
            "total_tokens": prev["total_tokens"] + (row["batch_tokens"] or 0),
            "last_seen":    row["batch_last_seen"] or prev["last_seen"],
        }
    ts = datetime.utcnow().strftime("%H:%M:%S")
    print(f"\n[Batch {batch_id}] State snapshot @ {ts}")
    print(f"{'Category':<20} {'Total Docs':>12} {'Total Tokens':>14} Last Seen")
    print("-" * 65)
    for cat, s in sorted(_category_state.items()):
        print(f"{cat:<20} {s['total_docs']:>12} {s['total_tokens']:>14} {s['last_seen']}")

query_stateful = (
    watermarked.writeStream
    .outputMode("append")
    .foreachBatch(_stateful_batch)
    .option("checkpointLocation", CHECKPOINT_STATE)
    .trigger(processingTime="30 seconds")
    .start()
)

print(f"[A] Window  checkpoint -> {CHECKPOINT_WIN}")
print(f"[B] Stateful checkpoint -> {CHECKPOINT_STATE}")

query_window.awaitTermination()
query_stateful.awaitTermination()
