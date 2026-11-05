"""Paper Word desktop: tray selection assistant for Windows and macOS."""
import json
import math
import os
import sys
import threading
import time
from pathlib import Path

import keyring
from PySide6.QtCore import QObject, QRunnable, QStandardPaths, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QSystemTrayIcon,
    QTextBrowser, QVBoxLayout, QWidget)
from pynput import keyboard, mouse

from selection import Selection, get_selection
from word_engine import GLMClient, WORD, valid_selection, core_html, detail_html, sections, test_connection, probe_reachability

SERVICE = "paper-word-desktop"
ACCOUNT = "glm-api-key"
DEFAULTS = {"model": "glm-5.3-flash", "mode": "auto"}


def settings_path():
    return Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)) / "settings.json"


def load_settings():
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        result = dict(DEFAULTS)
        if isinstance(data, dict):
            for key in DEFAULTS:
                if isinstance(data.get(key), str):
                    result[key] = data[key]
        if result["model"].lower() == "glm-4.7-flash":
            result["model"] = DEFAULTS["model"]
        if result["mode"] not in ("auto", "hotkey"):
            result["mode"] = "auto"
        return result
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(settings):
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({k: settings[k] for k in DEFAULTS}, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def icon():
    asset_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    artwork = asset_root / "assets" / "icon.png"
    if artwork.is_file():
        result = QIcon(str(artwork))
        if not result.isNull():
            return result
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#385f91"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(3, 3, 58, 58, 14, 14)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(37)
    painter.setFont(font)
    painter.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), "W")
    painter.end()
    return QIcon(pix)


class WorkSignals(QObject):
    update = Signal(int, str, str)
    complete = Signal(int, str, str)
    error = Signal(int, str, str)
    selection = Signal(object, int, int, bool, int)


class AnalysisJob(QRunnable):
    def __init__(self, engine, token, selection, key, config, mode, signals):
        super().__init__()
        self.engine, self.token, self.selection = engine, token, selection
        self.key, self.config, self.mode, self.signals = key, dict(config), mode, signals

    def run(self):
        try:
            value = self.engine.analyze(self.selection.word, self.selection.context, self.key,
                self.config["model"], self.mode,
                lambda text: self.signals.update.emit(self.token, self.mode, text))
            self.signals.complete.emit(self.token, self.mode, value)
        except Exception as error:
            message = str(error) if isinstance(error, ValueError) else "查询失败，请检查网络和配置。"
            self.signals.error.emit(self.token, self.mode, message)


class SelectionJob(QRunnable):
    def __init__(self, x, y, manual, serial, signals):
        super().__init__()
        self.x, self.y, self.manual, self.serial, self.signals = x, y, manual, serial, signals

    def run(self):
        result = get_selection(self.x, self.y, prefer_focus=self.manual)
        self.signals.selection.emit(result, self.x, self.y, self.manual, self.serial)


class HookSignals(QObject):
    mouse_release = Signal(int, int)
    mouse_press = Signal()
    hotkey = Signal()
    dismiss = Signal()
    escape = Signal()


class DiagnosticSignals(QObject):
    finished = Signal(str)


class DiagnosticJob(QRunnable):
    def __init__(self, key, model, signals):
        super().__init__()
        self.key, self.model, self.signals = key, model, signals

    def run(self):
        try:
            message = test_connection(self.key, self.model)
        except ValueError as error:
            message = str(error)
        except Exception:
            message = "测试失败，请检查网络和设置。"
        self.signals.finished.emit(message)


