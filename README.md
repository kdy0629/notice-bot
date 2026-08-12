# 학교 공지 알림 (GitHub Actions)

학교 게시판에 새 공지가 올라오면 디스코드로 알려줍니다.
GitHub Actions 가 10분마다 대신 확인하므로 **내 PC가 꺼져 있어도 알림이 옵니다.**

```
GitHub Actions (10분마다)  →  게시판 확인  →  새 글이 있으면  →  디스코드 웹훅
```

---

## 설정 순서

### 1단계 — 디스코드 웹훅 만들기

1. 알림을 받을 채널에 마우스를 올리고 **⚙️ 채널 편집**
2. 왼쪽 **연동 → 웹후크 → 새 웹후크**
3. 이름을 정하고 (예: `공지알림`) **웹후크 URL 복사**

> 이 URL 을 아는 사람은 누구나 채널에 글을 쓸 수 있습니다.
> 채팅에 붙여넣거나 저장소에 커밋하지 마세요. 3단계에서 Secrets 로만 등록합니다.

---

### 2단계 — GitHub 저장소에 올리기

저장소는 **공개(Public)** 를 권장합니다.
비공개는 Actions 무료 사용량이 월 2,000분이라 10분 간격이면 한도를 넘깁니다. 공개는 무제한입니다.

공개해도 위험하지 않습니다. 올라가는 건 코드와 공지 링크 목록뿐이고,
웹훅 주소는 Secrets 에 들어가 저장소에 남지 않습니다.

```bash
git init
git add .
git commit -m "학교 공지 알림 봇"
git branch -M main
git remote add origin https://github.com/<계정명>/notice-bot.git
git push -u origin main
```

---

### 3단계 — 웹훅 주소를 Secrets 에 등록

1. 저장소 페이지 → **Settings** → 왼쪽 **Secrets and variables → Actions**
2. **New repository secret** 클릭
3. 이름은 정확히 아래와 같이 입력

```
Name:   DISCORD_WEBHOOK_URL
Secret: (1단계에서 복사한 웹후크 URL)
```

---

### 4단계 — 첫 실행

1. 저장소의 **Actions** 탭 → 초록 버튼으로 워크플로 활성화
2. 왼쪽에서 **공지 확인** 선택 → 우측 **Run workflow** 로 수동 실행

**첫 실행에는 알림이 오지 않습니다.** 기존 공지가 한꺼번에 쏟아지는 걸 막기 위해
현재 목록을 기준선으로만 저장합니다. 이후 새로 올라오는 글부터 알림이 옵니다.

기준선은 `seen.json` 에 저장되고, 워크플로가 매번 저장소에 다시 커밋합니다.
저장소에 `chore: 확인한 공지 기록 갱신` 커밋이 보이면 정상 동작 중이라는 뜻입니다.

이제 끝입니다. 이후로는 10분마다 알아서 돌아갑니다.

---

## 감시 대상 바꾸기

`config.json` 을 수정하고 커밋하면 됩니다.

```json
{
  "board_name": "가천대 장학공지",
  "board_url": "https://www.gachon.ac.kr/kor/1146/subview.do",
  "selectors": { "row": "form > div.scroll-table > table.board-table.horizon1 > tbody > tr" },
  "check_interval_minutes": 10,
  "max_notify_per_check": 5,
  "keywords": []
}
```

### 가천대 다른 게시판

`board_url` 만 바꾸면 됩니다. 셀렉터는 구조가 같아 그대로 동작합니다.

| 게시판 | board_url |
|---|---|
| 학사공지 | `https://www.gachon.ac.kr/kor/3104/subview.do` |
| 전체공지 | `https://www.gachon.ac.kr/kor/7986/subview.do` |
| 장학공지 | `https://www.gachon.ac.kr/kor/1146/subview.do` |
| 취업공지 | `https://www.gachon.ac.kr/kor/1148/subview.do` |
| 비교과공지 | `https://www.gachon.ac.kr/kor/7943/subview.do` |
| 기타공지 | `https://www.gachon.ac.kr/kor/4006/subview.do` |

게시판을 바꿨다면 `seen.json` 을 삭제하고 커밋하세요. 기준선이 새로 잡힙니다.

### 다른 사이트 (학과 홈페이지 등)

셀렉터를 새로 찾아야 합니다. 아래 명령이 자동으로 찾아줍니다.

```
py inspect_board.py "https://감시할/게시판/주소"
```

후보가 점수순으로 나오고 각 후보마다 실제 추출된 제목이 미리보기로 표시됩니다.
**미리보기가 실제 공지 목록과 일치하는 후보**의 `"row"` 값을 `config.json` 에 넣으세요.

### 특정 키워드만 받기

제목에 해당 단어가 들어간 공지만 알립니다. 비워두면 전부 알립니다.

```json
"keywords": ["장학", "수강신청", "졸업"]
```

### 확인 주기 조정

`.github/workflows/check-notices.yml` 의 cron 값을 바꿉니다.

```yaml
- cron: '*/10 * * * *'   # 10분마다
- cron: '*/30 * * * *'   # 30분마다
```

GitHub 의 최소 간격은 5분입니다. 그보다 짧게 걸어도 무시됩니다.

---

## 로컬에서 시험해보기

푸시 전에 동작을 확인하고 싶다면:

1. `.env` 파일을 만들어 웹훅 주소를 넣습니다 (`.gitignore` 에 있어 커밋되지 않습니다)

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

2. 패키지를 설치하고 실행합니다

```
py -m pip install -r requirements.txt
```

3. `run_local.bat` 더블클릭

---

## 알아둘 점

**실행이 정시에 안 됩니다.**
GitHub 부하에 따라 10분 간격이어도 20~30분씩 밀릴 수 있습니다. 공식적으로 보장되지 않는 부분입니다.

**60일간 저장소에 활동이 없으면 스케줄이 자동 중지됩니다.**
GitHub 이 미리 메일로 알려주고, 버튼 한 번으로 다시 켤 수 있습니다.
다만 이 봇은 `seen.json` 을 계속 커밋하므로 실제로 멈출 일은 드뭅니다.

**가끔 워크플로가 빨갛게 실패할 수 있습니다.**
학교 서버가 잠깐 응답하지 않는 경우인데, 3번까지 재시도하도록 해두었습니다.
그래도 실패하면 다음 실행에서 자동으로 복구되니 무시하셔도 됩니다.
실패 메일이 거슬리면 GitHub **Settings → Notifications → Actions** 에서 끌 수 있습니다.

---

## 문제 해결

**알림이 안 옴**
→ Actions 탭에서 최근 실행 로그를 확인하세요. `새 공지 없음` 이면 정상 동작 중입니다.

**`글을 하나도 찾지 못했습니다` 로그**
→ 게시판 구조가 바뀌었거나 셀렉터가 맞지 않습니다. `inspect_board.py` 를 다시 실행하세요.

**`웹훅 전송 실패 401`**
→ Secrets 의 `DISCORD_WEBHOOK_URL` 이 잘못되었거나 웹훅이 삭제되었습니다.

**같은 공지가 또 옴**
→ `seen.json` 커밋이 실패하고 있을 수 있습니다.
   Actions 로그의 `확인 기록 저장` 단계를 확인하세요.

**알림을 처음부터 다시 받고 싶음**
→ `seen.json` 을 삭제하고 커밋하면 기준선이 초기화됩니다.

**`inspect_board.py` 가 목록을 못 찾음**
→ JavaScript 로 목록을 그리는 사이트입니다. 브라우저 `F12 → Network` 탭에서
   새로고침 시 나타나는 JSON 요청 주소를 찾으면 대응할 수 있습니다.
