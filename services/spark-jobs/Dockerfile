FROM apache/spark:3.5.1-python3

USER root

WORKDIR /opt/spark/work-dir

# underthesea cần gcc để build một số extension
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

# JOB được truyền qua biến môi trường SPARK_JOB (tên file .py)
# Ví dụ: SPARK_JOB=streaming_indexer.py
ENV SPARK_JOB=streaming_indexer.py

CMD ["sh", "-c", "python ${SPARK_JOB}"]
