# Member 1 — DevOps / Architect (macOS)
> Đọc SHARED_CONTRACTS.md trước

---

## Tuần 1 (Ngày 1–7)

### Task 1: Push repo lên GitHub, nhóm clone về
```bash
git add .
git commit -m "feat: init project structure"
git push origin main

# Tạo các branch cho thành viên
git checkout -b dev && git push origin dev
```
Nhắn nhóm clone về và chạy `docker compose up -d`.

### Task 2: Tạo `.gitignore`
```
venv/
.env
__pycache__/
*.pyc
data/*.parquet
data/*.json
.DS_Store
services/*/logs/
```

### Task 3: Tạo `.env.example`
```env
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
ES_HOST=localhost
ES_PORT=9200
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
SPARK_MASTER=spark://localhost:7077
```
Mỗi người copy thành `.env` rồi dùng — **không commit `.env` thật**.

### Task 4: Tạo MinIO buckets
```python
# scripts/init_minio.py
import boto3

client = boto3.client('s3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin'
)

for bucket in ['raw-data', 'spark-checkpoints', 'spark-output']:
    try:
        client.create_bucket(Bucket=bucket)
        print(f'Created: {bucket}')
    except Exception as e:
        print(f'Skipped {bucket}: {e}')
```
```bash
python scripts/init_minio.py
```

### Task 5: Tạo Elasticsearch index
```python
# scripts/init_es.py
from elasticsearch import Elasticsearch

es = Elasticsearch('http://localhost:9200')

mapping = {
    "mappings": {
        "properties": {
            "id":           {"type": "keyword"},
            "title":        {"type": "text", "analyzer": "standard"},
            "content":      {"type": "text", "analyzer": "standard"},
            "tokens":       {"type": "keyword"},
            "token_count":  {"type": "integer"},
            "category":     {"type": "keyword"},
            "topic_label":  {"type": "keyword"},
            "url":          {"type": "keyword"},
            "published_at": {"type": "date"},
            "indexed_at":   {"type": "date"}
        }
    }
}

if not es.indices.exists(index='vn-documents'):
    es.indices.create(index='vn-documents', body=mapping)
    print('Index created: vn-documents')
```
```bash
python scripts/init_es.py
```

### Task 6: Script health check cho nhóm
```bash
# scripts/health_check.sh
#!/bin/bash
echo "=== Health Check ==="
echo -n "Kafka:  "; docker exec vn-text-search-kafka-1 kafka-topics --list --bootstrap-server localhost:9092 > /dev/null 2>&1 && echo "OK" || echo "FAIL"
echo -n "ES:     "; curl -s http://localhost:9200/_cluster/health | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
echo -n "MinIO:  "; curl -s http://localhost:9000/minio/health/live > /dev/null && echo "OK" || echo "FAIL"
echo -n "Spark:  "; curl -s http://localhost:8080 | grep -q "ALIVE" && echo "OK" || echo "FAIL"
```
```bash
chmod +x scripts/health_check.sh
```

---

## Tuần 2 (Ngày 8–14)

### Task 7: Viết K8s namespace + ConfigMap
```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: text-search
```
```yaml
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: text-search
data:
  KAFKA_BOOTSTRAP_SERVERS: "kafka:9092"
  ES_HOST: "elasticsearch"
  ES_PORT: "9200"
  MINIO_ENDPOINT: "minio:9000"
  SPARK_MASTER: "spark://spark-master:7077"
```

### Task 8: Cài k3s (sau khi Docker Compose ổn định)
```bash
curl -sfL https://get.k3s.io | sh -
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
kubectl get nodes
```

### Task 9: GitHub Actions CI
```yaml
# .github/workflows/ci.yml
name: CI
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.11'}
      - run: pip install pytest elasticsearch kafka-python boto3
      - run: pytest services/ -v --ignore=services/frontend 2>/dev/null || true
```

---

## Tuần 3 (Ngày 15–21)

### Task 10: Viết K8s manifests cho từng service
Tạo file trong `k8s/<service>/deployment.yaml` cho: kafka, elasticsearch, minio, spark, api, frontend.

Mẫu deployment:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: elasticsearch
  namespace: text-search
spec:
  replicas: 1
  selector:
    matchLabels: {app: elasticsearch}
  template:
    metadata:
      labels: {app: elasticsearch}
    spec:
      containers:
      - name: elasticsearch
        image: elasticsearch:8.13.0
        env:
        - {name: discovery.type, value: single-node}
        - {name: ES_JAVA_OPTS, value: "-Xms512m -Xmx512m"}
        - {name: xpack.security.enabled, value: "false"}
        resources:
          limits: {memory: "1Gi"}
        ports:
        - containerPort: 9200
```

### Task 11: Deploy lên k3s
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/elasticsearch/
kubectl apply -f k8s/kafka/
kubectl apply -f k8s/spark/
kubectl get pods -n text-search
```
