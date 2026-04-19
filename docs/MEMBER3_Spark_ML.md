# Member 3 — Spark ML / Batch Jobs (Windows)
> Đọc SHARED_CONTRACTS.md trước. Làm việc trong `services/spark-jobs/`
> Phối hợp với Member 2 — dùng chung SparkSession config, không tạo riêng

---

## Setup máy Windows

```bash
# Trong WSL Ubuntu terminal — giống Member 2
sudo apt install -y openjdk-11-jdk
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
echo 'export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64' >> ~/.bashrc

pip install pyspark==3.5.1 elasticsearch==8.13.0 boto3
```

---

## Tuần 1 (Ngày 5–7)

### Task 1: Đọc data từ Elasticsearch về Spark
File: `services/spark-jobs/es_reader.py`

```python
from pyspark.sql import SparkSession
import pyspark.sql.functions as F

def get_spark():
    return SparkSession.builder \
        .appName("VnTextSearch-Batch") \
        .config("spark.jars.packages",
                "org.elasticsearch:elasticsearch-spark-30_2.12:8.13.0,"
                "org.apache.hadoop:hadoop-aws:3.3.4") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000") \
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .getOrCreate()

def read_from_es(spark, index="vn-documents"):
    return spark.read \
        .format("org.elasticsearch.spark.sql") \
        .option("es.nodes", "localhost") \
        .option("es.port", "9200") \
        .option("es.resource", index) \
        .load()

if __name__ == "__main__":
    spark = get_spark()
    df = read_from_es(spark)
    print(f"Total documents: {df.count()}")
    df.printSchema()
    df.show(5)
```

---

## Tuần 2 (Ngày 9–13)

### Task 2: MLlib — phân loại chủ đề (yêu cầu đề bài)
File: `services/spark-jobs/ml_classifier.py`

```python
from pyspark.ml import Pipeline
from pyspark.ml.feature import HashingTF, IDF, Tokenizer, StopWordsRemover
from pyspark.ml.classification import NaiveBayes
from pyspark.ml.evaluation import MulticlassClassificationEvaluator
from pyspark.sql import functions as F
from es_reader import get_spark, read_from_es

spark = get_spark()
df = read_from_es(spark).filter(F.col("category").isNotNull())

# Encode label
categories = ["thoi-su", "kinh-doanh", "the-thao", "giai-tri"]
category_index = {cat: float(i) for i, cat in enumerate(categories)}

@F.udf(returnType="double")
def encode_label(category):
    return category_index.get(category, 0.0)

df = df.withColumn("label", encode_label(F.col("category")))

# Pipeline: Tokenize → TF → IDF → NaiveBayes
tokenizer = Tokenizer(inputCol="content", outputCol="words")
remover = StopWordsRemover(inputCol="words", outputCol="filtered")
hashingTF = HashingTF(inputCol="filtered", outputCol="rawFeatures", numFeatures=10000)
idf = IDF(inputCol="rawFeatures", outputCol="features")
nb = NaiveBayes(smoothing=1.0, modelType="multinomial")

pipeline = Pipeline(stages=[tokenizer, remover, hashingTF, idf, nb])

# Train / test split
train_df, test_df = df.randomSplit([0.8, 0.2], seed=42)
model = pipeline.fit(train_df)

# Đánh giá
predictions = model.transform(test_df)
evaluator = MulticlassClassificationEvaluator(metricName="accuracy")
accuracy = evaluator.evaluate(predictions)
print(f"Accuracy: {accuracy:.4f}")

# Lưu model
model.write().overwrite().save("s3a://spark-output/topic-classifier/")

# Thêm topic_label vào tất cả documents
df_all = read_from_es(spark)
df_labeled = model.transform(
    tokenizer.transform(
        df_all.withColumn("words", F.split("content", " "))
    )
)

decode = {v: k for k, v in category_index.items()}

@F.udf(returnType="string")
def decode_label(pred):
    return decode.get(pred, "unknown")

df_labeled = df_labeled.withColumn("topic_label", decode_label(F.col("prediction")))
df_labeled.write.mode("overwrite").parquet("s3a://spark-output/labeled-documents/")
```

