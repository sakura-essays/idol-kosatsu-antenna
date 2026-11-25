"""Discover authors from public indexes, curated seeds and links in public entries."""
import collections
import concurrent.futures
import datetime as dt
import hashlib
import re
from urllib.error import HTTPError
from urllib.parse import quote, urljoin, urlsplit

from article_page import Page
from autopublication import timestamp
from catalog import norm, owned, valid_date
from feed import canonical, parse, plain, read, write
from network import Deferred, RobotsDenied
from retry import TRANSIENT_CODES, check_page

NOTE = re.compile(r'/([a-zA-Z0-9_-]+)/n/n[a-zA-Z0-9]+/?$')
AMEBA = re.compile(r'/([a-zA-Z0-9_-]+)/(?:entry-\d+\.html|)$')
BLOGS = {
    'hatenablog.com': 'hatena', 'hatenablog.jp': 'hatena', 'hateblo.jp': 'hatena',
    'hatenadiary.com': 'hatena', 'hatenadiary.jp': 'hatena', 'hatena.ne.jp': 'hatena',
    'livedoor.blog': 'livedoor', 'livedoor.jp': 'livedoor', 'blog.jp': 'livedoor',
    'blog.fc2.com': 'fc2', 'wordpress.com': 'wordpress', 'blogspot.com': 'blogger',
}
BLOG_PATH = re.compile(r'/(?:entry|archives|article|posts?|blog|diary)/|/\d{4}/(?:\d{1,2}/)?|[?&]p=\d+')


def identity(url):
    p = urlsplit(url)
    host, path = p.hostname, p.path
    if not host or p.scheme not in ('https', 'http') or p.username or p.password or p.port not in (None, 443):
        return None
    if host in ('note.com', 'www.note.com'):
        m = NOTE.fullmatch(path) or re.fullmatch(r'/([a-zA-Z0-9_-]+)/?', path)
        if m and m[1] not in {'info', 'tag', 'hashtag', 'search', 'topics', 'creator', 'help'}:
            home = 'https://note.com/' + m[1]
            return home, home + '/rss', 'note'
        return None
    if host == 'ameblo.jp':
        m = AMEBA.fullmatch(path) or re.fullmatch(r'/([a-zA-Z0-9_-]+)', path)
        if m:
            return 'https://ameblo.jp/' + m[1], 'https://rssblog.ameba.jp/' + m[1] + '/rss20.xml', 'ameba'
    if host == 'blog.livedoor.jp' and re.fullmatch(r'/[^/]+(?:/archives/[^/]+|/?)', path):
        return 'https://' + host + '/' + path.split('/')[1], None, 'livedoor'
    if host == 'plaza.rakuten.co.jp' and re.fullmatch(r'/[^/]+(?:/diary/\d+/?|/?)', path):
        return 'https://' + host + '/' + path.split('/')[1], None, 'rakuten'
    for domain, platform in BLOGS.items():
        if host.endswith('.' + domain) and host.split('.')[0] not in {'www', 'blog', 'news', 'help', 'staff'}:
            home = 'https://' + host
            return home, home + '/feed' if platform == 'hatena' else None, platform
    if re.search(r'\.(?:jp|com|net|org|blog|me|jp\.net)$', host) and BLOG_PATH.search(url):
        prefix = path[:path.index('/blog/') + 5] if '/blog/' in path else ''
        if host not in {'github.com', 'www.youtube.com', 'www.instagram.com', 'www.tiktok.com',
                        'www.oricon.co.jp', 'natalie.mu', 'news.yahoo.co.jp', 'x.com', 'www.amazon.co.jp'}:
            return 'https://' + host + prefix, None, 'blog'
    return None


def profile_key(url):
    parts = urlsplit(url)
    return (parts.hostname or '').removeprefix('www.') + parts.path.rstrip('/')


def excluded_source(source, moderation):
    entries = set(moderation.get('blocked_authors', []))
    urls = {profile_key(u) for u in entries | set(moderation.get('blocked_urls', [])) if '://' in u}
    return source['id'] in entries or profile_key(source['url']) in urls or source.get('publication_mode') == 'stopped'


