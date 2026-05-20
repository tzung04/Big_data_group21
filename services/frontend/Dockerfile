FROM node:20-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
# VITE_API_BASE_URL=/api → nginx proxy /api/ → http://api:8000/
# Tránh hardcode URL, hoạt động cho cả local (qua NodePort) và Ingress
RUN VITE_API_BASE_URL=/api npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
