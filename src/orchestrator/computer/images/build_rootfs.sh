#!/usr/bin/env bash
set -euo pipefail

MANIFEST="${1:-base}"
OUTPUT="${2:-data/computer-images/base.ext4}"
mkdir -p "$(dirname "$OUTPUT")"
python -m orchestrator.computer.images.builder --manifest "$MANIFEST" --output "$OUTPUT"
