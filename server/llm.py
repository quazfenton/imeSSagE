import openai
from typing import Dict, Any, Optional
import os
import logging
import time
from enum import Enum
from dataclasses import dataclass


class ChannelType(str, Enum):
    SMS = "sms"
    EMAIL = "email"
    RCS = "rcs"
    IMESSAGE = "imessage"


@dataclass
class DraftResult:
    """Result of message drafting operation"""
    success: bool
    message: str
    error: Optional[str] = None
    tokens_used: Optional[int] = None
    processing_time: Optional[float] = None


def draft_message(
    intent: str,
    channel: ChannelType,
    recipient_info: Optional[Dict[str, Any]] = None,
    sender_info: Optional[Dict[str, Any]] = None
) -> DraftResult:
    """
    Draft a message based on intent and channel constraints
    Returns a DraftResult object with success status and message
    """
    start_time = time.time()

    try:
        if channel == ChannelType.SMS:
            # SMS has character limit and informal tone
            draft = _draft_sms(intent, recipient_info, sender_info)
        elif channel == ChannelType.EMAIL:
            # Email can be longer and more formal
            draft = _draft_email(intent, recipient_info, sender_info)
        elif channel in [ChannelType.RCS, ChannelType.IMESSAGE]:
            # RCS and iMessage allow for richer formatting
            draft = _draft_rich_message(intent, recipient_info, sender_info)
        else:
            # Default to SMS format
            draft = _draft_sms(intent, recipient_info, sender_info)

        processing_time = time.time() - start_time
        return DraftResult(success=True, message=draft, processing_time=processing_time)

    except Exception as e:
        logging.error(f"Error drafting message: {e}")
        processing_time = time.time() - start_time
        return DraftResult(success=False, message="", error=str(e), processing_time=processing_time)


def _draft_sms(intent: str, recipient_info: Optional[Dict], sender_info: Optional[Dict]) -> str:
    """
    Draft an SMS message considering character limits and tone
    """
    # SMS typically limited to 160 characters for single message
    max_length = 160

    # Simple approach: truncate to max length if needed
    draft = intent.strip()

    if len(draft) > max_length:
        # Try to find a good breaking point
        draft = draft[:max_length-3] + "..."

    # Add informal touches if appropriate
    if recipient_info and recipient_info.get('relationship') in ['friend', 'family']:
        # Maybe add casual punctuation or shorten words
        pass

    return draft


def _draft_email(intent: str, recipient_info: Optional[Dict], sender_info: Optional[Dict]) -> str:
    """
    Draft an email with appropriate salutation and closing
    """
    salutation = "Hi"
    closing = "Best regards"

    if recipient_info:
        if recipient_info.get('formal'):
            salutation = f"Dear {recipient_info.get('name', 'Sir/Madam')}"
            closing = "Sincerely"
        elif recipient_info.get('name'):
            salutation = f"Hi {recipient_info.get('name')}"

    if sender_info:
        if sender_info.get('name'):
            closing = f"Best regards,\n{sender_info.get('name')}"

    draft = f"{salutation},\n\n{intent}\n\n{closing}"
    return draft


def _draft_rich_message(intent: str, recipient_info: Optional[Dict], sender_info: Optional[Dict]) -> str:
    """
    Draft a message for rich communication channels (RCS, iMessage)
    These can include more formatting and slightly longer content
    """
    # Rich messages can be a bit longer than SMS
    max_length = 300

    draft = intent.strip()

    if len(draft) > max_length:
        draft = draft[:max_length-3] + "..."

    # Could add rich formatting here if needed
    return draft


