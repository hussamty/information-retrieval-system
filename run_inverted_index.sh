#!/bin/bash

echo "Starting Index process in the background..."

# Activiting Virtual Environment
VENV_PATH="venv"
if [ -d "$VENV_PATH" ] && [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment: $VENV_PATH"
    source "$VENV_PATH/bin/activate"
fi

# Kill process that use these TCP ports without showing any standard output or errors.
echo "Attempting to stop any service on port 8008..."
fuser -k 8008/tcp > /dev/null 2>&1
sleep 2

# Run Services

echo "Starting Index API (port 8008)... Log: index.log"
python -m uvicorn api.inverted_index_representation_api:app --host 0.0.0.0 --port 8008 > index.log 2>&1 &
INDEX_PID=$!


sleep 3
echo ""
echo "Indexing service started."
echo "PIDs: Index_Process=$INDEX_PID"
echo "To monitor logs: tail -f index.log"
echo "To stop service: kill $INDEX_PID"
echo ""

