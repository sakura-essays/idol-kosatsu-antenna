"""Extract the visible article and advertised feeds from supported public HTML."""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from feed import date, plain

VOID = set('area base br col embed hr img input link meta param source track wbr'.split())
LINES = set('p div li section h1 h2 h3 h4 br blockquote tr'.split())
NO_CONTENT = set('style script noscript nav aside footer svg form iframe button template'.split())
BODY_CLASSES = set('entry-content entryContent entry-body article-body articleBody article__body post-content e-content entryBody blogbody'.split())


class Page(HTMLParser):
    def __init__(self, url, data):
        super().__init__()
        self.url = url
        self.stack = []
        self.parts = []
        self.links = []
        self.feeds = []
        self.tags = []
        self.metadata = {}
        self.structured = []
        self.script = None
        self.available = True
        self.feed(data.decode('utf-8', errors='replace') if isinstance(data, bytes) else data)

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        any_open = self.stack[-1][1] if self.stack else False
        parent_skip = self.stack[-1][2] if self.stack else False
        classes = set((attr.get('class') or '').split())
        identifier = attr.get('id') or ''
        is_body = (identifier in {'note-body', 'entryBody', 'entry-body', 'article-body', 'articleBody'}
                   or attr.get('itemprop') == 'articleBody' or attr.get('data-entry-body') is not None
                   or bool(classes & BODY_CLASSES))
        excluded = (tag in NO_CONTENT or bool(classes & {'advertisement', 'entry-footer', 'hatena-module', 'related-articles', 'blogcard', 'embed-card'})
                    or attr.get('aria-hidden') == 'true')
        if tag not in VOID:
            self.stack.append((tag, any_open or is_body, parent_skip or excluded))
        if tag in LINES and any_open and not parent_skip and not excluded:
            self.parts.append('\n')
        if tag == 'script' and attr.get('type') == 'application/ld+json':
            self.script = []
        if tag == 'a' and attr.get('href'):
            href = urljoin(self.url, attr['href'])
            self.links.append((href, any_open and not parent_skip))
            if '/tag/' in href and len(self.tags) < 30 and (any_open or 'hashtag' in classes or 'note.com' in self.url):
                from urllib.parse import unquote, urlsplit
                self.tags.append(unquote(urlsplit(href).path.split('/tag/', 1)[1]))
        if tag == 'link' and attr.get('href'):
            if attr.get('rel') == 'alternate' and attr.get('type') in ('application/rss+xml', 'application/atom+xml', 'application/rdf+xml'):
                self.feeds.append(urljoin(self.url, attr['href']))
            if attr.get('rel') == 'canonical':
                self.metadata['canonical'] = urljoin(self.url, attr['href'])
        if tag == 'meta' and attr.get('content'):
            prop = attr.get('property') or attr.get('name') or attr.get('itemprop')
            if prop:
                self.metadata[prop] = attr['content']
                if prop == 'article:tag':
                    self.tags.append(attr['content'])
        if tag == 'time' and attr.get('datetime') and 'date' not in self.metadata and not excluded:
            self.metadata['date'] = attr['datetime']

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            try:
                self.structured.append(json.loads(''.join(self.script)))
            except ValueError:
                pass
            self.script = None
        for i in range(len(self.stack) - 1, -1, -1):
            name, active, skipped = self.stack[i]
            if name == tag:
                if name in LINES and active and not skipped:
                    self.parts.append('\n')
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
        if self.stack and self.stack[-1][1] and not self.stack[-1][2]:
            self.parts.append(data)

    def article(self):
        metadata = self.metadata
        published = date(metadata.get('article:published_time') or metadata.get('datePublished') or metadata.get('date'))
        body = '\n'.join(' '.join(line.split()) for line in ''.join(self.parts).splitlines() if line.strip())
        def objects(data):
            if isinstance(data, dict):
                yield data
                yield from objects(data.get('@graph'))
            elif isinstance(data, list):
                for item in data:
                    yield from objects(item)
        structured_body = ''
        for row in (row for group in self.structured for row in objects(group)):
            if any(kind in str(row.get('@type', '')) for kind in ('Article', 'BlogPosting', 'CreativeWork')):
                published = published or date(row.get('datePublished'))
                self.available &= row.get('isAccessibleForFree') not in (False, 'false')
                if not body and not structured_body and isinstance(row.get('articleBody'), str):
                    structured_body = row['articleBody']
        if not body and self.available and structured_body:
            body = plain(structured_body)
        # Only the visible DOM is read for paid articles. Title/date never substitutes for body.
        return body, published, tuple(dict.fromkeys(t for t in self.tags if 0 < len(t) <= 60))