class SettingsDialog(QDialog):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setWindowTitle("LLMs-powered Translator 设置")
        self.setMinimumWidth(450)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.model = QLineEdit(owner.config["model"])
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("留空则保留已保存的密钥")
        self.mode = QComboBox()
        self.mode.addItem("划词后自动弹出", "auto")
        self.mode.addItem("仅用快捷键", "hotkey")
        self.mode.setCurrentIndex(max(0, self.mode.findData(owner.config["mode"])))
        form.addRow("GLM 模型", self.model)
        form.addRow("GLM API Key", self.password)
        form.addRow("触发方式", self.mode)
        layout.addLayout(form)
        key = "⌘ + ⌥ + W" if sys.platform == "darwin" else "Ctrl + Alt + W"
        notice = QLabel("快捷键：" + key + "。自动模式在鼠标划选或双击后尝试读取选区。\n"
            "查询时会将选词及可获取的附近原文发送给 GLM；仅单词及上下文缓存于本次运行内。\n"
            "使用 GLM Coding Plan 接口直连，不使用代理；密钥由系统凭据管理器保存。")
        notice.setWordWrap(True)
        notice.setStyleSheet("font-size:12px")
        layout.addWidget(notice)
        self.diagnostic_status = QLabel("测试会发送一次简短请求，可能消耗少量套餐额度。")
        self.diagnostic_status.setWordWrap(True)
        self.diagnostic_status.setStyleSheet("font-size:12px")
        layout.addWidget(self.diagnostic_status)
        self.diagnostic_signals = DiagnosticSignals()
        self.diagnostic_signals.finished.connect(self.diagnostic_finished)
        buttons = QHBoxLayout()
        self.test_button = QPushButton("测试连接")
        self.test_button.clicked.connect(self.test_connection)
        cancel, save = QPushButton("取消"), QPushButton("保存")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.save)
        buttons.addWidget(self.test_button); buttons.addStretch(); buttons.addWidget(cancel); buttons.addWidget(save)
        layout.addLayout(buttons)

    def test_connection(self):
        try:
            key = self.password.text().strip() or keyring.get_password(SERVICE, ACCOUNT) or ""
        except Exception:
            self.diagnostic_status.setText("无法读取系统凭据，请重新填写密钥。")
            return
        model = self.model.text().strip()
        if not key or not model:
            self.diagnostic_status.setText("请先填写 Coding Plan 密钥和模型名称。")
            return
        self.test_button.setEnabled(False)
        self.diagnostic_status.setText("正在测试连接和认证……")
        QThreadPool.globalInstance().start(DiagnosticJob(key, model, self.diagnostic_signals))

    @Slot(str)
    def diagnostic_finished(self, message):
        self.test_button.setEnabled(True)
        self.diagnostic_status.setText(message)

    def save(self):
        model = self.model.text().strip()
        if not model:
            QMessageBox.warning(self, "设置", "请填写 GLM 模型名称。")
            return
        try:
            if self.password.text().strip():
                if keyring.get_keyring().priority <= 0:
                    raise RuntimeError("系统凭据存储不可用")
                keyring.set_password(SERVICE, ACCOUNT, self.password.text().strip())
            self.owner.config = {"model":model, "mode":self.mode.currentData()}
            save_settings(self.owner.config)
            self.owner.engine.clear()
            self.password.clear()
            self.accept()
        except Exception:
            QMessageBox.warning(self, "设置", "保存失败，请检查系统凭据存储和设置目录。")


