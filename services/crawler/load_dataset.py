import json
import os
import uuid
from datetime import datetime

from datasets import load_dataset
from kafka import KafkaProducer

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
)

print("Đang tải dataset vietgpt/binhvq_news_vi ...")
ds = load_dataset("vietgpt/binhvq_news_vi", split="train[:2000]")
print(f"Đã tải {len(ds)} bài")

for i, item in enumerate(ds):
    msg = {
        "id": f"hf_{i}_{uuid.uuid4().hex[:8]}",
        "title": item.get("title", ""),
        "content": item.get("body", item.get("content", "")),
        "url": item.get("url", f"https://example.com/{i}"),
        "category": item.get("category", "unknown"),
        "source": "huggingface-binhvq",
        "published_at": datetime.utcnow().isoformat() + "Z",
        "crawled_at": datetime.utcnow().isoformat() + "Z",
    }
    producer.send("raw-documents", value=msg)
    if i % 100 == 0:
        print(f"  Sent {i}/{len(ds)}")

producer.flush()
print(f"Done! Đã đẩy {len(ds)} bài vào Kafka topic raw-documents")
