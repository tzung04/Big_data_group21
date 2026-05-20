import os

from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

from spark_session import get_spark_session
from udfs import get_vi_tokenize_udf

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
ES_NODES = os.getenv("ES_HOST", "localhost")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_INDEX = "vn-documents"
RAW_TOPIC = "raw-documents"
PROCESSED_TOPIC = "processed-documents"
CHECKPOINT_BASE = "s3a://spark-checkpoints/streaming"
CHECKPOINT_ES = f"{CHECKPOINT_BASE}/es"
CHECKPOINT_KAFKA = f"{CHECKPOINT_BASE}/kafka"

spark = get_spark_session("VnTextSearch-Streaming")
vi_tokenize = get_vi_tokenize_udf()

# Schema theo SHARED_CONTRACTS.md §raw-documents
raw_schema = StructType(
    [
        StructField("id", StringType()),
        StructField("title", StringType()),
        StructField("content", StringType()),
        StructField("url", StringType()),
        StructField("category", StringType()),
        StructField("source", StringType()),
        StructField("published_at", StringType()),
        StructField("crawled_at", StringType()),
    ]
)

df_raw = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
    .option("subscribe", RAW_TOPIC)
    .option("startingOffsets", "earliest")
    .load()
)

df_parsed = (
    df_raw.select(F.from_json(F.col("value").cast("string"), raw_schema).alias("data"))
    .select("data.*")
    .withColumn("published_at", F.to_timestamp("published_at"))
    .withColumn("crawled_at", F.to_timestamp("crawled_at"))
)

# Watermark 10 phút để xử lý late data, lọc record parse lỗi
df_watermarked = df_parsed.filter(F.col("id").isNotNull()).withWatermark(
    "published_at", "10 minutes"
)

# Tokenize + bổ sung fields theo processed-documents contract
df_processed = (
    df_watermarked
    .withColumn("tokens", vi_tokenize(F.col("content")))
    .withColumn("token_count", F.size(F.col("tokens")))
    .withColumn("topic_label", F.lit("unknown"))
    .withColumn("indexed_at", F.current_timestamp())
    .select(
        "id", "title", "content", "tokens", "token_count",
        "category", "topic_label", "url", "published_at", "indexed_at",
    )
)

# Sink 1: Elasticsearch — upsert by id, exactly-once via checkpoint
es_query = (
    df_processed.writeStream.outputMode("append")
    .format("org.elasticsearch.spark.sql")
    .option("es.nodes", ES_NODES)
    .option("es.port", ES_PORT)
    .option("es.resource", ES_INDEX)
    .option("es.mapping.id", "id")
    .option("es.write.operation", "upsert")
    .option("checkpointLocation", CHECKPOINT_ES)
    .start()
)

# Sink 2: Kafka processed-documents — forward downstream cho API consumer
df_kafka_out = df_processed.select(
    F.col("id").cast("string").alias("key"),
    F.to_json(
        F.struct(
            "id", "title", "content", "tokens", "token_count",
            "category", "topic_label", "url",
            F.date_format("published_at", "yyyy-MM-dd'T'HH:mm:ss'Z'").alias("published_at"),
            F.date_format("indexed_at", "yyyy-MM-dd'T'HH:mm:ss'Z'").alias("indexed_at"),
        )
    ).alias("value"),
)

kafka_query = (
    df_kafka_out.writeStream.outputMode("append")
    .format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
    .option("topic", PROCESSED_TOPIC)
    .option("checkpointLocation", CHECKPOINT_KAFKA)
    .start()
)

es_query.awaitTermination()
kafka_query.awaitTermination()
