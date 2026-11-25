"""Bounded article rechecks and gradual historical releases."""
import collections
import datetime as dt
from urllib.error import HTTPError

from article_page import Page
from autopublication import VERSION, current, timestamp
from catalog import valid_date
from feed import canonical
from network import Deferred, RobotsDenied

DAY = dt.timedelta(days=1)
TRANSIENT_CODES = {408, 425, 429, 500, 502, 503, 504}


def check_page(article, classifier, network, fingerprint, history=()):
    data, _ = network.get(article['url'])
    page = Page(article['url'], data)
    body, published, tags = page.article()
    page_url = page.metadata.get('canonical') or page.metadata.get('og:url')
    if page_url and canonical(page_url) != article['url']:
        raise ValueError('canonical article mismatch')
    if not body:
        raise ValueError('public article body unavailable')
    ev = classifier.assess(article['title'], body, tags, history, origin='page', truncated=not page.available)
    ev['taxonomy_hash'] = fingerprint
    return ev, published, page


def due(article, fingerprint, now):
    state = article.get('retry', {})
    if state.get('version') != VERSION or state.get('taxonomy_hash') != fingerprint:
        return True
    resume = timestamp(state.get('next'))
    # A closed record remains recoverable on source update or a new rule/dictionary.
    return not state.get('closed') and (resume is None or resume <= now)


def outcome(article, status, fingerprint, now):
    state = article.get('retry', {})
    if state.get('version') != VERSION or state.get('taxonomy_hash') != fingerprint:
        state = {}
    first = timestamp(state.get('first')) or now
    attempts = state.get('attempts', 0) + 1
    state = {'version': VERSION, 'taxonomy_hash': fingerprint, 'first': first.isoformat(),
             'attempts': attempts, 'last': now.isoformat(), 'cause': status}
    if status == 'source_not_public':
        state['closed'] = 'source_not_public'
    elif now - first >= DAY * (21 if status == 'temporary_access_failure' else 7) or attempts >= (7 if status == 'temporary_access_failure' else 4):
        state['closed'] = 'recheck_exhausted:' + status
    else:
        wait = dt.timedelta(days=min(3, 2 ** (attempts - 1)))
        state['next'] = min(now + wait, first + (21 if status == 'temporary_access_failure' else 7) * DAY).isoformat()
    article['retry'] = state


def recheck(article, classifier, network, fingerprint, now, history=()):
    try:
        ev, published, page = check_page(article, classifier, network, fingerprint, history)
        article['page_evidence'] = ev
        if not valid_date(article.get('published_at')) and valid_date(published):
            article['published_at'] = published
        if ev['result'] == 'pending' or not valid_date(article.get('published_at')):
            outcome(article, ev['reason'] if valid_date(article.get('published_at')) else 'publication_date_unverified', fingerprint, now)
        else:
            article.pop('retry', None)
        return page
    except Deferred:
        return None
    except RobotsDenied:
        outcome(article, 'robots_disallowed', fingerprint, now)
    except HTTPError as exc:
        reason = 'temporary_access_failure' if exc.code in TRANSIENT_CODES else 'source_not_public' if exc.code in (404, 410) else 'page_access_unavailable'
        outcome(article, reason, fingerprint, now)
    except (OSError, TimeoutError):
        outcome(article, 'temporary_access_failure', fingerprint, now)
    except ValueError:
        outcome(article, 'public_body_unavailable', fingerprint, now)
    return None


def release_archives(records, now, daily_limit=140, author_limit=5):
    today = now.date().isoformat()
    released_today = [a for a in records.values() if a.get('archive_released_on') == today]
    counts = collections.Counter(a['author_id'] for a in released_today)
    remaining = max(0, daily_limit - len(released_today))
    by_author = collections.defaultdict(list)
    for article in sorted((a for a in records.values() if a['status'] == 'archive'),
                          key=lambda a: timestamp(a['published_at']), reverse=True):
        by_author[article['author_id']].append(article)
    authors = sorted(by_author, key=lambda key: counts[key])
    for rank in range(author_limit):
        for author in authors:
            if remaining == 0:
                return
            if counts[author] < author_limit and rank < len(by_author[author]):
                by_author[author][rank]['archive_released_on'] = today
                counts[author] += 1
                remaining -= 1
