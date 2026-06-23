const fs = require('fs');
const path = 'D:\\milu_publish_reverse_20260513\\插入文档截图.png';
const ext = path.split('.').pop().toLowerCase();
const mimeMap = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp' };
const mime = mimeMap[ext] || 'image/png';
const buf = fs.readFileSync(path);
const b64 = buf.toString('base64');
console.log(`data:${mime};base64,${b64}`.slice(0, 200));
console.log('TOTAL_LEN:', `data:${mime};base64,${b64}`.length);