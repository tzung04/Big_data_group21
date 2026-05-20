from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType
from udfs import get_vi_tokenize_udf

KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
RAW_TOPIC = "raw-documents"
PROCESSED_TOPIC = "processed-documents"
ES_NODES = "localhost"
ES_PORT = "9200"
ES_INDEX = "vn-documents"
CHECKPOINT_BASE = "s3a://spark-checkpoints/streaming"
CHECKPOINT_ES = f"{CHECKPOINT_BASE}/es"
CHECKPOINT_KAFKA = f"{CHECKPOINT_BASE}/kafka"

# Khởi tạo Spark Session cho Kafka + Elasticsearch + MinIO checkpoint
spark = (
    SparkSession.builder
    .appName("VnTextSearch-Streaming")
    .config(
        "spark.jars.packages",
        "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,"
        "org.elasticsearch:elasticsearch-spark-30_2.12:8.13.0,"
        "org.apache.hadoop:hadoop-aws:3.3.4",
    )
    .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_BASE)
    .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000")
    .config("spark.hadoop.fs.s3a.access.key", "minioadmin")
    .config("spark.hadoop.fs.s3a.secret.key", "minioadmin")
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")
vi_tokenize = get_vi_tokenize_udf()

# Schema cho raw-documents theo SHARED_CONTRACTS.md
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

# Đọc stream từ Kafka topic raw-documents
df_raw = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
    .option("subscribe", RAW_TOPIC)
    .option("startingOffsets", "latest")
    .load()
)

# Parse JSON từ Kafka rồi chuẩn hóa time fields
df_parsed = (
    df_raw.select(F.from_json(F.col("value").cast("string"), raw_schema).alias("data"))
    .select("data.*")
    .withColumn("published_at", F.to_timestamp("published_at"))
    .withColumn("crawled_at", F.to_timestamp("crawled_at"))
)

# Loại record lỗi parse chính và xử lý late data bằng watermark
df_watermarked = df_parsed.filter(F.col("id").isNotNull()).withWatermark(
    "published_at", "10 minutes"
)

# Bổ sung fields theo processed contract/mapping
df_processed = (
    df_watermarked.withColumn(
        "tokens",
        vi_tokenize(F.col("content")),
    )
    .withColumn("token_count", F.size(F.col("tokens")))
    .withColumn("topic_label", F.lit("unknown"))
    .withColumn("indexed_at", F.current_timestamp())
    .select(
        "id",
        "title",
        "content",
        "tokens",
        "token_count",
        "category",
        "topic_label",
        "url",
        "published_at",
        "indexed_at",
    )
)

# Ghi stream vào Elasticsearch index vn-documents
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

# Publish processed-documents cho API consumer theo SHARED_CONTRACTS.md
df_kafka_out = df_processed.select(
    F.col("id").cast("string").alias("key"),
    F.to_json(
        F.struct(
            "id",
            "title",
            "content",
            "tokens",
            "token_count",
            "category",
            "topic_label",
            "url",
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