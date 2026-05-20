import os

from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import ArrayType, IntegerType, StringType, StructField, StructType

from spark_session import get_spark_session

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
PROCESSED_TOPIC = "processed-documents"
CHECKPOINT_PATH = "s3a://spark-checkpoints/window-stats"

spark = get_spark_session("VnTextSearch-WindowStats")
spark.conf.set("spark.sql.streaming.checkpointLocation", CHECKPOINT_PATH)

# Schema theo SHARED_CONTRACTS.md §processed-documents
processed_schema = StructType(
    [
        StructField("id", StringType()),
        StructField("title", StringType()),
        StructField("content", StringType()),
        StructField("tokens", ArrayType(StringType())),
        StructField("token_count", IntegerType()),
        StructField("category", StringType()),
        StructField("topic_label", StringType()),
        StructField("url", StringType()),
        StructField("published_at", StringType()),
        StructField("indexed_at", StringType()),
    ]
)

raw_stream = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
    .option("subscribe", PROCESSED_TOPIC)
    .option("startingOffsets", "latest")
    .load()
)

parsed_stream = (
    raw_stream
    .select(F.from_json(F.col("value").cast("string"), processed_schema).alias("data"))
    .select("data.*")
    .withColumn("published_at", F.to_timestamp("published_at"))
    .withColumn("token_count", F.col("token_count").cast("double"))
)

# Watermark 10 phút, sliding window 1 giờ / bước 30 phút
watermarked_stream = parsed_stream.filter(F.col("published_at").isNotNull()).withWatermark(
    "published_at", "10 minutes"
)

stats_df = (
    watermarked_stream.groupBy(
        F.window("published_at", "1 hour", "30 minutes"),
        F.col("category"),
    )
    .agg(
        F.count("id").alias("doc_count"),
        F.avg("token_count").alias("avg_tokens"),
    )
)

# Window function: xếp hạng category theo doc_count trong mỗi time window
window_spec = Window.partitionBy("window").orderBy(F.desc("doc_count"))
ranked_df = stats_df.withColumn("rank", F.rank().over(window_spec))

query = (
    ranked_df.writeStream.outputMode("complete")
    .format("console")
    .option("truncate", False)
    .option("checkpointLocation", CHECKPOINT_PATH)
    .start()
)

query.awaitTermination()
