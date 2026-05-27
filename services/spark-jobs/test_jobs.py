from __future__ import annotations
import math
import pyspark.sql.functions as F
import pytest
from pyspark.sql import SparkSession
from pyspark.sql.types import DoubleType

from enricher import enrich_documents
from udfs import get_vi_tokenize_udf
from custom_agg import compute_category_aggregates, _register_weighted_avg_udaf
from batch_pivot import pivot_categories
from time_series import (
    build_daily_series, compute_moving_stats,
    compute_growth_rates, detect_trend, detect_anomalies,
)


@pytest.fixture(scope="session")
def spark() -> SparkSession:
    s = (SparkSession.builder.master("local[2]").appName("test")
         .config("spark.sql.shuffle.partitions", "2").getOrCreate())
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()


# --- enricher ---

def test_enricher_daily_count(spark):
    docs = spark.createDataFrame(
        [("1","A","thoi-su","2024-01-15T08:00:00Z"),
         ("2","B","thoi-su","2024-01-15T09:00:00Z"),
         ("3","C","kinh-doanh","2024-01-15T10:00:00Z")],
        ["id","title","category","published_at"])
    result = enrich_documents(docs)
    assert result.count() == 3
    count = (result.filter((F.col("category")=="thoi-su")&(F.col("id")=="1"))
             .select("daily_count").first()["daily_count"])
    assert count == 2

def test_enricher_drop_invalid(spark):
    docs = spark.createDataFrame(
        [("1","V","thoi-su","2024-01-15T08:00:00Z"),
         ("2","M",None,"2024-01-15T09:00:00Z"),
         ("3","B","the-thao","not-a-date")],
        ["id","title","category","published_at"])
    ids = {r["id"] for r in enrich_documents(docs).select("id").collect()}
    assert ids == {"1"}

def test_enricher_multiple_categories(spark):
    docs = spark.createDataFrame(
        [("1","A","the-thao","2024-02-01T08:00:00Z"),
         ("2","B","the-thao","2024-02-01T09:00:00Z"),
         ("3","C","the-thao","2024-02-01T10:00:00Z"),
         ("4","D","kinh-doanh","2024-02-01T08:00:00Z")],
        ["id","title","category","published_at"])
    result = enrich_documents(docs)
    assert result.filter(F.col("category")=="the-thao").first()["daily_count"] == 3
    assert result.filter(F.col("category")=="kinh-doanh").first()["daily_count"] == 1


# --- udfs ---

def test_vi_tokenize_basic(spark):
    vi_tokenize = get_vi_tokenize_udf()
    df = spark.createDataFrame([("Ha Noi va Viet Nam co nhieu di san",)], ["text"])
    tokens = df.withColumn("t", vi_tokenize(F.col("text"))).first()["t"]
    assert isinstance(tokens, list) and len(tokens) > 0
    assert "va" not in tokens

def test_vi_tokenize_empty(spark):
    vi_tokenize = get_vi_tokenize_udf()
    df = spark.createDataFrame([("",), (None,)], ["text"])
    for row in df.withColumn("t", vi_tokenize(F.col("text"))).collect():
        assert row["t"] == []

def test_vi_tokenize_single_char(spark):
    vi_tokenize = get_vi_tokenize_udf()
    df = spark.createDataFrame([("a b c hello world",)], ["text"])
    tokens = df.withColumn("t", vi_tokenize(F.col("text"))).first()["t"]
    for t in tokens:
        assert len(t) > 1


# --- custom_agg ---

def test_category_aggregate_rank(spark):
    df = spark.createDataFrame(
        [("1","thoi-su",100),("2","thoi-su",200),
         ("3","kinh-doanh",50),("4","kinh-doanh",60)],
        ["id","category","token_count"])
    rows = {r["category"]: r for r in compute_category_aggregates(df).collect()}
    assert rows["thoi-su"]["rank_by_avg_tokens"] == 1
    assert rows["kinh-doanh"]["rank_by_avg_tokens"] == 2

