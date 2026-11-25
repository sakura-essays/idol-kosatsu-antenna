"""Shared robots checks and conservative request limits for public sources."""
import datetime as dt
import email.utils
import re
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit

from feed import UA, fetch


class Deferred(ValueError):
    """A bounded batch or a publisher cooldown deferred this request."""


class RobotsDenied(ValueError):
    """The publisher's robots file disallows the requested path."""


class Robots:
    def __init__(self, raw):
        groups = []
        agents, rules, delay = [], [], 0
        for line in raw.splitlines():
            key, separator, value = line.split('#', 1)[0].partition(':')
            if not separator:
                continue
            key, value = key.strip().lower(), value.strip()
            if key == 'user-agent':
                if rules or delay:
                    groups.append((agents, rules, delay))
                    agents, rules, delay = [], [], 0
                agents.append(value.lower())
            elif agents and key in ('allow', 'disallow') and value:
                pattern = re.escape(value.removesuffix('$')).replace(r'\*', '.*')
                if value.endswith('$'):
                    pattern += '$'
                rules.append((len(value.replace('*', '').removesuffix('$')), key == 'allow', re.compile('^' + pattern)))
            elif agents and key == 'crawl-delay':
                try:
                    delay = max(0, float(value))
                except ValueError:
                    pass
        groups.append((agents, rules, delay))
        agent = UA.split('/', 1)[0].lower()
        matching = [(max((len(a) if a != '*' else 0 for a in agents if a == '*' or a == agent), default=-1), rules, delay)
                    for agents, rules, delay in groups]
        priority = max((row[0] for row in matching), default=-1)
        self.rules = [rule for rank, rules, _ in matching if rank == priority >= 0 for rule in rules]
        self.delay = max((delay for rank, _, delay in matching if rank == priority >= 0), default=0)

    def allows(self, url):
        parts = urlsplit(url)
        path = (parts.path or '/') + ('?' + parts.query if parts.query else '')
        return max(((n, allow) for n, allow, pattern in self.rules if pattern.search(path)),
                   default=(0, True))[1]


def publisher(host):
    for suffix in ('note.com', 'hatenablog.com', 'hatenablog.jp', 'hateblo.jp', 'hatenadiary.jp',
                   'hatenadiary.com', 'ameba.jp', 'ameblo.jp', 'livedoor.blog', 'livedoor.jp', 'blog.jp', 'blog.fc2.com', 'wordpress.com'):
        if host == suffix or host.endswith('.' + suffix):
            return suffix
    return host


class PublicNetwork:
    def __init__(self, seconds=650, interval=0.65, fetcher=None):
        self.end = time.monotonic() + seconds
        self.interval = interval
        self.fetcher = fetcher or fetch
        self.robots = {}
        self.ready = {}
        self.cooldown = {}
        self.locks = {}
        self.host_locks = {}
        self.slots = {}
        self.lock = threading.Lock()

    def _limit(self, service, delay):
        with self.lock:
            lock = self.locks.setdefault(service, threading.Lock())
        with lock:
            now = time.monotonic()
            if self.cooldown.get(service, 0) > now:
                raise Deferred('publisher cooldown')
            ready = self.ready.get(service, now)
            if max(now, ready) >= self.end:
                raise Deferred('request budget exhausted')
            if ready > now:
                time.sleep(ready - now)
            self.ready[service] = time.monotonic() + max(self.interval, delay)

    def _robots(self, host):
        if host not in self.robots:
            self._limit(publisher(host.split(':', 1)[0]), 0)
            try:
                data, _ = self.fetcher('https://' + host + '/robots.txt')
                rules = Robots(data.decode('utf-8-sig', errors='replace'))
            except HTTPError as exc:
                if exc.code not in (404, 410):
                    raise
                rules = Robots('')
            self.robots[host] = rules
        return self.robots[host]

    def _check(self, url):
        parts = urlsplit(url)
        host = parts.netloc.lower()
        with self.lock:
            lock = self.host_locks.setdefault(host, threading.Lock())
        with lock:
            rules = self._robots(host)
        if not rules.allows(url):
            raise RobotsDenied('robots.txt: path disallowed')
        self._limit(publisher(parts.hostname), rules.delay)

    def get(self, url, headers=None):
        from feed import safe_url
        safe_url(url)
        service = publisher(urlsplit(url).hostname)
        with self.lock:
            slot = self.slots.setdefault(service, threading.BoundedSemaphore(3))
        with slot:
            try:
                self._check(url)
                def redirect(target):
                    # Same publisher redirects use its locked request budget. Ignore cross-
                    # publisher redirects; feed discovery must validate that source separately.
                    if publisher(urlsplit(target).hostname) != service:
                        raise ValueError('cross-publisher redirect')
                    self._check(target)
                return self.fetcher(url, headers, on_redirect=redirect)
            except HTTPError as exc:
                if exc.code in (429, 503):
                    raw = (exc.headers or {}).get('Retry-After', '')
                    try:
                        delay = int(raw)
                    except ValueError:
                        try:
                            when = email.utils.parsedate_to_datetime(raw)
                            delay = (when - dt.datetime.now(dt.timezone.utc)).total_seconds()
                        except (ValueError, TypeError):
                            delay = 60
                    self.cooldown[service] = time.monotonic() + max(60, delay)
                raise
