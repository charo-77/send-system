# -*- coding: utf-8 -*-
"""百家号发布池监控 - 简洁版 UI（含控制按钮）"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame
)


QSS = """
QMainWindow, QWidget { 
    background-color: #FFFFFF; 
    font-family: 'Segoe UI', 'Microsoft YaHei'; 
    color: #333333;
}

QLabel#title { 
    font-size: 16pt; 
    font-weight: bold; 
    color: #000000;
}

QLabel#summary { 
    font-size: 11pt; 
    color: #666666;
    margin: 10px 0px 8px 0px;
}

QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #CCCCCC;
    border-radius: 4px;
    padding: 6px 12px;
    font-size: 10pt;
    font-weight: bold;
    color: #333333;
}

QPushButton:hover {
    background-color: #F0F0F0;
    border: 1px solid #999999;
}

QPushButton:pressed {
    background-color: #E0E0E0;
}

QPushButton#btn_pause {
    color: #FF9800;
}

QPushButton#btn_resume {
    color: #4CAF50;
}

QPushButton#btn_stop {
    color: #F44336;
}

QFrame#account_card {
    background-color: #F5F5F5;
    border: 1px solid #E0E0E0;
    border-radius: 4px;
    padding: 12px;
    margin-bottom: 8px;
}

QLabel#account_name {
    font-size: 12pt;
    font-weight: bold;
    color: #000000;
}

QLabel#account_stats {
    font-size: 10pt;
    color: #555555;
    margin-top: 4px;
}

QLabel#article_title {
    font-size: 10pt;
    color: #0066CC;
    margin-top: 6px;
    font-style: italic;
}

QLabel#account_failure {
    font-size: 10pt;
    color: #DD0000;
    margin-top: 4px;
    font-weight: bold;
}

