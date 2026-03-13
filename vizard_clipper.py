"""
Clipper Agent — Main Modal App
================================
Serverless FastAPI endpoints that orchestrate the full pipeline:
  - Telegram webhook (receives URLs and commands)
  - Vizard webhook (receives clip-ready callbacks)
  - Health check
"""

import modal
import os

# ---------------------------------------------------------------------------
# Modal App Setup
# ---------------------------------------------------------------------------

app = modal.App("clipper-agent")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi[standard]", "requests")
    .add_local_python_source("app")  # includes the app/ package in the container
)

# All secrets stored in Modal
secrets = modal.Secret.from_name("vizard-clipper-secrets")

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

web_app = FastAPI(title="Clipper Agent")


@web_app.get("/health")
async def health():
    return {"status": "ok", "service": "clipper-agent"}


@web_app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Handle all incoming Telegram messages."""
    from app.telegram_bot import parse_update, send_message
    from app.vizard_client import create_project
    from app.airtable_client import get_approved_unscheduled, mark_scheduled, get_pending_count

    body = await request.json()
    update = parse_update(body)

    chat_id = update["chat_id"]
    if not chat_id:
        return {"ok": True}

    # --- Security Check: Only allow authorized chat ID ---
    allowed_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if allowed_chat_id and str(chat_id) != str(allowed_chat_id):
        print(f"🚫 Unauthorized access attempt from Chat ID: {chat_id}")
        return {"ok": True}
    
    # If not set, log it so the user can find theirs
    if not allowed_chat_id:
        print(f"👉 TIP: Your Chat ID is {chat_id}. Set it as ALLOWED_CHAT_ID in Modal Secrets to lock the bot.")

    # --- YouTube URL received → start Workflow 1 ---
    if update["youtube_url"]:
        url = update["youtube_url"]
        send_message(chat_id, f"*Processing started!*\n\nSending `{url}` to Vizard for clipping...\nThis usually takes 1-5 minutes. I'll message you when clips are ready.")

        # Get the Modal app URL for Vizard's webhook callback
        modal_url = os.environ.get("MODAL_APP_URL", "")
        vizard_webhook = f"{modal_url}/vizard/webhook?chat_id={chat_id}&source_url={url}"

        result = create_project(url, webhook_url=vizard_webhook, lang=update.get("lang", ""))

        if result["success"]:
            send_message(chat_id, f"✅ *Vizard accepted the video!*\n\nProject ID: `{result['project_id']}`\n\nI'll ping you here as soon as the clips are ready in Airtable.")
        else:
            send_message(chat_id, f"❌ *Error from Vizard:* {result.get('error', 'Unknown error')}")

        return {"ok": True}

    # --- "Done reviewing" → start Workflow 2 ---
    if update["is_done_reviewing"]:
        send_message(chat_id, "Checking for approved clips...")

        approved = get_approved_unscheduled()

        if not approved:
            pending = get_pending_count()
            if pending > 0:
                send_message(chat_id, f"No approved clips found, but you have *{pending}* clips still pending review.")
            else:
                send_message(chat_id, "No approved clips found. Approve some clips in Airtable first!")
            return {"ok": True}

        # Try to publish via Blotato
        blotato_key = os.environ.get("BLOTATO_API_KEY", "")
        scheduled_count = 0
        errors = []

        if blotato_key:
            from app.blotato_client import publish_clip

            for clip in approved:
                result = publish_clip(
                    video_url=clip["video_url"],
                    title=clip["title"],
                    description=clip.get("transcript", ""),
                )
                if result["success"]:
                    scheduled_count += 1
                else:
                    errors.append(f"'{clip['title']}': {result['error']}")

            # Mark all as scheduled in Airtable
            record_ids = [c["record_id"] for c in approved]
            mark_scheduled(record_ids)
        else:
            # No Blotato key yet — just mark as scheduled
            record_ids = [c["record_id"] for c in approved]
            mark_scheduled(record_ids)
            scheduled_count = len(approved)

        msg = f"*{scheduled_count} clip(s) scheduled!*"
        if errors:
            msg += f"\n\n{len(errors)} error(s):\n" + "\n".join(errors)

        send_message(chat_id, msg)
        return {"ok": True}

    # --- /status command ---
    if update["is_status"]:
        pending = get_pending_count()
        approved = get_approved_unscheduled()
        msg = f"*Status:*\n- {pending} clips pending review\n- {len(approved)} clips approved, waiting to schedule"
        send_message(chat_id, msg)
        return {"ok": True}

    # --- /help or /start ---
    if update["is_help"]:
        send_message(chat_id, (
            "*Clipper Agent Bot*\n\n"
            "Send me a YouTube URL and I'll generate short clips for you!\n\n"
            "*Commands:*\n"
            "- Send a YouTube link → generates clips\n"
            "- `done reviewing` → schedules approved clips\n"
            "- `/status` → shows pending/approved counts\n"
            "- `/help` → shows this message"
        ))
        return {"ok": True}

    # --- Unknown message ---
    send_message(chat_id, "I didn't understand that. Send me a YouTube URL or type /help.")
    return {"ok": True}


@web_app.post("/vizard/webhook")
async def vizard_webhook(request: Request, chat_id: int = 0, source_url: str = ""):
    """Handle Vizard's clip-ready callback."""
    from app.telegram_bot import send_message
    from app.airtable_client import create_clip_records
    from app.vizard_client import parse_clips

    body = await request.json()

    # Parse clips from Vizard's response
    clips = parse_clips(body)

    if not clips:
        if chat_id:
            send_message(chat_id, "Vizard finished but returned no clips. The video might be too short.")
        return {"ok": True, "clips": 0}

    # Create Airtable records
    record_ids = create_clip_records(clips, source_url=source_url)

    # Notify via Telegram
    if chat_id:
        airtable_base = os.environ.get("AIRTABLE_BASE_ID", "")
        airtable_url = f"https://airtable.com/{airtable_base}" if airtable_base else "Airtable"

        msg = f"*{len(clips)} clips ready for review!*\n\n"
        for i, clip in enumerate(clips[:5], 1):
            msg += f"{i}. *{clip['title']}* ({clip['duration_s']}s, score: {clip['viral_score']})\n"
        if len(clips) > 5:
            msg += f"...and {len(clips) - 5} more\n"
        msg += f"\n[Review in Airtable]({airtable_url})"
        msg += "\n\nWhen you're done reviewing, send me `done reviewing`."

        send_message(chat_id, msg)

    return {"ok": True, "clips": len(clips), "records": len(record_ids)}


# ---------------------------------------------------------------------------
# Deploy as Modal ASGI app
# ---------------------------------------------------------------------------

@app.function(image=image, secrets=[secrets])
@modal.asgi_app()
def fastapi_app():
    return web_app