def test_weighted_avg_udaf(spark):
    udf = _register_weighted_avg_udaf(spark)
    df = (spark.createDataFrame([("cat",10),("cat",10),("cat",1000)], ["category","token_count"])
          .withColumn("token_count", F.col("token_count").cast(DoubleType())))
    row = df.groupBy("category").agg(
        udf(F.col("token_count")).alias("wa"), F.avg("token_count").alias("sa")
    ).first()
    assert row["wa"] > row["sa"]


# --- pivot/unpivot ---

def test_pivot_columns(spark):
    df = spark.createDataFrame(
        [("1","thoi-su","2024-01-01T00:00:00Z"),
         ("2","kinh-doanh","2024-01-01T00:00:00Z"),
         ("3","the-thao","2024-01-02T00:00:00Z")],
        ["id","category","published_at"])
    df_p = (df.withColumn("date", F.to_date("published_at"))
            .groupBy("date").pivot("category", pivot_categories).agg(F.count("id")).fillna(0))
    assert len(df_p.columns) == 1 + len(pivot_categories)

def test_unpivot_row_count(spark):
    df = spark.createDataFrame(
        [("1","thoi-su","2024-01-01T00:00:00Z"),
         ("2","kinh-doanh","2024-01-01T00:00:00Z"),
         ("3","the-thao","2024-01-01T00:00:00Z")],
        ["id","category","published_at"])
    df_p = (df.withColumn("date", F.to_date("published_at"))
            .groupBy("date").pivot("category", pivot_categories).agg(F.count("id")).fillna(0))
    stack_expr = "stack({n},{pairs}) as (category,doc_count)".format(
        n=len(pivot_categories),
        pairs=", ".join(f"'{c}',`{c}`" for c in pivot_categories))
    df_u = df_p.select("date", F.expr(stack_expr)).filter(F.col("doc_count") > 0)
    assert df_u.count() == 3


# --- time_series ---

def _ts_df(spark):
    rows = [( f"d{d}_{i}", "thoi-su", 100, f"2024-01-{d:02d}T10:00:00Z")
            for d in range(1,15) for i in range(5)]
    rows += [(f"s{i}", "thoi-su", 200, "2024-01-10T10:00:00Z") for i in range(50)]
    df = spark.createDataFrame(rows, ["id","category","token_count","published_at"])
    return df.withColumn("published_at", F.to_timestamp("published_at"))

def test_moving_average_first_day(spark):
    df_daily = build_daily_series(_ts_df(spark))
    df_ma    = compute_moving_stats(df_daily)
    rows     = df_ma.filter(F.col("category")=="thoi-su").orderBy("date").collect()
    assert rows[0]["ma7"] is not None
    assert math.isclose(rows[0]["ma7"], rows[0]["doc_count"], rel_tol=1e-6)

def test_anomaly_spike(spark):
    df = _ts_df(spark)
    df_r = detect_anomalies(detect_trend(compute_growth_rates(
        compute_moving_stats(build_daily_series(df)))))
    row = df_r.filter((F.col("category")=="thoi-su")&(F.col("date")==F.lit("2024-01-10"))).first()
    assert row is not None and row["is_anomaly"] is True

def test_dod_growth_rate(spark):
    df = spark.createDataFrame(
        [("1","thoi-su",10,"2024-01-01T00:00:00Z"),
         ("2","thoi-su",10,"2024-01-01T01:00:00Z"),
         ("3","thoi-su",10,"2024-01-02T00:00:00Z"),
         ("4","thoi-su",10,"2024-01-02T01:00:00Z"),
         ("5","thoi-su",10,"2024-01-02T02:00:00Z"),
         ("6","thoi-su",10,"2024-01-02T03:00:00Z")],
        ["id","category","token_count","published_at"])
    df = df.withColumn("published_at", F.to_timestamp("published_at"))
    rows = {str(r["date"]): r for r in
            compute_growth_rates(compute_moving_stats(build_daily_series(df))).collect()}
    assert math.isclose(rows["2024-01-02"]["dod_growth_pct"], 100.0, rel_tol=1e-4)