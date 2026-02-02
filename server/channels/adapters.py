import smtplib
import asyncio
import ssl
import logging
from email.message import EmailMessage
from typing import Dict, Any, Optional
from dataclasses import dataclass
from ..redis_client import get_redis_client
import time


@dataclass
class SendResult:
    """Result of a send operation"""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ChannelAdapter:
    """Base class for all channel adapters"""

    async def send(self, message_data: Dict[str, Any]) -> SendResult:
        """Send a message via the channel. Must be implemented by subclasses."""
        raise NotImplementedError


class EmailAdapter(ChannelAdapter):
    """Adapter for sending emails via SMTP"""

    def __init__(self, smtp_server: str, smtp_port: int, username: str, password: str, from_email: str,
                 use_tls: bool = True, timeout: int = 30):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.use_tls = use_tls
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    async def send(self, message_data: Dict[str, Any]) -> SendResult:
        """Send an email message"""
        start_time = time.time()

        to_email = message_data.get('to')
        subject = message_data.get('subject', 'Message from LLM Service')
        body = message_data.get('text', '')
        html_body = message_data.get('html_body', '')  # Optional HTML version

        if not to_email:
            return SendResult(success=False, error="Recipient email address required")

        if not body and not html_body:
            return SendResult(success=False, error="Message body or HTML body required")

        try:
            msg = EmailMessage()
            msg["From"] = self.from_email
            msg["To"] = to_email
            msg["Subject"] = subject

            # Add both plain text and HTML versions if available
            if html_body:
                msg.add_alternative(html_body, subtype='html')
            if body:
                msg.set_content(body)

            # Create SMTP connection and send
            context = ssl.create_default_context()

            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=self.timeout) as smtp:
                if self.use_tls:
                    smtp.starttls(context=context)
                smtp.login(self.username, self.password)
                smtp.send_message(msg)

            processing_time = time.time() - start_time
            message_id = f"email_{hash(to_email + body + str(time.time()))}"

            self.logger.info(f"Email sent successfully to {to_email} in {processing_time:.2f}s")
            return SendResult(
                success=True,
                message_id=message_id,
                details={'processing_time': processing_time}
            )

        except smtplib.SMTPAuthenticationError as e:
            self.logger.error(f"SMTP authentication error for {to_email}: {str(e)}")
            return SendResult(success=False, error=f"Authentication failed: {str(e)}")
        except smtplib.SMTPRecipientsRefused as e:
            self.logger.error(f"Recipient refused for {to_email}: {str(e)}")
            return SendResult(success=False, error=f"Recipient refused: {str(e)}")
        except smtplib.SMTPServerDisconnected as e:
            self.logger.error(f"SMTP server disconnected for {to_email}: {str(e)}")
            return SendResult(success=False, error=f"Server disconnected: {str(e)}")
        except smtplib.SMTPException as e:
            self.logger.error(f"SMTP error for {to_email}: {str(e)}")
            return SendResult(success=False, error=f"SMTP error: {str(e)}")
        except Exception as e:
            self.logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return SendResult(success=False, error=f"Unexpected error: {str(e)}")


class AndroidAdapter(ChannelAdapter):
    """Adapter for sending SMS/RCS via Android WebSocket gateway"""

    def __init__(self, redis_client=None, timeout: int = 30):
        self.redis_client = redis_client
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    async def initialize(self):
        """Initialize the adapter"""
        if not self.redis_client:
            self.redis_client = await get_redis_client()

    async def send(self, message_data: Dict[str, Any]) -> SendResult:
        """Send an SMS/RCS message via Android gateway"""
        start_time = time.time()

        to_number = message_data.get('to')
        text = message_data.get('text', '')
        channel = message_data.get('channel', 'sms')  # 'sms' or 'rcs'
        message_id = message_data.get('message_id', f"sms_{int(time.time())}_{hash(to_number + text)}")

        if not to_number:
            return SendResult(success=False, error="Recipient phone number required")

        if not text:
            return SendResult(success=False, error="Message text required")

        try:
            # Validate phone number format (basic validation)
            if not isinstance(to_number, str) or len(to_number.replace('+', '').replace('-', '').replace(' ', '')) < 10:
                return SendResult(success=False, error="Invalid phone number format")

            # In a real implementation, this would send to the Android device via WebSocket
            # For now, we'll simulate by publishing to a Redis channel
            if not self.redis_client:
                await self.initialize()

            redis_client = self.redis_client or await get_redis_client()

            # Publish message to Android gateway
            await redis_client.publish("android_outbound", {
                "type": "send_message",
                "to": to_number,
                "text": text,
                "channel": channel,
                "message_id": message_id
            })

            processing_time = time.time() - start_time
            self.logger.info(f"Message {message_id} sent to Android gateway for {to_number} via {channel} in {processing_time:.2f}s")
            return SendResult(
                success=True,
                message_id=message_id,
                details={'processing_time': processing_time, 'channel': channel}
            )

        except Exception as e:
            self.logger.error(f"Failed to send message to Android gateway: {str(e)}")
            return SendResult(success=False, error=f"Gateway error: {str(e)}")


class IMessageAdapter(ChannelAdapter):
    """Adapter for sending iMessages via BlueBubbles or similar service"""

    def __init__(self, bluebubbles_url: str, api_key: str, timeout: int = 30):
        self.bluebubbles_url = bluebubbles_url
        self.api_key = api_key
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    async def send(self, message_data: Dict[str, Any]) -> SendResult:
        """Send an iMessage via BlueBubbles API"""
        import aiohttp
        import json

        start_time = time.time()

        to_address = message_data.get('to')
        text = message_data.get('text', '')
        device_id = message_data.get('device_id', 'default_device')  # Would come from config

        if not to_address:
            return SendResult(success=False, error="Recipient address required")

        if not text:
            return SendResult(success=False, error="Message text required")

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "deviceID": device_id,
                "message": text,
                "recipient": to_address
            }

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(
                    f"{self.bluebubbles_url}/api/v1/send",
                    json=payload,
                    headers=headers
                ) as response:
                    response_text = await response.text()

                    # Parse response
                    try:
                        result = json.loads(response_text)
                    except json.JSONDecodeError:
                        result = {"message": response_text}

                    if response.status == 200:
                        message_id = result.get("guid") or f"imsg_{int(time.time())}_{hash(to_address + text)}"
                        processing_time = time.time() - start_time

                        self.logger.info(f"iMessage sent successfully to {to_address} in {processing_time:.2f}s")
                        return SendResult(
                            success=True,
                            message_id=message_id,
                            details={'processing_time': processing_time, 'response': result}
                        )
                    else:
                        error_msg = result.get("message", f"HTTP {response.status}: {response_text}")
                        self.logger.error(f"iMessage API error for {to_address}: {error_msg}")
                        return SendResult(success=False, error=error_msg)

        except asyncio.TimeoutError:
            self.logger.error(f"Timeout sending iMessage to {to_address}")
            return SendResult(success=False, error="Request timeout")
        except aiohttp.ClientError as e:
            self.logger.error(f"Network error sending iMessage to {to_address}: {str(e)}")
            return SendResult(success=False, error=f"Network error: {str(e)}")
        except Exception as e:
            self.logger.error(f"Failed to send iMessage to {to_address}: {str(e)}")
            return SendResult(success=False, error=f"Unexpected error: {str(e)}")


