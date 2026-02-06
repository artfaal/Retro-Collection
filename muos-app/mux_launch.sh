#!/bin/sh
# HELP: Publish Collection
# ICON: app

. /opt/muos/script/var/func.sh

echo app >/tmp/act_go

APP_DIR="/mnt/sdcard/MUOS/application/RetroCollection"
LOG_FILE="$APP_DIR/last_run.log"

cd "$APP_DIR"
python3 publish_collection.py > "$LOG_FILE" 2>&1

sleep 3
