# sync_to_hbase.py
import happybase
import pandas as pd
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB, HBASE_HOST

# ---------- MongoDB 读取 ----------
client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
orders_col = db["orders"]
reviews_col = db["order_reviews"]

# ---------- HBase 连接 ----------
conn = happybase.Connection(HBASE_HOST)
behavior_table = conn.table("order_behavior")
comment_table = conn.table("comment_content")

def reverse_ts(ts):
    """反转时间戳，保证同一用户行为按时间倒序排列"""
    if pd.isna(ts):
        return None
    return str(9999999999999 - int(pd.to_datetime(ts).timestamp()))

def salt(customer_id):
    """2位随机盐值，打散Region热点"""
    import hashlib
    return hashlib.md5(customer_id.encode()).hexdigest()[:2]

# ---------- 写入订单行为日志 ----------
batch = behavior_table.batch(batch_size=500)
for doc in orders_col.find({}, no_cursor_timeout=True).batch_size(500):
    cid = doc["customer_id"]
    oid = doc["_id"]
    s = salt(cid)

    events = []
    if doc.get("order_purchase_timestamp"):
        events.append(("order_create", doc["order_purchase_timestamp"]))
    if doc.get("order_approved_at"):
        events.append(("payment_approved", doc["order_approved_at"]))
    if doc.get("order_delivered_carrier_date"):
        events.append(("shipped", doc["order_delivered_carrier_date"]))
    if doc.get("order_delivered_customer_date"):
        events.append(("delivered", doc["order_delivered_customer_date"]))
    if doc.get("has_review"):
        rev = reviews_col.find_one({"order_id": oid})
        if rev:
            events.append(("review", rev["review_creation_date"]))

    for event_type, ts in events:
        rts = reverse_ts(ts)
        if rts is None:
            continue
        row_key = f"{s}:{cid}:{rts}:{oid}"
        batch.put(
            row_key,
            {
                "info:order_id": oid,
                "info:event_type": event_type,
                "info:event_time": str(ts),
                "info:order_status": doc.get("order_status", ""),
            },
        )
batch.send()
print("order_behavior 写入完成")

# ---------- 写入评论正文 ----------
batch = comment_table.batch(batch_size=500)
for rev in reviews_col.find({}, no_cursor_timeout=True).batch_size(500):
    row_key = f"comment:{rev['_id']}"
    batch.put(
        row_key,
        {
            "content:title": rev.get("review_comment_title") or "",
            "content:message": rev.get("review_comment_message") or "",
            "meta:score": str(rev.get("review_score", 0)),
            "meta:creation_date": rev.get("review_creation_date", ""),
        },
    )
batch.send()
print("comment_content 写入完成")