# 🔔 YouTube → Slack 알림 봇

구독 채널의 새 영상이 올라오면 Slack으로 알림을 보내는 봇입니다.

---

## 📋 사전 준비

### 1. YouTube Data API 키 발급

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 (또는 기존 프로젝트 선택)
3. **API 및 서비스** → **라이브러리** 클릭
4. "YouTube Data API v3" 검색 → **사용 설정**
5. **API 및 서비스** → **사용자 인증 정보** 클릭
6. **+ 사용자 인증 정보 만들기** → **API 키** 선택
7. 생성된 API 키 복사 (예: `AIzaSy...`)

> ⚠️ **무료 할당량**: 하루 10,000 유닛 (채널당 영상 확인 = 약 100 유닛)

---

### 2. Slack Incoming Webhook 설정

1. [Slack API](https://api.slack.com/apps) 접속
2. **Create New App** → **From scratch** 선택
3. App 이름 입력 (예: "YouTube 알림 봇"), Workspace 선택
4. 좌측 메뉴에서 **Incoming Webhooks** 클릭
5. **Activate Incoming Webhooks** 토글 ON
6. **Add New Webhook to Workspace** 클릭
7. 알림 받을 채널 선택 (예: #youtube-alerts)
8. Webhook URL 복사 (예: `https://hooks.slack.com/services/T.../B.../xxx`)

---

## 🚀 로컬 실행 방법

### 1. 환경 변수 설정

`.env` 파일 생성:

```bash
YOUTUBE_API_KEY=your_youtube_api_key_here
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/xxx/xxx
```

### 2. 의존성 설치

```bash
pip install google-api-python-client python-dotenv requests
```

### 3. 실행

```bash
python youtube_slack_bot.py
```

---

## ☁️ GitHub Actions로 자동화 (1시간마다 실행)

### 1. GitHub 저장소 생성

1. GitHub에서 새 저장소 생성
2. 아래 파일들을 저장소에 업로드:
   - `youtube_slack_bot.py`
   - `channels.json`
   - `.github/workflows/youtube-notify.yml`

### 2. GitHub Secrets 설정

저장소 **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Name | Value |
|------|-------|
| `YOUTUBE_API_KEY` | YouTube API 키 |
| `SLACK_WEBHOOK_URL` | Slack Webhook URL |

### 3. 완료!

GitHub Actions가 1시간마다 자동으로 실행됩니다.

---

## 📁 파일 구조

```
youtube-slack-bot/
├── youtube_slack_bot.py    # 메인 스크립트
├── channels.json           # 구독 채널 목록
├── last_checked.json       # 마지막 확인 시간 (자동 생성)
├── .env                    # 환경 변수 (로컬용)
├── .github/
│   └── workflows/
│       └── youtube-notify.yml  # GitHub Actions 워크플로우
└── README.md
```

---

## ➕ 채널 추가/제거

`channels.json` 파일에서 채널을 추가하거나 제거하세요:

```json
{
  "channels": [
    {
      "name": "Stanford Online",
      "channel_id": "UCBa5G_ESCn8Yd4vw5U-gIcg"
    },
    {
      "name": "새 채널",
      "channel_id": "UC..."
    }
  ]
}
```

### 채널 ID 찾는 방법

1. 유튜브 채널 페이지 접속
2. 브라우저 URL 확인:
   - `youtube.com/channel/UC...` → `UC...` 부분이 채널 ID
   - `youtube.com/@username` → 페이지 소스에서 `channelId` 검색

또는 [이 사이트](https://commentpicker.com/youtube-channel-id.php)에서 URL로 검색

---

## 🛠️ 문제 해결

### API 할당량 초과
- 채널 수를 줄이거나 실행 주기를 늘리세요
- Google Cloud Console에서 할당량 확인 가능

### Slack 알림이 안 옴
- Webhook URL이 올바른지 확인
- Slack 앱이 채널에 초대되었는지 확인

### 중복 알림
- `last_checked.json` 파일 삭제 후 재실행
