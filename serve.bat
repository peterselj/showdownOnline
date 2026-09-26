@echo off
rem Double-click to run the app locally at http://localhost:8000
rem (a double-clicked index.html can't build cards - the card server
rem only accepts the live site and localhost). Close this window to stop.
cd /d "%~dp0"
start "" http://localhost:8000/
python -m http.server 8000
