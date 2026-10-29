"""Mijn knop, zelfstandige versie: werkt met elk thuissysteem (Homey, of iets anders).

- Alle instellingen staan in deze server (data/staat.json): dit is het ene systeem.
- Afspelen gaat via Music Assistant (Google Cast, Sonos, AirPlay, ...), met Spotify als bron.
- De knop aan de muur stuurt zijn drukken hierheen: POST /api/druk/<1-8> en /api/draai/<op|neer>
  (bij Homey: Flow -> HomeyScript, zie homey/knop.js).
- De iPad-app (index.html) praat met dezelfde API als de Home Assistant-versie.

Instellingen voor de ouder: config.json (rusttijd, speakers, volume). Het kind kan die niet wijzigen.
Draaien: .venv/bin/python app/server_ma.py   (dienst: mijn-knop.service, gemaakt door installeer.sh)
"""
import asyncio
import ipaddress
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import web

HIER = Path(__file__).parent
CONFIG = json.loads((HIER / "config.json").read_text())
DATA = HIER / "data"
STAAT = DATA / "staat.json"
HOESJES = DATA / "hoesjes.json"
EERDER = DATA / "eerder.json"
EERDER_MAX = 48

MA = CONFIG.get("music_assistant", "http://127.0.0.1:8095").rstrip("/")
MA_TOKEN = Path(os.path.expanduser(CONFIG.get("ma_token_bestand", "~/.config/mijn-knop/ma.token"))).read_text().strip()
POORT = int(CONFIG.get("poort", 8857))
THUIS = [ipaddress.ip_network(n) for n in CONFIG.get("thuisnetwerk", ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"])]
TZ = ZoneInfo(CONFIG.get("tijdzone", "Europe/Amsterdam"))
SPEAKERS = {s["id"]: s["naam"] for s in CONFIG.get("speakers", [])}
MAX_VOLUME = int(CONFIG.get("max_volume", 60))
WEKKER_VOLUME = int(CONFIG.get("wekker_volume", 22))
STAP = int(CONFIG.get("volume_stap", 3))
RUST = {"vanaf": "21:00", "tot": "07:00", "vanaf_weekend": "22:00", "tot_weekend": "09:00", **CONFIG.get("rust", {})}

PLEKKEN = range(1, 9)
WEKKERS = range(1, 5)
DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
VROEGST, LAATST = "05:00", "21:00"   # wekkers niet later dan de vroegste rusttijd
SOORTEN = "track|episode|album|playlist|show"
URI = re.compile(rf"(?:spotify:|open\.spotify\.com/(?:intl-[a-z-]+/)?)({SOORTEN})[/:]([A-Za-z0-9]{{22}})")
MA_SOORT = {"track": "track", "album": "album", "playlist": "playlist", "show": "podcast", "episode": "podcast_episode"}
NAAM_MAX = 40


# ---------- opslag ----------
def lees(pad, leeg):
    try:
        return json.loads(pad.read_text())
    except (OSError, ValueError):
        return leeg


def schrijf(pad, data):
    pad.parent.mkdir(exist_ok=True)
    tmp = pad.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    tmp.replace(pad)


def leeg_lied():
    return {"spotify": "", "naam": "", "soort": "", "hoesje": ""}


def staat():
    s = lees(STAAT, {})
    s.setdefault("plekken", {str(n): leeg_lied() for n in PLEKKEN})
    s.setdefault("wekkers", [{"tijd": t, "aan": False, "dagen": list(DAGEN), **leeg_lied()}
                             for t in ("07:15", "20:00", "19:00", "08:00")])
    s.setdefault("laatste", 0)
    s.setdefault("speaker", next(iter(SPEAKERS), ""))
    s.setdefault("gedaan", {})
    if s["speaker"] not in SPEAKERS and SPEAKERS:
        s["speaker"] = next(iter(SPEAKERS))
    return s


def bewaar(s):
    schrijf(STAAT, s)


def onthoud(item):
    lijst = [x for x in lees(EERDER, []) if x.get("spotify") != item["spotify"]]
    schrijf(EERDER, ([item] + lijst)[:EERDER_MAX])


def bewaar_hoesje(sleutel, url):
    if url and url.startswith("https://"):
        h = lees(HOESJES, {})
        if h.get(sleutel) != url:
            h[sleutel] = url
            schrijf(HOESJES, h)


def ontleed(tekst):
    m = URI.search(tekst or "")
    return (m.group(1), m.group(2)) if m else None


def schoon(naam):
    naam = re.sub(r"\s+", " ", str(naam or "")).strip()
    return naam if len(naam) <= NAAM_MAX else naam[:NAAM_MAX - 1].rstrip() + "…"


def goede_tijd(t):
    t = str(t)
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t) or not (VROEGST <= t <= LAATST):
        raise web.HTTPBadRequest(text=f"Kies een tijd tussen {VROEGST} en {LAATST}.")
    return t


def rusttijd(nu=None):
    """(rust?, tot) - doordeweeks vanaf-tot, weekend (vr/za-avond, za/zo-ochtend) _weekend."""
    nu = nu or datetime.now(TZ)
    t = nu.strftime("%H:%M")
    vanaf = RUST["vanaf_weekend"] if nu.weekday() in (4, 5) else RUST["vanaf"]
    tot = RUST["tot_weekend"] if nu.weekday() in (5, 6) else RUST["tot"]
    ochtend = nu if nu.hour < 12 else nu + timedelta(days=1)
    tot_tekst = RUST["tot_weekend"] if ochtend.weekday() >= 5 else RUST["tot"]
    return (t >= vanaf or t < tot), tot_tekst


# ---------- Music Assistant ----------
class MAFout(Exception):
    pass


async def ma(session, command, **args):
    try:
        async with session.post(MA + "/api", json={"command": command, "args": args},
                                headers={"Authorization": f"Bearer {MA_TOKEN}"},
                                timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status >= 400:
                raise MAFout(f"{command}: {r.status} {(await r.text())[:200]}")
            tekst = await r.text()
            return json.loads(tekst) if tekst else None
    except aiohttp.ClientError as e:
        raise MAFout(f"{command}: {e}") from e


async def speler(session, sp):
    return await ma(session, "players/get", player_id=sp) or {}


async def speel_lied(session, sp, lied, volume=None):
    """Vervang de wachtrij door dit ene lied/album; niets herhalen, niets doorspelen."""
    soort, sid = lied["spotify"].split(":")[1:]
    try:
        await ma(session, "players/cmd/ungroup", player_id=sp)
    except MAFout:
        pass
    for cmd, arg in (("player_queues/repeat", {"repeat_mode": "off"}),
                     ("player_queues/shuffle", {"shuffle_enabled": False}),
                     ("player_queues/autoplay", {"autoplay_enabled": False})):
        try:
            await ma(session, cmd, queue_id=sp, **arg)
        except MAFout:
            pass
    if volume is not None:
        try:
            await ma(session, "players/cmd/volume_mute", player_id=sp, muted=False)
        except MAFout:
            pass
        await ma(session, "players/cmd/volume_set", player_id=sp, volume_level=volume)
    await ma(session, "player_queues/play_media", queue_id=sp,
             media=[f"spotify://{MA_SOORT[soort]}/{sid}"], option="replace")


def speelt_dit(p, lied):
    """Speelt de speaker nu (een deel van) dit lied?"""
    uri = ((p.get("current_media") or {}).get("uri") or "")
    soort, sid = lied["spotify"].split(":")[1:]
    return soort not in ("track", "episode") or sid in uri


# ---------- middleware ----------
@web.middleware
async def alleen_thuis(request, handler):
    ip = ipaddress.ip_address(request.remote or "0.0.0.0")
    if not ip.is_loopback and not any(ip in n for n in THUIS):
        return web.Response(status=403, text="Alleen thuis op de wifi.")
    try:
        return await handler(request)
    except MAFout as e:
        request.app.logger.warning("Music Assistant: %s", e)
        return web.Response(status=502, text="Music Assistant reageert niet goed. Is Spotify gekoppeld?")


# ---------- API voor de iPad ----------
async def oembed(session, soort, sid):
    url = f"https://open.spotify.com/oembed?url={quote(f'https://open.spotify.com/{soort}/{sid}', safe='')}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status == 200:
                j = await r.json(content_type=None)
                return j.get("title") or "", j.get("thumbnail_url") or ""
    except (aiohttp.ClientError, TimeoutError, ValueError):
        pass
    return "", ""


async def plekken(request):
    s = staat()
    uit = []
    for n in PLEKKEN:
        l = s["plekken"][str(n)]
        uit.append({"nummer": n, "vol": bool(l["spotify"]), "naam": l["naam"], "spotify": l["spotify"],
                    "soort": l["soort"], "hoesje": l["hoesje"]})
    nu = {"staat": "", "titel": "", "artiest": "", "plek": s["laatste"]}
    if s["speaker"]:
        try:
            p = await speler(request.app["http"], s["speaker"])
            m = p.get("current_media") or {}
            nu.update(staat=p.get("playback_state") or p.get("state") or "", titel=m.get("title") or "", artiest=m.get("artist") or "")
        except MAFout:
            pass
    rust, tot = rusttijd()
    return web.json_response({"plekken": uit, "speaker": s["speaker"], "rust": rust, "rust_tot": tot,
                              "speakers": [{"id": k, "naam": v} for k, v in SPEAKERS.items()], "nu": nu})


def plek_nummer(request):
    try:
        n = int(request.match_info["n"])
    except ValueError:
        raise web.HTTPNotFound()
    if n not in PLEKKEN:
        raise web.HTTPNotFound()
    return n


async def lied_uit(request, body):
    p = ontleed(body.get("spotify", ""))
    if not p:
        raise web.HTTPBadRequest(text="Dat is geen Spotify-liedje.")
    naam, hoesje = schoon(body.get("naam")), str(body.get("hoesje") or "")
    if not naam or not hoesje.startswith("https://"):
        t, h = await oembed(request.app["http"], *p)
        naam = naam or schoon(t) or "Liedje"
        hoesje = hoesje if hoesje.startswith("https://") else h
    bewaar_hoesje(f"{p[0]}:{p[1]}", hoesje)
    lied = {"spotify": f"spotify:{p[0]}:{p[1]}", "naam": naam, "soort": p[0], "hoesje": hoesje}
    onthoud({"spotify": lied["spotify"], "soort": p[0], "titel": naam, "hoesje": hoesje})
    return lied


async def plek_zetten(request):
    n = plek_nummer(request)
    lied = await lied_uit(request, await request.json())
    s = staat(); s["plekken"][str(n)] = lied; bewaar(s)
    return web.json_response({"ok": True})


async def plek_naam(request):
    n = plek_nummer(request)
    naam = schoon((await request.json()).get("naam"))
    s = staat()
    if not naam or not s["plekken"][str(n)]["spotify"]:
        raise web.HTTPBadRequest()
    s["plekken"][str(n)]["naam"] = naam; bewaar(s)
    return web.json_response({"ok": True, "naam": naam})


async def plek_leeg(request):
    n = plek_nummer(request)
    s = staat(); s["plekken"][str(n)] = leeg_lied(); bewaar(s)
    return web.json_response({"ok": True})


async def wissel(request):
    body = await request.json()
    a, b = int(body.get("a", 0)), int(body.get("b", 0))
    if a not in PLEKKEN or b not in PLEKKEN or a == b:
        raise web.HTTPBadRequest()
    s = staat(); p = s["plekken"]
    p[str(a)], p[str(b)] = p[str(b)], p[str(a)]
    bewaar(s)
    return web.json_response({"ok": True})


async def druk(session, n):
    """Wat er gebeurt als plek n wordt 'ingedrukt' (knop aan de muur of ▶ in de app)."""
    s = staat()
    sp = s["speaker"]
    lied = s["plekken"][str(n)]
    if not sp or not lied["spotify"]:
        return "leeg"
    p = await speler(session, sp)
    staat_nu = p.get("playback_state") or p.get("state")
    if rusttijd()[0]:
        if staat_nu == "playing":
            await ma(session, "players/cmd/pause", player_id=sp)
        return "rust"
    if s["laatste"] == n and speelt_dit(p, lied):
        if staat_nu == "playing":
            await ma(session, "players/cmd/pause", player_id=sp); return "pauze"
        if staat_nu == "paused":
            await ma(session, "players/cmd/play", player_id=sp); return "verder"
    s["laatste"] = n; bewaar(s)
    await speel_lied(session, sp, lied)
    return "speelt"


async def speel(request):
    if rusttijd()[0]:
        raise web.HTTPConflict(text="De knop slaapt.")
    return web.json_response({"ok": True, "wat": await druk(request.app["http"], plek_nummer(request))})


async def pauze(request):
    s = staat(); sp = s["speaker"]
    p = await speler(request.app["http"], sp)
    if (p.get("playback_state") or p.get("state")) == "paused":
        if rusttijd()[0]:
            raise web.HTTPConflict(text="De knop slaapt.")
        await ma(request.app["http"], "players/cmd/play", player_id=sp)
    else:
        await ma(request.app["http"], "players/cmd/pause", player_id=sp)
    return web.json_response({"ok": True})


async def speaker(request):
    sp = (await request.json()).get("speaker")
    if sp not in SPEAKERS:
        raise web.HTTPBadRequest()
    s = staat(); s["speaker"] = sp; bewaar(s)
    return web.json_response({"ok": True})


async def link(request):
    u = request.query.get("u", "").strip()
    sess = request.app["http"]
    if not ontleed(u) and (urlparse(u).hostname or "") in ("spotify.link", "spotify.app.link"):
        try:
            async with sess.get(u, allow_redirects=True, max_redirects=5, timeout=aiohttp.ClientTimeout(total=8)) as r:
                u = " ".join(str(h.url) for h in [*r.history, r])
        except (aiohttp.ClientError, TimeoutError):
            pass
    p = ontleed(u)
    if not p:
        return web.json_response({"ok": False})
    titel, hoesje = await oembed(sess, *p)
    bewaar_hoesje(f"{p[0]}:{p[1]}", hoesje)
    item = {"spotify": f"spotify:{p[0]}:{p[1]}", "soort": p[0], "titel": titel or "Liedje", "hoesje": hoesje}
    onthoud(item)
    return web.json_response({"ok": True, **item})


async def eerder(request):
    return web.json_response({"items": lees(EERDER, [])})


# ---------- knop aan de muur ----------
async def knop_druk(request):
    return web.json_response({"ok": True, "wat": await druk(request.app["http"], plek_nummer(request))})


async def knop_draai(request):
    richting = request.match_info["richting"]
    if richting not in ("op", "neer"):
        raise web.HTTPNotFound()
    s = staat(); sp = s["speaker"]
    if richting == "op" and rusttijd()[0]:
        return web.json_response({"ok": True, "wat": "rust"})
    p = await speler(request.app["http"], sp)
    v = int(p.get("volume_level") or 20) + (STAP if richting == "op" else -STAP)
    v = max(0, min(MAX_VOLUME, v))
    await ma(request.app["http"], "players/cmd/volume_set", player_id=sp, volume_level=v)
    return web.json_response({"ok": True, "volume": v})


# ---------- wekkers ----------
def wekker_nummer(request):
    try:
        k = int(request.match_info["k"])
    except ValueError:
        raise web.HTTPNotFound()
    if k not in WEKKERS:
        raise web.HTTPNotFound()
    return k


async def wekkers(request):
    s = staat()
    uit = [{"nummer": k, "tijd": w["tijd"], "aan": w["aan"] and bool(w["spotify"]), "dagen": w["dagen"],
            "vol": bool(w["spotify"]), "spotify": w["spotify"], "soort": w["soort"], "naam": w["naam"], "hoesje": w["hoesje"]}
           for k, w in enumerate(s["wekkers"], 1)]
    return web.json_response({"wekkers": uit, "vroegst": VROEGST, "laatst": LAATST})


async def wekker_zetten(request):
    k = wekker_nummer(request)
    body = await request.json()
    s = staat(); w = s["wekkers"][k - 1]
    if "tijd" in body:
        w["tijd"] = goede_tijd(body["tijd"])
    if "dagen" in body:
        w["dagen"] = [d for d in DAGEN if d in (body["dagen"] or [])]
    if body.get("leeg"):
        w.update(leeg_lied()); body["aan"] = False
    elif body.get("spotify"):
        w.update(await lied_uit(request, body)); body.setdefault("aan", True)
    if "aan" in body:
        w["aan"] = bool(body["aan"]) and bool(w["spotify"])
    bewaar(s)
    return web.json_response({"ok": True})


async def wekker_probeer(request):
    k = wekker_nummer(request)
    s = staat(); w = s["wekkers"][k - 1]
    if w["spotify"] and s["speaker"]:
        await speel_lied(request.app["http"], s["speaker"], w, volume=WEKKER_VOLUME)
    return web.json_response({"ok": True})


async def wekker_lus(app):
    """Kijkt elke 15 s of er een wekker af moet gaan (lokale tijd, één keer per dag)."""
    while True:
        try:
            nu = datetime.now(TZ)
            vandaag, tijd, dag = nu.strftime("%Y-%m-%d"), nu.strftime("%H:%M"), DAGEN[nu.weekday()]
            s = staat()
            for k, w in enumerate(s["wekkers"], 1):
                sleutel = f"wekker{k}"
                if (w["aan"] and w["spotify"] and dag in w["dagen"] and w["tijd"] <= tijd < (datetime.strptime(w["tijd"], "%H:%M") + timedelta(minutes=2)).strftime("%H:%M")
                        and s["gedaan"].get(sleutel) != vandaag and s["speaker"]):
                    s["gedaan"][sleutel] = vandaag; bewaar(s)
                    await speel_lied(app["http"], s["speaker"], w, volume=WEKKER_VOLUME)
                    app.logger.info("wekker %s afgegaan (%s)", k, w["naam"])
        except Exception as e:  # nooit de lus laten stoppen
            app.logger.warning("wekker: %s", e)
        await asyncio.sleep(15)


# ---------- app ----------
async def index(request):
    return web.FileResponse(HIER / "index.html", headers={"Cache-Control": "no-cache"})


async def start(app):
    app["http"] = aiohttp.ClientSession()
    app["lus"] = asyncio.create_task(wekker_lus(app))


async def stop(app):
    app["lus"].cancel()
    await app["http"].close()


def maak_app():
    app = web.Application(middlewares=[alleen_thuis])
    app.on_startup.append(start)
    app.on_cleanup.append(stop)
    app.router.add_get("/", index)
    app.router.add_get("/api/plekken", plekken)
    app.router.add_post("/api/plek/{n}", plek_zetten)
    app.router.add_delete("/api/plek/{n}", plek_leeg)
    app.router.add_post("/api/plek/{n}/naam", plek_naam)
    app.router.add_post("/api/plek/{n}/speel", speel)
    app.router.add_post("/api/wissel", wissel)
    app.router.add_post("/api/pauze", pauze)
    app.router.add_post("/api/speaker", speaker)
    app.router.add_get("/api/link", link)
    app.router.add_get("/api/eerder", eerder)
    app.router.add_get("/api/wekkers", wekkers)
    app.router.add_post("/api/wekker/{k}", wekker_zetten)
    app.router.add_post("/api/wekker/{k}/probeer", wekker_probeer)
    app.router.add_post("/api/druk/{n}", knop_druk)
    app.router.add_post("/api/draai/{richting}", knop_draai)
    app.router.add_static("/static", HIER / "static")
    return app


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    web.run_app(maak_app(), host="0.0.0.0", port=POORT, access_log=None)
