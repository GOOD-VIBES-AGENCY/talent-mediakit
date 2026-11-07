#!/usr/bin/env python3
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mediakit_lib as mk
import refresh_mediakit


DETAIL_FIXTURE = """
<script>
const TALENT = {
    handle:      "@moo_mo_k",
    sns: {
      instagram: {
        handle:    "@moo_mo_k",
        url:       "https://instagram.com/moo_mo_k",
        followers: "242,179",
        engRate:   "2.43%",
      },
      tiktok: {
        handle:    "@peach12299",
        url:       "https://tiktok.com/@peach12299",
        followers: "337,600",
      },
    },
    totalFollowers: "589,000+",
    pricing: [
      { type: "Instagram フィード投稿", price: "¥484,000〜", note: "1投稿" },
    ],
};
</script>
<div class="nav-date" id="nav-date">Media Kit 2026.09</div>
"""

INDEX_FIXTURE = """
    {
      name: "Momoka",   nameJa: "桃佳",      handle: "@moo_mo_k",
      label: "Beauty Creator",
      ig:  "242,000+",  total: "579,000+",
      photo: "./momoka/momoka.jpg",  url: "./momoka/"
    },
"""


class FormulaTests(unittest.TestCase):
    def test_floor_plus_matches_historical_index_rule(self):
        self.assertEqual(mk.floor_plus(242179), "242,000+")
        self.assertEqual(mk.floor_plus(242179 + 337600), "579,000+")
        self.assertEqual(mk.floor_plus(66989 + 47500 + 10800), "125,000+")
        self.assertEqual(mk.floor_plus(26027), "26,000+")

    def test_kit_label_uses_oldest_platform_date(self):
        self.assertEqual(mk.kit_label(["2026-11-07", "2026-09-28"]), "Media Kit 2026.09")
        self.assertEqual(mk.kit_label(["2026-11-07", "2026-11-07"]), "Media Kit 2026.11")


class SourceSeparationTests(unittest.TestCase):
    def test_momoka_source_file_is_exact_profile(self):
        sources = json.loads((ROOT / "scripts" / "follower_sources.json").read_text(encoding="utf-8"))
        self.assertEqual(sources["momoka"]["instagram"], "https://www.instagram.com/momoo_ka_")

    def test_override_beats_displayed_account(self):
        sources = {"momoka": {"instagram": mk.MOMOKA_IG_SOURCE}}
        resolved = mk.resolve_instagram_source(
            "momoka", "https://instagram.com/moo_mo_k", sources
        )
        self.assertEqual(resolved, "https://www.instagram.com/momoo_ka_")
        self.assertEqual(mk.instagram_username(resolved), "momoo_ka_")

    def test_other_talent_uses_displayed_url(self):
        sources = {"momoka": {"instagram": mk.MOMOKA_IG_SOURCE}}
        display = "https://instagram.com/hino.nana11"
        self.assertEqual(mk.resolve_instagram_source("nana", display, sources), display)

    def test_apply_updates_counts_without_touching_display_or_price(self):
        counts = {"instagram": 243866, "tiktok": 337600}
        updated = mk.apply_detail_counts(DETAIL_FIXTURE, counts, {"instagram": "2026-11-07"})
        self.assertIn('handle:    "@moo_mo_k"', updated)
        self.assertIn('url:       "https://instagram.com/moo_mo_k"', updated)
        self.assertIn('price: "¥484,000〜"', updated)
        self.assertNotIn("https://www.instagram.com/momoo_ka_", updated)
        self.assertIn('followers: "243,866"', updated)
        self.assertIn('followers: "337,600"', updated)
        self.assertIn('totalFollowers: "581,000+"', updated)
        self.assertIn("Media Kit 2026.09", updated)
        self.assertIn('data-instagram-as-of="2026-11-07"', updated)
        self.assertNotIn("data-tiktok-as-of", updated)
        self.assertNotIn("2026-09-15", updated)

    def test_label_changes_only_when_every_platform_was_measured(self):
        counts = {"instagram": 243866, "tiktok": 337600}
        updated = mk.apply_detail_counts(
            DETAIL_FIXTURE, counts, {"instagram": "2026-11-07", "tiktok": "2026-11-07"}
        )
        self.assertIn("Media Kit 2026.11", updated)
        self.assertIn('data-tiktok-as-of="2026-11-07"', updated)

    def test_index_handle_stays_while_counts_follow_detail(self):
        updated = mk.update_index_card(INDEX_FIXTURE, "momoka", "243,000+", "581,000+")
        self.assertIn('handle: "@moo_mo_k"', updated)
        self.assertIn('url: "./momoka/"', updated)
        self.assertIn('ig:  "243,000+"', updated)
        self.assertIn('total: "581,000+"', updated)


