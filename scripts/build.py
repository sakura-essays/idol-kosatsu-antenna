"""Build public metadata and static, directly addressable author pages."""
import collections,html,json,shutil,re,hashlib
from feed import ROOT,read,write
from catalog import load_catalog
FIELDS=('id','url','title','author_id','published_at','group_ids','member_ids','song_ids','category_ids','topic_ids')
def build():
    records,sources,tax=load_catalog();settings=read(ROOT/'config/settings.json',{})
    if len({s['id'] for s in sources})!=len(sources):raise ValueError('Duplicate author ID')
    for s in sources:
        if not re.fullmatch('[a-zA-Z0-9_-]+',s['id']):raise ValueError('Unsafe author ID')
    articles=[{k:a.get(k,[]) for k in FIELDS} for a in records if a['status']=='published'];articles.sort(key=lambda a:a['published_at'],reverse=True)
    groups={g['id']:g['name'] for g in tax['groups']}
    by_author=collections.defaultdict(list)
    for a in articles:by_author[a['author_id']].append(a)
    authors=[{k:s[k] for k in ('id','name','url','platform')}|{'count':len(by_author[s['id']]),'groups':sorted({groups[g] for a in by_author[s['id']] for g in a['group_ids']})} for s in sources if by_author[s['id']]]
    available={a['url'] for a in articles};picks=[]
    for p in read(ROOT/'config/pickups.json',[]):
        if p['url'] in available and p.get('reviewed_at') and p.get('criteria') and 1<=len(p.get('note',''))<=160 and p['url'] not in {x['url'] for x in picks}:picks.append({'url':p['url'],'note':p['note']})
    out=ROOT/'dist';out.mkdir(exist_ok=True)
    for p in (ROOT/'web').iterdir():shutil.copy2(p,out/p.name)
    data=dict(articles=articles,authors=authors,taxonomy=tax,settings=settings,pickups=picks[:6])
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    (out/'data.js').write_text('window.ANTENNA='+payload+';\n')
    template=(ROOT/'web/index.html').read_text()
    for asset in ('data.js','core.js','app.js','analytics.js','style.css'):
        version=hashlib.sha256((out/asset).read_bytes()).hexdigest()[:12];template=template.replace('"'+asset+'"','"'+asset+'?v='+version+'"')
    about=(out/'about.html').read_text()
    for asset in ('analytics.js','style.css','about.js'):
        version=hashlib.sha256((out/asset).read_bytes()).hexdigest()[:12];about=about.replace('"'+asset+'"','"'+asset+'?v='+version+'"')
    (out/'about.html').write_text(about)
    esc=html.escape;base=settings['base_url']
    def page(path,heading,rows,preset=''):
        body=template.replace('{{CANONICAL}}',esc(base+'/'+path,quote=True)).replace('{{HEADING}}',esc(heading))
        if path=='index.html':body=body.replace('<h1 id="page-heading">'+esc(heading)+'</h1>','<h1 id="page-heading"><span>'+esc(heading).replace('、','、</span><span>',1)+'</span></h1>')
        body=body.replace('{{FALLBACK}}','<ul>'+''.join('<li><a href="'+esc(a['url'],quote=True)+'">'+esc(a['title'])+'</a></li>' for a in rows[:40])+'</ul>')
        if path.startswith('authors/'):body=body.replace('<head>','<head><base href="../">')
        if preset:body=body.replace('</head>',preset+'</head>')
        body=body.replace('<title>アイドル考察アンテナ</title>','<title>'+esc(heading)+'｜アイドル考察アンテナ</title>')
        (out/path).write_text(body)
    page('index.html','人気の大小を離れて、アイドルを読む。',articles)
    page('writers.html','書き手から、違う景色へ。',articles,'<script>window.VIEW="writers";</script>')
    ad=out/'authors';shutil.rmtree(ad,ignore_errors=True);ad.mkdir()
    for a in authors:page('authors/'+a['id']+'.html',a['name']+' の記事',by_author[a['id']],'<script>window.PRESET_AUTHOR='+json.dumps(a['id'])+';</script>')
    (out/'.nojekyll').touch()
    paths=['index.html','writers.html','about.html']+['authors/'+a['id']+'.html' for a in authors]
    (out/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+esc(base+'/'+p)+'</loc></url>' for p in paths)+'</urlset>')
    (out/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: '+base+'/sitemap.xml\n')
    write(ROOT/'state/articles.json',records);write(ROOT/'state/review.json',[a for a in records if a['status']=='pending'])
    print('Built',len(articles),'articles /',len(authors),'authors')
if __name__=='__main__':build()
