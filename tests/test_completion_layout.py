from html.parser import HTMLParser
from pathlib import Path
import unittest


class ButtonsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.parents = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'button' and attrs.get('id'):
            self.parents[attrs['id']] = tuple(self.stack)
        if tag not in {'meta','link','input','br','hr','img','path'}:
            self.stack.append((tag,tuple(attrs.items()),self.getpos()))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()


class CompletionLayoutTests(unittest.TestCase):
    def test_completion_home_shares_two_column_row_with_previous(self):
        root = Path(__file__).resolve().parents[1]
        html = (root/'static/index.html').read_text()
        parser = ButtonsParser()
        parser.feed(html)
        self.assertEqual(parser.parents['previousButton'],parser.parents['completionHomeButton'])
        self.assertIn('quiz-actions',dict(parser.parents['completionHomeButton'][-1][1])['class'])
        self.assertLess(html.index('id="previousButton"'),html.index('id="completionHomeButton"'))
        self.assertNotIn('#completionHomeButton { margin-top:',(root/'static/styles.css').read_text())
