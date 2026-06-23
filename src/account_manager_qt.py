# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
import sys
import traceback
from collections import deque
from pathlib import Path

import re

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from account_monitor import apply_browser_state
from account_store import (
    DEFAULT_ACCOUNT_STORE,
    DEFAULT_SETTINGS_PATH,
    AccountRecord,
    import_accounts_from_xlsx,
    load_account_records,
    load_settings,
    save_account_records,
    save_settings,
)
from embedded_account_browser import EmbeddedBrowserTabs


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_XLSX = REPO_ROOT / "CK.xlsx"
CRASH_LOG_PATH = REPO_ROOT / "runtime" / "account_manager" / "qt_crash.log"


class PublishConfigDialog(QDialog):
    def __init__(self, parent=None, initial: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("发布配置")
        self.resize(460, 260)
        self._initial = initial or {}

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.root_edit = QLineEdit(str(self._initial.get("root") or ""))
        browse_btn = QPushButton("选择")
        browse_btn.clicked.connect(self.pick_root)
        root_row = QHBoxLayout()
        root_row.addWidget(self.root_edit, 1)
        root_row.addWidget(browse_btn)
        root_wrap = QWidget()
        root_wrap.setLayout(root_row)
        form.addRow("目标文件夹", root_wrap)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 999)
        self.count_spin.setValue(int(self._initial.get("count") or 1))
        form.addRow("每账号条数", self.count_spin)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(0, 3600)
        self.interval_spin.setValue(int(self._initial.get("success_interval_seconds") or 0))
        form.addRow("成功间隔秒数", self.interval_spin)

        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 99)
        self.concurrency_spin.setValue(int(self._initial.get("concurrency") or 1))
        form.addRow("并发账号数", self.concurrency_spin)

        self.activity_edit = QLineEdit(str(self._initial.get("activity_name") or ""))
        form.addRow("活动名", self.activity_edit)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["direct", "grouped"])
        mode = str(self._initial.get("publish_mode") or "direct")
        idx = self.mode_combo.findText(mode)
        self.mode_combo.setCurrentIndex(max(idx, 0))
        form.addRow("发布模式", self.mode_combo)

        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok_btn = QPushButton("开始发布")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        root.addLayout(buttons)

    def pick_root(self):
        folder = QFileDialog.getExistingDirectory(self, "选择发布目录", self.root_edit.text().strip() or str(REPO_ROOT))
        if folder:
            self.root_edit.setText(folder)

    def payload(self) -> dict:
        return {
            "root": self.root_edit.text().strip(),
            "count": self.count_spin.value(),
            "success_interval_seconds": self.interval_spin.value(),
            "concurrency": self.concurrency_spin.value(),
            "activity_name": self.activity_edit.text().strip(),
            "publish_mode": self.mode_combo.currentText().strip() or "direct",
        }


def _display_publish_quota(value: str) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"\(\d{1,2}/\d{1,2}/\d{1,2}\)", text) else ""


class AccountManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store_path = DEFAULT_ACCOUNT_STORE
        self.settings_path = DEFAULT_SETTINGS_PATH
        self.settings = load_settings(self.settings_path)
        self.accounts: list[AccountRecord] = []
        self.group_names: list[str] = list(self.settings.get("group_names") or [])
        self.monitor_rows: list[dict] = []
        self.monitor_by_worker: dict[str, dict] = {}
        self.visible_accounts: list[AccountRecord] = []
        self.query_queue: deque[AccountRecord] = deque()
        self.query_running = False
        self.query_timer = QTimer(self)
        self.query_timer.setSingleShot(True)
        self.query_timer.timeout.connect(self._on_query_timeout)

        self.setWindowTitle("账号管理器")
        self.resize(1460, 860)
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #f6f8fb;
                color: #203047;
                font-size: 13px;
            }
            QLineEdit, QComboBox, QSpinBox, QTableWidget {
                background: #ffffff;
                border: 1px solid #d7e1ee;
                border-radius: 10px;
                padding: 6px 8px;
                selection-background-color: #dbeafe;
                selection-color: #1d3557;
            }
            QPushButton {
                background: #e8f0fb;
                border: 1px solid #c8d8ee;
                border-radius: 10px;
                padding: 8px 14px;
                color: #23415f;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #dbeafe;
            }
            QLabel[role="muted"] {
                color: #5c728f;
                padding: 2px 4px;
            }
            QHeaderView::section {
                background: #eef4fb;
                color: #48617f;
                border: none;
                border-bottom: 1px solid #d7e1ee;
                padding: 8px;
                font-weight: 600;
            }
            QTableWidget {
                gridline-color: #edf2f8;
                alternate-background-color: #f9fbfe;
            }
            QTableWidget::item:selected {
                background: #dbeafe;
                color: #1d3557;
            }
            QTabWidget::pane {
                border: 1px solid #d7e1ee;
                border-radius: 12px;
                background: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background: #edf4fb;
                color: #4a607b;
                border: 1px solid #d7e1ee;
                border-bottom: none;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                padding: 8px 14px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #1f3955;
            }
            QSplitter::handle {
                background: #e7edf5;
                width: 6px;
            }
            """
        )

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        toolbar = QHBoxLayout()
        self.publish_btn = QPushButton("发布")
        self.publish_btn.clicked.connect(self.launch_publish)
        self.query_btn = QPushButton("查询")
        self.query_btn.clicked.connect(self.query_accounts)
        self.query_toggle_btn = QPushButton("展开查询结果")
        self.query_toggle_btn.clicked.connect(self.toggle_query_panel)
        self.import_btn = QPushButton("导入 CK.xlsx")
        self.import_btn.clicked.connect(self.import_xlsx)
        self.create_group_btn = QPushButton("创建分组")
        self.create_group_btn.clicked.connect(self.create_group)
        self.batch_group_btn = QPushButton("添加分组")
        self.batch_group_btn.clicked.connect(self.batch_set_group)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.reload_accounts)

        self.group_filter = QComboBox()
        self.group_filter.currentIndexChanged.connect(self.render_table)
        self.group_filter.setMinimumWidth(140)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索账号名称 / 昵称 / 分组")
        self.search_edit.textChanged.connect(self.render_table)

        toolbar.addWidget(self.publish_btn)
        toolbar.addWidget(self.query_btn)
        toolbar.addWidget(self.query_toggle_btn)
        toolbar.addWidget(self.create_group_btn)
        toolbar.addWidget(self.batch_group_btn)
        toolbar.addWidget(self.import_btn)
        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.group_filter)
        toolbar.addWidget(self.search_edit, 1)
        root.addLayout(toolbar)

        self.query_panel = QWidget()
        query_layout = QVBoxLayout(self.query_panel)
        query_layout.setContentsMargins(0, 0, 0, 0)
        query_layout.setSpacing(6)
        self.query_hint = QLabel("查询当前筛选结果里的全部账号；只展示清洗后的结果，脏数据直接留空。")
        self.query_hint.setProperty("role", "muted")
        query_layout.addWidget(self.query_hint)
        self.query_table = QTableWidget(0, 7)
        self.query_table.setHorizontalHeaderLabels(["昨日收益", "机构", "账号ID", "活跃值", "发布数量", "分组", "状态"])
        self.query_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.query_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.query_table.verticalHeader().setVisible(False)
        self.query_table.setAlternatingRowColors(True)
        self.query_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.query_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.query_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.query_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.query_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.query_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.query_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        query_layout.addWidget(self.query_table)
        self.query_panel.setVisible(False)
        root.addWidget(self.query_panel)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(self.splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["账号名称", "昵称", "分组"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(1, 86)
        self.table.setColumnWidth(2, 68)
        self.table.itemDoubleClicked.connect(lambda *_: self.open_selected_account())
        left_layout.addWidget(self.table, 1)

        self.embedded_tabs = EmbeddedBrowserTabs(self.accounts, self)
        self.embedded_tabs.statusChanged.connect(self.on_browser_status_changed)
        self.embedded_tabs.snapshotChanged.connect(self.on_browser_snapshot_changed)
        self.embedded_tabs.accountReady.connect(self.on_account_ready)

        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(self.embedded_tabs)
        self.splitter.setSizes([360, 1100])

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(12000)
        self.refresh_timer.timeout.connect(self.refresh_from_state)
        self.refresh_timer.start()

        QShortcut(QKeySequence("Delete"), self, activated=self.delete_selected_accounts)
        QShortcut(QKeySequence("Ctrl+G"), self, activated=self.batch_set_group)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search_edit.setFocus)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.reload_accounts)

        self.reload_accounts()

    def selected_records(self) -> list[AccountRecord]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()}) if self.table.selectionModel() else []
        records: list[AccountRecord] = []
        for row in rows:
            if 0 <= row < len(self.visible_accounts):
                records.append(self.visible_accounts[row])
        return records

    def current_record(self) -> AccountRecord | None:
        records = self.selected_records()
        return records[0] if records else None

    def toggle_query_panel(self):
        visible = not self.query_panel.isVisible()
        self.query_panel.setVisible(visible)
        self.query_toggle_btn.setText("收起查询结果" if visible else "展开查询结果")

    def _build_query_rows(self) -> list[dict]:
        rows: list[dict] = []
        visible_workers = {item.worker_name for item in self.visible_accounts}
        account_by_worker = {item.worker_name: item for item in self.accounts}
        for snapshot in self.monitor_rows:
            worker_name = str(snapshot.get("worker_name") or "").strip()
            if not worker_name or worker_name not in visible_workers:
                continue
            item = account_by_worker.get(worker_name)
            status = str(snapshot.get("online_status") or (item.online_status if item else "unknown") or "unknown").strip().lower()
            rows.append(
                {
                    "worker_name": worker_name,
                    "income": str(snapshot.get("yesterday_income") or "").strip(),
                    "org_name": str(snapshot.get("org_name") or "").strip(),
                    "account_id": (item.real_name or item.account_name or item.worker_name) if item else worker_name,
                    "active_value": str(snapshot.get("activity_value") or "").strip(),
                    "publish_quota": _display_publish_quota(snapshot.get("publish_quota") or ""),
                    "group_name": (item.group_name if item else str(snapshot.get("group_name") or "").strip()),
                    "status": status,
                }
            )
        return rows

    def refresh_query_table(self):
        rows = self._build_query_rows()
        self.query_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            items = [
                QTableWidgetItem(row["income"]),
                QTableWidgetItem(row["org_name"]),
                QTableWidgetItem(row["account_id"]),
                QTableWidgetItem(row["active_value"]),
                QTableWidgetItem(row["publish_quota"]),
                QTableWidgetItem(row["group_name"]),
                QTableWidgetItem("掉线" if row["status"] == "offline" else "在线" if row["status"] == "online" else row["status"]),
            ]
            if row["status"] == "offline":
                red = QColor("#d93025")
                for item in items:
                    item.setForeground(red)
            for col, item in enumerate(items):
                self.query_table.setItem(row_index, col, item)

    def refresh_from_state(self):
        self.monitor_rows = apply_browser_state(self.accounts)
        self.monitor_by_worker = {row.get("worker_name") or "": row for row in self.monitor_rows}
        self.render_table()
        self.refresh_query_table()

    def on_browser_status_changed(self, worker_name: str, status: str, real_name: str):
        for item in self.accounts:
            if item.worker_name == worker_name:
                item.online_status = status
                if real_name:
                    item.real_name = real_name
                break
        self.render_table()
        self.refresh_query_table()

    def on_browser_snapshot_changed(self, worker_name: str, snapshot: dict):
        if worker_name:
            self.monitor_by_worker[worker_name] = snapshot or {}
        self.render_table()
        self.refresh_query_table()

    def reload_accounts(self):
        self.accounts = load_account_records(self.store_path)
        self.embedded_tabs.accounts = self.accounts
        known_groups = {item.group_name for item in self.accounts if item.group_name}
        known_groups.update(self.group_names)
        self.group_names = sorted(x for x in known_groups if x)
        self.render_group_filter()
        self.refresh_from_state()

    def render_group_filter(self):
        current = self.group_filter.currentText().strip()
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        self.group_filter.addItem("全部")
        for group in self.group_names:
            self.group_filter.addItem(group)
        idx = self.group_filter.findText(current)
        self.group_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.group_filter.blockSignals(False)

    def render_table(self):
        selected_workers = {item.worker_name for item in self.selected_records()}
        group = self.group_filter.currentText().strip()
        keyword = self.search_edit.text().strip().lower()
        visible: list[AccountRecord] = []
        for item in self.accounts:
            if group and group != "全部" and item.group_name != group:
                continue
            haystack = " | ".join([item.real_name, item.worker_name, item.group_name]).lower()
            if keyword and keyword not in haystack:
                continue
            visible.append(item)

        self.visible_accounts = visible
        self.table.setRowCount(len(visible))
        self.table.clearSelection()
        for row, item in enumerate(visible):
            real_name_item = QTableWidgetItem(item.real_name or item.account_name or item.worker_name)
            nickname_item = QTableWidgetItem(item.worker_name)
            group_item = QTableWidgetItem(item.group_name)
            if item.online_status == "offline":
                red = QColor("#d93025")
                real_name_item.setForeground(red)
                nickname_item.setForeground(red)
                group_item.setForeground(red)
            self.table.setItem(row, 0, real_name_item)
            self.table.setItem(row, 1, nickname_item)
            self.table.setItem(row, 2, group_item)
            if item.worker_name in selected_workers:
                self.table.selectRow(row)

        if visible and not selected_workers:
            self.table.selectRow(0)

    def import_xlsx(self):
        start = str(self.settings.get("last_xlsx_path") or DEFAULT_XLSX)
        path, _ = QFileDialog.getOpenFileName(self, "选择 CK.xlsx", start, "Excel Files (*.xlsx)")
        if not path:
            return
        import_accounts_from_xlsx(Path(path), self.store_path)
        self.settings["last_xlsx_path"] = path
        save_settings(self.settings, self.settings_path)
        self.reload_accounts()

    def create_group(self):
        text, ok = QInputDialog.getText(self, "创建分组", "输入新分组名")
        if not ok:
            return
        group_name = text.strip()
        if not group_name:
            return
        if group_name not in self.group_names:
            self.group_names.append(group_name)
            self.group_names.sort()
            self.settings["group_names"] = self.group_names
            save_settings(self.settings, self.settings_path)
        self.render_group_filter()

    def batch_set_group(self):
        records = self.selected_records()
        if not records:
            QMessageBox.warning(self, "提示", "先选中一个或多个账号")
            return
        options = ["(清空分组)"] + self.group_names
        text, ok = QInputDialog.getItem(self, "添加分组", "选择分组", options, editable=False)
        if not ok:
            return
        group_name = "" if text == "(清空分组)" else text.strip()
        for item in records:
            item.group_name = group_name
        if group_name and group_name not in self.group_names:
            self.group_names.append(group_name)
            self.group_names.sort()
        self.settings["group_names"] = self.group_names
        save_settings(self.settings, self.settings_path)
        save_account_records(self.accounts, self.store_path)
        self.reload_accounts()

    def edit_fingerprint_profile(self):
        records = self.selected_records()
        if not records:
            QMessageBox.warning(self, "提示", "先选中一个或多个账号")
            return
        current = records[0].fingerprint_profile or records[0].fingerprint_id or ""
        text, ok = QInputDialog.getText(self, "设置指纹浏览器", "输入指纹浏览器路径/ID", text=current)
        if not ok:
            return
        value = text.strip()
        for item in records:
            item.fingerprint_profile = value
            item.fingerprint_id = value
        save_account_records(self.accounts, self.store_path)
        self.reload_accounts()

    def delete_selected_accounts(self):
        records = self.selected_records()
        if not records:
            return
        names = ", ".join(item.worker_name for item in records[:5])
        if len(records) > 5:
            names += " ..."
        reply = QMessageBox.question(self, "删除账号", f"确认删除 {len(records)} 个账号？\n{names}")
        if reply != QMessageBox.StandardButton.Yes:
            return
        deleted = {item.worker_name for item in records}
        self.accounts = [item for item in self.accounts if item.worker_name not in deleted]
        save_account_records(self.accounts, self.store_path)
        self.reload_accounts()

    def show_context_menu(self, pos):
        menu = QMenu(self)
        act_open = menu.addAction("打开主页")
        act_query = menu.addAction("查询")
        act_group = menu.addAction("添加分组")
        act_fp = menu.addAction("设置指纹浏览器")
        act_delete = menu.addAction("删除")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == act_open:
            self.open_selected_account()
        elif action == act_query:
            self.query_accounts()
        elif action == act_group:
            self.batch_set_group()
        elif action == act_fp:
            self.edit_fingerprint_profile()
        elif action == act_delete:
            self.delete_selected_accounts()

    def open_selected_account(self):
        item = self.current_record()
        if item is None:
            QMessageBox.warning(self, "提示", "先选中一个账号")
            return
        if not item.ck:
            QMessageBox.warning(self, "提示", f"账号 {item.worker_name} 没有 CK，无法打开主页")
            return
        self.embedded_tabs.open_account(item)

    def query_accounts(self):
        if self.query_running:
            QMessageBox.information(self, "查询进行中", "当前查询还没跑完，别连点。")
            return
        records = [item for item in self.visible_accounts if item.ck]
        if not records:
            QMessageBox.warning(self, "提示", "当前分组/筛选结果里没有可查询账号")
            return
        self.query_queue = deque(records)
        self.query_running = True
        self.query_btn.setEnabled(False)
        self.query_btn.setText(f"查询中 {len(records)}")
        if not self.query_panel.isVisible():
            self.toggle_query_panel()
        self._run_next_query_step()

    def _finish_query(self):
        self.query_running = False
        self.query_btn.setEnabled(True)
        self.query_btn.setText("查询")
        QMessageBox.information(self, "查询完成", "当前页面显示分组的账号已分批查询。")
        self.refresh_from_state()

    def _run_next_query_step(self):
        if not self.query_queue:
            self._finish_query()
            return
        item = self.query_queue[0]
        self.embedded_tabs.open_account(item)
        self.query_btn.setText(f"查询中 {len(self.query_queue)}")
        self.query_timer.start(8000)

    def on_account_ready(self, worker_name: str):
        if not self.query_running:
            return
        if not self.query_queue:
            return
        current = self.query_queue[0]
        if current.worker_name != worker_name:
            return
        self.query_timer.stop()
        self.query_queue.popleft()
        QTimer.singleShot(400, self._run_next_query_step)

    def _on_query_timeout(self):
        if not self.query_running:
            return
        if self.query_queue:
            self.query_queue.popleft()
        self._run_next_query_step()

    def launch_publish(self):
        records = [item for item in self.accounts if item.enabled]
        current_group = self.group_filter.currentText().strip()
        keyword = self.search_edit.text().strip().lower()
        filtered = []
        for item in records:
            if current_group and current_group != "全部" and item.group_name != current_group:
                continue
            haystack = " | ".join([item.real_name, item.worker_name, item.group_name]).lower()
            if keyword and keyword not in haystack:
                continue
            filtered.append(item)

        if not filtered:
            QMessageBox.warning(self, "提示", "当前筛选结果没有可发布账号")
            return

        defaults = {
            "root": str(self.settings.get("last_publish_root") or ""),
            "count": int(self.settings.get("last_publish_count") or 1),
            "success_interval_seconds": int(self.settings.get("last_success_interval_seconds") or 0),
            "concurrency": int(self.settings.get("last_concurrency") or min(4, max(1, len(filtered)))),
            "activity_name": str(self.settings.get("last_activity_name") or ""),
            "publish_mode": str(self.settings.get("last_publish_mode") or "direct"),
        }
        dialog = PublishConfigDialog(self, defaults)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        if not payload["root"]:
            QMessageBox.warning(self, "提示", "请先选择目标文件夹")
            return

        self.settings["last_publish_root"] = payload["root"]
        self.settings["last_publish_count"] = payload["count"]
        self.settings["last_success_interval_seconds"] = payload["success_interval_seconds"]
        self.settings["last_concurrency"] = payload["concurrency"]
        self.settings["last_activity_name"] = payload["activity_name"]
        self.settings["last_publish_mode"] = payload["publish_mode"]
        save_settings(self.settings, self.settings_path)

        selected_workers = [item.worker_name for item in filtered if item.ck]
        if not selected_workers:
            QMessageBox.warning(self, "提示", "当前筛选账号都没有 CK，无法发布")
            return

        cmd = [
            sys.executable,
            str(Path(__file__).with_name("run_publish_pool.py")),
            "--root",
            payload["root"],
            "--accounts",
            ",".join(selected_workers),
            "--count",
            str(payload["count"]),
            "--publish-mode",
            payload["publish_mode"],
            "--account-store",
            str(self.store_path),
            "--success-interval-seconds",
            str(payload["success_interval_seconds"]),
            "--concurrency",
            str(payload["concurrency"]),
        ]
        if payload["activity_name"]:
            cmd += ["--activity-name", payload["activity_name"]]
        subprocess.Popen(cmd, cwd=str(REPO_ROOT))



def _log_unhandled_exception(exc_type, exc_value, exc_tb):
    CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CRASH_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write("\n=== UNHANDLED EXCEPTION ===\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=fh)


def main() -> int:
    sys.excepthook = _log_unhandled_exception
    app = QApplication(sys.argv)
    window = AccountManagerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
