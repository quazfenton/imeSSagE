from typing import Dict, List, Optional, Any
from enum import Enum
import sqlite3
import json
import logging
from datetime import datetime
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import threading


class ChannelPreference(Enum):
    """Enumeration of communication channel preferences"""
    SMS = "sms"
    RCS = "rcs"
    EMAIL = "email"
    IMESSAGE = "imessage"


@dataclass
class Contact:
    """Data class representing a contact"""
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    imessage_capable: bool = False
    rcs_capable: bool = False
    preferred_channel: Optional[ChannelPreference] = None
    opt_in: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_contact_date: Optional[datetime] = None
    message_count: int = 0
    blocked: bool = False
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


class ContactManager:
    """Manages contacts and their preferences"""

    def __init__(self, db_path: str = "contacts.db"):
        self.db_path = db_path
        self.lock = threading.Lock()  # Thread-safe operations
        self.init_db()

    def init_db(self):
        """Initialize the contacts database"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                self._create_table_if_not_exists(cursor)
        except Exception as e:
            logging.error(f"Failed to initialize database: {e}")
            raise

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()

    def _create_table_if_not_exists(self, cursor):
        """Create the contacts table if it doesn't exist"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                imessage_capable BOOLEAN DEFAULT FALSE,
                rcs_capable BOOLEAN DEFAULT FALSE,
                preferred_channel TEXT,
                opt_in BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_contact_date TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                blocked BOOLEAN DEFAULT FALSE,
                tags TEXT DEFAULT '[]',
                UNIQUE(phone, email)
            )
        """)

    def add_contact(self, contact: Contact) -> bool:
        """Add a new contact to the database"""
        try:
            with self.lock:  # Ensure thread safety
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    self._create_table_if_not_exists(cursor)

                    cursor.execute("""
                        INSERT INTO contacts (
                            id, name, phone, email, imessage_capable, rcs_capable,
                            preferred_channel, opt_in, last_contact_date, message_count,
                            blocked, tags
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        contact.id, contact.name, contact.phone, contact.email,
                        contact.imessage_capable, contact.rcs_capable,
                        contact.preferred_channel.value if contact.preferred_channel else None,
                        contact.opt_in, contact.last_contact_date, contact.message_count,
                        contact.blocked, json.dumps(contact.tags)
                    ))

                    conn.commit()
                    logging.info(f"Contact {contact.name} added successfully")
                    return True
        except sqlite3.IntegrityError as e:
            logging.warning(f"Contact with phone/email already exists: {e}")
            return False
        except Exception as e:
            logging.error(f"Error adding contact {contact.name}: {e}")
            return False

    def update_contact(self, contact: Contact) -> bool:
        """Update an existing contact"""
        try:
            with self.lock:  # Ensure thread safety
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    cursor.execute("""
                        UPDATE contacts SET
                            name = ?,
                            phone = ?,
                            email = ?,
                            imessage_capable = ?,
                            rcs_capable = ?,
                            preferred_channel = ?,
                            opt_in = ?,
                            updated_at = CURRENT_TIMESTAMP,
                            last_contact_date = ?,
                            message_count = ?,
                            blocked = ?,
                            tags = ?
                        WHERE id = ?
                    """, (
                        contact.name, contact.phone, contact.email,
                        contact.imessage_capable, contact.rcs_capable,
                        contact.preferred_channel.value if contact.preferred_channel else None,
                        contact.opt_in, contact.last_contact_date, contact.message_count,
                        contact.blocked, json.dumps(contact.tags), contact.id
                    ))

                    rows_affected = cursor.rowcount
                    conn.commit()

                    if rows_affected > 0:
                        logging.info(f"Contact {contact.name} updated successfully")
                        return True
                    else:
                        logging.warning(f"Contact with ID {contact.id} not found for update")
                        return False
        except Exception as e:
            logging.error(f"Error updating contact {contact.name}: {e}")
            return False

    def get_contact_by_id(self, contact_id: str) -> Optional[Contact]:
        """Retrieve a contact by ID"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
                row = cursor.fetchone()

                if row:
                    return self._row_to_contact(row)
                return None
        except Exception as e:
            logging.error(f"Error retrieving contact by ID {contact_id}: {e}")
            return None

    def get_contact_by_phone(self, phone: str) -> Optional[Contact]:
        """Retrieve a contact by phone number"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                self._create_table_if_not_exists(cursor)

                cursor.execute("SELECT * FROM contacts WHERE phone = ?", (phone,))
                row = cursor.fetchone()

                if row:
                    return self._row_to_contact(row)
                return None
        except Exception as e:
            logging.error(f"Error retrieving contact by phone {phone}: {e}")
            return None

    def get_contact_by_email(self, email: str) -> Optional[Contact]:
        """Retrieve a contact by email address"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT * FROM contacts WHERE email = ?", (email,))
                row = cursor.fetchone()

                if row:
                    return self._row_to_contact(row)
                return None
        except Exception as e:
            logging.error(f"Error retrieving contact by email {email}: {e}")
            return None

    def search_contacts(self, query: str) -> List[Contact]:
        """Search contacts by name, phone, or email"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT * FROM contacts
                    WHERE name LIKE ? OR phone LIKE ? OR email LIKE ?
                    ORDER BY name
                """, (f"%{query}%", f"%{query}%", f"%{query}%"))

                rows = cursor.fetchall()
                return [self._row_to_contact(row) for row in rows]
        except Exception as e:
            logging.error(f"Error searching contacts with query '{query}': {e}")
            return []

    def get_all_contacts(self, limit: Optional[int] = None, offset: int = 0) -> List[Contact]:
        """Retrieve all contacts with optional pagination"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                query = "SELECT * FROM contacts ORDER BY name"
                params = []

                if limit is not None:
                    query += " LIMIT ? OFFSET ?"
                    params.extend([limit, offset])
                else:
                    query += " LIMIT 1000"  # Prevent loading too many records at once
                    params.append(1000)

                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._row_to_contact(row) for row in rows]
        except Exception as e:
            logging.error(f"Error retrieving all contacts: {e}")
            return []

    def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact by ID"""
        try:
            with self.lock:  # Ensure thread safety
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    cursor.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
                    rows_affected = cursor.rowcount
                    conn.commit()

                    if rows_affected > 0:
                        logging.info(f"Contact with ID {contact_id} deleted successfully")
                        return True
                    else:
                        logging.warning(f"Contact with ID {contact_id} not found for deletion")
                        return False
        except Exception as e:
            logging.error(f"Error deleting contact with ID {contact_id}: {e}")
            return False

    def increment_message_count(self, contact_id: str) -> bool:
        """Increment the message count for a contact"""
        try:
            with self.lock:  # Ensure thread safety
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    cursor.execute("""
                        UPDATE contacts
                        SET message_count = message_count + 1,
                            last_contact_date = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (contact_id,))

                    rows_affected = cursor.rowcount
                    conn.commit()

                    if rows_affected > 0:
                        logging.info(f"Message count incremented for contact {contact_id}")
                        return True
                    else:
                        logging.warning(f"Contact with ID {contact_id} not found for message count increment")
                        return False
        except Exception as e:
            logging.error(f"Error incrementing message count for contact {contact_id}: {e}")
            return False

    def get_preferred_channel(self, contact: Contact) -> ChannelPreference:
        """Get the preferred channel for a contact"""
        # If contact has a preferred channel, use it
        if contact.preferred_channel:
            return contact.preferred_channel

        # Otherwise, determine based on capabilities
        if contact.imessage_capable:
            return ChannelPreference.IMESSAGE
        elif contact.rcs_capable:
            return ChannelPreference.RCS
        elif contact.email:
            return ChannelPreference.EMAIL
        elif contact.phone:
            return ChannelPreference.SMS

        # Default to SMS if no other options
        return ChannelPreference.SMS

    def get_fallback_channels(self, contact: Contact) -> List[ChannelPreference]:
        """Get fallback channels for a contact in priority order"""
        channels = []

        # Add preferred channel first if set
        if contact.preferred_channel and contact.preferred_channel not in channels:
            channels.append(contact.preferred_channel)

        # Add other available channels in priority order
        if contact.imessage_capable and ChannelPreference.IMESSAGE not in channels:
            channels.append(ChannelPreference.IMESSAGE)

        if contact.rcs_capable and ChannelPreference.RCS not in channels:
            channels.append(ChannelPreference.RCS)

        if contact.email and ChannelPreference.EMAIL not in channels:
            channels.append(ChannelPreference.EMAIL)

        if contact.phone and ChannelPreference.SMS not in channels:
            channels.append(ChannelPreference.SMS)

        return channels

    def _row_to_contact(self, row) -> Contact:
        """Convert a database row to a Contact object"""
        try:
            return Contact(
                id=row['id'],
                name=row['name'],
                phone=row['phone'],
                email=row['email'],
                imessage_capable=bool(row['imessage_capable']),
                rcs_capable=bool(row['rcs_capable']),
                preferred_channel=ChannelPreference(row['preferred_channel']) if row['preferred_channel'] else None,
                opt_in=bool(row['opt_in']),
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
                last_contact_date=datetime.fromisoformat(row['last_contact_date']) if row['last_contact_date'] else None,
                message_count=row['message_count'] if row['message_count'] else 0,
                blocked=bool(row['blocked']),
                tags=json.loads(row['tags']) if row['tags'] else []
            )
        except Exception as e:
            logging.error(f"Error converting database row to Contact object: {e}")
            # Return a minimal contact object in case of conversion error
            return Contact(
                id=row['id'],
                name=row['name'],
                phone=row['phone'],
                email=row['email']
            )

    def get_contact_stats(self) -> Dict[str, Any]:
        """Get statistics about contacts in the database"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Count total contacts
                cursor.execute("SELECT COUNT(*) as count FROM contacts")
                total_contacts = cursor.fetchone()['count']

                # Count opted-in contacts
                cursor.execute("SELECT COUNT(*) as count FROM contacts WHERE opt_in = 1")
                opted_in_contacts = cursor.fetchone()['count']

                # Count blocked contacts
                cursor.execute("SELECT COUNT(*) as count FROM contacts WHERE blocked = 1")
                blocked_contacts = cursor.fetchone()['count']

                # Count contacts by channel capability
                cursor.execute("SELECT COUNT(*) as count FROM contacts WHERE imessage_capable = 1")
                imessage_contacts = cursor.fetchone()['count']

                cursor.execute("SELECT COUNT(*) as count FROM contacts WHERE rcs_capable = 1")
                rcs_contacts = cursor.fetchone()['count']

                cursor.execute("SELECT COUNT(*) as count FROM contacts WHERE email IS NOT NULL")
                email_contacts = cursor.fetchone()['count']

                cursor.execute("SELECT COUNT(*) as count FROM contacts WHERE phone IS NOT NULL")
                phone_contacts = cursor.fetchone()['count']

                return {
                    'total_contacts': total_contacts,
                    'opted_in_contacts': opted_in_contacts,
                    'blocked_contacts': blocked_contacts,
                    'imessage_capable': imessage_contacts,
                    'rcs_capable': rcs_contacts,
                    'email_enabled': email_contacts,
                    'phone_enabled': phone_contacts
                }
        except Exception as e:
            logging.error(f"Error getting contact stats: {e}")
            return {}


# Global contact manager instance
contact_manager = ContactManager()


# Functions to interact with the contact manager
def get_contact_for_sending(to_identifier: str) -> Optional[Contact]:
    """
    Get a contact by phone number or email for message sending
    """
    # Try to find by phone first
    contact = contact_manager.get_contact_by_phone(to_identifier)

    if not contact:
        # Then try by email
        contact = contact_manager.get_contact_by_email(to_identifier)

    return contact


def record_message_sent(contact_id: str):
    """
    Record that a message was sent to a contact
    """
    contact_manager.increment_message_count(contact_id)


def is_contact_opted_in(contact: Contact) -> bool:
    """
    Check if a contact has opted in to receive messages
    """
    if contact is None:
        return False
    return contact.opt_in and not contact.blocked


def get_best_channel_for_contact(contact: Contact) -> str:
    """
    Determine the best channel to use for contacting someone
    """
    if contact is None:
        return "sms"  # Default fallback
    preferred = contact_manager.get_preferred_channel(contact)
    return preferred.value


def get_fallback_channels_for_contact(contact: Contact) -> List[str]:
    """
    Get fallback channels for a contact
    """
    if contact is None:
        return ["sms", "email"]  # Default fallbacks
    fallbacks = contact_manager.get_fallback_channels(contact)
    return [fb.value for fb in fallbacks]


# Example usage
if __name__ == "__main__":
    # Example of creating and using contacts
    from uuid import uuid4

    # Create a sample contact
    sample_contact = Contact(
        id=str(uuid4()),
        name="John Doe",
        phone="+1234567890",
        email="john@example.com",
        imessage_capable=True,
        rcs_capable=True,
        preferred_channel=ChannelPreference.RCS,
        tags=["customer", "priority"]
    )

    # Add to contact manager
    success = contact_manager.add_contact(sample_contact)
    print(f"Contact added: {success}")

    # Retrieve the contact
    retrieved = contact_manager.get_contact_by_phone("+1234567890")
    if retrieved:
        print(f"Retrieved contact: {retrieved.name}")
        print(f"Preferred channel: {contact_manager.get_preferred_channel(retrieved)}")
        print(f"Fallback channels: {contact_manager.get_fallback_channels(retrieved)}")

        # Get stats
        stats = contact_manager.get_contact_stats()
        print(f"Contact stats: {stats}")