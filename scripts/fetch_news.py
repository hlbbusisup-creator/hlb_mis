#!/usr/bin/env python3
"""
HLB그룹 주간 뉴스 수집 스크립트
Google News RSS → news.json 저장
GitHub Actions에서 2시간마다 자동 실행
"""

import json
import re
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

# ── 검색어 목록 ─────────────────────────────────────────────────
QUERIES = [
    'HLB 신약', 'HLB 임상', 'HLB 계약', 'HLB FDA', 'HLB 허가',
    'HLB생명과학', 'HLB제약', 'HLB테라퓨틱스',
    'HLB바이오스텝', 'HLB이노베이션', 'HLB파나진', 'HLB제넥스', 'HLB펩',
    'HLB이엔지', 'HLB오션테크', '신화어드밴스', '프레시코',
    'HLB바이오코드', '지에프퍼멘틱', '코아바이오', 'HLB네트웍스',
    '현대요트', 'HLB솔루션', 'HLB에너지', 'HLB셀', '티니코',
    'HLB생활건강', 'HLB라이프케어', 'HLB에프엔비',
    '헤일로유니버스', '오리지널아카이브'
]

# ── 주식/분석 기사 필터 키워드 ──────────────────────────────────
STOCK_KW = [
    '주가', '추가매수', '장내매수', '자사주', '목표주가', '투자의견',
    '상장폐지', '공매도', '보통주', '우선주', '지분취득', '주식취득',
    '상한가', '하한가', '매수세', '매도세', '시가총액',
    '투자분석', '시황레이더', '주달', 'VI 발동', '투자심리',
    '거래량 확대', '수급', '기관매수', '외인매수', '공시', '보고서'
]

def is_stock_article(title):
    return any(kw in title for kw in STOCK_KW)

def clean_title(title):
    """HTML 엔티티 및 태그 제거"""
    title = re.sub(r'<[^>]+>', '', title)
    title = title.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>') \
                 .replace('&quot;', '"').replace('&#39;', "'").replace('&apos;', "'")
    return title.strip()

def parse_pubdate(s):
    """RSS pubDate 파싱 → datetime (UTC)"""
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.fromisoformat(s.replace('Z', '+00:00'))
        except Exception:
            return None

def title_words(title):
    """한글/영문 2자 이상 단어 추출 (중복 판단용)"""
    return re.findall(r'[가-힣A-Za-z0-9]{2,}', title)

def is_duplicate(new_title, kept):
    """기존 기사들과 핵심 단어 4개 이상 겹치면 중복"""
    words = set(title_words(new_title))
    for k in kept:
        shared = words & set(title_words(k['title']))
        if len(shared) >= 4:
            return True
    return False

def fetch_google_rss(query, max_items=5):
    """Google News RSS 수집"""
    url = ('https://news.google.com/rss/search?q=' +
           urllib.parse.quote(query) + '&hl=ko&gl=KR&ceid=KR:ko')
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; HLB-News-Bot/1.0)'
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_text = resp.read().decode('utf-8', errors='replace')
        root = ET.fromstring(xml_text)
        channel = root.find('channel')
        if channel is None:
            return []
        items = []
        for item in list(channel.findall('item'))[:max_items]:
            title_el  = item.find('title')
            link_el   = item.find('link')
            pubdate_el= item.find('pubDate')
            source_el = item.find('source')
            if title_el is None:
                continue
            title   = clean_title(title_el.text or '')
            link    = (link_el.text or '').strip() if link_el is not None else ''
            pubdate = parse_pubdate(pubdate_el.text or '') if pubdate_el is not None else None
            source  = (source_el.text or '').strip() if source_el is not None else ''
            if not title:
                continue
            items.append({
                'title':   title,
                'link':    link,
                'source':  source,
                'pubDate': pubdate,
                'query':   query
            })
        return items
    except Exception as e:
        print(f'  RSS 오류 [{query}]: {e}', file=sys.stderr)
        return []

def main():
    print('HLB 뉴스 수집 시작...')
    all_news = []
    seen_titles = set()

    for query in QUERIES:
        items = fetch_google_rss(query)
        for item in items:
            t = item['title']
            if t in seen_titles:
                continue
            seen_titles.add(t)
            all_news.append(item)
        print(f'  [{query}] {len(items)}건')

    print(f'수집 총 {len(all_news)}건')

    # ── 주식/분석 기사 필터 ──
    all_news = [n for n in all_news if not is_stock_article(n['title'])]
    print(f'필터 후 {len(all_news)}건')

    # ── 7일 이내 기사만 ──
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    all_news = [n for n in all_news if n['pubDate'] and n['pubDate'] >= week_ago]
    print(f'7일 필터 후 {len(all_news)}건')

    # ── 최신순 정렬 ──
    all_news.sort(key=lambda x: x['pubDate'] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    # ── 스마트 중복 제거 ──
    kept = []
    for n in all_news:
        if not is_duplicate(n['title'], kept):
            kept.append(n)
    print(f'중복 제거 후 {len(kept)}건')

    # ── 최대 20건 ──
    kept = kept[:20]

    # ── JSON 직렬화 ──
    fetched_at = datetime.now(timezone.utc).isoformat()
    result = {
        'news': [
            {
                'title':   n['title'],
                'link':    n['link'],
                'source':  n['source'],
                'pubDate': n['pubDate'].isoformat() if n['pubDate'] else '',
                'query':   n['query']
            }
            for n in kept
        ],
        'fetchedAt': fetched_at,
        'count': len(kept)
    }

    # 저장소 루트 기준으로 news.json 저장
    out_path = 'news.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'저장 완료: {out_path} ({len(kept)}건, {fetched_at})')

if __name__ == '__main__':
    main()
