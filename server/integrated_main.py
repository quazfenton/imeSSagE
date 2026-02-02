from fastapi import FastAPI, WebSocket, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
import asyncio
import logging
from typing import Optional, List, Dict, Any
from enum import Enum
from uuid import uuid4
import json
import time
from datetime import datetime

from .models.routing_state_machine import Message, MessageState, transition, process_message
from .channels.adapters import channel_manager, SendResult
from .utils.contact_manager import contact_manager, get_contact_for_sending, record_message_sent, is_contact_opted_in
from .llm import enhance_with_llm, ChannelType, DraftResult, validate_message, sanitize_message
from .workers.redis_workers import enqueue_message
from .config import get_config, init_config

# Initialize configuration
config = get_config()

# Configure logging
logging.basicConfig(level=getattr(logging, config.log_level.upper()))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LLM-Powered Free SMS/RCS/Email Service",
    description="A service that leverages device-backed gateways to send messages without per-message costs",
    version="1.0.0"
)

# Global set to hold active Android WebSocket connections
ANDROID_CLIENTS = set()

class DraftRequest(BaseModel):
    to: str = Field(..., description="Recipient identifier (phone number or email)")
    channel: Optional[str] = Field(None, description="Channel to use (rcs, sms, email, imessage). Auto-selected if not provided")
    text: str = Field(..., min_length=1, max_length=10000, description="Message text to send")
    email: Optional[str] = Field(None, description="Required if channel is email")
    intent: Optional[str] = Field(None, description="Original intent for LLM enhancement")
    fallback_channels: Optional[List[str]] = Field(default_factory=list, description="Fallback channels in order of preference")
    use_llm_enhancement: bool = Field(True, description="Whether to use LLM to enhance the message")
    priority: int = Field(1, ge=1, le=5, description="Priority level (1-5, higher is more urgent)")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for message categorization")

class SendMessageResponse(BaseModel):
    success: bool
    message_id: Optional[str] = None
    status: str
    channel_used: Optional[str] = None
    error: Optional[str] = None
    processing_time: Optional[float] = None
    details: Optional[Dict[str, Any]] = None

