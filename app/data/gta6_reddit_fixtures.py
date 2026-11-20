"""Realistic Nov 2026 GTA VI launch-week Reddit fixtures (synthetic data only).

All usernames, emails, and IPs below are purely synthetic RFC-2606 / RFC-5737
test placeholders included deliberately to verify active PII redaction across
tool outputs, structured logs, and persistent memory pipelines.
"""

from __future__ import annotations

from typing import Any

GTA6_LAUNCH_FIXTURES: dict[str, list[dict[str, Any]]] = {
    "OLED_Gaming": [
        {
            "thread_id": "t3_oled_gta6_001",
            "subreddit": "OLED_Gaming",
            "title": "GTA VI night-time neon lighting in Vice City is the biggest reason to upgrade to an OLED monitor",
            "permalink": "/r/OLED_Gaming/comments/oled_gta6_001/gta_vi_night_time_neon_lighting/",
            "upvotes": 4820,
            "comment_count": 612,
            "comments_per_hour": 148.5,
            "sentiment_score": 0.88,
            "top_excerpts": [
                "Just upgraded to a 4K 240Hz QD-OLED before launch—Driving down Ocean Beach at midnight looks unreal.",
                "Posted by u/neon_gamer_99: anyone have Black Friday OLED TV deals under 1500 for PS5 Pro + GTA6?",
            ],
            "tags": ["oled_displays", "hdr", "purchase_intent", "vice_city", "positive"],
        },
        {
            "thread_id": "t3_oled_gta6_002",
            "subreddit": "OLED_Gaming",
            "title": "Best HDR calibration settings for GTA VI on LG C4 and Samsung S90D OLEDs",
            "permalink": "/r/OLED_Gaming/comments/oled_gta6_002/best_hdr_calibration_settings/",
            "upvotes": 2310,
            "comment_count": 389,
            "comments_per_hour": 92.0,
            "sentiment_score": 0.81,
            "top_excerpts": [
                "Finally convinced me to buy a 65-inch OLED for the living room this weekend.",
                "Contact u/hdr_calibrator at hdr.tips@example.com for the test pattern chart.",
            ],
            "tags": ["oled_displays", "hdr", "purchase_intent", "tv_upgrade"],
        },
    ],
    "4kTV": [
        {
            "thread_id": "t3_4ktv_gta6_001",
            "subreddit": "4kTV",
            "title": "Buying a new 65-inch TV specifically for GTA VI launch weekend — OLED vs Mini-LED?",
            "permalink": "/r/4kTV/comments/4ktv_gta6_001/buying_65_inch_tv_for_gta_vi/",
            "upvotes": 1740,
            "comment_count": 445,
            "comments_per_hour": 110.2,
            "sentiment_score": 0.76,
            "top_excerpts": [
                "GTA VI dark interiors and Vice City reflections make true blacks worth every penny.",
                "My wife approved the TV upgrade after seeing the launch trailer in HDR.",
            ],
            "tags": ["oled_displays", "purchase_intent", "buying_guide", "positive"],
        },
    ],
    "PS5": [
        {
            "thread_id": "t3_ps5_gta6_001",
            "subreddit": "PS5",
            "title": "GTA VI is 212 GB after Day-1 patch 01.002.001 — which 2TB NVMe SSD should I buy today?",
            "permalink": "/r/PS5/comments/ps5_gta6_001/gta_vi_212gb_nvme_ssd_recommendations/",
            "upvotes": 6190,
            "comment_count": 1120,
            "comments_per_hour": 245.0,
            "sentiment_score": 0.62,
            "top_excerpts": [
                "Had to uninstall four games just to fit the 212 GB install. Ordering a 2TB heatsink NVMe SSD tonight.",
                "Which Gen4 SSD has the fastest load times in Leonida? Asking for u/ps5_storage_hunter.",
            ],
            "tags": ["ssd_storage", "console_hardware", "purchase_intent", "212gb_install"],
        },
        {
            "thread_id": "t3_ps5_gta6_002",
            "subreddit": "PS5",
            "title": "DualSense adaptive triggers and 3D Tempest Audio headset impressions in GTA VI",
            "permalink": "/r/PS5/comments/ps5_gta6_002/dualsense_and_headset_impressions/",
            "upvotes": 3180,
            "comment_count": 498,
            "comments_per_hour": 104.0,
            "sentiment_score": 0.84,
            "top_excerpts": [
                "Spatial audio in Vice City traffic is insane—looking for a wireless low-latency headset upgrade.",
                "Trigger resistance on older muscle cars feels genuinely next-gen.",
            ],
            "tags": ["gaming_peripherals", "console_hardware", "purchase_intent", "positive"],
        },
    ],
    "xbox": [
        {
            "thread_id": "t3_xbox_gta6_001",
            "subreddit": "xbox",
            "title": "Xbox Series S crash loop after Patch 01.002.001 — refund wave megathread",
            "permalink": "/r/xbox/comments/xbox_gta6_001/xbox_series_s_crash_refund_megathread/",
            "upvotes": 5420,
            "comment_count": 1890,
            "comments_per_hour": 380.4,
            "sentiment_score": -0.74,
            "top_excerpts": [
                "Three hard crashes in Port Gellhorn on Series S. Requesting a digital refund immediately.",
                "Support ticket from u/series_s_owner (phone 555-019-2834, IP 198.51.100.42) still unanswered.",
                "Wait—seriously considering buying a Series X or expansion card because storage + crashes are brutal.",
            ],
            "tags": [
                "brand_safety_refund_wave",
                "brand_safety_crash_outrage",
                "ssd_storage",
                "console_hardware",
                "negative",
            ],
        },
    ],
    "GTA6": [
        {
            "thread_id": "t3_gta6_001",
            "subreddit": "GTA6",
            "title": "GTA VI Launch Day Bugs, Glitches & Download Queue Megathread",
            "permalink": "/r/GTA6/comments/gta6_001/launch_day_bugs_glitches_megathread/",
            "upvotes": 14800,
            "comment_count": 6420,
            "comments_per_hour": 890.0,
            "sentiment_score": -0.35,
            "top_excerpts": [
                "Authentication queue stalled for 45 minutes and mission 4 soft-locked during the getaway.",
                "Stocked up on energy drinks and snacks for a 36-hour Leonida marathon once this 212GB patch finishes!",
            ],
            "tags": [
                "brand_safety_crash_outrage",
                "cpg_beverages",
                "launch_megathread",
                "mixed",
            ],
        },
        {
            "thread_id": "t3_gta6_002",
            "subreddit": "GTA6",
            "title": "Heated debate: Driving physics & Jason/Lucia story thread [EXPLICIT / TOXIC FLAMEWAR]",
            "permalink": "/r/GTA6/comments/gta6_002/driving_physics_heated_debate/",
            "upvotes": 2910,
            "comment_count": 2150,
            "comments_per_hour": 412.0,
            "sentiment_score": -0.68,
            "top_excerpts": [
                "Mods had to enable slow mode due to severe profanity, personal attacks, and harassment in replies.",
                "Multiple users spamming boycott threats and hostile slurs over vehicle handling changes.",
            ],
            "tags": [
                "brand_safety_toxicity",
                "brand_safety_profanity",
                "boycott_chatter",
                "negative",
            ],
        },
        {
            "thread_id": "t3_gta6_003",
            "subreddit": "GTA6",
            "title": "Launch weekend battle-station setups: snacks, energy drinks, and zero sleep in Vice City",
            "permalink": "/r/GTA6/comments/gta6_003/launch_weekend_battlestation_setups/",
            "upvotes": 8340,
            "comment_count": 1240,
            "comments_per_hour": 265.0,
            "sentiment_score": 0.91,
            "top_excerpts": [
                "Got two cases of zero-sugar energy drinks, headset charged, OLED calibrated—see you in Leonida!",
                "Took Friday off work; marathon gaming snacks are fully stocked.",
            ],
            "tags": ["cpg_beverages", "gaming_peripherals", "oled_displays", "purchase_intent", "positive"],
        },
    ],
    "gaming": [
        {
            "thread_id": "t3_gaming_gta6_001",
            "subreddit": "gaming",
            "title": "GTA VI hits 99 Metascore — Digital Foundry calls Vice City lighting a generational leap",
            "permalink": "/r/gaming/comments/gaming_gta6_001/gta_vi_99_metascore_digital_foundry/",
            "upvotes": 32400,
            "comment_count": 4810,
            "comments_per_hour": 620.0,
            "sentiment_score": 0.87,
            "top_excerpts": [
                "Never bought a console mid-cycle before, but I am picking up a PS5 Pro + headset this afternoon.",
                "Grabbed snacks and energy drinks for the whole weekend—launch hype is unreal.",
            ],
            "tags": [
                "console_hardware",
                "gaming_peripherals",
                "cpg_beverages",
                "purchase_intent",
                "positive",
            ],
        },
    ],
    "buildapc": [
        {
            "thread_id": "t3_buildapc_gta6_001",
            "subreddit": "buildapc",
            "title": "No GTA VI PC date yet — buying a PS5 + 2TB NVMe SSD now or waiting for 2027?",
            "permalink": "/r/buildapc/comments/buildapc_gta6_001/no_pc_date_buying_console_or_wait/",
            "upvotes": 4120,
            "comment_count": 980,
            "comments_per_hour": 176.0,
            "sentiment_score": 0.12,
            "top_excerpts": [
                "Caved and bought a console + 2TB NVMe SSD because avoiding spoilers for a year is impossible.",
                "At least my 4K OLED monitor works great on console HDMI 2.1 in the meantime.",
            ],
            "tags": ["console_hardware", "ssd_storage", "oled_displays", "purchase_intent"],
        },
    ],
    "rockstar": [
        {
            "thread_id": "t3_rockstar_gta6_001",
            "subreddit": "rockstar",
            "title": "Official GTA VI Day-1 Patch Notes (01.002.001) & Known Issues Tracker",
            "permalink": "/r/rockstar/comments/rockstar_gta6_001/day_1_patch_notes_known_issues/",
            "upvotes": 5890,
            "comment_count": 870,
            "comments_per_hour": 160.0,
            "sentiment_score": 0.34,
            "top_excerpts": [
                "Glad Rockstar acknowledged the Series S memory crash and promised a hotfix within 48 hours.",
                "Download servers stabilized after midnight staggered rollout.",
            ],
            "tags": ["patch_notes", "brand_safety_crash_outrage", "neutral"],
        },
    ],
}
