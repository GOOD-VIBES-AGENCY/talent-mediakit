#!/usr/bin/env python3
"""
GVA メディアキット 週次自動更新スクリプト（GitHub Actions用）
Instagram投稿URLからog:imageを取得してthumbsに保存し、HTMLの相対パスを維持する
"""
import re
import os
import sys
import time
import urllib.request
import urllib.error
import html as html_module
import json
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TALENTS = ["kanna", "mayu", "miu", "momoka", "nana", "oto", "ririka", "sae", "saki", "yui"]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
}

IG_GRAPHQL_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
    'X-IG-App-ID': '936619743392459',
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'application/json',
}


def get_og_image(post_url, retries=2):
    """Instagram投稿URLからog:imageを取得"""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(post_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                content = resp.read().decode('utf-8', errors='ignore')
            match = re.search(r'og:image"\s+content="([^"]+)"', content)
            if match:
                return html_module.unescape(match.group(1))
            return None
        except Exception as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
            else:
                print(f"  ERROR: {post_url}: {e}", file=sys.stderr)
                return None


def download_image(url, filepath, retries=2):
    """画像をダウンロード"""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={**HEADERS, 'Referer': 'https://www.instagram.com/'})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            if len(data) < 500:
                raise ValueError(f"Too small: {len(data)} bytes")
            with open(filepath, 'wb') as f:
                f.write(data)
            return len(data)
        except Exception as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
            else:
                print(f"  ERROR download: {e}", file=sys.stderr)
                return 0


def extract_post_urls(html_content):
    """HTMLからInstagram投稿URLを抽出"""
    pattern = r'url:\s*"(https://www\.instagram\.com/(?:reel|p)/[^/"]+/?)"'
    return re.findall(pattern, html_content)


def update_html_thumbs(html_path, count):
    """HTMLのthumb CDN URLを相対パスに変更"""
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
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
    return thumb_idx


def get_nana_posts_from_api():
    """nana(@hino.nana11)の最新投稿をInstagram APIから取得"""
    try:
        req = urllib.request.Request(
            "https://www.instagram.com/api/v1/users/web_profile_info/?username=hino.nana11",
            headers=IG_GRAPHQL_HEADERS
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        media = data['data']['user']['edge_owner_to_timeline_media']['edges']
        posts = []
        for m in media[:6]:
            node = m['node']
            sc = node.get('shortcode', '')
            type_map = {'GraphVideo': 'REEL', 'GraphImage': 'IMAGE', 'GraphSidecar': 'CAROUSEL'}
            ptype = type_map.get(node.get('__typename', ''), 'IMAGE')
            likes = node.get('edge_media_preview_like', {}).get('count', 0)
            comments = node.get('edge_media_to_comment', {}).get('count', 0)
            posts.append((ptype, likes, comments, f"https://www.instagram.com/p/{sc}/"))
        return posts
    except Exception as e:
        print(f"  WARNING: nana API error: {e}", file=sys.stderr)
        return []


def process_talent(talent):
    html_path = os.path.join(REPO, talent, 'index.html')
    thumbs_dir = os.path.join(REPO, talent, 'thumbs')
    os.makedirs(thumbs_dir, exist_ok=True)
    
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # thumbが相対パスなら既に変換済み → thumbsの画像を更新するだけ
    has_relative = bool(re.search(r'thumb:\s*"\./thumbs/', content))
    # thumbがCDN URLなら変換も必要
    has_cdn = bool(re.search(r'thumb:\s*"https://scontent', content))
    
    post_urls = extract_post_urls(content)
    print(f"\n=== {talent}: {len(post_urls)} posts ===")
    
    if not post_urls and talent == 'nana':
        return process_nana_new(html_path, thumbs_dir, content)
    
    if not post_urls:
        print(f"  WARNING: no post URLs")
        return 0, 0
    
    success = 0
    for i, url in enumerate(post_urls, 1):
        og_url = get_og_image(url)
        if og_url:
            fpath = os.path.join(thumbs_dir, f"post_{i:02d}.jpg")
            size = download_image(og_url, fpath)
            if size > 0:
                print(f"  [{i}] OK -> post_{i:02d}.jpg ({size:,}b)")
                success += 1
            else:
                print(f"  [{i}] FAIL: download")
        else:
            print(f"  [{i}] SKIP: no og:image")
        time.sleep(1.5)
    
    if has_cdn and success > 0:
        replaced = update_html_thumbs(html_path, success)
        print(f"  HTML: {replaced} CDN URLs -> relative paths")
    
    return success, len(post_urls)


def process_nana_new(html_path, thumbs_dir, content):
    """nanaのHTML更新（投稿URLなし → APIから取得）"""
    print("  nana: APIから取得中...")
    posts = get_nana_posts_from_api()
    if not posts:
        return 0, 0
    
    success = 0
    entries = []
    for i, (ptype, likes, comments, url) in enumerate(posts, 1):
        og_url = get_og_image(url)
        if og_url:
            fpath = os.path.join(thumbs_dir, f"post_{i:02d}.jpg")
            size = download_image(og_url, fpath)
            if size > 0:
                print(f"  [{i}] OK -> post_{i:02d}.jpg ({size:,}b)")
                entries.append(f'      {{ type: "{ptype}", thumb: "./thumbs/post_{i:02d}.jpg", likes: {likes}, comments: {comments}, url: "{url}" }}')
                success += 1
        time.sleep(1.5)
    
    if entries:
        new_content = content.replace('recentPosts: []', f'recentPosts: [\n' + ',\n'.join(entries) + '\n    ]')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"  nana HTML: {success} posts added")
    
    return success, len(posts)


if __name__ == "__main__":
    start = datetime.now()
    print(f"GVA メディアキット 週次更新 - {start.strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    for talent in TALENTS:
        try:
            ok, total = process_talent(talent)
            results[talent] = (ok, total)
        except Exception as e:
            print(f"\n=== {talent}: ERROR: {e} ===")
            import traceback; traceback.print_exc()
            results[talent] = (0, 0)
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*40}")
    print(f"完了 ({elapsed:.0f}秒)")
    total_ok = sum(ok for ok, _ in results.values())
    total_all = sum(t for _, t in results.values())
    for talent, (ok, total) in results.items():
        s = "✅" if ok == total and total > 0 else "⚠️" if ok > 0 else "❌"
        print(f"{s} {talent}: {ok}/{total}")
    print(f"合計: {total_ok}/{total_all}")
    if total_ok == 0:
        sys.exit(1)
