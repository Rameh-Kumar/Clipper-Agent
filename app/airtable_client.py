"""
Airtable Client
===============
Create, query, and update clip records in the 'shorts/Reel' table.
"""

import os
import requests

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_PAT", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")
TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME", "shorts/Reel")

API_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_NAME}"


def _headers():
    return {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }


def create_clip_records(clips: list, source_url: str, source_title: str = "") -> list:
    """
    Create Airtable records for a batch of clips.

    Airtable allows max 10 records per request.
    Returns list of created record IDs.
    """
    record_ids = []

    # Process in batches of 10 (Airtable limit)
    for i in range(0, len(clips), 10):
        batch = clips[i:i + 10]
        records = []

        for clip in batch:
            fields = {
                "Title": clip.get("title", "Untitled"),
                "Caption": clip.get("transcript", ""),
                "Viral Score": float(clip.get("viral_score", 0)),
                "Viral Reason": clip.get("viral_reason", ""),
                "Source URL": source_url,
                "Status": "Ready",
            }

            # Add video as attachment if URL exists
            if clip.get("video_url"):
                fields["Video"] = [
                    {"url": clip["video_url"], "filename": f"{clip.get('title', 'clip')}.mp4"}
                ]

            records.append({"fields": fields})

        payload = {"records": records}
        response = requests.post(API_URL, headers=_headers(), json=payload)

        if response.status_code == 200:
            data = response.json()
            for rec in data.get("records", []):
                record_ids.append(rec["id"])
        else:
            print(f"Airtable error: {response.status_code} - {response.text}")

    return record_ids


def get_approved_unscheduled() -> list:
    """
    Get all clips where Status=Approved.

    Returns list of dicts with record id and fields.
    """
    params = {
        "filterByFormula": "{Status}='Approved'",
        "sort[0][field]": "Viral Score",
        "sort[0][direction]": "desc",
    }

    response = requests.get(API_URL, headers=_headers(), params=params)

    if response.status_code != 200:
        print(f"Airtable error: {response.status_code} - {response.text}")
        return []

    data = response.json()
    results = []

    for rec in data.get("records", []):
        fields = rec.get("fields", {})
        # Get the video URL from the attachment field
        video_attachments = fields.get("Video", [])
        video_url = video_attachments[0].get("url", "") if video_attachments else ""

        results.append({
            "record_id": rec["id"],
            "title": fields.get("Title", "Untitled"),
            "video_url": video_url,
            "caption": fields.get("Caption", ""),
            "viral_score": fields.get("Viral Score", 0),
        })

    return results


def mark_scheduled(record_ids: list) -> bool:
    """Mark clips as Ready (scheduled) in Airtable."""
    # Process in batches of 10
    for i in range(0, len(record_ids), 10):
        batch = record_ids[i:i + 10]
        records = []

        for rid in batch:
            records.append({
                "id": rid,
                "fields": {
                    "Status": "Ready",
                }
            })

        payload = {"records": records}
        response = requests.patch(API_URL, headers=_headers(), json=payload)

        if response.status_code != 200:
            print(f"Airtable update error: {response.status_code} - {response.text}")
            return False

    return True


def get_pending_count() -> int:
    """Count clips with Ready status (pending review)."""
    params = {
        "filterByFormula": "{Status}='Ready'",
    }
    response = requests.get(API_URL, headers=_headers(), params=params)
    if response.status_code == 200:
        return len(response.json().get("records", []))
    return 0
