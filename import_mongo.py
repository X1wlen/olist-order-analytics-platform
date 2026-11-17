# import_mongo_.py
import pandas as pd
from pymongo import MongoClient, ASCENDING, DESCENDING
from config import MONGO_URI, MONGO_DB
from tqdm import tqdm
from pymongo import ReplaceOne

CSV = "./olist_csv"

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[MONGO_DB]

orders_col = db["orders"]
items_col = db["order_items"]
payments_col = db["order_payments"]
reviews_col = db["order_reviews"]
products_col = db["products"]
customers_col = db["customers"]

# ---------- 1. 幂等清理 ----------
for col in [orders_col, items_col, payments_col, reviews_col, products_col, customers_col]:
    col.delete_many({})

def upsert_many(col, docs):
    col.bulk_write(
    [ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in docs],
    ordered=False,
)

# ---------- 2. 只读必要列 ----------
orders = pd.read_csv(
    f"{CSV}/olist_orders_dataset.csv",
    usecols=[
        "order_id",
        "customer_id",
        "order_status",
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
    ],
)

items = pd.read_csv(
    f"{CSV}/olist_order_items_dataset.csv",
    usecols=[
        "order_id",
        "product_id",
        "seller_id",
        "price",
        "freight_value",
    ],
)

payments = pd.read_csv(
    f"{CSV}/olist_order_payments_dataset.csv",
    usecols=[
        "order_id",
        "payment_type",
        "payment_installments",
        "payment_value",
    ],
)

reviews = pd.read_csv(
    f"{CSV}/olist_order_reviews_dataset.csv",
    usecols=[
        "order_id",
        "review_id",
        "review_score",
        "review_comment_title",
        "review_comment_message",
        "review_creation_date",
        "review_answer_timestamp",
    ],
)

products = pd.read_csv(
    f"{CSV}/olist_products_dataset.csv",
    usecols=[
        "product_id",
        "product_category_name",
        "product_name_lenght",
        "product_description_lenght",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ],
)

customers = pd.read_csv(
    f"{CSV}/olist_customers_dataset.csv",
    usecols=[
        "customer_id",
        "customer_unique_id",
        "customer_city",
        "customer_state",
    ],
)

trans = pd.read_csv(
    f"{CSV}/product_category_name_translation.csv",
    usecols=["product_category_name", "product_category_name_english"],
)

# ---------- 3. 类目映射 ----------
# 商品id+商品种类英文名
prod_cat = products.merge(trans, on="product_category_name", how="left")
cat_map = dict(
    zip(prod_cat["product_id"], prod_cat["product_category_name_english"])
)


# ---------- 4. 预建 Map，避免 groupby.groups 内存爆炸 ----------
items_map = {
    oid: group.to_dict("records")
    for oid, group in items.groupby("order_id")
}

payments_map = {}
for oid, group in payments.groupby("order_id"):
    payments_map[oid] = {
        "payment_type": group["payment_type"].iloc[0],
        "payment_value": float(group["payment_value"].sum()),
        "installments": int(group["payment_installments"].max()),
    }

reviews_map = {}
for _, r in reviews.iterrows():
    reviews_map[r["order_id"]] = {
        "review_id": r["review_id"],
        "review_score": int(r["review_score"]),
        "review_comment_title": r["review_comment_title"]
        if pd.notna(r["review_comment_title"])
        else None,
        "review_comment_message": r["review_comment_message"]
        if pd.notna(r["review_comment_message"])
        else None,
        "review_creation_date": r["review_creation_date"],
        "review_answer_timestamp": r["review_answer_timestamp"]
        if pd.notna(r["review_answer_timestamp"])
        else None,
    }

cust_map = dict(zip(customers["customer_id"], customers["customer_unique_id"]))
state_map = dict(zip(customers["customer_id"], customers["customer_state"]))

# ---------- 5. 写入 customers ----------
customer_docs = []
for _, c in customers.iterrows():
    customer_docs.append(
        {
            "_id": c["customer_id"],
            "customer_unique_id": c["customer_unique_id"],
            "customer_city": c["customer_city"],
            "customer_state": c["customer_state"],
        }
    )
upsert_many(customers_col, customer_docs)
 
