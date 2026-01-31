# LLM-Powered Free SMS/RCS/Email Service

This project implements a messaging service that leverages device-backed gateways to send SMS, RCS, and email messages without per-message costs. The system uses an LLM to draft messages and intelligently routes them through the most appropriate free channel.

## Architecture

The system consists of several key components:

1. **LLM Service**: Drafts messages based on user intent
2. **Message Orchestrator**: Routes messages to appropriate channels
3. **Device Gateways**: Android app for SMS/RCS, BlueBubbles for iMessage
4. **SMTP Client**: For email delivery
5. **State Machine**: Manages message lifecycle and retries
6. **Redis Workers**: Async processing queues

## Components

### Server Components
- `main.py` / `integrated_main.py`: FastAPI server with WebSocket gateway
- `models/routing_state_machine.py`: Message state management
- `workers/redis_workers.py`: Async message processing
- `channels/adapters.py`: Channel-specific sending logic
- `llm.py`: Message drafting with LLM enhancement
- `utils/contact_manager.py`: Contact and preference management

### Key Features

- **Multi-channel delivery**: SMS, RCS, Email, iMessage
- **Intelligent routing**: Chooses optimal delivery method
- **Fallback mechanisms**: Automatic fallback to alternative channels
- **LLM-powered drafting**: Generates appropriate messages for each channel
- **Safety controls**: Rate limiting, opt-in verification
- **Delivery confirmation**: Tracks message status

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up Redis server:
```bash
# Install and start Redis
sudo apt-get install redis-server
sudo systemctl start redis
```

3. Configure environment variables:
```bash
export REDIS_HOST=localhost
export REDIS_PORT=6379
export OPENAI_API_KEY=your_openai_api_key
```

4. For email functionality, configure SMTP settings in `channels/adapters.py`

5. For Android gateway, deploy the companion app (not included in this repo)

## Usage

### Starting the Server

```bash
cd server
uvicorn integrated_main:app --host 0.0.0.0 --port 8000
```

### Sending a Message

```bash
curl -X POST http://localhost:8000/send \
  -H "Content-Type: application/json" \
  -d '{
    "to": "+1234567890",
    "channel": "sms",
    "text": "Hello from the LLM messaging service!",
    "use_llm_enhancement": true
  }'
```

### Drafting a Message

```bash
curl -X POST http://localhost:8000/draft \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "Remind John about his appointment tomorrow at 3pm",
    "channel": "sms"
  }'
```

### Adding a Contact

```bash
curl -X POST http://localhost:8000/contacts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "phone": "+1234567890",
    "email": "john@example.com",
    "imessage_capable": true,
    "rcs_capable": true,
    "preferred_channel": "rcs"
  }'
```

## Android Gateway App

The Android component is not included in this repository but would include:

- WebSocket client to connect to the server
- AccessibilityService to send messages via Google Messages
- NotificationListenerService to receive delivery receipts
- Proper permissions in AndroidManifest.xml

## Security Considerations

- Rate limiting per recipient
- Opt-in verification
- Message logging and audit trails
- Secure WebSocket connections
- Environment-based credential storage

## Limitations

- Requires physical devices for SMS/RCS (not scalable like Twilio)
- Dependent on carrier policies for SMS
- Requires proper setup of email SMTP
- Android accessibility permissions required

## Extending

The system is designed to be extensible:

- Add new channel adapters in `channels/adapters.py`
- Modify routing logic in `models/routing_state_machine.py`
- Enhance LLM prompts in `llm.py`
- Add new contact properties in `utils/contact_manager.py`

## License

MIT