#!/usr/bin/env bash
# Mijn knop installeren (zelfstandige versie: Music Assistant + elk thuissysteem, bijv. Homey).
# Gebruik:  ./installeer.sh --speaker "Naam van de speaker in de kinderkamer" [--speaker "Tweede speaker"]
# Zonder --speaker toont hij eerst welke speakers er zijn.
set -euo pipefail
cd "$(dirname "$0")"
HIER="$(pwd)"
stap() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

stap "1. Controle"
python3 controle.py || true

stap "2. Python-omgeving"
rm -rf .venv
if python3 -m venv .venv >/dev/null 2>&1; then
  .venv/bin/pip install -q --upgrade pip aiohttp
elif command -v uv >/dev/null 2>&1 || [ -x "$HOME/.local/bin/uv" ]; then
  UV=$(command -v uv || echo "$HOME/.local/bin/uv"); rm -rf .venv
  "$UV" venv -q --python "$(command -v python3)" .venv && "$UV" pip install -q --python .venv/bin/python aiohttp
elif sudo -n true 2>/dev/null; then
  PV=$(python3 -c "import sys;print(f'{sys.version_info[0]}.{sys.version_info[1]}')")
  echo "python3-venv ontbreekt, ik installeer python$PV-venv"
  sudo -n apt-get install -y -q "python$PV-venv" >/dev/null && rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip aiohttp
else
  echo "FOUT: kan geen Python-omgeving maken. Installeer python3-venv:  sudo apt install python3-venv"; exit 1
fi
.venv/bin/python -c "import aiohttp" && echo "aiohttp staat klaar in .venv"

stap "3. Music Assistant"
if curl -fsS http://127.0.0.1:8095/info >/dev/null 2>&1; then
  echo "Music Assistant draait al, die gebruik ik."
else
  if docker info >/dev/null 2>&1; then D=docker; elif sudo -n docker info >/dev/null 2>&1; then D="sudo -n docker"; else
    echo "FOUT: Docker niet beschikbaar (of geen rechten). Installeer Docker of voeg je gebruiker toe aan de groep docker."; exit 1; fi
  export MA_DATA="$HOME/.local/share/mijn-knop/music-assistant"; mkdir -p "$MA_DATA"
  $D compose -f installatie/docker-compose.yml up -d
  echo "Music Assistant gestart (http://127.0.0.1:8095)"
fi

stap "4. Music Assistant inrichten"
set +e; python3 installatie/ma_setup.py "$@"; RC=$?; set -e
[ $RC -eq 1 ] && exit 1

if [ ! -f app/config.json ]; then
  echo; echo "Kies hierboven de speaker van de kinderkamer en draai opnieuw met --speaker \"<naam>\"."; exit 2
fi
POORT=$(python3 -c "import json;print(json.load(open('app/config.json'))['poort'])")

stap "5. Mijn knop als dienst"
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/mijn-knop.service <<UNIT
[Unit]
Description=Mijn knop (iPad-app voor de knop aan de muur, alleen thuisnetwerk)
After=network-online.target

[Service]
ExecStart=$HIER/.venv/bin/python $HIER/app/server_ma.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now mijn-knop.service
systemctl --user restart mijn-knop.service
sleep 2
IP=$(python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('1.1.1.1',80));print(s.getsockname()[0])")
if curl -fsS "http://127.0.0.1:$POORT/api/plekken" >/dev/null; then echo "Mijn knop draait."; else
  echo "FOUT: Mijn knop reageert niet. Kijk: journalctl --user -u mijn-knop -n 50"; exit 1; fi
sed "s#http://SERVER-IP:8857#http://$IP:$POORT#" homey/knop.js > homey/knop-ingevuld.js

stap "Klaar"
echo "iPad-app:   http://$IP:$POORT   (Safari > Delen > Zet op beginscherm)"
echo "Homey:      zet homey/knop-ingevuld.js in HomeyScript en maak de Flows (zie OVERDRACHT.md, stap Homey)."
[ $RC -eq 2 ] && echo "LET OP: er staat hierboven nog een HANDMATIGE stap (meestal: Spotify koppelen in Music Assistant)."
exit $RC
