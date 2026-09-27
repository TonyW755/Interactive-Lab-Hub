#!/usr/bin/env bash

set -euo pipefail

VOICES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/voices"

# Ask for the phone number using neural TTS
python3 -m piper \
  --model en_US-lessac-medium \
  --data-dir "$VOICES_DIR" \
  --output-raw \
  -- "Please say your phone number, one digit at a time." \
| aplay -r 22050 -f S16_LE -t raw -

# Record the response
arecord -d 8 -f S16_LE -c 1 -r 16000 phone_response.wav

# Confirm recording
python3 -m piper \
  --model en_US-lessac-medium \
  --data-dir "$VOICES_DIR" \
  --output-raw \
  -- "Thank you. I recorded your phone number." \
| aplay -r 22050 -f S16_LE -t raw -

# Transcribe the response
python transcribe.py phone_response.wav --model tiny.en
