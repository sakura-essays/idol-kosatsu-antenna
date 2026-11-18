"""Versioned, deterministic RSS evidence; no article body is persisted."""
import re, hashlib, json, datetime as dt
from feed import fiction_guard
VERSION='rss-1.1'
ESSAY=r'考察|批評|感想|レビュー|分析|論評|振り返|参戦|観戦|行って|行った|観て|見て|聴いて|感じ|思った|思う|好き|楽しかっ|良かった|よかった|泣いた'
CONTEXT=r'アイドル|ライブ|コンサート|公演|歌唱|歌詞|楽曲|振付|推し|ファン|MV|ミュージックビデオ|卒業|運営|パフォーマンス'
CULTURE=r'アイドル|推し活|ファンダム|オタク文化|妄ツイ文化'
# Common nouns and short aliases cannot alone establish an idol subject.
AMBIGUOUS={'嵐','超特急','Perfume','SEVENTEEN','TWICE','・・・・・・・・・','元凶','Butter','フルーツバスケット'}
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def taxonomy_hash(tax):return digest(json.dumps(tax,ensure_ascii=False,sort_keys=True))
def evidence(title,text,tax):
    from catalog import suggest,match
    whole=title+' '+text
    def groups(value):
        return [g['id'] for g in tax['groups'] if any(a not in AMBIGUOUS and match(a,value) for a in [g['name']]+g.get('aliases',[])) or (g['name'] in AMBIGUOUS and any(c.isalnum() for c in g['name']) and match(g['name'],value) and re.search(CONTEXT,value))]
    tg,bg=groups(title),groups(text)
    body_subject=bool(bg) and all(any(match(a,text[:400]) and len(re.findall(re.escape(a),text,re.I))>=2 for a in [g['name']]+g.get('aliases',[])) for g in tax['groups'] if g['id'] in bg)
    title_culture=bool(re.search(CULTURE,title))
    body_culture=bool(re.search(CULTURE,text[:300])) and len(re.findall(CULTURE,text))>=2
    inferred=[];title_inferred=[]
    if re.search(CONTEXT,whole):
        for m in tax.get('members',[]):
            if len(m['name'])>=4 and match(m['name'],whole):
                inferred+=m['group_ids']
                if match(m['name'],title) and re.search(r'アイドル|ライブ|コンサート|公演|歌唱|歌詞|楽曲|卒業|ステージ',whole):title_inferred+=m['group_ids']
        for s in tax.get('songs',[]):
            if s['name'] not in AMBIGUOUS and any(mark+s['name']+end in whole for mark,end in [('「','」'),('『','』')]):
                inferred.append(s['group_id'])
                if s['name'] in title:title_inferred.append(s['group_id'])
    gs=sorted(set(tg or title_inferred or bg or inferred)); classification=suggest(whole,tax)
    classification['group_ids']=gs
    classification['member_ids']=[m['id'] for m in tax.get('members',[]) if set(gs)&set(m['group_ids']) and match(m['name'],whole)]
    classification['song_ids']=[s['id'] for s in tax.get('songs',[]) if s['group_id'] in gs and match(s['name'],whole)]
    classification['category_ids']=sorted({g['category_id'] for g in tax['groups'] if g['id'] in gs})
    culture=bool(re.search(CULTURE,whole))
    if not gs and culture:classification['category_ids']=['culture']
    guard=fiction_guard(title,text)
    # Explicit discussion of fiction culture is nonfiction; quoted narrative still holds.
    if guard and re.search(r'(?:妄ツイ|夢小説|二次創作)(?:文化|の文化|を批評|を考察|の是非|の倫理)',title) and not re.search(r'[〇○△×]{1,2}\s*[:：「]',text):guard=None
    if guard and guard[1]=='本文に架空の物語・公演である明示':guard=('pending','架空表現の引用と創作本文の区別を確認待ち')
    personal=bool(re.search(ESSAY,whole));title_essay=bool(re.search(ESSAY,title))
    promo=bool(re.search(r'アフィリエイト|PR記事|提供記事|購入はこちら|販売開始|商品紹介|スポンサー',whole,re.I))
    listing=bool(re.search(r'(?:セットリスト|出演情報|ニュース|開催情報|スケジュール)(?:のみ|まとめ|一覧|速報)?[！!。\s]*$',title)) and not personal
    unrelated=bool(re.search(r'今日の(?:夕食|昼食|朝食)|料理レシピ|株式投資|FX投資|競馬予想|天気予報',title)) and not gs and not culture
    result,reason='pending','関連性・文章形式の根拠不足'
    if guard:result,reason=guard
    elif promo:result,reason=('pending','宣伝と感想の混在') if personal else ('excluded','宣伝・商品紹介の明示')
    elif listing:result,reason='excluded','情報一覧のみ（感想の根拠なし）'
    elif unrelated:result,reason='excluded','無関係な題材の明示'
    elif len(text.strip())<40:reason='RSS要約が短く判定材料不足'
    elif not tg and len(set(bg))>1:reason='本文に複数グループ・主題の確認待ち'
    elif (gs or culture) and personal and (tg or title_inferred or title_culture or body_subject or body_culture):result,reason='published','アイドルの主題と考察・感想の文脈をRSSで確認'
    return dict(version=VERSION,taxonomy_hash=taxonomy_hash(tax),title_hash=digest(title),body_hash=digest(text),body_length=len(text.strip()),classification=classification,result=result,reason=reason,title_subject=bool(tg or title_inferred) or title_culture,title_essay=title_essay,body_subject=body_subject,body_culture=body_culture,observed_at=dt.datetime.now(dt.timezone.utc).isoformat())
def automatic(article,source,tax=None):
    if source.get('publication_mode')=='manual':return 'pending','書き手設定により記事単位の手動確認が必要'
    e=article.get('rss_evidence',{})
    if e.get('version')!=VERSION or e.get('title_hash')!=digest(article['title']):return 'pending','現行ルールのRSS根拠未取得'
    if tax is not None and e.get('taxonomy_hash')!=taxonomy_hash(tax):return 'pending','分類辞書変更・RSS根拠の再取得待ち'
    mode=source.get('publication_mode','standard')
    if mode not in ('eligible','standard','cautious'):return 'pending','書き手設定を確認待ち'
    if e['result']=='published' and mode=='cautious' and not (e['title_subject'] and e['title_essay']):return 'pending','慎重判定・タイトルの主題と形式の確認待ち'
    return e['result'],e['reason']
