"""Build a Zotero XPI from the repository sources without third-party tools."""
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent.parent
source = root / 'zotero'
manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
version = manifest['version']
destination = root / 'dist' / f'llms-powered-translator-zotero-{version}.xpi'
destination.parent.mkdir(exist_ok=True)
files = ['manifest.json', 'bootstrap.js', 'panel.xhtml', 'settings.xhtml', 'assets/icon.png']
with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
    for filename in files:
        archive.write(source / filename, filename)
with ZipFile(destination) as archive:
    if archive.testzip() is not None:
        raise RuntimeError('Invalid XPI archive')
print(destination)
