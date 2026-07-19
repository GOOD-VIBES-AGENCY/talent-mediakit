#!/usr/bin/env python3
"""
GVA メディアキット サムネイル更新スクリプト
Instagram投稿URLからog:imageを取得してthumbsに保存する
"""
import re
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import html

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TALENTS = ["kanna", "mayu", "miu", "momoka", "oto", "ririka", "sae", "saki", "yui"]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'ja,en;q=0.9',
}


def get_og_image(post_url):
    """Instagram投稿URLからog:imageを取得"""
    req = urllib.request.Request(post_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
        
        match = re.search(r'og:image"\s+content="([^"]+)"', content)
        if match:
            return html.unescape(match.group(1))
        return None
    except Exception as e:
        print(f"  ERROR getting {post_url}: {e}")
        return None


def download_image(url, filepath):
    """画像をダウンロード"""
    req = urllib.request.Request(url, headers={
        **HEADERS,
        'Referer': 'https://www.instagram.com/',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        with open(filepath, 'wb') as f:
            f.write(data)
        return len(data)
    except Exception as e:
        print(f"  ERROR downloading: {e}")
        return 0


def extract_post_urls(html_content):
    """HTMLからpost URLを抽出"""
    pattern = r'url:\s*"(https://www\.instagram\.com/(?:reel|p)/[^/"]+/?)"'
    return re.findall(pattern, html_content)


def update_html_thumbs(html_path, count):
    """HTMLのthumb URLを相対パスに変更"""
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    new_lines = []
    thumb_idx = 0
    for line in lines:
        if re.search(r'thumb:\s*"https://scontent', line) and thumb_idx < count:
            new_thumb = f'./thumbs/post_{thumb_idx+1:02d}.jpg'
            line = re.sub(r'thumb:\s*"https://[^"]*"', f'thumb: "{new_thumb}"', line)
            thumb_idx += 1
        new_lines.append(line)
    
    new_content = '\n'.join(new_lines)
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return thumb_idx


def process_talent(talent):
    html_path = os.path.join(REPO, talent, 'index.html')
    thumbs_dir = os.path.join(REPO, talent, 'thumbs')
    os.makedirs(thumbs_dir, exist_ok=True)
    
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    post_urls = extract_post_urls(content)
    print(f"\n=== {talent}: {len(post_urls)} posts found ===")
    
    success_count = 0
    
    for i, post_url in enumerate(post_urls, 1):
        fname = f"post_{i:02d}.jpg"
        fpath = os.path.join(thumbs_dir, fname)
        
        print(f"  [{i}] {post_url}")
        
        og_url = get_og_image(post_url)
        if not og_url:
            print(f"       SKIP: could not get og:image")
            time.sleep(1)
            continue
        
        size = download_image(og_url, fpath)
        if size > 0:
            print(f"       OK -> {fname} ({size} bytes)")
            success_count += 1
        else:
            print(f"       FAIL: download failed")
        
        time.sleep(1.5)
    
    if success_count > 0:
        replaced = update_html_thumbs(html_path, success_count)
        print(f"  HTML updated: {replaced} thumbs replaced")
    
    return success_count, len(post_urls)


if __name__ == "__main__":
    print("GVA メディアキット サムネイル更新開始")
    print(f"Repo: {REPO}")
    
    results = {}
    for talent in TALENTS:
        try:
            ok, total = process_talent(talent)
            results[talent] = (ok, total)
        except Exception as e:
            print(f"\n=== {talent}: ERROR: {e} ===")
            results[talent] = (0, 0)
    
    print("\n\n=== 完了レポート ===")
    for talent, (ok, total) in results.items():
        status = "OK" if ok == total and total > 0 else "PARTIAL" if ok > 0 else "FAIL"
        print(f"{status} {talent}: {ok}/{total}")
