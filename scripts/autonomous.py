"""Run one bounded round of discovery, collection, rechecks and release."""
import collections
import concurrent.futures
import datetime as dt
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin

from autopublication import Classifier, VERSION, current, timestamp
from catalog import apply, owned, valid_date
from collect import ingest
from discover import (add_candidate, automatic_class, excluded_source, get_candidate,
                      note_page_links, primary_family, profile_key, remember_tags, run_discovery)
from feed import canonical, parse, read, write
from network import Deferred, PublicNetwork
from publication import taxonomy_hash
from retry import due, recheck, release_archives


def sources_for(root):
    manual = read(root/'config/sources.json', [])
    ids = {s['id'] for s in manual}
    keys = {profile_key(s['url']) for s in manual}
    return manual + [s for s in read(root/'state/discovered-sources.json', [])
                     if s['id'] not in ids and profile_key(s['url']) not in keys]


def feed_items(source, old, network, fingerprint):
    headers = {}
    if old.get('fingerprint') == VERSION + fingerprint:
        if old.get('etag'):
            headers['If-None-Match'] = old['etag']
        if old.get('modified'):
            headers['If-Modified-Since'] = old['modified']
    data, received = network.get(source['feed'], headers)
    items = []
    for item in parse(data):
        try:
            item['url'] = canonical(urljoin(source['url'].rstrip('/')+'/',item['url']))
        except ValueError:
            continue
        if item['title'] and owned(item['url'],source):
            items.append(item)
    if not items:
        raise ValueError('empty feed or no owned entries')
    return items, {k.lower():v for k,v in received.items()}


def feed_entry(headers, fingerprint, now, classification=None):
    h = {k.lower():v for k,v in headers.items()}
    row = {'etag':h.get('etag'), 'modified':h.get('last-modified'), 'last_success':now.isoformat(),
           'fingerprint':VERSION + fingerprint}
    if classification:
        row['auto_class'] = classification
    return row


def collect_feeds(records, sources, cache, network, classifier, fingerprint, now, moderation, candidates=None):
    def due_sources():
        for source in sources:
            if (not source.get('enabled') or not source.get('feed')
                    or excluded_source(source, moderation)):
                continue
            old = cache.get(source['id'], {})
            restart = timestamp(old.get('next'))
            success = timestamp(old.get('last_success'))
            if restart and restart > now:
                continue
            category = old.get('auto_class') or source.get('auto_class')
            if source.get('auto_class') and category == 'C' and success and not restart and now-success < dt.timedelta(days=2):
                continue
            yield source
    schedule = sorted(due_sources(),key=lambda s: cache.get(s['id'],{}).get('checked_at',''))
    def check(source):
        old = cache.get(source['id'],{})
        try:
            items, headers = feed_items(source,old,network,fingerprint)
            return 'ok', items, headers, ''
        except Deferred:
            return 'deferred', [], {}, ''
        except HTTPError as exc:
            if exc.code == 304 and old.get('fingerprint') == VERSION + fingerprint:
                return 'unchanged', [], {}, ''
            return 'error', [], {}, 'HTTP '+str(exc.code)
        except (ValueError,OSError) as exc:
            return 'error', [], {}, str(exc)[:120]

    logs = []
    taken = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as pool:
        for source,(status,items,headers,error) in zip(schedule,pool.map(check,schedule)):
            ident = source['id']
            old = cache.get(ident,{})
            log = {'id':ident,'checked_at':now.isoformat(),'status':status,'last_success':old.get('last_success')}
            if status == 'ok':
                taken += ingest(records,items,source,classifier=classifier,fingerprint=fingerprint,now=now)
                accepted = [records[item['url']] for item in items
                            if records[item['url']].get('page_evidence',records[item['url']]['auto_evidence'])['result'] == 'published']
                mode = automatic_class(len(accepted),len(items))
                mode = mode if mode != 'D' else old.get('auto_class') or source.get('auto_class') or 'C'
                cache[ident] = feed_entry(headers,fingerprint,now,mode)
                if source.get('auto_class'):
                    source['auto_class'] = mode
                    if accepted:
                        groups = [g for row in accepted
                                  for g in (row.get('page_evidence') or row['auto_evidence'])['classification']['group_ids']]
                        source['groups'] = sorted(set(groups))
                        source['primary_family'] = primary_family(groups,classifier,source.get('discovery_family',''))
                if candidates is not None:
                    for item in items[:6]:
                        if records[item['url']]['auto_evidence']['result']=='published':
                            for link in item['links'][:5]:
                                candidate=get_candidate(urljoin(item['url'],link),channel='article-link')
                                if candidate and candidate['id']!=source['id']:
                                    add_candidate(candidates,candidate,now)
                log.update(items=len(items),last_success=now.isoformat())
            elif status == 'unchanged':
                cache[ident] = {k:v for k,v in old.items() if k not in ('failures','next')}
                cache[ident]['last_success'] = now.isoformat()
                log['last_success'] = now.isoformat()
            elif status == 'error':
                failures = old.get('failures',0) + 1
                interval = dt.timedelta(hours=min(168,6*2**min(5,failures-1)))
                cache[ident] = {**old,'failures':failures,'next':(now+interval).isoformat()}
                log['error'] = error
            if status != 'deferred':
                cache[ident]['checked_at'] = now.isoformat()
            logs.append(log)
    return logs,taken


