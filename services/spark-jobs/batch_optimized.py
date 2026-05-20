from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import broadcast

SOURCE_PATH = "s3a://spark-output/"
OUTPUT_PATH = "s3a://spark-output/optimized/"

spark = (
    SparkSession.builder.appName("VnTextSearch-BatchOptimized")
    .config(
        "spark.jars.packages",
        "org.apache.hadoop:hadoop-aws:3.3.4",
    )
    .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000")
    .config("spark.hadoop.fs.s3a.access.key", "minioadmin")
    .config("spark.hadoop.fs.s3a.secret.key", "minioadmin")
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

# Partition pruning: lọc sớm theo published_at để Spark chỉ đọc phần dữ liệu cần thiết
# Lưu ý: hiệu quả nhất khi dữ liệu parquet được partition theo published_at / date

df_optimized = (
    spark.read.parquet(SOURCE_PATH)
    .filter(F.col("published_at") >= F.lit("2024-01-01"))
)

# Bảng tra cứu category nhỏ: cache để dùng nhiều lần, sau đó broadcast khi join
# Join bằng broadcast giúp tránh shuffle lớn khi bảng category chỉ có vài dòng

df_categories = spark.createDataFrame(
    [
        ("thoi-su", "Thời sự"),
        ("kinh-doanh", "Kinh doanh"),
        ("the-thao", "Thể thao"),
        ("giai-tri", "Giải trí"),
    ],
    ["category_id", "category_name"],
)

df_categories.cache()

df_enriched = df_optimized.join(
    broadcast(df_categories),
    df_optimized["category"] == df_categories["category_id"],
    how="left",
)

# Dọn cache sau khi dùng xong

df_categories.unpersist()

# Ghi ra MinIO để các job/report khác dùng tiếp

df_enriched.write.mode("overwrite").parquet(OUTPUT_PATH)
