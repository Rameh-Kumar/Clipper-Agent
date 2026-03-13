"""
Vizard API Test Script
======================
Sends one YouTube URL to Vizard, polls until clips are ready,
then downloads all generated clips to a local folder.

Usage:
  1. Set your API key below (or as environment variable VIZARD_API_KEY)
  2. Run: python test_vizard.py
  3. To resume/download an existing project: python test_vizard.py <projectId>
"""

import os
import sys
import time
import json
import requests
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- Configuration ---

VIZARD_API_KEY = os.environ.get("VIZARD_API_KEY", "46b0ff831c1846ae9e5405bb93e9236f")
YOUTUBE_URL = "https://youtu.be/43LZBvgBzVw?si=qlfbI5QtsmO-6Xxl"
OUTPUT_DIR = Path("clips")

# Vizard API endpoints
BASE_URL = "https://elb-api.vizard.ai/hvizard-server-front/open-api/v1"
CREATE_URL = f"{BASE_URL}/project/create"
QUERY_URL = f"{BASE_URL}/project/query"  # + /{projectId}

# Clip settings
CLIP_SETTINGS = {
    "videoUrl": YOUTUBE_URL,
    "videoType": 2,           # 2 = YouTube
    "lang": "hi",             # Spoken language in the video (hi = Hindi/Hinglish)
    "preferLength": [2, 3],   # Array: 2=30-60s, 3=1-3min (minimum 30s, better endpoints)
    "ratioOfClip": 1,         # 1 = 9:16 vertical (Shorts format)
    "subtitleSwitch": 1,      # 1 = subtitles ON
    "headlineSwitch": 1,      # 1 = AI headline ON
    "highlightSwitch": 1,     # 1 = highlight keywords ON
    "emojiSwitch": 1,         # 1 = AI emoji ON
    "removeSilenceSwitch": 0, # 0 = keep silences (safer for first test)
}

POLL_INTERVAL = 30  # seconds between status checks
MAX_WAIT = 30 * 60  # give up after 30 minutes


# --- Helpers ---

def get_headers():
    return {
        "Content-Type": "application/json",
        "VIZARDAI_API_KEY": VIZARD_API_KEY,
    }


def create_project():
    """Submit the YouTube video to Vizard for clipping."""
    print(f"\n[>>] Sending video to Vizard...")
    print(f"    URL: {YOUTUBE_URL}")
    print(f"    Settings: 9:16 vertical, subtitles ON, 30s-3min clips\n")

    response = requests.post(CREATE_URL, headers=get_headers(), json=CLIP_SETTINGS, timeout=60)

    if response.status_code != 200:
        print(f"[FAIL] API request failed with status {response.status_code}")
        print(f"    Response: {response.text}")
        sys.exit(1)

    data = response.json()

    if data.get("code") != 2000:
        print(f"[FAIL] Vizard returned error code: {data.get('code')}")
        print(f"    Message: {data.get('message') or data.get('msg', 'No message')}")
        print(f"    Full response: {json.dumps(data, indent=2)}")
        sys.exit(1)

    project_id = data.get("projectId") or (data.get("data") or {}).get("projectId")
    if not project_id:
        print(f"[FAIL] No projectId in response")
        print(f"    Full response: {json.dumps(data, indent=2)}")
        sys.exit(1)

    print(f"[OK] Project created! ID: {project_id}")
    print(f"     Vizard is now processing your video...\n")
    return project_id


