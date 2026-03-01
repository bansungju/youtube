#!/usr/bin/env python3
"""
Slack YouTube 추천 → Notion 자동 저장 스크립트
"""

import os
import re
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "24ce4d83b1cb44839ae83a9a5bfe6e00")

TOPIC_KEYWORDS = {
    "Moltbot/ClaudeBot": ["moltbot", "몰트봇", "clawdbot", "클로드봇", "claude bot", "claudebot"],
    "AI 에이전트": ["agent", "에이전트", "agentic", "do anything", "autonomous"],
    "LLM/GPT": ["llm", "gpt", "claude", "gemini", "chatgpt", "language model"],
    "노코드/자동화": ["노코드", "no code", "nocode", "자동화", "automation"],
    "헬스케어": ["healthcare", "헬스케어", "의료", "medical", "health"],
}

def classify_topic(text: str) -> str:
    text_lower = text.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                return topic
    return "기타"

def parse_slack_message(text: str, attachments: List[dict] = None) -> Optional[Dict]:
    if "블로그 추천" not in text and "점수:" not in text:
        return None
    result = {}
    score_match = re.search(r'점수:\s*(\d+)/10', text)
    if score_match:
        result['점수'] = int(score_match.group(1))
    type_match = re.search(r'유형:\s*(.+?)(?:\n|$)', text)
    if type_match:
        result['유형'] = type_match.group(1).strip()
    core_match = re.search(r'핵심:\s*(.+?)(?=\n💡|\n✍️|\n📅|$)', text, re.DOTALL)
    if core_match:
        result['핵심'] = core_match.group(1).strip()
    reason_match = re.search(r'이유:\s*(.+?)(?=\n✍️|\n📅|$)', text, re.DOTALL)
    if reason_match:
        result['이유'] = reason_match.group(1).strip()
    column_match = re.search(r'칼럼 관점:\s*(.+?)(?=\n📅|$)', text, re.DOTALL)
    if column_match:
        result['칼럼관점'] = column_match.group(1).strip()
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    result['날짜'] = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')
    if attachments:
        for att in attachments:
            if att.get('service_name') == 'YouTube' or 'youtube' in att.get('from_url', '').lower():
                result['제목'] = att.get('title', '')
                result['채널명'] = att.get('author_name', '')
                result['YouTube URL'] = att.get('title_link') or att.get('from_url', '')
                break
    if '제목' not in result and '핵심' in result:
        result['제목'] = result['핵심'][:50] + ('...' if len(result.get('핵심', '')) > 50 else '')
    full_text = f"{result.get('핵심', '')} {result.get('이유', '')} {result.get('제목', '')}"
    result['토픽'] = classify_topic(full_text)
    return result if '점수' in result else None

def get_slack_messages(hours_back: int = 2) -> List[dict]:
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        print("❌ SLACK_BOT_TOKEN 또는 SLACK_CHANNEL_ID가 설정되지 않았습니다.")
        return []
    url = "https://slack.com/api/conversations.history"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json"}
    oldest = (datetime.now() - timedelta(hours=hours_back)).timestamp()
    params = {"channel": SLACK_CHANNEL_ID, "oldest": str(oldest), "limit": 100}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    if not data.get('ok'):
        print(f"❌ Slack API 에러: {data.get('error')}")
        return []
    return data.get('messages', [])

def get_existing_slack_ts() -> set:
    if not NOTION_API_KEY:
        return set()
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    headers = {"Authorization": f"Bearer {NOTION_API_KEY}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
    existing_ts = set()
    has_more = True
    start_cursor = None
    while has_more:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        response = requests.post(url, headers=headers, json=body)
        data = response.json()
        if 'results' not in data:
            break
        for page in data['results']:
            slack_ts = page.get('properties', {}).get('Slack TS', {}).get('rich_text', [])
            if slack_ts:
                existing_ts.add(slack_ts[0].get('plain_text', ''))
        has_more = data.get('has_more', False)
        start_cursor = data.get('next_cursor')
    return existing_ts

def save_to_notion(data: Dict, slack_ts: str) -> bool:
    if not NOTION_API_KEY:
        return False
    url = "https://api.notion.com/v1/pages"
    headers = {"Authorization": f"Bearer {NOTION_API_KEY}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
    type_mapping = {"강연/교육": "강연/교육", "뉴스/트렌드": "뉴스/트렌드", "튜토리얼": "튜토리얼", "리뷰/분석": "리뷰/분석", "인터뷰": "인터뷰"}
    properties = {"제목": {"title": [{"text": {"content": data.get('제목', 'Untitled')}}]}, "Slack TS": {"rich_text": [{"text": {"content": slack_ts}}]}}
    if '점수' in data:
        properties["점수"] = {"number": data['점수']}
    if '유형' in data:
        for key in type_mapping:
            if key in data['유형']:
                properties["유형"] = {"select": {"name": key}}
                break
    for field in ['핵심', '이유', '칼럼관점', '채널명']:
        if field in data and data[field]:
            properties[field] = {"rich_text": [{"text": {"content": data[field][:2000]}}]}
    if 'YouTube URL' in data and data['YouTube URL']:
        properties["YouTube URL"] = {"url": data['YouTube URL']}
    if '토픽' in data:
        properties["토픽"] = {"select": {"name": data['토픽']}}
    if '날짜' in data:
        properties["날짜"] = {"date": {"start": data['날짜']}}
    body = {"parent": {"database_id": NOTION_DATABASE_ID}, "properties": properties}
    response = requests.post(url, headers=headers, json=body)
    if response.status_code == 200:
        print(f"✅ 저장: {data.get('제목', '')[:30]}... [{data.get('토픽', '기타')}]")
        return True
    print(f"❌ 저장 실패: {response.json()}")
    return False

def delete_old_entries(days: int = 7) -> int:
    if not NOTION_API_KEY:
        return 0
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    headers = {"Authorization": f"Bearer {NOTION_API_KEY}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    body = {"filter": {"property": "날짜", "date": {"before": cutoff_date}}}
    response = requests.post(url, headers=headers, json=body)
    data = response.json()
    deleted_count = 0
    for page in data.get('results', []):
        page_id = page['id']
        delete_response = requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=headers, json={"archived": True})
        if delete_response.status_code == 200:
            deleted_count += 1
    if deleted_count > 0:
        print(f"🗑️ {deleted_count}개 오래된 항목 삭제됨")
    return deleted_count

def main():
    print("🚀 Slack → Notion 동기화 시작")
    existing_ts = get_existing_slack_ts()
    print(f"📊 기존 항목: {len(existing_ts)}개")
    messages = get_slack_messages(hours_back=2)
    print(f"📨 Slack 메시지: {len(messages)}개")
    saved_count = 0
    for msg in messages:
        slack_ts = msg.get('ts', '')
        if slack_ts in existing_ts:
            continue
        parsed = parse_slack_message(msg.get('text', ''), msg.get('attachments', []))
        if parsed and save_to_notion(parsed, slack_ts):
            saved_count += 1
    print(f"📈 {saved_count}개 저장 완료")
    delete_old_entries(days=7)
    print("✅ 동기화 완료!")

if __name__ == "__main__":
    main()