def get_candidate(url, *, title='', family='', channel='', index='', explicit=False):
    try:
        source = identity(url)
        if explicit and not source:
            p = urlsplit(url)
            if p.scheme == 'https' and p.path in ('', '/') and p.hostname:
                source = (url.rstrip('/'), None, 'blog')
        if not source:
            return None
        target = canonical(url)
        home, feed, platform = source
        h = urlsplit(home)
        source_id = h.path.split('/')[1] if platform == 'note' else 'auto-' + hashlib.sha256(profile_key(home).encode()).hexdigest()[:16]
        return {'id': source_id, 'url': home, 'feed': feed, 'platform': platform,
                'article': target if target.rstrip('/') != home else '',
                'title': plain(title)[:240], 'family': family, 'channel': channel, 'index': index}
    except (ValueError, TypeError, AttributeError):
        return None


def tag_candidates(url, data, family, channel, term):
    from html.parser import HTMLParser
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows = []
        def handle_starttag(self, tag, attrs):
            attr = dict(attrs)
            if tag == 'a' and attr.get('href'):
                target = urljoin(url, attr['href'])
                host = urlsplit(target).hostname
                if (host == 'note.com' and NOTE.fullmatch(urlsplit(target).path) or
                        host == 'ameblo.jp' and re.search(r'/entry-\d+\.html$', urlsplit(target).path)):
                    self.rows.append((target, attr.get('title') or attr.get('aria-label') or ''))
    links = Links()
    links.feed(data.decode('utf-8', errors='replace'))
    return [a for target,title in dict.fromkeys(links.rows)
            if (a := get_candidate(target, title=title, family=family, channel=channel, index=term))]


def add_candidate(candidates, row, now):
    key = profile_key(row['url'])
    old = candidates.get(key)
    if not old:
        candidates[key] = {**row, 'first': now.isoformat(), 'status': 'unverified'}
        return
    if row.get('article') and row['article'] != old.get('article'):
        if not old.get('article') or (row.get('title') and not old.get('title')):
            old.update(article=row['article'],title=row['title'])
        recent = old.setdefault('additional_articles', [])
        if row['article'] not in recent and len(recent) < 4:
            recent.append(row['article'])
    if row.get('family') and not old.get('family'):
        old['family'] = row['family']


def feed_for(candidate, network):
    supplied = candidate.get('feed')
    if supplied:
        return supplied
    url = candidate['url']
    data, _ = network.get(url)
    page = Page(url, data)
    home = urlsplit(url)
    for feed in page.feeds:
        feed = re.sub(r'^http:', 'https:', feed)
        host = urlsplit(feed).hostname
        if host == home.hostname or (host and host.removeprefix('www.') == home.hostname.removeprefix('www.')):
            return feed
    raise ValueError('public feed not advertised')


def primary_family(group_ids, classifier, fallback=''):
    by_series = {
        'ikonoijoy': {'equal-love','not-equal-me','nearly-joy'},
        'kawaii-lab': {'fruits-zipper','candy-tune','sweet-steady','cutie-street','more-star'},
        'stardust': {'momoclo','ebichu','tokisen','batten','tohoku','ukka','team-shachi'},
        'tobe': {'number-i','imp'},
        'bmsg': {'be-first','mazzel','hana'},
        'auditions': {'me-i','issue','jo1','ini','nexz','niziu','andteam','dxteen'},
        'live-local': {'ilife','yosugala','appare','festive','linq','fishbowl','negicco','ryutist','bish',
                       'wack','ringwanderung','task-have-fun','title-mitei','cu-mete','tiptoe','kasumisou-stella'},
    }
    series = {group: key for key,groups in by_series.items() for group in groups}
    weights = collections.Counter(series.get(g, classifier.groups.get(g)) for g in group_ids)
    return next((key for key,count in weights.most_common() if key),fallback or 'culture')


