from __future__ import annotations
import argparse
import os
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from es_reader import DEFAULT_INDEX, get_spark, read_from_es

OUTPUT_PATH = os.getenv("TS_OUTPUT_PATH", "s3a://spark-output/time-series/")


def build_daily_series(df):
    return (
        df.filter(F.col("published_at").isNotNull())
          .filter(F.col("category").isNotNull())
          .withColumn("date", F.to_date("published_at"))
          .groupBy("date", "category")
          .agg(
              F.count("id").alias("doc_count"),
              F.avg(F.coalesce(F.col("token_count").cast("double"), F.lit(0.0)))
               .alias("avg_token_count"),
          )
          .orderBy("date", "category")
    )


def compute_moving_stats(df_daily):
    """7-day va 14-day moving average + rolling std."""
    w7  = Window.partitionBy("category").orderBy(F.col("date").cast("long")).rowsBetween(-6, 0)
    w14 = Window.partitionBy("category").orderBy(F.col("date").cast("long")).rowsBetween(-13, 0)
    return (
        df_daily
        .withColumn("ma7",  F.avg("doc_count").over(w7))
        .withColumn("std7", F.stddev("doc_count").over(w7))
        .withColumn("ma14", F.avg("doc_count").over(w14))
        .withColumn("min7", F.min("doc_count").over(w7))
        .withColumn("max7", F.max("doc_count").over(w7))
    )


def compute_growth_rates(df_ma):
    """Day-over-day va week-over-week growth rate dung lag()."""
    w = Window.partitionBy("category").orderBy("date")
    return (
        df_ma
        .withColumn("prev_day",  F.lag("doc_count", 1).over(w))
        .withColumn("prev_week", F.lag("doc_count", 7).over(w))
        .withColumn("dod_growth_pct",
            F.when(F.col("prev_day").isNotNull() & (F.col("prev_day") > 0),
                   (F.col("doc_count") - F.col("prev_day")) / F.col("prev_day") * 100)
            .otherwise(F.lit(None)))
        .withColumn("wow_growth_pct",
            F.when(F.col("prev_week").isNotNull() & (F.col("prev_week") > 0),
                   (F.col("doc_count") - F.col("prev_week")) / F.col("prev_week") * 100)
            .otherwise(F.lit(None)))
    )


def detect_trend(df_growth):
    """Trend = up/down/stable dua tren ma7 vs ma14."""
    return df_growth.withColumn(
        "trend",
        F.when(F.col("ma7") > F.col("ma14") * 1.05, F.lit("up"))
         .when(F.col("ma7") < F.col("ma14") * 0.95, F.lit("down"))
         .otherwise(F.lit("stable"))
    )


def detect_anomalies(df_trend):
    """Anomaly: |z-score| > 2 (mean +/- 2*std tren toan bo lich su per category)."""
    w_all = Window.partitionBy("category").rowsBetween(
        Window.unboundedPreceding, Window.unboundedFollowing
    )
    return (
        df_trend
        .withColumn("global_mean", F.avg("doc_count").over(w_all))
        .withColumn("global_std",  F.stddev("doc_count").over(w_all))
        .withColumn("z_score",
            F.when(F.col("global_std") > 0,
                   (F.col("doc_count") - F.col("global_mean")) / F.col("global_std"))
            .otherwise(F.lit(0.0)))
        .withColumn("is_anomaly", F.abs(F.col("z_score")) > 2.0)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index",  default=DEFAULT_INDEX)
    parser.add_argument("--output", default=OUTPUT_PATH)
    args = parser.parse_args()

    spark     = get_spark()
    df        = read_from_es(spark, index=args.index)
    df_daily  = build_daily_series(df)
    df_ma     = compute_moving_stats(df_daily)
    df_growth = compute_growth_rates(df_ma)
    df_trend  = detect_trend(df_growth)
    df_result = detect_anomalies(df_trend)

    print("=== Time Series: doc_count, MA7, growth rate, trend, anomaly ===")
    df_result.select(
        "date", "category", "doc_count",
        F.round("ma7", 2).alias("ma7"),
        F.round("dod_growth_pct", 2).alias("dod_%"),
        F.round("wow_growth_pct", 2).alias("wow_%"),
        "trend", "is_anomaly", F.round("z_score", 2).alias("z_score"),
    ).orderBy("category", "date").show(50, truncate=False)

    print("=== Anomaly days ===")
    df_result.filter(F.col("is_anomaly")).select(
        "date", "category", "doc_count",
        F.round("global_mean", 2).alias("mean"),
        F.round("global_std",  2).alias("std"),
        F.round("z_score",     2).alias("z_score"),
    ).orderBy(F.desc("z_score")).show(20, truncate=False)

    df_result.write.mode("overwrite").partitionBy("category").parquet(args.output)
    df_result.filter(F.col("is_anomaly")).write.mode("overwrite").parquet(
        args.output.rstrip("/") + "-anomalies/"
    )
    print(f"Saved -> {args.output}")


if __name__ == "__main__":
    main()