def recheck_queue(root, records, sources, candidates, discovery_state, classifier, network, fingerprint, now, limit, moderation):
    by_source = {s['id']:s for s in sources}
    manual = {canonical(u) for u in moderation.get('articles',{})}
    migrations = {row['url'] for row in read(root/'config/reassessment.json',{}).get('articles',[])}
    selected = [a for a in records.values() if a['status']=='pending' and a['url'] not in manual
                and a.get('auto_candidate') in {'pending','published'}
                and a.get('reason')!='explicit_manual_source'
                and a.get('origin')=='rss' and due(a,fingerprint,now)]
    def priority(article):
        recent = timestamp(article.get('published_at'))
        ev = article.get('auto_evidence') or article.get('rss_evidence',{})
        hint = bool(classifier.subjects(article['title']) or ev.get('classification',{}).get('group_ids'))
        started = bool(article.get('retry',{}).get('first'))
        return (article['url'] not in migrations, not started, not (recent and now-recent < dt.timedelta(days=7)),
                not hint, article.get('first_seen_at',''))
    selected.sort(key=priority)

    def check(article):
        source = by_source[article['author_id']]
        historical = source.get('groups',())
        return recheck(article,classifier,network,fingerprint,now,historical)
    processed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for article,page in zip(selected[:limit],pool.map(check,selected[:limit])):
            if page or article.get('retry',{}).get('last') == now.isoformat():
                processed += 1
            if page and article.get('page_evidence',{}).get('result') == 'published':
                groups=article['page_evidence']['classification']['group_ids']
                remember_tags(discovery_state,page.tags,primary_family(groups,classifier))
                for target in note_page_links(page):
                    row = get_candidate(target, channel='article-link')
                    if row:
                        add_candidate(candidates,row,now)
    return processed