def poll_project(project_id):
    """Poll Vizard until clips are ready, then return clip data."""
    url = f"{QUERY_URL}/{project_id}"
    elapsed = 0

    while elapsed < MAX_WAIT:
        print(f"[...] Checking status... ({elapsed // 60}m {elapsed % 60}s elapsed)")

        response = requests.get(url, headers=get_headers())

        if response.status_code != 200:
            print(f"      Status check failed (HTTP {response.status_code}), retrying...")
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            continue

        data = response.json()
        code = data.get("code")

        if code == 1000:
            # Still processing
            print(f"      Still processing...")
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            continue

        elif code == 2000:
            # Done! Handle both response shapes
            project_data = data.get("data") or data
            videos = project_data.get("videos", [])
            print(f"\n[DONE] Processing complete!")
            print(f"       Generated {len(videos)} clip(s)\n")
            return project_data

        else:
            err_msg = data.get("errMsg") or data.get("message") or data.get("msg", "No message")
            print(f"      [FAIL] Unexpected status code: {code}")
            print(f"      Message: {err_msg}")
            print(f"      Full response: {json.dumps(data, indent=2)}")
            sys.exit(1)

    print(f"\n[TIMEOUT] Gave up after {MAX_WAIT // 60} minutes.")
    print(f"          Re-run with: python test_vizard.py {project_id}")
    sys.exit(1)


def download_clips(project_data):
    """Download all generated clips to the output folder."""
    videos = project_data.get("videos", [])

    if not videos:
        print("[FAIL] No clips found in the response.")
        return

    OUTPUT_DIR.mkdir(exist_ok=True)

    print(f"[DL] Downloading {len(videos)} clip(s) to ./{OUTPUT_DIR}/\n")
    print(f"{'#':<4} {'Title':<50} {'Duration':<10} {'Score':<8}")
    print(f"{'='*4} {'='*50} {'='*10} {'='*8}")

    for i, video in enumerate(videos, 1):
        title = video.get("title", f"clip_{i}")
        duration_ms = video.get("videoMsDuration", 0)
        duration_s = round(duration_ms / 1000) if duration_ms else "?"
        viral_score = video.get("viralScore", "?")
        video_url = video.get("videoUrl", "")

        # Clean filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)
        safe_title = safe_title[:60].strip()
        filename = f"{i:02d}_{safe_title}.mp4"
        filepath = OUTPUT_DIR / filename

        # Print info row
        display_title = title[:48] + ".." if len(title) > 50 else title
        print(f"{i:<4} {display_title:<50} {str(duration_s) + 's':<10} {str(viral_score):<8}")

        if not video_url:
            print(f"     [SKIP] No download URL for this clip")
            continue

        # Download the clip
        try:
            r = requests.get(video_url, stream=True)
            r.raise_for_status()

            total_size = int(r.headers.get("content-length", 0))
            downloaded = 0

            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = int(downloaded / total_size * 100)
                        mb_done = downloaded // (1024*1024)
                        mb_total = total_size // (1024*1024)
                        print(f"     [{pct}%] {mb_done}MB / {mb_total}MB", end="\r")

            file_size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"     [OK] Saved: {filename} ({file_size_mb:.1f} MB)        ")

        except Exception as e:
            print(f"     [FAIL] Download failed: {e}")

    print(f"\n{'='*72}")
    print(f"[OK] Done! Check the ./{OUTPUT_DIR}/ folder for your clips.")
    print(f"     Watch them and decide if the quality is good enough.\n")


def save_metadata(project_data):
    """Save the full API response for reference."""
    metadata_file = OUTPUT_DIR / "_metadata.json"
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(project_data, f, indent=2, ensure_ascii=False)
    print(f"[i] Full metadata saved to {metadata_file}")


# --- Main ---

def main():
    print("=" * 72)
    print("  Vizard API Test - Clip Quality Check")
    print("=" * 72)

    # Validate API key
    if VIZARD_API_KEY == "YOUR_API_KEY_HERE" or not VIZARD_API_KEY:
        print("\n[FAIL] No API key set!")
        print("       Set VIZARD_API_KEY env var or edit the script.")
        sys.exit(1)

    # Check for project ID argument (resume mode)
    resuming_project_id = sys.argv[1] if len(sys.argv) > 1 else None

    if resuming_project_id:
        print(f"\n[>>] Resuming with existing Project ID: {resuming_project_id}")
        project_id = resuming_project_id
    else:
        # Step 1: Submit video
        project_id = create_project()

    # Step 2: Poll until done
    project_data = poll_project(project_id)

    # Step 3: Download clips
    download_clips(project_data)

    # Step 4: Save metadata
    save_metadata(project_data)


if __name__ == "__main__":
    main()
