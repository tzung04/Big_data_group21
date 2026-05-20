from pyspark.sql import functions as F
from pyspark.sql.functions import broadcast

from spark_session import get_spark_session

SOURCE_PATH = "s3a://spark-output/"
OUTPUT_PATH = "s3a://spark-output/optimized/"

spark = get_spark_session("VnTextSearch-BatchOptimized")

# Partition pruning: Spark chỉ đọc parquet partitions có published_at >= cutoff
df_optimized = (
    spark.read.parquet(SOURCE_PATH)
    .filter(F.col("published_at") >= F.lit("2024-01-01"))
)

# Bảng tra cứu nhỏ → cache + broadcast để tránh shuffle khi join
df_categories = spark.createDataFrame(
    [
        ("thoi-su", "Thời sự"),
        ("kinh-doanh", "Kinh doanh"),
        ("the-thao", "Thể thao"),
        ("giai-tri", "Giải trí"),
        ("giao-duc", "Giáo dục"),
    ],
    ["category_id", "category_name"],
)
df_categories.cache()

df_enriched = df_optimized.join(
    broadcast(df_categories),
    df_optimized["category"] == df_categories["category_id"],
    how="left",
)

df_categories.unpersist()

df_enriched.write.mode("overwrite").parquet(OUTPUT_PATH)
