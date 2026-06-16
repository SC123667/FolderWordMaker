from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .core import ConversionCancelled, build_word, scan_sources


DEPTHS = {
    "当前": 0,
    "一层": 1,
    "两层": 2,
    "全部": None,
}


class Worker(QObject):
    progress = Signal(int, int, str)
    done = Signal(str, int, int)
    failed = Signal(str)

    def __init__(self, root: str, output: str, depth: int | None) -> None:
        super().__init__()
        self.root = Path(root)
        self.output = Path(output)
        self.depth = depth
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            result = build_word(
                self.root,
                self.output,
                self.depth,
                progress=self.progress.emit,
                cancel_event=self.cancel_event,
            )
            self.done.emit(str(result.output_path), result.source_count, result.page_count)
        except ConversionCancelled:
            self.failed.emit("已停止")
        except ValueError:
            self.failed.emit("0 项")
        except FileNotFoundError:
            self.failed.emit("路径")
        except Exception:
            self.failed.emit("失败")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("目录汇总 Word")
        self.resize(760, 520)
        self.worker: Worker | None = None
        self.thread: QThread | None = None
        self.last_output: str | None = None
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QWidget()
        shell = QVBoxLayout(root)
        shell.setContentsMargins(28, 26, 28, 26)
        shell.setSpacing(18)

        header = QHBoxLayout()
        title = QLabel("目录汇总 Word")
        title.setObjectName("Title")
        version = QLabel(f"v{__version__}")
        version.setObjectName("Version")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(version)
        shell.addLayout(header)

        panel = QFrame()
        panel.setObjectName("Panel")
        form = QVBoxLayout(panel)
        form.setContentsMargins(22, 22, 22, 22)
        form.setSpacing(18)

        form.addLayout(self._row("根目录", self._make_root_picker()))
        form.addLayout(self._row("范围", self._make_depth_picker()))
        form.addLayout(self._row("输出", self._make_output_picker()))

        self.summary = QLabel("0 项")
        self.summary.setObjectName("Summary")
        form.addWidget(self.summary)
        shell.addWidget(panel)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        shell.addWidget(self.progress)

        self.status = QLabel("就绪")
        self.status.setObjectName("Status")
        shell.addWidget(self.status)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        self.log_view.setFixedHeight(126)
        shell.addWidget(self.log_view)

        actions = QHBoxLayout()
        self.scan_btn = QPushButton("扫描")
        self.scan_btn.clicked.connect(lambda: self.refresh_count(write_log=True))
        self.run_btn = QPushButton("生成 Word")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self.start_build)
        self.cancel_btn = QPushButton("停止")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.stop_build)
        self.open_btn = QPushButton("打开")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.open_output)
        actions.addWidget(self.scan_btn)
        actions.addStretch(1)
        actions.addWidget(self.open_btn)
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.run_btn)
        shell.addLayout(actions)

        self.setCentralWidget(root)

    def _row(self, label_text: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)
        label = QLabel(label_text)
        label.setObjectName("FieldLabel")
        label.setFixedWidth(62)
        row.addWidget(label)
        row.addWidget(widget, 1)
        return row

    def _make_root_picker(self) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.root_edit = QLineEdit()
        self.root_edit.textChanged.connect(self._sync_default_output)
        pick = QPushButton("选择")
        pick.clicked.connect(self.pick_root)
        layout.addWidget(self.root_edit, 1)
        layout.addWidget(pick)
        return box

    def _make_output_picker(self) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.output_edit = QLineEdit()
        pick = QPushButton("另存")
        pick.clicked.connect(self.pick_output)
        layout.addWidget(self.output_edit, 1)
        layout.addWidget(pick)
        return box

    def _make_depth_picker(self) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.depth_group = QButtonGroup(self)
        self.depth_group.setExclusive(True)
        for index, text in enumerate(DEPTHS):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setProperty("segment", True)
            button.toggled.connect(lambda _checked: self.refresh_count())
            if text == "当前":
                button.setChecked(True)
            self.depth_group.addButton(button, index)
            layout.addWidget(button)
        layout.addStretch(1)
        return box

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #F5F5F2;
                color: #1E2428;
                font-family: "Inter", "SF Pro Text", "Microsoft YaHei", sans-serif;
                font-size: 14px;
            }
            QLabel#Title {
                font-size: 25px;
                font-weight: 700;
            }
            QLabel#Version {
                color: #6C7378;
                font-size: 12px;
                padding: 6px 10px;
                background: #ECECEA;
                border-radius: 8px;
            }
            QLabel#FieldLabel {
                color: #596166;
                font-weight: 600;
            }
            QLabel#Summary {
                color: #2D5F57;
                font-size: 13px;
                padding-top: 3px;
            }
            QLabel#Status {
                color: #697176;
                min-height: 22px;
            }
            QFrame#Panel {
                background: #FFFFFF;
                border: 1px solid #E1E1DD;
                border-radius: 8px;
            }
            QLineEdit {
                background: #FAFAF8;
                border: 1px solid #D8D8D2;
                border-radius: 8px;
                padding: 10px 12px;
                selection-background-color: #2D5F57;
            }
            QPushButton {
                min-height: 34px;
                padding: 7px 14px;
                border-radius: 8px;
                border: 1px solid #D3D4CE;
                background: #FFFFFF;
                color: #1F2529;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #F1F3F0;
            }
            QPushButton:disabled {
                color: #A2A7AA;
                background: #ECEDEA;
            }
            QPushButton#Primary {
                background: #1F5C54;
                border-color: #1F5C54;
                color: white;
            }
            QPushButton#Primary:hover {
                background: #184C46;
            }
            QPushButton[segment="true"] {
                min-width: 68px;
            }
            QPushButton[segment="true"]:checked {
                background: #1F5C54;
                color: white;
                border-color: #1F5C54;
            }
            QProgressBar {
                height: 8px;
                border: 0;
                border-radius: 4px;
                background: #E3E4DF;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background: #1F5C54;
            }
            QPlainTextEdit#Log {
                background: #202522;
                color: #D9E3DC;
                border: 1px solid #202522;
                border-radius: 8px;
                padding: 10px 12px;
                font-family: "SF Mono", "Menlo", "Consolas", monospace;
                font-size: 12px;
                selection-background-color: #315F55;
            }
            """
        )

    def pick_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "根目录")
        if directory:
            self.root_edit.setText(directory)
            self.refresh_count()

    def pick_output(self) -> None:
        start = self.output_edit.text() or str(Path.home() / "目录汇总.docx")
        path, _ = QFileDialog.getSaveFileName(self, "输出", start, "Word (*.docx)")
        if path:
            if not path.lower().endswith(".docx"):
                path += ".docx"
            self.output_edit.setText(path)

    def _sync_default_output(self) -> None:
        root = self.root_edit.text().strip()
        if root and not self.output_edit.text().strip():
            self.output_edit.setText(str(Path(root) / "目录汇总.docx"))

    def selected_depth(self) -> int | None:
        button = self.depth_group.checkedButton()
        return DEPTHS[button.text()] if button else 0

    def append_log(self, text: str) -> None:
        if not hasattr(self, "log_view"):
            return
        self.log_view.appendPlainText(text)
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def refresh_count(self, write_log: bool = False) -> None:
        if not hasattr(self, "summary"):
            return
        root = self.root_edit.text().strip()
        if not root:
            self.summary.setText("0 项")
            if write_log:
                self.append_log("扫描 0 项")
            return
        try:
            sources = scan_sources(Path(root), self.selected_depth())
            self.summary.setText(f"{len(sources)} 项")
            self.status.setText("就绪")
            if write_log:
                self.append_log(f"扫描 {len(sources)} 项")
        except FileNotFoundError:
            self.summary.setText("0 项")
            self.status.setText("路径")
            if write_log:
                self.append_log("扫描 路径")
        except Exception:
            self.summary.setText("0 项")
            self.status.setText("失败")
            if write_log:
                self.append_log("扫描 失败")

    def start_build(self) -> None:
        root = self.root_edit.text().strip()
        output = self.output_edit.text().strip()
        if not root or not output:
            QMessageBox.warning(self, "缺少", "根目录 / 输出")
            return
        self.set_busy(True)
        self.progress.setValue(0)
        self.status.setText("生成中")
        self.append_log("生成 开始")
        self.worker = Worker(root, output, self.selected_depth())
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(self.on_failed)
        self.worker.done.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def stop_build(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.status.setText("停止中")

    def on_progress(self, current: int, total: int, name: str) -> None:
        value = int((current / total) * 100) if total else 0
        self.progress.setValue(value)
        self.status.setText(name)
        if current < total:
            self.append_log(f"{current + 1}/{total} {name}")

    def on_done(self, output_path: str, source_count: int, page_count: int) -> None:
        self.last_output = output_path
        self.summary.setText(f"{source_count} 项 / {page_count} 页")
        self.status.setText("完成")
        self.append_log(f"完成 {page_count} 页")
        self.progress.setValue(100)
        self.open_btn.setEnabled(True)
        self.set_busy(False)

    def on_failed(self, message: str) -> None:
        self.status.setText(message)
        self.append_log(message)
        self.set_busy(False)

    def set_busy(self, busy: bool) -> None:
        self.root_edit.setEnabled(not busy)
        self.output_edit.setEnabled(not busy)
        self.scan_btn.setEnabled(not busy)
        self.run_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        for button in self.depth_group.buttons():
            button.setEnabled(not busy)

    def open_output(self) -> None:
        if not self.last_output:
            return
        QDesktopServices.openUrl(Path(self.last_output).resolve().as_uri())


def main() -> None:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
