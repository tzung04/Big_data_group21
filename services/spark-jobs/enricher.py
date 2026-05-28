"""
enricher.py
Join 1: sort-merge join (large x large) - df_docs x df_daily_stats
Join 2: broadcast join  (large x small) - result x df_category_meta
Cache df_prepared vi dung 2 lan.
"""
from __future__ import annotations
import argparse
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.functions import broadcast
from es_reader import DEFAULT_INDEX, get_spark, read_from_es

DEFAULT_OUTPUT_PATH = "s3a://spark-output/enriched-documents/"

CATEGORY_META = [
    ("thoi-su",    "Thoi su",    "news"),
    ("kinh-doanh", "Kinh doanh", "business"),
    ("the-thao",   "The thao",   "sports"),
    ("giai-tri",   "Giai tri",   "entertainment"),
    ("giao-duc",   "Giao duc",   "education"),
]


def prepare_documents(df_docs: DataFrame) -> DataFrame:
    return (
        df_docs.select("id", "title", "category", "published_at", "token_count")
        .withColumn("date", F.to_date("published_at"))
        .filter(F.col("category").isNotNull())
        .filter(F.col("date").isNotNull())
    )


def build_daily_stats(df_prepared: DataFrame) -> DataFrame:
    return (
        df_prepared.groupBy("category", "date")
        .agg(
            F.count("id").alias("daily_count"),
            F.avg(F.coalesce(F.col("token_count").cast("double"), F.lit(0.0)))
             .alias("daily_avg_tokens"),
        )
        .hint("merge")
    )


def enrich_documents(df_docs: DataFrame) -> DataFrame:
    spark = df_docs.sparkSession
    df_prepared = prepare_documents(df_docs)
    df_prepared.cache()

    df_stats = build_daily_stats(df_prepared)

    # Join 1: sort-merge (tat auto-broadcast de dam bao SortMergeJoin)
    spark.conf.set("spark.sql.autoBroadcastJoinThreshold", -1)
    df_joined = df_prepared.hint("merge").join(df_stats, on=["category", "date"], how="left")

    # Join 2: broadcast
    spark.conf.set("spark.sql.autoBroadcastJoinThreshold", 10 * 1024 * 1024)
    df_meta = spark.createDataFrame(CATEGORY_META, ["category_id", "category_name", "category_en"])
    df_meta.cache()

    df_enriched = (
        df_joined.join(broadcast(df_meta),
                       df_joined["category"] == df_meta["category_id"], how="left")
        .select("id", "title", "category", "category_name", "category_en",
                "date", "daily_count", "daily_avg_tokens")
    )

    df_meta.unpersist()
    df_prepared.unpersist()
    return df_enriched


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index",  default=DEFAULT_INDEX)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    spark = get_spark()
    spark.conf.set("spark.sql.autoBroadcastJoinThreshold", -1)

    df_docs     = read_from_es(spark, index=args.index)
    df_enriched = enrich_documents(df_docs)

    print("=== Query Plan (SortMergeJoin + BroadcastHashJoin) ===")
    df_enriched.explain(mode="formatted")

    df_enriched.write.mode("overwrite").parquet(args.output)
    print(f"Saved -> {args.output}")


if __name__ == "__main__":
    main()
