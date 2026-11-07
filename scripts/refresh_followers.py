#!/usr/bin/env python3
"""公開ページと Instagram の公開埋め込みからフォロワー数を取り、一覧の合計へ反映する。

使わないもの:
- 未文書化のプロフィール API
- クローラを装う User-Agent や、拒否された取得元への迂回

表示中の handle / URL / 料金は書き換えない。
桃佳の Instagram は follower_sources.json の URL だけを見にいき、
一覧の @moo_mo_k にはしない。

取得できなかった欄は元の数値のまま、計測日も付けない。未取得があれば終了コード 1。
"""
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mediakit_lib as mk

HONEST_UA = "GOOD-VIBES-AGENCY-mediakit/1.0 (+https://goodvibesagency.tokyo/talent-mediakit/)"
HEADERS = {
    "User-Agent": HONEST_UA,
    "Accept": "text/html,application/json;q=0.9",
    "Accept-Language": "ja,en;q=0.8",
}


def now_jst():
    return datetime.now(ZoneInfo("Asia/Tokyo"))


def fetch_text(url):
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.status, response.geturl(), response.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as error:
        error.read()
        return error.code, getattr(error, "url", url), ""
    except Exception as error:
        return type(error).__name__, url, ""


def fetch_instagram_count(profile_url):
    """通常の公開プロフィールを先に見る。ログイン壁なら公式の公開埋め込みだけを使う。"""
    username = mk.instagram_username(profile_url)
    status, final, body = fetch_text(profile_url)
    login_walled = "accounts/login" in (final or "")
    profile_note = "login_redirect" if login_walled else f"status:{status}"
    if status == 200 and body and not login_walled:
        count = mk.parse_instagram_embed_followers(body, username)
        if count is not None:
            return count, "instagram_public_page", {"profile_page": profile_note}
    embed_url = f"https://www.instagram.com/{username}/embed/"
    embed_status, embed_final, embed_body = fetch_text(embed_url)
    embed_login = "accounts/login" in (embed_final or "")
    if embed_status == 200 and embed_body and not embed_login:
        count = mk.parse_instagram_embed_followers(embed_body, username)
        if count is not None:
            return count, "instagram_public_embed", {
                "profile_page": profile_note,
                "embed_url": embed_url,
            }
    return None, "unavailable", {
        "profile_page": profile_note,
        "embed_status": embed_status,
    }


def fetch_tiktok_count(profile_url):
    username = profile_url.rstrip("/").rsplit("/", 1)[-1].lstrip("@")
    if not username:
        return None, "missing-username", {}
    page = f"https://www.tiktok.com/@{username}"
    status, _final, body = fetch_text(page)
    if status == 200 and body:
        count = mk.parse_tiktok_followers(body, username)
        if count is not None:
            return count, "tiktok_public_page", {}
    return None, f"unavailable:{status}", {}


def fetch_youtube_count(profile_url):
    handle = profile_url.rstrip("/").rsplit("/", 1)[-1]
    if not handle.startswith("@"):
        handle = "@" + handle
    page = profile_url if profile_url.startswith("http") else f"https://www.youtube.com/{handle}"
    status, _final, body = fetch_text(page)
    if status == 200 and body:
        exact = mk.parse_youtube_exact_subscribers(body, handle)
        if exact is not None:
            return exact, "youtube_public_exact", {}
        rounded = mk.parse_youtube_public_rounded(body, handle)
        extra = {"public_rounded_label": rounded} if rounded else {}
        return None, "rounded-display-only", extra
    return None, f"unavailable:{status}", {}


FETCHERS = {
    "instagram": fetch_instagram_count,
    "tiktok": fetch_tiktok_count,
    "youtube": fetch_youtube_count,
}


def refresh(root=mk.REPO, write=False, sleep_seconds=0.4):
    sources = mk.load_sources()
    today = now_jst().date().isoformat()
    retrieved_at = now_jst().isoformat(timespec="seconds")
    provenance = {
        "retrieved_at": retrieved_at,
        "user_agent": HONEST_UA,
        "talents": {},
        "gaps": [],
    }
    talent_counts = {}
    wrote = []

    for talent in mk.TALENTS:
        path = root / talent / "index.html"
        original = path.read_text(encoding="utf-8")
        parsed = mk.parse_talent_html(original)
        counts = dict(parsed["platforms"])
        measured = {}
        talent_record = {}

        for platform in list(counts):
            if platform == "instagram":
                source = mk.resolve_instagram_source(talent, parsed["urls"]["instagram"], sources)
            else:
                source = parsed["urls"][platform]
            count, method, extra = FETCHERS[platform](source)
            entry = {"source": source, "method": method, **extra}
            if count is None:
                entry.update({
                    "status": "gap",
                    "displayed_count": counts[platform],
                })
                provenance["gaps"].append(f"{talent}.{platform}:{method}")
                print(f"GAP {talent} {platform} source={source} ({method})", file=sys.stderr)
            else:
                counts[platform] = count
                measured[platform] = today
                entry.update({"status": "updated", "count": count, "retrieved_on": today})
                print(f"OK  {talent} {platform} {count} source={source} method={method}")
            talent_record[platform] = entry
            time.sleep(sleep_seconds)

        updated = mk.apply_detail_counts(original, counts, measured)
        if updated != original:
            wrote.append(talent)
            if write:
                path.write_text(updated, encoding="utf-8")
        provenance["talents"][talent] = talent_record
        talent_counts[talent] = counts

    index_path = root / "index.html"
    index_html = index_path.read_text(encoding="utf-8")
    new_index = mk.sync_index(index_html, talent_counts)
    if new_index != index_html:
        wrote.append("index")
        if write:
            index_path.write_text(new_index, encoding="utf-8")

    if write:
        mk.PROVENANCE_PATH.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"updated_files={','.join(wrote) if wrote else '-'} gaps={len(provenance['gaps'])}")
    return provenance


def main(argv):
    write = "--write" in argv
    provenance = refresh(write=write)
    if provenance["gaps"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
