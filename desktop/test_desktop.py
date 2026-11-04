import json
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import requests
from urllib3 import exceptions as urllib3_errors

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

import selection
import word_engine
from app import Controller, Popup, SettingsDialog, load_settings, save_settings


class FakeResponse:
    status_code = 200
    encoding = None
    headers = {"Content-Type":"text/event-stream"}
    def __init__(self, content):
        self.content = content
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def iter_lines(self, **kwargs):
        midpoint = len(self.content) // 2
        for chunk in (self.content[:midpoint], self.content[midpoint:]):
            yield "data: " + json.dumps({"choices":[{"delta":{"content":chunk}}]}, ensure_ascii=False)
        yield "data: [DONE]"


class FakeSession:
    def __init__(self, post):
        self.fake_post = post
        self.trust_env = True
        self.verify = False
        self.proxies = {"https":"http://invalid.example"}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def post(self, url, **kwargs):
        assert self.trust_env is False, 'network must not inherit proxy or CA environment settings'
        assert self.verify is True, 'TLS verification must remain enabled'
        assert self.proxies == {}, 'network must use a direct connection'
        return self.fake_post(url, **kwargs)


class DesktopTests(unittest.TestCase):
    def test_partial_and_context(self):
        result = selection.from_neighbors("timiza", "The op", "tion is useful")
        self.assertEqual(result.word, "optimization")
        self.assertIn("[[optimization]]", result.context)
        self.assertIsNone(selection.from_neighbors("two words", "", ""))
        self.assertEqual(selection.from_value("MSI", "MSI and MSI").context, "")
        self.assertIn("[[MSI]]", selection.from_value("MSI", "Message-signaled interrupt (MSI)").context)

    def test_core_and_detail_format(self):
        text = ("释义：v. 中断\n词形：三单=interrupts；过去=interrupted；过分=interrupted；现在分词=interrupting；n. interrupts\n"
                "同词族：interruption n. 中断\ninterruptible adj. 可中断")
        result = word_engine.core_html(text)
        self.assertIn("三单/过去/过分/现在分词", result)
        self.assertIn("interrupts / interrupted / interrupted / interrupting", result)
        self.assertNotIn("n. interrupts", result)
        self.assertNotIn("<script>", word_engine.core_html("释义：<script>"))
        details = "搭配：interrupt handler 中断处理器\n词根：词源不确定\n近义词：stop v. 停止；suspend v. 暂停"
        self.assertEqual(word_engine.detail_html(details, "近义词"), "stop v. 停止<br>suspend v. 暂停")

    def test_streaming_context_and_cache(self):
        content = "释义：n. 消息信号中断\n同词族：interrupt v. 中断"
        captured = []
        def post(url, **kwargs):
            captured.append((url, kwargs))
            return FakeResponse(content)
        client = word_engine.GLMClient()
        seen = []
        with patch.object(word_engine.requests, "Session", side_effect=lambda:FakeSession(post)):
            client.analyze("MSI", "Message-signaled interrupt ([[MSI]])", "test-secret", "glm-5.3-flash", "core", seen.append)
            client.analyze("MSI", "Message-signaled interrupt ([[MSI]])", "test-secret", "glm-5.3-flash", "core", seen.append)
            self.assertEqual(len(captured), 1)
            client.analyze("MSI", "computer maker [[MSI]]", "test-secret", "glm-5.3-flash", "core", seen.append)
            self.assertEqual(len(captured), 2)
        self.assertEqual(seen[-1], content)
        body = captured[0][1]["json"]
        self.assertIn("Message-signaled interrupt", body["messages"][1]["content"])
        self.assertEqual(captured[0][0], 'https://open.bigmodel.cn/api/coding/paas/v4/chat/completions')
        self.assertEqual(body["model"], 'glm-5.3-flash')
        self.assertEqual(body["reasoning_effort"], 'low')
        self.assertNotIn('thinking', body)
        self.assertNotIn("test-secret", json.dumps(body))

    def test_connection_diagnostics_and_redaction(self):
        error = requests.exceptions.ConnectionError(urllib3_errors.ReadTimeoutError(None, '/private-secret', 'timed out'))
        message = word_engine.network_error_message(error)
        self.assertIn('响应超时', message)
        self.assertNotIn('private-secret', message)
        self.assertIn('代理', word_engine.network_error_message(requests.exceptions.ProxyError('http://user:private-secret@host')))
        self.assertIn('证书', word_engine.network_error_message(requests.exceptions.SSLError('private-secret')))
        self.assertIn('超时', word_engine.network_error_message(requests.exceptions.ConnectTimeout('private-secret')))
        class HttpFailure:
            status_code = 403
            def json(self): return {'error':{'code':'1002','message':'private-secret'}}
        with self.assertRaisesRegex(ValueError, '1002') as caught:
            word_engine.raise_for_glm_status(HttpFailure())
        self.assertNotIn('private-secret', str(caught.exception))
        calls = []
        def post(url, **kw):
            calls.append((url, kw))
            return FakeResponse('ok')
        with patch.object(word_engine.requests, 'Session', side_effect=lambda:FakeSession(post)):
            result = word_engine.test_connection('fake-key','glm-5.3-flash')
        self.assertIn('连接成功', result)
        self.assertEqual(calls[0][0], word_engine.CODING_ENDPOINT)
        self.assertEqual(calls[0][1]['json']['max_tokens'], 32)
        self.assertNotIn('fake-key', json.dumps(calls[0][1]['json']))
        calls.clear()
        with patch.object(word_engine.requests, 'Session', side_effect=lambda:FakeSession(post)):
            self.assertEqual(word_engine.probe_reachability(), 'HTTP 200')
        self.assertNotIn('headers', calls[0][1], 'the transport test must not use credentials')

    def test_connection_diagnostic_button(self):
        app = QApplication.instance() or QApplication([])
        owner = types.SimpleNamespace(config={'model':'glm-5.3-flash','mode':'auto'}, engine=types.SimpleNamespace(clear=lambda: None))
        dialog = SettingsDialog(owner)
        with patch('app.keyring.get_password', return_value='fake-key'), patch('app.test_connection', return_value='测试成功'):
            dialog.test_connection()
            deadline = time.monotonic() + 3
            while dialog.diagnostic_status.text() != '测试成功' and time.monotonic() < deadline:
                app.processEvents(); time.sleep(.01)
            self.assertEqual(dialog.diagnostic_status.text(), '测试成功')
            self.assertTrue(dialog.test_button.isEnabled())
        dialog.close()

    def test_gui_components(self):
        app = QApplication.instance() or QApplication([])
        owner = types.SimpleNamespace(config={"model":"glm-5.3-flash", "mode":"auto"}, toggle_detail=lambda name: None)
        popup = Popup(owner)
        popup.set_detail("词根")
        self.assertFalse(popup.detail.isHidden())
        self.assertEqual(popup.buttons["词根"].text(), "收起词根")
        popup.set_detail("近义词")
        self.assertEqual(popup.buttons["词根"].text(), "查看词根")
        settings = SettingsDialog(owner)
        self.assertEqual(settings.mode.count(), 2)
        self.assertFalse(hasattr(settings, 'endpoint'))
        self.assertEqual(settings.password.text(), "")
        popup.close(); settings.close()
        self.assertIsNotNone(app)

    def test_controller_uses_one_optional_request(self):
        app = QApplication.instance() or QApplication([])
        class Tray:
            def __init__(self, *args): pass
            def setToolTip(self, *args): pass
            def setContextMenu(self, *args): pass
            def show(self): pass
            def hide(self): pass
            def showMessage(self, *args): pass
            @property
            def activated(self): return types.SimpleNamespace(connect=lambda fn:None)
        class Engine:
            def __init__(self): self.calls = []
            def clear(self): pass
            def analyze(self, word, context, key, model, mode, callback):
                self.calls.append(mode)
                text = ('释义：v. 中断\n词形：三单=interrupts；过去=interrupted\n同词族：interruption n. 中断'
                        if mode == 'core' else '搭配：interrupt handler 中断处理器\n词根：词源不确定\n近义词：suspend v. 暂停')
                callback(text)
                return text
        with patch('app.QSystemTrayIcon', Tray), patch.object(Controller, '_start_hooks'), patch('app.keyring.get_password', return_value='test-key'), patch('app.save_settings'):
            controller = Controller(app)
            controller.engine = Engine()
            controller.show_word(selection.Selection('interrupt', 'interrupt'))
            deadline = time.monotonic() + 3
            while '中断' not in controller.popup.content.toPlainText() and time.monotonic() < deadline:
                app.processEvents(); time.sleep(.01)
            self.assertIn('中断', controller.popup.content.toPlainText())
            controller.toggle_detail('搭配')
            deadline = time.monotonic() + 3
            while not controller.extra_done and time.monotonic() < deadline:
                app.processEvents(); time.sleep(.01)
            self.assertTrue(controller.extra_done)
            controller.toggle_detail('词根')
            self.assertIn('词源不确定', controller.popup.detail.toPlainText())
            controller.toggle_detail('近义词')
            self.assertIn('suspend', controller.popup.detail.toPlainText())
            self.assertEqual(controller.engine.calls, ['core', 'optional'])
            previous_token = controller.token
            previous_serial = controller.selection_serial
            with patch('app.QApplication.topLevelAt', return_value=controller.popup):
                controller.on_mouse_press()
                self.assertTrue(controller.popup.isVisible(), 'clicking inside must keep popup open')
            with patch('app.QApplication.topLevelAt', return_value=None):
                controller.on_mouse_press()
                self.assertFalse(controller.popup.isVisible(), 'clicking outside must close popup')
            self.assertGreater(controller.token, previous_token)
            self.assertGreater(controller.selection_serial, previous_serial)
            controller.on_update(previous_token, 'core', '释义：v. 过期数据')
            self.assertNotIn('过期数据', controller.popup.content.toPlainText())
            controller.popup.show()
            controller.hooks.escape.emit()
            self.assertFalse(controller.popup.isVisible(), 'Escape must close the popup')
            controller.popup.close(); controller.tray.hide()

    def test_old_settings_migrate_without_key_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text(json.dumps({'model':'glm-4.7-flash','endpoint':'standard','mode':'hotkey'}),encoding='utf-8')
            with patch('app.settings_path', return_value=path):
                settings = load_settings()
                self.assertEqual(settings, {'model':'glm-5.3-flash','mode':'hotkey'})
                save_settings(settings)
                self.assertNotIn('endpoint', json.loads(path.read_text(encoding='utf-8')))
                path.write_text(json.dumps({'model':'glm-custom','endpoint':'standard','mode':'auto'}),encoding='utf-8')
                self.assertEqual(load_settings()['model'], 'glm-custom')

    def test_blank_key_preserves_existing_credential(self):
        app = QApplication.instance() or QApplication([])
        owner = types.SimpleNamespace(config={'model':'glm-5.3-flash','mode':'auto'}, engine=types.SimpleNamespace(clear=lambda: None))
        dialog = SettingsDialog(owner)
        with patch('app.keyring.set_password') as save_key, patch('app.save_settings'):
            dialog.save()
            save_key.assert_not_called()
            self.assertEqual(owner.config['model'], 'glm-5.3-flash')
        dialog.close()

    def test_dark_and_light_palette(self):
        app = QApplication.instance() or QApplication([])
        owner = types.SimpleNamespace(toggle_detail=lambda name: None)
        popup = Popup(owner)
        popup.set_core('释义：v. 中断\n词形：过去=interrupted')
        popup.refresh_theme(Qt.ColorScheme.Dark)
        app.processEvents()
        self.assertIn('#20242c', popup.styleSheet())
        self.assertIn('#f0f2f5', popup.content.styleSheet())
        self.assertIn('#bbc3ce', popup.content.toHtml().lower())
        popup.refresh_theme(Qt.ColorScheme.Light)
        app.processEvents()
        self.assertIn('#ffffff', popup.styleSheet())
        self.assertIn('#18243a', popup.content.styleSheet())
        popup.close()


if __name__ == "__main__":
    unittest.main()
