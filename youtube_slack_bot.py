#!/usr/bin/env python3
"""
YouTube → Slack 알림 봇 (with Claude AI 블로그 적합성 판단)
구독 채널의 새 영상이 올라오면 Claude가 블로그 적합성을 판단하고 Slack으로 알림을 보냅니다.
"""

import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path
from googleapiclient.discovery import build
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 설정
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# 파일 경로
SCRIPT_DIR = Path(__file__).parent
CHANNELS_FILE = SCRIPT_DIR / "channels.json"
LAST_CHECKED_FILE = SCRIPT_DIR / "last_checked.json"

# 블로그 적합성 판단 프롬프트 (youtube-to-blog 스킬 기준)
BLOG_EVALUATION_PROMPT = """당신은 유튜브 영상을 칼럼 톤 블로그 글로 변환하는 전문가입니다.

다음 YouTube 영상이 블로그 글로 작성하기에 적합한지 판단해주세요.

## 블로그 적합성 기준

### ✅ 블로그로 쓰기 좋은 영상
- 명확한 주장이나 인사이트가 있음
- 독자에게 전달할 메시지가 있음
- 정보가 구조화되어 있거나 구조화 가능함
- 시의성 있는 주제 (트렌드, 이슈)
- 깊이 있는 분석이나 관점 제시

### ❌ 블로그로 쓰기 애매한 영상
| 유형 | 이유 |
|------|------|
| 단순 홍보/광고 | 정보성 없음, 일시적 |
| 잡담/수다 | 핵심 메시지 없음 |
| 음악/엔터 | 텍스트로 전달 불가 |
| 튜토리얼 (단순 클릭 따라하기) | 영상이 더 효과적 |
| 실시간 반응/게임 플레이 | 맥락 없는 순간들 |
| 1분 미만 쇼츠 | 확장할 내용 부족 |
| 3시간+ 팟캐스트 (주제 분산) | 핵심 추출 어려움 |

## 영상 유형 분류
- **인터뷰/대담**: 팟캐스트, 토크쇼, 컨퍼런스
- **강연/교육**: TED, 강의, 튜토리얼
- **뉴스/분석**: 시사, 트렌드, 리뷰
- **브이로그/체험**: 여행, 일상, 체험
- **다큐/스토리**: 다큐멘터리, 역사

## 영상 정보
- **제목**: {title}
- **채널**: {channel}
- **설명**: {description}

## 판단 결과
다음 JSON 형식으로만 응답하세요:
{{
    "is_suitable": true/false,
    "score": 1-10,
    "video_type": "인터뷰/대담" | "강연/교육" | "뉴스/분석" | "브이로그/체험" | "다큐/스토리" | "기타",
    "reason": "판단 이유 (1-2문장)",
    "blog_angle": "칼럼 톤으로 작성한다면 어떤 관점/질문으로 접근할 수 있는지 (적합한 경우만)",
    "key_message": "이 영상의 핵심 메시지 (1문장)"
}}
"""


def load_channels():
    """채널 목록 로드"""
    if not CHANNELS_FILE.exists():
        print(f"❌ {CHANNELS_FILE} 파일이 없습니다.")
        return []

    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("channels", [])


