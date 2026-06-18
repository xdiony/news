"""
新闻数据抓取脚本
抓取 RSS/Atom feeds → 翻译英文 → 去重 → 输出 news_data.json
"""
import urllib.request, urllib.parse, ssl, json, re, time, xml.etree.ElementTree as ET
from datetime import datetime

ssl._create_default_https_context = ssl._create_unverified_context

UA = 'Mozilla/5.0 (compatible; MorningDigest/1.0)'
TIMEOUT = 15

# ===================== 板块和源配置 =====================
FEEDS = {
    'shizheng': [
        ('新华网', 'http://www.xinhuanet.com/politics/news_politics.xml', 'zh'),
        ('人民网', 'http://www.people.com.cn/rss/politics.xml', 'zh'),
        ('澎湃新闻', 'https://www.thepaper.cn/rss_www.xml', 'zh'),
        ('观察者网', 'https://www.guancha.cn/rss', 'zh'),
        ('BBC News', 'https://feeds.bbci.co.uk/news/world/rss.xml', 'en'),
        ('Reuters', 'https://news.google.com/rss/search?q=site:reuters.com/world&hl=en-US&gl=US&ceid=US:en', 'en'),
    ],
    'jingji': [
        ('华尔街见闻', '__json__https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=30', 'zh'),
        ('第一财经', 'https://www.yicai.com/feed/', 'zh'),
        ('CNBC', 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114', 'en'),
    ],
    'keji': [
        ('36氪', 'https://36kr.com/feed', 'zh'),
        ('爱范儿', 'https://www.ifanr.com/feed', 'zh'),
        ('TechCrunch', 'https://techcrunch.com/feed/', 'en'),
        ('The Verge', 'https://www.theverge.com/rss/index.xml', 'en'),
        ('Wired', 'https://www.wired.com/feed/rss', 'en'),
        ('Ars Technica', 'https://feeds.arstechnica.com/arstechnica/technology-lab', 'en'),
        ('MIT Tech Review', 'https://www.technologyreview.com/feed/', 'en'),
        ('Hacker News', 'https://hnrss.org/frontpage', 'en'),
        ('Engadget', 'https://www.engadget.com/rss.xml', 'en'),
    ],
}

PANEL_NAMES = {
    'shizheng': {'name': '时政', 'emoji': '🏛', 'max': 15},
    'jingji': {'name': '经济', 'emoji': '💰', 'max': 15},
    'keji': {'name': '科技', 'emoji': '🤖', 'max': 15},
}

# ===================== 工具函数 =====================
def strip_html(text):
    if not text:
        return ''
    text = re.sub(r'<[^>]*>', '', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def clean_title(text):
    t = strip_html(text)
    # Remove common prefixes
    t = re.sub(r'^\[.*?\]\s*', '', t)
    t = re.sub(r'^(视频|图集|专题)\s*[：:]?\s*', '', t)
    return t.strip()

def word_set(text):
    cleaned = text.lower()
    cleaned = re.sub(r'[^\u4e00-\u9fa5a-z0-9]', ' ', cleaned)
    return set(w for w in cleaned.split() if len(w) > 0)

def overlap_pct(a, b):
    wa, wb = word_set(a), word_set(b)
    if not wa and not wb:
        return 0
    intersect = len(wa & wb)
    return intersect / max(len(wa), len(wb))

def try_parse_date(s):
    """Try various date formats"""
    if not s:
        return None
    formats = [
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S %Z',
        '%Y-%m-%dT%H:%M:%S%z',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except:
            continue
    
    # Try with timezone offset handling
    try:
        from datetime import timezone
        s_clean = re.sub(r'\s*[+-]\d{4}$', '', s)
        s_clean = re.sub(r'\s*GMT$', '', s_clean)
        return datetime.strptime(s_clean.strip(), '%a, %d %b %Y %H:%M:%S')
    except:
        pass
    
    return None

# ===================== RSS/Atom 解析 =====================
def fetch_rss(url):
    """Fetch and parse RSS 2.0 or Atom feed"""
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        content = resp.read()
    
    # Try to determine encoding
    encoding = 'utf-8'
    header = content[:2000]
    m = re.search(rb'encoding=["\']([^"\']+)["\']', header)
    if m:
        try:
            encoding = m.group(1).decode('ascii')
        except:
            pass
    
    text = content.decode(encoding, errors='replace')
    root = ET.fromstring(text)
    
    items = []
    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    
    # RSS 2.0 format
    for item in root.iter('item'):
        title = item.findtext('title', '')
        link = item.findtext('link', '')
        desc = item.findtext('description', '')
        pub = item.findtext('pubDate', '')
        items.append((title, link, desc, pub))
    
    # Atom format
    if not items:
        for entry in root.findall('.//atom:entry', ns) or root.findall('.//{http://www.w3.org/2005/Atom}entry'):
            title = entry.findtext('{http://www.w3.org/2005/Atom}title', '')
            link_el = entry.find('{http://www.w3.org/2005/Atom}link')
            link = link_el.get('href', '') if link_el is not None else ''
            desc = entry.findtext('{http://www.w3.org/2005/Atom}summary', '') or entry.findtext('{http://www.w3.org/2005/Atom}content', '')
            pub = entry.findtext('{http://www.w3.org/2005/Atom}published', '') or entry.findtext('{http://www.w3.org/2005/Atom}updated', '')
            items.append((title, link, desc, pub))
    
    return items

def fetch_json_api(url):
    """Fetch and parse JSON API (e.g. 华尔街见闻)"""
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    
    items = []
    content_list = data.get('data', {}).get('items', []) or data.get('data', [])
    if isinstance(content_list, dict):
        content_list = list(content_list.values())
    
    for entry in content_list:
        title = entry.get('title', '') or entry.get('content', '') or entry.get('text', '')
        if not title:
            continue
        link = entry.get('uri', '') or entry.get('url', '') or ''
        desc = entry.get('summary', '') or entry.get('content_text', '') or ''
        pub = entry.get('display_time', '') or entry.get('created_at', '') or ''
        items.append((title, link, desc, pub))
    
    return items

# ===================== 翻译 =====================
TRANSLATE_CACHE = {}

def translate_text(text, source='en', target='zh-CN'):
    if not text or len(text) < 3:
        return text
    key = text[:80]
    if key in TRANSLATE_CACHE:
        return TRANSLATE_CACHE[key]
    
    try:
        encoded = urllib.parse.quote(text[:500])
        url = f'https://translate.googleapis.com/translate_a/single?client=gtx&sl={source}&tl={target}&dt=t&q={encoded}'
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        result = ''.join(seg[0] for seg in data[0] if seg[0]).strip()
        TRANSLATE_CACHE[key] = result or text
    except Exception as e:
        TRANSLATE_CACHE[key] = text
    
    return TRANSLATE_CACHE[key]

def translate_batch(texts, workers=8):
    """Concurrent translation with ThreadPoolExecutor"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    results = [None] * len(texts)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {executor.submit(translate_text, t): i for i, t in enumerate(texts) if t}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except:
                results[idx] = texts[idx]
    return results

# ===================== 主流程 =====================
def fetch_all():
    all_data = {}
    
    for panel_key, feeds in FEEDS.items():
        print(f'\n{"="*50}')
        print(f'  {PANEL_NAMES[panel_key]["emoji"]} {PANEL_NAMES[panel_key]["name"]}')
        print(f'{"="*50}')
        
        panel_items = []
        
        for source_name, url, lang in feeds:
            print(f'  抓取: {source_name} ...', end=' ', flush=True)
            
            try:
                if url.startswith('__json__'):
                    raw_items = fetch_json_api(url[8:])
                else:
                    raw_items = fetch_rss(url)
                
                if not raw_items:
                    print(f'0条')
                    continue
                
                # Process items
                processed = []
                for title, link, desc, pub in raw_items:
                    title = clean_title(title or '')
                    if not title or len(title) < 4:
                        continue
                    desc = strip_html(desc or '')[:200]
                    pub_date = try_parse_date(pub)
                    processed.append({
                        'title': title,
                        'description': desc,
                        'link': link or '',
                        'pubDate': pub_date.isoformat() if pub_date else datetime.now().isoformat(),
                        'source': source_name,
                        '_lang': lang,
                    })
                
                print(f'{len(processed)}条')
                panel_items.extend(processed)
                
            except Exception as e:
                print(f'失败: {str(e)[:40]}')
        
        # Translate English items
        en_items = [(i, item) for i, item in enumerate(panel_items) if item['_lang'] == 'en']
        if en_items:
            print(f'  翻译 {len(en_items)} 条英文 ...', end=' ', flush=True)
            titles = [item['title'][:200] for _, item in en_items]
            descs = [item['description'][:300] if item['description'] else '' for _, item in en_items]
            
            all_texts = []
            for t, d in zip(titles, descs):
                all_texts.append(t)
                if d:
                    all_texts.append(d)
            
            translated = translate_batch(all_texts)
            
            idx = 0
            for i, item in en_items:
                panel_items[i]['title'] = translated[idx] or item['title']
                idx += 1
                if item['description']:
                    panel_items[i]['description'] = translated[idx] or item['description']
                    idx += 1
            
            print('完成')
        
        # Deduplicate
        max_items = PANEL_NAMES[panel_key]['max']
        panel_items.sort(key=lambda x: x['pubDate'], reverse=True)
        
        deduped = []
        seen_urls = set()
        for item in panel_items:
            if item['link'] and item['link'] in seen_urls:
                continue
            # Title overlap check
            is_dup = any(overlap_pct(item['title'], e['title']) > 0.55 for e in deduped)
            if is_dup:
                continue
            if item['link']:
                seen_urls.add(item['link'])
            deduped.append(item)
            if len(deduped) >= max_items:
                break
        
        all_data[panel_key] = deduped
        print(f'  → 最终: {len(deduped)} 条')
    
    # Add empty dongxiang panel
    all_data['dongxiang'] = []
    
    return all_data

if __name__ == '__main__':
    print('晨间速览 · 数据抓取')
    print(f'启动时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    
    start = time.time()
    data = fetch_all()
    
    output = {
        'generated_at': datetime.now().isoformat(),
        'panels': PANEL_NAMES,
        'data': data,
    }
    
    output_path = 'news_data.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    elapsed = time.time() - start
    print(f'\n{"="*50}')
    print(f'完成! 耗时 {elapsed:.1f}s')
    print(f'输出: {output_path}')
    
    for k, v in data.items():
        print(f'  {PANEL_NAMES.get(k, {}).get("name", k)}: {len(v)} 条')