# ---------- 6. 写入 products ----------
product_docs = []
for _, p in products.iterrows():
    product_docs.append(
        {
            "_id": p["product_id"],
            "product_category_name": p["product_category_name"],
            "product_category_name_english": cat_map.get(p["product_id"]) or "unknown",
            "product_photos_qty": int(p["product_photos_qty"])
            if pd.notna(p["product_photos_qty"])
            else 0,
            "product_weight_g": float(p["product_weight_g"])
            if pd.notna(p["product_weight_g"])
            else None,
            "product_length_cm": float(p["product_length_cm"])
            if pd.notna(p["product_length_cm"])
            else None,
            "product_height_cm": float(p["product_height_cm"])
            if pd.notna(p["product_height_cm"])
            else None,
            "product_width_cm": float(p["product_width_cm"])
            if pd.notna(p["product_width_cm"])
            else None,
        }
    )
upsert_many(products_col, product_docs)

# ---------- 7. 写入 order_items ----------
items_docs = []
for oid, group in items.groupby("order_id"):
    for _, it in group.iterrows():
        items_docs.append(
            {
                "_id": f"{oid}_{it['product_id']}_{it['seller_id']}",
                "order_id": oid,
                "product_id": it["product_id"],
                "seller_id": it["seller_id"],
                "price": float(it["price"]),
                "freight_value": float(it["freight_value"]),
                "category_english": cat_map.get(it["product_id"]) or "unknown",
            }
        )

upsert_many(items_col, items_docs)

# ---------- 8. 写入 order_payments ----------
payments_docs = []
for oid, pay in payments_map.items():
    payments_docs.append(
        {
            "_id": oid,
            "order_id": oid,
            "payment_type": pay["payment_type"],
            "payment_value": pay["payment_value"],
            "installments": pay["installments"],
        }
    )
upsert_many(payments_col, payments_docs)

# ---------- 9. 写入 order_reviews ----------
reviews_docs = []
for oid, rev in reviews_map.items():
    reviews_docs.append(
        {
            "_id": rev["review_id"],
            "order_id": oid,
            "review_score": rev["review_score"],
            "review_comment_title": rev["review_comment_title"],
            "review_comment_message": rev["review_comment_message"],
            "review_creation_date": rev["review_creation_date"],
            "review_answer_timestamp": rev["review_answer_timestamp"],
        }
    )
upsert_many(reviews_col, reviews_docs)

# ---------- 10. 写入 orders ----------
order_docs = []
for _, o in tqdm(orders.iterrows(), total=len(orders)):
    oid = o["order_id"]

    order_docs.append(
        {
            "_id": oid,
            "customer_id": o["customer_id"],
            "customer_unique_id": cust_map.get(o["customer_id"]),
            "customer_state": state_map.get(o["customer_id"]),
            "order_status": o["order_status"],
            "order_purchase_timestamp": pd.to_datetime(o["order_purchase_timestamp"])
            if pd.notna(o["order_purchase_timestamp"])
            else None,
            "order_approved_at": pd.to_datetime(o["order_approved_at"])
            if pd.notna(o["order_approved_at"])
            else None,
            "order_delivered_carrier_date": pd.to_datetime(o["order_delivered_carrier_date"])
            if pd.notna(o["order_delivered_carrier_date"])
            else None,
            "order_delivered_customer_date": pd.to_datetime(o["order_delivered_customer_date"])
            if pd.notna(o["order_delivered_customer_date"])
            else None,
            "has_review": oid in reviews_map,
            "has_payment": oid in payments_map,
        }
    )

upsert_many(orders_col, order_docs)

# ---------- 11. 索引 ----------
orders_col.create_index([("customer_unique_id", ASCENDING)])
orders_col.create_index([("order_purchase_timestamp", DESCENDING)])
orders_col.create_index([("customer_state", ASCENDING), ("order_purchase_timestamp", DESCENDING)])
orders_col.create_index([("order_status", ASCENDING)])

items_col.create_index([("order_id", ASCENDING)])
items_col.create_index([("product_id", ASCENDING)])
items_col.create_index([("seller_id", ASCENDING)])

payments_col.create_index([("order_id", ASCENDING)])

reviews_col.create_index([("order_id", ASCENDING)])
reviews_col.create_index([("review_score", ASCENDING)])
reviews_col.create_index([("review_creation_date", ASCENDING)])

products_col.create_index([("product_category_name_english", ASCENDING)])

customers_col.create_index([("customer_unique_id", ASCENDING)])
customers_col.create_index([("customer_state", ASCENDING)])

# ---------- 12. 统计 ----------
print("orders:", orders_col.count_documents({}))
print("order_items:", items_col.count_documents({}))
print("order_payments:", payments_col.count_documents({}))
print("order_reviews:", reviews_col.count_documents({}))
print("products:", products_col.count_documents({}))
print("customers:", customers_col.count_documents({}))
print("MongoDB 导入完成")