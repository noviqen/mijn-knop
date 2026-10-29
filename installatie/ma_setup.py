"""Richt Music Assistant in voor Mijn knop. Wordt aangeroepen door installeer.sh.

python3 ma_setup.py [--speaker "Naam in Music Assistant" ...]
- wacht tot Music Assistant draait
- maakt (als er nog niemand is) een gebruiker 'mijnknop' + een blijvende sleutel (~/.config/mijn-knop/)
- toont alle gevonden speakers; met --speaker schrijft hij app/config.json
- kijkt of Spotify al gekoppeld is
Exitcode 0 = klaar, 2 = er is nog een handmatige stap (staat in de uitvoer).
"""
import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MA = os.environ.get("MA_URL", "http://127.0.0.1:8095")
CONF = Path.home() / ".config" / "mijn-knop"
TOKEN = CONF / "ma.token"
APP = Path(__file__).resolve().parent.parent / "app"


def post(pad, data, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    r = urllib.request.Request(MA + pad, data=json.dumps(data).encode(), headers=h)
    with urllib.request.urlopen(r, timeout=30) as res:
        t = res.read()
        return json.loads(t) if t else None


def cmd(token, command, **args):
    return post("/api", {"command": command, "args": args}, token)


def wacht():
    for _ in range(60):
        try:
            with urllib.request.urlopen(MA + "/info", timeout=5) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(3)
    sys.exit("Music Assistant start niet (geen antwoord op %s/info). Kijk: docker logs music-assistant" % MA)


def sleutel():
    if TOKEN.exists():
        t = TOKEN.read_text().strip()
        try:
            cmd(t, "players/all")
            return t
        except urllib.error.HTTPError:
            print("Bestaande sleutel werkt niet meer, ik maak een nieuwe.")
    CONF.mkdir(parents=True, exist_ok=True)
    os.chmod(CONF, 0o700)
    wachtwoord = secrets.token_urlsafe(18)
    try:
        r = post("/setup", {"username": "mijnknop", "password": wachtwoord})
    except urllib.error.HTTPError as e:
        print("\nMusic Assistant heeft al een eigenaar (%s)." % e.code)
        print("HANDMATIG: log in op %s, ga naar Instellingen > Profiel > Tokens, maak een token 'Mijn knop'" % MA)
        print("en zet die in %s (chmod 600). Draai daarna installeer.sh opnieuw." % TOKEN)
        sys.exit(2)
    kort = r["token"]
    lang = cmd(kort, "auth/token/create", name="Mijn knop")
    TOKEN.write_text(lang); os.chmod(TOKEN, 0o600)
    inlog = CONF / "music-assistant-inlog.txt"
    inlog.write_text(f"Music Assistant: {MA}\nGebruiker: mijnknop\nWachtwoord: {wachtwoord}\n"); os.chmod(inlog, 0o600)
    print(f"Gebruiker 'mijnknop' gemaakt. Inloggegevens: {inlog}")
    return lang


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speaker", action="append", default=[], help="naam of id van de speaker in Music Assistant (eerste = kinderkamer)")
    ap.add_argument("--poort", type=int, default=8857)
    a = ap.parse_args()
    info = wacht()
    print(f"Music Assistant {info.get('server_version')} draait op {MA}")
    t = sleutel()
    time.sleep(8)  # speakers worden even gezocht
    spelers = [p for p in cmd(t, "players/all") if p.get("available") and not p.get("hide_in_ui")]
    print("\nGevonden speakers:")
    for p in spelers:
        print(f"  - {(p.get('display_name') or p.get('name')).strip():30} ({p.get('provider')}, id {p.get('player_id')})")
    klaar = True
    if a.speaker:
        gekozen = []
        for i, naam in enumerate(a.speaker):
            hit = [p for p in spelers if p.get("player_id") == naam.strip()] or \
                  [p for p in spelers if (p.get("display_name") or p.get("name") or "").strip().lower() == naam.strip().lower()]
            if not hit:
                sys.exit(f"Speaker '{naam}' niet gevonden. Kies een naam of id uit de lijst hierboven.")
            if len(hit) > 1:
                sys.exit(f"Er zijn {len(hit)} speakers die '{naam}' heten. Gebruik het id uit de lijst hierboven, bijv. --speaker {hit[0]['player_id']}")
            gekozen.append({"id": hit[0]["player_id"], "naam": "Mijn kamer" if i == 0 else naam.strip()})
        cfg_pad = APP / "config.json"
        cfg = json.loads(cfg_pad.read_text()) if cfg_pad.exists() else json.loads((APP / "config.voorbeeld.json").read_text())
        cfg.update(speakers=gekozen, poort=a.poort, music_assistant=MA, ma_token_bestand=str(TOKEN))
        cfg_pad.write_text(json.dumps(cfg, indent=1, ensure_ascii=False))
        print(f"\nconfig.json geschreven met: {', '.join(g['naam'] for g in gekozen)}")
    else:
        print("\nHANDMATIG: draai opnieuw met --speaker \"<naam van de speaker in de kinderkamer>\"")
        klaar = False
    providers = cmd(t, "config/providers") or []
    if not any(p.get("domain") == "spotify" and p.get("enabled") for p in providers):
        print(f"\nHANDMATIG (eenmalig, door de eigenaar): open {info.get('base_url') or MA}, log in")
        print("  (gegevens in ~/.config/mijn-knop/music-assistant-inlog.txt), ga naar Instellingen > Muziekbronnen,")
        print("  voeg Spotify toe en log in met het Spotify Premium-account van het huis.")
        klaar = False
    else:
        print("\nSpotify is gekoppeld.")
    sys.exit(0 if klaar else 2)


if __name__ == "__main__":
    main()
