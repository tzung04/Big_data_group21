# Member 5 Report: Frontend and Monitoring

## Scope

Member 5 owns the demo-facing user interface, Grafana monitoring dashboard, and documentation for the Frontend + Monitoring part of VnTextSearch.

## Deliverables

- React Search UI in `services/frontend`.
- Stats page in `services/frontend/src/Stats.jsx`.
- Grafana provisioning and overview dashboard in `monitoring/grafana`.
- Prometheus scrape and alert examples in `monitoring/prometheus`.
- This handover report for integration and presentation.

## Frontend

The React UI supports the Week 1 and Week 3 tasks from the setup guide:

- Search input connected to `GET /search` by `axios`.
- Category filter for common Vietnamese news categories.
- Result cards using the shared `vn-documents` fields: `id`, `title`, `content`, `category`, `topic_label`, `token_count`, `url`, `published_at`, and `indexed_at`.
- Score display is optional because it is returned by Elasticsearch search responses but is not stored in the shared index mapping.
- Pagination using `page` and `size` query parameters.
- Loading, empty, and API error states.
- Header link to Grafana on port `3001`.

Expected API contract:

```http
GET /search?q=<keyword>&category=<optional>&page=1&size=10
```

Supported response shapes:

```json
{
  "total": 123,
  "took_ms": 42,
  "results": [
    {
      "id": "vnexpress_1234567",
      "title": "Tieu de bai bao",
      "content": "Noi dung bai bao...",
      "tokens": ["tieu_de", "bai_bao"],
      "token_count": 120,
      "category": "thoi-su",
      "topic_label": "chinh-tri",
      "url": "https://example.com",
      "published_at": "2024-01-15T08:00:00Z",
      "indexed_at": "2024-01-15T08:06:00Z",
      "score": 12.34
    }
  ]
}
```

The UI also accepts plain arrays, or objects using `hits` or `items`, to reduce integration friction with the backend.

## Monitoring

The Grafana dashboard tracks:

- Kafka ingest rate.
- Spark streaming latency.
- Elasticsearch indexing rate.
- Cluster CPU and memory.
- Service availability.

Prometheus examples include scrape jobs for Prometheus, Kafka exporter, Elasticsearch exporter, Spark master, and FastAPI. The alert examples cover service downtime, high memory usage, and stopped Elasticsearch indexing.

## Run Frontend

```bash
cd services/frontend
npm install
npm run dev
```

Default local URL:

```text
http://localhost:5173
```

Shared service ports used by Member 5:

```text
FastAPI:    http://localhost:8000
Prometheus: http://localhost:9090
Grafana:    http://localhost:3001
```

If the FastAPI backend is not on `http://localhost:8000`, set:

```bash
VITE_API_BASE_URL=http://localhost:<port> npm run dev
```

For UI-only demo without FastAPI, set:

```bash
VITE_USE_MOCK_API=true npm run dev
```

## Demo Checklist

- `docker compose ps` shows API, Elasticsearch, Kafka, Spark, Prometheus, and Grafana running.
- `GET /search?q=ha noi` returns at least one result.
- `GET /stats` returns `total` and `by_category`.
- Frontend can search and open source links.
- Frontend Stats view can render category counts.
- Grafana opens the `VnTextSearch Overview` dashboard.
- At least one panel shows live data after the pipeline starts.

## Lessons Learned Notes

- Frontend should tolerate backend response changes during integration.
- Search UX needs explicit empty and error states because Elasticsearch may be empty during early demos.
- Monitoring metrics depend on exporters. Dashboard panels should be treated as ready templates until Kafka, Spark, and Elasticsearch exporters are wired into Docker Compose or Kubernetes.
