import { useState } from "react";
import axios from "axios";
import { Activity, BarChart3, ExternalLink, Search } from "lucide-react";
import Stats from "./Stats";

const API = "http://localhost:8000";
const CATEGORIES = ["", "thoi-su", "kinh-doanh", "the-thao", "giai-tri", "giao-duc"];
const PAGE_SIZE = 10;

const DEMO_DOCUMENTS = [
  {
    id: "vnexpress_demo_1",
    title: "Hà Nội triển khai hệ thống tìm kiếm văn bản tiếng Việt",
    content:
      "Pipeline Kafka, Spark Structured Streaming và Elasticsearch giúp lập chỉ mục tin tức tiếng Việt theo thời gian gần thực.",
    category: "cong-nghe",
    topic_label: "du-lieu-lon",
    url: "https://vnexpress.net/"
  },
  {
    id: "vnexpress_demo_2",
    title: "Kinh doanh số tăng trưởng nhờ phân tích dữ liệu lớn",
    content:
      "Dashboard Grafana theo dõi tốc độ ingest, độ trễ Spark và tỷ lệ index vào Elasticsearch.",
    category: "kinh-doanh",
    topic_label: "kinh-te-so",
    url: "https://vnexpress.net/kinh-doanh"
  },
  {
    id: "vnexpress_demo_3",
    title: "Đội tuyển Việt Nam có trận đấu tuyệt vời",
    content:
      "Bài viết thể thao được tokenizer tiếng Việt xử lý trước khi đưa vào chỉ mục tìm kiếm full-text.",
    category: "the-thao",
    topic_label: "bong-da",
    url: "https://vnexpress.net/the-thao"
  },
  {
    id: "vnexpress_demo_4",
    title: "Giao diện demo hỗ trợ highlight kết quả tìm kiếm",
    content:
      "Người dùng có thể nhập từ khóa, lọc chuyên mục và chuyển trang trong React Search UI.",
    category: "giai-tri",
    topic_label: "demo",
    url: "https://vnexpress.net/giai-tri"
  }
];

function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [view, setView] = useState("search");

  const search = async (e, newPage = 1) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError("");
    setNotice("");

    try {
      const res = await axios.get(`${API}/search`, {
        params: {
          q: query,
          category: category || undefined,
          page: newPage,
          size: PAGE_SIZE
        },
        timeout: 3000
      });
      setResults(res.data.results || []);
      setTotal(res.data.total || 0);
      setPage(newPage);
    } catch (err) {
      const demoResults = searchDemoDocuments(query, category, newPage);
      setResults(demoResults.results);
      setTotal(demoResults.total);
      setPage(newPage);
      setNotice("FastAPI /search chưa chạy ở port 8000, đang hiển thị kết quả demo.");
    }

    setLoading(false);
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">Kappa Architecture</p>
          <h1>VnTextSearch</h1>
          <p className="subtitle">Tìm kiếm và theo dõi kho văn bản tiếng Việt</p>
        </div>

        <div className="nav-actions">
          <button className={view === "search" ? "nav-button active" : "nav-button"} onClick={() => setView("search")}>
            <Search size={18} />
            Search
          </button>
          <button className={view === "stats" ? "nav-button active" : "nav-button"} onClick={() => setView("stats")}>
            <Activity size={18} />
            Stats
          </button>
          <a className="grafana-link" href="http://localhost:3001" target="_blank" rel="noreferrer">
            <BarChart3 size={18} />
            Grafana
          </a>
        </div>
      </section>

      {view === "stats" ? (
        <Stats />
      ) : (
        <>
          <section className="search-panel">
            <form className="search-form" onSubmit={search}>
              <label className="search-box">
                <Search size={22} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Nhập từ khóa tìm kiếm..."
                />
              </label>

              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map((c) => (
                  <option key={c || "all"} value={c}>
                    {c || "Tất cả chuyên mục"}
                  </option>
                ))}
              </select>

              <button className="primary-button" type="submit" disabled={loading}>
                {loading ? "Đang tìm..." : "Tìm kiếm"}
              </button>
            </form>
          </section>

          <section className="results-layout">
            <div className="results-header">
              <div>
                <h2>Kết quả tìm kiếm</h2>
                <p>{total > 0 ? `Tìm thấy ${total.toLocaleString("vi-VN")} kết quả` : "Index: vn-documents"}</p>
              </div>
              <span className="page-indicator">Trang {page} / {totalPages}</span>
            </div>

            {error && <div className="state-message error">{error}</div>}
            {notice && <div className="notice-message">{notice}</div>}

            {!error && results.length === 0 && (
              <div className="state-message">
                Nhập từ khóa để tìm trong FastAPI port 8000 và Elasticsearch index vn-documents.
              </div>
            )}

            <div className="result-list">
              {results.map((r) => (
                <article className="result-card" key={r.id}>
                  <div className="result-meta">
                    <span>{r.category}</span>
                    {r.topic_label && <span>{r.topic_label}</span>}
                  </div>

                  <a className="result-title" href={r.url} target="_blank" rel="noreferrer">
                    {r.highlight?.title ? (
                      <span dangerouslySetInnerHTML={{ __html: r.highlight.title[0] }} />
                    ) : (
                      highlightText(r.title, query)
                    )}
                    <ExternalLink size={15} />
                  </a>

                  {r.highlight?.content ? (
                    <p dangerouslySetInnerHTML={{ __html: r.highlight.content[0] }} />
                  ) : (
                    <p>{highlightText(r.content, query)}</p>
                  )}
                </article>
              ))}
            </div>

            {total > PAGE_SIZE && (
              <div className="pagination">
                <button onClick={() => search(null, page - 1)} disabled={page === 1 || loading}>
                  Trước
                </button>
                <span>Trang {page} / {totalPages}</span>
                <button onClick={() => search(null, page + 1)} disabled={page >= totalPages || loading}>
                  Sau
                </button>
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}

function searchDemoDocuments(query, category, page) {
  const normalizedQuery = query.trim().toLocaleLowerCase("vi-VN");
  const filtered = DEMO_DOCUMENTS.filter((item) => {
    const matchesCategory = !category || item.category === category;
    const text = `${item.title} ${item.content} ${item.category} ${item.topic_label}`.toLocaleLowerCase("vi-VN");
    return matchesCategory && text.includes(normalizedQuery);
  });
  const start = (page - 1) * PAGE_SIZE;

  return {
    total: filtered.length,
    results: filtered.slice(start, start + PAGE_SIZE)
  };
}

function highlightText(text = "", keyword = "") {
  const trimmed = keyword.trim();
  if (!trimmed) return text;

  const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const regex = new RegExp(`(${escaped})`, "gi");
  const parts = text.split(regex);

  return parts.map((part, index) =>
    part.toLocaleLowerCase("vi-VN") === trimmed.toLocaleLowerCase("vi-VN") ? (
      <mark key={`${part}-${index}`}>{part}</mark>
    ) : (
      part
    )
  );
}

export default App;
