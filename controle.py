"""Stap 0: kan Mijn knop op deze server draaien? Draai: python3 controle.py

Kijkt alleen, verandert niets. Elke regel is OK, LET OP of FOUT, met wat je eraan doet.
"""
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import urllib.request

uitslag = []


def meld(status, wat, uitleg=""):
    uitslag.append(status)
    print(f"[{status:6}] {wat}" + (f"\n         -> {uitleg}" if uitleg else ""))


def run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None


# 1. Python
if sys.version_info >= (3, 10):
    meld("OK", f"Python {sys.version.split()[0]}")
else:
    meld("FOUT", f"Python {sys.version.split()[0]} is te oud", "Python 3.10 of nieuwer nodig.")

# 2. Pakketten
for mod, pip in (("aiohttp", "aiohttp"), ("soco", "soco")):
    if importlib.util.find_spec(mod):
        meld("OK", f"Python-pakket {mod}")
    else:
        meld("LET OP", f"Python-pakket {mod} ontbreekt", f"Installeer in een venv: python3 -m venv .venv && .venv/bin/pip install {pip}")

# 3. git
meld("OK", "git") if shutil.which("git") else meld("FOUT", "git ontbreekt", "Installeer git.")

# 4. Thuisnetwerk
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("1.1.1.1", 80)); ip = s.getsockname()[0]; s.close()
    prive = ip.startswith(("192.168.", "10.")) or (ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31)
    if prive:
        meld("OK", f"Server-adres in het thuisnetwerk: {ip}")
    else:
        meld("FOUT", f"Server-adres {ip} lijkt niet in een thuisnetwerk te zitten",
             "De server moet in hetzelfde netwerk staan als de Sonos en de iPad (geen cloudserver).")
except OSError:
    meld("FOUT", "Geen netwerk gevonden")

# 5. Internet (voor titels en hoesjes van Spotify)
try:
    urllib.request.urlopen("https://open.spotify.com/oembed?url=https://open.spotify.com/track/2374M0fQpWi3dLnB54qaLX", timeout=8)
    meld("OK", "Spotify-titels en -hoesjes ophalen werkt")
except Exception as e:
    meld("FOUT", "Spotify oEmbed niet bereikbaar", f"Internet nodig op de server ({e.__class__.__name__}).")

# 6. Sonos
if importlib.util.find_spec("soco"):
    import soco
    try:
        gevonden = soco.discover(timeout=6) or set()
    except Exception:
        gevonden = set()
    if gevonden:
        namen = ", ".join(sorted(z.player_name for z in gevonden))
        meld("OK", f"Sonos gevonden: {namen}")
    else:
        meld("FOUT", "Geen Sonos gevonden",
             "Staat de server in hetzelfde netwerk? Draait hij in Docker of een VM, dan werkt zoeken soms niet: "
             "probeer soco.SoCo('<ip-van-speaker>') met het IP uit de Sonos-app (Instellingen > Systeem > Over mijn systeem).")
else:
    meld("LET OP", "Sonos niet gecontroleerd", "Installeer eerst soco (zie hierboven) en draai dit opnieuw.")

# 7. Altijd aan (systemd --user + linger)
r = run("systemctl", "--user", "is-system-running")
if r is not None and r.stdout.strip() in ("running", "degraded"):
    meld("OK", "systemd --user beschikbaar (app kan als dienst draaien)")
else:
    meld("LET OP", "systemd --user niet beschikbaar", "Dan op een andere manier altijd laten draaien (bijv. een systeemdienst).")
r = run("loginctl", "show-user", os.environ.get("USER", ""), "--property=Linger")
if r is not None and "Linger=yes" in r.stdout:
    meld("OK", "Dienst blijft draaien als je uitlogt (linger aan)")
else:
    meld("LET OP", "Linger staat uit", "Zet aan met: sudo loginctl enable-linger $USER  (anders stopt de app als je uitlogt).")

# 8. Poort vrij
with socket.socket() as s:
    vrij = s.connect_ex(("127.0.0.1", 8857)) != 0
meld("OK", "Poort 8857 is vrij") if vrij else meld("LET OP", "Poort 8857 is al in gebruik", "Kies een andere poort tussen 8700 en 8899.")

print()
if "FOUT" in uitslag:
    print("UITSLAG: nog niet klaar. Los eerst de FOUT-regels op.")
elif "LET OP" in uitslag:
    print("UITSLAG: bijna klaar. Kijk naar de LET OP-regels.")
else:
    print("UITSLAG: alles klaar om te bouwen.")
print("Daarna nog met de eigenaar nagaan: Homey met HomeyScript-app, en Spotify gekoppeld in de Sonos-app.")
