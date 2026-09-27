#!/usr/bin/env bash
# Neural TTS greeting with Piper
set -euo pipefail
VOICES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/voices"

python3 -m piper \
  --model en_US-lessac-medium \
  --data-dir "$VOICES_DIR" \
  --output-raw \
  -- "Hello Tony, welcome back!" \
| aplay -r 22050 -f S16_LE -t raw -
