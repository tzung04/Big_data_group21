# services/spark-jobs/Dockerfile
FROM apache/spark:3.5.1
USER root

RUN pip install --no-cache-dir \
    kafka-python==2.0.2 \
    elasticsearch==8.13.0 \
    boto3==1.34.0 \
    underthesea==6.8.4

WORKDIR /opt/spark-jobs

# core utilities
COPY spark_session.py .
COPY udfs.py .
COPY es_reader.py .

# streaming
COPY streaming_indexer.py .
COPY window_stats.py .

# batch
COPY batch_pivot.py .
COPY batch_optimized.py .
COPY enricher.py .
COPY custom_agg.py .

# advanced analytics
COPY ml_classifier.py .
COPY graph_analysis.py .
COPY time_series.py .

ENV SPARK_MASTER=local[2]
ENV SPARK_JOB=streaming_indexer.py
ENV CHECKPOINT_BASE=s3a://spark-checkpoints
ENV PATH="/opt/spark/bin:${PATH}"

ENTRYPOINT ["/opt/spark/bin/spark-submit", \
  "--packages", \
  "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.hadoop:hadoop-aws:3.3.4,graphframes:graphframes:0.8.3-spark3.5-s_2.12", \
  "--repositories", "https://repos.spark-packages.org/"]

CMD ["/opt/spark-jobs/streaming_indexer.py"]
