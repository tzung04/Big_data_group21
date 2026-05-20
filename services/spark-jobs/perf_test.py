from __future__ import annotations

import argparse
import time

from es_reader import DEFAULT_INDEX, get_spark, read_from_es


def _run_count(df) -> tuple[int, float]:
    start = time.perf_counter()
    count = df.count()
    duration = time.perf_counter() - start
    return count, duration


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure read/count performance with and without Spark cache."
    )
    parser.add_argument("--index", default=DEFAULT_INDEX, help="Elasticsearch index name")
    args = parser.parse_args()

    spark = get_spark()
    df = read_from_es(spark, index=args.index)

    count_without_cache, time_without_cache = _run_count(df)
    print(f"Without cache: {time_without_cache:.2f}s, {count_without_cache} docs")

    df.cache()
    _, cache_build_time = _run_count(df)
    count_with_cache, cached_time = _run_count(df)
    df.unpersist()

    print(f"With cache (build): {cache_build_time:.2f}s")
    print(f"With cache (2nd run): {cached_time:.2f}s, {count_with_cache} docs")


if __name__ == "__main__":
    main()
