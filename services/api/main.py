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