#!/usr/bin/env python3
"""メディアキットの表示値と集計。フォロワーの取得元と表示アカウントは別。"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCES_PATH = Path(__file__).with_name("follower_sources.json")
PROVENANCE_PATH = Path(__file__).with_name("count_provenance.json")

TALENTS = ["kanna", "mayu", "miu", "momoka", "nana", "oto", "ririka", "sae", "saki", "yui"]

# 計測日を付けられなかったページに残っている、既存の表示文言。
EXISTING_KIT_LABEL = "Media Kit 2026.09"

MOMOKA_IG_SOURCE = "https://www.instagram.com/momoo_ka_"
MOMOKA_INDEX_HANDLE = "@moo_mo_k"
MOMOKA_DETAIL_HANDLE = "@momoo_ka_"
MOMOKA_DETAIL_URL = "https://instagram.com/momoo_ka_"

PLATFORM_FIELD = {
    "instagram": "followers",
    "tiktok": "followers",
    "youtube": "subscribers",
}


def format_count(n):
    return f"{int(n):,}"


def parse_count(text):
    return int(str(text).replace(",", "").replace("+", "").strip())


def floor_plus(n):
    """一覧と Total Reach の既存表記。千人未満を切り捨てて '+' を付ける。"""
    floored = (int(n) // 1000) * 1000
    return f"{floored:,}+"


def kit_label(as_of_dates):
    """表示中の全プラットフォームのうち、いちばん古い日付の年月。"""
    if not as_of_dates:
        raise ValueError("as_of_dates is empty")
    oldest = min(as_of_dates)
    year, month, _day = oldest.split("-")
    return f"Media Kit {year}.{month}"


def load_sources(path=SOURCES_PATH):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("follower_sources.json must be an object")
    return data


def instagram_username(profile_url):
    path = re.sub(r"/+$", "", profile_url.split("?")[0].split("#")[0])
    username = path.rsplit("/", 1)[-1]
    if not re.fullmatch(r"[A-Za-z0-9._]+", username or ""):
        raise ValueError(f"invalid instagram username in {profile_url}")
    return username


def resolve_instagram_source(talent, display_url, sources=None):
    """表示URLではなく、フォロワー取得に使うプロフィールURL。"""
    sources = load_sources() if sources is None else sources
    override = (sources.get(talent) or {}).get("instagram")
    if override:
        return override
    return display_url


def _platform_block(html, platform):
    match = re.search(rf"({platform}:\s*\{{)(.*?)(\n\s*\}})", html, re.S)
    if not match:
        return None
    return match


def parse_talent_html(html):
    """詳細ページから表示アカウントと数値を読む。price や handle は変更しない。"""
    result = {"platforms": {}, "handles": {}, "urls": {}}
    for platform, field in PLATFORM_FIELD.items():
        block = _platform_block(html, platform)
        if not block:
            continue
        body = block.group(2)
        handle = re.search(r'handle:\s*"([^"]+)"', body)
        url = re.search(r'url:\s*"([^"]+)"', body)
        count = re.search(rf'{field}:\s*"([^"]+)"', body)
        if not count:
            raise ValueError(f"missing {platform}.{field}")
        result["platforms"][platform] = parse_count(count.group(1))
        result["handles"][platform] = handle.group(1) if handle else None
        result["urls"][platform] = url.group(1) if url else None
    total = re.search(r'totalFollowers:\s*"([^"]+)"', html)
    result["totalFollowers"] = total.group(1) if total else None
    nav = re.search(r'<div class="nav-date"[^>]*>[^<]*</div>', html)
    result["nav"] = nav.group(0) if nav else None
    result["display_lines"] = display_lines(html)
    return result


def display_lines(html):
    """画面に出るアカウント・料金の行。数値更新で変わってはいけない。"""
    kept = []
    for line in html.splitlines():
        if re.search(r'\bhandle:\s*"', line) or re.search(r'\burl:\s*"', line) or re.search(r'\bprice:\s*"', line):
            kept.append(line.strip())
    return kept


def parse_index(html):
    cards = []
    pattern = re.compile(
        r'name:\s*"(?P<name>[^"]+)".*?handle:\s*"(?P<handle>[^"]+)".*?'
        r'ig:\s*"(?P<ig>[^"]+)".*?total:\s*"(?P<total>[^"]+)".*?url:\s*"(?P<url>\./[^"]+/)"',
        re.S,
    )
    for match in pattern.finditer(html):
        cards.append(match.groupdict())
    return cards


def derived_total(platforms):
    if not platforms:
        raise ValueError("no platforms")
    return floor_plus(sum(platforms.values()))


def replace_platform_count(html, platform, new_count):
    field = PLATFORM_FIELD[platform]
    match = _platform_block(html, platform)
    if not match:
        raise ValueError(f"missing {platform} block")
    body = match.group(2)
    new_body, count = re.subn(
        rf'({field}:\s*")[^"]+(")',
        rf"\g<1>{format_count(new_count)}\2",
        body,
        count=1,
    )
    if count != 1:
        raise ValueError(f"could not replace {platform}.{field}")
    return html[: match.start()] + match.group(1) + new_body + match.group(3) + html[match.end() :]


def replace_total(html, total_text):
    new_html, count = re.subn(
        r'(totalFollowers:\s*")[^"]+(")',
        rf"\g<1>{total_text}\2",
        html,
        count=1,
    )
    if count != 1:
        raise ValueError("could not replace totalFollowers")
    return new_html


def nav_label(nav_html):
    match = re.search(r'<div class="nav-date" id="nav-date"[^>]*>([^<]*)</div>', nav_html or "")
    return match.group(1) if match else None


def render_nav_date(existing_label, platforms, measured_as_ofs):
    """実測できた欄だけ日付属性を付ける。未計測が残るページの表示月は変えない。"""
    ordered = [name for name in ("instagram", "tiktok", "youtube") if name in measured_as_ofs]
    attrs = " ".join(f'data-{name}-as-of="{measured_as_ofs[name]}"' for name in ordered)
    complete = set(platforms) <= set(measured_as_ofs)
    label = kit_label([measured_as_ofs[name] for name in platforms]) if complete else existing_label
    attr_space = f" {attrs}" if attrs else ""
    return f'<div class="nav-date" id="nav-date"{attr_space}>{label}</div>'


def replace_nav_date(html, platforms, measured_as_ofs):
    if not measured_as_ofs:
        return html
    existing = nav_label(html)
    if not existing:
        raise ValueError("missing nav-date")
    new_html, count = re.subn(
        r'<div class="nav-date" id="nav-date"[^>]*>[^<]*</div>',
        render_nav_date(existing, platforms, measured_as_ofs),
        html,
        count=1,
    )
    if count != 1:
        raise ValueError("could not replace nav-date")
    return new_html


def apply_detail_counts(html, counts, measured_as_ofs):
    """数値と、実測できた欄の日付だけを書き換える。handle / url / price は触らない。"""
    updated = html
    for platform, value in counts.items():
        updated = replace_platform_count(updated, platform, value)
    updated = replace_total(updated, derived_total(counts))
    updated = replace_nav_date(updated, counts, measured_as_ofs)
    before = display_lines(html)
    after = display_lines(updated)
    if before != after:
        raise RuntimeError("display account or price lines changed")
    return updated


def update_index_card(html, slug, ig_plus, total_plus):
    pattern = re.compile(r'(ig:\s*")[^"]+("\s*,\s*total:\s*")[^"]+(")')
    for match in pattern.finditer(html):
        window = html[match.end() : match.end() + 220]
        if f"./{slug}/" not in window:
            continue
        replacement = f"{match.group(1)}{ig_plus}{match.group(2)}{total_plus}{match.group(3)}"
        return html[: match.start()] + replacement + html[match.end() :]
    raise ValueError(f"index card not found for {slug}")


def sync_index(html, talent_counts):
    updated = html
    before = [(card["name"], card["handle"], card["url"]) for card in parse_index(html)]
    for slug, counts in talent_counts.items():
        updated = update_index_card(
            updated,
            slug,
            floor_plus(counts["instagram"]),
            derived_total(counts),
        )
    after = [(card["name"], card["handle"], card["url"]) for card in parse_index(updated)]
    if before != after:
        raise RuntimeError("index display identity changed")
    return updated


def parse_instagram_embed_followers(html, username):
    """embed HTML のうち、指定ユーザー名に隣接した edge_followed_by だけを採用する。"""
    patterns = [
        rf'\\"username\\":\\"{re.escape(username)}\\".{{0,400}}?edge_followed_by\\":\{{\\"count\\":(\d+)',
        rf'"username":"{re.escape(username)}".{{0,400}}?"edge_followed_by":\{{"count":(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return int(match.group(1))
    return None


def parse_tiktok_followers(html, username):
    """そのユーザーの statsV2.followerCount だけ。丸められた stats 値は使わない。"""
    precise = re.search(
        rf'"uniqueId":"{re.escape(username)}".{{0,40000}}?"statsV2":\{{"followerCount":"(\d+)"',
        html,
    )
    if precise:
        return int(precise.group(1))
    return None


def parse_youtube_exact_subscribers(html, handle):
    """整数の subscriberCount だけを採用する。『1.12万人』のような丸め表示は捨てる。"""
    token = re.escape(handle.lstrip("@"))
    patterns = [
        rf'{token}.{{0,600}}?"subscriberCount":"(\d+)"',
        rf'{token}.{{0,600}}?"subscriberCount":(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return int(match.group(1))
    return None


def parse_youtube_public_rounded(html, handle):
    """公開ページに出ている丸め表記。整数へ換算しない。"""
    token = re.escape(handle.lstrip("@"))
    match = re.search(rf"{token}.{{0,160}}?([0-9]+(?:\.[0-9]+)?万人)", html)
    return match.group(1) if match else None


def nav_as_ofs(nav_html):
    return dict(re.findall(r'data-([a-z]+)-as-of="(\d{4}-\d{2}-\d{2})"', nav_html or ""))


def consistency_errors(root=REPO, sources=None, provenance=None):
    """一覧・詳細・日付属性・桃佳の取得元が矛盾していないか。"""
    errors = []
    if provenance is None and PROVENANCE_PATH.exists():
        provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    sources = load_sources() if sources is None else sources
    momoka_source = (sources.get("momoka") or {}).get("instagram")
    if momoka_source != MOMOKA_IG_SOURCE:
        errors.append(f"momoka instagram source must be {MOMOKA_IG_SOURCE}, got {momoka_source}")

    index_html = (Path(root) / "index.html").read_text(encoding="utf-8")
    cards = {card["url"]: card for card in parse_index(index_html)}
    if cards.get("./momoka/", {}).get("handle") != MOMOKA_INDEX_HANDLE:
        errors.append("index Momoka handle changed")

    for talent in TALENTS:
        html = (Path(root) / talent / "index.html").read_text(encoding="utf-8")
        parsed = parse_talent_html(html)
        if MOMOKA_IG_SOURCE in html:
            errors.append(f"{talent}: follower source URL was copied into the page")
        expected_total = derived_total(parsed["platforms"])
        if parsed["totalFollowers"] != expected_total:
            errors.append(f"{talent}: totalFollowers {parsed['totalFollowers']} != {expected_total}")
        card = cards.get(f"./{talent}/")
        if not card:
            errors.append(f"{talent}: missing index card")
            continue
        expected_ig = floor_plus(parsed["platforms"]["instagram"])
        if card["ig"] != expected_ig:
            errors.append(f"{talent}: index ig {card['ig']} != {expected_ig}")
        if card["total"] != expected_total:
            errors.append(f"{talent}: index total {card['total']} != {expected_total}")
        as_ofs = nav_as_ofs(parsed["nav"])
        label = nav_label(parsed["nav"])
        if provenance:
            records = provenance.get("talents", {}).get(talent, {})
            retrieved_day = str(provenance.get("retrieved_at", ""))[:10]
            gaps = [name for name, entry in records.items() if entry.get("status") != "updated"]
            for platform, entry in records.items():
                if entry.get("status") == "updated":
                    if as_ofs.get(platform) != retrieved_day:
                        errors.append(f"{talent}: {platform} as-of is not the retrieval day")
                    if parsed["platforms"].get(platform) != entry.get("count"):
                        errors.append(f"{talent}: {platform} count drifted from provenance")
                elif platform in as_ofs:
                    errors.append(f"{talent}: estimated as-of on unmeasured {platform}")
            if records and not gaps:
                if kit_label([retrieved_day]) != label:
                    errors.append(f"{talent}: full refresh label {label}")
            elif records and gaps and label != EXISTING_KIT_LABEL:
                errors.append(f"{talent}: incomplete refresh relabeled to {label}")

    momoka_html = (Path(root) / "momoka" / "index.html").read_text(encoding="utf-8")
    momoka = parse_talent_html(momoka_html)
    if momoka["handles"].get("instagram") != MOMOKA_DETAIL_HANDLE:
        errors.append("momoka detail instagram handle changed")
    if momoka["urls"].get("instagram") != MOMOKA_DETAIL_URL:
        errors.append("momoka detail instagram url changed")

    if provenance:
        recorded = provenance.get("talents", {}).get("momoka", {}).get("instagram", {})
        if recorded.get("source") != MOMOKA_IG_SOURCE:
            errors.append("provenance momoka source drifted")
        if recorded.get("status") == "updated":
            if recorded.get("count") != momoka["platforms"]["instagram"]:
                errors.append("provenance momoka count does not match the page")
            if instagram_username(recorded.get("source", "")) != "momoo_ka_":
                errors.append("provenance username is not momoo_ka_")
    return errors
