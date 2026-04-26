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


def get_spark_session(app_name: str) -> SparkSession:
    """Create a shared SparkSession configuration for all Spark jobs."""
    builder = (
        SparkSession.builder.appName(app_name)
        .config("spark.jars.packages", SPARK_PACKAGES)
        .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000")
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin")
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin")
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
    )

    spark_master = os.getenv("SPARK_MASTER")
    if spark_master:
        builder = builder.master(spark_master)

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark
