from fastapi import FastAPI, WebSocket, HTTPException
from pydantic import BaseModel
import asyncio
import smtplib
from email.message import EmailMessage
import logging
from typing import Optional, List
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Global set to hold active Android WebSocket connections
ANDROID_CLIENTS = set()

class MessageState(str, Enum):
    DRAFTED = "drafted"
    ROUTING = "routing"
    BLOCKED = "blocked"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    FALLBACK = "fallback"

class DraftRequest(BaseModel):
    to: str
    channel: str  # rcs | sms | email
    text: str
    email: Optional[str] = None
    fallback_channels: Optional[List[str]] = []

@app.websocket("/ws/android")
async def android_gateway(ws: WebSocket):
    await ws.accept()
    ANDROID_CLIENTS.add(ws)
    logger.info(f"Android client connected. Total clients: {len(ANDROID_CLIENTS)}")
    
    try:
        while True:
            data = await ws.receive_json()
            logger.info(f"Incoming from phone: {data}")
            
            # Handle different types of messages from the Android device
            msg_type = data.get("type")
            if msg_type == "delivery_receipt":
                # Process delivery receipt
                logger.info(f"Delivery receipt received: {data}")
            elif msg_type == "incoming_message":
                # Process incoming message
                logger.info(f"Incoming message: {data}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        ANDROID_CLIENTS.discard(ws)
        logger.info(f"Android client disconnected. Total clients: {len(ANDROID_CLIENTS)}")

@app.post("/send")
async def send_message(req: DraftRequest):
    """
    Main endpoint to send messages via different channels
    """
    logger.info(f"Sending message to {req.to} via {req.channel}: {req.text}")
    
    if req.channel in ("rcs", "sms"):
        if not ANDROID_CLIENTS:
            logger.error("No Android gateway online")
            return {"error": "no android gateway online"}
        
        # Send message to Android device
        ws = next(iter(ANDROID_CLIENTS))  # Get first available client
        await ws.send_json({
            "type": "send_message",
            "to": req.to,
            "text": req.text,
            "channel": req.channel
        })
        logger.info(f"Message sent to Android device for {req.to}")
        return {"status": "sent via android", "channel": req.channel}

    elif req.channel == "email":
        if not req.email:
            return {"error": "email address required for email channel"}
        
        try:
            send_email(req.email, req.text)
            logger.info(f"Email sent to {req.email}")
            return {"status": "email sent", "channel": req.channel}
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return {"error": f"email sending failed: {str(e)}"}
    
    else:
        return {"error": f"unsupported channel: {req.channel}"}

def send_email(to_email: str, body: str):
    """
    Send email via SMTP
    """
    # These should come from environment/config in production
    smtp_server = "smtp.gmail.com"
    smtp_port = 465
    sender_email = "your_email@gmail.com"  # Replace with actual email
    sender_password = "your_app_password"  # Replace with actual app password
    
    msg = EmailMessage()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = "Message from LLM Service"
    msg.set_content(body)

    with smtplib.SMTP_SSL(smtp_server, smtp_port) as smtp:
        smtp.login(sender_email, sender_password)
        smtp.send_message(msg)

@app.get("/")
async def root():
    return {"message": "LLM Messaging Service API", "android_clients": len(ANDROID_CLIENTS)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)