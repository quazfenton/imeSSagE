#!/usr/bin/env python3
"""
Demonstration of the LLM-Powered Free SMS/RCS/Email Service

This script demonstrates the core functionality of the messaging system
without requiring all external dependencies to be installed.
"""

import sys
import os
import json
from datetime import datetime
from uuid import uuid4

# Add server directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'server'))

from server.models.routing_state_machine import Message, MessageState, transition, process_message, send_worker
from server.utils.contact_manager import Contact, ChannelPreference, ContactManager

# Import LLM functionality with fallback
try:
    from server.llm import draft_message, ChannelType
    LLM_AVAILABLE = True
except ImportError:
    # Create fallback implementations
    def draft_message(intent, channel, recipient_info=None, sender_info=None):
        return f"[LLM not available] {intent}"

    from enum import Enum
    class ChannelType(str, Enum):
        SMS = "sms"
        EMAIL = "email"
        RCS = "rcs"
        IMESSAGE = "imessage"

    LLM_AVAILABLE = False


def demo_message_routing():
    """Demonstrate the message routing state machine"""
    print("=== Message Routing State Machine Demo ===\n")
    
    # Create a message
    msg = Message(
        id=str(uuid4()),
        to="+1234567890",
        text="Appointment reminder: Your meeting is at 3pm today."
    )
    
    print(f"Initial message state: {msg.state}")
    print(f"Message ID: {msg.id}")
    print(f"To: {msg.to}")
    print(f"Text: {msg.text}\n")
    
    # Process through state machine
    print("Processing message through state machine...")
    
    # Transition to ROUTING
    transition(msg, "route")
    print(f"After routing: {msg.state}")
    
    # Simulate successful routing decision
    msg.channel = "rcs"  # Selected channel
    transition(msg, "ok")
    print(f"After queueing: {msg.state}")
    
    # Simulate sending
    transition(msg, "send")
    print(f"After sending initiated: {msg.state}")
    
    # Simulate successful send
    transition(msg, "success")
    print(f"After successful send: {msg.state}")
    
    # Simulate confirmation
    transition(msg, "confirm")
    print(f"After confirmation: {msg.state}")
    
    print(f"\nFinal message state: {msg.state}")
    print(f"Channel used: {msg.channel}")
    

def demo_contact_management():
    """Demonstrate contact management"""
    print("\n=== Contact Management Demo ===\n")

    # Create a contact manager
    contact_manager = ContactManager(":memory:")  # Use in-memory DB for demo
    contact_manager.init_db()  # Initialize the database

    # Create a sample contact
    contact = Contact(
        id=str(uuid4()),
        name="Jane Smith",
        phone="+1987654321",
        email="jane@example.com",
        imessage_capable=True,
        rcs_capable=True,
        preferred_channel=ChannelPreference.RCS,
        tags=["customer", "priority"]
    )

    print(f"Created contact: {contact.name}")
    print(f"Phone: {contact.phone}")
    print(f"Email: {contact.email}")
    print(f"iMessage capable: {contact.imessage_capable}")
    print(f"RCS capable: {contact.rcs_capable}")
    print(f"Preferred channel: {contact.preferred_channel}")
    print(f"Tags: {contact.tags}")

    # Add to contact manager
    success = contact_manager.add_contact(contact)
    print(f"\nContact added successfully: {success}")

    # Retrieve the contact
    retrieved = contact_manager.get_contact_by_phone("+1987654321")
    print(f"Retrieved contact: {retrieved.name if retrieved else 'Not found'}")

    # Show channel preferences
    if retrieved:
        preferred = contact_manager.get_preferred_channel(retrieved)
        fallbacks = contact_manager.get_fallback_channels(retrieved)

        print(f"\nPreferred channel: {preferred}")
        print(f"Fallback channels: {fallbacks}")


def demo_message_drafting():
    """Demonstrate LLM-based message drafting"""
    print("\n=== Message Drafting Demo ===\n")
    
    # Example intents to draft
    intents = [
        ("appointment_reminder", "Remind John about his appointment tomorrow at 3pm"),
        ("meeting_update", "Inform the team about the meeting postponement"),
        ("welcome_message", "Welcome the new customer to our service")
    ]
    
    channels = [ChannelType.SMS, ChannelType.EMAIL]
    
    for intent_name, intent in intents:
        print(f"Intent: {intent_name} - '{intent}'")
        
        for channel in channels:
            drafted = draft_message(intent, channel)
            print(f"  {channel.value.upper()}: {drafted[:60]}{'...' if len(drafted) > 60 else ''}")
        
        print()


def demo_system_integration():
    """Demonstrate how components work together"""
    print("=== System Integration Demo ===\n")
    
    # Create a contact
    contact = Contact(
        id=str(uuid4()),
        name="Bob Johnson",
        phone="+15551234567",
        email="bob@example.com",
        imessage_capable=False,
        rcs_capable=True,
        preferred_channel=ChannelPreference.RCS,
        tags=["client"]
    )
    
    print(f"Contact: {contact.name} ({contact.phone})")
    print(f"Capabilities: RCS={contact.rcs_capable}, iMessage={contact.imessage_capable}")
    print(f"Preferred channel: {contact.preferred_channel}")
    
    # Draft a message for this contact
    intent = "Your package will arrive tomorrow between 2 and 4pm"
    channel_type = ChannelType(contact.preferred_channel.value)

    drafted_message = draft_message(
        intent,
        channel_type,
        recipient_info={
            "name": contact.name,
            "relationship": contact.tags[0] if contact.tags else "unknown"
        }
    )

    print(f"\nDrafted message: {drafted_message}")

    # Create a message object
    msg = Message(
        id=str(uuid4()),
        to=contact.phone,
        text=drafted_message,
        channel=contact.preferred_channel.value
    )
    
    print(f"\nMessage created:")
    print(f"  ID: {msg.id}")
    print(f"  To: {msg.to}")
    print(f"  Channel: {msg.channel}")
    print(f"  Text: {msg.text}")
    print(f"  State: {msg.state}")
    
    # Process through routing
    process_message(msg, contact)
    print(f"  After routing: {msg.state}")
    
    print(f"\nMessage is now ready for sending via {msg.channel}!")


def main():
    print("LLM-Powered Free SMS/RCS/Email Service - Demonstration")
    print("=" * 60)
    
    demo_message_routing()
    demo_contact_management()
    demo_message_drafting()
    demo_system_integration()
    
    print("\n" + "=" * 60)
    print("Demo completed! This demonstrates the core functionality of the")
    print("LLM-powered messaging system without external dependencies.")


if __name__ == "__main__":
    main()