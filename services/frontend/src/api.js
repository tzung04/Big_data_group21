import axios from "axios";

export const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
export const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API === "true";

const MOCK_DOCUMENTS = [
  {
    id: "vnexpress_demo_1",
    title: "Ha Noi trien khai he thong tim kiem van ban tieng Viet",
    content:
      "Pipeline Kafka, Spark Structured Streaming va Elasticsearch lap chi muc tin tuc tieng Viet theo thoi gian gan thuc.",
    tokens: ["ha_noi", "tim_kiem", "van_ban", "tieng_viet"],
    token_count: 24,
    category: "cong-nghe",
    topic_label: "du-lieu-lon",
    url: "https://vnexpress.net/",
    published_at: "2024-01-15T08:00:00Z",
    indexed_at: "2024-01-15T08:06:00Z",
    score: 12.7
  },
  {
    id: "vnexpress_demo_2",
    title: "Kinh doanh so tang truong nho phan tich du lieu lon",
    content:
      "Dashboard Grafana theo doi toc do ingest, do tre Spark va ty le index vao Elasticsearch.",
    tokens: ["kinh_doanh", "du_lieu_lon", "grafana"],
    token_count: 19,
    category: "kinh-doanh",
    topic_label: "kinh-te-so",
    url: "https://vnexpress.net/kinh-doanh",
    published_at: "2024-01-16T08:00:00Z",
    indexed_at: "2024-01-16T08:05:30Z",
    score: 9.8
  },
  {
    id: "vnexpress_demo_3",
    title: "Doi tuyen Viet Nam co tran dau tuyet voi",
    content:
      "Bai viet the thao duoc tokenizer tieng Viet xu ly truoc khi dua vao chi muc tim kiem full-text.",
    tokens: ["doi_tuyen", "viet_nam", "the_thao"],
    token_count: 21,
    category: "the-thao",
    topic_label: "bong-da",
    url: "https://vnexpress.net/the-thao",
    published_at: "2024-01-17T08:00:00Z",
    indexed_at: "2024-01-17T08:04:00Z",
    score: 8.4
  }
];

export async function searchDocuments({ query, category, page = 1, size = 10 }) {
  if (USE_MOCK_API) {
    return searchMockDocuments({ query, category, page, size });
  }

  const res = await axios.get(`${API}/search`, {
    params: {
      q: query,
      category: category || undefined,
      page,
      size
    }
  });

  return {
    total: res.data.total ?? 0,
    results: res.data.results ?? [],
    took_ms: res.data.took_ms
  };
}

export async function getStats() {
  if (USE_MOCK_API) {
    return {
      total: MOCK_DOCUMENTS.length,
      by_category: MOCK_DOCUMENTS.reduce((acc, item) => {
        acc[item.category] = (acc[item.category] || 0) + 1;
        return acc;
      }, {})
    };
  }

  const res = await axios.get(`${API}/stats`);
  return res.data;
}

function searchMockDocuments({ query, category, page, size }) {
  const normalizedQuery = query.trim().toLocaleLowerCase("vi-VN");
  const filtered = MOCK_DOCUMENTS.filter((item) => {
    const inCategory = !category || item.category === category;
    const haystack = [
      item.title,
      item.content,
      item.category,
      item.topic_label,
      ...(item.tokens ?? [])
    ]
      .join(" ")
      .toLocaleLowerCase("vi-VN");

    return inCategory && haystack.includes(normalizedQuery);
  });

  const start = (page - 1) * size;

  return {
    total: filtered.length,
    took_ms: 3,
    results: filtered.slice(start, start + size)
  };
}
