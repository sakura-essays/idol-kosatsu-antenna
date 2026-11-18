"""Dry-run the backlog; explicit URL release only, never a moving count limit."""
import argparse,collections,random
from feed import ROOT,read,write
from catalog import load_catalog

def report():
    rows,_,_=load_catalog()
    baseline=set(read(ROOT/'config/publication.json',{}).get('backlog_urls',[]))
    groups=collections.defaultdict(list)
    for a in rows:
        if a['url'] in baseline and a.get('decision',{}).get('method')=='automatic':groups[a.get('auto_candidate','pending')].append(a)
    summary={'counts':{k:len(groups[k]) for k in ('published','pending','excluded')},'samples':{},'author_distribution':{},'group_distribution':{}}
    rng=random.Random(20261118)
    for key,items in groups.items():
        summary['samples'][key]=[{'url':a['url'],'title':a['title'],'reason':a.get('rss_evidence',{}).get('reason',a['reason']),'body_length':a.get('rss_evidence',{}).get('body_length',0)} for a in rng.sample(sorted(items,key=lambda a:a['url']),min(20,len(items)))]
    summary['author_distribution']=dict(collections.Counter(a['author_id'] for a in groups['published']))
    summary['group_distribution']=dict(collections.Counter(g for a in groups['published'] for g in a['group_ids']))
    return summary
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='state/publication-dry-run.json');args=p.parse_args()
    result=report();write(ROOT/args.output,result);print(result['counts']);print(result['author_distribution']);print(result['group_distribution'])