def summary(records, sources, candidates, now, discovered, previous, rechecked, taken, logs, cache, moderation):
    reasons = collections.Counter(a['reason'] for a in records.values())
    totals = collections.Counter(a['status'] for a in records.values())
    queue = [a for a in records.values() if a['status']=='pending' and a['decision']['method']=='automatic'
             and a['reason']!='explicit_manual_source']
    queue_urls = {a['url'] for a in queue}
    manual = {a['url'] for a in records.values() if a['status']=='pending' and a['url'] not in queue_urls}
    active = [s for s in sources if s.get('enabled') and s.get('feed') and not excluded_source(s,moderation)
              and cache.get(s['id'],{}).get('failures',0)<5]
    class_counts = collections.Counter(cache.get(s['id'],{}).get('auto_class') or s.get('auto_class') or 'legacy' for s in active)
    changed = [a for url,a in records.items() if a['status']!=previous.get(url)]
    additions = collections.Counter(a['status'] for a in changed)
    automatic = collections.Counter(a['status'] for a in changed if a['decision']['method']=='automatic')
    by_group = collections.defaultdict(set)
    for s in active:
        for g in s.get('groups',()):
            by_group[g].add(s['id'])
    for a in records.values():
        if a['status']=='published':
            for g in a['group_ids']:
                by_group[g].add(a['author_id'])
    waiting_first = sum(not a.get('retry',{}).get('first') for a in queue)
    active_ids = {s['id'] for s in active}
    by_family = collections.Counter()
    for s in active:
        by_family[s.get('primary_family') or s.get('discovery_family') or 'unassigned'] += 1
    return {**discovered,'registered_total':len(sources),'enabled_feeds':len(active),'source_classes':dict(class_counts),
            'platforms':dict(collections.Counter(s['platform'] for s in active)),
            'families':dict(by_family),
            'groups':{k:len(v & active_ids) for k,v in sorted(by_group.items())},'candidates_total':len(candidates),
            'candidate_statuses':dict(collections.Counter(a['status'] for a in candidates.values())),
            'entries_fetched':taken,'decisions':dict(totals),'decisions_changed':dict(additions),
            'automatic_published':automatic['published'],'automatic_excluded':automatic['excluded'],
            'rechecked':rechecked,'internal_recheck':len(queue),'recheck_not_yet_attempted':waiting_first, 'archive_release_queue':totals['archive'],
            'long_recheck':sum(bool((first:=timestamp(a.get('retry',{}).get('first'))) and now-first>=dt.timedelta(days=7)) for a in queue),
            'manual_review':len(manual),'failed_feeds':sum(r['status']=='error' for r in logs),
            'deferred_feeds':sum(r['status']=='deferred' for r in logs),'reasons':dict(reasons),
            'automatic_publication_rate':round(automatic['published']/max(1,automatic['published']+automatic['excluded']),4),
            'manual_review_rate':round(sum(a['url'] in manual for a in changed)/max(1,len(changed)),4)}


def merge_bootstrap(records, sources, bundle, fingerprint):
    by_id = {s['id']:s for s in sources}
    imported = 0
    for addition in bundle.get('articles',[]):
        url = canonical(addition['url'])
        source = by_id.get(addition['author_id'])
        if not source or not owned(url,source):
            continue
        row = records.get(url)
        if row and (row['title'] != addition['title'] or row['author_id'] != addition['author_id']):
            continue
        evidence = {key:addition[key] for key in ('auto_evidence','page_evidence') if current(addition,key,fingerprint)}
        if not evidence:
            continue
        if row is None:
            row = {k:addition[k] for k in ('url','title','author_id','published_at','first_seen_at')}
            row['origin'] = 'rss'
            records[url] = row
        for key,value in evidence.items():
            if not current(row,key,fingerprint):
                row[key] = value
        imported += 1
    return imported


