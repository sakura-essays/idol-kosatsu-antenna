"""Feed utilities adapted from Sakura Essay Antenna (MIT); metadata only."""
import datetime as dt, email.utils, html, http.client, ipaddress, json, pathlib, re, socket, unicodedata
import urllib.request, urllib.error, urllib.parse, urllib.robotparser
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
ROOT=pathlib.Path(__file__).resolve().parents[1]
UTC=dt.timezone.utc
UA='IdolEssayAntenna/1.0 (+https://sakura-essays.github.io/idol-kosatsu-antenna/)'
LIMIT=4_000_000

def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(path)

class Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[];self.links=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.skip+=1
        if not self.skip and tag=='a':
            link=dict(attrs).get('href')
            if link and len(self.links)<40:self.links.append(link)
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)

def plain(s):
    p=Text();p.feed(s or '');return ' '.join(p.parts).strip()

def canonical(url):
    p=urllib.parse.urlsplit(url.strip())
    if p.scheme not in ('https','http') or not p.hostname or p.username or p.password: raise ValueError('unsafe article URL')
    # note article query parameters identify share routes, not separate articles.
    # Keep arbitrary publisher queries, which can be part of their identity.
    if p.hostname in ('note.com','www.note.com') and re.fullmatch(r'/[A-Za-z0-9_-]+/n/[A-Za-z0-9]+/?',p.path):
        return 'https://note.com'+p.path.rstrip('/')
    q=[(k,v) for k,v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid','ref','hl')]
    return urllib.parse.urlunsplit((p.scheme,p.netloc.lower(),p.path,urllib.parse.urlencode(q),''))

def safe_url(url):
    canonical(url)  # Validate URL syntax, but check the actual fetch target below.
    p=urllib.parse.urlsplit(url.strip())
    if p.scheme!='https' or p.port not in (None,443):raise ValueError('HTTPS public endpoints only')
    # Known publisher hosts also work through environments whose HTTPS proxy resolves DNS.
    proxy_safe={'note.com','ameblo.jp','rssblog.ameba.jp','blogtag.ameba.jp'}
    known_suffixes=('.hatenablog.com','.hatenablog.jp','.hateblo.jp','.hatenadiary.jp','.hatenadiary.com','.blog.fc2.com','.wordpress.com')
    if p.hostname in proxy_safe or p.hostname.endswith(known_suffixes):return url
    for addr in socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(addr[4][0]).is_global:raise ValueError('Private address blocked')
    return url

class Redirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, check=None):
        self.check=check
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        safe_url(newurl)
        if self.check:self.check(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(url,headers=None,*,on_redirect=None):
    safe_url(url)
    req=urllib.request.Request(url,headers={'User-Agent':UA,**(headers or {})})
    try:
        with urllib.request.build_opener(Redirect(on_redirect)).open(req,timeout=10) as r:
            data=r.read(LIMIT+1)
            if len(data)>LIMIT:raise ValueError('Response exceeds 4 MB limit')
            return data,dict(r.headers)
    except http.client.HTTPException as exc:
        raise OSError('Incomplete HTTP response') from exc

def date(value):
    try:d=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,AttributeError):
        try:d=email.utils.parsedate_to_datetime(value)
        except (ValueError,TypeError):return None
    if not d or not d.tzinfo:return None
    return d.astimezone(UTC).isoformat()

def parse(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('DTD/entities not allowed')
    try:
        root=ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError('Malformed RSS/Atom XML') from exc
    if root.tag.split('}')[-1] not in ('rss','feed','RDF'):raise ValueError('Not an RSS/Atom feed')
    for item in root.iter():
        if item.tag.split('}')[-1] not in ('item','entry'):continue
        values={}
        tags=[]
        for node in item:
            key=node.tag.split('}')[-1]
            if key=='link' and node.attrib.get('href'):
                if node.attrib.get('rel','alternate')=='alternate':values['link']=node.attrib['href']
            elif key=='category':
                term=node.attrib.get('term') or node.text
                if term:tags.append(term.strip())
            elif key in ('content','summary','description') and len(node):
                values[key]=' '.join(node.itertext())
            elif node.text:values[key]=node.text
        raw=values.get('encoded') or values.get('content') or values.get('description') or values.get('summary') or ''
        source_text=Text()
        source_text.feed(re.sub(r'</(?:p|li|div|h[1-6])>|<br\s*/?>', '\n', raw, flags=re.I))
        text=' '.join(source_text.parts).strip()
        yield dict(title=html.unescape(values.get('title','')).strip(),url=values.get('link',''),
                   published_at=date(values.get('pubDate') or values.get('published') or values.get('date')),
                   text=text,tags=tags,links=source_text.links,creator=values.get('creatorName') or values.get('creator'),
                   truncated=bool(re.search(r'続きをみる|続きを読む|read more',text,re.I)))

def fiction_guard(title,text):
    """Article-level guard. Creative work elsewhere never disqualifies an author."""
    t=unicodedata.normalize('NFKC',title)
    b=unicodedata.normalize('NFKC',text or '')
    fiction=r'妄ツイ|妄リク|夢小説|創作小説|二次創作|夢日記|恋愛小説|短編小説|連載小説|妄想小説|妄想ストーリー'
    criticism=r'批評|考察|レビュー|感想|文化|について|とは|消費|倫理|規制|是非|問題|やめよう|書き手|界隈'
    # A bracketed genre label remains fiction even if its subtitle says 感想.
    if re.search(r'[【〖\[](?:妄ツイ|夢小説|連載小説)(?:[・/](?:妄ツイ|小説|連載小説|短編小説))*[】〗\]]',t):
        return 'excluded','創作ジャンルの明示（記事単位）'
    if re.match(r'^(?:【全文無料】)?脚本[「『]',t) and not re.search(r'(?:の|を)(?:考察|批評|感想|レビュー)',t):
        return 'excluded','創作脚本の明示（記事単位）'
    if re.search(fiction,t) and not re.search(criticism,t):
        return 'excluded','創作作品の明示（記事単位）'
    if re.search(r'(?:この物語は|この作品は|ここから[^。]{0,40})(?:[^。]{0,40})フィクション|配役も架空|妄想の中で開催|メンバーとは何ら関係のない物語',b):
        return 'excluded','本文に架空の物語・公演である明示'
    # A real MV/drama may contain dialogue, romance and fictional characters.
    # Ambiguous fiction signals go to review, never straight to publication.
    if (re.search(fiction,t+' '+b) or re.search(r'(?:[〇○△×]{2}\s*[「:：]|[〇○△×]\s*[:：])',b)):
        return 'pending','創作の手掛かりあり・批評や引用との区別を確認待ち'
    if re.search(r'第\s*[0-9０-９一二三四五六七八九十]+\s*話|幼馴染|幼なじみ|同棲',t) and not re.search(criticism,t):
        return 'pending','物語形式の可能性・実活動との関係を確認待ち'
    return None
