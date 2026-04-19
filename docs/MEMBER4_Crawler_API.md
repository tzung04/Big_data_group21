# Member 4 — Crawler + FastAPI (Windows)
> Đọc SHARED_CONTRACTS.md trước. Làm việc trong `services/crawler/` và `services/api/`

---

## Setup máy Windows

```bash
# Trong WSL Ubuntu terminal
pip install fastapi uvicorn requests beautifulsoup4 kafka-python==2.0.2 elasticsearch==8.13.0 boto3 datasets
```

---

## Tuần 1 (Ngày 3–6)

### Task 1: Tạo Kafka topic
```bash
# Chạy 1 lần sau khi docker compose up
docker exec vn-text-search-kafka-1 \
  kafka-topics --create \
  --topic raw-documents \
  --bootstrap-server localhost:9092 \
  --partitions 3 \
  --replication-factor 1

docker exec vn-text-search-kafka-1 \
  kafka-topics --create \
  --topic processed-documents \
  --bootstrap-server localhost:9092 \
  --partitions 3 \
  --replication-factor 1
```

### Task 2: Load dataset HuggingFace (nhanh, không cần crawl)
File: `services/crawler/load_dataset.py`

```python
"""
Tải dataset báo tiếng Việt từ HuggingFace, đẩy vào Kafka
Chạy 1 lần để có data test cho cả nhóm
"""
from datasets import load_dataset
from kafka import KafkaProducer
import json, uuid
from datetime import datetime

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8')
)

print("Đang tải dataset...")
ds = load_dataset('binhvq/news-vi', split='train[:2000]')  # 2000 bài để test
print(f"Đã tải {len(ds)} bài")

for i, item in enumerate(ds):
    msg = {
        "id": f"hf_{i}_{uuid.uuid4().hex[:8]}",
        "title": item.get("title", ""),
        "content": item.get("body", item.get("content", "")),
        "url": item.get("url", f"https://example.com/{i}"),
        "category": item.get("category", "unknown"),
        "source": "huggingface-binhvq",
        "published_at": datetime.now().isoformat() + "Z",
        "crawled_at": datetime.now().isoformat() + "Z"
    }
    producer.send("raw-documents", value=msg)
    if i % 100 == 0:
        print(f"  Sent {i}/{len(ds)}")

producer.flush()
print("Done! Đã đẩy vào Kafka topic raw-documents")
```

```bash
python services/crawler/load_dataset.py
```

### Task 3: Crawler VnExpress (streaming liên tục)
File: `services/crawler/vnexpress_crawler.py`

```python
"""
Crawler chạy liên tục, cứ 5 phút crawl 1 lần
Dùng để demo streaming real-time
"""
import requests, json, time, hashlib
from bs4 import BeautifulSoup
from kafka import KafkaProducer
from datetime import datetime

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8')
)

CATEGORIES = ['thoi-su', 'kinh-doanh', 'the-thao', 'giai-tri', 'giao-duc']
seen_urls = set()

def crawl_category(category, max_pages=2):
    articles = []
    for page in range(1, max_pages + 1):
        try:
            url = f"https://vnexpress.net/{category}-p{page}"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            for item in soup.select('.item-news'):
                a_tag = item.select_one('h3.title-news a, h2.title-news a')
                desc = item.select_one('p.description')
                if not a_tag:
                    continue
                article_url = a_tag.get('href', '')
                if article_url in seen_urls:
                    continue
                seen_urls.add(article_url)
                articles.append({
                    "id": "vne_" + hashlib.md5(article_url.encode()).hexdigest()[:12],
                    "title": a_tag.text.strip(),
                    "content": desc.text.strip() if desc else a_tag.text.strip(),
                    "url": article_url,
                    "category": category,
                    "source": "vnexpress",
                    "published_at": datetime.now().isoformat() + "Z",
                    "crawled_at": datetime.now().isoformat() + "Z"
                })
            time.sleep(1)
        except Exception as e:
            print(f"Error crawling {category} page {page}: {e}")
    return articles

def run():
    print("Crawler started. Ctrl+C để dừng.")
    while True:
        total = 0
        for cat in CATEGORIES:
            articles = crawl_category(cat)
            for article in articles:
                producer.send("raw-documents", value=article)
            total += len(articles)
            time.sleep(2)
        producer.flush()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sent {total} articles. Sleeping 5 minutes...")
        time.sleep(300)

if __name__ == "__main__":
    run()
```

### Task 4: Tạo Elasticsearch index
File: `services/crawler/init_es.py`

```python
from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")

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
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0
    }
}

if es.indices.exists(index="vn-documents"):
    print("Index already exists")
else:
    es.indices.create(index="vn-documents", body=mapping)
    print("Created index: vn-documents")
```

---

## Tuần 2 (Ngày 9–13)

### Task 5: FastAPI search endpoint
File: `services/api/main.py`

```python
from fastapi import FastAPI, Query
from elasticsearch import Elasticsearch
from typing import Optional
import uvicorn

app = FastAPI(title="VN Text Search API")
es = Elasticsearch("http://localhost:9200")

@app.get("/health")
def health():
    return {"status": "ok", "es": es.ping()}

@app.get("/search")
def search(
    q: str = Query(..., description="Từ khóa tìm kiếm"),
    category: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50)
):
    must = [{"multi_match": {"query": q, "fields": ["title^2", "content"]}}]
    if category:
        must.append({"term": {"category": category}})

    body = {
        "from": (page - 1) * size,
        "size": size,
        "query": {"bool": {"must": must}},
        "highlight": {
            "fields": {"title": {}, "content": {"fragment_size": 200}}
        }
    }

    res = es.search(index="vn-documents", body=body)
    hits = res["hits"]["hits"]

    return {
        "total": res["hits"]["total"]["value"],
        "page": page,
        "results": [
            {
                "id": h["_source"].get("id"),
                "title": h["_source"].get("title"),
                "category": h["_source"].get("category"),
                "url": h["_source"].get("url"),
                "highlight": h.get("highlight", {}),
                "score": h["_score"]
            }
            for h in hits
        ]
    }

@app.get("/stats")
def stats():
    res = es.search(index="vn-documents", body={
        "size": 0,
        "aggs": {
            "by_category": {"terms": {"field": "category"}},
            "total_docs": {"value_count": {"field": "id"}}
        }
    })
    return {
        "total": res["hits"]["total"]["value"],
        "by_category": {
            b["key"]: b["doc_count"]
            for b in res["aggregations"]["by_category"]["buckets"]
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Chạy API:
```bash
cd services/api
uvicorn main:app --reload --port 8000
# Test: http://localhost:8000/docs
```

---

## Tuần 3 (Ngày 18–19)

### Task 6: Test API
File: `services/api/test_api.py`

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

def test_search_requires_query():
    response = client.get("/search")
    assert response.status_code == 422  # validation error

@patch("main.es")
def test_search_returns_results(mock_es):
    mock_es.ping.return_value = True
    mock_es.search.return_value = {
        "hits": {
            "total": {"value": 1},
            "hits": [{
                "_source": {"id": "1", "title": "Test", "category": "thoi-su", "url": "http://x.com"},
                "_score": 1.0,
                "highlight": {}
            }]
        }
    }
    response = client.get("/search?q=test")
    assert response.status_code == 200
    assert response.json()["total"] == 1
```
```bash
pytest services/api/test_api.py -v
```
