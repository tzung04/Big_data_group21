BTL BIG DATA KÌ 20252

GROUP 21

Thành viên:
1. Bùi Anh Đức - 20225285
2. Vũ Viết Dũng - 20220023
3. Lê Hồng Sơn - 20225389
4. Ngô Hồng Phúc - 20225376
5. Phan Trí Dũng - 20225295

# Text Search — Hệ thống tìm kiếm kho văn bản

## Yêu cầu môi trường
- Python 3.11.x (dùng pyenv)
- Docker Desktop (tăng RAM lên 6GB trong Settings)
- Java 17 (Temurin)

## Setup lần đầu (mỗi thành viên tự làm)

```bash
# 1. Clone repo
git clone <repo-url>
cd text-search

# 2. Tạo virtualenv và cài thư viện
python -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows WSL2

pip install -r requirements.txt

# 3. Copy file cấu hình môi trường
cp .env.example .env
# (không cần sửa gì nếu dùng Docker Compose local)
```

## Khởi động theo vai trò

| Vai trò | Thư mục | Lệnh |
|---------|---------|------|
| A1 — Infra | `infra/` | `docker compose -f docker-compose.full.yml up -d` |
| A2 — Ingest | `ingest/` | `docker compose up -d` |
| A3 — Spark Batch | `spark/batch/` | `docker compose up -d` |
| A4 — Streaming | `spark/streaming/` | `docker compose up -d` |
| A5 — Serve | `serve/` | `docker compose up -d` |

## Kiểm tra services đang chạy

```bash
docker compose ps
docker compose logs <service-name>
```

## Tắt khi xong

```bash
docker compose down
```

## Kết nối vào K8s cluster chung (khi tích hợp)

```bash
# Nhận file kubeconfig từ A1, đặt vào ~/.kube/config
bash scripts/port-forward-all.sh
```

## Cấu trúc thư mục

```
text-search/
├── config/settings.py      ← hằng số chung, mọi người import từ đây
├── infra/                  ← A1: Helm charts, K8s manifests
├── ingest/                 ← A2: crawler, Kafka producer
├── spark/batch/            ← A3: Spark batch jobs
├── spark/streaming/        ← A4: Spark Streaming jobs
├── serve/                  ← A5: FastAPI, storage configs
├── docs/lessons-learned/   ← cả nhóm viết báo cáo
├── scripts/                ← scripts tiện ích
├── requirements.txt        ← thư viện Python chốt cuối
└── .env.example            ← mẫu biến môi trường
```

## Git workflow

```bash
# Tạo branch mới cho task của mình
git checkout -b feature/ten-task

# Commit
git add .
git commit -m "feat(spark): thêm TF-IDF window function"

# Push và tạo PR vào develop
git push origin feature/ten-task
```

**Quy tắc:** không commit thẳng lên `main` hay `develop`. Luôn tạo PR.
