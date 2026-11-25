import datetime as dt
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from article_page import Page
from autopublication import Classifier, VERSION
from catalog import apply
from discover import get_candidate, inspect, tag_candidates
from feed import ROOT, read
from network import Robots
from publication import taxonomy_hash
from retry import release_archives, due, outcome


class AutonomousTests(unittest.TestCase):
    def setUp(self):
        self.tax = read(ROOT/'config/taxonomy.json',{})
        self.classifier = Classifier(self.tax)
        self.fingerprint = taxonomy_hash(self.tax)
        self.now = dt.datetime(2026,11,25,tzinfo=dt.timezone.utc)
        self.url = 'https://note.com/writer/n/n123'
        self.source = {'id':'writer','url':'https://note.com/writer','feed':'https://note.com/writer/rss',
                       'platform':'note','enabled':True,'publication_mode':'standard',
                       'auto_publish_after':'2026-11-24T00:00:00Z'}
        self.settings = {'enabled':True,'autonomous':True,'backlog_urls':[self.url]}
        self.title = 'AKB48のライブ感想'

    def article(self, published='2026-11-01T00:00:00Z'):
        ev = self.classifier.assess(self.title,'AKB48のライブに行った。声の重なりがすごく好き。')
        ev['taxonomy_hash'] = self.fingerprint
        return {'url':self.url,'author_id':'writer','origin':'rss','title':self.title,
                'published_at':published,'first_seen_at':'2026-11-20T00:00:00Z','auto_evidence':ev}

    def classify(self, title, body, tags=()):
        return self.classifier.assess(title,body,tags,origin='page')['result']

    def test_short_negative_and_abstract_opinions(self):
        self.assertEqual(self.classify('AKB48の配信','歌声が好き。'), 'published')
        self.assertEqual(self.classify('同じことを繰り返す夜','AKB48の公演に行った。AKB48の歌唱に違和感がある。'), 'published')
        self.assertEqual(self.classify('今日の話','TWICEのライブに行った。BTSの歌声にも心を打たれた。'), 'published')
        self.assertEqual(self.classify('週末','地方アイドルの特典会に行った。心に残る。'), 'published')

    def test_announcement_incidental_and_fiction(self):
        self.assertEqual(self.classify('AKB48 出演情報','新しいテレビ出演をお知らせします。日時は公式から。'), 'excluded')
        self.assertEqual(self.classify('【夢小説】AKB48','私と架空のメンバーの物語。'), 'excluded')
        self.assertEqual(self.classify('今日のバスケット観戦','野球のメンバーとバスケの選手。試合頑張ってほしい。'*10), 'excluded')
        self.assertNotEqual(self.classify('ある記録','野球の球技大会を見た。'*8+'AKB48は好き。'), 'published')

    def test_robots_wildcard_query_and_precedence(self):
        robots = Robots('User-agent: *\nDisallow: /api/\nDisallow: /*/comments$\nAllow: /api/public\n')
        self.assertFalse(robots.allows('https://note.com/api/anything'))
        self.assertTrue(robots.allows('https://note.com/api/public'))
        self.assertFalse(robots.allows('https://note.com/writer/n/entry/comments'))
        self.assertTrue(robots.allows('https://note.com/writer/n/entry'))

    def test_browser_page_excludes_chrome_and_paid_structured_body(self):
        page=Page(self.url, '<nav>THEME</nav><script type="application/ld+json">'
                  '{"@type":"Article","isAccessibleForFree":false,"articleBody":"private",'
                  '"datePublished":"2026-11-11T00:00:00Z"}</script>'
                  '<div id="note-body"><p>内容</p><aside>related</aside><p>感想</p></div><footer>FOOTER</footer>')
        body, date, _ = page.article()
        self.assertEqual(body,'内容\n感想')
        self.assertEqual(date,'2026-11-11T00:00:00+00:00')
        self.assertFalse(page.available)

    def test_archive_staged_and_uses_original_date(self):
        records={self.url:self.article()}
        apply(records,[self.source],[],{},self.tax,settings=self.settings,now=self.now)
        self.assertEqual(records[self.url]['status'],'archive')
        release_archives(records,self.now,1,1)
        apply(records,[self.source],[],{},self.tax,settings=self.settings,now=self.now)
        self.assertEqual(records[self.url]['status'],'published')
        self.assertEqual(records[self.url]['published_at'],'2026-11-01T00:00:00Z')
        self.assertEqual(records[self.url]['site_added_at'],self.now.isoformat())

    def test_old_override_exclusion_and_opt_out_win(self):
        for mod in ({'articles':{self.url:{'status':'excluded'}}},{'blocked_authors':[self.source['url']]},
                    {'blocked_urls':[self.url+'?utm_source=a']},{'blocked_authors':['writer']}):
            rows={self.url:self.article('2026-11-24T00:00:00Z')}
            apply(rows,[self.source],[],mod,self.tax,settings=self.settings,now=self.now)
            self.assertEqual(rows[self.url]['status'],'excluded')

    def test_retry_closes_and_new_version_reopens(self):
        a=self.article()
        for days in (0,1,3,7):
            outcome(a,'insufficient_context',self.fingerprint,self.now+dt.timedelta(days=days))
        self.assertTrue(a['retry']['closed'])
        self.assertFalse(due(a,self.fingerprint,self.now+dt.timedelta(days=10)))
        self.assertTrue(due(a,'new-dictionary',self.now+dt.timedelta(days=10)))

    def test_candidate_is_own_feed_and_admits_mixed_sources(self):
        c = get_candidate('https://note.com/writer/n/n123?utm_source=test',channel='note-new')
        self.assertEqual(c['feed'],'https://note.com/writer/rss')
        fixture = (b'<rss><channel><title>Writer</title>'
                   b'<item><title>AKB48 concert</title><description>None</description><link>https://note.com/other/n/n6</link></item>'
                   b'<item><title>AKB48 concert</title><description>None</description><link>https://note.com/writer/n/n7</link>'
                   b'<pubDate>Thu, 20 Nov 2025 12:00:00 +0900</pubDate></item></channel></rss>')
        network=type('Network',(),{'get':lambda self,url:(fixture,{})})()
        with patch.object(self.classifier,'assess',return_value={'result':'published','classification':{'group_ids':['akb48']}}):
            source, items, _, _ = inspect(c,self.classifier,network,self.fingerprint,self.now,set())
        self.assertEqual(source['auto_class'],'C')
        self.assertEqual([a['url'] for a in items],['https://note.com/writer/n/n7'])
        self.assertEqual(len(tag_candidates('https://note.com/tag/AKB48',
                         b'<a href="/writer/n/n123" title="a"></a><a href="/tag/AKB48"></a>',
                         '48','note-tag','AKB48')),1)
