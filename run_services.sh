#!/bin/bash

echo "Starting all services in the background..."

# Activiting Virtual Environment
VENV_PATH="venv"
if [ -d "$VENV_PATH" ] && [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment: $VENV_PATH"
    source "$VENV_PATH/bin/activate"
fi

# Kill process that use these TCP ports without showing any standard output or errors.
echo "Attempting to stop any services on ports 8001, 8002, 8003..."
fuser -k 8001/tcp > /dev/null 2>&1
fuser -k 8002/tcp > /dev/null 2>&1
fuser -k 8003/tcp > /dev/null 2>&1
sleep 2

# Run Services

echo "Starting Data Loader API (port 8001)... Log: data_loader.log"
python -m uvicorn api.data_loader_api:app --host 0.0.0.0 --port 8001 > data_loader.log 2>&1 &
DATA_LOADER_PID=$!

echo "Starting Representation API (port 8002)... Log: representation.log"
python -m uvicorn api.representation_api:app --host 0.0.0.0 --port 8002 > representation.log 2>&1 &
REPRESENTATION_PID=$!

echo "Starting Search API (port 8003)... Log: search.log"
python -m uvicorn api.search_api:app --host 0.0.0.0 --port 8003 > search.log 2>&1 &
SEARCH_PID=$!

sleep 3
echo ""
echo "All services started."
echo "PIDs: Data_Loader=$DATA_LOADER_PID, Representation=$REPRESENTATION_PID, Search=$SEARCH_PID"
echo "To monitor logs: tail -f *.log"
echo "To stop all services: kill $DATA_LOADER_PID $REPRESENTATION_PID $SEARCH_PID"
echo ""

