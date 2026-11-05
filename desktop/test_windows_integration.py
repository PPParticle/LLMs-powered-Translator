"""Live UI Automation smoke test against a throwaway test window with synthetic text."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from selection import windows_selection

CHILD = r'''
import json, sys
from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QTextEdit
app = QApplication([])
w = QTextEdit()
w.setWindowTitle('PaperWordStudy test fixture')
w.setPlainText('Synthetic context: This optimization is useful.\nLLMs-powered Translator')
w.resize(520, 180)
w.show()
w.activateWindow()
w.setFocus()
cursor = w.textCursor()
selected = sys.argv[1]
start = w.toPlainText().index(selected)
cursor.setPosition(start)
cursor.setPosition(start + len(selected), QTextCursor.MoveMode.KeepAnchor)
w.setTextCursor(cursor)
QTimer.singleShot(1000, lambda: (print(json.dumps({'x':w.mapToGlobal(w.rect().center()).x(),'y':w.mapToGlobal(w.rect().center()).y()}), flush=True)))
QTimer.singleShot(15000, app.quit)
sys.exit(app.exec())
'''

if __name__ == '__main__':
    if sys.platform != 'win32':
        raise SystemExit('Windows only')
    for selected, expected in [('timiza', 'optimization'), ('LLMs-powered Translator', 'LLMs-powered Translator'), ('powered', 'powered')]:
      child = subprocess.Popen([sys.executable, '-c', CHILD, selected], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
      try:
        line = child.stdout.readline()
        if not line:
            raise RuntimeError('Fixture failed: ' + child.stderr.read()[:500])
        point = json.loads(line)
        result = windows_selection(point['x'], point['y'])
        if not result:
            raise RuntimeError('Text selection not exposed by this Qt control')
        assert result.selected == selected, result
        assert result.word == expected, result
        assert '[[' + expected + ']]' in result.context, result
        print('PASS: Windows UI Automation selection:', selected)
        if len(sys.argv) > 1:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'selection-result.json'
                packaged = subprocess.run([sys.argv[1], '--selection-test', str(point['x']), str(point['y']), str(output)], timeout=15)
                assert packaged.returncode == 0 and output.exists(), 'Packaged selection test failed'
                saved = json.loads(output.read_text(encoding='utf-8'))
                assert saved['word'] == expected and '[[' + expected + ']]' in saved['context'], saved
                print('PASS: Packaged executable selection:', selected)
      finally:
        child.terminate()
        child.wait(timeout=5)
