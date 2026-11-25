"""Article eligibility for autonomous collection. Evidence contains no source prose."""
import datetime as dt
import functools
import re

from catalog import norm
from feed import fiction_guard
from publication import AMBIGUOUS, digest

VERSION = 'eligibility-2.2'
TOPIC = r'アイドル|ハロプロ|ハロー！プロジェクト|ジャニーズ|STARTO|K[ -]?POP|坂道シリーズ'
FANDOM = r'推しメン|チェキ|特典会|生誕祭|卒コン|対バン|推し活|ファンダム|オタ活|ヲタ活|ミーグリ|(?:個別)?握手会|推しについて|推しの配信|FCイベント|バーイベ'
PERFORMANCE = r'ライブ|コンサート|公演|楽曲|歌詞|ダンス|歌唱|パフォーマンス|歌声|振り付け|振付|生歌|MV|ミュージックビデオ|ステージ|劇場'
VOICE = (
    r'考察|批評|感想|レビュー|雑感|現場レポ|ライブレポ|観覧記|参加記|参戦|'
    r'行(?:った|きました|って(?:き|来)(?:た|ました))|(?:観|見|聴|聞)(?:て(?:き|来)た|たら|.*?かった)|'
    r'思(?:った|う|いました|える|えた)|感(?:じ|動)|考え(?:た|る|て)|'
    r'好き|苦手|良かった|よかった|すごかった|楽しかった|面白かっ|最高だった|'
    r'素晴らし|嬉し|うれし|楽しい|楽しめ|悔し|惜し(?:い|かっ)|泣(?:い|け)|'
    r'初めて|待ち望|気にな|印象|記憶に|見入|聞き入|聴き入|'
    r'かわい|可愛|かっこい|格好い|しみた|染みた|素敵|心を打|刺さ(?:る|った)|鳥肌|魅力|残念|違和感|物足り|個人的|自分にとって|'
    r'私(?:は|には|にとって)|僕(?:は|には|にとって)|私はそう|自分なり|'
    r'に惹か|心に残|に救われ|分かった|わかった|してほしい|ではないか|じゃないか|参加(?:した|しました|してきた)|'
    r'からこそ|だろう|に見え|に聞こえ|に聴こえ|に感じ|しなかった|雑記|を振り返'
)
TITLE_FORM = r'考察|批評|分析|感想|レビュー|雑感|現場レポ|ライブレポ|観覧記|参加記|参戦|振り返|の話|なぜ'
AD = r'アフィリエイト|広告掲載|PR記事|提供記事|購入はこちら|予約受付|販売開始|商品紹介|スポンサー|商品リンク'
NEWS = r'お知らせ|告知|ニュース|速報|転載|プレスリリース|出演情報|セットリスト|販売|チケット譲'
OTHER = r'今日の(?:夕食|昼食|朝食)|料理レシピ|家計簿|株式投資|FX投資|競馬予想|天気予報|コスメ収納|ポケモン(?:対戦|育成)|小説(?:感想|レビュー)|映画(?:鑑賞|レビュー)'
PRIVACY = r'(?:自宅住所|自宅の住所|本名と住所|携帯番号|個人の電話番号|実家の住所).{0,18}(?:晒[すし]|特定した|公開(?:します|する)|暴露)'
REPRINT = r'(?:無断転載(?:です|しました)|(?:元記事|ニュース|記事本文)(?:の|を)(?:全文転載|丸ごと転載))'
AMBIGUOUS_NAMES = {norm(x) for x in AMBIGUOUS} | {norm(x) for x in (
    '=LOVE', 'LOVE', 'HANA', 'INI', 'ME:I', 'ASP', 'BiS', 'IMP.', 'TOBE', 'ACE',
    'KARA', 'IU', 'TXT', 'RIIZE', 'IVE', 'EXO', 'V6', '龍宮城', 'ISSUE', 'SWEET STEADY', 'MORE STAR', 'WEST.',
    'LinQ', 'タイトル未定', 'りんご娘', 'Task have Fun', 'fishbowl', 'おこさまぷれ〜と。'
)}
NOISE = re.compile(r'^\s*(?:続きをみる|続きを読む|記事へのリアクション)[。\s]*$', re.I)
CONTEXT = TOPIC + '|' + FANDOM + '|' + PERFORMANCE + r'|メンバー|ファン|推し|卒業|担当|楽曲|ペンライト|オーディション'


@functools.lru_cache(maxsize=8)
def _alias_pattern(aliases):
    mapping = {}
    for alias, ident in aliases:
        key = norm(alias)
        if key:
            mapping.setdefault(key, set()).add(ident)
    # Longer aliases take precedence over contained short names.
    terms = sorted(mapping, key=lambda x: (-len(x), x))
    pattern = '|'.join(r'(?<![a-z0-9])' + re.escape(a) + r'(?![a-z0-9])'
                       if a.isascii() else re.escape(a) for a in terms)
    return re.compile(pattern or r'(?!)'), mapping