QScrollArea { 
    border: none;
    background-color: #FFFFFF;
}
"""

CONTROL_FILE = ".publish_control.json"


class MonitorWindow(QMainWindow):
    def __init__(self, monitor_path):
        super().__init__()
        # 确保路径是 Path 对象
        if isinstance(monitor_path, str):
            monitor_path = Path(monitor_path)
        
        self.monitor_path = monitor_path
        self.control_file = self.monitor_path.parent / CONTROL_FILE
        
        # 调试：打印路径
        print(f"[Monitor] 监控文件路径: {self.monitor_path}")
        print(f"[Monitor] 监控文件存在: {self.monitor_path.exists()}")
        print(f"[Monitor] 控制文件路径: {self.control_file}")
        
        self.setWindowTitle('发布监控')
        self.resize(700, 900)
        self.setMinimumSize(600, 700)
        self.setStyleSheet(QSS)
        
        # 主布局
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(15, 15, 15, 15)
        root.setSpacing(8)
        
        # 标题
        title = QLabel('发布监控')
        title.setObjectName('title')
        root.addWidget(title)
        
        # 摘要
        self.summary = QLabel('加载中...')
        self.summary.setObjectName('summary')
        root.addWidget(self.summary)
        
        # 控制按钮区
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        
        self.btn_pause = QPushButton('⏸ 暂停')
        self.btn_pause.setObjectName('btn_pause')
        self.btn_pause.clicked.connect(self.on_pause)
        button_layout.addWidget(self.btn_pause)
        
        self.btn_resume = QPushButton('▶ 继续')
        self.btn_resume.setObjectName('btn_resume')
        self.btn_resume.clicked.connect(self.on_resume)
        button_layout.addWidget(self.btn_resume)
        
        self.btn_stop = QPushButton('⏹ 停止')
        self.btn_stop.setObjectName('btn_stop')
        self.btn_stop.clicked.connect(self.on_stop)
        button_layout.addWidget(self.btn_stop)
        
        button_layout.addStretch()
        root.addLayout(button_layout)
        
        # 内容区（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)
        scroll.setWidget(self.content)
        root.addWidget(scroll, 1)
        
        # 定时刷新
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        
        self.refresh()
    
    def on_pause(self):
        """暂停发布"""
        self._write_control({"mode": "pause"})
    
    def on_resume(self):
        """继续发布"""
        self._write_control({"mode": "running"})
    
    def on_stop(self):
        """停止发布"""
        self._write_control({"mode": "stop"})
    
    def _write_control(self, payload: dict):
        """写入控制文件"""
        try:
            from datetime import datetime
            payload['updated_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
            self.control_file.parent.mkdir(parents=True, exist_ok=True)
            self.control_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass
    
    def _load_data(self) -> dict:
        """加载数据"""
        try:
            if self.monitor_path.exists():
                data = json.loads(self.monitor_path.read_text(encoding='utf-8'))
                accounts = data.get('账号', [])
                print(f"[Monitor] 数据加载成功: {len(accounts)} 个账号")
                return data
            else:
                print(f"[Monitor] 文件不存在: {self.monitor_path}")
        except Exception as e:
            print(f"[Monitor] 数据加载失败: {e}")
        return {}
    
    def refresh(self):
        """刷新显示"""
        data = self._load_data()
        
        # 更新摘要
        summary = data.get('总体状态', '加载中...')
        self.summary.setText(summary)
        
        # 清空内容
        while self.content_layout.count() > 0:
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 显示账号信息
        accounts = data.get('账号', [])
        if not accounts:
            no_data = QLabel('等待数据...')
            no_data.setStyleSheet("color: #999999; font-size: 11pt;")
            self.content_layout.addWidget(no_data)
            return
        
        for account in accounts:
            name = account.get('name', '?')
            progress = account.get('progress', '0/0')
            success = account.get('success', 0)
            failed = account.get('failed', 0)
            processing = account.get('processing', 0)
            processing_titles = account.get('processing_titles', [])
            failure_reasons = account.get('failure_reasons', [])
            
            # 账号卡片
            card = QFrame()
            card.setObjectName('account_card')
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(0, 0, 0, 0)
            card_layout.setSpacing(3)
            
            # 第一行：账号名 + 进度
            header_layout = QHBoxLayout()
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(15)
            
            name_label = QLabel(name)
            name_label.setObjectName('account_name')
            header_layout.addWidget(name_label)
            
            progress_label = QLabel(f"进度: {progress}")
            progress_label.setObjectName('account_stats')
            progress_label.setStyleSheet("font-weight: bold;")
            header_layout.addWidget(progress_label)
            header_layout.addStretch()
            
            card_layout.addLayout(header_layout)
            
            # 第二行：成功/失败/发布中 统计
            stats_text = []
            if success > 0:
                stats_text.append(f"成功 {success}")
            if failed > 0:
                stats_text.append(f"失败 {failed}")
            if processing > 0:
                stats_text.append(f"发布中 {processing}")
            
            stats_label = QLabel("  |  ".join(stats_text) if stats_text else "")
            stats_label.setObjectName('account_stats')
            card_layout.addWidget(stats_label)
            
            # 当前正在发布的文章（最新的一个）
            if processing_titles:
                title_text = processing_titles[0][:70]  # 截断到 70 字
                title_label = QLabel(title_text)
                title_label.setObjectName('article_title')
                title_label.setWordWrap(True)
                card_layout.addWidget(title_label)
            
            # 失败原因（最近的一个）
            if failure_reasons:
                reason = failure_reasons[0]  # 只显示最近一个
                fail_label = QLabel(f"失败: {reason}")
                fail_label.setObjectName('account_failure')
                fail_label.setWordWrap(True)
                card_layout.addWidget(fail_label)
            
            self.content_layout.addWidget(card)
        
        # 底部空间
        self.content_layout.addStretch()


def main():
    # run_publish_pool.py 会直接传入本轮 monitor.json，避免 UI 误读历史监控目录。
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        root = Path("C:/Users/Administrator/Desktop/mingming/01")
        monitor_base = root / "发布监控"
        path = None
        if monitor_base.exists():
            dirs = [x for x in monitor_base.iterdir() if x.is_dir()]
            if dirs:
                latest_dir = sorted(dirs, key=lambda x: x.stat().st_mtime, reverse=True)[0]
                path = latest_dir / "monitor.json"
        if not path:
            path = Path('monitor.json')
    
    print(f"[UI] 启动: {path}", flush=True)
    print(f"[UI] 文件存在: {path.exists()}", flush=True)
    
    app = QApplication(sys.argv)
    w = MonitorWindow(path)
    w.show()
    
    print(f"[UI] 窗口显示", flush=True)
    
    # 实时刷新（每 500ms）
    def refresh_timer():
        w.refresh()
        QTimer.singleShot(500, refresh_timer)
    
    QTimer.singleShot(500, refresh_timer)
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
