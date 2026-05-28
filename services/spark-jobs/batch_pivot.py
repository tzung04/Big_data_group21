import os
from pyspark.sql import functions as F
from pyspark.sql import SparkSession
from spark_session import get_spark_session

ES_NODES = os.getenv("ES_HOST", "localhost")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_INDEX = "vn-documents"
OUTPUT_PATH = "s3a://spark-output/daily-pivot/"
UNPIVOT_OUTPUT_PATH = "s3a://spark-output/daily-unpivot/"

# Export ra ngoai de test_jobs.py co the import ma khong trigger code top-level
pivot_categories = ["thoi-su", "kinh-doanh", "the-thao", "giai-tri", "giao-duc"]


def run_pivot(spark: SparkSession, df=None):
    """
    Chay pivot + unpivot.
    df: truyen vao khi test; neu None thi doc tu Elasticsearch.
    """
    if df is None:
        df = (
            spark.read.format("org.elasticsearch.spark.sql")
            .option("es.nodes", ES_NODES)
            .option("es.port", ES_PORT)
            .option("es.resource", ES_INDEX)
            .load()
        )

    # PIVOT: long -> wide (ngay x category)
    df_pivot = (
        df
        .withColumn("date", F.to_date(F.col("published_at")))
        .groupBy("date")
        .pivot("category", pivot_categories)
        .agg(F.count("id"))
        .orderBy("date")
    )
    pivot_filled = df_pivot.fillna(0)

    print("=== PIVOT ===")
    pivot_filled.show(20, truncate=False)
    pivot_filled.write.mode("overwrite").parquet(OUTPUT_PATH)

    # UNPIVOT: wide -> long dung stack()
    stack_expr = "stack({n}, {pairs}) as (category, doc_count)".format(
        n=len(pivot_categories),
        pairs=", ".join(f"'{cat}', `{cat}`" for cat in pivot_categories),
    )
    df_unpivot = (
        pivot_filled
        .select("date", F.expr(stack_expr))
        .filter(F.col("doc_count") > 0)
        .orderBy("date", "category")
    )

    print("=== UNPIVOT ===")
    df_unpivot.show(30, truncate=False)
    df_unpivot.write.mode("overwrite").parquet(UNPIVOT_OUTPUT_PATH)

    print(f"Saved pivot   -> {OUTPUT_PATH}")
    print(f"Saved unpivot -> {UNPIVOT_OUTPUT_PATH}")

    return pivot_filled, df_unpivot


if __name__ == "__main__":
    spark = get_spark_session("VnTextSearch-BatchPivot")
    run_pivot(spark)