class Popup(QWidget):
    def __init__(self, owner):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.owner = owner
        self.setObjectName("pwsPopup")
        self._core_text = ""
        self.setWindowTitle("LLMs-powered Translator")
        self.setMinimumWidth(360)
        self.resize(400, 200)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        self.title = QLabel()
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self.title)
        self.context_status = QLabel()
        outer.addWidget(self.context_status)
        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(False)
        outer.addWidget(self.content)
        row = QHBoxLayout()
        self.buttons = {}
        for name in ("搭配", "词根", "近义词"):
            button = QPushButton("查看" + name)
            button.clicked.connect(lambda checked=False, value=name: owner.toggle_detail(value))
            self.buttons[name] = button
            row.addWidget(button)
        row.addStretch()
        outer.addLayout(row)
        self.detail = QTextBrowser()
        self.detail.hide()
        outer.addWidget(self.detail)
        self.content.document().contentsChanged.connect(self.schedule_fit)
        self.detail.document().contentsChanged.connect(self.schedule_fit)
        self._fit_pending = False
        QApplication.styleHints().colorSchemeChanged.connect(self.refresh_theme)
        self.refresh_theme()

    def schedule_fit(self):
        if not self._fit_pending:
            self._fit_pending = True
            QTimer.singleShot(0, self.fit_contents)

    def fit_contents(self):
        self._fit_pending = False
        width = max(100, self.width() - 26)
        for browser, minimum, maximum in ((self.content, 42, 190), (self.detail, 90, 270)):
            browser.document().setTextWidth(width)
            height = max(minimum, min(maximum, math.ceil(browser.document().size().height()) + 8))
            if browser.minimumHeight() != height or browser.maximumHeight() != height:
                browser.setFixedHeight(height)
        self.layout().activate()
        wanted = self.layout().sizeHint().height()
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            wanted = min(wanted, area.height())
        self.resize(self.width(), wanted)
        if screen and self.isVisible():
            self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_fit_pending'):
            self.schedule_fit()

    def refresh_theme(self, scheme=None):
        scheme = scheme if scheme is not None else QApplication.styleHints().colorScheme()
        dark = scheme == Qt.ColorScheme.Dark
        if scheme == Qt.ColorScheme.Unknown:
            dark = QApplication.palette().window().color().lightness() < 128
        background, foreground, muted, border = (
            ("#20242c", "#f0f2f5", "#bbc3ce", "#49515d") if dark else
            ("#ffffff", "#18243a", "#606b7a", "#d9dfe7")
        )
        button_bg, button_border = ("#363d49", "#5b6574") if dark else ("#f5f7fa", "#cbd3dd")
        self._muted, self._border = muted, border
        self.setStyleSheet(
            "QWidget#pwsPopup { background:" + background + "; color:" + foreground + "; }"
            "QPushButton { background:" + button_bg + "; color:" + foreground + "; border:1px solid " + button_border + "; border-radius:4px; padding:3px 6px; }"
        )
        self.title.setStyleSheet("font-size:15px;font-weight:600;color:" + foreground)
        self.context_status.setStyleSheet("font-size:11px;color:" + muted)
        browser_style = "QTextBrowser {border:0;background:transparent;font-size:13px;color:" + foreground + ";}"
        self.content.setStyleSheet(browser_style)
        self.detail.setStyleSheet(browser_style)
        if self._core_text:
            self.content.setHtml(core_html(self._core_text, muted, border))

    def set_core(self, text):
        self._core_text = text
        self.content.setHtml(core_html(text, self._muted, self._border))

    def set_detail(self, active):
        for name, button in self.buttons.items():
            button.setText(("收起" if name == active else "查看") + name)
        self.detail.setVisible(bool(active))
        self.schedule_fit()