@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handle validation errors globally"""
    logger.error(f"Validation error: {exc}")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "Validation error",
            "details": exc.errors()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions globally"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "details": str(exc)
        }
    )

@app.on_event("startup")
async def startup_event():
    """Initialize components on startup"""
    start_time = time.time()
    try:
        # Initialize configuration
        init_config()
        config = get_config()

        # Initialize channel manager with configuration
        await channel_manager.initialize({
            'email': {
                'smtp_server': config.smtp.server,
                'smtp_port': config.smtp.port,
                'username': config.smtp.username,
                'password': config.smtp.password,
                'from_email': config.smtp.from_email,
                'use_tls': config.smtp.use_tls,
                'timeout': config.smtp.timeout
            },
            'android_timeout': config.android.websocket_timeout,
            'imessage': {
                'enabled': False  # Configure as needed
            }
        })

        init_time = time.time() - start_time
        logger.info(f"Application {config.app_name} v{config.version} started in {init_time:.2f}s")
        logger.info(f"Environment: {config.environment}")
        logger.info(f"API server running on {config.api_server.host}:{config.api_server.port}")
    except Exception as e:
        logger.error(f"Failed to initialize components: {e}")
        raise

@app.websocket("/ws/android")
async def android_gateway(ws: WebSocket):
    """WebSocket endpoint for Android gateway connections"""
    await ws.accept()
    ANDROID_CLIENTS.add(ws)
    client_id = str(uuid4())
    logger.info(f"Android client {client_id} connected. Total clients: {len(ANDROID_CLIENTS)}")

    try:
        while True:
            try:
                data = await ws.receive_json()
                logger.info(f"Incoming from Android client {client_id}: {data}")

                # Handle different types of messages from the Android device
                msg_type = data.get("type")
                if msg_type == "delivery_receipt":
                    # Process delivery receipt
                    logger.info(f"Delivery receipt received from {client_id}: {data}")
                    # Here you would update message status in Redis/database
                elif msg_type == "incoming_message":
                    # Process incoming message
                    logger.info(f"Incoming message from {client_id}: {data}")
                    # Here you would handle incoming messages
                elif msg_type == "device_status":
                    # Process device status updates
                    logger.info(f"Device status from {client_id}: {data}")
                elif msg_type == "heartbeat":
                    # Respond to heartbeat
                    await ws.send_json({"type": "pong", "timestamp": time.time()})
                else:
                    logger.warning(f"Unknown message type from {client_id}: {msg_type}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing message from Android client {client_id}: {e}")
                break
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for client {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        ANDROID_CLIENTS.discard(ws)
        logger.info(f"Android client {client_id} disconnected. Total clients: {len(ANDROID_CLIENTS)}")

@app.post("/send", response_model=SendMessageResponse)
async def send_message(req: DraftRequest, background_tasks: BackgroundTasks):
    """
    Main endpoint to send messages via different channels
    """
    start_time = time.time()
    logger.info(f"Received send request: to={req.to}, channel={req.channel}")

    try:
        # Get contact information
        contact = get_contact_for_sending(req.to)

        if not contact:
            # Create a temporary contact if not found
            contact = contact_manager.get_contact_by_phone(req.to)
            if not contact:
                # If still not found, create a minimal contact
                contact = contact_manager.get_contact_by_email(req.to)
                if not contact and req.email:
                    # Create a temporary contact
                    from .utils.contact_manager import Contact, ChannelPreference
                    contact = Contact(
                        id=str(uuid4()),
                        name="Unknown",
                        phone=req.to if '@' not in req.to else None,
                        email=req.to if '@' in req.to else req.email
                    )

        # Check if contact has opted in
        if contact and not is_contact_opted_in(contact):
            processing_time = time.time() - start_time
            return SendMessageResponse(
                success=False,
                status="blocked",
                error="Contact has not opted in to receive messages",
                processing_time=processing_time
            )

        # Use LLM to enhance the message if requested
        text_to_send = req.text
        if req.use_llm_enhancement and (req.intent or req.text):
            intent = req.intent or req.text
            channel_type = ChannelType(req.channel) if req.channel else ChannelType.SMS

            llm_result: DraftResult = enhance_with_llm(
                intent=intent,
                channel=channel_type,
                recipient_info={
                    "name": contact.name if contact else None,
                    "relationship": contact.tags[0] if contact and contact.tags else "unknown"
                } if contact else None
            )

            if llm_result.success:
                text_to_send = llm_result.message
            else:
                logger.warning(f"LLM enhancement failed: {llm_result.error}, using original text")
                text_to_send = req.text

        # Sanitize the message
        text_to_send = sanitize_message(text_to_send)

        # Determine the channel to use
        channel_to_use = req.channel
        if not channel_to_use:
            if contact:
                channel_to_use = contact_manager.get_preferred_channel(contact).value
            else:
                # Default to SMS if no contact info
                channel_to_use = "sms"

        # Get fallback channels
        fallback_channels = req.fallback_channels
        if not fallback_channels and contact:
            fallback_channels = [ch.value for ch in contact_manager.get_fallback_channels(contact)]

        # Validate the message
        validation = validate_message(text_to_send, ChannelType(channel_to_use))
        if not validation["valid"]:
            processing_time = time.time() - start_time
            return SendMessageResponse(
                success=False,
                status="validation_failed",
                error=",".join(validation["errors"]),
                processing_time=processing_time
            )

        # Create message object
        msg_id = str(uuid4())
        message = Message(
            id=msg_id,
            to=req.to,
            text=text_to_send,
            channel=channel_to_use
        )
        message.priority = req.priority
        message.metadata = {"tags": req.tags, "source": "api"}

        # Process the message through the state machine
        process_success = process_message(message, contact)

        if not process_success or message.state == MessageState.BLOCKED:
            processing_time = time.time() - start_time
            return SendMessageResponse(
                success=False,
                status="blocked",
                error="Message blocked by safety filters",
                processing_time=processing_time
            )

        # Enqueue the message for processing
        await enqueue_message(
            to=req.to,
            text=text_to_send,
            channel=channel_to_use,
            fallback_channels=fallback_channels,
            priority=req.priority
        )

        # Record that a message was sent to this contact
        if contact:
            record_message_sent(contact.id)

        processing_time = time.time() - start_time
        logger.info(f"Message {msg_id} enqueued for {req.to} via {channel_to_use} in {processing_time:.2f}s")

        return SendMessageResponse(
            success=True,
            message_id=msg_id,
            status="enqueued",
            channel_used=channel_to_use,
            processing_time=processing_time,
            details={"tags": req.tags}
        )

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Error processing send request: {str(e)}")
        return SendMessageResponse(
            success=False,
            status="error",
            error=str(e),
            processing_time=processing_time
        )

@app.post("/draft")
async def draft_message_endpoint(req: DraftRequest):
    """
    Endpoint to draft a message using LLM without sending
    """
    start_time = time.time()
    try:
        intent = req.intent or req.text
        channel_type = ChannelType(req.channel) if req.channel else ChannelType.SMS

        result: DraftResult = enhance_with_llm(
            intent=intent,
            channel=channel_type,
            recipient_info={"relationship": "unknown"}  # Default recipient info
        )

        processing_time = time.time() - start_time
        if result.success:
            return {
                "success": True,
                "drafted_message": result.message,
                "processing_time": processing_time,
                "tokens_used": result.tokens_used
            }
        else:
            return {
                "success": False,
                "error": result.error,
                "processing_time": processing_time
            }
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Error drafting message: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "processing_time": processing_time
        }

@app.get("/")
async def root():
    return {
        "message": "LLM Messaging Service API",
        "version": "1.0.0",
        "android_clients": len(ANDROID_CLIENTS),
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": [
            "/send - Send a message",
            "/draft - Draft a message with LLM",
            "/ws/android - Android WebSocket gateway",
            "/health - Health check",
            "/metrics - Metrics endpoint",
            "/contacts - Manage contacts"
        ]
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    start_time = time.time()

    # Check channel adapters health
    channel_health = await channel_manager.health_check()

    # Check Redis connectivity (would need actual Redis connection check in production)
    redis_connected = True  # Placeholder - implement actual check

    # Check contact manager
    contact_stats = contact_manager.get_contact_stats()

    processing_time = time.time() - start_time

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "processing_time": processing_time,
        "android_gateways_connected": len(ANDROID_CLIENTS),
        "components": {
            "channel_adapters": channel_health,
            "redis": "connected" if redis_connected else "disconnected",
            "contact_manager": {
                "status": "ready",
                "stats": contact_stats
            }
        }
    }

@app.get("/metrics")
async def metrics():
    """Metrics endpoint for monitoring"""
    return {
        "android_connections": len(ANDROID_CLIENTS),
        "contacts_total": contact_manager.get_contact_stats().get('total_contacts', 0),
        "active_components": {
            "channel_adapters": len(channel_manager.adapters),
            "initialized": channel_manager.initialized
        }
    }

# Additional utility endpoints

@app.get("/contacts")
async def get_contacts(limit: Optional[int] = 100, offset: int = 0):
    """Get all contacts with pagination"""
    try:
        contacts = contact_manager.get_all_contacts(limit=limit, offset=offset)
        return {
            "success": True,
            "contacts": [c.__dict__ for c in contacts],
            "total": len(contacts),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error retrieving contacts: {e}")
        return {"success": False, "error": str(e)}

@app.get("/contacts/search")
async def search_contacts(query: str):
    """Search contacts by name, phone, or email"""
    try:
        contacts = contact_manager.search_contacts(query)
        return {
            "success": True,
            "contacts": [c.__dict__ for c in contacts],
            "total": len(contacts),
            "query": query
        }
    except Exception as e:
        logger.error(f"Error searching contacts: {e}")
        return {"success": False, "error": str(e)}

@app.get("/contacts/{contact_id}")
async def get_contact_by_id(contact_id: str):
    """Get a specific contact by ID"""
    try:
        contact = contact_manager.get_contact_by_id(contact_id)
        if contact:
            return {"success": True, "contact": contact.__dict__}
        else:
            raise HTTPException(status_code=404, detail="Contact not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving contact {contact_id}: {e}")
        return {"success": False, "error": str(e)}

@app.post("/contacts")
async def add_contact(contact_data: dict):
    """Add a new contact"""
    try:
        from .utils.contact_manager import Contact, ChannelPreference

        contact = Contact(
            id=str(uuid4()),
            name=contact_data["name"],
            phone=contact_data.get("phone"),
            email=contact_data.get("email"),
            imessage_capable=contact_data.get("imessage_capable", False),
            rcs_capable=contact_data.get("rcs_capable", False),
            preferred_channel=ChannelPreference(contact_data["preferred_channel"]) if contact_data.get("preferred_channel") else None,
            opt_in=contact_data.get("opt_in", True),
            tags=contact_data.get("tags", []),
            blocked=contact_data.get("blocked", False)
        )

        success = contact_manager.add_contact(contact)
        if success:
            return {"success": True, "contact_id": contact.id}
        else:
            return {"success": False, "error": "Contact already exists or invalid data"}
    except KeyError as e:
        return {"success": False, "error": f"Missing required field: {str(e)}"}
    except Exception as e:
        logger.error(f"Error adding contact: {e}")
        return {"success": False, "error": str(e)}

@app.put("/contacts/{contact_id}")
async def update_contact(contact_id: str, contact_data: dict):
    """Update an existing contact"""
    try:
        from .utils.contact_manager import Contact, ChannelPreference

        # Get existing contact to preserve unchanged fields
        existing_contact = contact_manager.get_contact_by_id(contact_id)
        if not existing_contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        # Update contact with provided data
        updated_contact = Contact(
            id=contact_id,
            name=contact_data.get("name", existing_contact.name),
            phone=contact_data.get("phone", existing_contact.phone),
            email=contact_data.get("email", existing_contact.email),
            imessage_capable=contact_data.get("imessage_capable", existing_contact.imessage_capable),
            rcs_capable=contact_data.get("rcs_capable", existing_contact.rcs_capable),
            preferred_channel=ChannelPreference(contact_data["preferred_channel"]) if contact_data.get("preferred_channel") else existing_contact.preferred_channel,
            opt_in=contact_data.get("opt_in", existing_contact.opt_in),
            tags=contact_data.get("tags", existing_contact.tags),
            blocked=contact_data.get("blocked", existing_contact.blocked)
        )

        success = contact_manager.update_contact(updated_contact)
        if success:
            return {"success": True, "contact_id": contact_id}
        else:
            return {"success": False, "error": "Failed to update contact"}
    except Exception as e:
        logger.error(f"Error updating contact {contact_id}: {e}")
        return {"success": False, "error": str(e)}

@app.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str):
    """Delete a contact"""
    try:
        success = contact_manager.delete_contact(contact_id)
        if success:
            return {"success": True, "message": "Contact deleted successfully"}
        else:
            return {"success": False, "error": "Contact not found"}
    except Exception as e:
        logger.error(f"Error deleting contact {contact_id}: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)