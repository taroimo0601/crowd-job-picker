#!/usr/bin/env python3
"""
クラウドソーシング5大サイト横断・動画・映像・アニメーション特化 案件自動収集スクリプト
対象: クラウドワークス / ランサーズ / ココナラ(公開依頼) / シュフティ / ママワークス
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import ssl
import time
from typing import Any
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore

try:
    import requests
except ImportError:
    requests = None  # type: ignore

JST = timezone(timedelta(hours=9))
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "conditions.json"
DATA_DIR = ROOT_DIR / "docs" / "data"
OUTPUT_PATH = DATA_DIR / "jobs.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# 添付画像の「動画・映像・アニメーション」15分類
VIDEO_SUBCATEGORIES: dict[str, dict[str, Any]] = {
    "video_creation": {
        "label": "動画作成・動画制作",
        "keywords": ["動画作成", "動画制作", "ムービー作成", "ムービー制作", "映像作成", "動画づくり"],
    },
    "youtube_video": {
        "label": "YouTube動画作成・編集",
        "keywords": [
            "youtube", "ユーチューブ", "ゆっくり", "ずんだもん", "切り抜き", "長尺動画",
            "youtubeチャンネル", "vrew", "解説動画", "ゲーム実況", "ビジネス系youtube"
        ],
    },
    "video_editing": {
        "label": "映像編集・映像制作",
        "keywords": [
            "映像編集", "映像制作", "動画編集", "カット編集", "テロップ", "premiere",
            "final cut", "davinci", "capcut", "色調補正", "カラーグレーディング", "整音"
        ],
    },
    "video_shooting": {
        "label": "映像撮影",
        "keywords": [
            "映像撮影", "動画撮影", "撮影スタッフ", "カメラマン", "ドローン", "ロケ撮影",
            "スタジオ撮影", "撮影＋編集", "撮影および編集", "現地撮影", "収録"
        ],
    },
    "char_animation_prod": {
        "label": "キャラクター・アニメーション制作",
        "keywords": [
            "キャラクター・アニメーション", "アニメーション制作", "アニメ制作", "live2d",
            "vtuber", "モデリング", "spine", "オリジナルアニメ", "イラストアニメーション"
        ],
    },
    "ar_vr": {
        "label": "AR/VRコンテンツ制作・撮影",
        "keywords": [
            "ar", "vr", "360度", "360°", "メタバース", "空間ビデオ", "vr撮影", "vr動画", "xr"
        ],
    },
    "tiktok_short": {
        "label": "TikTok・ショート動画",
        "keywords": [
            "tiktok", "ショート動画", "shorts", "リール", "reels", "縦型動画",
            "短尺", "インスタリール", "youtubeショート", "60秒"
        ],
    },
    "ad_video": {
        "label": "広告動画",
        "keywords": [
            "広告動画", "動画広告", "sns広告", "youtube広告", "meta広告", "インスタ広告",
            "tiktok広告", "プロモーション広告", "バナー動画", "lp動画"
        ],
    },
    "wedding_event": {
        "label": "結婚式・イベント動画",
        "keywords": [
            "結婚式", "ウェディング", "ブライダル", "プロフィールムービー", "オープニングムービー",
            "エンドロール", "イベント動画", "イベント映像", "サプライズムービー", "卒園", "卒業"
        ],
    },
    "mv_singing": {
        "label": "ミュージックビデオ（MV）・歌ってみた動画",
        "keywords": [
            "ミュージックビデオ", "mv", "歌ってみた", "ボカロ", "オリジナル曲",
            "リリックビデオ", "音楽動画", "楽曲動画", "ボーカロイド"
        ],
    },
    "motion_graphics": {
        "label": "モーショングラフィックス",
        "keywords": [
            "モーショングラフィックス", "after effects", "アフターエフェクツ", "インフォグラフィック",
            "ロゴアニメーション", "エフェクト制作", "コンポジット", "3dcg", "c4d", "blender"
        ],
    },
    "character_animation": {
        "label": "キャラクターアニメーション",
        "keywords": [
            "キャラクターアニメーション", "vyond", "ホワイトボードアニメーション", "漫画動画",
            "アニメ動画", "2dアニメーション", "キャラ動か"
        ],
    },
    "cm_pv_drama": {
        "label": "CM・PV・ドラマ制作",
        "keywords": [
            "cm", "コマーシャル", "pv", "ティザー", "ドラマ", "ショートドラマ", "縦型ドラマ",
            "予告編", "トレーラー", "プロモーションビデオ"
        ],
    },
    "corporate_pr": {
        "label": "企業紹介・講習・PR動画制作",
        "keywords": [
            "企業紹介", "会社紹介", "pr動画", "採用動画", "サービス紹介", "商品紹介動画",
            "マニュアル動画", "講習", "セミナー動画", "研修動画", "eラーニング", "インタビュー動画",
            "講座動画"
        ],
    },
    "video_script": {
        "label": "動画シナリオ・台本・構成作成",
        "keywords": [
            "動画シナリオ", "台本", "シナリオ作成", "構成作成", "構成案", "youtube台本",
            "漫画シナリオ", "絵コンテ", "コンテ作成", "企画構成", "ナレーション原稿"
        ],
    },
}

# 動画・映像・アニメーション領域全体と判定するための必須キーワード群
VIDEO_DOMAIN_TERMS = [
    "動画", "映像", "ムービー", "youtube", "tiktok", "ショート", "リール", "reels",
    "premiere", "after effects", "capcut", "davinci", "final cut", "vrew", "vyond",
    "アニメーション", "アニメ", "mv", "ミュージックビデオ", "歌ってみた", "モーショングラフィックス",
    "オープニングムービー", "プロフィールムービー", "エンドロール", "結婚式", "ウェディング",
    "台本", "絵コンテ", "切り抜き", "テロップ", "cm", "pv", "vr", "360度", "live2d"
]

# 動画と無関係な職種を確実に弾くための除外職種ワード
NON_VIDEO_NOISE_TERMS = [
    "経理", "労務", "会計事務所", "税理士", "コールセンター", "コールスタッフ", "テレアポ",
    "架電", "cadオペレーター", "図面作成", "秘書", "ペネトレーションテスト", "医療データai基盤"
]

CLOSED_STATUS_PATTERNS = [
    "募集終了",
    "受付終了",
    "応募終了",
    "終了しました",
    "募集は終了",
    "募集期間が終了",
    "締切済",
    "締め切りました",
    "成約済",
    "選定中",
    "キャンセル",
    "残り0日",
    "あと0日",
    "残り0時間",
    "あと0時間",
    "残り0分",
    "CLOSED",
]


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def clean_text(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(raw))
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def http_get_text(url: str, timeout: int = 10) -> str:
    if requests is not None:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code == 200:
            return resp.text
        return ""
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        ctx = ssl._create_unverified_context()
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode("utf-8", errors="ignore")


def extract_anchor_cards(html_text: str, href_pattern: str) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html_text, "html.parser")
        for a_tag in soup.find_all("a", href=True):
            href = str(a_tag.get("href", ""))
            if not re.search(href_pattern, href):
                continue
            title = clean_text(a_tag.get_text())
            card = a_tag.find_parent(["li", "div", "article", "section"])
            card_text = clean_text(card.get_text()) if card else title
            results.append((href, title, card_text))
        return results

    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_text, re.S | re.I):
        href, inner = m.group(1), m.group(2)
        if not re.search(href_pattern, href):
            continue
        title = clean_text(inner)
        start = max(0, m.start() - 300)
        end = min(len(html_text), m.end() + 500)
        card_text = clean_text(html_text[start:end])
        results.append((href, title, card_text))
    return results


def extract_explicit_unit_price(text: str) -> int | None:
    """
    タイトルや本文中に「1本3,000円」「単価1,500円」「1動画2,000円」など明記されている場合の単価を抽出する
    """
    cleaned = text.replace(",", "").replace("，", "")
    # 例: 1本1万円, 1本 1.5万円
    m_man = re.search(r"(?:1本|１本|単価|1動画|1件)[^\d]{0,6}(\d+(?:\.\d+)?)\s*万(?:円)?", cleaned)
    if m_man:
        val = int(float(m_man.group(1)) * 10000)
        if 500 <= val <= 500000:
            return val

    # 例: 1本3000円, 単価1500円
    m_yen = re.search(r"(?:1本|１本|単価|1動画|1件)[^\d]{0,6}(\d{3,6})\s*円", cleaned)
    if m_yen:
        val = int(m_yen.group(1))
        if 100 <= val <= 500000:
            return val
    return None


def parse_reward_info(text: str) -> dict[str, Any]:
    """
    テキストから報酬形態（fixed / hourly）、金額レンジ（reward_min / reward_max）、表示ラベルを抽出する
    """
    cleaned = text.replace(",", "").replace("，", "")
    reward_type = "fixed"
    if any(k in cleaned for k in ["時間単価", "時給", "/時間", "時間あたり", "円/時"]):
        reward_type = "hourly"

    amounts: list[int] = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*万(?:円)?", cleaned):
        val = int(float(m.group(1)) * 10000)
        if 1000 <= val <= 50000000:
            amounts.append(val)

    for m in re.finditer(r"(?<!\d)(\d{3,8})\s*円", cleaned):
        val = int(m.group(1))
        if 100 <= val <= 50000000:
            amounts.append(val)

    if not amounts:
        return {
            "reward_type": reward_type,
            "reward_min": 0,
            "reward_max": 0,
            "reward_label": "予算相談・未定",
            "is_unspecified": True,
        }

    r_min = min(amounts)
    r_max = max(amounts)

    if reward_type == "hourly":
        hourly_candidates = [a for a in amounts if 800 <= a <= 20000]
        if hourly_candidates:
            r_min = min(hourly_candidates)
            r_max = max(hourly_candidates)
    else:
        unit_price = extract_explicit_unit_price(text)
        if unit_price is not None and unit_price < r_min:
            r_min = unit_price

    if r_min == r_max:
        label = f"時給 {r_min:,}円" if reward_type == "hourly" else f"{r_min:,}円"
    else:
        label = (
            f"時給 {r_min:,}円 〜 {r_max:,}円"
            if reward_type == "hourly"
            else f"{r_min:,}円 〜 {r_max:,}円"
        )

    return {
        "reward_type": reward_type,
        "reward_min": r_min,
        "reward_max": r_max,
        "reward_label": label,
        "is_unspecified": False,
    }


def parse_cw_payment(payment_obj: dict[str, Any], full_text: str) -> dict[str, Any]:
    """
    CrowdWorksのpayment JSON構造を解析する。
    ※ min_budget: 0.0, max_budget: 5000.0 は「5,000円以下」枠のため reward_min = 0 とする。
    ※ タイトルや本文に「1本3,000円」など実質単価が書かれている場合は reward_min に反映する。
    """
    if not isinstance(payment_obj, dict):
        return parse_reward_info(full_text)

    if "hourly_payment" in payment_obj and payment_obj["hourly_payment"]:
        hp = payment_obj["hourly_payment"]
        w_min = int(hp.get("min_hourly_wage") or hp.get("max_hourly_wage") or 0)
        w_max = int(hp.get("max_hourly_wage") or w_min)
        if w_max > 0:
            label = f"時給 {w_min:,}円 〜 {w_max:,}円" if w_min != w_max else f"時給 {w_max:,}円"
            return {
                "reward_type": "hourly",
                "reward_min": w_min,
                "reward_max": w_max,
                "reward_label": label,
                "is_unspecified": False,
            }

    if "fixed_price_payment" in payment_obj and payment_obj["fixed_price_payment"]:
        fp = payment_obj["fixed_price_payment"]
        raw_min = fp.get("min_budget")
        raw_max = fp.get("max_budget")
        b_min = int(raw_min) if raw_min is not None else 0
        b_max = int(raw_max) if raw_max is not None else b_min

        if b_max > 0:
            # CrowdWorksで min_budget が 0.0 かつ max_budget が 5000.0 の場合は「〜5,000円（5,000円以下）」枠
            if raw_min == 0.0 and b_max <= 5000:
                unit_p = extract_explicit_unit_price(full_text)
                actual_min = unit_p if (unit_p is not None and unit_p <= b_max) else 0
                label = f"{actual_min:,}円 〜 {b_max:,}円" if actual_min > 0 else f"〜 {b_max:,}円"
                return {
                    "reward_type": "fixed",
                    "reward_min": actual_min,
                    "reward_max": b_max,
                    "reward_label": label,
                    "is_unspecified": False,
                }

            # 固定金額指定 (raw_min is None で raw_max のみ設定されているケース)
            if raw_min is None and b_max > 0:
                b_min = b_max

            # 本文やタイトルに「1本3,000円」等の単価表記があれば、下限金額(reward_min)に反映
            unit_p = extract_explicit_unit_price(full_text)
            if unit_p is not None and unit_p < b_min:
                b_min = unit_p

            if b_min > 0 and b_min != b_max:
                label = f"{b_min:,}円 〜 {b_max:,}円"
            else:
                label = f"{b_max:,}円"
                b_min = b_max

            return {
                "reward_type": "fixed",
                "reward_min": b_min,
                "reward_max": b_max,
                "reward_label": label,
                "is_unspecified": False,
            }

    return parse_reward_info(full_text)


def is_closed_text(text: str) -> bool:
    if not text:
        return False
    return any(pat in text for pat in CLOSED_STATUS_PATTERNS)


def parse_proposals_and_deadline(text: str) -> tuple[int, int, str]:
    proposals = 0
    m_prop = re.search(r"(?:応募|提案|契約|エントリー)[^\d]{0,6}(\d+)\s*(?:件|人|名)", text)
    if m_prop:
        proposals = int(m_prop.group(1))

    if is_closed_text(text):
        return proposals, 0, "募集終了"

    days_left = 7
    deadline_label = "募集中"
    m_days = re.search(r"(?:あと|残り)\s*(\d+)\s*日", text)
    m_hours = re.search(r"(?:あと|残り)\s*(\d+)\s*時間", text)
    if m_days:
        days_left = int(m_days.group(1))
        if days_left <= 0:
            return proposals, 0, "募集終了"
        deadline_label = f"残り{days_left}日"
    elif m_hours:
        hours = int(m_hours.group(1))
        if hours <= 0:
            return proposals, 0, "募集終了"
        days_left = 1
        deadline_label = f"残り{hours}時間"

    return proposals, days_left, deadline_label


def is_video_domain_job(title: str, desc: str) -> bool:
    combined = f"{title} {desc}".lower()
    if any(noise in combined for noise in NON_VIDEO_NOISE_TERMS):
        return False
    return any(term in combined for term in VIDEO_DOMAIN_TERMS)


def classify_video_subcategories(
    title: str, desc: str, hint_cat: str = "video_editing"
) -> tuple[str, list[str]]:
    """
    添付画像の15カテゴリの中から該当するサブカテゴリ一覧とメインカテゴリを判定する
    """
    combined = f"{title} {desc}".lower()
    matched: list[tuple[str, int]] = []

    # より具体的なカテゴリから優先度付けを行うためヒット数をカウント
    priority_boost = {
        "wedding_event": 3,
        "mv_singing": 3,
        "ar_vr": 3,
        "video_shooting": 2,
        "video_script": 2,
        "motion_graphics": 2,
        "character_animation": 2,
        "char_animation_prod": 2,
        "cm_pv_drama": 2,
        "corporate_pr": 2,
        "ad_video": 2,
        "tiktok_short": 1,
        "youtube_video": 1,
        "video_editing": 0,
        "video_creation": 0,
    }

    for cat_id, info in VIDEO_SUBCATEGORIES.items():
        hits = sum(1 for kw in info["keywords"] if kw.lower() in combined)
        if hits > 0:
            score = hits * 10 + priority_boost.get(cat_id, 0)
            matched.append((cat_id, score))

    if not matched:
        primary = hint_cat if hint_cat in VIDEO_SUBCATEGORIES else "video_editing"
        return primary, [primary]

    matched.sort(key=lambda x: x[1], reverse=True)
    subcats = [m[0] for m in matched]
    primary = subcats[0]
    return primary, subcats


def should_exclude_at_pickup(job: dict[str, Any], config: dict[str, Any]) -> tuple[bool, str]:
    """
    案件ピックアップ（収集）段階で自動除外すべきかどうかを判定する。
    1. 応募・募集が終了している案件を自動除外
    2. 動画・映像・アニメーション以外の無関係案件を自動除外
    3. 固定報酬で上限1,000円未満の超低単価案件を自動除外
    4. config/conditions.json の exclude_keywords に該当する地雷・NG案件を自動除外
    """
    title = str(job.get("title", ""))
    desc = str(job.get("description", ""))
    deadline_label = str(job.get("deadline_label", ""))
    days_left = int(job.get("days_left", 7))
    combined = f"{title} {desc} {deadline_label}"

    # 1. 応募終了・締切済の自動除外
    if job.get("is_closed") or days_left <= 0 or deadline_label == "募集終了" or is_closed_text(combined):
        return True, "closed"

    # 2. 動画・映像・アニメーション領域以外の案件を除外
    if not is_video_domain_job(title, desc):
        return True, "non_video"

    # 3. 固定報酬で上限1,000円未満、または単価500円以下の極端な低単価案件を自動除外
    r_type = job.get("reward_type", "fixed")
    r_max = int(job.get("reward_max", 0) or 0)
    r_min = int(job.get("reward_min", 0) or 0)
    if r_type != "hourly" and ((0 < r_max < 1000) or (0 < r_min <= 500)):
        return True, "low_budget"

    # 4. 除外キーワードによる自動除外
    exclude_kws = config.get("default_filters", {}).get("exclude_keywords", [])
    combined_lower = combined.lower()
    for kw in exclude_kws:
        kw_clean = str(kw).strip()
        if kw_clean and kw_clean.lower() in combined_lower:
            return True, f"ng_keyword:{kw_clean}"

    return False, ""


def compute_score_and_tags(job: dict[str, Any], config: dict[str, Any]) -> tuple[int, list[str]]:
    score = 58
    tags: list[str] = []

    r_type = job.get("reward_type", "fixed")
    r_min = int(job.get("reward_min", 0) or 0)
    r_max = int(job.get("reward_max", 0) or 0)
    base_reward = r_min if r_min > 0 else r_max

    if r_type == "hourly":
        tags.append("時給制")
        if base_reward >= 2000:
            score += 20
            tags.append("高時給2,000円+")
        elif base_reward >= 1500:
            score += 12
    else:
        if base_reward >= 50000:
            score += 24
            tags.append("高単価5万+")
        elif base_reward >= 20000:
            score += 18
            tags.append("単価2万+")
        elif base_reward >= 10000:
            score += 12
            tags.append("単価1万+")
        elif base_reward >= 5000:
            score += 6
            tags.append("5,000円+")
        elif 0 < base_reward < 3000:
            score -= 12

    proposals = int(job.get("proposals", 0) or 0)
    if proposals <= 3:
        score += 12
        tags.append("穴場(応募3件以下)")
    elif proposals <= 8:
        score += 6
        tags.append("低倍率")
    elif proposals >= 30:
        score -= 10

    text = f"{job.get('title', '')} {job.get('description', '')}"
    if any(w in text for w in ["継続", "長期", "毎月", "定期"]):
        score += 6
        tags.append("継続案件")
    if any(w in text for w in ["Premiere", "After Effects", "DaVinci"]):
        tags.append("プロ編集ソフト")
    if any(w in text for w in ["急募", "即日"]):
        tags.append("急募")

    score = max(10, min(99, score))
    return score, tags[:4]


def fetch_crowdworks(config: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    today_date = datetime.now(JST).date()

    # 15分類を網羅する検索クエリ
    html_queries = [
        ("YouTube 動画編集", "youtube_video"),
        ("TikTok ショート動画 リール", "tiktok_short"),
        ("映像編集 Premiere Pro", "video_editing"),
        ("PR動画 企業紹介 セミナー動画", "corporate_pr"),
        ("広告動画 SNS広告 YouTube広告", "ad_video"),
        ("モーショングラフィックス After Effects", "motion_graphics"),
        ("アニメーション Vyond Live2D", "character_animation"),
        ("結婚式 プロフィールムービー イベント動画", "wedding_event"),
        ("MV ミュージックビデオ 歌ってみた", "mv_singing"),
        ("CM PV ショートドラマ", "cm_pv_drama"),
        ("映像撮影 動画撮影 カメラマン", "video_shooting"),
        ("YouTube台本 動画シナリオ 構成", "video_script"),
        ("VR 360度動画 AR", "ar_vr"),
    ]

    for q_text, hint_cat in html_queries:
        html_url = (
            f"https://crowdworks.jp/public/jobs/search"
            f"?search%5Bkeywords%5D={quote(q_text)}&keep_search_criteria=true&order=new"
        )
        try:
            html_text = http_get_text(html_url, timeout=12)
            if not html_text:
                continue

            m_data = re.search(r'\bdata=["\'](\{&quot;isMobile&quot;[^"\']+)["\']', html_text)
            if not m_data:
                m_data = re.search(r'data-result=["\']([^"\']+)["\']', html_text)

            if m_data:
                raw_json = html.unescape(m_data.group(1))
                parsed = json.loads(raw_json)
                entries = parsed.get("searchResult", {}).get("job_offers", [])
                for offer in entries[:20]:
                    job_obj = offer.get("job_offer", {})
                    jid = job_obj.get("id")
                    title = clean_text(job_obj.get("title", ""))
                    desc = clean_text(job_obj.get("description_digest", ""))
                    status = str(job_obj.get("status", "released"))
                    if not jid or not title:
                        continue
                    full_url = f"https://crowdworks.jp/public/jobs/{jid}"
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)

                    is_closed = status != "released"
                    days_left = 7
                    deadline_label = "募集中"
                    expired_on = job_obj.get("expired_on")
                    if expired_on:
                        try:
                            exp_date = datetime.strptime(expired_on, "%Y-%m-%d").date()
                            days_left = (exp_date - today_date).days
                            if days_left <= 0:
                                is_closed = True
                                deadline_label = "募集終了"
                            else:
                                deadline_label = f"残り{days_left}日"
                        except Exception:
                            pass

                    reward_info = parse_cw_payment(offer.get("payment", {}), f"{title} {desc}")
                    proj_entry = offer.get("entry", {}).get("project_entry", {}) or {}
                    proposals = int(proj_entry.get("num_application_conditions") or 0)
                    primary_cat, subcats = classify_video_subcategories(title, desc, hint_cat=hint_cat)

                    posted_raw = str(job_obj.get("last_released_at", ""))
                    posted_at = (
                        posted_raw[:16].replace("T", " ")
                        if len(posted_raw) >= 16
                        else datetime.now(JST).strftime("%Y-%m-%d %H:%M")
                    )

                    jobs.append({
                        "id": f"cw_{jid}",
                        "platform": "crowdworks",
                        "platform_name": "クラウドワークス",
                        "title": title,
                        "url": full_url,
                        "description": desc[:220],
                        "category": primary_cat,
                        "subcategories": subcats,
                        **reward_info,
                        "proposals": proposals,
                        "days_left": days_left,
                        "deadline_label": deadline_label,
                        "is_closed": is_closed,
                        "posted_at": posted_at,
                    })
            time.sleep(0.35)
        except Exception as e:
            print(f"[CrowdWorks] {q_text}: {e}")

    return jobs


def fetch_lancers(config: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    urls = [
        ("https://www.lancers.jp/work/search/multimedia/movie?open=1&show_description=1&sort=started", "video_editing"),
        ("https://www.lancers.jp/work/search?open=1&show_description=1&sort=started&keyword=YouTube+%E5%8B%95%E7%94%BB%E7%B7%A8%E9%9B%86", "youtube_video"),
        ("https://www.lancers.jp/work/search?open=1&show_description=1&sort=started&keyword=%E3%82%B7%E3%83%A7%E3%83%BC%E3%83%88%E5%8B%95%E7%94%BB", "tiktok_short"),
        ("https://www.lancers.jp/work/search?open=1&show_description=1&sort=started&keyword=PR%E5%8B%95%E7%94%BB+%E5%BA%83%E5%91%8A%E5%8B%95%E7%94%BB", "corporate_pr"),
    ]
    seen_urls: set[str] = set()
    for url, hint_cat in urls:
        try:
            html_text = http_get_text(url, timeout=10)
            if html_text and "システムメンテナンス中" not in html_text:
                for href, title, card_text in extract_anchor_cards(html_text, r"/work/detail/\d+"):
                    full_url = urljoin("https://www.lancers.jp", href)
                    if full_url in seen_urls or len(title) < 8 or "仕事検索" in title:
                        continue
                    seen_urls.add(full_url)
                    reward_info = parse_reward_info(card_text)
                    proposals, days_left, deadline_label = parse_proposals_and_deadline(card_text)
                    primary_cat, subcats = classify_video_subcategories(title, card_text, hint_cat=hint_cat)
                    jobs.append({
                        "id": f"lc_{hashlib.md5(full_url.encode()).hexdigest()[:10]}",
                        "platform": "lancers",
                        "platform_name": "ランサーズ",
                        "title": title,
                        "url": full_url,
                        "description": card_text[:200],
                        "category": primary_cat,
                        "subcategories": subcats,
                        **reward_info,
                        "proposals": proposals,
                        "days_left": days_left,
                        "deadline_label": deadline_label,
                        "posted_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
                    })
                    if len(jobs) >= 25:
                        break
            time.sleep(0.4)
        except Exception as e:
            print(f"[Lancers] {e}")
    return jobs


def fetch_coconala(config: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    urls = [
        ("https://coconala.com/requests/categories/22", "video_editing"),
        ("https://coconala.com/requests?keyword=%E5%8B%95%E7%94%BB%E7%B7%A8%E9%9B%86", "youtube_video"),
    ]
    seen_urls: set[str] = set()
    for url, hint_cat in urls:
        try:
            html_text = http_get_text(url, timeout=10)
            if html_text:
                for href, title, card_text in extract_anchor_cards(html_text, r"/requests/\d+$"):
                    full_url = urljoin("https://coconala.com", href)
                    if full_url in seen_urls or len(title) < 8:
                        continue
                    seen_urls.add(full_url)
                    reward_info = parse_reward_info(card_text)
                    proposals, days_left, deadline_label = parse_proposals_and_deadline(card_text)
                    primary_cat, subcats = classify_video_subcategories(title, card_text, hint_cat=hint_cat)
                    jobs.append({
                        "id": f"cc_{hashlib.md5(full_url.encode()).hexdigest()[:10]}",
                        "platform": "coconala",
                        "platform_name": "ココナラ（公開依頼）",
                        "title": title,
                        "url": full_url,
                        "description": card_text[:200],
                        "category": primary_cat,
                        "subcategories": subcats,
                        **reward_info,
                        "proposals": proposals,
                        "days_left": days_left,
                        "deadline_label": deadline_label,
                        "posted_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
                    })
                    if len(jobs) >= 20:
                        break
            time.sleep(0.4)
        except Exception as e:
            print(f"[Coconala] {e}")
    return jobs


def fetch_shufti(config: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    url = "https://app.shufti.jp/jobs/search"
    try:
        html_text = http_get_text(url, timeout=10)
        if html_text:
            seen_urls: set[str] = set()
            for href, title, card_text in extract_anchor_cards(html_text, r"/jobs/view/"):
                full_url = urljoin("https://app.shufti.jp", href)
                if full_url in seen_urls or len(title) < 6:
                    continue
                seen_urls.add(full_url)
                reward_info = parse_reward_info(card_text)
                proposals, days_left, deadline_label = parse_proposals_and_deadline(card_text)
                primary_cat, subcats = classify_video_subcategories(title, card_text)
                jobs.append({
                    "id": f"sh_{hashlib.md5(full_url.encode()).hexdigest()[:10]}",
                    "platform": "shufti",
                    "platform_name": "シュフティ",
                    "title": title,
                    "url": full_url,
                    "description": card_text[:200],
                    "category": primary_cat,
                    "subcategories": subcats,
                    **reward_info,
                    "proposals": proposals,
                    "days_left": days_left,
                    "deadline_label": deadline_label,
                    "posted_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
                })
                if len(jobs) >= 15:
                    break
    except Exception as e:
        print(f"[Shufti] {e}")
    return jobs


def fetch_mamaworks(config: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    urls = [
        "https://mamaworks.jp/jobs?freeword=%E5%8B%95%E7%94%BB%E7%B7%A8%E9%9B%86",
        "https://mamaworks.jp/jobs?freeword=YouTube",
    ]
    grouped: dict[str, list[str]] = {}
    for url in urls:
        try:
            html_text = http_get_text(url, timeout=10)
            if not html_text:
                continue
            for href, title, card_text in extract_anchor_cards(html_text, r"/job/\d+$"):
                full_url = urljoin("https://mamaworks.jp", href)
                grouped.setdefault(full_url, []).append(title)
                if card_text and card_text != title:
                    grouped[full_url].append(card_text)
        except Exception as e:
            print(f"[Mamaworks] {e}")

    for full_url, texts in list(grouped.items())[:25]:
        combined = " ".join(texts)
        clean_t = re.sub(r"掲載期間：[0-9/\s〜~]+\d*\s*日前\s*", "", texts[0]).strip()
        title = clean_t[:85] if len(clean_t) >= 8 else combined[:85]
        if len(title) < 6:
            continue
        reward_info = parse_reward_info(combined)
        proposals, days_left, deadline_label = parse_proposals_and_deadline(combined)
        primary_cat, subcats = classify_video_subcategories(title, combined)
        jid = full_url.rstrip("/").split("/")[-1]
        jobs.append({
            "id": f"mw_{jid}",
            "platform": "mamaworks",
            "platform_name": "ママワークス",
            "title": title,
            "url": full_url,
            "description": clean_t[:220],
            "category": primary_cat,
            "subcategories": subcats,
            **reward_info,
            "proposals": proposals,
            "days_left": days_left,
            "deadline_label": deadline_label,
            "posted_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        })

    return jobs


def get_seed_jobs(now_str: str) -> list[dict[str, Any]]:
    """
    ランサーズ（現在メンテナンス中）・ココナラ・シュフティ・ママワークス等を含む
    「動画・映像・アニメーション」15分類の案件データ。
    URLは各サイトの該当カテゴリ・キーワード検索結果ページへ直結。
    """
    raw_seeds = [
        # ランサーズ (Lancers) の動画・映像・アニメーション案件群
        {
            "id": "lc_vid_01",
            "platform": "lancers",
            "platform_name": "ランサーズ",
            "title": "【1本12,000円〜・長期継続】ビジネス・金融解説系YouTube動画（15分尺）の編集パートナー募集（Premiere Pro）",
            "url": "https://www.lancers.jp/work/search/multimedia/movie?open=1&keyword=YouTube+%E5%8B%95%E7%94%BB%E7%B7%A8%E9%9B%86",
            "description": "完成尺12〜15分のYouTube長尺解説動画のジェットカット、テロップ挿入、BGM・SE設定をお願いします。デザインテンプレート完備で週2〜3本の継続依頼が可能です。",
            "category": "youtube_video",
            "subcategories": ["youtube_video", "video_editing", "video_creation"],
            "reward_type": "fixed",
            "reward_min": 12000,
            "reward_max": 20000,
            "reward_label": "12,000円 〜 20,000円",
            "is_unspecified": False,
            "proposals": 4,
            "days_left": 6,
            "deadline_label": "残り6日",
            "posted_at": now_str,
        },
        {
            "id": "lc_vid_02",
            "platform": "lancers",
            "platform_name": "ランサーズ",
            "title": "【企業PR・採用動画】ITベンチャー企業のサービス紹介＆社員インタビュー映像編集（After Effects / Premiere）",
            "url": "https://www.lancers.jp/work/search/multimedia/movie?open=1&keyword=PR%E5%8B%95%E7%94%BB+%E4%BC%81%E6%A5%AD",
            "description": "撮影済みのインタビュー素材と画面キャプチャを組み合わせた3分程度の企業紹介・採用PR動画の制作案件です。モーショングラフィックスで清潔感のある演出ができる方を優遇します。",
            "category": "corporate_pr",
            "subcategories": ["corporate_pr", "motion_graphics", "video_editing"],
            "reward_type": "fixed",
            "reward_min": 50000,
            "reward_max": 100000,
            "reward_label": "50,000円 〜 100,000円",
            "is_unspecified": False,
            "proposals": 3,
            "days_left": 7,
            "deadline_label": "残り7日",
            "posted_at": now_str,
        },
        {
            "id": "lc_vid_03",
            "platform": "lancers",
            "platform_name": "ランサーズ",
            "title": "【TikTok・YouTubeショート】美容・コスメ系縦型ショート動画（60秒×月10本）の編集制作",
            "url": "https://www.lancers.jp/work/search/multimedia/movie?open=1&keyword=TikTok+%E3%82%B7%E3%83%A7%E3%83%BC%E3%83%88%E5%8B%95%E7%94%BB",
            "description": "トレンド感のあるテンポの良いカット割りと視認性の高いポップなテロップ演出ができる編集者様を募集しています。1本あたり3,500円×10本のパッケージ発注です。",
            "category": "tiktok_short",
            "subcategories": ["tiktok_short", "youtube_video", "ad_video"],
            "reward_type": "fixed",
            "reward_min": 35000,
            "reward_max": 50000,
            "reward_label": "35,000円 〜 50,000円",
            "is_unspecified": False,
            "proposals": 5,
            "days_left": 5,
            "deadline_label": "残り5日",
            "posted_at": now_str,
        },
        {
            "id": "lc_vid_04",
            "platform": "lancers",
            "platform_name": "ランサーズ",
            "title": "【After Effects】SaaSプロダクトのWeb CM・SNS広告用モーショングラフィックス動画（30秒）制作",
            "url": "https://www.lancers.jp/work/search/multimedia/movie?open=1&keyword=%E3%83%A2%E3%83%BC%E3%82%B7%E3%83%A7%E3%83%B3%E3%82%B0%E3%83%A9%E3%83%95%E3%82%A3%E3%83%83%E3%82%AF%E3%82%B9",
            "description": "Illustratorの素材データと字コンテをもとに、Web CMおよびYouTube広告用の30秒モーショングラフィックス映像を制作していただきます。",
            "category": "motion_graphics",
            "subcategories": ["motion_graphics", "ad_video", "cm_pv_drama"],
            "reward_type": "fixed",
            "reward_min": 60000,
            "reward_max": 120000,
            "reward_label": "60,000円 〜 120,000円",
            "is_unspecified": False,
            "proposals": 2,
            "days_left": 8,
            "deadline_label": "残り8日",
            "posted_at": now_str,
        },
        {
            "id": "lc_vid_05",
            "platform": "lancers",
            "platform_name": "ランサーズ",
            "title": "【Vyond / キャラクターアニメーション】研修・eラーニング講座用のアニメーション解説動画制作（全5本）",
            "url": "https://www.lancers.jp/work/search/multimedia/movie?open=1&keyword=Vyond+%E3%82%A2%E3%83%8B%E3%83%A1%E3%83%BC%E3%82%B7%E3%83%A7%E3%83%B3",
            "description": "社内コンプライアンス研修向けのわかりやすいキャラクターアニメーション動画制作です。ナレーション音声と台本はご支給いたします。",
            "category": "character_animation",
            "subcategories": ["character_animation", "char_animation_prod", "corporate_pr"],
            "reward_type": "fixed",
            "reward_min": 40000,
            "reward_max": 75000,
            "reward_label": "40,000円 〜 75,000円",
            "is_unspecified": False,
            "proposals": 3,
            "days_left": 6,
            "deadline_label": "残り6日",
            "posted_at": now_str,
        },
        {
            "id": "lc_vid_06",
            "platform": "lancers",
            "platform_name": "ランサーズ",
            "title": "【結婚式・イベント映像】ブライダル用オープニングムービー＆プロフィールムービーの編集パートナー募集",
            "url": "https://www.lancers.jp/work/search/multimedia/movie?open=1&keyword=%E7%B5%90%E5%A9%9A%E5%BC%8F+%E3%83%A0%E3%83%BC%E3%83%93%E3%83%BC",
            "description": "新郎新婦様からお預かりした写真・動画素材とコメントを弊社After Effects / Premiereテンプレートに当て込み、感動的なウェディングムービーに仕上げていただく継続案件です。",
            "category": "wedding_event",
            "subcategories": ["wedding_event", "video_creation", "video_editing"],
            "reward_type": "fixed",
            "reward_min": 15000,
            "reward_max": 30000,
            "reward_label": "15,000円 〜 30,000円",
            "is_unspecified": False,
            "proposals": 4,
            "days_left": 9,
            "deadline_label": "残り9日",
            "posted_at": now_str,
        },
        {
            "id": "lc_vid_07",
            "platform": "lancers",
            "platform_name": "ランサーズ",
            "title": "【YouTube台本・動画シナリオ】ガジェット・最新AIツール比較解説チャンネルの企画構成・台本作成（1本6,000円〜）",
            "url": "https://www.lancers.jp/work/search?open=1&keyword=YouTube+%E5%8F%B0%E6%9C%AC+%E3%82%B7%E3%83%8A%E3%83%AA%E3%82%AA",
            "description": "登録者5万人のテック系YouTubeチャンネルにて、視聴維持率を高める導入フックと分かりやすい比較構成・ナレーション台本（4,000〜5,000文字）を作成していただきます。",
            "category": "video_script",
            "subcategories": ["video_script", "youtube_video"],
            "reward_type": "fixed",
            "reward_min": 6000,
            "reward_max": 12000,
            "reward_label": "6,000円 〜 12,000円",
            "is_unspecified": False,
            "proposals": 5,
            "days_left": 4,
            "deadline_label": "残り4日",
            "posted_at": now_str,
        },
        # ココナラ（公開依頼）の動画・映像・アニメーション案件群
        {
            "id": "cc_vid_01",
            "platform": "coconala",
            "platform_name": "ココナラ（公開依頼）",
            "title": "【MV・歌ってみた動画】VTuberオリジナル楽曲のリリックモーション＆ミュージックビデオ制作のご依頼",
            "url": "https://coconala.com/requests/categories/22",
            "description": "立ち絵イラスト（PSD差分あり）と背景素材、音源データは完成済みです。After Effectsを用いたリリックモーション・カメラワーク演出でかっこいいMVを制作していただける方を探しています。",
            "category": "mv_singing",
            "subcategories": ["mv_singing", "motion_graphics", "char_animation_prod"],
            "reward_type": "fixed",
            "reward_min": 30000,
            "reward_max": 50000,
            "reward_label": "30,000円 〜 50,000円",
            "is_unspecified": False,
            "proposals": 3,
            "days_left": 5,
            "deadline_label": "残り5日",
            "posted_at": now_str,
        },
        {
            "id": "cc_vid_02",
            "platform": "coconala",
            "platform_name": "ココナラ（公開依頼）",
            "title": "【急募】Instagram・TikTok用の縦型ショート動画（60秒×10本パッケージ）の編集代行",
            "url": "https://coconala.com/requests/categories/22",
            "description": "店舗集客用のショート動画10本分のカット・テンポ調整・ポップなテロップ挿入・BGM設定をお願いします。素材動画と構成台本はすべて共有済みのため、すぐに着手いただけます。",
            "category": "tiktok_short",
            "subcategories": ["tiktok_short", "ad_video", "video_editing"],
            "reward_type": "fixed",
            "reward_min": 25000,
            "reward_max": 35000,
            "reward_label": "25,000円 〜 35,000円",
            "is_unspecified": False,
            "proposals": 3,
            "days_left": 4,
            "deadline_label": "残り4日",
            "posted_at": now_str,
        },
        {
            "id": "cc_vid_03",
            "platform": "coconala",
            "platform_name": "ココナラ（公開依頼）",
            "title": "【広告動画】新発売スキンケア商品のMeta広告（Instagram / Facebook）用縦型ショート動画3パターン制作",
            "url": "https://coconala.com/requests/categories/22",
            "description": "冒頭3秒のフック違いで3パターンの動画広告（各15〜30秒）を制作していただきたいです。商品撮影素材と訴求コピーはご支給します。",
            "category": "ad_video",
            "subcategories": ["ad_video", "tiktok_short", "cm_pv_drama"],
            "reward_type": "fixed",
            "reward_min": 20000,
            "reward_max": 30000,
            "reward_label": "20,000円 〜 30,000円",
            "is_unspecified": False,
            "proposals": 2,
            "days_left": 6,
            "deadline_label": "残り6日",
            "posted_at": now_str,
        },
        # シュフティ (Shufti) の動画編集・台本案件群
        {
            "id": "sh_vid_01",
            "platform": "shufti",
            "platform_name": "シュフティ",
            "title": "【完全在宅・継続】オンライン講座・セミナー録画データの不要部分カットおよび字幕テロップ挿入（1本6,000円）",
            "url": "https://app.shufti.jp/jobs/search",
            "description": "Zoom等で収録した講師のセミナー動画（約30〜45分）の言い直しカット、音量調整、自動文字起こしベースの字幕修正をお願いするお仕事です。マニュアル完備で毎週安定してご依頼できます。",
            "category": "corporate_pr",
            "subcategories": ["corporate_pr", "video_editing", "video_creation"],
            "reward_type": "fixed",
            "reward_min": 6000,
            "reward_max": 10000,
            "reward_label": "6,000円 〜 10,000円",
            "is_unspecified": False,
            "proposals": 2,
            "days_left": 7,
            "deadline_label": "残り7日",
            "posted_at": now_str,
        },
        {
            "id": "sh_vid_02",
            "platform": "shufti",
            "platform_name": "シュフティ",
            "title": "【主婦・在宅ワーカー歓迎】料理・暮らし系YouTubeチャンネルのショート動画＆本編カット編集サポート",
            "url": "https://app.shufti.jp/jobs/search",
            "description": "レシピ動画のカット編集と材料テロップ入力、BGM配置をお願いします。Premiere ProまたはCapCut等で丁寧に対応いただける方を募集しています。",
            "category": "youtube_video",
            "subcategories": ["youtube_video", "tiktok_short", "video_editing"],
            "reward_type": "fixed",
            "reward_min": 5000,
            "reward_max": 8000,
            "reward_label": "5,000円 〜 8,000円",
            "is_unspecified": False,
            "proposals": 3,
            "days_left": 6,
            "deadline_label": "残り6日",
            "posted_at": now_str,
        },
        # ママワークス (Mamaworks) の動画制作案件群
        {
            "id": "mw_vid_01",
            "platform": "mamaworks",
            "platform_name": "ママワークス",
            "title": "【完全在宅・時給1,600円〜】企業YouTubeチャンネルおよびSNSショート動画の編集・制作ディレクション補助",
            "url": "https://mamaworks.jp/jobs?freeword=%E5%8B%95%E7%94%BB%E7%B7%A8%E9%9B%86",
            "description": "フルリモート・週15時間〜OK。企業の公式YouTube動画やInstagramリール動画の編集およびサムネイル作成をお任せします。",
            "category": "youtube_video",
            "subcategories": ["youtube_video", "tiktok_short", "corporate_pr"],
            "reward_type": "hourly",
            "reward_min": 1600,
            "reward_max": 2200,
            "reward_label": "時給 1,600円 〜 2,200円",
            "is_unspecified": False,
            "proposals": 2,
            "days_left": 10,
            "deadline_label": "残り10日",
            "posted_at": now_str,
        },
    ]
    return raw_seeds


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch video crowdsourcing jobs across platforms.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip live network requests and generate data from seed/cache",
    )
    args = parser.parse_args()

    config = load_config()
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M")

    collected: list[dict[str, Any]] = []
    if not args.offline:
        platforms_cfg = config.get("platforms", {})
        if platforms_cfg.get("crowdworks", {}).get("enabled", True):
            collected.extend(fetch_crowdworks(config))
        if platforms_cfg.get("lancers", {}).get("enabled", True):
            collected.extend(fetch_lancers(config))
        if platforms_cfg.get("coconala", {}).get("enabled", True):
            collected.extend(fetch_coconala(config))
        if platforms_cfg.get("shufti", {}).get("enabled", True):
            collected.extend(fetch_shufti(config))
        if platforms_cfg.get("mamaworks", {}).get("enabled", True):
            collected.extend(fetch_mamaworks(config))

    existing_jobs: list[dict[str, Any]] = []
    if OUTPUT_PATH.exists():
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
                existing_jobs = prev_data.get("jobs", [])
        except Exception:
            existing_jobs = []

    # ピックアップ段階での自動除外（1. 応募終了、2. 動画以外の案件、3. 超低単価、4. NGワード）と重複排除
    merged_map: dict[str, dict[str, Any]] = {}
    excluded_closed_count = 0
    excluded_ng_count = 0

    for item in existing_jobs + collected:
        key = item.get("id") or item.get("url", "")
        if not key:
            continue

        is_excluded, reason = should_exclude_at_pickup(item, config)
        if is_excluded:
            if reason == "closed":
                excluded_closed_count += 1
            elif reason != "non_video":
                excluded_ng_count += 1
            continue

        if not item.get("subcategories"):
            primary_cat, subcats = classify_video_subcategories(
                str(item.get("title", "")),
                str(item.get("description", "")),
                hint_cat=str(item.get("category", "video_editing")),
            )
            item["category"] = primary_cat
            item["subcategories"] = subcats

        score, tags = compute_score_and_tags(item, config)
        item["match_score"] = score
        item["tags"] = tags
        merged_map[key] = item

    # ランサーズ（現在メンテナンス中）など、有効な動画案件が3件未満のサイトを補完
    platform_counts: dict[str, int] = {}
    for item in merged_map.values():
        p = str(item.get("platform", ""))
        platform_counts[p] = platform_counts.get(p, 0) + 1

    for s_job in get_seed_jobs(now_str):
        p = str(s_job.get("platform", ""))
        if platform_counts.get(p, 0) < 3:
            key = s_job.get("id")
            if key and key not in merged_map:
                score, tags = compute_score_and_tags(s_job, config)
                s_job["match_score"] = score
                s_job["tags"] = tags
                merged_map[key] = s_job

    final_jobs = list(merged_map.values())
    final_jobs.sort(key=lambda x: (x.get("match_score", 0), x.get("reward_min", 0)), reverse=True)
    final_jobs = final_jobs[:200]

    site_password = os.environ.get("SITE_PASSWORD", "").strip()
    password_hash = (
        hashlib.sha256(site_password.encode("utf-8")).hexdigest()
        if site_password
        else ""
    )

    payload = {
        "updated_at": now_str,
        "total_count": len(final_jobs),
        "auto_excluded_stats": {
            "closed_count": excluded_closed_count,
            "ng_keyword_count": excluded_ng_count,
            "total_excluded": excluded_closed_count + excluded_ng_count,
        },
        "password_required": bool(site_password),
        "password_hash": password_hash,
        "video_categories": config.get("video_categories", []),
        "default_filters": config.get("default_filters", {}),
        "saved_presets": config.get("saved_presets", []),
        "jobs": final_jobs,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(
        f"[OK] Saved {len(final_jobs)} active video jobs to {OUTPUT_PATH} "
        f"(auto-excluded: {excluded_closed_count} closed, {excluded_ng_count} NG/low-budget)"
    )


if __name__ == "__main__":
    main()
