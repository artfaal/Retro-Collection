#!/bin/sh

APP_DIR="/mnt/sdcard/MUOS/application/RetroCollection"

echo ""
echo "================================"
echo "  Retro Collection Publisher"
echo "================================"
echo ""

cd "$APP_DIR"
python3 publish_collection.py

echo ""
echo "Press any button..."
sleep 3
