"""Independent catalog, identifiers and conservative title suggestions."""
import re, unicodedata, datetime as dt, hashlib
from urllib.parse import urlsplit
from feed import ROOT,read,canonical,date

def norm(s): return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',s).casefold()).strip()
def match(alias,text):
    a=norm(alias);t=norm(text)
    return bool(re.search(r'(?<![a-z0-9])'+re.escape(a)+r'(?![a-z0-9])',t)) if a.isascii() else a in t

def suggest(title,tax):
    groups=[g['id'] for g in tax['groups'] if any(match(a,title) for a in [g['name']]+g.get('aliases',[]))]
    # A person can only be suggested inside an already identified group context.
    members=[m['id'] for m in tax.get('members',[]) if set(groups)&set(m['group_ids']) and any(match(a,title) for a in [m['name']]+m.get('aliases',[]))]
    songs=[s['id'] for s in tax.get('songs',[]) if s['group_id'] in groups and any(match(a,title) for a in [s['name']]+s.get('aliases',[]))]
    return dict(group_ids=groups,member_ids=members,song_ids=songs,category_ids=sorted({g['category_id'] for g in tax['groups'] if g['id'] in groups}))

def owned(url,source):
    p,h=urlsplit(url),urlsplit(source['url'])
    return p.hostname==h.hostname and (h.hostname!='note.com' or p.path.startswith(h.path.rstrip('/')+'/n/'))

def valid_date(value):
    try:
        d=dt.datetime.fromisoformat(value) if 'T' in value else dt.datetime.combine(dt.date.fromisoformat(value),dt.time(),tzinfo=dt.timezone.utc)
        return bool(d.tzinfo) and d<=dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=10)
    except (TypeError,ValueError): return False

def apply(records,sources,manual,moderation,tax):
    src={s['id']:s for s in sources}; blocked={canonical(u) for u in moderation.get('blocked_urls',[])}
    blocked_authors=set(moderation.get('blocked_authors',[]))
    for item in manual:
        u=canonical(item['url'])
        if item['author_id'] not in src or not owned(u,src[item['author_id']]):raise ValueError('Manual author mismatch')
        if not item.get('verified_at') or not item.get('verification'):raise ValueError('Manual verification missing')
        # Manual verification never automatically approves changed RSS metadata.
        if u not in records:records[u]={**item,'url':u,'origin':'manual','status':'pending'}
    decisions={canonical(k):v for k,v in moderation.get('articles',{}).items()}
    ids={k:{v['id'] for v in tax[k]} for k in ('groups','members','songs','categories','topics')}
    fields={'group_ids':'groups','member_ids':'members','song_ids':'songs','category_ids':'categories','topic_ids':'topics'}
    from publication import automatic,VERSION,EVIDENCE_VERSION,digest,taxonomy_hash
    migration=read(ROOT/'config/publication.json',{})
    backlog=set(migration.get('backlog_urls',[])); released=set(migration.get('released_urls',[]))
    for u,a in records.items():
        before=(a.get('status'),a.get('reason'),a.get('decision',{}).get('method'))
        a['id']=hashlib.sha256(u.encode()).hexdigest()[:20]
        a['status']='pending';a['reason']='記事単位の確認待ち'
        a.update(suggest(a['title'],tax));a['topic_ids']=[]
        o=decisions.get(u,{})
        method='automatic'
        source=src.get(a['author_id'],{})
        if a.get('origin')=='rss' and source.get('feed') and owned(u,source) and valid_date(a.get('published_at')):
            a['status'],a['reason']=automatic(a,source,tax)
            if not o and a.get('rss_evidence',{}).get('version')==EVIDENCE_VERSION and a.get('rss_evidence',{}).get('title_hash')==digest(a['title']) and a['rss_evidence'].get('taxonomy_hash')==taxonomy_hash(tax):
                a.update(a['rss_evidence']['classification'])
            a['auto_candidate']=a['status']
            if a['status']=='published' and (not migration.get('enabled',False) or (u in backlog and u not in released)):
                a['status']='pending';a['reason']='過去記事の段階移行待ち' if u in backlog else '自動公開を停止中'
        else:
            a['auto_candidate']='pending'
        if o:
            method='human'
            a['status']='pending';a['reason']='人間の判断情報・タイトル・日付を再確認待ち'
        if o.get('reviewed_title') and o['reviewed_title']!=a['title']:
            a['status']='pending';a['reason']='確認後のタイトル変更・再確認待ち'

        if o.get('reviewed_title')==a['title']:
            for f,k in fields.items():
                if f in o:
                    if not isinstance(o[f],list) or not set(o[f])<=ids[k]:raise ValueError('Unknown '+f)
                    a[f]=o[f]
            # Group categories are always included; culture-only essays need no group.
            a['category_ids']=sorted(set(a['category_ids'])|{g['category_id'] for g in tax['groups'] if g['id'] in a['group_ids']})
            if o.get('status')=='published' and o.get('verified_nonfiction') and o.get('reviewed_at') and valid_date(a.get('published_at')) and a['category_ids']:
                a['status']='published';a['reason']='元記事を確認・掲載承認済み'
        if o.get('status') in ('pending','excluded'):a['status']=o['status'];a['reason']='管理者による保留・除外'
        if u in blocked or a['author_id'] in blocked_authors or not src.get(a['author_id'],{}).get('enabled') or source.get('publication_mode')=='stopped':
            a['status']='excluded';a['reason']='掲載停止（再取得防止）';method='block'
        current=(a['status'],a['reason'],method)
        if before!=current or a.get('decision',{}).get('rule_version')!=VERSION:
            a['decision']={'result':a['status'],'method':method,'reason':a['reason'],'decided_at':dt.datetime.now(dt.timezone.utc).isoformat(),'rule_version':VERSION}
        a['migration_cohort']='backlog' if u in backlog else 'new'
    return records

def load_catalog():
    sources=read(ROOT/'config/sources.json',[]);tax=read(ROOT/'config/taxonomy.json',{})
    records={canonical(a['url']):a for a in read(ROOT/'state/articles.json',[])}
    return list(apply(records,sources,read(ROOT/'config/manual_articles.json',[]),read(ROOT/'config/moderation.json',{}),tax).values()),sources,tax
