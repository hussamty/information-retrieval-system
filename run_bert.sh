#!/bin/bash

echo "Starting Embedding BERT process in the background..."

# Activiting Virtual Environment
VENV_PATH="venv"
if [ -d "$VENV_PATH" ] && [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment: $VENV_PATH"
    source "$VENV_PATH/bin/activate"
fi

# Kill process that use these TCP ports without showing any standard output or errors.
echo "Attempting to stop any service on port 8007..."
fuser -k 8007/tcp > /dev/null 2>&1
sleep 2

# Run Services

echo "Starting BERT API (port 8007)... Log: bert.log"
python -m uvicorn api.bert_representation_api:app --host 0.0.0.0 --port 8007 > bert.log 2>&1 &
BERT_PID=$!


sleep 3
echo ""
echo "BERT service started."
echo "PIDs: BERT_Process=$BERT_PID"
echo "To monitor logs: tail -f bert.log"
echo "To stop service: kill $BERT_PID"
echo ""

