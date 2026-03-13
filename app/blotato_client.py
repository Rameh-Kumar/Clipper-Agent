"""
Blotato Client
==============
Publish clips to YouTube Shorts (and optionally TikTok, Instagram Reels) via Blotato.
"""

import os
import requests

BLOTATO_API_KEY = os.environ.get("BLOTATO_API_KEY", "")
BLOTATO_API_URL = "https://backend.blotato.com/v2/posts"


def publish_clip(video_url: str, title: str, description: str = "",
                 platforms: list = None, schedule_time: str = None) -> dict:
    """
    Publish a clip via Blotato.

    Args:
        video_url: Direct URL to the video file
        title: Title for the post
        description: Optional description/caption
        platforms: List of platforms (default: ["youtube"])
        schedule_time: ISO timestamp for scheduled posting (optional)

    Returns:
        dict with success status and post details
    """
    if platforms is None:
        platforms = ["youtube"]

    headers = {
        "Authorization": f"Bearer {BLOTATO_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "mediaUrls": [video_url],
        "text": title,
        "platforms": platforms,
    }

    # Add account ID if provided
    account_id = os.environ.get("BLOTATO_YOUTUBE_ACCOUNT_ID")
    if account_id:
        payload["accountId"] = account_id

    if description:
        payload["text"] = f"{title}\n\n{description}"

    if schedule_time:
        payload["scheduledTime"] = schedule_time

    response = requests.post(BLOTATO_API_URL, headers=headers, json=payload)

    if response.status_code in (200, 201):
        data = response.json()
        return {"success": True, "data": data}
    else:
        return {
            "success": False,
            "error": f"HTTP {response.status_code}: {response.text}",
        }


def check_connection() -> dict:
    """Check if the Blotato API key is valid."""
    headers = {
        "Authorization": f"Bearer {BLOTATO_API_KEY}",
    }
    response = requests.get("https://backend.blotato.com/v2/accounts", headers=headers)
    if response.status_code == 200:
        return {"connected": True, "accounts": response.json()}
    return {"connected": False, "error": response.text}
