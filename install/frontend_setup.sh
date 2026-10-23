#!/bin/sh

cd frontend
./build.sh
cd ..
# Replace the served build in place: copying build/ onto an existing static/ nested
# it as static/build and kept serving the old files. rootCA.pem stays.
mkdir -p ./backend/api/static
rm -rf ./backend/api/static/assets
cp -R ./frontend/build/. ./backend/api/static/
cp ./backend/mkcert/certs/rootCA.pem ./backend/api/static
