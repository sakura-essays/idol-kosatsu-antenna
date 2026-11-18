import copy,json,sys,pathlib,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from feed import ROOT,read
from publication import evidence
from catalog import apply
from collect import ingest
class PublicationTests(unittest.TestCase):
 def setUp(self):
  self.tax=read(ROOT/'config/taxonomy.json',{});self.s={'id':'fixture','url':'https://note.com/fixture','feed':'https://note.com/fixture/rss','enabled':True};self.url=self.s['url']+'/n/n123'
 def judge(self,t,b):return evidence(t,b,self.tax)
 def test_clear_essay(self):self.assertEqual(self.judge('AKB48の歌唱を考察','今回のAKB48の公演を見て、歌声の聞こえ方について考えた。声が重なると印象が変わるのが面白いと思った。')['result'],'published')
 def test_short_impression(self):self.assertEqual(self.judge('イコラブのライブ感想','イコラブのライブへ行った。初めて生で聴いた曲が良かった。隣の人も一緒に歌っていて楽しかった。')['result'],'published')
 def test_fiction_and_critique(self):
  self.assertEqual(self.judge('【妄ツイ】AKB48と僕の夏','これはメンバーとは何ら関係のない物語です。')['result'],'excluded')
  self.assertEqual(self.judge('アイドルの妄ツイ文化を考察','妄ツイ文化とアイドルの距離を考察する。ファンの表現としてどのように読まれるのか。境界について私は思う。')['result'],'published')
 def test_incidental_group_in_movie_review(self):
  self.assertEqual(self.judge('『映画作品』備忘録','Negiccoのライブについて書いたのは去年です。今日は映画についての記録です。映画を見て感じたこと。とても面白かった。')['result'],'pending')
 def test_group_from_body(self):
  self.assertEqual(self.judge('久々のライブの感想','AKB48のライブへ行った。曲の聴こえ方が好きだった。AKB48の公演を見て楽しかった。また見たいと思った。')['result'],'published')
 def test_unrelated(self):self.assertEqual(self.judge('今日の夕食','今日はカレーを作った。野菜をたくさん入れてみた。明日は何を食べようかと思った。とても美味しかった。')['result'],'excluded')
 def test_promo(self):self.assertEqual(self.judge('AKB48 商品紹介','販売開始。購入はこちら。商品紹介とスポンサーからのPR記事です。詳細についてはリンク先をご覧ください。')['result'],'excluded')
 def test_insufficient_and_ascii(self):
  for t,b in [('ありがとう',''),('LIVE感想','LIVEは楽しかった。'*10),('LOVEレビュー','LOVEについて感じたこと。'*10)]:self.assertEqual(self.judge(t,b)['result'],'pending')
 def test_multiple_groups(self):
  e=self.judge('AKB48とBTSの歌唱を考察','AKB48とBTSの歌唱を比較して、ライブならではの表現の違いが好きだと思った。ステージの見せ方も面白い。')
  self.assertEqual(set(e['classification']['group_ids']),{'akb48','bts'});self.assertEqual(e['result'],'published')
  self.assertEqual(self.judge('昨日の感想','AKB48とBTSのライブを見て楽しかった。'*5)['result'],'pending')
 def calc(self,override=None,source=None):
  r={};s=source or self.s;ingest(r,[{'url':self.url,'title':'AKB48のライブ感想','text':'AKB48のライブを見てとても楽しかった。'*4,'published_at':'2026-01-01'}],s)
  with patch('catalog.read',return_value={'enabled':True}):apply(r,[s],[],{'articles':{self.url:override}} if override else {},self.tax)
  return r[self.url]
 def test_new_rss_automatically_published(self):self.assertEqual(self.calc()['status'],'published')
 def test_manual_writer_requires_review_with_automation_enabled(self):
  source={**self.s,'publication_mode':'manual'}
  self.assertEqual(self.calc(source=source)['status'],'pending')
  approved={'status':'published','verified_nonfiction':True,'reviewed_title':'AKB48のライブ感想','reviewed_at':'2026-11-18','category_ids':['48']}
  self.assertEqual(self.calc(approved,source=source)['status'],'published')
 def test_manual_priority(self):
  for status in ('pending','excluded'):self.assertEqual(self.calc({'status':status})['status'],status)
  self.assertEqual(self.calc({'status':'published','verified_nonfiction':True,'reviewed_title':'AKB48のライブ感想','reviewed_at':'2026-11-18','category_ids':['48']})['status'],'published')
 def test_stopped_and_unknown_policy(self):
  for mode,status in [('stopped','excluded'),('bogus','pending')]:self.assertEqual(self.calc(source={**self.s,'publication_mode':mode})['status'],status)
 def test_changed_manual_title_held_even_with_rss(self):self.assertEqual(self.calc({'status':'published','verified_nonfiction':True,'reviewed_title':'旧題名','reviewed_at':'2026-11-18'})['status'],'pending')
 def test_audit(self):
  a=self.calc();self.assertEqual(a['decision']['method'],'automatic');self.assertNotIn('text',a);self.assertEqual(a['decision']['result'],'published')
 def test_backlog_release_and_kill_switch(self):
  for config,expected in [({'enabled':False},'pending'),({'enabled':True,'backlog_urls':[self.url]},'pending'),({'enabled':True,'backlog_urls':[self.url],'released_urls':[self.url]},'published')]:
   r={};ingest(r,[{'url':self.url,'title':'AKB48のライブ感想','text':'AKB48のライブを見てとても楽しかった。'*4,'published_at':'2026-01-01'}],self.s)
   with patch('catalog.read',return_value=config):apply(r,[self.s],[],{},self.tax)
   self.assertEqual(r[self.url]['status'],expected)
if __name__=='__main__':unittest.main()
