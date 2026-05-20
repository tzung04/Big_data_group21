import requests, json, time, hashlib
from bs4 import BeautifulSoup
from kafka import KafkaProducer
from datetime import datetime

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8')
)

CATEGORIES = ['thoi-su', 'kinh-doanh', 'the-thao', 'giai-tri', 'giao-duc']
seen_urls = set()

def crawl_category(category, max_pages=2):
    articles = []
    for page in range(1, max_pages + 1):
        try:
            url = f"https://vnexpress.net/{category}-p{page}"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            for item in soup.select('.item-news'):
                a_tag = item.select_one('h3.title-news a, h2.title-news a')
                desc = item.select_one('p.description')
                if not a_tag:
                    continue
                article_url = a_tag.get('href', '')
                if article_url in seen_urls:
                    continue
                seen_urls.add(article_url)
                articles.append({
                    "id": "vne_" + hashlib.md5(article_url.encode()).hexdigest()[:12],
                    "title": a_tag.text.strip(),
                    "content": desc.text.strip() if desc else a_tag.text.strip(),
                    "url": article_url,
                    "category": category,
                    "source": "vnexpress",
                    "published_at": datetime.now().isoformat() + "Z",
                    "crawled_at": datetime.now().isoformat() + "Z"
                })
            time.sleep(1)
        except Exception as e:
            print(f"Error crawling {category} page {page}: {e}")
    return articles

def run():
    print("Crawler started. Ctrl+C để dừng.")
    while True:
        total = 0
        for cat in CATEGORIES:
            articles = crawl_category(cat)
            for article in articles:
                producer.send("raw-documents", value=article)
            total += len(articles)
            time.sleep(2)
        producer.flush()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sent {total} articles. Sleeping 5 minutes...")
        time.sleep(300)

if __name__ == "__main__":
    run()