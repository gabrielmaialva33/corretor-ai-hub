"""
Webhook routes for external integrations
"""
import hashlib
import hmac
from typing import Dict, Any

import structlog
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from src.core.config import get_settings
from src.services.webhook_processor import WebhookProcessor

logger = structlog.get_logger()
settings = get_settings()

router = APIRouter()
webhook_processor = WebhookProcessor()


def verify_webhook_signature(request_body: bytes, signature: str, secret: str) -> bool:
    """Verify webhook signature"""
    expected_signature = hmac.new(
        secret.encode(),
        request_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)


@router.post("/evo")
async def evo_webhook(
        request: Request,
        background_tasks: BackgroundTasks
):
    """
    Receive webhooks from EVO API
    
    This endpoint receives WhatsApp messages and events
    """
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Verify signature if configured
        if settings.WEBHOOK_SECRET:
            signature = request.headers.get("X-Hub-Signature-256", "")
            if not verify_webhook_signature(body, signature, settings.WEBHOOK_SECRET):
                logger.warning("Invalid EVO webhook signature")
                raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse payload
        payload = await request.json()

        # Log webhook
        logger.info(
            "Received EVO webhook",
            event_type=payload.get("event"),
            instance=payload.get("instance")
        )

        # Process in background
        background_tasks.add_task(
            webhook_processor.process_evo_webhook,
            payload
        )

        return JSONResponse(
            status_code=200,
            content={"status": "received"}
        )

    except Exception as e:
        logger.error("Error processing EVO webhook", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/chatwoot")
async def chatwoot_webhook(
        request: Request,
        background_tasks: BackgroundTasks
):
    """
    Receive webhooks from Chatwoot
    
    This endpoint receives conversation and message events
    """
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Verify signature if configured
        if settings.WEBHOOK_SECRET:
            signature = request.headers.get("X-Chatwoot-Signature", "")
            if not verify_webhook_signature(body, signature, settings.WEBHOOK_SECRET):
                logger.warning("Invalid Chatwoot webhook signature")
                raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse payload
        payload = await request.json()

        # Log webhook
        logger.info(
            "Received Chatwoot webhook",
            event_type=payload.get("event"),
            account_id=payload.get("account", {}).get("id")
        )

        # Process in background
        background_tasks.add_task(
            webhook_processor.process_chatwoot_webhook,
            payload
        )

        return JSONResponse(
            status_code=200,
            content={"status": "received"}
        )

    except Exception as e:
        logger.error("Error processing Chatwoot webhook", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/google-calendar")
async def google_calendar_webhook(
        request: Request,
        background_tasks: BackgroundTasks
):
    """
    Receive webhooks from Google Calendar
    
    This endpoint receives calendar event updates
    """
    try:
        # Parse payload
        payload = await request.json()

        # Google Calendar uses channel tokens for verification
        channel_token = request.headers.get("X-Goog-Channel-Token", "")

        # Log webhook
        logger.info(
            "Received Google Calendar webhook",
            resource_id=request.headers.get("X-Goog-Resource-ID"),
            channel_id=request.headers.get("X-Goog-Channel-ID")
        )

        # Process in background
        background_tasks.add_task(
            webhook_processor.process_calendar_webhook,
            payload,
            channel_token
        )

        return JSONResponse(
            status_code=200,
            content={"status": "received"}
        )

    except Exception as e:
        logger.error("Error processing Google Calendar webhook", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/test")
async def test_webhook():
    """Test webhook endpoint to verify configuration"""
    return {
        "status": "ok",
        "message": "Webhook endpoint is working",
        "evo_url": settings.EVO_WEBHOOK_URL,
        "chatwoot_url": settings.CHATWOOT_WEBHOOK_URL
    }


@router.post("/test/evo")
async def test_evo_webhook(payload: Dict[str, Any]):
    """
    Test EVO webhook processing
    
    This endpoint allows testing webhook processing without actual EVO events
    """
    try:
        result = await webhook_processor.process_evo_webhook(payload)
        return {
            "status": "processed",
            "result": result
        }
    except Exception as e:
        logger.error("Error in test EVO webhook", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/chatwoot")
async def test_chatwoot_webhook(payload: Dict[str, Any]):
    """
    Test Chatwoot webhook processing
    
    This endpoint allows testing webhook processing without actual Chatwoot events
    """
    try:
        result = await webhook_processor.process_chatwoot_webhook(payload)
        return {
            "status": "processed",
            "result": result
        }
    except Exception as e:
        logger.error("Error in test Chatwoot webhook", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
