import urllib.request, urllib.parse, json, base64, sys

img_path = r"D:\milu_publish_reverse_20260513\插入文档截图.png"
with open(img_path, "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

data = urllib.parse.urlencode({
    "apikey": "K87720488988957",
    "language": "chs",
    "isOverlayRequired": "false",
}).encode()

req = urllib.request.Request(
    "https://api.ocr.space/parse/image",
    data=data,
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
        print(json.dumps(result, ensure_ascii=False, indent=2))
except Exception as e:
    print("ERROR:", e)