class ParserTests(unittest.TestCase):
    def test_embed_count_is_bound_to_username(self):
        decoy = '"username":"moo_mo_k","edge_followed_by":{"count":1}'
        real = '\\"username\\":\\"momoo_ka_\\",\\"edge_followed_by\\":{\\"count\\":243866}'
        self.assertEqual(mk.parse_instagram_embed_followers(decoy + real, "momoo_ka_"), 243866)
        self.assertIsNone(mk.parse_instagram_embed_followers(decoy, "momoo_ka_"))

    def test_plain_embed_json_also_binds_username(self):
        html = '"username":"momoo_ka_","edge_followed_by":{"count":243866}'
        self.assertEqual(mk.parse_instagram_embed_followers(html, "momoo_ka_"), 243866)

    def test_tiktok_uses_exact_stats_v2_and_ignores_rounded_stats(self):
        html = (
            '"uniqueId":"other","statsV2":{"followerCount":"1"}'
            '"uniqueId":"peach12299","nickname":"MOMOKA"'
            + ("x" * 50)
            + '"stats":{"followerCount":348700},"statsV2":{"followerCount":"348664"'
        )
        self.assertEqual(mk.parse_tiktok_followers(html, "peach12299"), 348664)
        rounded_only = '"uniqueId":"peach12299","stats":{"followerCount":348700}'
        self.assertIsNone(mk.parse_tiktok_followers(rounded_only, "peach12299"))

    def test_youtube_rounded_man_is_not_an_exact_count(self):
        html = "@hino.nana11 • チャンネル登録者数 1.12万人"
        self.assertIsNone(mk.parse_youtube_exact_subscribers(html, "@hino.nana11"))

    def test_youtube_exact_integer_near_handle_is_accepted(self):
        html = '@hino.nana11","subscriberCount":"11234"'
        self.assertEqual(mk.parse_youtube_exact_subscribers(html, "@hino.nana11"), 11234)


class AccessMethodTests(unittest.TestCase):
    def test_count_and_thumbnail_scripts_do_not_bypass_blocks(self):
        forbidden = ("web_profile_info", "Googlebot", "X-IG-App-ID")
        paths = [
            "scripts/refresh_followers.py",
            "scripts/refresh_mediakit.py",
            "scripts/download_thumbs.py",
            "scripts/mediakit_lib.py",
            "scripts/follower_sources.json",
        ]
        for relative in paths:
            text = (ROOT / relative).read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{relative} contains {token}")


class ThumbnailFailureTests(unittest.TestCase):
    def test_partial_thumbnail_refresh_is_a_failure(self):
        self.assertEqual(refresh_mediakit.exit_code_for_results({"mayu": (5, 6), "oto": (5, 6)}), 1)
        self.assertEqual(refresh_mediakit.exit_code_for_results({"nana": (0, 0)}), 1)
        self.assertEqual(refresh_mediakit.exit_code_for_results({"kanna": (6, 6)}), 0)


class RepoConsistencyTests(unittest.TestCase):
    def test_pages_match_derived_totals_and_momoka_display(self):
        errors = mk.consistency_errors(ROOT)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_display_accounts_and_prices_match_main(self):
        for path in ["index.html", *[f"{talent}/index.html" for talent in mk.TALENTS]]:
            current = (ROOT / path).read_text(encoding="utf-8")
            base = subprocess.check_output(
                ["git", "show", f"origin/main:{path}"], cwd=ROOT, text=True
            )
            self.assertEqual(
                mk.display_lines(current),
                mk.display_lines(base),
                path,
            )

    def test_momoka_provenance_used_the_override_source(self):
        provenance = json.loads((ROOT / "scripts" / "count_provenance.json").read_text(encoding="utf-8"))
        instagram = provenance["talents"]["momoka"]["instagram"]
        self.assertEqual(instagram["status"], "updated")
        self.assertEqual(instagram["source"], "https://www.instagram.com/momoo_ka_")
        self.assertNotIn("moo_mo_k", instagram["source"])
        youtube = provenance["talents"]["nana"]["youtube"]
        page = mk.parse_talent_html((ROOT / "nana" / "index.html").read_text(encoding="utf-8"))
        if youtube["status"] == "gap":
            self.assertEqual(page["platforms"]["youtube"], youtube["displayed_count"])
            rounded = youtube.get("public_rounded_label")
            if rounded:
                self.assertIn("万", rounded)
                self.assertNotIn(rounded, (ROOT / "nana" / "index.html").read_text(encoding="utf-8"))
        self.assertNotIn("web_profile_info", json.dumps(provenance))
        self.assertNotIn("Googlebot", json.dumps(provenance))


if __name__ == "__main__":
    unittest.main()
