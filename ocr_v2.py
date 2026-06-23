import urllib.request, json

with open(r"D:\milu_publish_reverse_20260513\redbox_area.jpg", "rb") as f:
    img_data = f.read()
import base64
b64 = base64.b64encode(img_data).decode()

# Try with file upload approach
import urllib.parse

boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
body = f"--{boundary}\r\nContent-Disposition: form-data; name=\"apikey\"\r\n\r\nK87720488988957\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nchs\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"base64Image\"\r\n\r\ndata:image/jpeg;base64,{b64}\r\n--{boundary}--".encode()

req = urllib.request.Request(
    "https://api.ocr.space/parse/image",
    data=body,
    headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body))
    }
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
        text = result.get("ParsedResults", [{}])[0].get("ParsedText", "")
        print("RESULT:", text.strip())
except Exception as e:
    print("ERROR:", e)