# download_data.py
import kagglehub, os, shutil

path = kagglehub.dataset_download("olistbr/brazilian-ecommerce")
print("下载到:", path)

dst = "./olist_csv"
os.makedirs(dst, exist_ok=True)
for f in os.listdir(path):
    if f.endswith(".csv"):
        shutil.copy(os.path.join(path, f), dst)
print("CSV 已复制到", dst)