def shared_group_blog(name, classifier):
    label = re.fullmatch(r'(.+?)[ 　]*(?:オフィシャルブログ|公式ブログ)(?:[ 　]+Powered by Ameba)?',name,re.I)
    if not label:
        return False
    group_name = norm(label[1])
    return group_name in classifier.aliases[1] or group_name in {'s★スパイシー'}

def automatic_class(n, total):
    return 'A' if n >= 3 and n * 2 >= total else 'B' if n >= 2 else 'C' if n else 'D'


def inspect(candidate, classifier, network, fingerprint, now, blocked_articles, *, inspect_page=False):
    feed_url = feed_for(candidate, network)
    data, headers = network.get(feed_url)
    source = {k: candidate[k] for k in ('id', 'url', 'platform')}
    source['feed'] = feed_url
    items = []
    for item in parse(data):
        try:
            url = canonical(urljoin(source['url'] + '/', item['url']))
        except (ValueError, TypeError):
            continue
        if item['title'] and owned(url, source) and url not in blocked_articles:
            item['url'] = url
            items.append(item)
    if not items:
        raise ValueError('no identifiable owned public entries in feed')

    # Feeds with multiple credited writers do not identify a single writer.
    bylines = collections.Counter(a['creator'] for a in items if a.get('creator'))
    if len(bylines) > 1 and bylines.most_common(1)[0][1] < sum(bylines.values()) * .8:
        raise ValueError('multi-author feed')
    from xml.etree import ElementTree
    tree = ElementTree.fromstring(data)
    channel = tree.find('channel')
    parent = channel if channel is not None else tree
    title = next((plain(e.text) for e in parent if e.tag.split('}')[-1] == 'title' and e.text), '')
    name = bylines.most_common(1)[0][0] if bylines else title
    if not name:
        raise ValueError('missing public writer or blog name')
    if shared_group_blog(name,classifier):
        raise ValueError('multi-author group blog')

    qualifying = []
    for item in items:
        item['auto_evidence'] = classifier.assess(item['title'], item['text'], item['tags'], truncated=item['truncated'])
        item['auto_evidence']['taxonomy_hash'] = fingerprint
        if item['auto_evidence']['result'] == 'published' and valid_date(item['published_at']):
            qualifying.append(item)
    if not qualifying and inspect_page:
        article_url = candidate.get('article')
        examples = [i for i in items if i['url'] == article_url]
        if not examples and article_url and article_url not in blocked_articles and owned(article_url,source):
            # A rare contributor can have a relevant post outside the feed's current window.
            try:
                data, _ = network.get(article_url)
                page = Page(article_url,data)
                body, published, tags = page.article()
                actual_url = page.metadata.get('canonical') or page.metadata.get('og:url')
                actual_title = page.metadata.get('og:title')
                if actual_url and canonical(actual_url)==article_url and actual_title and body and valid_date(published):
                    evidence = classifier.assess(actual_title,body,tags,origin='page',truncated=not page.available)
                    if evidence['result']=='published':
                        evidence['taxonomy_hash'] = fingerprint
                        entry={'url':article_url,'title':actual_title,'published_at':published,
                               'text':'','tags':tags,'truncated':True,'page_evidence':evidence}
                        items.append(entry)
                        qualifying.append(entry)
            except Deferred:
                raise
            except HTTPError as exc:
                if exc.code in TRANSIENT_CODES:
                    raise
            except ValueError:
                pass
        if not qualifying:
            examples = examples or [i for i in items if classifier.subjects(i['title'])][:1]
            for item in examples[:1]:
                try:
                    page, published, _ = check_page(item,classifier,network,fingerprint)
                except Deferred:
                    raise
                except HTTPError as exc:
                    if exc.code in TRANSIENT_CODES:
                        raise
                    break
                except ValueError:
                    break
                if page['result']=='published' and valid_date(item['published_at'] or published):
                    item['page_evidence'] = page
                    item['published_at'] = item['published_at'] or published
                    qualifying.append(item)
    category = automatic_class(len(qualifying), len(items))
    if category == 'D':
        return None, [], headers, 'no_qualifying_entry'
    groups = sorted({g for item in qualifying for g in (item.get('page_evidence') or item['auto_evidence'])['classification']['group_ids']})
    family = primary_family((g for item in qualifying
                             for g in (item.get('page_evidence') or item['auto_evidence'])['classification']['group_ids']),
                            classifier,candidate.get('family',''))
    source.update(name=name[:180], enabled=True, publication_mode='standard', auto_class=category,
                  registered_at=now.isoformat(), discovered_via=candidate.get('channel', ''),
                  discovery_family=candidate.get('family', ''), representative_url=qualifying[0]['url'],
                  groups=groups,primary_family=family)
    return source, items, headers, ''


