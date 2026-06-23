from PIL import Image

img = Image.open(r"D:\milu_publish_reverse_20260513\插入文档截图.jpg")
w, h = img.size

# Scan for red pixels (RGB)
# Red bounding box detection using PIL pixel access
min_x, min_y, max_x, max_y = w, h, 0, 0

for y in range(h):
    for x in range(w):
        r, g, b = img.getpixel((x, y))
        if r > 150 and g < 100 and b < 100:
            if x < min_x: min_x = x
            if x > max_x: max_x = x
            if y < min_y: min_y = y
            if y > max_y: max_y = y

if max_x > min_x and max_y > min_y:
    # Expand by 30px
    y1 = max(0, min_y - 30)
    y2 = min(h, max_y + 30)
    x1 = max(0, min_x - 30)
    x2 = min(w, max_x + 30)
    crop = img.crop((x1, y1, x2, y2))
    new_w = max(800, crop.width * 2)
    new_h = int(crop.height * (new_w / crop.width))
    crop = crop.resize((new_w, new_h), Image.LANCZOS)
    crop.save(r"D:\milu_publish_reverse_20260513\redbox_area.jpg", quality=95)
    print(f"Red box: ({x1},{y1})-({x2},{y2}), crop size: {crop.size}")
else:
    print("No red pixels found. Check if image has different red encoding.")