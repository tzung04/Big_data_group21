from __future__ import annotations

import argparse

import pyspark.sql.functions as F
from pyspark.sql import DataFrame
from pyspark.sql import SparkSession

from spark_session import get_spark_session


ES_HOST = "localhost"
ES_PORT = "9200"
DEFAULT_INDEX = "vn-documents"


def get_spark() -> SparkSession:
    return get_spark_session("VnTextSearch-Batch")


def read_from_es(spark: SparkSession, index: str = DEFAULT_INDEX) -> DataFrame:
    return (
        spark.read.format("org.elasticsearch.spark.sql")
        .option("es.nodes", ES_HOST)
        .option("es.port", ES_PORT)
        .option("es.resource", index)
        .load()
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read vn-documents index from Elasticsearch into Spark"
    )
    parser.add_argument("--index", default=DEFAULT_INDEX, help="Elasticsearch index name")
    parser.add_argument("--limit", type=int, default=5, help="Number of records to show")
    args = parser.parse_args()

    spark = get_spark()
    df = read_from_es(spark, index=args.index)

    total_docs = df.select(F.count("*").alias("total")).collect()[0]["total"]
    print(f"Index: {args.index}")
    print(f"Total documents: {total_docs}")
    df.printSchema()
    df.show(args.limit, truncate=False)


if __name__ == "__main__":
    main()
