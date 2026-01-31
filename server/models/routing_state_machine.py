from enum import Enum
from typing import Optional, List, Dict, Any
import time
import random
import logging


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


class Message:
    def __init__(self, id: str, to: str, text: str, channel: Optional[str] = None):
        self.id = id
        self.to = to
        self.text = text
        self.state = MessageState.DRAFTED
        self.channel = channel
        self.attempts = 0
        self.max_attempts = 3
        self.fallback_channels: List[str] = []
        self.last_error: Optional[str] = None
        self.created_at = time.time()
        self.sent_at: Optional[float] = None
        self.confirmed_at: Optional[float] = None
        self.priority: int = 1  # Higher number = higher priority
        self.expires_at: Optional[float] = None  # Timestamp when message expires
        self.retry_after: Optional[float] = None  # Timestamp for next retry
        self.metadata: Dict[str, Any] = {}  # Additional metadata for the message


def transition(msg: Message, event: str) -> bool:
    """
    State transition function for the message routing state machine
    Returns True if transition was successful, False otherwise
    """
    # Define the state transition table
    transition_table = {
        MessageState.DRAFTED: {
            "route": MessageState.ROUTING
        },
        MessageState.ROUTING: {
            "blocked": MessageState.BLOCKED,
            "ok": MessageState.QUEUED
        },
        MessageState.BLOCKED: {
            # No transitions from blocked state
        },
        MessageState.QUEUED: {
            "send": MessageState.SENDING
        },
        MessageState.SENDING: {
            "success": MessageState.SENT,
            "error": MessageState.FAILED
        },
        MessageState.SENT: {
            "confirm": MessageState.CONFIRMED,
            "timeout": MessageState.CONFIRMED  # optimistic
        },
        MessageState.CONFIRMED: {
            # No transitions from confirmed state
        },
        MessageState.FAILED: {
            "retry": MessageState.QUEUED,
            "fallback": MessageState.FALLBACK
        },
        MessageState.FALLBACK: {
            "reroute": MessageState.QUEUED
        }
    }

    # Check if the transition is valid
    if msg.state in transition_table and event in transition_table[msg.state]:
        old_state = msg.state
        msg.state = transition_table[msg.state][event]

        # Update timestamps based on state
        if msg.state == MessageState.SENT:
            msg.sent_at = time.time()
        elif msg.state == MessageState.CONFIRMED:
            msg.confirmed_at = time.time()

        logging.info(f"Message {msg.id} transitioned from {old_state} to {msg.state} via event '{event}'")
        return True
    else:
        logging.warning(f"No transition defined for state {msg.state} with event '{event}' for message {msg.id}")
        return False


def choose_channel(contact) -> Optional[str]:
    """
    Routing rules engine to select the best channel for a contact
    Returns None if no suitable channel is found
    """
    if contact is None:
        return "sms"  # Default fallback

    # Check for iMessage capability
    if hasattr(contact, 'imessage') and contact.imessage:
        return "imessage"

    # Check for RCS capability
    if hasattr(contact, 'rcs') and contact.rcs:
        return "rcs"

    # Check for email
    if hasattr(contact, 'email') and contact.email:
        return "email"

    # Check for SMS
    if hasattr(contact, 'phone') and contact.phone:
        return "sms"

    # No suitable channel found
    return None


def process_message(msg: Message, contact) -> bool:
    """
    Main processing loop for a message
    Returns True if processing should continue, False if blocked
    """
    try:
        # Transition to routing state
        transition(msg, "route")

        # Choose the best channel for the contact
        channel = choose_channel(contact)
        if channel is None:
            logging.error(f"No suitable channel found for message {msg.id}")
            transition(msg, "blocked")
            return False

        msg.channel = channel

        # Check if the message should be blocked
        if is_blocked(contact, msg):
            logging.info(f"Message {msg.id} blocked by safety filters")
            transition(msg, "blocked")
            return False

        # Transition to queued state
        transition(msg, "ok")
        logging.info(f"Message {msg.id} processed successfully, channel: {msg.channel}")
        return True

    except Exception as e:
        logging.error(f"Error processing message {msg.id}: {str(e)}")
        msg.last_error = str(e)
        transition(msg, "error")
        return False


