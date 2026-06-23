from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _now_str() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class PublishMonitor:
    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.status_path = self.out_dir / '发布监控.json'
        self.text_path = self.out_dir / '发布监控.txt'
        self.text_utf8bom_path = self.out_dir / '发布监控_UTF8.txt'
        self.text_ascii_path = self.out_dir / 'monitor_ascii.txt'
        self.data: dict[str, Any] = {
            '项目': '百家号多窗口发布监控',
            '更新时间': _now_str(),
            '总体状态': '运行中',
            '窗口': {}
        }
        self.flush()

    def update_slot(self, slot: int, state_cn: str, **kwargs: Any) -> None:
        key = f'窗口{slot}'
        item = self.data['窗口'].setdefault(key, {})
        item['状态'] = state_cn
        item['更新时间'] = _now_str()
        for k, v in kwargs.items():
            item[k] = v
        self.data['更新时间'] = _now_str()
        self.flush()

    def finish(self, summary_text: str | None = None) -> None:
        self.data['总体状态'] = '已结束'
        self.data['更新时间'] = _now_str()
        if summary_text:
            self.data['结果摘要'] = summary_text
        self.flush()

    def flush(self) -> None:
        self.status_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = [
            f"项目：{self.data.get('项目', '')}",
            f"总体状态：{self.data.get('总体状态', '')}",
            f"更新时间：{self.data.get('更新时间', '')}",
            ''
        ]
        windows = self.data.get('窗口', {})
        for name in sorted(windows.keys()):
            item = windows[name]
            lines.append(f"{name}：{item.get('状态', '未知')}")
            for k, v in item.items():
                if k == '状态':
                    continue
                lines.append(f"  - {k}：{v}")
            lines.append('')
        if self.data.get('结果摘要'):
            lines.append(f"结果摘要：{self.data['结果摘要']}")
        text = '\n'.join(lines)
        self.text_path.write_text(text, encoding='utf-8')
        self.text_utf8bom_path.write_text(text, encoding='utf-8-sig')
        ascii_text = text.encode('ascii', errors='replace').decode('ascii')
        self.text_ascii_path.write_text(ascii_text, encoding='ascii')
