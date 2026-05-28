from __future__ import annotations

import os

from pyspark.sql import SparkSession

SPARK_PACKAGES = ",".join(
    [
        "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1",
        "org.elasticsearch:elasticsearch-spark-30_2.12:8.13.0",
        "org.apache.hadoop:hadoop-aws:3.3.4",
    ]
)

_MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
_MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
_MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")


def get_spark_session(app_name: str) -> SparkSession:
    builder = (
        SparkSession.builder.appName(app_name)
        .config("spark.jars.packages", SPARK_PACKAGES)
        .config("spark.hadoop.fs.s3a.endpoint", _MINIO_ENDPOINT)
        .config("spark.hadoop.fs.s3a.access.key", _MINIO_ACCESS_KEY)
        .config("spark.hadoop.fs.s3a.secret.key", _MINIO_SECRET_KEY)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
    )

    spark_master = os.getenv("SPARK_MASTER")
    if spark_master:
        builder = builder.master(spark_master)

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark
