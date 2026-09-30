#!/bin/bash
# OFS — publish the built frontend to a folder Apache can actually read.
#
#   bash deploy/publish.sh
#
# Run from the project root (the folder containing backend/ and frontend/).
# Re-run it after every `npm run build`.
#
# ---------------------------------------------------------------------
# WHY THIS SCRIPT EXISTS
# ---------------------------------------------------------------------
# Apache runs as the user `_www`, not as you. To serve a file it must be
# able to traverse EVERY folder above it. On macOS:
#
#   /Users/<you>            drwx------   owner only  -> _www blocked here
#   /Users/<you>/Desktop    additionally protected by TCC (privacy layer)
#
# So a DocumentRoot inside ~/Desktop or ~/Documents gives a 403 Forbidden
# no matter how correct the Apache config is. `apachectl configtest` still
# says "Syntax OK", because the syntax IS fine — the failure only happens
# when a request arrives and Apache tries to read the path.
#
# The wrong fix is `chmod 755 ~` : it exposes your entire home folder to
# every account on the machine, and TCC blocks Desktop regardless.
#
# The right fix is to keep the source in your project (where git and your
# editor want it) and publish a COPY into Apache's own document area,
# which is world-readable by design. That is also how a real deployment
# works: you build an artifact, then you deploy the artifact.
# ---------------------------------------------------------------------

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
