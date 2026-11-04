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
w.setPlainText('Synthetic context: This optimization is useful.')
w.resize(520, 180)
w.show()
w.activateWindow()
w.setFocus()
cursor = w.textCursor()
start = w.toPlainText().index('timiza')
cursor.setPosition(start)
cursor.setPosition(start + len('timiza'), QTextCursor.MoveMode.KeepAnchor)
w.setTextCursor(cursor)
QTimer.singleShot(1000, lambda: (print(json.dumps({'x':w.mapToGlobal(w.rect().center()).x(),'y':w.mapToGlobal(w.rect().center()).y()}), flush=True)))
QTimer.singleShot(15000, app.quit)
sys.exit(app.exec())
'''

if __name__ == '__main__':
    if sys.platform != 'win32':
        raise SystemExit('Windows only')
    child = subprocess.Popen([sys.executable, '-c', CHILD], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        line = child.stdout.readline()
        if not line:
            raise RuntimeError('Fixture failed: ' + child.stderr.read()[:500])
        point = json.loads(line)
        result = windows_selection(point['x'], point['y'])
        if not result:
            raise RuntimeError('Text selection not exposed by this Qt control')
        assert result.selected == 'timiza', result
        assert result.word == 'optimization', result
        assert '[[optimization]]' in result.context, result
        print('PASS: Windows UI Automation selected text, completion, and bounded context.')
        if len(sys.argv) > 1:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'selection-result.json'
                packaged = subprocess.run([sys.argv[1], '--selection-test', str(point['x']), str(point['y']), str(output)], timeout=15)
                assert packaged.returncode == 0 and output.exists(), 'Packaged selection test failed'
                saved = json.loads(output.read_text(encoding='utf-8'))
                assert saved['word'] == 'optimization' and '[[optimization]]' in saved['context'], saved
                print('PASS: Packaged Windows executable reads the synthetic selection.')
    finally:
        child.terminate()
        child.wait(timeout=5)
