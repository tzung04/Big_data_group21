import { useEffect, useState } from "react";
import axios from "axios";

const DEMO_STATS = {
  total: 1250,
  by_category: {
    "thoi-su": 320,
    "kinh-doanh": 260,
    "the-thao": 210,
    "giai-tri": 180,
    "giao-duc": 160,
    "cong-nghe": 120
  }
};

export default function Stats() {
  const [stats, setStats] = useState(null);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    axios
      .get("http://localhost:8000/stats", { timeout: 3000 })
      .then((r) => setStats(r.data))
      .catch(() => {
        setStats(DEMO_STATS);
        setNotice("FastAPI /stats chưa chạy ở port 8000, đang hiển thị dữ liệu demo.");
      });
  }, []);

  if (!stats) {
    return <section className="stats-panel">Đang tải...</section>;
  }

  const rows = Object.entries(stats.by_category || {});

  return (
    <section className="stats-panel">
      <div className="stats-header">
        <div>
          <p className="eyebrow">System Metrics</p>
          <h2>Thống kê hệ thống</h2>
        </div>
        <div className="total-documents">
          <span>Tổng văn bản</span>
          <strong>{stats.total.toLocaleString("vi-VN")}</strong>
        </div>
      </div>

      {notice && <div className="notice-message">{notice}</div>}

      <div className="stats-grid">
        {rows.map(([cat, count]) => (
          <article className="stat-card" key={cat}>
            <span>{cat}</span>
            <strong>{count.toLocaleString("vi-VN")}</strong>
          </article>
        ))}
      </div>

      <table className="stats-table">
        <thead>
          <tr>
            <th>Chuyên mục</th>
            <th>Số bài</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([cat, count]) => (
            <tr key={cat}>
              <td>{cat}</td>
              <td>{count.toLocaleString("vi-VN")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
