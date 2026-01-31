import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from server.models.routing_state_machine import Message, MessageState, transition, send_worker
from server.utils.contact_manager import Contact, ChannelPreference
from server.llm import draft_message, ChannelType


def test_message_state_transitions():
    """Test that message state transitions work correctly"""
    msg = Message(id="test", to="+1234567890", text="Test message")
    
    # Initial state should be DRAFTED
    assert msg.state == MessageState.DRAFTED
    
    # Transition to ROUTING
    transition(msg, "route")
    assert msg.state == MessageState.ROUTING
    
    # Transition to QUEUED
    transition(msg, "ok")
    assert msg.state == MessageState.QUEUED
    
    # Transition to SENDING
    transition(msg, "send")
    assert msg.state == MessageState.SENDING
    
    # Transition to SENT
    transition(msg, "success")
    assert msg.state == MessageState.SENT
    
    print("✓ Message state transitions work correctly")


def test_draft_message_sms():
    """Test SMS message drafting"""
    intent = "Meeting at 3pm today"
    drafted = draft_message(intent, ChannelType.SMS)
    
    # SMS should be shortened if too long
    assert len(drafted) <= 160
    assert "3pm" in drafted
    
    print("✓ SMS message drafting works correctly")


def test_draft_message_email():
    """Test email message drafting"""
    intent = "Meeting reminder"
    recipient_info = {"name": "John Doe", "formal": True}
    sender_info = {"name": "Acme Corp"}
    
    drafted = draft_message(intent, ChannelType.EMAIL, recipient_info, sender_info)
    
    assert "Dear John Doe" in drafted
    assert "Acme Corp" in drafted
    assert "Meeting reminder" in drafted
    
    print("✓ Email message drafting works correctly")


def test_contact_creation():
    """Test contact creation and management"""
    contact = Contact(
        id="test_contact",
        name="Test User",
        phone="+1234567890",
        email="test@example.com",
        imessage_capable=True,
        preferred_channel=ChannelPreference.RCS
    )
    
    assert contact.name == "Test User"
    assert contact.phone == "+1234567890"
    assert contact.imessage_capable is True
    assert contact.preferred_channel == ChannelPreference.RCS
    
    print("✓ Contact creation works correctly")


def test_message_object_creation():
    """Test message object creation"""
    msg = Message(
        id="test_msg",
        to="+1234567890",
        text="Test message content"
    )
    
    assert msg.id == "test_msg"
    assert msg.to == "+1234567890"
    assert msg.text == "Test message content"
    assert msg.state == MessageState.DRAFTED
    assert msg.attempts == 0
    
    print("✓ Message object creation works correctly")


if __name__ == "__main__":
    test_message_state_transitions()
    test_draft_message_sms()
    test_draft_message_email()
    test_contact_creation()
    test_message_object_creation()
    
    print("\n🎉 All tests passed!")