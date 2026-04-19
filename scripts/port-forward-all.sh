#!/bin/bash
# Chạy script này khi cần kết nối vào K8s cluster chung
# Mỗi service forward sang cùng port trên localhost

echo "Starting port-forward cho tất cả services..."

kubectl port-forward svc/kafka          9092:9092 &
kubectl port-forward svc/minio          9000:9000 &
kubectl port-forward svc/elasticsearch  9200:9200 &
kubectl port-forward svc/mongodb        27017:27017 &
kubectl port-forward svc/redis          6379:6379 &
kubectl port-forward svc/grafana        3000:80 &

echo ""
echo "Services đang chạy tại:"
echo "  Kafka:         localhost:9092"
echo "  MinIO:         localhost:9000  (UI: localhost:9001)"
echo "  Elasticsearch: localhost:9200"
echo "  MongoDB:       localhost:27017"
echo "  Redis:         localhost:6379"
echo "  Grafana:       localhost:3000"
echo ""
echo "Nhấn Ctrl+C để tắt tất cả"

# Chờ Ctrl+C rồi kill tất cả background jobs
wait
