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

#python scripts/init_es.py