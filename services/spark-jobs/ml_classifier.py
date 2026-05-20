from __future__ import annotations

import argparse
from typing import Sequence

from pyspark.ml import Pipeline
from pyspark.ml.classification import NaiveBayes
from pyspark.ml.evaluation import MulticlassClassificationEvaluator
from pyspark.ml.feature import HashingTF, IDF, StopWordsRemover, StringIndexer, StringIndexerModel, Tokenizer
from pyspark.ml.pipeline import PipelineModel
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, DataType, IntegerType, StringType

from es_reader import DEFAULT_INDEX, get_spark, read_from_es


DEFAULT_MODEL_PATH = "s3a://spark-output/topic-classifier/"
DEFAULT_LABELED_OUTPUT_PATH = "s3a://spark-output/labeled-documents/"
CONTRACT_COLUMNS = [
    "id",
    "title",
    "content",
    "tokens",
    "token_count",
    "category",
    "topic_label",
    "url",
    "published_at",
    "indexed_at",
]
CONTRACT_FALLBACK_TYPES: dict[str, DataType] = {
    "id": StringType(),
    "title": StringType(),
    "content": StringType(),
    "tokens": ArrayType(StringType()),
    "token_count": IntegerType(),
    "category": StringType(),
    "topic_label": StringType(),
    "url": StringType(),
    "published_at": StringType(),
    "indexed_at": StringType(),
}


def _prepare_training_data(df: DataFrame) -> DataFrame:
    return (
        df.filter(F.col("category").isNotNull())
        .filter(F.col("content").isNotNull())
        .filter(F.length(F.trim(F.col("content"))) > 0)
    )


def _build_pipeline() -> Pipeline:
    indexer = StringIndexer(
        inputCol="category",
        outputCol="label",
        handleInvalid="skip",
    )
    tokenizer = Tokenizer(inputCol="content", outputCol="words")
    remover = StopWordsRemover(inputCol="words", outputCol="filtered")
    hashing_tf = HashingTF(inputCol="filtered", outputCol="rawFeatures", numFeatures=10000)
    idf = IDF(inputCol="rawFeatures", outputCol="features")
    classifier = NaiveBayes(
        labelCol="label",
        featuresCol="features",
        smoothing=1.0,
        modelType="multinomial",
    )
    return Pipeline(stages=[indexer, tokenizer, remover, hashing_tf, idf, classifier])


def _get_indexer_labels(model: PipelineModel) -> Sequence[str]:
    for stage in model.stages:
        if isinstance(stage, StringIndexerModel):
            return stage.labels
    raise RuntimeError("Cannot find StringIndexerModel in trained pipeline.")


def _prediction_to_topic_expr(labels: Sequence[str]) -> F.Column:
    mapping_expr_items = []
    for index, label in enumerate(labels):
        mapping_expr_items.extend([F.lit(float(index)), F.lit(label)])
    mapping = F.create_map(*mapping_expr_items)
    return F.coalesce(mapping[F.col("prediction")], F.lit("unknown"))


def _build_labeled_output(predictions: DataFrame, labels: Sequence[str]) -> DataFrame:
    df_labeled = predictions.withColumn("topic_label", _prediction_to_topic_expr(labels))
    for col_name in CONTRACT_COLUMNS:
        if col_name not in df_labeled.columns:
            df_labeled = df_labeled.withColumn(
                col_name,
                F.lit(None).cast(CONTRACT_FALLBACK_TYPES[col_name]),
            )
    return df_labeled.select(*CONTRACT_COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Spark ML model to classify topic labels.")
    parser.add_argument("--index", default=DEFAULT_INDEX, help="Elasticsearch index name")
    parser.add_argument(
        "--model-output",
        default=DEFAULT_MODEL_PATH,
        help="Output path for saving trained model",
    )
    parser.add_argument(
        "--labeled-output",
        default=DEFAULT_LABELED_OUTPUT_PATH,
        help="Output path for saving labeled documents",
    )
    args = parser.parse_args()

    spark = get_spark()
    df_all = read_from_es(spark, index=args.index)
    df_train = _prepare_training_data(df_all)

    label_count = df_train.select("category").distinct().count()
    if label_count < 2:
        raise ValueError(
            "Need at least 2 categories with non-empty content in Elasticsearch index "
            f"'{args.index}' to train classifier."
        )

    train_df, test_df = df_train.randomSplit([0.8, 0.2], seed=42)
    if train_df.rdd.isEmpty() or test_df.rdd.isEmpty():
        raise ValueError(
            "Training or test split is empty. Add more documents to Elasticsearch before training."
        )

    pipeline = _build_pipeline()
    model = pipeline.fit(train_df)

    predictions = model.transform(test_df)
    evaluator = MulticlassClassificationEvaluator(
        labelCol="label",
        predictionCol="prediction",
        metricName="accuracy",
    )
    accuracy = evaluator.evaluate(predictions)
    print(f"Accuracy: {accuracy:.4f}")

    model.write().overwrite().save(args.model_output)
    print(f"Saved model to: {args.model_output}")

    predict_input = df_all.withColumn("content", F.coalesce(F.col("content"), F.lit("")))
    full_predictions = model.transform(predict_input)
    labels = _get_indexer_labels(model)
    df_labeled = _build_labeled_output(full_predictions, labels)
    df_labeled.write.mode("overwrite").parquet(args.labeled_output)
    print(f"Saved labeled documents to: {args.labeled_output}")


if __name__ == "__main__":
    main()
