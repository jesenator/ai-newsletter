#!/bin/bash
cd "$(dirname "$0")"

# Wait for internet connection
wait_for_internet() {
  until ping -c 1 -W 2 8.8.8.8 &>/dev/null; do
    sleep 5
  done
}

wait_for_internet
sleep 60
wait_for_internet

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  python3 -m venv venv
  source venv/bin/activate
  pip3 install -r requirements.txt
else
  source venv/bin/activate
fi

# Ensure deps are installed
pip3 install -q -r requirements.txt

caffeinate -i python3 generate.py --send-email

