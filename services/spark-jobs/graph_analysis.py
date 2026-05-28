from __future__ import annotations
import argparse
import os
from pyspark.sql import functions as F
from es_reader import DEFAULT_INDEX, get_spark, read_from_es

MIN_SHARED_TOKENS = int(os.getenv("GRAPH_MIN_SHARED_TOKENS", "3"))
PAGERANK_RESET    = float(os.getenv("GRAPH_PAGERANK_RESET", "0.15"))
PAGERANK_ITER     = int(os.getenv("GRAPH_PAGERANK_ITER", "5"))
OUTPUT_PATH       = os.getenv("GRAPH_OUTPUT_PATH", "s3a://spark-output/graph-analysis/")


def build_vertices(df):
    return (
        df.select(
            F.col("id"),
            F.coalesce(F.col("category"),    F.lit("unknown")).alias("category"),
            F.coalesce(F.col("topic_label"), F.lit("unknown")).alias("topic_label"),
            F.coalesce(F.col("token_count").cast("long"), F.lit(0)).alias("token_count"),
        )
        .dropDuplicates(["id"])
        .filter(F.col("id").isNotNull())
    )


def build_edges(df, min_shared: int = MIN_SHARED_TOKENS):
    """Edge: 2 bai cung category co >= min_shared token chung."""
    df_clean = (
        df.filter(F.col("id").isNotNull())
          .filter(F.col("category").isNotNull())
          .filter(F.col("tokens").isNotNull())
          .select("id", "category", "tokens")
    )
    return (
        df_clean.alias("a")
        .join(df_clean.alias("b"), on="category")
        .filter(F.col("a.id") < F.col("b.id"))
        .withColumn("shared_count",
                    F.size(F.array_intersect(F.col("a.tokens"), F.col("b.tokens"))))
        .filter(F.col("shared_count") >= min_shared)
        .select(
            F.col("a.id").alias("src"),
            F.col("b.id").alias("dst"),
            F.col("shared_count").alias("relationship"),
        )
    )


def run_graph_analysis(spark, vertices, edges, output_base):
    try:
        from graphframes import GraphFrame
    except ImportError:
        raise RuntimeError(
            "GraphFrames chua duoc cai. Them --packages graphframes:graphframes:0.8.3-spark3.5-s_2.12"
        )

    g = GraphFrame(vertices, edges)
    spark.sparkContext.setCheckpointDir(f"{output_base}checkpoints/")

    # 1. Degrees
    print("=== 1. Degrees ===")
    degrees = (
        g.degrees
         .join(g.inDegrees.withColumnRenamed("degree", "in_degree"),  on="id", how="left")
         .join(g.outDegrees.withColumnRenamed("degree", "out_degree"), on="id", how="left")
         .fillna(0, subset=["in_degree", "out_degree"])
         .orderBy(F.desc("degree"))
    )
    degrees.show(20, truncate=False)
    degrees.write.mode("overwrite").parquet(f"{output_base}degrees/")

    # 2. PageRank
    print("=== 2. PageRank ===")
    pr = g.pageRank(resetProbability=PAGERANK_RESET, maxIter=PAGERANK_ITER)
    top_pr = pr.vertices.select("id", "category", "pagerank").orderBy(F.desc("pagerank"))
    top_pr.show(20, truncate=False)
    top_pr.write.mode("overwrite").parquet(f"{output_base}pagerank/")

    # 3. Connected Components
    print("=== 3. Connected Components ===")
    cc = g.connectedComponents()
    cc.groupBy("component").agg(F.count("id").alias("size")).orderBy(F.desc("size")).show(10)
    cc.write.mode("overwrite").parquet(f"{output_base}connected_components/")

    # 4. Triangle Count
    print("=== 4. Triangle Count ===")
    tc = g.triangleCount()
    tc.select("id", "category", "count").orderBy(F.desc("count")).show(20, truncate=False)
    tc.write.mode("overwrite").parquet(f"{output_base}triangle_count/")

    # 5. BFS
    print("=== 5. BFS (demo tu node PageRank cao nhat) ===")
    try:
        top_node = top_pr.first()["id"]
        # toExpr dung cot co san trong vertices goc (category), khong dung pagerank
        bfs_result = g.bfs(
            fromExpr=f"id = '{top_node}'",
            toExpr="category IS NOT NULL",
            maxPathLength=3,
        )
        bfs_result.show(10, truncate=False)
    except Exception as e:
        print(f"BFS skipped: {e}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index",      default=DEFAULT_INDEX)
    parser.add_argument("--output",     default=OUTPUT_PATH)
    parser.add_argument("--min-shared", type=int, default=MIN_SHARED_TOKENS)
    args = parser.parse_args()

    spark = get_spark()
    spark.sparkContext.setCheckpointDir(f"{args.output}checkpoints/")

    df       = read_from_es(spark, index=args.index)
    vertices = build_vertices(df)
    edges    = build_edges(df, min_shared=args.min_shared)

    print(f"Vertices: {vertices.count()} | Edges: {edges.count()}")
    run_graph_analysis(spark, vertices, edges, args.output)


if __name__ == "__main__":
    main()