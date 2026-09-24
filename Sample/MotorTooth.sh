#!/bin/bash
MotorTooth_stamp="MotorTooth.sh: 2026-09-24 - 1234"
if [ "${dbgclaude^^}" = "Y" ]; then echo "$MotorTooth_stamp"; fi

# Run from this script's folder so relative paths in the .s2gcfg work.
cd "$(dirname "$0")"

python3 ../s2g_app.py MotorTooth.s2gcfg
