"""RSS/Atom metadata collection. New RSS entries pass the versioned publication gate."""
import datetime as dt, time, urllib.error, urllib.parse, urllib.robotparser
from feed import ROOT,UA,read,write,fetch,parse,canonical,fiction_guard
from catalog import owned,apply
from publication import evidence
from autopublication import VERSION as AUTO_VERSION

def ingest(records,items,source,*,classifier=None,fingerprint=None,now=None):
    tax=read(ROOT/'config/taxonomy.json',{}) if classifier is None else None
    now=now or dt.datetime.now(dt.timezone.utc)
    count=0
    for item in items:
        try:u=canonical(item['url'])
        except ValueError:continue
        if not item['title'] or not owned(u,source):continue
        old=records.get(u,{})
        row={**old, 'url':u, 'title':item['title'], 'author_id':source['id'],
             'published_at':old.get('published_at') or item['published_at'],
             'origin':old.get('origin','rss'), 'first_seen_at':old.get('first_seen_at') or now.isoformat()}
        if classifier is None:
            row['content_warning']=fiction_guard(item['title'],item['text'])
            row['rss_evidence']=evidence(item['title'],item['text'],tax)
        else:
            ev=item.get('auto_evidence',{})
            if ev.get('version')!=AUTO_VERSION or ev.get('taxonomy_hash')!=fingerprint:
                ev=classifier.assess(item['title'],item['text'],item.get('tags',()),
                                     tuple(source.get('groups',())),truncated=item.get('truncated',False))
            ev['taxonomy_hash']=fingerprint
            titled=bool(old and old.get('title')!=item['title'])
            previous=old.get('auto_evidence',{})
            changed=bool(previous) and any(ev[field] != previous.get(field) for field in ('title_hash','body_hash'))
            if changed or titled:
                row.pop('page_evidence',None)
                row.pop('retry',None)
            if titled:
                row['title_changed']=True
            row['auto_evidence']=ev
            if item.get('page_evidence',{}).get('taxonomy_hash')==fingerprint:
                row['page_evidence']=item['page_evidence']
        records[u]=row
        count+=1
    return count

def legacy_run():
    sources=read(ROOT/'config/sources.json',[]);records={canonical(a['url']):a for a in read(ROOT/'state/articles.json',[])}
    cache=read(ROOT/'state/feeds.json',{});logs=[];robots={};failures=0
    stamp=dt.datetime.now(dt.timezone.utc).isoformat()
    for s in sources:
        if not s.get('enabled') or not s.get('feed'):continue
        old=cache.get(s['id'],{});log={'id':s['id'],'checked_at':stamp,'last_success':old.get('last_success')}
        try:
            host=urllib.parse.urlsplit(s['feed']).netloc
            if host not in robots:
                rp=urllib.robotparser.RobotFileParser()
                try:data,_=fetch('https://'+host+'/robots.txt');rp.parse(data.decode().splitlines())
                except urllib.error.HTTPError as e:
                    if e.code==404:rp.parse([])
                    else:raise
                robots[host]=rp
            if not robots[host].can_fetch(UA,s['feed']):raise ValueError('robots.txt disallows feed')
            time.sleep(1)
            headers={}
            # Re-fetch after rule/dictionary changes; a 304 cannot refresh evidence.
            from publication import EVIDENCE_VERSION,taxonomy_hash
            tax=read(ROOT/'config/taxonomy.json',{})
            current=[a for a in records.values() if a['author_id']==s['id'] and a.get('origin')=='rss']
            fresh=bool(current) and all(a.get('rss_evidence',{}).get('version')==EVIDENCE_VERSION and a.get('rss_evidence',{}).get('taxonomy_hash')==taxonomy_hash(tax) for a in current)
            if fresh and old.get('etag'):headers['If-None-Match']=old['etag']
            if fresh and old.get('modified'):headers['If-Modified-Since']=old['modified']
            data,h=fetch(s['feed'],headers);items=list(parse(data))
            if not items:raise ValueError('Empty feed; existing data retained')
            log.update(status='ok',items=ingest(records,items,s),last_success=stamp)
            cache[s['id']]={'etag':h.get('ETag'),'modified':h.get('Last-Modified'),'last_success':stamp}
        except urllib.error.HTTPError as e:
            if e.code==304:log.update(status='unchanged',last_success=stamp);cache[s['id']]={**old,'last_success':stamp}
            else:log.update(status='error',error='HTTP '+str(e.code));failures+=1
        except Exception as e:log.update(status='error',error=str(e)[:200]);failures+=1
        logs.append(log);print(s['id'],log['status'],flush=True)
    apply(records,sources,read(ROOT/'config/manual_articles.json',[]),read(ROOT/'config/moderation.json',{}),read(ROOT/'config/taxonomy.json',{}))
    write(ROOT/'state/articles.json',list(records.values()));write(ROOT/'state/feeds.json',cache)
    write(ROOT/'state/review.json',[a for a in records.values() if a['status']=='pending'])
    write(ROOT/'state/status.json',{'attempted_at':stamp,'feeds':logs,'failures':failures})
    return 2 if failures else 0
def run():
    settings=read(ROOT/'config/publication.json',{})
    if settings.get('autonomous'):
        from autonomous import run as autonomous_run
        return autonomous_run(ROOT, settings)
    return legacy_run()


if __name__=='__main__':
    raise SystemExit(run())
