"""Stap 0: kan Mijn knop (zelfstandige versie) op deze server draaien? Draai: python3 controle.py

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
for mod, pip in (("aiohttp", "aiohttp"),):
    if importlib.util.find_spec(mod):
        meld("OK", f"Python-pakket {mod}")
    else:
        meld("LET OP", f"Python-pakket {mod} ontbreekt", "Geen probleem: installeer.sh zet het in een eigen .venv.")

# 2b. Eigen Python-omgeving kunnen maken
if importlib.util.find_spec("ensurepip") or shutil.which("uv") or os.path.exists(os.path.expanduser("~/.local/bin/uv")):
    meld("OK", "Eigen Python-omgeving (venv) maken kan")
else:
    meld("LET OP", "python3-venv ontbreekt", "installeer.sh probeert het zelf (met sudo), anders: sudo apt install python3-venv")

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
             "De server moet in hetzelfde netwerk staan als de speakers en de iPad (geen cloudserver).")
except OSError:
    meld("FOUT", "Geen netwerk gevonden")

# 5. Internet (voor titels en hoesjes van Spotify)
try:
    urllib.request.urlopen("https://open.spotify.com/oembed?url=https://open.spotify.com/track/2374M0fQpWi3dLnB54qaLX", timeout=8)
    meld("OK", "Spotify-titels en -hoesjes ophalen werkt")
except Exception as e:
    meld("FOUT", "Spotify oEmbed niet bereikbaar", f"Internet nodig op de server ({e.__class__.__name__}).")

# 6. Music Assistant of Docker (voor het afspelen op Google Cast, Sonos, AirPlay, ...)
try:
    urllib.request.urlopen("http://127.0.0.1:8095/info", timeout=4)
    meld("OK", "Music Assistant draait al op deze server")
except Exception:
    r = run("docker", "info")
    r2 = run("sudo", "-n", "docker", "info") if not (r and r.returncode == 0) else r
    if r and r.returncode == 0:
        meld("OK", "Docker werkt (installeer.sh zet Music Assistant neer)")
    elif r2 and r2.returncode == 0:
        meld("OK", "Docker werkt via sudo (installeer.sh zet Music Assistant neer)")
    else:
        meld("FOUT", "Geen Docker en geen Music Assistant",
             "Installeer Docker (https://docs.docker.com/engine/install/) of zet je gebruiker in de groep docker.")

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
print("Daarna nog nodig: Spotify Premium (koppelen in Music Assistant), en op Homey de app HomeyScript.")