def exploration_order(indexes, state, sources, now):
    counts = collections.Counter(s.get('primary_family') or s.get('discovery_family') for s in sources)
    last = state.get('indexes', {})
    # Recompute weekly priorities automatically from registered coverage. Older index visits
    # win within a tier, so the same popular pages cannot crowd out less familiar subjects.
    week = now.strftime('%G-%V')
    if state.get('week') != week:
        state.update(week=week, coverage=dict(counts))
    coverage = state['coverage']
    buckets = collections.defaultdict(list)
    for row in indexes:
        buckets[(row['family'], row['channel'])].append(row)
    for rows in buckets.values():
        rows.sort(key=lambda row: (last.get(row['url'], {}).get('visits', 0),
                                   last.get(row['url'], {}).get('day', ''), row['term']))
    ordered = []
    while buckets:
        # Prefer the least explored index, then low-coverage series, then a distinct
        # medium or series within this round.
        keys = sorted(buckets, key=lambda key: (
            last.get(buckets[key][0]['url'], {}).get('visits', 0),
            coverage.get(key[0], 0), last.get(buckets[key][0]['url'], {}).get('day', ''),
            key[1] == 'note-tag', key))
        for key in keys:
            ordered.append(buckets[key].pop(0))
            if not buckets[key]:
                del buckets[key]
    return ordered



def candidate_order(candidates, now):
    groups = collections.defaultdict(list)
    for row in candidates:
        if row['status'] in {'registered', 'duplicate', 'stopped'}:
            continue
        if (timestamp(row.get('next')) or now) > now:
            continue
        groups[(row['platform'],row.get('family',''))].append(row)
    for rows in groups.values():
        hints = re.compile(r'考察|批評|感想|雑感|レビュー|レポ|参戦|観た|見た|行った|について|思う|好き|推し')
        rows.sort(key=lambda row: (row.get('attempts',0),
                                   row.get('channel') not in {'existing-candidate','search','article-link'},
                                   not bool(hints.search(row['title'])),not bool(row['title']),row['first']))
    return [rows[i] for i in range(max(map(len,groups.values()),default=0))
            for rows in groups.values() if i < len(rows)]


def remember_tags(state, tags, family):
    indexes = state.setdefault('dynamic_indexes',{})
    for term in tags[:8]:
        if not re.fullmatch(r'[\w .&!＋+♡=≠≒-]{3,45}',term) or term in {'アイドル','音楽','感想','日記','ライブ','コンサート','オタク'}:
            continue
        url='https://note.com/tag/'+quote(term,safe='')+'?mode=new'
        if len(indexes)>=150 and url not in indexes:
            del indexes[next(iter(indexes))]
        indexes[url]={'url':url,'family':family or 'culture','channel':'note-related-tag','term':term}

def note_page_links(page):
    for target, in_body in dict.fromkeys(page.links):
        host = urlsplit(target).hostname
        if in_body or (host == 'note.com' and NOTE.fullmatch(urlsplit(target).path)):
            yield target


