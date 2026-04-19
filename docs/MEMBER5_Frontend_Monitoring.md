# Member 5 — Frontend + Monitoring (Windows)
> Đọc SHARED_CONTRACTS.md trước. Làm việc trong `services/frontend/`

---

## Setup máy Windows

```bash
# Trong WSL Ubuntu hoặc PowerShell
# Cài Node.js 20 LTS: https://nodejs.org/
node --version  # v20.x.x
npm --version

# Tạo React app
cd services/frontend
npm create vite@latest . -- --template react
npm install
npm install axios
```

---

## Tuần 1 (Ngày 6–7)

### Task 1: React UI cơ bản — ô tìm kiếm + hiển thị kết quả
File: `services/frontend/src/App.jsx`

```jsx
import { useState } from 'react'
import axios from 'axios'

const API = 'http://localhost:8000'

function App() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const search = async (e) => {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError('')
    try {
      const res = await axios.get(`${API}/search`, { params: { q: query } })
      setResults(res.data.results)
      setTotal(res.data.total)
    } catch (err) {
      setError('Không thể kết nối API. Đảm bảo FastAPI đang chạy ở port 8000.')
    }
    setLoading(false)
  }

  return (
    <div style={{ maxWidth: 800, margin: '40px auto', padding: '0 20px', fontFamily: 'sans-serif' }}>
      <h1 style={{ color: '#1a56db' }}>🔍 Tìm kiếm văn bản tiếng Việt</h1>

      <form onSubmit={search} style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Nhập từ khóa tìm kiếm..."
          style={{ flex: 1, padding: '10px 14px', fontSize: 16, border: '2px solid #d1d5db', borderRadius: 8 }}
        />
        <button
          type="submit"
          disabled={loading}
          style={{ padding: '10px 24px', background: '#1a56db', color: 'white', border: 'none', borderRadius: 8, fontSize: 16, cursor: 'pointer' }}
        >
          {loading ? '...' : 'Tìm kiếm'}
        </button>
      </form>

      {error && <p style={{ color: 'red' }}>{error}</p>}
      {total > 0 && <p style={{ color: '#6b7280' }}>Tìm thấy {total} kết quả</p>}

      <div>
        {results.map(r => (
          <div key={r.id} style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, marginBottom: 12 }}>
            <a href={r.url} target="_blank" rel="noreferrer"
               style={{ fontSize: 18, fontWeight: 600, color: '#1a56db', textDecoration: 'none' }}>
              {r.highlight?.title
                ? <span dangerouslySetInnerHTML={{ __html: r.highlight.title[0] }} />
                : r.title}
            </a>
            <span style={{ marginLeft: 8, background: '#dbeafe', color: '#1e40af', padding: '2px 8px', borderRadius: 4, fontSize: 12 }}>
              {r.category}
            </span>
            {r.highlight?.content && (
              <p style={{ color: '#374151', marginTop: 8, fontSize: 14 }}
                 dangerouslySetInnerHTML={{ __html: r.highlight.content[0] }} />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default App
```

Chạy frontend:
```bash
cd services/frontend
npm run dev
# Mở http://localhost:5173
```

---

## Tuần 2 (Ngày 10–13)

### Task 2: Thêm filter theo category + pagination
Thêm vào `App.jsx` phần state và UI:

