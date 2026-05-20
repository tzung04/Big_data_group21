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