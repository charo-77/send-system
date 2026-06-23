from PIL import Image

img = Image.open(r"D:\milu_publish_reverse_20260513\插入文档截图.jpg")
w, h = img.size
# Top half - likely the toolbar area with "插入" and dropdown
top = img.crop((0, 0, w, h//2))
top.save(r"D:\milu_publish_reverse_20260513\insert_top.jpg", quality=90)
# Bottom half - likely the editor area
bot = img.crop((0, h//2, w, h))
bot.save(r"D:\milu_publish_reverse_20260513\insert_bot.jpg", quality=90)
print(f"Split: top={top.size}, bot={bot.size}")