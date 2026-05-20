from __future__ import annotations

import pyspark.sql.functions as F
import pytest
from pyspark.sql import SparkSession

from enricher import enrich_documents


@pytest.fixture(scope="session")
def spark() -> SparkSession:
    session = SparkSession.builder.master("local[2]").appName("spark-jobs-test").getOrCreate()
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def test_enricher_join_daily_count(spark: SparkSession) -> None:
    docs = spark.createDataFrame(
        [
            ("1", "A", "thoi-su", "2024-01-15T08:00:00Z"),
            ("2", "B", "thoi-su", "2024-01-15T09:00:00Z"),
            ("3", "C", "kinh-doanh", "2024-01-15T10:00:00Z"),
        ],
        ["id", "title", "category", "published_at"],
    )

    result = enrich_documents(docs)

    assert result.count() == 3

    thoi_su_count = (
        result.filter((F.col("category") == "thoi-su") & (F.col("id") == "1"))
        .select("daily_count")
        .first()["daily_count"]
    )
    assert thoi_su_count == 2


def test_enricher_drop_invalid_category_or_date(spark: SparkSession) -> None:
    docs = spark.createDataFrame(
        [
            ("1", "Valid", "thoi-su", "2024-01-15T08:00:00Z"),
            ("2", "Missing Category", None, "2024-01-15T09:00:00Z"),
            ("3", "Bad Date", "the-thao", "not-a-date"),
        ],
        ["id", "title", "category", "published_at"],
    )

    result_ids = {row["id"] for row in enrich_documents(docs).select("id").collect()}
    assert result_ids == {"1"}
