#!/bin/sh
# HELP: Publish Collection
# ICON: app

. /opt/muos/script/var/func.sh

echo app >/tmp/act_go

APP_DIR="/mnt/sdcard/MUOS/application/RetroCollection"

/opt/muos/frontend/muterm -s 20 -bg 1a1a2e -fg e0e0e0 "$APP_DIR/run.sh"