def run(root, settings, *, check_limit=300):
    now = dt.datetime.now(dt.timezone.utc)
    sources = sources_for(root)
    manual = read(root/'config/manual_articles.json',[])
    moderation = read(root/'config/moderation.json',{})
    taxonomy = read(root/'config/taxonomy.json',{})
    fingerprint = taxonomy_hash(taxonomy)
    classifier = Classifier(taxonomy)
    records = {canonical(a['url']):a for a in read(root/'state/articles.json',[])}
    previous = {u:a['status'] for u,a in records.items()}
    cache = read(root/'state/feeds.json',{})
    auto_sources = read(root/'state/discovered-sources.json',[])
    discovery_state = read(root/'state/discovery.json',{})
    candidates = read(root/'state/discovery-candidates.json',{})
    existing_candidates=set(candidates)
    existing_profiles={profile_key(source['url']) for source in sources}
    network = PublicNetwork(seconds=420)
    bundle_path = root/'state/bootstrap-articles.json'
    bundle = read(bundle_path,{})
    imported = merge_bootstrap(records,sources,bundle,fingerprint)
    logs, taken = collect_feeds(records,sources,cache,network,classifier,fingerprint,now,moderation,candidates)
    network.end = time.monotonic()+160
    accepted,discovered = run_discovery(root,discovery_state,candidates,sources,classifier,network,fingerprint,now,moderation)
    for source,items,headers in accepted:
        if excluded_source(source,moderation):
            continue
        taken += ingest(records,items,source,classifier=classifier,fingerprint=fingerprint,now=now)
        cache[source['id']] = feed_entry(headers,fingerprint,now,source['auto_class'])
        auto_sources.append(source)
        sources.append(source)
    apply(records,sources,manual,moderation,taxonomy,settings=settings,now=now)
    network.end = time.monotonic()+360
    # Previously confirmed groups can disambiguate sparse titles. A feed still needs
    # article-specific performance or fandom context before it can pass eligibility.
    history = collections.defaultdict(collections.Counter)
    for a in records.values():
        if a['status']=='published':
            history[a['author_id']].update(a['group_ids'])
    context_sources = [{**s, 'groups':s.get('groups') or [g for g,n in history[s['id']].most_common(3) if n >= 2]}
                       for s in sources]
    rechecked = recheck_queue(root,records,context_sources,candidates,discovery_state,classifier,network,fingerprint,now,check_limit,moderation)
    apply(records,sources,manual,moderation,taxonomy,settings=settings,now=now)
    if settings.get('enabled'):
        release_archives(records,now,settings.get('archive_daily_limit',140),settings.get('archive_author_daily_limit',5))
        apply(records,sources,manual,moderation,taxonomy,settings=settings,now=now)
    pending = [a for a in records.values() if a['status']=='pending' and (a['decision']['method']=='human' or a['reason']=='explicit_manual_source')]
    discovered['found'] = len(set(candidates)-existing_candidates-existing_profiles)
    metrics = summary(records,sources,candidates,now,discovered,previous,rechecked,taken,logs,cache,moderation)
    metrics['bootstrap_evidence_imported'] = imported
    metrics['bootstrap_writers_registered'] = len(set(bundle.get('writer_ids',[])) & {s['id'] for s in sources})
    status = {'attempted_at':now.isoformat(),'feeds':logs,'failures':metrics['failed_feeds'],'metrics':metrics}
    write(root/'state/discovered-sources.json',auto_sources)
    write(root/'state/articles.json',list(records.values()))
    write(root/'state/review.json',pending)
    write(root/'state/feeds.json',cache)
    write(root/'state/discovery.json',discovery_state)
    write(root/'state/discovery-candidates.json',candidates)
    write(root/'state/status.json',status)
    if bundle:
        bundle_path.unlink(missing_ok=True)
    headline = {k:metrics[k] for k in ('enabled_feeds','found','registered','automatic_published','internal_recheck','manual_review','failed_feeds','deferred_feeds')}
    print(json.dumps(headline,ensure_ascii=False),flush=True)
    step = os.environ.get('GITHUB_STEP_SUMMARY')
    if step:
        with Path(step).open('a',encoding='utf-8') as out:
            out.write('### 自動収集\n\n|項目|件数|\n|---|---:|\n')
            for k,v in headline.items():
                out.write(f'|{k}|{v}|\n')
    if metrics['failed_feeds']:
        print(f"::warning::{metrics['failed_feeds']} feeds failed; retained metadata and scheduled retry")
    return 0
