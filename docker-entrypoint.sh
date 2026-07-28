#!/bin/sh
set -eu

mkdir -p /app/data /app/logs /vault

calendar_path="${INFOCOLLECTOR_CALENDAR_PATH:-/app/data/economic-calendar.json}"
if [ ! -f "$calendar_path" ]; then
  cp /app/ui/economic-calendar.json "$calendar_path"
fi

exec "$@"
