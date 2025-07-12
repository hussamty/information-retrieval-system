#!/bin/bash

echo "Starting BM25 process in the background..."

# Activiting Virtual Environment
VENV_PATH="venv"
if [ -d "$VENV_PATH" ] && [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment: $VENV_PATH"
    source "$VENV_PATH/bin/activate"
fi

# Kill process that use these TCP ports without showing any standard output or errors.
echo "Attempting to stop any service on port 8006..."
fuser -k 8006/tcp > /dev/null 2>&1
sleep 2

# Run Services

echo "Starting BM25 API (port 8006)... Log: bm25.log"
python -m uvicorn api.bm25_representation_api:app --host 0.0.0.0 --port 8006 > bm25.log 2>&1 &
BM25_PID=$!


sleep 3
echo ""
echo "BM25 service started."
echo "PIDs: BM25_Process=$BM25_PID"
echo "To monitor logs: tail -f bm25.log"
echo "To stop service: kill $BM25_PID"
echo ""

