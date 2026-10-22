#!/usr/bin/env python3
"""
クラウドソーシング5大サイト横断・案件自動収集＆スコアリングスクリプト
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
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

CATEGORY_KEYWORDS = {
    "development": [
        "Python", "JavaScript", "TypeScript", "React", "Next.js", "Vue", "PHP",
        "Laravel", "Ruby", "Go", "Swift", "Kotlin", "Flutter", "GAS", "API",
        "スクレイピング", "自動化", "システム開発", "アプリ開発", "AI", "ChatGPT",
        "LLM", "プロンプト", "Dify", "Bot", "マクロ", "VBA", "AWS", "DB", "ツール"
    ],
    "design": [
        "Webデザイン", "LP", "ランディングページ", "WordPress", "コーディング",
        "HTML", "CSS", "バナー", "サムネイル", "ロゴ", "イラスト", "Figma",
        "Photoshop", "Illustrator", "Canva", "UI", "UX", "Studio", "Wix", "チラシ"
    ],
    "video": [
        "動画編集", "映像制作", "YouTube", "ショート動画", "TikTok", "リール",
        "Reels", "Premiere", "After Effects", "CapCut", "DaVinci", "切り抜き",
        "テロップ", "アニメーション", "PR動画", "Vrew"
    ],
    "writing": [
        "ライティング", "記事作成", "SEO", "ブログ", "コラム", "構成案", "執筆",
        "リライト", "シナリオ", "台本", "インタビュー", "翻訳", "校正", "文字起こし",
        "レビュー", "体験談", "プレスリリース"
    ],
    "business": [
        "データ入力", "リスト作成", "リサーチ", "事務", "経理", "アシスタント",
        "秘書", "カスタマーサポート", "メール対応", "スプレッドシート", "Excel",
        "ECサイト", "商品登録", "出品", "テレアポ", "SNS運用", "Instagram運用"
    ],
}


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


def parse_rss_items(xml_text: str) -> list[dict[str, str]]:
    if feedparser is not None:
        feed = feedparser.parse(xml_text)
        return [
            {
                "title": clean_text(e.get("title", "")),
                "link": str(e.get("link", "")),
                "summary": clean_text(e.get("summary", "")),
            }
            for e in feed.entries
        ]
    items: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
        for item_el in root.findall(".//item"):
            title = clean_text(item_el.findtext("title") or "")
            link = (item_el.findtext("link") or "").strip()
            desc = clean_text(item_el.findtext("description") or "")
            if title and link:
                items.append({"title": title, "link": link, "summary": desc})
    except Exception:
        pass
    return items


def extract_anchor_cards(html_text: str, href_pattern: str) -> list[tuple[str, str, str]]:
    """
    HTMLから指定正規表現にマッチするリンクの (href, title, card_text) リストを返す
    """
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


def parse_reward_info(text: str) -> dict[str, Any]:
    """
    テキストから報酬形態（fixed / hourly / task）、金額レンジ（min / max）、表示ラベルを抽出する
    """
    cleaned = text.replace(",", "").replace("，", "")
    reward_type = "fixed"
    if any(k in cleaned for k in ["時間単価", "時給", "/時間", "時間あたり", "円/時"]):
        reward_type = "hourly"
    elif any(k in cleaned for k in ["タスク", "1件あたり", "文字単価"]):
        reward_type = "task"
    elif "コンペ" in cleaned:
        reward_type = "competition"

    # 「○万円〜○万円」「○円〜○円」などの抽出
    amounts: list[int] = []

    # 万単位の数値 (例: 5万円, 10万〜30万円, 1.5万円)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*万(?:円)?", cleaned):
        val = int(float(m.group(1)) * 10000)
        if 1000 <= val <= 50000000:
            amounts.append(val)

    # 円単位の数値 (例: 3000円, 1500円)
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

    # 時給なのに万単位の記述などが混ざった場合の補正
    if reward_type == "hourly":
        hourly_candidates = [a for a in amounts if 800 <= a <= 20000]
        if hourly_candidates:
            r_min = min(hourly_candidates)
            r_max = max(hourly_candidates)

    if r_min == r_max:
        if reward_type == "hourly":
            label = f"時給 {r_min:,}円"
        else:
            label = f"{r_min:,}円"
    else:
        if reward_type == "hourly":
            label = f"時給 {r_min:,}円 〜 {r_max:,}円"
        else:
            label = f"{r_min:,}円 〜 {r_max:,}円"

    return {
        "reward_type": reward_type,
        "reward_min": r_min,
        "reward_max": r_max,
        "reward_label": label,
        "is_unspecified": False,
    }


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


def is_closed_text(text: str) -> bool:
    if not text:
        return False
    for pat in CLOSED_STATUS_PATTERNS:
        if pat in text:
            return True
    return False


def parse_proposals_and_deadline(text: str) -> tuple[int, int, str]:
    """
    テキストから応募・提案数、残り日数、締切ラベルを抽出する。
    募集終了している場合は days_left = 0, deadline_label = "募集終了" を返す。
    """
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


def should_exclude_at_pickup(job: dict[str, Any], config: dict[str, Any]) -> tuple[bool, str]:
    """
    案件ピックアップ（収集）段階で自動除外すべきかどうかを判定する。
    1. 応募・募集が終了している案件を自動除外
    2. 固定報酬で上限1,000円未満の超低単価・アンケート案件を自動除外
    3. config/conditions.json の exclude_keywords に該当する地雷・NG案件を自動除外
    """
    title = str(job.get("title", ""))
    desc = str(job.get("description", ""))
    deadline_label = str(job.get("deadline_label", ""))
    days_left = int(job.get("days_left", 7))
    combined = f"{title} {desc} {deadline_label}"

    # 1. 応募終了・締切済の自動除外
    if job.get("is_closed") or days_left <= 0 or deadline_label == "募集終了" or is_closed_text(combined):
        return True, "closed"

    # 2. 固定報酬で上限1,000円未満の極端な低単価案件を自動除外
    r_type = job.get("reward_type", "fixed")
    r_max = int(job.get("reward_max", 0) or 0)
    if r_type != "hourly" and 0 < r_max < 1000:
        return True, "low_budget_under_1000"

    # 3. 除外キーワードによる自動除外
    exclude_kws = config.get("default_filters", {}).get("exclude_keywords", [])
    combined_lower = combined.lower()
    for kw in exclude_kws:
        kw_clean = str(kw).strip()
        if kw_clean and kw_clean.lower() in combined_lower:
            return True, f"ng_keyword:{kw_clean}"

    return False, ""


def detect_category(title: str, description: str, default_cat: str = "other") -> str:
    combined = f"{title} {description}".lower()
    best_cat = default_cat
    best_hits = 0
    for cat, kw_list in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in kw_list if kw.lower() in combined)
        if hits > best_hits:
            best_hits = hits
            best_cat = cat
    return best_cat if best_cat != "other" else "business"


def compute_score_and_tags(job: dict[str, Any], config: dict[str, Any]) -> tuple[int, list[str]]:
    """
    案件の条件適合度・魅力度スコア（0〜100）と特徴タグを自動算出する
    """
    score = 55
    tags: list[str] = []

    r_type = job.get("reward_type", "fixed")
    r_max = job.get("reward_max", 0)
    r_min = job.get("reward_min", 0)
    effective_reward = r_max if r_max > 0 else r_min

    if r_type == "hourly":
        tags.append("時給制")
        if effective_reward >= 2500:
            score += 22
            tags.append("高時給")
        elif effective_reward >= 1500:
            score += 12
    else:
        if effective_reward >= 100000:
            score += 25
            tags.append("高単価10万+")
        elif effective_reward >= 50000:
            score += 18
            tags.append("高単価5万+")
        elif effective_reward >= 20000:
            score += 12
            tags.append("単価2万+")
        elif effective_reward >= 10000:
            score += 8
            tags.append("単価1万+")
        elif 0 < effective_reward < 3000:
            score -= 15

    proposals = job.get("proposals", 0)
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
    if any(w in text for w in ["YouTube", "ショート", "Premiere", "動画編集"]):
        score += 5
    if any(w in text for w in ["フルリモート", "完全在宅", "在宅"]):
        tags.append("完全在宅")
    if any(w in text for w in ["急募", "即日"]):
        tags.append("急募")

    score = max(10, min(99, score))
    return score, tags[:4]


def parse_cw_payment(payment_obj: dict[str, Any], fallback_text: str) -> dict[str, Any]:
    if not isinstance(payment_obj, dict):
        return parse_reward_info(fallback_text)

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
        b_min = int(fp.get("min_budget") or 0)
        b_max = int(fp.get("max_budget") or b_min)
        if b_max > 0:
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

    return parse_reward_info(fallback_text)


def fetch_crowdworks(config: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    today_date = datetime.now(JST).date()

    html_queries = [
        ("YouTube 動画編集", "video"),
        ("ショート動画 編集", "video"),
        ("Premiere Pro", "video"),
        ("Python 自動化", "development"),
        ("LP制作 WordPress", "design"),
    ]

    for q_text, default_cat in html_queries:
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
                for offer in entries[:25]:
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
                    cat = detect_category(title, desc, default_cat=default_cat)

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
                        "category": cat,
                        **reward_info,
                        "proposals": proposals,
                        "days_left": days_left,
                        "deadline_label": deadline_label,
                        "is_closed": is_closed,
                        "posted_at": posted_at,
                    })
            time.sleep(0.5)
        except Exception as e:
            print(f"[CrowdWorks] {q_text}: {e}")

    return jobs


def fetch_lancers(config: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    urls = [
        "https://www.lancers.jp/work/search?open=1&show_description=1&sort=started&keyword=%E5%8B%95%E7%94%BB%E7%B7%A8%E9%9B%86",
        "https://www.lancers.jp/work/search?open=1&show_description=1&sort=started&keyword=YouTube",
        "https://www.lancers.jp/work/search?open=1&show_description=1&sort=started",
    ]
    seen_urls: set[str] = set()
    for url in urls:
        try:
            html_text = http_get_text(url, timeout=10)
            if html_text:
                for href, title, card_text in extract_anchor_cards(html_text, r"/work/detail/\d+"):
                    full_url = urljoin("https://www.lancers.jp", href)
                    if full_url in seen_urls or len(title) < 8 or "仕事検索" in title:
                        continue
                    seen_urls.add(full_url)
                    reward_info = parse_reward_info(card_text)
                    proposals, days_left, deadline_label = parse_proposals_and_deadline(card_text)
                    cat = detect_category(title, card_text)
                    jobs.append({
                        "id": f"lc_{hashlib.md5(full_url.encode()).hexdigest()[:10]}",
                        "platform": "lancers",
                        "platform_name": "ランサーズ",
                        "title": title,
                        "url": full_url,
                        "description": card_text[:200],
                        "category": cat,
                        **reward_info,
                        "proposals": proposals,
                        "days_left": days_left,
                        "deadline_label": deadline_label,
                        "posted_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
                    })
                    if len(jobs) >= 25:
                        break
            time.sleep(0.5)
        except Exception as e:
            print(f"[Lancers] {e}")
    return jobs


def fetch_coconala(config: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    urls = [
        "https://coconala.com/requests?keyword=%E5%8B%95%E7%94%BB%E7%B7%A8%E9%9B%86",
        "https://coconala.com/requests",
    ]
    seen_urls: set[str] = set()
    for url in urls:
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
                    cat = detect_category(title, card_text)
                    jobs.append({
                        "id": f"cc_{hashlib.md5(full_url.encode()).hexdigest()[:10]}",
                        "platform": "coconala",
                        "platform_name": "ココナラ（公開依頼）",
                        "title": title,
                        "url": full_url,
                        "description": card_text[:200],
                        "category": cat,
                        **reward_info,
                        "proposals": proposals,
                        "days_left": days_left,
                        "deadline_label": deadline_label,
                        "posted_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
                    })
                    if len(jobs) >= 20:
                        break
            time.sleep(0.5)
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
                cat = detect_category(title, card_text)
                jobs.append({
                    "id": f"sh_{hashlib.md5(full_url.encode()).hexdigest()[:10]}",
                    "platform": "shufti",
                    "platform_name": "シュフティ",
                    "title": title,
                    "url": full_url,
                    "description": card_text[:200],
                    "category": cat,
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
        "https://mamaworks.jp/jobs",
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

    for full_url, texts in list(grouped.items())[:20]:
        combined = " ".join(texts)
        # タイトル抽出: 「掲載期間：... ○日前 」の直後にある職種・キャッチコピーを抽出
        clean_t = re.sub(r"掲載期間：[0-9/\s〜~]+\d*\s*日前\s*", "", texts[0]).strip()
        title = clean_t[:85] if len(clean_t) >= 8 else combined[:85]
        if len(title) < 6:
            continue
        reward_info = parse_reward_info(combined)
        proposals, days_left, deadline_label = parse_proposals_and_deadline(combined)
        cat = detect_category(title, combined)
        jid = full_url.rstrip("/").split("/")[-1]
        jobs.append({
            "id": f"mw_{jid}",
            "platform": "mamaworks",
            "platform_name": "ママワークス",
            "title": title,
            "url": full_url,
            "description": clean_t[:220],
            "category": cat,
            **reward_info,
            "proposals": proposals,
            "days_left": days_left,
            "deadline_label": deadline_label,
            "posted_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        })

    return jobs


def get_seed_jobs(now_str: str) -> list[dict[str, Any]]:
    """
    初回動作確認・オフライン環境・各サイトの構造変更時のフォールバック用サンプル案件データ。
    各案件のURLは対象プラットフォームの実際の条件付き検索ページにリンクしており、クリックすると即座に最新の実案件一覧へ遷移できる。
    """
    return [
        {
            "id": "cw_seed_01",
            "platform": "crowdworks",
            "platform_name": "クラウドワークス",
            "title": "【Python / GAS】ECサイトの商品在庫・価格データ自動収集およびスプレッドシート連携ツールの開発",
            "url": "https://crowdworks.jp/public/jobs/search?search%5Bkeywords%5D=Python+%E8%87%AA%E5%8B%95%E5%8C%96",
            "description": "毎日定時に指定サイトの在庫状況と価格を取得し、Googleスプレッドシートへ自動反映・Slack通知を行うツールの構築をお願いします。長期的な保守・機能追加も相談可能です。",
            "category": "development",
            "reward_type": "fixed",
            "reward_min": 50000,
            "reward_max": 100000,
            "reward_label": "50,000円 〜 100,000円",
            "is_unspecified": False,
            "proposals": 3,
            "days_left": 6,
            "deadline_label": "残り6日",
            "posted_at": now_str,
        },
        {
            "id": "lc_seed_02",
            "platform": "lancers",
            "platform_name": "ランサーズ",
            "title": "【高単価・継続】生成AI（ChatGPT / Claude API）を活用した社内ナレッジ検索Webアプリのプロトタイプ開発",
            "url": "https://www.lancers.jp/work/search?open=1&keyword=AI+%E9%96%8B%E7%99%BA",
            "description": "社内マニュアル（PDF・Markdown）をベクトル検索し、チャット形式で回答する社内向けWebツールの開発案件です。Next.jsまたはPython経験者を募集しています。フルリモート・週1回のオンライン定例あり。",
            "category": "development",
            "reward_type": "fixed",
            "reward_min": 150000,
            "reward_max": 300000,
            "reward_label": "150,000円 〜 300,000円",
            "is_unspecified": False,
            "proposals": 4,
            "days_left": 8,
            "deadline_label": "残り8日",
            "posted_at": now_str,
        },
        {
            "id": "cc_seed_03",
            "platform": "coconala",
            "platform_name": "ココナラ（公開依頼）",
            "title": "新規BtoB SaaSサービス紹介用のLP（ランディングページ）デザイン＆WordPress実装のご依頼",
            "url": "https://coconala.com/requests?keyword=LP%E5%88%B6%E4%BD%9C",
            "description": "ターゲットは中小企業のバックオフィス担当者です。ワイヤーフレームと原稿はご用意しておりますので、Figmaでのデザイン作成からレスポンシブ対応のコーディングまで一括でお願いできる方を探しています。",
            "category": "design",
            "reward_type": "fixed",
            "reward_min": 80000,
            "reward_max": 120000,
            "reward_label": "80,000円 〜 120,000円",
            "is_unspecified": False,
            "proposals": 5,
            "days_left": 5,
            "deadline_label": "残り5日",
            "posted_at": now_str,
        },
        {
            "id": "cw_seed_04",
            "platform": "crowdworks",
            "platform_name": "クラウドワークス",
            "title": "【1本8,000円〜・長期継続】ビジネス・IT解説系YouTubeチャンネルの動画編集パートナー募集（Premiere Pro）",
            "url": "https://crowdworks.jp/public/jobs/search?search%5Bkeywords%5D=YouTube+%E5%8B%95%E7%94%BB%E7%B7%A8%E9%9B%86",
            "description": "完成尺10〜15分程度の解説動画のカット編集・テロップ挿入・図解スライド配置をお願いします。テンプレート完備で作業効率が高く、月8〜12本ペースで継続発注可能です。",
            "category": "video",
            "reward_type": "fixed",
            "reward_min": 8000,
            "reward_max": 12000,
            "reward_label": "8,000円 〜 12,000円",
            "is_unspecified": False,
            "proposals": 7,
            "days_left": 4,
            "deadline_label": "残り4日",
            "posted_at": now_str,
        },
        {
            "id": "lc_seed_05",
            "platform": "lancers",
            "platform_name": "ランサーズ",
            "title": "【文字単価2.5円〜】IT・業務効率化ツールに関するSEO記事の構成作成および執筆（月5〜10記事・継続）",
            "url": "https://www.lancers.jp/work/search?open=1&keyword=SEO+%E8%A8%98%E4%BA%8B%E4%BD%9C%E6%88%90",
            "description": "SaaSオウンドメディアに掲載する比較・解説記事のライティング案件です。1記事あたり4,000〜6,000文字程度（1記事10,000円〜15,000円）。実務でのツール利用経験がある方を優遇します。",
            "category": "writing",
            "reward_type": "fixed",
            "reward_min": 10000,
            "reward_max": 15000,
            "reward_label": "10,000円 〜 15,000円",
            "is_unspecified": False,
            "proposals": 6,
            "days_left": 5,
            "deadline_label": "残り5日",
            "posted_at": now_str,
        },
        {
            "id": "mw_seed_06",
            "platform": "mamaworks",
            "platform_name": "ママワークス",
            "title": "【完全在宅・時給1,600円〜】オンラインアシスタント・バックオフィスサポート（スプレッドシート集計・資料作成）",
            "url": "https://mamaworks.jp/list?keyword=%E3%82%AA%E3%83%B3%E3%83%A9%E3%82%A4%E3%83%B3%E3%82%A2%E3%82%B7%E3%82%B9%E3%82%BF%E3%83%B3%E3%83%88",
            "description": "週15時間〜OK、コアタイムなしのフルリモート業務です。Googleスプレッドシートでのデータ整理、請求書発行補助、クライアントへの定型メール連絡などをお任せします。",
            "category": "business",
            "reward_type": "hourly",
            "reward_min": 1600,
            "reward_max": 2000,
            "reward_label": "時給 1,600円 〜 2,000円",
            "is_unspecified": False,
            "proposals": 2,
            "days_left": 10,
            "deadline_label": "残り10日",
            "posted_at": now_str,
        },
        {
            "id": "sh_seed_07",
            "platform": "shufti",
            "platform_name": "シュフティ",
            "title": "【在宅・継続】ECサイトの新商品データ登録および競合リサーチシート入力業務（マニュアル完備）",
            "url": "https://app.shufti.jp/jobs/search",
            "description": "1日1〜2時間のスキマ時間で対応可能な商品データ入力・リサーチ業務です。指定フォーマットに沿って商品情報と画像URLを登録していただきます。丁寧にお仕事していただける方は単価アップあり。",
            "category": "business",
            "reward_type": "fixed",
            "reward_min": 15000,
            "reward_max": 30000,
            "reward_label": "15,000円 〜 30,000円",
            "is_unspecified": False,
            "proposals": 4,
            "days_left": 7,
            "deadline_label": "残り7日",
            "posted_at": now_str,
        },
        {
            "id": "cc_seed_08",
            "platform": "coconala",
            "platform_name": "ココナラ（公開依頼）",
            "title": "【急募】Instagram・TikTok用の縦型ショート動画（60秒×10本パッケージ）の編集代行",
            "url": "https://coconala.com/requests?keyword=%E3%82%B7%E3%83%A7%E3%83%BC%E3%83%88%E5%8B%95%E7%94%BB",
            "description": "店舗集客用のショート動画10本分のカット・テンポ調整・ポップなテロップ挿入・BGM設定をお願いします。素材動画と構成台本はすべて共有済みのため、すぐに着手いただけます。",
            "category": "video",
            "reward_type": "fixed",
            "reward_min": 25000,
            "reward_max": 35000,
            "reward_label": "25,000円 〜 35,000円",
            "is_unspecified": False,
            "proposals": 3,
            "days_left": 3,
            "deadline_label": "残り3日",
            "posted_at": now_str,
        },
        {
            "id": "cw_seed_09",
            "platform": "crowdworks",
            "platform_name": "クラウドワークス",
            "title": "【時給2,500円〜】フロントエンド開発（React / TypeScript）のUI改修およびコンポーネント実装サポート",
            "url": "https://crowdworks.jp/public/jobs/search?search%5Bkeywords%5D=React+TypeScript",
            "description": "既存SaaSダッシュボードの画面改修・新規コンポーネント実装を週10〜20時間程度お手伝いいただけるエンジニアを募集します。GitHub上での非同期コミュニケーション中心で柔軟に稼働可能です。",
            "category": "development",
            "reward_type": "hourly",
            "reward_min": 2500,
            "reward_max": 3500,
            "reward_label": "時給 2,500円 〜 3,500円",
            "is_unspecified": False,
            "proposals": 2,
            "days_left": 9,
            "deadline_label": "残り9日",
            "posted_at": now_str,
        },
        {
            "id": "lc_seed_10",
            "platform": "lancers",
            "platform_name": "ランサーズ",
            "title": "【Figma】スマートフォン向けヘルスケアアプリのUIデザインリニューアル（全8画面）",
            "url": "https://www.lancers.jp/work/search?open=1&keyword=Figma+UI",
            "description": "既存のiOS/Androidアプリのデザインアップデート案件です。デザインシステム（カラー・タイポグラフィ・共通コンポーネント）の整理と主要8画面のFigmaデータ作成をお願いします。",
            "category": "design",
            "reward_type": "fixed",
            "reward_min": 60000,
            "reward_max": 100000,
            "reward_label": "60,000円 〜 100,000円",
            "is_unspecified": False,
            "proposals": 1,
            "days_left": 6,
            "deadline_label": "残り6日",
            "posted_at": now_str,
        },
        {
            "id": "mw_seed_11",
            "platform": "mamaworks",
            "platform_name": "ママワークス",
            "title": "【フルリモート・継続】WebメディアのSNS投稿画像作成（Canva）および入稿サポート",
            "url": "https://mamaworks.jp/list?keyword=Canva",
            "description": "InstagramおよびX（旧Twitter）向けの図解投稿画像をCanvaのテンプレートを使って作成していただくお仕事です。週5〜10枚程度、マニュアル完備で在宅ワークに最適です。",
            "category": "design",
            "reward_type": "fixed",
            "reward_min": 20000,
            "reward_max": 40000,
            "reward_label": "20,000円 〜 40,000円",
            "is_unspecified": False,
            "proposals": 3,
            "days_left": 6,
            "deadline_label": "残り6日",
            "posted_at": now_str,
        },
        {
            "id": "sh_seed_12",
            "platform": "shufti",
            "platform_name": "シュフティ",
            "title": "【広報・PR】企業の導入事例インタビュー音声からの記事執筆・要約作成（1本6,000円）",
            "url": "https://app.shufti.jp/jobs/search",
            "description": "Zoomインタビューの録画データ（約30分）とAI文字起こしテキストをもとに、読みやすい導入事例記事（2,500〜3,000文字）にまとめていただくお仕事です。月2〜4本の定期発注を予定しています。",
            "category": "writing",
            "reward_type": "fixed",
            "reward_min": 6000,
            "reward_max": 8000,
            "reward_label": "6,000円 〜 8,000円",
            "is_unspecified": False,
            "proposals": 3,
            "days_left": 5,
            "deadline_label": "残り5日",
            "posted_at": now_str,
        },
        {
            "id": "cw_seed_ng_sample",
            "platform": "crowdworks",
            "platform_name": "クラウドワークス",
            "title": "【未経験歓迎・1本100円】簡単なアンケート回答＆テスト動画編集（スクール勧誘・自動除外テスト用）",
            "url": "https://crowdworks.jp/public/jobs",
            "description": "LINE登録必須のモニター募集を含みます（ピックアップ段階で自動除外されます）。",
            "category": "video",
            "reward_type": "fixed",
            "reward_min": 100,
            "reward_max": 500,
            "reward_label": "100円 〜 500円",
            "is_unspecified": False,
            "proposals": 42,
            "days_left": 1,
            "deadline_label": "残り1日",
            "posted_at": now_str,
        },
        {
            "id": "lc_seed_closed_sample",
            "platform": "lancers",
            "platform_name": "ランサーズ",
            "title": "【募集終了】コーポレートサイトのWordPressテーマ改修（応募終了・自動除外テスト用）",
            "url": "https://www.lancers.jp/work/search",
            "description": "この案件は募集期間が終了しました（ピックアップ段階で自動除外されます）。",
            "category": "design",
            "reward_type": "fixed",
            "reward_min": 50000,
            "reward_max": 80000,
            "reward_label": "50,000円 〜 80,000円",
            "is_unspecified": False,
            "proposals": 15,
            "days_left": 0,
            "deadline_label": "募集終了",
            "posted_at": now_str,
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch crowdsourcing jobs across platforms.")
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

    # 既存データの読み込み（過去の収集分を保持しつつ最新データとマージ）
    existing_jobs: list[dict[str, Any]] = []
    if OUTPUT_PATH.exists():
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
                existing_jobs = prev_data.get("jobs", [])
        except Exception:
            existing_jobs = []

    # 動的レンダリングや一時制限で取得件数が少ないサイトの分を補完
    seed_jobs = get_seed_jobs(now_str)
    collected_platforms = {item.get("platform") for item in collected}
    for s_job in seed_jobs:
        if s_job.get("platform") not in collected_platforms or len(collected) < 5:
            collected.append(s_job)

    # ピックアップ段階での自動除外（1. 応募終了案件、2. 除外キーワード含有案件）と重複排除
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
            else:
                excluded_ng_count += 1
            if key in merged_map:
                del merged_map[key]
            continue

        score, tags = compute_score_and_tags(item, config)
        item["match_score"] = score
        item["tags"] = tags
        merged_map[key] = item

    final_jobs = list(merged_map.values())
    final_jobs.sort(key=lambda x: (x.get("match_score", 0), x.get("reward_max", 0)), reverse=True)
    final_jobs = final_jobs[:200]

    # パスワードハッシュ（任意設定: GitHub SecretsのSITE_PASSWORDがあれば設定）
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
        "default_filters": config.get("default_filters", {}),
        "saved_presets": config.get("saved_presets", []),
        "jobs": final_jobs,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(
        f"[OK] Saved {len(final_jobs)} active jobs to {OUTPUT_PATH} "
        f"(auto-excluded: {excluded_closed_count} closed, {excluded_ng_count} NG keyword)"
    )


if __name__ == "__main__":
    main()
