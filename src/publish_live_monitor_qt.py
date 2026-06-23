# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QFrame, QLabel, QMainWindow,
    QScrollArea, QVBoxLayout, QWidget, QHBoxLayout
)


class C:
    BG = '#FFF8F0'
    BG2 = '#FFF3E6'
    FG = '#4A2C0A'
    FG_DIM = '#A07850'
    FG_BRIGHT = '#2B1500'
    ACCENT = '#DA291C'
    YELLOW = '#FFC72C'
    BORDER = '#E0C8A0'
    OK = '#2E7D32'
    WARN = '#FF8F00'
    ERR = '#DA291C'
    RUN = '#1E88E5'
    CHIP_BG = '#F7E7D3'


QSS = f"""
QMainWindow, QWidget {{ background-color: {C.BG}; font-family: 'Microsoft YaHei'; color: {C.FG}; font-size: 9pt; }}
QWidget#header {{ background-color: {C.ACCENT}; min-height: 58px; max-height: 58px; }}
QLabel#title {{ color: white; font-size: 12pt; font-weight: bold; background: transparent; }}
QLabel#sub {{ color: {C.YELLOW}; font-size: 8.5pt; background: transparent; }}
QFrame#row_card {{ background-color: white; border: 1px solid {C.BORDER}; border-radius: 6px; min-height: 34px; max-height: 34px; }}
QLabel#line {{ color: {C.FG_BRIGHT}; font-size: 8.5pt; background: transparent; }}
QLabel#status {{ color: white; font-size: 8.5pt; font-weight: bold; border-radius: 9px; padding: 3px 8px; min-width: 92px; max-width: 92px; }}
QScrollArea {{ border: none; background: transparent; }}
"""


def state_color(text: str) -> str:
    t = text or ''
    if '成功' in t:
        return C.OK
    if '失败' in t or '不足' in t:
        return C.ERR
    if '验证' in t:
        return C.WARN
    return C.RUN


def short_status(item: dict) -> str:
    status = str(item.get('状态', '') or '')
    reason = str(item.get('失败原因', '') or item.get('说明', '') or '')
    if '成功' in status:
        return '发布成功'
    if '失败' in status:
        if 'article' in reason.lower() or '不足' in reason:
            return '文章不足'
        return '发布失败'
    if '验证' in status:
        return '需要验证'
    if '封面' in status:
        return '处理封面'
    if '导入' in status:
        return '导入文章'
    if '提交' in status or '发布' in status:
        return '正在发布'
    if '打开浏览器' in status or '启动' in status:
        return '启动浏览器'
    return status or '等待开始'


class AccountRow(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('row_card')
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(8)

        self.status = QLabel('等待开始')
        self.status.setObjectName('status')
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet(f"background:{C.RUN};")

        self.line = QLabel('-')
        self.line.setObjectName('line')
        self.line.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        root.addWidget(self.status, 0)
        root.addWidget(self.line, 1)

    def update_row(self, account_name: str, article_title: str, published: int, total: int, status_text: str, failure_code: str, failure_reason: str):
        self.status.setText(status_text)
        self.status.setStyleSheet(f"background:{state_color(status_text)};")
        fail = ''
        if failure_code:
            fail = f' | 失败={failure_code}'
            if failure_reason:
                fail += f'({failure_reason})'
        self.line.setText(f'{account_name} | {published}/{total} | {article_title or "-"}{fail}')


class MonitorWindow(QMainWindow):
    def __init__(self, monitor_path: Path):
        super().__init__()
        self.monitor_path = monitor_path
        self.rows: dict[str, AccountRow] = {}
        run_name = monitor_path.parent.name if monitor_path.parent.name else 'monitor'
        self.setWindowTitle(f'发布监控 · {run_name}')
        self.resize(980, 620)
        self.setMinimumSize(760, 420)
        self.setStyleSheet(QSS)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName('header')
        hh = QVBoxLayout(header)
        hh.setContentsMargins(12, 6, 12, 6)
        title = QLabel('发布监控')
        title.setObjectName('title')
        sub = QLabel('窄行模式：账号 | 已发布/计划发 | 文章标题 | 失败摘要')
        sub.setObjectName('sub')
        self.summary = QLabel('运行中')
        self.summary.setStyleSheet('color:white; font-weight:bold; background:transparent;')
        hh.addWidget(title)
        hh.addWidget(sub)
        hh.addWidget(self.summary)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        wrap = QWidget()
        self.list_layout = QVBoxLayout(wrap)
        self.list_layout.setContentsMargins(8, 8, 8, 8)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()
        scroll.setWidget(wrap)
        root.addWidget(scroll, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(1200)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def _load_data(self) -> dict:
        for enc in ('utf-8', 'utf-8-sig', 'gbk'):
            try:
                if self.monitor_path.exists():
                    return json.loads(self.monitor_path.read_text(encoding=enc))
            except Exception:
                pass
        return {}

    def refresh(self):
        data = self._load_data()
        windows = data.get('窗口', {}) if isinstance(data, dict) else {}
        self.summary.setText(f"{data.get('总体状态', '运行中')} · 账号数 {len(windows)}")

        for name in sorted(windows.keys()):
            item = windows[name]
            account_name = str(item.get('账号') or name)
            article_title = str(item.get('文章标题') or '')
            failure_code = str(item.get('失败分类') or '').strip()
            failure_reason = str(item.get('失败原因') or '').strip()
            try:
                published = int(item.get('已发布', 0))
                total = int(item.get('总共', 1))
            except Exception:
                published, total = 0, 1
            status_text = short_status(item)
            if name not in self.rows:
                row = AccountRow()
                self.rows[name] = row
                self.list_layout.insertWidget(self.list_layout.count() - 1, row)
            self.rows[name].update_row(account_name, article_title, published, total, status_text, failure_code, failure_reason)


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r'D:\milu_publish_reverse_20260513\debug\cn_monitor_run_20260521_1718\发布监控.json')
    app = QApplication(sys.argv)
    w = MonitorWindow(path)
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
