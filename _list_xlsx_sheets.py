import zipfile, re
p = r'D:\milu_publish_reverse_20260513\CK.xlsx'
s = zipfile.ZipFile(p).read('xl/workbook.xml').decode('utf-8','ignore')
print(re.findall(r'<sheet[^>]*name="([^"]+)"', s))
