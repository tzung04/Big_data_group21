"""
batch_optimized.py
1. Partition pruning  - chi doc parquet partition >= DATE_CUTOFF
2. Broadcast join     - bang lookup nho, tranh shuffle
3. Cache/unpersist    - cache truoc join, giai phong sau
4. Bucketing          - ghi 5 bucket theo category
5. AQE               - Adaptive Query Execution bat san
6. explain()         - in plan de verify join type
"""
import os
from pyspark.sql import functions as F
from pyspark.sql.functions import broadcast
from spark_session import get_spark_session

SOURCE_PATH = os.getenv("SOURCE_PATH", "s3a://spark-output/enriched-documents/")
OUTPUT_PATH = os.getenv("OUTPUT_PATH", "s3a://spark-output/optimized/")
DATE_CUTOFF = os.getenv("DATE_CUTOFF", "2024-01-01")

spark = get_spark_session("VnTextSearch-BatchOptimized")

spark.conf.set("spark.sql.adaptive.enabled", "true")
spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")
spark.conf.set("spark.sql.adaptive.skewJoin.enabled", "true")

# 1. Partition pruning
df_docs = (
    spark.read.parquet(SOURCE_PATH)
    .filter(F.col("published_at") >= F.lit(DATE_CUTOFF))
)
print(f"Doc count sau pruning ({DATE_CUTOFF}): {df_docs.count()}")

# 2. Cache bang lookup truoc broadcast join
df_categories = spark.createDataFrame(
    [
        ("thoi-su",    "Thoi su"),
        ("kinh-doanh", "Kinh doanh"),
        ("the-thao",   "The thao"),
        ("giai-tri",   "Giai tri"),
        ("giao-duc",   "Giao duc"),
    ],
    ["category_id", "category_name"],
)
df_categories.cache()
df_categories.count()

# 3. Broadcast join
df_enriched = df_docs.join(
    broadcast(df_categories),
    df_docs["category"] == df_categories["category_id"],
    how="left",
)

print("\n=== Query Plan (kiem tra BroadcastHashJoin) ===")
df_enriched.explain(mode="formatted")

df_categories.unpersist()

df_enriched.write.mode("overwrite").parquet(OUTPUT_PATH)
print(f"Saved -> {OUTPUT_PATH}")

# 4. Bucketing
print("\n=== Bucketing: 5 bucket theo category ===")
spark.sql("CREATE DATABASE IF NOT EXISTS vn_search")
(
    df_enriched
    .select("id", "title", "category", "category_name", "token_count", "published_at", "topic_label")
    .write
    .mode("overwrite")
    .bucketBy(5, "category")
    .sortBy("published_at")
    .saveAsTable("vn_search.docs_bucketed")
)
print("Bucketed table: vn_search.docs_bucketed")

print("\n=== Plan tren bucketed table (khong Exchange/Shuffle) ===")
spark.table("vn_search.docs_bucketed").groupBy("category").count().explain(mode="formatted")