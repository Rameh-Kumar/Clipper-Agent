"""
Vizard API Client
=================
Handles creating clip projects and parsing webhook responses.
"""

import os
import requests

VIZARD_API_KEY = os.environ.get("VIZARD_API_KEY", "")
BASE_URL = "https://elb-api.vizard.ai/hvizard-server-front/open-api/v1"


def create_project(youtube_url: str, webhook_url: str = "", lang: str = "") -> dict:
    """
    Submit a YouTube video to Vizard for AI clipping.
    
    Returns dict with projectId on success, or error info on failure.
    """
    headers = {
        "Content-Type": "application/json",
        "VIZARDAI_API_KEY": VIZARD_API_KEY,
    }

    payload = {
        "videoUrl": youtube_url,
        "videoType": 2,           # 2 = YouTube
        "lang": lang or os.environ.get("VIZARD_DEFAULT_LANG", "hi"),
        "preferLength": [2, 3],   # 2=30-60s, 3=1-3min (minimum 30s)
        "ratioOfClip": 1,         # 1 = 9:16 vertical
        "subtitleSwitch": 1,      # Subtitles ON
        "headlineSwitch": 1,      # AI headline ON
        "highlightSwitch": 1,     # Highlight keywords ON
        "emojiSwitch": 1,         # AI emoji ON
        "removeSilenceSwitch": 0, # Keep silences
    }

    # Add template ID if provided
    template_id = os.environ.get("VIZARD_TEMPLATE_ID")
    if template_id:
        payload["templateId"] = template_id

    # Add webhook URL if provided (Vizard calls this when done)
    if webhook_url:
        payload["webhookUrl"] = webhook_url

    response = requests.post(
        f"{BASE_URL}/project/create",
        headers=headers,
        json=payload,
    )

    if response.status_code != 200:
        return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}

    data = response.json()

    if data.get("code") != 2000:
        err = data.get("errMsg") or data.get("message") or data.get("msg", "Unknown error")
        return {"success": False, "error": err, "code": data.get("code")}

    project_id = data.get("projectId") or (data.get("data") or {}).get("projectId")
    return {"success": True, "project_id": project_id}


def query_project(project_id: str) -> dict:
    """
    Query a Vizard project for status and clips.
    
    Returns dict with status and clips list if done.
    """
    headers = {
        "VIZARDAI_API_KEY": VIZARD_API_KEY,
    }

    response = requests.get(
        f"{BASE_URL}/project/query/{project_id}",
        headers=headers,
    )

    if response.status_code != 200:
        return {"status": "error", "error": f"HTTP {response.status_code}"}

    data = response.json()
    code = data.get("code")

    if code == 1000:
        return {"status": "processing"}
    elif code == 2000:
        project_data = data.get("data") or data
        return {"status": "done", "clips": parse_clips(project_data)}
    else:
        err = data.get("errMsg") or data.get("message") or "Unknown error"
        return {"status": "error", "error": err, "code": code}


def parse_clips(project_data: dict) -> list:
    """Extract clip info from Vizard project data."""
    videos = project_data.get("videos", [])
    clips = []

    for v in videos:
        duration_ms = v.get("videoMsDuration", 0)
        clips.append({
            "title": v.get("title", "Untitled Clip"),
            "video_url": v.get("videoUrl", ""),
            "viral_score": v.get("viralScore", "0"),
            "transcript": v.get("transcript", ""),
            "duration_s": round(duration_ms / 1000) if duration_ms else 0,
            "viral_reason": v.get("viralReason", ""),
            "editor_url": v.get("clipEditorUrl", ""),
        })

    # Sort by viral score descending
    clips.sort(key=lambda c: float(c["viral_score"]), reverse=True)
    return clips
