from datasets import load_dataset
from kafka import KafkaProducer
import json, uuid
from datetime import datetime

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8')
)

print("Đang tải dataset...")
ds = load_dataset('vietgpt/binhvq_news_vi', split='train[:2000]')  # 2000 bài để test
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