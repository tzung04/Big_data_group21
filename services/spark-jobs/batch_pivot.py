import os

from pyspark.sql import functions as F

from spark_session import get_spark_session

ES_NODES = os.getenv("ES_HOST", "localhost")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_INDEX = "vn-documents"
OUTPUT_PATH = "s3a://spark-output/daily-pivot/"

spark = get_spark_session("VnTextSearch-BatchPivot")

# Đọc toàn bộ index từ Elasticsearch, sau đó pivot số bài theo ngày × category
df_batch = (
    spark.read.format("org.elasticsearch.spark.sql")
    .option("es.nodes", ES_NODES)
    .option("es.port", ES_PORT)
    .option("es.resource", ES_INDEX)
    .load()
)

pivot_categories = ["thoi-su", "kinh-doanh", "the-thao", "giai-tri", "giao-duc"]

df_pivot = (
    df_batch
    .withColumn("date", F.to_date(F.col("published_at")))
    .groupBy("date")
    .pivot("category", pivot_categories)
    .agg(F.count("id"))
    .orderBy("date")
)

# fillna(0) để tránh null trong các category không có bài trong ngày đó
pivot_filled = df_pivot.fillna(0)

pivot_filled.show(20, truncate=False)
pivot_filled.write.mode("overwrite").parquet(OUTPUT_PATH)