### Task 3: Sort-merge join (yêu cầu đề bài)
File: `services/spark-jobs/enricher.py`

```python
from es_reader import get_spark, read_from_es
from pyspark.sql import functions as F

spark = get_spark()

# Bảng lớn: documents từ ES
df_docs = read_from_es(spark)

# Bảng thống kê lớn: số bài theo category theo ngày
df_stats = df_docs \
    .withColumn("date", F.to_date("published_at")) \
    .groupBy("category", "date") \
    .agg(F.count("id").alias("daily_count"))

# Sort-merge join (yêu cầu đề bài) — cả 2 bảng đều lớn
df_docs_with_date = df_docs.withColumn("date", F.to_date("published_at"))

# Spark tự chọn sort-merge join khi 2 bảng đều lớn
df_enriched = df_docs_with_date.join(df_stats, on=["category", "date"], how="left")

df_enriched \
    .select("id", "title", "category", "date", "daily_count") \
    .write.mode("overwrite") \
    .parquet("s3a://spark-output/enriched-documents/")

print("Enriched documents saved.")
```

### Task 4: Custom aggregation (yêu cầu đề bài)
File: `services/spark-jobs/custom_agg.py`

```python
from es_reader import get_spark, read_from_es
from pyspark.sql import functions as F
from pyspark.sql.window import Window

spark = get_spark()
df = read_from_es(spark)

# Hàm tổng hợp tùy biến: tỷ lệ bài dài (> 500 tokens) theo category
@F.udf(returnType="double")
def long_doc_ratio(token_count):
    return 1.0 if (token_count or 0) > 500 else 0.0

df_agg = df \
    .withColumn("is_long", long_doc_ratio(F.col("token_count"))) \
    .groupBy("category") \
    .agg(
        F.count("id").alias("total_docs"),
        F.sum("is_long").alias("long_docs"),
        F.avg("token_count").alias("avg_tokens"),
        F.max("token_count").alias("max_tokens"),
        (F.sum("is_long") / F.count("id") * 100).alias("long_doc_pct")
    )

# Window function: rank category theo avg_tokens
window_spec = Window.orderBy(F.desc("avg_tokens"))
df_ranked = df_agg.withColumn("rank", F.rank().over(window_spec))
df_ranked.show()
```

---

## Tuần 3 (Ngày 15–17)

### Task 5: Performance test
File: `services/spark-jobs/perf_test.py`

```python
import time
from es_reader import get_spark, read_from_es

spark = get_spark()

# Test 1: đọc không cache
start = time.time()
df = read_from_es(spark)
count1 = df.count()
print(f"Without cache: {time.time()-start:.2f}s, {count1} docs")

# Test 2: với cache
start = time.time()
df.cache()
count2 = df.count()  # lần đầu build cache
count3 = df.count()  # lần 2 từ cache
print(f"With cache (2nd run): {time.time()-start:.2f}s")
df.unpersist()
```

### Task 6: Integration test
File: `services/spark-jobs/test_jobs.py`

```python
import pytest
from pyspark.sql import SparkSession
import pyspark.sql.functions as F

@pytest.fixture(scope="session")
def spark():
    return SparkSession.builder.master("local[2]").appName("test").getOrCreate()

def test_enricher_join(spark):
    docs = spark.createDataFrame([
        ("1", "thoi-su", "2024-01-15"), ("2", "thoi-su", "2024-01-15"),
        ("3", "kinh-doanh", "2024-01-15")
    ], ["id", "category", "date"])

    stats = spark.createDataFrame([
        ("thoi-su", "2024-01-15", 2), ("kinh-doanh", "2024-01-15", 1)
    ], ["category", "date", "daily_count"])

    result = docs.join(stats, on=["category", "date"], how="left")
    assert result.count() == 3
    assert result.filter(F.col("category") == "thoi-su").first()["daily_count"] == 2
```
```bash
pytest services/spark-jobs/test_jobs.py -v
```
