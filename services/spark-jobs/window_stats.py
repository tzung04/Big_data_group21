from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import ArrayType, IntegerType, StringType, StructField, StructType

KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
PROCESSED_TOPIC = "processed-documents"
CHECKPOINT_PATH = "s3a://spark-checkpoints/window-stats"

spark = (
    SparkSession.builder.appName("VnTextSearch-WindowStats")
    .config(
        "spark.jars.packages",
        "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,"
        "org.apache.hadoop:hadoop-aws:3.3.4",
    )
    .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_PATH)
    .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000")
    .config("spark.hadoop.fs.s3a.access.key", "minioadmin")
    .config("spark.hadoop.fs.s3a.secret.key", "minioadmin")
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

# Định nghĩa schema cho dữ liệu đã xử lý từ Kafka
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

# Đọc từ Kafka topic processed-documents do streaming job chính phát ra
# Lấy token_count để tính avg theo sliding window
raw_stream = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
    .option("subscribe", PROCESSED_TOPIC)
    .option("startingOffsets", "latest")
    .load()
)

parsed_stream = (
    raw_stream.select(F.from_json(F.col("value").cast("string"), processed_schema).alias("data"))
    .select("data.*")
    .withColumn("published_at", F.to_timestamp("published_at"))
    .withColumn("token_count", F.col("token_count").cast("double"))
)

# Áp dụng watermark để xử lý dữ liệu trễ 
watermarked_stream = parsed_stream.filter(F.col("published_at").isNotNull()).withWatermark(
    "published_at", "10 minutes"
)
# Tính toán số lượng tài liệu và trung bình token theo category trong sliding window 1 giờ, trượt 30 phút
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

window_spec = Window.partitionBy("window").orderBy(F.desc("doc_count"))
ranked_df = stats_df.withColumn("rank", F.rank().over(window_spec))

query = (
    ranked_df.writeStream.outputMode("complete")
    .format("console")
    .option("truncate", False)
    .start()
)

query.awaitTermination()
