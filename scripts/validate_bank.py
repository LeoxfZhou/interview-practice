"""Read-only checks for the distributable question bank (no database writes)."""
import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import database as db


def load_rows():
    paths = [ROOT/'data/questions.json', *sorted((ROOT/'data/foundations').glob('*.json'))]
    return [row for path in paths for row in json.loads(path.read_text(encoding='utf-8'))]


def validate(rows):
    ids, prompts = set(), set()
    topics = {t['slug'] for t in db.TOPICS}
    for row in rows:
        qid = row['id']
        assert qid not in ids, f'duplicate ID: {qid}'
        ids.add(qid)
        prompt = db._normalize_prompt(row['prompt'])
        assert prompt not in prompts, f'duplicate prompt: {qid}'
        prompts.add(prompt)
        for key in ('prompt','answer','stage','source_name','source_ref','difficulty','kind'):
            assert isinstance(row[key], str) and row[key].strip(), (qid, key)
        assert row['content_type'] in {'foundation','interview'}, qid
        assert row['primary_topic'] in row['topics'], qid
        assert set(row['topics']) <= topics, qid
        text = json.dumps(row, ensure_ascii=False)
        assert not re.search(r'/Users/|/home/|file://|[A-Z]:\\\\Users\\\\|\[!answer\]', text, re.I), qid
        prose = re.sub(r'```.*?```', '', row['answer'], flags=re.S)
        assert '[[' not in prose and '路线图对应' not in prose, qid
        for code in re.findall(r'```python\s*\n(.*?)```', row['answer'], re.S):
            ast.parse(code, filename=qid)
    return ids


def main():
    rows = load_rows()
    validate(rows)
    print(f'题库校验通过：{len(rows)} 条，未写入题库或数据库。')


if __name__ == '__main__':
    main()
