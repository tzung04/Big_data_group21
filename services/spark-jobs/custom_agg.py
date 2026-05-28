from __future__ import annotations
import argparse
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType
from pyspark.sql.window import Window
from es_reader import DEFAULT_INDEX, get_spark, read_from_es

DEFAULT_OUTPUT_PATH = "s3a://spark-output/category-aggregates/"


def _register_weighted_avg_udaf(spark):
    from pyspark.sql.functions import pandas_udf
    import pandas as pd
    import math

    @pandas_udf(returnType=DoubleType())
    def weighted_avg_tokens(token_counts: pd.Series) -> float:
        """UDAF: weighted average, trong so = log(token_count + 1).
        Dung math.log1p thay numpy de tranh phu thuoc numpy ngoai bundle."""
        values = token_counts.fillna(0).tolist()
        weights = [math.log1p(v) for v in values]
        total_weight = sum(weights)
        if total_weight == 0:
            return float(sum(values) / len(values)) if values else 0.0
        return float(sum(v * w for v, w in zip(values, weights)) / total_weight)

    spark.udf.register("weighted_avg_tokens", weighted_avg_tokens)
    return weighted_avg_tokens


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
            F.min("token_count_num").alias("min_tokens"),
            F.stddev("token_count_num").alias("stddev_tokens"),
            (F.sum("is_long") / F.count("id") * F.lit(100.0)).alias("long_doc_pct"),
        )
    )

    window_rank = Window.orderBy(F.desc("avg_tokens"))
    window_pct  = Window.orderBy(F.desc("total_docs"))

    return (
        df_agg
        .withColumn("rank_by_avg_tokens", F.rank().over(window_rank))
        .withColumn("rank_by_total_docs", F.rank().over(window_pct))
        .withColumn("pct_rank_docs", F.percent_rank().over(window_pct))
    )


def compute_weighted_avg_per_category(df, weighted_avg_udf):
    """UDAF: weighted average token_count per category."""
    return (
        df.filter(F.col("category").isNotNull())
        .withColumn("token_count_num",
                    F.coalesce(F.col("token_count").cast("double"), F.lit(0.0)))
        .groupBy("category")
        .agg(
            weighted_avg_udf(F.col("token_count_num")).alias("weighted_avg_tokens"),
            F.count("id").alias("total_docs"),
        )
        .orderBy(F.desc("weighted_avg_tokens"))
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default=DEFAULT_INDEX)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    spark = get_spark()
    weighted_avg_udf = _register_weighted_avg_udaf(spark)
    df = read_from_es(spark, index=args.index)

    df_ranked = compute_category_aggregates(df)
    print("=== Category aggregates with window ranking ===")
    df_ranked.orderBy("rank_by_avg_tokens").show(truncate=False)
    df_ranked.write.mode("overwrite").parquet(args.output)

    df_weighted = compute_weighted_avg_per_category(df, weighted_avg_udf)
    print("=== UDAF: Weighted average token count per category ===")
    df_weighted.show(truncate=False)
    df_weighted.write.mode("overwrite").parquet(args.output.rstrip("/") + "-weighted/")


if __name__ == "__main__":
    main()