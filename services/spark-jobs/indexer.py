from spark_session import get_spark_session

# Khởi tạo Spark
spark = get_spark_session("VnTextSearch-Indexer")

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
