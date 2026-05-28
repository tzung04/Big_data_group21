import os

from elasticsearch import Elasticsearch

_ES_HOST = os.getenv("ES_HOST", "localhost")
_ES_PORT = os.getenv("ES_PORT", "9200")

es = Elasticsearch(f"http://{_ES_HOST}:{_ES_PORT}")

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
            "indexed_at":   {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
}

if es.indices.exists(index="vn-documents"):
    print("Index vn-documents already exists")
else:
    es.indices.create(index="vn-documents", body=mapping)
    print("Created index: vn-documents")