def run_discovery(root, state, candidates, sources, classifier, network, fingerprint, now, moderation,
                  *, index_limit=18, candidate_limit=24, index_loader=None, force=False):
    if state.get('day') == now.date().isoformat() and not force:
        return [], {'found':0, 'inspected':0, 'registered':0, 'index_requests':0}
    config = read(root/'config/discovery.json', {})
    old_count = len(candidates)
    for seed in config.get('seeds', []):
        row = get_candidate(seed['url'],title=seed.get('title',''),family=seed.get('family',''),channel='search',explicit=True)
        if row:
            add_candidate(candidates,row,now)
    for seed in read(root/'config/candidates.json', []):
        row = get_candidate(seed['url'],title=seed.get('title',''),channel='existing-candidate')
        if row:
            add_candidate(candidates,row,now)
    history = state.setdefault('indexes', {})
    indexes = list({row['url']:row for row in [*state.get('dynamic_indexes',{}).values(),*config.get('indexes',[])]}.values())
    indexes = exploration_order(indexes, state, sources, now)
    indexes = [r for r in indexes if force or history.get(r['url'],{}).get('day') != now.date().isoformat()]
    if index_loader is None:
        indexes = indexes[:index_limit]
    blocked_articles = {canonical(u) for u in moderation.get('blocked_urls', [])}
    blocked_articles.update(canonical(u) for u,a in moderation.get('articles',{}).items() if a.get('status')=='excluded')
    def index(row):
        try:
            data = index_loader(row['url']) if index_loader else network.get(row['url'])[0]
            return row, tag_candidates(row['url'], data, row['family'], row['channel'], row['term']), ''
        except Deferred:
            return row, [], 'deferred'
        except (ValueError, OSError) as exc:
            return row, [], type(exc).__name__
    visited = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for row, results, error in pool.map(index, indexes):
            if error == 'deferred':
                continue
            visited += 1
            start = history.get(row['url'],{}).get('visits',0)
            history[row['url']] = {'day':now.date().isoformat(),'visits':start+1,'links':len(results),'error':error}
            for found in results:
                if found.get('article') not in blocked_articles:
                    add_candidate(candidates,found,now)
    keys = {profile_key(s['url']) for s in sources}
    existing_ids = {s['id'] for s in sources}
    for key, candidate in candidates.items():
        if excluded_source(candidate, moderation):
            candidate['status'] = 'stopped'
        elif key in keys or candidate['id'] in existing_ids:
            if candidate['status'] != 'registered':
                candidate['status'] = 'duplicate'
    selected = candidate_order(candidates.values(),now)[:candidate_limit]
    def validate(candidate):
        try:
            return inspect(candidate,classifier,network,fingerprint,now,blocked_articles,
                           inspect_page=(bool(candidate.get('title')) or candidate.get('channel') == 'existing-candidate'))
        except Deferred:
            return None,[],{},'deferred'
        except RobotsDenied:
            return None,[],{},'robots_disallowed'
        except HTTPError as exc:
            return None,[],{},'http_'+str(exc.code)
        except (ValueError, OSError) as exc:
            return None,[],{},str(exc)[:100]
    active_feeds = {canonical(s['feed']).rstrip('/') for s in sources if s.get('feed')}
    accepted = []
    inspected = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for candidate,(source,items,headers,error) in zip(selected,pool.map(validate,selected)):
            if error == 'deferred':
                continue
            inspected += 1
            candidate['attempts'] = candidate.get('attempts',0)+1
            candidate['last'] = now.isoformat()
            if source:
                candidate['name'] = source['name']
                if canonical(source['feed']).rstrip('/') in active_feeds:
                    candidate['status'] = 'duplicate'
                else:
                    candidate['status'] = 'registered'
                    active_feeds.add(canonical(source['feed']).rstrip('/'))
                    accepted.append((source,items,headers))
            else:
                permanent = error in {'no_qualifying_entry','multi-author feed','multi-author group blog','robots_disallowed','http_404','http_410'}
                candidate.update(status='D',reason=error,next=(now+dt.timedelta(days=30 if permanent else min(21,2**min(5,candidate['attempts'])))).isoformat())
    state['day'] = now.date().isoformat()
    return accepted, {'found':len(candidates)-old_count,'inspected':inspected,'registered':len(accepted),'index_requests':visited}
