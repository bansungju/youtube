#!/usr/bin/env python3
"""
YouTube → Slack 알림 봇
구독 채널의 새 영상이 올라오면 Slack으로 알림을 보냅니다.
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

# 파일 경로
SCRIPT_DIR = Path(__file__).parent
CHANNELS_FILE = SCRIPT_DIR / "channels.json"
LAST_CHECKED_FILE = SCRIPT_DIR / "last_checked.json"


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
                "description": snippet["description"][:200] + "..." if len(snippet["description"]) > 200 else snippet["description"],
                "published_at": snippet["publishedAt"],
                "thumbnail": snippet["thumbnails"].get("high", snippet["thumbnails"].get("default", {})).get("url", ""),
                "channel_title": snippet["channelTitle"]
            })

        return videos

    except Exception as e:
        print(f"❌ 영상 목록 가져오기 실패 ({channel_id}): {e}")
        return []


def send_slack_notification(video, channel_name):
    """Slack으로 알림 전송"""
    video_url = f"https://www.youtube.com/watch?v={video['video_id']}"

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
                    "text": f"*<{video_url}|{video['title']}>*\n\n{video['description']}"
                },
                "accessory": {
                    "type": "image",
                    "image_url": video["thumbnail"],
                    "alt_text": video["title"]
                } if video["thumbnail"] else None
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"📅 {video['published_at'][:10]}"
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]
    }

    # accessory가 None인 경우 제거
    if message["blocks"][1]["accessory"] is None:
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
    print("🔔 YouTube → Slack 알림 봇 시작")
    print(f"⏰ 실행 시간: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 50)

    # API 키 확인
    if not YOUTUBE_API_KEY:
        print("❌ YOUTUBE_API_KEY가 설정되지 않았습니다.")
        return

    if not SLACK_WEBHOOK_URL:
        print("❌ SLACK_WEBHOOK_URL이 설정되지 않았습니다.")
        return

    # YouTube API 클라이언트 생성
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    # 채널 목록 로드
    channels = load_channels()
    if not channels:
        print("❌ 확인할 채널이 없습니다.")
        return

    print(f"📺 확인할 채널: {len(channels)}개")

    # 마지막 확인 시간 로드
    last_checked = load_last_checked()

    # 현재 시간
    now = datetime.now(timezone.utc)

    # 새 영상 카운트
    new_videos_count = 0

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
            if last_check_time is None:
                # 첫 실행: 최근 1시간 이내 영상만 알림
                time_diff = (now - published_at).total_seconds()
                if time_diff <= 3600:  # 1시간 = 3600초
                    send_slack_notification(video, channel_name)
                    new_videos_count += 1
            else:
                last_check_dt = datetime.fromisoformat(last_check_time)
                if published_at > last_check_dt:
                    send_slack_notification(video, channel_name)
                    new_videos_count += 1

        # 마지막 확인 시간 업데이트
        last_checked[channel_id] = now.isoformat()

    # 마지막 확인 시간 저장
    save_last_checked(last_checked)

    print("\n" + "=" * 50)
    print(f"✅ 완료! 새 영상 {new_videos_count}개 알림 전송")
    print("=" * 50)


if __name__ == "__main__":
    main()
