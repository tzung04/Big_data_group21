import { useEffect, useState } from "react";
import { getStats } from "./api";

export default function Stats() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getStats()
      .then((data) => setStats(data))
      .catch(() => setError("Không thể kết nối API. Kiểm tra dịch vụ FastAPI."));
  }, []);

  if (error) {
    return <section className="stats-panel"><p className="notice-message">{error}</p></section>;
  }

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
