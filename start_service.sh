#!/bin/bash

# Startup script for the LLM Messaging Service

echo "Starting LLM Messaging Service..."

# Create logs directory
mkdir -p logs

# Check if Redis is running
if ! pgrep redis-server > /dev/null; then
    echo "Starting Redis server..."
    redis-server --daemonize yes
    sleep 2
fi

# Check if required Python packages are installed
if ! python -c "import fastapi, redis, openai, yaml, dotenv" &> /dev/null; then
    echo "Installing required packages..."
    pip install -r requirements.txt
fi

echo "Starting the messaging service..."
cd server
PYTHONPATH=. uvicorn integrated_main:app --host 0.0.0.0 --port 8000 --log-config logging_config.py

echo "Service stopped."