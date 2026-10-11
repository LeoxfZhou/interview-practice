"""Build a whitelisted static site; never publish Python sources or SQLite files."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.database import TOPICS
from scripts.validate_bank import load_rows, validate


def build(output: Path):
    # Require an empty output to avoid accidentally uploading stale/private files.
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be an empty directory; use a fresh build directory.')
    rows = load_rows()
    validate(rows)
    payload = json.dumps({'topics':TOPICS,'questions':rows}, ensure_ascii=False).encode()
    bank_name = 'bank-' + hashlib.sha256(payload).hexdigest()[:16] + '.json'
    (output/'data').mkdir(parents=True, exist_ok=True)
    (output/'static').mkdir()
    (output/'data'/bank_name).write_bytes(payload)
    names = {}
    for name in ('styles.css','app.js','browser-store.js'):
        data = (ROOT/'static'/name).read_bytes()
        stem, extension = name.rsplit('.',1)
        target = f'{stem}-{hashlib.sha256(data).hexdigest()[:16]}.{extension}'
        (output/'static'/target).write_bytes(data)
        names[name] = './static/'+target
    config = 'window.InterviewStaticConfig = ' + json.dumps({'bankUrl':'./data/'+bank_name,'storageKey':'interview-practice:progress:v1'}) + ';\n'
    config_name = 'config-' + hashlib.sha256(config.encode()).hexdigest()[:16] + '.js'
    (output/'static'/config_name).write_text(config)
    html = (ROOT/'static/index.html').read_text()
    html = re.sub(r'/static/styles\.css\?v=[^" ]+', names['styles.css'], html)
    html = re.sub(r'<script src="/static/app\.js\?v=[^"]+" defer></script>',
        f'<script src="./static/{config_name}" defer></script>\n    <script src="{names["browser-store.js"]}" defer></script>\n    <script src="{names["app.js"]}" defer></script>', html)
    html = html.replace('方向与评价保存在本机；正确题在 Reset 前不再抽取。', '网页版：记录仅存此浏览器，不上传；清除网站数据会丢失记录，换设备不自动同步。正确题在 Reset 前不再抽取。')
    html = html.replace('内容范围与方向会自动保存', '内容范围与方向保存在此浏览器')
    html = html.replace('<head>', '<head>\n    <meta name="referrer" content="no-referrer" />\n    <meta http-equiv="Content-Security-Policy" content="default-src \'self\'; script-src \'self\'; style-src \'self\' \'unsafe-inline\'; img-src \'self\' data:; connect-src \'self\'; object-src \'none\'; base-uri \'self\'; form-action \'none\'" />')
    html = html.replace('</body>', '<noscript>此学习工具需要启用 JavaScript；学习记录仅保存在当前浏览器。</noscript>\n  </body>')
    (output/'index.html').write_text(html)
    (output/'.nojekyll').write_text('')
    print(f'Built {len(rows)} questions into {output}')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'dist')
    build(parser.parse_args().output)
