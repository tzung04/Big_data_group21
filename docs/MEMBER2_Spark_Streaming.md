# Member 2 — Spark Streaming / Data Engineer (Windows)
> Đọc SHARED_CONTRACTS.md trước. Làm việc trong `services/spark-jobs/`

---

## Setup máy Windows

```bash
# Trong WSL Ubuntu terminal
sudo apt install -y openjdk-11-jdk
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
echo 'export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64' >> ~/.bashrc

pip install pyspark==3.5.1 kafka-python==2.0.2 elasticsearch==8.13.0 underthesea boto3
```

---

## Tuần 1 (Ngày 3–7)

### Task 1: Spark Structured Streaming cơ bản
File: `services/spark-jobs/streaming_indexer.py`

```python
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import *

spark = SparkSession.builder \
    .appName("VnTextSearch-Streaming") \
    .config("spark.jars.packages",
            "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,"
            "org.elasticsearch:elasticsearch-spark-30_2.12:8.13.0") \
    .config("spark.sql.streaming.checkpointLocation", "s3a://spark-checkpoints/streaming") \
    .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000") \
    .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
    .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
    .config("spark.hadoop.fs.s3a.path.style.access", "true") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# Schema theo SHARED_CONTRACTS.md
schema = StructType([
    StructField("id", StringType()),
    StructField("title", StringType()),
    StructField("content", StringType()),
    StructField("url", StringType()),
    StructField("category", StringType()),
    StructField("source", StringType()),
    StructField("published_at", StringType()),
    StructField("crawled_at", StringType())
])

# Đọc từ Kafka topic raw-documents
df_raw = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "raw-documents") \
    .option("startingOffsets", "latest") \
    .load()

df_parsed = df_raw \
    .select(F.from_json(F.col("value").cast("string"), schema).alias("data")) \
    .select("data.*") \
    .withColumn("published_at", F.to_timestamp("published_at")) \
    .withColumn("crawled_at", F.to_timestamp("crawled_at"))

# Watermark xử lý late data (yêu cầu đề bài)
df_watermarked = df_parsed.withWatermark("published_at", "10 minutes")

# Ghi vào Elasticsearch
query = df_watermarked.writeStream \
    .outputMode("append") \
    .format("org.elasticsearch.spark.sql") \
    .option("es.nodes", "localhost") \
    .option("es.port", "9200") \
    .option("es.resource", "vn-documents") \
    .option("es.mapping.id", "id") \
    .option("es.write.operation", "upsert") \
    .option("checkpointLocation", "s3a://spark-checkpoints/streaming") \
    .start()

query.awaitTermination()
```

Chạy thử:
```bash
spark-submit \
  --master spark://localhost:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.elasticsearch:elasticsearch-spark-30_2.12:8.13.0,org.apache.hadoop:hadoop-aws:3.3.4 \
  services/spark-jobs/streaming_indexer.py
```

---

## Tuần 2 (Ngày 8–12)

### Task 2: UDF tokenize tiếng Việt (yêu cầu đề bài)
File: `services/spark-jobs/udfs.py`

```python
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, StringType

def get_vi_tokenize_udf():
    """UDF tokenize tiếng Việt dùng underthesea"""
    @F.udf(returnType=ArrayType(StringType()))
    def vi_tokenize(text):
        if not text:
            return []
        try:
            from underthesea import word_tokenize
            tokens = word_tokenize(text, format='list')
            # Lọc stopwords đơn giản
            stopwords = {'và', 'của', 'là', 'có', 'cho', 'với', 'các', 'được', 'trong', 'này'}
            return [t.lower() for t in tokens if t not in stopwords and len(t) > 1]
        except:
            return text.lower().split()
    return vi_tokenize
```

