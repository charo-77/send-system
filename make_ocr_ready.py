from PIL import Image, ImageOps, ImageEnhance

img = Image.open(r"D:\milu_publish_reverse_20260513\插入文档截图.jpg")

# Crop just the toolbar/dropdown area (top portion)
w, h = img.size
toolbar = img.crop((0, 80, w, 350))
toolbar.save(r"D:\milu_publish_reverse_20260513\toolbar_only.jpg", quality=90)

# Convert to high contrast B&W for OCR
gray = toolbar.convert('L')
bw = gray.point(lambda x: 0 if x < 120 else 255)
bw.save(r"D:\milu_publish_reverse_20260513\toolbar_bw.jpg", quality=90)

# Also do just the very top strip with the dropdown
top = img.crop((300, 80, w-50, 400))
gray2 = top.convert('L')
bw2 = gray2.point(lambda x: 0 if x < 120 else 255)
bw2.save(r"D:\milu_publish_reverse_20260513\top_strip.jpg", quality=90)

print("Saved toolbar and top strip")