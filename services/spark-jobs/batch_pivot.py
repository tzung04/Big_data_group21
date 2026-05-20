from pyspark.sql import SparkSession
from pyspark.sql import functions as F

ES_NODES = "localhost"
ES_PORT = "9200"
ES_INDEX = "vn-documents"
OUTPUT_PATH = "s3a://spark-output/daily-pivot/"

spark = (
    SparkSession.builder.appName("VnTextSearch-BatchPivot")
    .config(
        "spark.jars.packages",
        "org.elasticsearch:elasticsearch-spark-30_2.12:8.13.0,"
        "org.apache.hadoop:hadoop-aws:3.3.4",
    )
    .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000")
    .config("spark.hadoop.fs.s3a.access.key", "minioadmin")
    .config("spark.hadoop.fs.s3a.secret.key", "minioadmin")
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

# Đọc dữ liệu đã được index từ Elasticsearch index vn-documents
# Sau đó pivot số bài theo ngày x category

df_batch = (
    spark.read.format("org.elasticsearch.spark.sql")
    .option("es.nodes", ES_NODES)
    .option("es.port", ES_PORT)
    .option("es.resource", ES_INDEX)
    .load()
)

pivot_categories = ["thoi-su", "kinh-doanh", "the-thao", "giai-tri"]

df_pivot = (
    df_batch.withColumn("date", F.to_date(F.col("published_at")))
    .groupBy("date")
    .pivot("category", pivot_categories)
    .agg(F.count("id"))
    .orderBy("date")
)

# Điền 0 cho các category không có dữ liệu trong một ngày
pivot_filled = df_pivot.fillna(0)

pivot_filled.show(20, truncate=False)

pivot_filled.write.mode("overwrite").parquet(OUTPUT_PATH)