Thêm vào streaming_indexer.py sau khi parse:
```python
from udfs import get_vi_tokenize_udf
vi_tokenize = get_vi_tokenize_udf()

df_processed = df_watermarked \
    .withColumn("tokens", vi_tokenize(F.col("content"))) \
    .withColumn("token_count", F.size(F.col("tokens"))) \
    .withColumn("indexed_at", F.current_timestamp())
```

### Task 3: Window functions — thống kê real-time (yêu cầu đề bài)
File: `services/spark-jobs/window_stats.py`

```python
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.window import Window

# Job riêng đọc từ Kafka, tính thống kê theo window
df_stats = df_watermarked \
    .groupBy(
        F.window("published_at", "1 hour", "30 minutes"),  # sliding window
        F.col("category")
    ) \
    .agg(
        F.count("id").alias("doc_count"),
        F.avg("token_count").alias("avg_tokens")
    )

# Window function: rank category theo số bài
window_spec = Window.partitionBy("window").orderBy(F.desc("doc_count"))
df_ranked = df_stats.withColumn("rank", F.rank().over(window_spec))

# Ghi ra console để debug
query = df_ranked.writeStream \
    .outputMode("complete") \
    .format("console") \
    .option("truncate", False) \
    .start()
```

### Task 4: Pivot thống kê (yêu cầu đề bài)
File: `services/spark-jobs/batch_pivot.py`

```python
# Batch job: pivot số bài theo ngày x category
df_batch = spark.read \
    .format("org.elasticsearch.spark.sql") \
    .option("es.nodes", "localhost") \
    .option("es.resource", "vn-documents") \
    .load()

df_pivot = df_batch \
    .withColumn("date", F.to_date("published_at")) \
    .groupBy("date") \
    .pivot("category", ["thoi-su", "kinh-doanh", "the-thao", "giai-tri"]) \
    .agg(F.count("id")) \
    .orderBy("date")

df_pivot.show(20)
df_pivot.write.mode("overwrite").parquet("s3a://spark-output/daily-pivot/")
```

---

## Tuần 3 (Ngày 15–17)

### Task 5: Tối ưu hiệu năng (yêu cầu đề bài)

```python
# Partition pruning: đọc data theo ngày
df_optimized = spark.read.parquet("s3a://spark-output/") \
    .filter(F.col("published_at") >= "2024-01-01")  # partition pruning

# Cache reference table nhỏ (broadcast join)
df_categories = spark.createDataFrame([
    ("thoi-su", "Thời sự"), ("kinh-doanh", "Kinh doanh"),
    ("the-thao", "Thể thao"), ("giai-tri", "Giải trí")
], ["category_id", "category_name"])
df_categories.cache()  # cache vì nhỏ, dùng nhiều lần

# Broadcast join (yêu cầu đề bài)
from pyspark.sql.functions import broadcast
df_enriched = df_batch.join(broadcast(df_categories), on="category", how="left")
df_categories.unpersist()  # giải phóng sau khi dùng xong
```

### Task 6: Viết unit test
File: `services/spark-jobs/test_udfs.py`

```python
import pytest
from pyspark.sql import SparkSession
from udfs import get_vi_tokenize_udf
import pyspark.sql.functions as F

@pytest.fixture(scope="session")
def spark():
    return SparkSession.builder.master("local[1]").appName("test").getOrCreate()

def test_vi_tokenize(spark):
    vi_tokenize = get_vi_tokenize_udf()
    df = spark.createDataFrame([("Hà Nội là thủ đô của Việt Nam",)], ["text"])
    result = df.withColumn("tokens", vi_tokenize(F.col("text"))).collect()
    assert len(result[0]["tokens"]) > 0

def test_vi_tokenize_empty(spark):
    vi_tokenize = get_vi_tokenize_udf()
    df = spark.createDataFrame([(None,)], ["text"])
    result = df.withColumn("tokens", vi_tokenize(F.col("text"))).collect()
    assert result[0]["tokens"] == []
```
```bash
pytest services/spark-jobs/test_udfs.py -v
```
