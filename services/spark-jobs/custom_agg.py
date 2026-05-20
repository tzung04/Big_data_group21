from __future__ import annotations

import argparse

from pyspark.sql import functions as F
from pyspark.sql.window import Window

from es_reader import DEFAULT_INDEX, get_spark, read_from_es


DEFAULT_OUTPUT_PATH = "s3a://spark-output/category-aggregates/"


def compute_category_aggregates(df):
    token_count = F.coalesce(F.col("token_count").cast("double"), F.lit(0.0))
    is_long_doc = F.when(token_count > 500, F.lit(1.0)).otherwise(F.lit(0.0))

    df_agg = (
        df.filter(F.col("category").isNotNull())
        .withColumn("token_count_num", token_count)
        .withColumn("is_long", is_long_doc)
        .groupBy("category")
        .agg(
            F.count("id").alias("total_docs"),
            F.sum("is_long").alias("long_docs"),
            F.avg("token_count_num").alias("avg_tokens"),
            F.max("token_count_num").alias("max_tokens"),
            (F.sum("is_long") / F.count("id") * F.lit(100.0)).alias("long_doc_pct"),
        )
    )

    window_spec = Window.orderBy(F.desc("avg_tokens"))
    return df_agg.withColumn("rank", F.rank().over(window_spec))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute custom category aggregations and ranking by avg token count."
    )
    parser.add_argument("--index", default=DEFAULT_INDEX, help="Elasticsearch index name")
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_PATH,
        help="Output parquet path for custom aggregation results",
    )
    args = parser.parse_args()

    spark = get_spark()
    df = read_from_es(spark, index=args.index)
    df_ranked = compute_category_aggregates(df)

    df_ranked.orderBy("rank").show(truncate=False)
    df_ranked.write.mode("overwrite").parquet(args.output)
    print(f"Saved custom aggregations to: {args.output}")


if __name__ == "__main__":
    main()