class MockAdapter(ChannelAdapter):
    """Mock adapter for testing purposes"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.sent_messages = []

    async def send(self, message_data: Dict[str, Any]) -> SendResult:
        """Mock send - just log the message"""
        start_time = time.time()

        to = message_data.get('to')
        text = message_data.get('text', '')
        channel = message_data.get('channel', 'mock')

        message_id = f"mock_{int(time.time())}_{hash(to + text)}"

        mock_result = {
            'message_id': message_id,
            'to': to,
            'text': text,
            'channel': channel,
            'timestamp': time.time()
        }

        self.sent_messages.append(mock_result)

        processing_time = time.time() - start_time
        self.logger.info(f"Mock message {message_id} sent to {to} via {channel} in {processing_time:.2f}s")

        return SendResult(
            success=True,
            message_id=message_id,
            details={'processing_time': processing_time, 'mock_result': mock_result}
        )


# Global channel adapters instance
class ChannelAdapterManager:
    """Manages all channel adapters"""

    def __init__(self):
        self.adapters: Dict[str, ChannelAdapter] = {}
        self.initialized = False
        self.logger = logging.getLogger(self.__class__.__name__)

    async def initialize(self, config: Optional[Dict[str, Any]] = None):
        """Initialize all adapters"""
        if self.initialized:
            return

        # Get configuration from environment or provided config
        config = config or {}

        # Initialize email adapter (using environment variables or config)
        email_config = config.get('email', {})
        email_adapter = EmailAdapter(
            smtp_server=email_config.get('smtp_server', 'smtp.gmail.com'),
            smtp_port=email_config.get('smtp_port', 465),
            username=email_config.get('username', 'your_email@gmail.com'),
            password=email_config.get('password', 'your_app_password'),
            from_email=email_config.get('from_email', 'your_email@gmail.com'),
            use_tls=email_config.get('use_tls', True),
            timeout=email_config.get('timeout', 30)
        )

        # Initialize Android adapter
        android_adapter = AndroidAdapter(timeout=config.get('android_timeout', 30))
        await android_adapter.initialize()

        # Initialize iMessage adapter (optional)
        imessage_config = config.get('imessage', {})
        if imessage_config.get('enabled', False):
            imessage_adapter = IMessageAdapter(
                bluebubbles_url=imessage_config.get('bluebubbles_url', 'http://localhost:8080'),
                api_key=imessage_config.get('api_key', 'your_bluebubbles_api_key'),
                timeout=imessage_config.get('timeout', 30)
            )
        else:
            # Use mock adapter if iMessage is not configured
            imessage_adapter = MockAdapter()

        # Register adapters
        self.adapters = {
            "email": email_adapter,
            "sms": android_adapter,
            "rcs": android_adapter,
            "imessage": imessage_adapter
        }

        # Add mock adapter for testing
        self.adapters["mock"] = MockAdapter()

        self.initialized = True
        self.logger.info("Channel adapters initialized successfully")

    def get_adapter(self, channel: str) -> Optional[ChannelAdapter]:
        """Get an adapter for a specific channel"""
        if not self.initialized:
            self.logger.warning("ChannelAdapterManager not initialized, returning None")
            return None
        return self.adapters.get(channel.lower())

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all adapters"""
        if not self.initialized:
            return {"status": "not_initialized", "adapters": {}}

        results = {}
        for channel, adapter in self.adapters.items():
            try:
                # For now, just check if adapter exists and is accessible
                # More sophisticated health checks could be implemented
                results[channel] = {"status": "available", "error": None}
            except Exception as e:
                results[channel] = {"status": "error", "error": str(e)}

        return {"status": "healthy", "adapters": results}


# Global instance
channel_manager = ChannelAdapterManager()


async def send_via_channel(message_data: Dict[str, Any]) -> SendResult:
    """Send a message via the appropriate channel"""
    channel = message_data.get('channel', 'sms')

    if not channel_manager.initialized:
        await channel_manager.initialize()

    adapter = channel_manager.get_adapter(channel)

    if not adapter:
        return SendResult(success=False, error=f"No adapter available for channel: {channel}")

    return await adapter.send(message_data)


async def get_channel_health() -> Dict[str, Any]:
    """Get health status of all channel adapters"""
    return await channel_manager.health_check()