def send_worker(msg: Message) -> bool:
    """
    Worker function to send a message via its selected channel
    Returns True if successful, False if failed
    """
    try:
        transition(msg, "send")

        # Add human-like delay before sending
        human_delay()

        send_via_channel(msg)
        transition(msg, "success")
        logging.info(f"Message {msg.id} sent successfully via {msg.channel}")
        return True

    except Exception as e:
        msg.last_error = str(e)
        msg.attempts += 1
        logging.error(f"Failed to send message {msg.id} via {msg.channel}: {str(e)}. Attempt {msg.attempts}/{msg.max_attempts}")

        if msg.attempts < msg.max_attempts:
            transition(msg, "retry")
            # Set retry time to 30 seconds from now
            msg.retry_after = time.time() + 30
            return False
        else:
            transition(msg, "fallback")
            return False


def fallback(msg: Message) -> bool:
    """
    Fallback logic when primary channel fails
    Returns True if fallback channel is available, False otherwise
    """
    if not msg.fallback_channels:
        logging.info(f"No fallback channels available for message {msg.id}, marking as failed")
        msg.state = MessageState.FAILED
        return False

    # Use the next fallback channel
    msg.channel = msg.fallback_channels.pop(0)
    msg.attempts = 0
    transition(msg, "reroute")
    logging.info(f"Message {msg.id} falling back to channel: {msg.channel}")
    return True


def send_via_channel(msg: Message):
    """
    Placeholder function for sending via different channels
    This would be implemented with actual channel adapters
    """
    if not msg.channel:
        raise ValueError(f"No channel specified for message {msg.id}")

    if msg.channel == "rcs":
        # Would connect to Android gateway
        logging.info(f"Sending via RCS to {msg.to}: {msg.text[:50]}...")
        # Actual implementation would connect to Android gateway
    elif msg.channel == "imessage":
        # Would connect to BlueBubbles
        logging.info(f"Sending via iMessage to {msg.to}: {msg.text[:50]}...")
        # Actual implementation would connect to BlueBubbles
    elif msg.channel == "email":
        # Would use SMTP
        logging.info(f"Sending via Email to {msg.to}: {msg.text[:50]}...")
        # Actual implementation would use SMTP
    elif msg.channel == "sms":
        # Would connect to Android gateway
        logging.info(f"Sending via SMS to {msg.to}: {msg.text[:50]}...")
        # Actual implementation would connect to Android gateway
    else:
        raise ValueError(f"Unknown channel: {msg.channel}")


def confirm_worker(msg: Message) -> bool:
    """
    Check for delivery confirmation
    Returns True if confirmed, False otherwise
    """
    try:
        if receipt_seen(msg):
            transition(msg, "confirm")
            logging.info(f"Message {msg.id} confirmed delivered")
            return True
        else:
            # If not confirmed, we might want to check again later
            logging.debug(f"Message {msg.id} not yet confirmed")
            return False
    except Exception as e:
        logging.error(f"Error checking confirmation for message {msg.id}: {str(e)}")
        return False


def receipt_seen(msg: Message) -> bool:
    """
    Check if a receipt has been seen for the message
    This is a simulation - in reality this would check external systems
    """
    # In a real implementation, this would check external systems
    # For now, we'll simulate with a probability based on channel
    if msg.channel == "email":
        # Email has lower confirmation rate
        return random.random() < 0.7
    elif msg.channel in ["rcs", "imessage"]:
        # Rich messaging has higher confirmation rate
        return random.random() < 0.9
    else:
        # SMS has medium confirmation rate
        return random.random() < 0.8


def human_delay():
    """
    Add human-like delays before sending
    """
    # Use a more realistic distribution for human-like delays
    delay = random.uniform(1.2, 4.5)
    time.sleep(delay)


def is_blocked(contact, msg: Message) -> bool:
    """
    Safety check to prevent abuse
    """
    try:
        # Check if contact exists and has opted in
        if contact is None:
            return False  # Allow messages to unknown contacts (for new user onboarding)

        if hasattr(contact, 'opt_in') and not contact.opt_in:
            return True

        # Check if contact is blocked
        if hasattr(contact, 'blocked') and contact.blocked:
            return True

        # Check message frequency per contact
        # This would require access to historical data in a real implementation
        # For now, we'll just return False
        return False

    except Exception as e:
        logging.error(f"Error in is_blocked check: {str(e)}")
        return True  # If there's an error, block the message as a safety measure