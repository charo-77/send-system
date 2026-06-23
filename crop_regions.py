from PIL import Image

img = Image.open(r"D:\milu_publish_reverse_20260513\插入文档截图.jpg")
w, h = img.size

# Try different crops focusing on likely toolbar / dropdown area
crops = [
    ("toolbar", (0, 50, w//2, 250)),
    ("center_top", (w//4, 50, 3*w//4, 350)),
    ("dropdown_area", (w//3, 80, w-50, 400)),
]

for name, box in crops:
    region = img.crop(box)
    region.save(f"D:\milu_publish_reverse_20260513\crop_{name}.jpg", quality=90)
    print(f"Saved crop_{name}: {region.size}")