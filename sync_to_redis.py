# sync_to_redis.py
import redis
import pandas as pd
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB, REDIS_HOST, REDIS_PORT

# ---------- MongoDB 读取 ----------
client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
orders_col = db["orders"]
items_col = db["order_items"]
reviews_col = db["order_reviews"]

# ---------- Redis 连接 ----------
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
pipe = r.pipeline()

# ---------- 1. 商品评论数 & 平均评分 ----------
# 通过 order_items 关联 reviews，按 product_id 聚合
review_stats = {}
for rev in reviews_col.find({}, {"order_id": 1, "review_score": 1}):
    oid = rev["order_id"]
    score = rev["review_score"]
    # 查该订单包含的商品
    for item in items_col.find({"order_id": oid}, {"product_id": 1}):
        pid = item["product_id"]
        if pid not in review_stats:
            review_stats[pid] = {"count": 0, "total_score": 0}
        review_stats[pid]["count"] += 1
        review_stats[pid]["total_score"] += score

for pid, stats in review_stats.items():
    avg = round(stats["total_score"] / stats["count"], 1)
    pipe.set(f"comment:count:{pid}", stats["count"])
    pipe.set(f"product:avg_score:{pid}", avg)

# ---------- 2. 热门商品排行（ZSET） ----------
from datetime import datetime
today = datetime.now().strftime("%Y%m%d")
for pid, stats in review_stats.items():
    avg = stats["total_score"] / stats["count"]
    hot_score = stats["count"] * avg  # 热度 = 评论数 × 平均分
    pipe.zadd(f"product:hot:{today}", {pid: hot_score})

# ---------- 3. 用户最近订单 ----------
for doc in orders_col.find({}, {"customer_unique_id": 1, "order_purchase_timestamp": 1}).sort("order_purchase_timestamp", -1).limit(50000):
    uid = doc.get("customer_unique_id")
    if uid:
        key = f"user:recent:order:{uid}"
        pipe.lpush(key, doc["_id"])
        pipe.ltrim(key, 0, 4)  # 只保留最近5个

pipe.execute()
print("Redis 写入完成")
print(f"  商品评分Key数: {r.dbsize()}")
print(f"  今日热门排行: {r.zcard(f'product:hot:{today}')}")