def load_last_checked():
    """마지막 확인 시간 로드"""
    if not LAST_CHECKED_FILE.exists():
        return {}

    with open(LAST_CHECKED_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_last_checked(data):
    """마지막 확인 시간 저장"""
    with open(LAST_CHECKED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_latest_videos(youtube, channel_id, max_results=5):
    """채널의 최신 영상 목록 가져오기"""
    try:
        # 채널의 uploads playlist ID 가져오기
        channel_response = youtube.channels().list(
            part="contentDetails",
            id=channel_id
        ).execute()

        if not channel_response.get("items"):
            print(f"⚠️ 채널을 찾을 수 없습니다: {channel_id}")
            return []

        uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # 최신 영상 목록 가져오기
        playlist_response = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=max_results
        ).execute()

        videos = []
        for item in playlist_response.get("items", []):
            snippet = item["snippet"]
            videos.append({
                "video_id": snippet["resourceId"]["videoId"],
                "title": snippet["title"],
                "description": snippet["description"][:500] if len(snippet["description"]) > 500 else snippet["description"],
                "published_at": snippet["publishedAt"],
                "thumbnail": snippet["thumbnails"].get("high", snippet["thumbnails"].get("default", {})).get("url", ""),
                "channel_title": snippet["channelTitle"]
            })

        return videos

    except Exception as e:
        print(f"❌ 영상 목록 가져오기 실패 ({channel_id}): {e}")
        return []


def evaluate_blog_suitability(video, channel_name):
    """Claude API로 블로그 적합성 판단"""
    if not ANTHROPIC_API_KEY:
        print("⚠️ ANTHROPIC_API_KEY가 없어 블로그 적합성 판단을 건너뜁니다.")
        return None

    prompt = BLOG_EVALUATION_PROMPT.format(
        title=video["title"],
        channel=channel_name,
        description=video["description"]
    )

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 500,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            content = result["content"][0]["text"]

            # JSON 파싱 시도
            try:
                # JSON 부분만 추출
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    evaluation = json.loads(content[json_start:json_end])
                    return evaluation
            except json.JSONDecodeError:
                print(f"⚠️ JSON 파싱 실패: {content}")
                return None
        else:
            print(f"❌ Claude API 오류: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"❌ Claude API 호출 실패: {e}")
        return None


def send_slack_notification(video, channel_name, evaluation=None):
    """Slack으로 알림 전송 (블로그 적합성 포함)"""
    video_url = f"https://www.youtube.com/watch?v={video['video_id']}"

    # 블로그 적합성 판단 결과 포맷팅
    if evaluation:
        is_suitable = evaluation.get("is_suitable", False)
        score = evaluation.get("score", 0)
        video_type = evaluation.get("video_type", "기타")
        reason = evaluation.get("reason", "")
        blog_angle = evaluation.get("blog_angle", "")
        key_message = evaluation.get("key_message", "")

        if is_suitable:
            eval_emoji = "✅"
            eval_text = f"*블로그 추천!* (점수: {score}/10)"
            eval_detail = f"🎬 유형: {video_type}\n💬 핵심: {key_message}\n💡 이유: {reason}"
            if blog_angle:
                eval_detail += f"\n✍️ 칼럼 관점: {blog_angle}"
        else:
            eval_emoji = "⏭️"
            eval_text = f"*스킵 권장* (점수: {score}/10)"
            eval_detail = f"🎬 유형: {video_type}\n💡 이유: {reason}"
    else:
        eval_emoji = "❓"
        eval_text = "*판단 불가*"
        eval_detail = "Claude API 연동 필요"

    # Slack 메시지 구성 (Block Kit)
    message = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🎬 *{channel_name}* 새 영상 업로드!"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*<{video_url}|{video['title']}>*\n\n{video['description'][:200]}..."
                },
                "accessory": {
                    "type": "image",
                    "image_url": video["thumbnail"],
                    "alt_text": video["title"]
                } if video["thumbnail"] else None
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{eval_emoji} {eval_text}\n\n{eval_detail}"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"📅 {video['published_at'][:10]} | 🤖 Claude AI 분석"
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]
    }

    # accessory가 None인 경우 제거
    if message["blocks"][1].get("accessory") is None:
        del message["blocks"][1]["accessory"]

    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json=message,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            print(f"✅ Slack 알림 전송 완료: {video['title']}")
            return True
        else:
            print(f"❌ Slack 알림 전송 실패: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print(f"❌ Slack 알림 전송 오류: {e}")
        return False


def main():
    """메인 실행 함수"""
    print("=" * 50)
    print("🔔 YouTube → Slack 알림 봇 시작 (with Claude AI)")
    print(f"⏰ 실행 시간: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 50)

    # API 키 확인
    if not YOUTUBE_API_KEY:
        print("❌ YOUTUBE_API_KEY가 설정되지 않았습니다.")
        return

    if not SLACK_WEBHOOK_URL:
        print("❌ SLACK_WEBHOOK_URL이 설정되지 않았습니다.")
        return

    if not ANTHROPIC_API_KEY:
        print("⚠️ ANTHROPIC_API_KEY가 설정되지 않았습니다. 블로그 적합성 판단 없이 진행합니다.")

    # YouTube API 클라이언트 생성
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    # 채널 목록 로드
    channels = load_channels()
    if not channels:
        print("❌ 확인할 채널이 없습니다.")
        return

    print(f"📺 확인할 채널: {len(channels)}개")
    print(f"🤖 Claude AI 블로그 판단: {'활성화' if ANTHROPIC_API_KEY else '비활성화'}")

    # 마지막 확인 시간 로드
    last_checked = load_last_checked()

    # 현재 시간
    now = datetime.now(timezone.utc)

    # 새 영상 카운트
    new_videos_count = 0
    blog_recommended_count = 0

    # 각 채널 확인
    for channel in channels:
        channel_id = channel["channel_id"]
        channel_name = channel["name"]

        print(f"\n🔍 확인 중: {channel_name}")

        # 최신 영상 가져오기
        videos = get_latest_videos(youtube, channel_id)

        if not videos:
            continue

        # 마지막 확인 시간 이후의 새 영상 필터링
        last_check_time = last_checked.get(channel_id)

        for video in videos:
            published_at = datetime.fromisoformat(video["published_at"].replace("Z", "+00:00"))

            # 첫 실행이거나 마지막 확인 이후의 영상인 경우
            is_new = False
            if last_check_time is None:
                time_diff = (now - published_at).total_seconds()
                if time_diff <= 172800:  # 48시간 = 172800초 (테스트용)
                    is_new = True
            else:
                last_check_dt = datetime.fromisoformat(last_check_time)
                if published_at > last_check_dt:
                    is_new = True

            if is_new:
                # Claude로 블로그 적합성 판단
                print(f"  🤖 블로그 적합성 판단 중: {video['title'][:30]}...")
                evaluation = evaluate_blog_suitability(video, channel_name)

                # Slack 알림 전송
                send_slack_notification(video, channel_name, evaluation)
                new_videos_count += 1

                if evaluation and evaluation.get("is_suitable"):
                    blog_recommended_count += 1

        # 마지막 확인 시간 업데이트
        last_checked[channel_id] = now.isoformat()

    # 마지막 확인 시간 저장
    save_last_checked(last_checked)

    print("\n" + "=" * 50)
    print(f"✅ 완료! 새 영상 {new_videos_count}개 알림 전송")
    print(f"📝 블로그 추천 영상: {blog_recommended_count}개")
    print("=" * 50)


if __name__ == "__main__":
    main()