def _match(value, lookup, contextual=False):
    pattern, mapping = lookup
    normalized = norm(value)
    return {ident for m in pattern.finditer(normalized)
            if not contextual or m[0] not in AMBIGUOUS_NAMES or re.search(CONTEXT, value, re.I)
            for ident in mapping[m[0]]}


class Classifier:
    def __init__(self, taxonomy):
        self.groups = {g['id']: g['category_id'] for g in taxonomy['groups']}
        self.aliases = _alias_pattern(tuple((a, g['id']) for g in taxonomy['groups']
                                            for a in [g['name'], *g.get('aliases', [])]))
        self.members = tuple(taxonomy.get('members', []))
        self.songs = tuple(taxonomy.get('songs', []))

    def subjects(self, value):
        ids = _match(value, self.aliases, contextual=True)
        if re.search(CONTEXT, value, re.I):
            for m in self.members:
                if len(m['name']) >= 4 and norm(m['name']) in norm(value):
                    ids.update(m['group_ids'])
        return ids

    def assess(self, title, text, tags=(), history=(), *, origin='rss', truncated=False):
        title = title.strip()
        text = '\n'.join(line.strip() for line in text.splitlines() if not NOISE.fullmatch(line))
        text = text[:45_000]
        body = [s.strip() for s in re.split(r'[。！？\n]+|(?<=[.!?])\s+', text) if len(s.strip()) > 3]
        tags = ' '.join(tags)
        title_groups = self.subjects(title)
        tag_groups = self.subjects(tags)
        groups = set(title_groups)
        topic_title = bool(title_groups or re.search(TOPIC + '|' + FANDOM, title, re.I))
        topical, voiced, personal = 0, 0, 0
        topic_intro = False
        first_groups = set()
        for index, section in enumerate(body):
            subject = self.subjects(section)
            explicit = bool(subject or re.search(TOPIC + '|' + FANDOM, section, re.I))
            supported = bool((topic_title or tag_groups or history) and re.search(PERFORMANCE + '|' + FANDOM, section, re.I))
            groups.update(subject)
            if index < 4:
                first_groups.update(subject)
            if explicit or supported:
                topical += 1
                topic_intro |= index < 4 and explicit
            opinion = bool(re.search(VOICE, section, re.I))
            personal += opinion
            if opinion and (explicit or supported):
                voiced += 1
        if not groups and (topic_title or topical) and tag_groups:
            groups = tag_groups
        if not groups and history and topical and re.search(FANDOM, text, re.I):
            groups = set(history) if len(history) == 1 else set()
        whole = title + '\n' + text
        group_ids = sorted(g for g in groups if g in self.groups)
        category_ids = sorted({self.groups[g] for g in group_ids})
        classification = {
            'group_ids': group_ids,
            'category_ids': category_ids or ['culture'],
            'member_ids': [m['id'] for m in self.members if groups.intersection(m['group_ids']) and norm(m['name']) in norm(whole)],
            'song_ids': [s['id'] for s in self.songs if s['group_id'] in groups and any(x + s['name'] + y in whole for x, y in [('「', '」'), ('『', '』')])],
        }
        title_form = bool(re.search(TITLE_FORM, title))
        headline_voice = bool(re.search(VOICE, title))
        fan_report = bool(re.search(r'配信|特典会|イベント|公演|ライブ',title) and
                          len(set(re.findall(FANDOM,text,re.I)))>=2 and personal>=2)
        firsthand = bool(re.search(r'私(?:は|が)|僕(?:は|が)|個人的|行って(?:き|来)|参加して|買って',text))
        strong_body = (topical >= 2 and (topic_intro or voiced >= 2)
                       and (topical >= max(2, len(body) // 14) or (first_groups and voiced)))
        described_subject = bool(topical and personal and
                                 ((first_groups and re.search(r'について|考えてみた|の話|レポ|感想|推し|ヲタク', title))
                                  or (groups and '選抜' in title and len(re.findall(r'センター|選抜メンバー',text))>=3)))
        has_subject = topic_title or strong_body or described_subject or fan_report or (bool(tag_groups) and topical and personal)
        guard = fiction_guard(title, text)
        fiction_topic = re.search(r'(?:妄ツイ|夢小説|二次創作)(?:文化|の文化|を批評|を考察|の是非|の倫理)', title)
        about_real_episode = bool((title_groups or topical >= 2) and personal and
                                  re.search(r'番組|配信|ドラマ|ドキュメンタリー|ラジオ|放送', whole))
        result, reason = 'pending', 'insufficient_context'
        if re.search(PRIVACY, whole) or re.search(REPRINT, whole):
            result, reason = 'excluded', 'explicit_privacy_or_reprint'
        elif not groups and re.search(r'私は.{0,35}アイドル(?:でも|で(?:は|も)|じゃ)ない', text[:500]):
            result, reason = ('pending' if truncated else 'excluded'), 'unrelated_topic'
        elif guard and not (guard[0]=='pending' and (fiction_topic or
                           (about_real_episode and guard[1].startswith('物語形式')))):
            result, reason = guard[0], 'fiction' if guard[0] == 'excluded' else 'ambiguous_fiction'
        elif re.search(r'学マス|学園アイドルマスター|シャニマス|デレステ|アイドルマスター|アイカツ', whole) and not groups and not re.search(r'声優.{0,12}(?:ライブ|公演)|(?:リアル|現実)のアイドル|声優として', whole):
            result, reason = 'excluded', 'fictional_subject'
        elif title_form and re.search(OTHER, title) and not topic_title and voiced < 2:
            result, reason = ('excluded' if origin == 'page' or not truncated else 'pending'), 'unrelated_topic'
        elif re.search(r'お知らせ|告知',title) and re.search(r'(?:ブログ|記事|レポ).{0,12}(?:予定|書きます|お楽しみに|準備中|公開します)',text) and len(text)<270:
            result,reason=('pending' if truncated else 'excluded'),'announcement_or_promotion'
        elif re.search(NEWS + '|' + AD, title) and not (personal and (voiced or title_form or headline_voice or (topic_title and personal>=2 and firsthand))):
            result, reason = ('pending' if truncated else 'excluded'), 'announcement_or_promotion'
        elif re.search(AD, text) and not (voiced or (topic_title and (title_form or firsthand) and personal>=2)):
            result, reason = ('pending' if truncated else 'excluded'), 'promotion_without_comment'
        elif has_subject and ((topic_title and personal and (topical or title_form or headline_voice or (origin=='page' and personal>=2))) or
                              (fan_report and origin=='page') or
                              (strong_body and (voiced or (personal and (title_form or topical >= 3)))) or
                              (described_subject and (origin == 'page' or voiced)) or
                              (tag_groups and personal and (voiced or (origin == 'page' and topical)))):
            if origin == 'page' or not truncated or topic_title or (strong_body and voiced >= 2):
                result, reason = 'published', 'original_idol_commentary'
        elif (origin=='page' and len(body)<=3 and not truncated and voiced
              and re.search(r'アイドル.{0,8}(?:公演|特典会|配信|ライブ)|(?:推しメン|ミーグリ|特典会).{0,8}(?:参加|行った)', whole)):
            result,reason='published','short_idol_impression'
        elif (origin=='page' and truncated and topic_title and title_form and len(text)>=55
              and re.search(r'について|を論じ|を分析|を検討|検証',text)
              and not re.search(AD,text)):
            result,reason='published','editorial_scope_in_visible_preview'
        elif len(text) >= 15 and topic_title and headline_voice and (origin == 'page' or not truncated) and not re.search(NEWS + '|' + AD, whole):
            result, reason = 'published', 'short_idol_impression'
        elif origin == 'page' and len(text) >= 160 and not (topic_title or topical or tag_groups):
            result, reason = 'excluded', 'unrelated_topic'
        elif re.search(OTHER, title) and not (topic_title or topical):
            result, reason = ('pending' if truncated else 'excluded'), 'unrelated_topic'
        return {'version': VERSION, 'title_hash': digest(title), 'body_hash': digest(text),
                'body_length': len(text), 'classification': classification, 'result': result,
                'reason': reason, 'origin': origin, 'truncated': truncated}


def current(article, key, fingerprint):
    ev = article.get(key, {})
    if (ev.get('version') == VERSION and ev.get('taxonomy_hash') == fingerprint
            and ev.get('title_hash') == digest(article['title'])):
        return ev
    return None


def timestamp(value):
    try:
        parsed = dt.datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def auto_decision(article, source, fingerprint, now):
    page = current(article, 'page_evidence', fingerprint)
    rss = current(article, 'auto_evidence', fingerprint)
    ev = page or rss
    state = article.get('retry', {})
    if state.get('cause') == 'source_not_public' and state.get('closed') and state.get('version') == VERSION:
        return 'excluded', 'source_not_public', ev
    if source.get('publication_mode') == 'manual' and not source.get('auto_class'):
        return 'pending', 'explicit_manual_source', ev
    if not ev or ev['result'] == 'pending':
        # A weak page extraction must never become evidence of irrelevance.
        if state.get('closed') and state.get('version') == VERSION and state.get('taxonomy_hash') == fingerprint:
            return 'excluded', state['closed'], ev
        old = article.get('rss_evidence', {})
        if (not ev and old.get('result') == 'excluded' and old.get('title_hash') == digest(article['title'])
                and (old.get('reason', '').startswith('創作') or old.get('reason') == '無関係な題材の明示')):
            return 'excluded', 'legacy_explicit_exclusion', None
        return 'pending', ev['reason'] if ev else 'collect_article_evidence', ev
    if ev['result'] == 'published' and page is None and source.get('auto_class') == 'C' and ev['truncated']:
        if state.get('closed') and state.get('version') == VERSION and state.get('taxonomy_hash') == fingerprint:
            return 'excluded', state['closed'], ev
        return 'pending', 'verify_low_frequency_source_excerpt', ev
    return ev['result'], ev['reason'], ev