def enhance_with_llm(
    intent: str,
    channel: ChannelType,
    recipient_info: Optional[Dict[str, Any]] = None,
    sender_info: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    model: str = "gpt-3.5-turbo",
    max_retries: int = 3
) -> DraftResult:
    """
    Use an LLM to enhance the drafted message based on context
    """
    start_time = time.time()

    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        # Fallback to simple drafting if no API key
        logging.warning("No OpenAI API key provided, using simple drafting")
        return draft_message(intent, channel, recipient_info, sender_info)

    # Prepare context for the LLM
    context_parts = []

    context_parts.append(f"The message should be appropriate for {channel.value} channel.")

    if recipient_info:
        if 'name' in recipient_info:
            context_parts.append(f"The recipient's name is {recipient_info['name']}.")
        if 'relationship' in recipient_info:
            context_parts.append(f"The relationship with recipient is {recipient_info['relationship']}.")
        if 'tone_preference' in recipient_info:
            context_parts.append(f"The recipient prefers {recipient_info['tone_preference']} tone.")
        if 'language' in recipient_info:
            context_parts.append(f"The recipient prefers {recipient_info['language']} language.")

    if sender_info:
        if 'name' in sender_info:
            context_parts.append(f"The sender's name is {sender_info['name']}.")

    context = " ".join(context_parts)

    # Construct the prompt for the LLM
    prompt = f"""
Context: {context}

Original intent: {intent}

Please draft an appropriate message for the specified channel and context.
The message should be concise and appropriate for the relationship between sender and recipient.
For SMS, keep it under 160 characters. For email, include appropriate greeting and closing.
For RCS/iMessage, you can use a conversational tone.

Drafted message:
"""

    # Retry mechanism
    for attempt in range(max_retries):
        try:
            # Using OpenAI API to enhance the message
            client = openai.OpenAI(api_key=api_key)

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.7
            )

            enhanced_message = response.choices[0].message.content.strip()
            tokens_used = response.usage.total_tokens if response.usage else None

            # Apply channel-specific constraints to the LLM-generated message
            if channel == ChannelType.SMS and len(enhanced_message) > 160:
                enhanced_message = enhanced_message[:157] + "..."

            processing_time = time.time() - start_time
            return DraftResult(
                success=True,
                message=enhanced_message,
                tokens_used=tokens_used,
                processing_time=processing_time
            )

        except openai.AuthenticationError as e:
            logging.error(f"OpenAI authentication error: {e}")
            processing_time = time.time() - start_time
            return DraftResult(
                success=False,
                message="",
                error=f"Authentication error: {str(e)}",
                processing_time=processing_time
            )
        except openai.RateLimitError as e:
            logging.warning(f"Rate limit exceeded, attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                # Wait before retrying (exponential backoff)
                time.sleep(2 ** attempt)
                continue
            else:
                processing_time = time.time() - start_time
                return DraftResult(
                    success=False,
                    message="",
                    error=f"Rate limit exceeded after {max_retries} attempts: {str(e)}",
                    processing_time=processing_time
                )
        except openai.APIConnectionError as e:
            logging.warning(f"API connection error, attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            else:
                processing_time = time.time() - start_time
                return DraftResult(
                    success=False,
                    message="",
                    error=f"Connection error after {max_retries} attempts: {str(e)}",
                    processing_time=processing_time
                )
        except openai.APIError as e:
            logging.error(f"OpenAI API error: {e}")
            processing_time = time.time() - start_time
            return DraftResult(
                success=False,
                message="",
                error=f"API error: {str(e)}",
                processing_time=processing_time
            )
        except Exception as e:
            logging.error(f"Unexpected error enhancing message with LLM: {e}")
            processing_time = time.time() - start_time
            return DraftResult(
                success=False,
                message="",
                error=f"Unexpected error: {str(e)}",
                processing_time=processing_time
            )

    # This shouldn't be reached due to the return statements, but just in case
    processing_time = time.time() - start_time
    return DraftResult(
        success=False,
        message="",
        error="Max retries exceeded",
        processing_time=processing_time
    )


def validate_message(message: str, channel: ChannelType) -> Dict[str, Any]:
    """
    Validate that a message meets the requirements for a specific channel
    """
    validation_result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "suggestions": []
    }

    if channel == ChannelType.SMS:
        if len(message) > 160:
            validation_result["warnings"].append("Message exceeds SMS single-part limit (160 chars)")
        if len(message) > 1530:  # SMS multipart limit
            validation_result["errors"].append("Message exceeds SMS multipart limit (1530 chars)")
        if not message.strip():
            validation_result["errors"].append("Message cannot be empty")
        if message.count('\n') > 3:
            validation_result["suggestions"].append("Consider reducing line breaks for SMS")

    elif channel == ChannelType.EMAIL:
        if not message.strip():
            validation_result["errors"].append("Message cannot be empty")
        # Could add more email-specific validations
        if len(message) < 10:
            validation_result["warnings"].append("Email message might be too short")

    elif channel in [ChannelType.RCS, ChannelType.IMESSAGE]:
        if not message.strip():
            validation_result["errors"].append("Message cannot be empty")
        # Could add more rich message validations
        if len(message) > 10000:  # Typical rich message limit
            validation_result["warnings"].append("Message might exceed rich message limits")

    validation_result["valid"] = len(validation_result["errors"]) == 0

    return validation_result


def sanitize_message(message: str) -> str:
    """
    Sanitize a message by removing potentially harmful content
    """
    # Remove potentially dangerous characters or patterns
    sanitized = message

    # Remove control characters except common ones
    sanitized = ''.join(char for char in sanitized if ord(char) >= 32 or char in '\n\r\t')

    # Remove potentially harmful patterns (basic XSS protection)
    harmful_patterns = [
        '<script', 'javascript:', 'vbscript:', 'onload=', 'onerror=',
        'onclick=', 'onmouseover=', 'onfocus='
    ]

    for pattern in harmful_patterns:
        if pattern.lower() in sanitized.lower():
            logging.warning(f"Potentially harmful pattern detected and removed: {pattern}")
            sanitized = sanitized.replace(pattern, '', 1)  # Just remove the first occurrence

    return sanitized


def get_message_characteristics(message: str) -> Dict[str, Any]:
    """
    Analyze message characteristics for optimization
    """
    return {
        'length': len(message),
        'word_count': len(message.split()),
        'line_count': len(message.split('\n')),
        'has_emojis': any(ord(c) > 127 for c in message),
        'has_urls': 'http://' in message.lower() or 'https://' in message.lower(),
        'has_phone_numbers': any(c.isdigit() for c in message) and len([c for c in message if c.isdigit()]) >= 10,
        'has_emails': '@' in message and '.' in message.split('@')[1] if '@' in message else False
    }


# Example usage
if __name__ == "__main__":
    # Example of drafting messages
    intent = "Your appointment is confirmed for tomorrow at 3pm."

    sms_result = draft_message(intent, ChannelType.SMS, {"relationship": "friend"})
    print(f"SMS: {sms_result.message}")
    print(f"Success: {sms_result.success}, Time: {sms_result.processing_time:.3f}s")

    email_result = draft_message(intent, ChannelType.EMAIL, {
        "name": "John Doe",
        "formal": True
    }, {
        "name": "Acme Clinic"
    })
    print(f"Email: {email_result.message}")
    print(f"Success: {email_result.success}, Time: {email_result.processing_time:.3f}s")

    rcs_result = draft_message(intent, ChannelType.RCS, {"relationship": "family"})
    print(f"RCS: {rcs_result.message}")
    print(f"Success: {rcs_result.success}, Time: {rcs_result.processing_time:.3f}s")

    # Example of validation
    validation = validate_message(email_result.message, ChannelType.EMAIL)
    print(f"Validation: {validation}")

    # Example of sanitization
    sanitized = sanitize_message("<script>alert('test')</script>Hello world!")
    print(f"Sanitized: {sanitized}")

    # Example of message characteristics
    characteristics = get_message_characteristics(email_result.message)
    print(f"Characteristics: {characteristics}")