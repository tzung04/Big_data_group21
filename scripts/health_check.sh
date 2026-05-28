#!/bin/bash
echo "=== Health Check ==="
echo -n "Kafka:  "; docker exec vn-text-search-kafka-1 kafka-topics --list --bootstrap-server localhost:9092 > /dev/null 2>&1 && echo "OK" || echo "FAIL"
echo -n "ES:     "; curl -s http://localhost:9200/_cluster/health | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
echo -n "MinIO:  "; curl -s http://localhost:9000/minio/health/live > /dev/null && echo "OK" || echo "FAIL"
echo -n "Spark:  "; curl -s http://localhost:8080 | grep -q "ALIVE" && echo "OK" || echo "FAIL"

#chmod +x scripts/health_check.sh