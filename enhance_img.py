from PIL import Image, ImageEnhance, ImageFilter

img = Image.open(r"D:\milu_publish_reverse_20260513\插入文档截图.jpg")
img = img.convert('L')
img = ImageEnhance.Contrast(img).enhance(3.0)
img = ImageEnhance.Sharpness(img).enhance(2.0)
img.save(r"D:\milu_publish_reverse_20260513\insert_enhanced.jpg", quality=95)
print("Enhanced:", img.size, img.mode)