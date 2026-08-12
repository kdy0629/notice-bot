"""게시판을 확인해 새 공지가 있으면 디스코드 웹훅으로 알린다.

한 번 실행하고 끝나는 스크립트다. GitHub Actions 가 주기적으로 실행한다.
로컬에서 시험하려면 .env 에 DISCORD_WEBHOOK_URL 을 넣고 실행하면 된다.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
SEEN_PATH = BASE_DIR / "seen.json"

KST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

DATE_PATTERN = re.compile(r"\d{4}[-./]\s?\d{1,2}[-./]\s?\d{1,2}")

# 디스코드는 메시지 하나에 임베드를 10개까지만 받는다
EMBEDS_PER_MESSAGE = 10


def log(msg):
    print(f"[{datetime.now(KST):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def load_env_file():
    """로컬 실행 편의를 위해 .env 를 읽는다. Actions 에서는 없어도 그만이다."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_seen():
    """이미 알린 공지 링크를 오래된 것부터 순서대로 돌려준다."""
    if not SEEN_PATH.exists():
        return []
    try:
        data = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else list(data)
    except (json.JSONDecodeError, OSError):
        log("seen.json 을 읽지 못했습니다. 빈 목록으로 시작합니다.")
        return []


def save_seen(links):
    # 순서를 지켜야 한다. 집합으로 다루면 잘라낼 때 최근 공지가 날아가고
    # 오래된 것이 남아, 이미 알린 공지를 다시 알리는 사고가 난다.
    seen_set = set()
    ordered = []
    for link in links:
        if link not in seen_set:
            seen_set.add(link)
            ordered.append(link)
    SEEN_PATH.write_text(
        json.dumps(ordered[-500:], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def fetch_html(board_url, attempts=3):
    """학교 서버가 잠깐 흔들리는 정도로 워크플로가 실패하지 않도록 재시도한다."""
    last_error = None
    for i in range(attempts):
        try:
            res = requests.get(board_url, headers=HEADERS, timeout=20)
            res.raise_for_status()
            res.encoding = res.apparent_encoding or res.encoding
            return res.text
        except requests.RequestException as e:
            last_error = e
            if i < attempts - 1:
                wait = 5 * (i + 1)
                log(f"접속 실패 ({e}). {wait}초 후 재시도합니다.")
                time.sleep(wait)
    raise last_error


def fetch_notices(board_url, selectors):
    """게시판을 긁어 공지 목록을 [{title, link, date}, ...] 로 돌려준다."""
    soup = BeautifulSoup(fetch_html(board_url), "lxml")

    notices = []
    for row in soup.select(selectors.get("row", "")):
        link_sel = selectors.get("link", "")
        anchor = row.select_one(link_sel) if link_sel else row.find("a", href=True)
        if not anchor or not anchor.get("href"):
            continue

        title_sel = selectors.get("title", "")
        if title_sel:
            title_el = row.select_one(title_sel)
            title = title_el.get_text(strip=True) if title_el else anchor.get_text(strip=True)
        else:
            title = anchor.get_text(strip=True)

        title = re.sub(r"\s+", " ", title).strip()
        if len(title) < 2:
            continue

        date_sel = selectors.get("date", "")
        if date_sel:
            date_el = row.select_one(date_sel)
            date = date_el.get_text(strip=True) if date_el else ""
        else:
            m = DATE_PATTERN.search(row.get_text(" ", strip=True))
            date = m.group(0) if m else ""

        notices.append(
            {"title": title, "link": urljoin(board_url, anchor["href"]), "date": date}
        )

    return notices


def build_embed(notice, board_name):
    embed = {
        "title": notice["title"][:250],
        "url": notice["link"],
        "color": 0x2B7FFF,
        "author": {"name": f"📢 {board_name}"},
        "footer": {"text": "새 공지가 등록되었습니다"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if notice["date"]:
        embed["fields"] = [{"name": "작성일", "value": notice["date"], "inline": True}]
    return embed


def send_webhook(webhook_url, embeds, fallback_content=None):
    for i in range(0, len(embeds), EMBEDS_PER_MESSAGE):
        chunk = embeds[i : i + EMBEDS_PER_MESSAGE]
        payload = {"embeds": chunk}
        if fallback_content and i == 0:
            payload["content"] = fallback_content
        res = requests.post(webhook_url, json=payload, timeout=20)
        if res.status_code >= 400:
            raise RuntimeError(f"웹훅 전송 실패 {res.status_code}: {res.text[:200]}")


def main():
    load_env_file()

    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    board_name = config.get("board_name", "공지사항")
    board_url = config.get("board_url", "").strip()
    selectors = config.get("selectors", {})
    max_notify = int(config.get("max_notify_per_check", 5))
    keywords = [k.strip().lower() for k in config.get("keywords", []) if k.strip()]

    problems = []
    if not webhook_url:
        problems.append(
            "DISCORD_WEBHOOK_URL 이 없습니다. "
            "(GitHub 은 Secrets, 로컬은 .env 에 넣어주세요)"
        )
    if not board_url:
        problems.append("config.json 의 board_url 이 비어 있습니다.")
    if not selectors.get("row"):
        problems.append("config.json 의 selectors.row 가 비어 있습니다.")
    if problems:
        for p in problems:
            log(f"[설정 오류] {p}")
        sys.exit(1)

    log(f"확인 중: {board_url}")

    try:
        notices = fetch_notices(board_url, selectors)
    except Exception as e:
        log(f"게시판 확인 실패: {e}")
        sys.exit(1)

    if not notices:
        log("글을 하나도 찾지 못했습니다. selectors.row 를 확인하세요.")
        sys.exit(1)

    first_run = not SEEN_PATH.exists()
    seen_list = load_seen()
    seen = set(seen_list)
    fresh = [n for n in notices if n["link"] not in seen]

    if first_run:
        # 첫 실행에 기존 공지를 전부 쏟아내지 않도록 기준선만 기록한다.
        # 게시판은 최신순이므로 뒤집어서 오래된 것부터 쌓는다.
        save_seen([n["link"] for n in reversed(notices)])
        log(f"첫 실행: 기존 공지 {len(notices)}건을 기준선으로 저장했습니다.")
        return

    if not fresh:
        log(f"새 공지 없음 (총 {len(notices)}건 확인)")
        return

    targets = fresh
    if keywords:
        targets = [n for n in fresh if any(k in n["title"].lower() for k in keywords)]

    log(f"새 공지 {len(fresh)}건 발견, 알림 대상 {len(targets)}건")

    if targets:
        # 게시판이 통째로 갱신된 경우 폭탄 전송을 막는다
        picked = targets[:max_notify]
        skipped = len(targets) - len(picked)
        embeds = [build_embed(n, board_name) for n in reversed(picked)]
        note = (
            f"⚠️ 새 공지가 많아 {skipped}건은 생략했습니다. {board_url}"
            if skipped
            else None
        )
        try:
            send_webhook(webhook_url, embeds, fallback_content=note)
        except Exception as e:
            log(f"전송 실패: {e}")
            # 기록을 남기지 않고 종료해야 다음 실행에서 다시 시도한다
            sys.exit(1)
        for n in picked:
            log(f"  전송: {n['title'][:50]}")

    # 알림을 보냈든 키워드에 걸러졌든, 확인한 글은 모두 기록해 재알림을 막는다
    seen_list.extend(n["link"] for n in reversed(fresh))
    save_seen(seen_list)


if __name__ == "__main__":
    main()