```jsx
// Thêm state
const [category, setCategory] = useState('')
const [page, setPage] = useState(1)
const CATEGORIES = ['', 'thoi-su', 'kinh-doanh', 'the-thao', 'giai-tri', 'giao-duc']

// Sửa hàm search
const search = async (e, newPage = 1) => {
  if (e) e.preventDefault()
  setLoading(true)
  try {
    const res = await axios.get(`${API}/search`, {
      params: { q: query, category: category || undefined, page: newPage }
    })
    setResults(res.data.results)
    setTotal(res.data.total)
    setPage(newPage)
  } catch (err) {
    setError('Lỗi kết nối API')
  }
  setLoading(false)
}

// Thêm vào JSX (sau form)
<select value={category} onChange={e => setCategory(e.target.value)}
        style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db' }}>
  {CATEGORIES.map(c => <option key={c} value={c}>{c || 'Tất cả chuyên mục'}</option>)}
</select>

// Pagination (cuối danh sách)
{total > 10 && (
  <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 24 }}>
    <button onClick={() => search(null, page - 1)} disabled={page === 1}>← Trước</button>
    <span>Trang {page} / {Math.ceil(total / 10)}</span>
    <button onClick={() => search(null, page + 1)} disabled={page >= Math.ceil(total / 10)}>Sau →</button>
  </div>
)}
```

### Task 3: Trang Stats — hiển thị số liệu hệ thống
File: `services/frontend/src/Stats.jsx`

```jsx
import { useEffect, useState } from 'react'
import axios from 'axios'

export default function Stats() {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    axios.get('http://localhost:8000/stats').then(r => setStats(r.data))
  }, [])

  if (!stats) return <p>Đang tải...</p>

  return (
    <div>
      <h2>Thống kê hệ thống</h2>
      <p>Tổng số văn bản: <strong>{stats.total.toLocaleString()}</strong></p>
      <table border="1" cellPadding="8">
        <thead><tr><th>Chuyên mục</th><th>Số bài</th></tr></thead>
        <tbody>
          {Object.entries(stats.by_category).map(([cat, count]) => (
            <tr key={cat}><td>{cat}</td><td>{count}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

---

## Tuần 3 (Ngày 15–19)

### Task 4: Cấu hình Prometheus scrape
File: `prometheus.yml` (ở root project):

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'elasticsearch'
    metrics_path: '/_prometheus/metrics'
    static_configs:
      - targets: ['localhost:9200']

  - job_name: 'kafka'
    static_configs:
      - targets: ['localhost:9092']
```

Mount vào docker-compose.yml phần prometheus:
```yaml
  prometheus:
    image: prom/prometheus
    ports: ['9090:9090']
    mem_limit: 256m
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
```

### Task 5: Grafana — tạo dashboard cơ bản
1. Mở http://localhost:3001, login: `admin` / `admin`
2. Vào **Connections → Add new connection → Prometheus**
3. URL: `http://prometheus:9090` → **Save & test**
4. Tạo dashboard mới với 3 panels:

**Panel 1 — Tổng số document trong ES:**
```
# PromQL query (nếu ES exporter được cài)
elasticsearch_indices_docs_total{index="vn-documents"}
```

**Panel 2 — CPU usage Docker:**
```
rate(container_cpu_usage_seconds_total[5m]) * 100
```

**Panel 3 — Memory usage:**
```
container_memory_usage_bytes / 1024 / 1024
```

> Nếu chưa có ES metrics trong Prometheus, dùng panel Text để hiển thị số liệu từ API:
> Tạo HTTP datasource trỏ vào `http://host.docker.internal:8000`

### Task 6: Dockerfile cho frontend
File: `services/frontend/Dockerfile`

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

Build và test:
```bash
cd services/frontend
docker build -t vn-search-frontend .
docker run -p 3000:80 vn-search-frontend
# Mở http://localhost:3000
```

### Task 7: Viết README tổng cho repo
File: `README.md` ở root:

```markdown
# VN Text Search

Hệ thống tìm kiếm văn bản tiếng Việt — Kappa Architecture

## Khởi động nhanh
```bash
git clone <repo-url>
cd vn-text-search
cp .env.example .env
docker compose up -d
python services/crawler/load_dataset.py   # load data
python services/api/main.py               # start API
cd services/frontend && npm run dev       # start UI
```

## URLs
- Search UI: http://localhost:5173
- API docs: http://localhost:8000/docs
- Spark UI: http://localhost:8080
- MinIO: http://localhost:9001
- Grafana: http://localhost:3001
```
