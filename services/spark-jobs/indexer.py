from pyspark.sql import SparkSession
from pyspark.sql import functions as F

# Khởi tạo Spark
spark = SparkSession.builder \
    .appName("VnTextSearch-Indexer") \
    .getOrCreate()

print("Spark Started")

# Đọc stream từ Kafka
df_stream = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "raw-documents") \
    .option("startingOffsets", "latest") \
    .load()

# Convert dữ liệu Kafka (binary → string)
df_value = df_stream.selectExpr("CAST(value AS STRING) as json")

# In ra dữ liệu để kiểm tra
query = df_value.writeStream \
    .outputMode("append") \
    .format("console") \
    .option("truncate", False) \
    .start()

query.awaitTermination()