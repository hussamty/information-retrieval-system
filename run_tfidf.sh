#!/bin/bash

echo "Starting TFIDF process in the background..."

# Activiting Virtual Environment
VENV_PATH="venv"
if [ -d "$VENV_PATH" ] && [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment: $VENV_PATH"
    source "$VENV_PATH/bin/activate"
fi

# Kill process that use these TCP ports without showing any standard output or errors.
echo "Attempting to stop any service on port 8005..."
fuser -k 8005/tcp > /dev/null 2>&1
sleep 2

# Run Services

echo "Starting TFIDF API (port 8005)... Log: tfidf.log"
python -m uvicorn api.tfidf_representation_api:app --host 0.0.0.0 --port 8005 > tfidf.log 2>&1 &
TFIDF_PID=$!


sleep 3
echo ""
echo "TFIDF service started."
echo "PIDs: TFIDF_Process=$TFIDF_PID"
echo "To monitor logs: tail -f tfidf.log"
echo "To stop service: kill $TFIDF_PID"
echo ""

