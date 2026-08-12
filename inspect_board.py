"""게시판 URL을 분석해서 config.json에 넣을 CSS 셀렉터 후보를 찾아준다.

사용법:
    py inspect_board.py "https://학교주소/공지사항"
"""

import re
import sys
from collections import Counter
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 게시판 목록의 결정적 단서는 "행마다 붙은 작성일"이다.
# 느슨하게 잡으면 학기 표기(26-2) 같은 것까지 날짜로 오인하므로 연-월-일만 인정한다.
DATE_PATTERN = re.compile(r"\d{4}[-./]\s?\d{1,2}[-./]\s?\d{1,2}")

# 네비게이션 메뉴는 링크가 많아 게시판으로 오인되기 쉽다.
NAV_HINT = re.compile(r"gnb|lnb|snb|nav|menu|footer|header|breadcrumb|sitemap|tab", re.I)


def css_path(el):
    """요소를 가리키는 짧은 CSS 셀렉터를 만든다."""
    parts = []
    cur = el
    for _ in range(4):
        if cur is None or cur.name in ("html", "[document]"):
            break
        seg = cur.name
        classes = [c for c in (cur.get("class") or []) if not c.isdigit()]
        if cur.get("id"):
            parts.append(f"#{cur['id']}")
            break
        if classes:
            seg += "." + ".".join(classes[:2])
        parts.append(seg)
        cur = cur.parent
    return " > ".join(reversed(parts))


def is_navish(el):
    """요소가 네비게이션/헤더/푸터 안에 있는지 본다."""
    cur = el
    for _ in range(5):
        if cur is None or not hasattr(cur, "get"):
            break
        if cur.name in ("nav", "header", "footer"):
            return True
        ident = " ".join([cur.get("id") or ""] + (cur.get("class") or []))
        if ident and NAV_HINT.search(ident):
            return True
        cur = cur.parent
    return False


def score_group(parent, main_tag, rows):
    """행 묶음이 게시판 목록처럼 보이는 정도를 점수화한다."""
    if len(rows) < 3:
        return 0

    linked = 0
    dated = 0
    titles = []
    for row in rows:
        a = row.find("a", href=True)
        if not a:
            continue
        text = a.get_text(strip=True)
        if len(text) < 4:
            continue
        linked += 1
        titles.append(text)
        if DATE_PATTERN.search(row.get_text(" ", strip=True)):
            dated += 1

    if linked < 3:
        return 0

    # 링크 개수는 상한을 둔다. 메뉴처럼 항목만 많은 묶음이 1위를 먹는 걸 막기 위함이다.
    score = min(linked, 20) * 5

    # 행마다 작성일이 붙어 있으면 게시판일 확률이 결정적으로 높아진다.
    score += int(dated / linked * 150)

    # 표 형태의 tr 묶음은 전형적인 게시판 구조다.
    if main_tag == "tr":
        score += 20

    # 제목이 중복되면 메뉴이거나 반복 위젯이다.
    if len(set(titles)) < len(titles) * 0.7:
        score -= 40

    if is_navish(parent):
        score -= 100

    return max(score, 0)


def find_candidates(soup):
    """부모별로 같은 태그의 형제들을 묶어 목록 후보를 만든다."""
    groups = []
    for parent in soup.find_all(["tbody", "ul", "ol", "div", "table"]):
        children = [c for c in parent.find_all(recursive=False) if c.name in ("tr", "li", "div", "dl")]
        if len(children) < 3:
            continue
        tag_counts = Counter(c.name for c in children)
        main_tag, count = tag_counts.most_common(1)[0]
        if count < 3:
            continue
        rows = [c for c in children if c.name == main_tag]
        s = score_group(parent, main_tag, rows)
        if s > 0:
            groups.append((s, parent, main_tag, rows))
    groups.sort(key=lambda g: g[0], reverse=True)
    return groups


def describe(parent, main_tag, rows, base_url):
    selector = f"{css_path(parent)} > {main_tag}"
    samples = []
    for row in rows[:5]:
        a = row.find("a", href=True)
        if not a:
            continue
        text = a.get_text(strip=True)
        link = urljoin(base_url, a["href"])
        m = DATE_PATTERN.search(row.get_text(" ", strip=True))
        samples.append((text, link, m.group(0) if m else ""))
    return selector, samples


def main():
    if len(sys.argv) < 2:
        print('사용법: py inspect_board.py "게시판 URL"')
        sys.exit(1)

    url = sys.argv[1]
    print(f"[*] 접속 중: {url}\n")

    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        res.raise_for_status()
    except Exception as e:
        print(f"[!] 접속 실패: {e}")
        sys.exit(1)

    res.encoding = res.apparent_encoding or res.encoding
    soup = BeautifulSoup(res.text, "lxml")

    title = soup.title.get_text(strip=True) if soup.title else "(제목 없음)"
    print(f"[*] 페이지 제목: {title}")
    print(f"[*] 응답 크기: {len(res.text):,} bytes\n")

    # 로그인 페이지로 튕겼는지 간단히 확인
    lowered = res.text.lower()
    if any(k in lowered for k in ("login", "signin", "로그인")) and len(res.text) < 30000:
        print("[!] 로그인 페이지일 가능성이 있습니다. 시크릿 모드로 확인해 보세요.\n")

    groups = find_candidates(soup)
    if not groups:
        print("[!] 게시판 목록 구조를 찾지 못했습니다.")
        print("    JavaScript로 목록을 그리는 사이트일 수 있습니다.")
        print("    브라우저 F12 → Network 탭에서 JSON 요청이 있는지 확인해 보세요.")
        return

    print(f"[*] 목록 후보 {len(groups)}개를 찾았습니다. 점수순으로 표시합니다.\n")
    print("=" * 70)

    for i, (score, parent, main_tag, rows) in enumerate(groups[:3], 1):
        selector, samples = describe(parent, main_tag, rows, url)
        print(f"\n[후보 {i}]  점수 {score}  |  행 개수 {len(rows)}")
        print(f'  "row": "{selector}"')
        print("  ── 추출된 글 미리보기 ──")
        for text, link, date in samples:
            date_str = f"  ({date})" if date else ""
            print(f"    · {text[:50]}{date_str}")
            print(f"      {link[:90]}")

    print("\n" + "=" * 70)
    print("\n[>] 미리보기가 실제 공지 목록과 일치하는 후보를 골라,")
    print("    위의 \"row\" 값을 config.json 의 selectors.row 에 그대로 넣으세요.")
    print("    board_url 에는 방금 사용한 주소를 넣으면 됩니다.")


if __name__ == "__main__":
    main()