class Controller(QObject):
    def __init__(self, app):
        super().__init__()
        self.app, self.config = app, load_settings()
        try:
            save_settings(self.config)  # Drop the legacy endpoint field while preserving other settings.
        except OSError:
            pass
        self.engine, self.pool = GLMClient(), QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(4)
        self.signals = WorkSignals()
        self.signals.update.connect(self.on_update)
        self.signals.complete.connect(self.on_complete)
        self.signals.error.connect(self.on_error)
        self.signals.selection.connect(self.on_selection)
        self.hooks = HookSignals()
        self.hooks.mouse_release.connect(self.on_mouse_release)
        self.hooks.mouse_press.connect(self.on_mouse_press)
        self.hooks.hotkey.connect(self.on_hotkey)
        self.hooks.dismiss.connect(self.on_key_dismiss)
        self.hooks.escape.connect(self.dismiss_popup)
        self.popup = Popup(self)
        self.token, self.selection_serial, self.selection, self.active_detail = 0, 0, None, None
        self.extra_text, self.extra_running, self.extra_done = "", False, False
        self.dialog = None
        self.tray = QSystemTrayIcon(icon(), self)
        self.tray.setToolTip("LLMs-powered Translator")
        menu = QMenu()
        for label, callback in (("手动查询", self.manual_query), ("设置", self.open_settings), ("退出", self.quit)):
            action = QAction(label, menu); action.triggered.connect(callback); menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.manual_query() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self._start_hooks()

    def _start_hooks(self):
        self._last_down = None
        self._last_click = (0, 0, 0.0)
        if sys.platform == "darwin":
            try:
                import ApplicationServices as ax
                if not ax.AXIsProcessTrusted():
                    ax.AXIsProcessTrustedWithOptions({ax.kAXTrustedCheckOptionPrompt: True})
                    self.tray.showMessage("LLMs-powered Translator", "请在系统设置中允许辅助功能访问；快捷键还可能需要输入监控权限。")
            except Exception:
                self.tray.showMessage("LLMs-powered Translator", "请检查系统辅助功能和输入监控权限。")
        def on_click(x, y, button, pressed):
            if button != mouse.Button.left:
                return
            if pressed:
                self._last_down = (x, y)
                self.hooks.mouse_press.emit()
                return
            now = time.monotonic()
            previous_x, previous_y, previous_t = self._last_click
            double = now - previous_t < 0.45 and abs(x-previous_x) < 5 and abs(y-previous_y) < 5
            self._last_click = (x, y, now)
            down = self._last_down
            self._last_down = None
            if down and (abs(x-down[0]) + abs(y-down[1]) > 4 or double):
                self.hooks.mouse_release.emit(int(x), int(y))
        try:
            self.mouse_listener = mouse.Listener(on_click=on_click)
            self.mouse_listener.start()
            hotkey = "<cmd>+<alt>+w" if sys.platform == "darwin" else "<ctrl>+<alt>+w"
            self.key_listener = keyboard.GlobalHotKeys({hotkey: self.hooks.hotkey.emit,
                "<esc>": self.hooks.escape.emit, "<left>": self.hooks.dismiss.emit,
                "<right>": self.hooks.dismiss.emit, "<up>": self.hooks.dismiss.emit,
                "<down>": self.hooks.dismiss.emit})
            self.key_listener.start()
        except Exception:
            self.tray.showMessage("LLMs-powered Translator", "全局监听不可用，请检查系统辅助功能权限或使用手动查询。")

    @Slot(int, int)
    def on_mouse_release(self, x, y):
        if self.config["mode"] != "auto" or self.dialog is not None:
            return
        if QApplication.topLevelAt(QCursor.pos()) is not None:
            return
        self.selection_serial += 1
        serial = self.selection_serial
        QTimer.singleShot(160, lambda: self.pool.start(SelectionJob(x, y, False, serial, self.signals)) if serial == self.selection_serial else None)

    def dismiss_popup(self):
        self.selection_serial += 1
        self.token += 1
        self.popup.hide()

    @Slot()
    def on_mouse_press(self):
        if QApplication.topLevelAt(QCursor.pos()) is not self.popup:
            self.dismiss_popup()

    @Slot()
    def on_key_dismiss(self):
        if self.popup.isVisible() and not self.popup.isActiveWindow():
            self.dismiss_popup()

    @Slot()
    def on_hotkey(self):
        if self.config["mode"] != "hotkey" or self.dialog is not None:
            return
        if QApplication.topLevelAt(QCursor.pos()) is not None:
            return
        position = mouse.Controller().position
        self.selection_serial += 1
        self.pool.start(SelectionJob(position[0], position[1], True, self.selection_serial, self.signals))

    @Slot(object, int, int, bool, int)
    def on_selection(self, selection, x, y, manual, serial):
        if serial != self.selection_serial:
            return
        if selection is None:
            return
        if not valid_selection(selection.selected) or not valid_selection(selection.word):
            return
        self.show_word(selection)

    def show_word(self, selection):
        if not valid_selection(selection.selected) or not valid_selection(selection.word):
            return
        self.selection_serial += 1
        self.token += 1
        self.selection = selection
        self.active_detail, self.extra_text, self.extra_running, self.extra_done = None, "", False, False
        self.popup.set_detail(None)
        self.popup.title.setText((selection.selected + " → " if selection.selected != selection.word else "") + selection.word)
        self.popup.context_status.setText("" if selection.context else "未获取上下文")
        self.popup.context_status.setVisible(not bool(selection.context))
        self.popup._core_text = ""
        self.popup.content.setPlainText("正在连接 GLM……")
        pos = QCursor.pos()
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.popup.move(max(area.left(), min(pos.x()+12, area.right()-self.popup.width())),
                max(area.top(), min(pos.y()+16, area.bottom()-self.popup.height())))
        self.popup.show()
        self.popup.raise_()
        self.submit("core")

    def submit(self, mode):
        if not self.selection or not valid_selection(self.selection.selected) or not valid_selection(self.selection.word):
            return False
        try:
            key = keyring.get_password(SERVICE, ACCOUNT) or ""
        except Exception:
            key = ""
        if not key:
            if mode == "optional":
                self.extra_running = False
                self.popup.detail.setPlainText("请在托盘菜单的“设置”中填写 GLM API Key。")
            else:
                self.popup.content.setPlainText("请在托盘菜单的“设置”中填写 GLM API Key。")
            return False
        self.pool.start(AnalysisJob(self.engine, self.token, self.selection, key, self.config, mode, self.signals))
        return True

    def toggle_detail(self, name):
        self.active_detail = None if self.active_detail == name else name
        self.popup.set_detail(self.active_detail)
        if not self.active_detail:
            return
        if self.extra_done:
            self.popup.detail.setHtml(detail_html(self.extra_text, name) or "没有返回此部分，请重新查询。")
        else:
            self.popup.detail.setPlainText("正在查询……")
            if not self.extra_running:
                self.extra_running = True
                self.submit("optional")

    @Slot(int, str, str)
    def on_update(self, token, mode, text):
        if token != self.token:
            return
        if mode == "core":
            self.popup.set_core(text)
            lemma = sections(text).get("原形", [])
            if lemma and WORD.fullmatch(lemma[0]) and lemma[0].lower() != self.selection.word.lower():
                prefix = self.selection.selected + " → " if self.selection.selected != self.selection.word else ""
                self.popup.title.setText(prefix + self.selection.word + " → " + lemma[0])
        else:
            self.extra_text = text
            if self.active_detail:
                part = detail_html(text, self.active_detail)
                if part:
                    self.popup.detail.setHtml(part)

    @Slot(int, str, str)
    def on_complete(self, token, mode, text):
        if token == self.token and mode == "optional":
            self.extra_text, self.extra_running, self.extra_done = text, False, True
            if self.active_detail:
                self.popup.detail.setHtml(detail_html(text, self.active_detail) or "没有返回此部分，请重新查询。")

    @Slot(int, str, str)
    def on_error(self, token, mode, message):
        if token != self.token:
            return
        if mode == "core":
            self.popup.content.setPlainText(message)
        else:
            self.extra_running = False
            if self.active_detail:
                self.popup.detail.setPlainText(message)

    def open_settings(self):
        if self.dialog is not None:
            return
        self.dialog = SettingsDialog(self)
        self.dialog.exec()
        self.dialog = None

    def manual_query(self):
        if self.dialog is not None:
            return
        self.dialog = True
        word, accepted = QInputDialog.getText(None, "手动查询", "输入英文词语、短语或句子：")
        self.dialog = None
        word = word.strip()
        if accepted and word:
            if not valid_selection(word):
                QMessageBox.information(None, "LLMs-powered Translator", "请输入不超过 500 个字符的英文词语、短语或句子。")
            else:
                self.show_word(Selection(word, word))

    def quit(self):
        self.token += 1
        self.selection_serial += 1
        for name in ("mouse_listener", "key_listener"):
            listener = getattr(self, name, None)
            if listener:
                listener.stop()
        self.tray.hide()
        self.app.quit()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--network-test":
        Path(sys.argv[2]).write_text(probe_reachability(), encoding="utf-8")
        return 0
    if len(sys.argv) == 5 and sys.argv[1] == "--selection-test" and sys.platform == "win32":
        try:
            result = get_selection(int(sys.argv[2]), int(sys.argv[3]))
            data = {"selected": result.selected, "word": result.word, "context": result.context} if result else None
            Path(sys.argv[4]).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return 0 if result else 1
        except Exception:
            return 1
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        # A packaged, offline startup check for the build; no hooks, keys, or requests.
        try:
            app = QApplication([sys.argv[0]])
            if sys.platform == "win32":
                import uiautomation
                assert uiautomation.PatternId.TextPattern
            assert keyring.get_keyring().priority > 0
            test_owner = type("Owner", (), {"toggle_detail": lambda self, name: None})()
            popup = Popup(test_owner)
            popup.set_detail("词根")
            assert popup.buttons["词根"].text() == "收起词根"
            Path(sys.argv[2]).write_text("PASS", encoding="utf-8")
            popup.close()
            return 0
        except Exception:
            Path(sys.argv[2]).write_text("FAIL", encoding="utf-8")
            return 1
    app = QApplication(sys.argv)
    app.setApplicationName("PaperWordStudy")
    app.setOrganizationName("PaperWordStudy")
    app.setWindowIcon(icon())
    app.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "LLMs-powered Translator", "系统托盘不可用，无法启动。")
        return 1
    controller = Controller(app)
    try:
        key_exists = bool(keyring.get_password(SERVICE, ACCOUNT))
    except Exception:
        key_exists = False
    if not key_exists:
        QTimer.singleShot(300, controller.open_settings)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
