#!/bin/bash
# Copies the built frontend to a folder Apache can read. Run from the project root: bash deploy/publish.sh
# Apache runs as _www and cannot read inside ~/Desktop, so the build is copied to Apache's own document folder.
# Re-run it after every npm run build.

set -e

SRC="$(pwd)/frontend/dist"
DEST="/Library/WebServer/Documents/ofs"

if [ ! -f "$SRC/index.html" ]; then
  echo "ERROR: $SRC/index.html not found."
  echo "Build first:  cd frontend && VITE_API_BASE= npm run build"
  exit 1
fi

echo "Publishing  $SRC"
echo "        ->  $DEST"

sudo mkdir -p "$DEST"
sudo rsync -a --delete "$SRC"/ "$DEST"/

# Readable by _www, writable only by root.
sudo chown -R root:wheel "$DEST"
sudo chmod -R a+rX "$DEST"

echo
echo "Published. Contents:"
ls -la "$DEST"
echo
echo "Next:  sudo apachectl restart   then open http://localhost:8080"
