#!/bin/bash
cd "$(dirname "$0")"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Newsletter run.sh started"

# Wait for internet connection
wait_for_internet() {
  until ping -c 1 -W 2 8.8.8.8 &>/dev/null; do
    sleep 5
  done
}

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Waiting for internet..."
wait_for_internet
sleep 60
wait_for_internet
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Internet connected"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Creating venv..."
  python3 -m venv venv
  source venv/bin/activate
  pip3 install -r requirements.txt
else
  source venv/bin/activate
fi

# Ensure deps are installed
pip3 install -q -r requirements.txt

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting newsletter generation..."
caffeinate -i python3 main.py --send-email "$@"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Newsletter run.sh finished"

