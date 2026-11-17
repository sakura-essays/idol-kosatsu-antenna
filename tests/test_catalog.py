import copy,json,sys,pathlib,unittest,tempfile
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from feed import ROOT,canonical,parse,safe_url
from catalog import apply,suggest,read,load_catalog
from collect import ingest,run
class CatalogTests(unittest.TestCase):
 def setUp(self):
  self.sources=read(ROOT/'config/sources.json',[]);self.manual=read(ROOT/'config/manual_articles.json',[]);self.mod=read(ROOT/'config/moderation.json',{});self.tax=read(ROOT/'config/taxonomy.json',{});self.a=self.manual[0];self.url=self.a['url']
 def calc(self,records=None,mod=None):return apply(records or {},self.sources,self.manual,mod or self.mod,self.tax)
 def test_manual_publication_and_unique(self):
  r=self.calc();self.assertEqual(len(r),len(self.manual));self.assertTrue(all(a['status']=='published' for a in r.values()))
 def test_tracking_dedup(self):self.assertEqual(canonical(self.url+'?utm_source=x#top'),self.url)
 def test_note_share_routes_are_one_article(self):
  self.assertEqual(canonical(self.url+'?sub_rt=share_pb&magazine_key=xyz'),self.url)
  self.assertEqual(canonical(self.url.replace('https://note.com','http://www.note.com')+'/'),self.url)
 def test_other_publishers_keep_identity_query(self):
  self.assertEqual(canonical('https://example.org/?p=123&utm_source=test'),'https://example.org/?p=123')
 def test_fetch_checks_actual_scheme_and_port(self):
  for u in ('http://note.com/account/n/id','https://note.com:444/account/n/id'):
   with self.assertRaises(ValueError):safe_url(u)
 def test_block_wins_over_approval(self):
  m=copy.deepcopy(self.mod);m['blocked_urls']=[self.url];self.assertEqual(self.calc(mod=m)[self.url]['status'],'excluded')
 def test_author_block(self):
  m=copy.deepcopy(self.mod);m['blocked_authors']=[self.a['author_id']];self.assertEqual(self.calc(mod=m)[self.url]['status'],'excluded')
 def test_title_change_requires_new_review(self):
  r=self.calc();r[self.url]['title']='Changed title';self.assertEqual(self.calc(r)[self.url]['status'],'pending')
 def test_future_date_never_published(self):
  r=self.calc();r[self.url]['published_at']='2999-01-01';self.assertEqual(self.calc(r)[self.url]['status'],'pending')
 def test_new_rss_is_pending_and_no_body_storage(self):
  r={};s=self.sources[0];u=s['url']+'/n/test'
  ingest(r,[dict(url=u,title='モーニング娘。 感想',published_at='2020-01-01',text='private feed text')],s)
  self.assertNotIn('text',r[u]);self.assertEqual(self.calc(r)[u]['status'],'pending')
 def test_feed_cannot_impersonate_another_note_author(self):
  r={};ingest(r,[dict(url='https://note.com/other/n/xxx',title='test',published_at='2020-01-01',text='')],self.sources[0]);self.assertFalse(r)
 def test_cross_group_and_ascii_boundary(self):
  self.assertEqual(set(suggest('AKB48 と BTS の考察',self.tax)['group_ids']),{'akb48','bts'})
  self.assertNotIn('ive',suggest('LIVE感想',self.tax)['group_ids'])
  self.assertNotIn('ini',suggest('minimal',self.tax)['group_ids'])
 def test_person_without_group_not_inferred(self):self.assertFalse(suggest('松村北斗の演技',self.tax)['member_ids'])
 def test_atom_and_rss(self):
  a=list(parse(b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>T</title><link href="https://example.org/a"/><published>2020-01-01T00:00:00Z</published></entry></feed>'))
  self.assertEqual(a[0]['url'],'https://example.org/a');self.assertTrue(a[0]['published_at'])
  a=list(parse(b'<rss><channel><item><title>X</title><link>https://example.org/b</link><pubDate>Wed, 01 Jan 2020 00:00:00 GMT</pubDate></item></channel></rss>'));self.assertTrue(a[0]['published_at'])
  with self.assertRaises(ValueError):list(parse(b'<!DOCTYPE rss><rss/>'))
 def test_failure_retains_existing_records(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp);(p/'config').mkdir();(p/'state').mkdir()
   for f in ['sources','manual_articles','moderation','taxonomy']:(p/'config'/f'{f}.json').write_text(json.dumps(read(ROOT/'config'/f'{f}.json',{})))
   initial=list(self.calc().values());(p/'state/articles.json').write_text(json.dumps(initial))
   with patch('collect.ROOT',p),patch('collect.fetch',side_effect=TimeoutError('fixture failure')),patch('collect.time.sleep'):
    self.assertEqual(run(),2)
   after=read(p/'state/articles.json',[]);self.assertEqual({a['url'] for a in initial},{a['url'] for a in after});self.assertTrue(all(a['status']=='published' for a in after))
 def test_publication_has_valid_identifiers(self):
  rows,_,_=load_catalog();self.assertEqual(len({a['url'] for a in rows}),len(rows))
  for a in rows:
   for field,key in [('group_ids','groups'),('member_ids','members'),('song_ids','songs'),('topic_ids','topics'),('category_ids','categories')]:self.assertLessEqual(set(a.get(field,[])),{x['id'] for x in self.tax[key]})
if __name__=='__main__':unittest.main()
