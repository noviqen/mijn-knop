"""Webapp "Mijn knop": een kind zet zelf liedjes op zijn of haar knop aan de muur (iPad).

8 plekken: knop 1-4 kort drukken = plek 1-4, lang drukken = plek 5-8.
Een plek = input_text.kind_knop_N (Spotify-link) + input_text.kind_knop_N_naam.
Afspelen doet HA zelf (script.kind_knop, automation.knop_kind_hue_tap_dial).

Alleen bereikbaar vanaf het thuisnetwerk. De HA-sleutel blijft op de server
(~/.config/webapps/ha.token, account "Webapps", geen admin). Deze server kent
alleen de acties hieronder; al het andere wordt geweigerd.
Liedjes komen binnen als Spotify-link (de iPad van het kind heeft een eigen Spotify-account,
dus HA's Spotify-bibliotheek is niet de hare). Titel en hoesje via Spotify oEmbed.
Hoesjes staan in data/hoesjes.json, eerder geplakte liedjes in data/eerder.json.
Draaien: python server.py  (aiohttp nodig; als dienst via systemd --user)
"""
import ipaddress
import itertools
import json
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import quote, urlparse

import aiohttp
from aiohttp import web

HA = "http://<HOME-ASSISTANT-IP>"
TOKEN = Path(os.path.expanduser("~/.config/webapps/ha.token")).read_text().strip()
HIER = Path(__file__).parent
HOESJES = HIER / "data" / "hoesjes.json"
EERDER = HIER / "data" / "eerder.json"
EERDER_MAX = 48
POORT = 8857
THUIS = ipaddress.ip_network("192.168.1.0/24")   # pas aan naar je eigen thuisnetwerk

PLEKKEN = range(1, 9)
SPEAKERS = {
    "media_player.kinderkamer": "Mijn kamer",
    "media_player.keuken": "Keuken",
}
SOORTEN = "track|episode|album|playlist|show"
URI = re.compile(rf"(?:spotify:|open\.spotify\.com/(?:intl-[a-z-]+/)?)({SOORTEN})[/:]([A-Za-z0-9]{{22}})")
NAAM_MAX = 40
WEKKERS = range(1, 5)
DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
VROEGST, LAATST = "05:00", "21:00"   # wekkers niet later dan de vroegste rusttijd
RUST = "binary_sensor.knop_kind_rusttijd"   # doordeweeks 21-07, weekend 22-09 (helpers input_datetime.knop_kind_rust_*)


@web.middleware
async def alleen_thuis(request, handler):
    ip = ipaddress.ip_address(request.remote or "0.0.0.0")
    if ip not in THUIS and not ip.is_loopback:
        return web.Response(status=403, text="Alleen thuis op de wifi.")
    return await handler(request)


async def ha(session, method, path, data=None):
    async with session.request(method, HA + path, json=data,
                               headers={"Authorization": f"Bearer {TOKEN}"},
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
        r.raise_for_status()
        return await r.json()


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


def lees_hoesjes():
    return lees(HOESJES, {})


def onthoud(item):
    """Bovenaan 'Eerder toegevoegd' zetten (zonder dubbele)."""
    lijst = [x for x in lees(EERDER, []) if x.get("spotify") != item["spotify"]]
    schrijf(EERDER, ([item] + lijst)[:EERDER_MAX])


def bewaar_hoesje(sleutel, url):
    if not url or not url.startswith("https://"):
        return
    h = lees_hoesjes()
    if h.get(sleutel) != url:
        h[sleutel] = url
        schrijf(HOESJES, h)


def ontleed(tekst):
    m = URI.search(tekst or "")
    return (m.group(1), m.group(2)) if m else None


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
    s = request.app["http"]
    alle = {x["entity_id"]: x for x in await ha(s, "GET", "/api/states")}
    hoesjes = lees_hoesjes()
    uit = []
    for n in PLEKKEN:
        link = (alle.get(f"input_text.kind_knop_{n}", {}).get("state") or "").strip()
        naam = (alle.get(f"input_text.kind_knop_{n}_naam", {}).get("state") or "").strip()
        p = ontleed(link)
        hoesje = ""
        if p:
            sleutel = f"{p[0]}:{p[1]}"
            hoesje = hoesjes.get(sleutel, "")
            if not hoesje:                       # oude knoppen: één keer opzoeken
                _, hoesje = await oembed(s, *p)
                bewaar_hoesje(sleutel, hoesje)
        uit.append({"nummer": n, "vol": bool(p), "naam": naam if p else "",
                    "spotify": f"spotify:{p[0]}:{p[1]}" if p else "",
                    "soort": p[0] if p else "", "hoesje": hoesje})
    speaker = alle.get("input_select.knop_kind_speaker", {}).get("state", "")
    sp = alle.get(speaker, {})
    a = sp.get("attributes", {})
    laatste = int(float(alle.get("input_number.kind_knop_laatste", {}).get("state") or 0))
    rust = alle.get(RUST, {}).get("state") == "on"
    nu = datetime.now(ZoneInfo("Europe/Amsterdam"))
    ochtend = nu if nu.hour < 12 else nu + timedelta(days=1)
    tot = alle.get("input_datetime.knop_kind_rust_tot_weekend" if ochtend.weekday() >= 5 else "input_datetime.knop_kind_rust_tot", {}).get("state", "")[:5]
    return web.json_response({
        "plekken": uit,
        "speaker": speaker,
        "speakers": [{"id": k, "naam": v} for k, v in SPEAKERS.items()],
        "rust": rust, "rust_tot": tot,
        "nu": {"staat": sp.get("state", ""), "titel": a.get("media_title") or "",
               "artiest": a.get("media_artist") or "", "plek": laatste},
    })


def plek_nummer(request):
    try:
        n = int(request.match_info["n"])
    except ValueError:
        raise web.HTTPNotFound()
    if n not in PLEKKEN:
        raise web.HTTPNotFound()
    return n


async def zet(session, n, link, naam):
    await ha(session, "POST", "/api/services/input_text/set_value",
             {"entity_id": f"input_text.kind_knop_{n}", "value": link})
    await ha(session, "POST", "/api/services/input_text/set_value",
             {"entity_id": f"input_text.kind_knop_{n}_naam", "value": naam})


def schoon(naam):
    naam = re.sub(r"\s+", " ", str(naam or "")).strip()
    return naam if len(naam) <= NAAM_MAX else naam[:NAAM_MAX - 1].rstrip() + "…"


async def plek_zetten(request):
    n = plek_nummer(request)
    body = await request.json()
    p = ontleed(body.get("spotify", ""))
    if not p:
        raise web.HTTPBadRequest(text="Dat is geen Spotify-liedje.")
    s = request.app["http"]
    naam, hoesje = schoon(body.get("naam")), str(body.get("hoesje") or "")
    if not naam or not hoesje.startswith("https://"):
        t, h = await oembed(s, *p)
        naam = naam or schoon(t) or "Liedje"
        hoesje = hoesje if hoesje.startswith("https://") else h
    bewaar_hoesje(f"{p[0]}:{p[1]}", hoesje)
    onthoud({"spotify": f"spotify:{p[0]}:{p[1]}", "soort": p[0], "titel": naam, "hoesje": hoesje})
    await zet(s, n, f"https://open.spotify.com/{p[0]}/{p[1]}", naam)
    return web.json_response({"ok": True})


async def plek_naam(request):
    n = plek_nummer(request)
    naam = schoon((await request.json()).get("naam"))
    if not naam:
        raise web.HTTPBadRequest()
    await ha(request.app["http"], "POST", "/api/services/input_text/set_value",
             {"entity_id": f"input_text.kind_knop_{n}_naam", "value": naam})
    return web.json_response({"ok": True, "naam": naam})


async def plek_leeg(request):
    await zet(request.app["http"], plek_nummer(request), "", "")
    return web.json_response({"ok": True})


async def wissel(request):
    body = await request.json()
    a, b = int(body.get("a", 0)), int(body.get("b", 0))
    if a not in PLEKKEN or b not in PLEKKEN or a == b:
        raise web.HTTPBadRequest()
    s = request.app["http"]
    st = {x["entity_id"]: x["state"] for x in await ha(s, "GET", "/api/states")}
    la, na = st.get(f"input_text.kind_knop_{a}", ""), st.get(f"input_text.kind_knop_{a}_naam", "")
    lb, nb = st.get(f"input_text.kind_knop_{b}", ""), st.get(f"input_text.kind_knop_{b}_naam", "")
    await zet(s, a, lb, nb)
    await zet(s, b, la, na)
    return web.json_response({"ok": True})


async def speel(request):
    n = plek_nummer(request)
    if (await ha(request.app["http"], "GET", f"/api/states/{RUST}")).get("state") == "on":
        raise web.HTTPConflict(text="De knop slaapt.")
    await ha(request.app["http"], "POST", "/api/services/script/kind_knop", {"nummer": n})
    return web.json_response({"ok": True})


async def huidige_speaker(s):
    sp = (await ha(s, "GET", "/api/states/input_select.knop_kind_speaker"))["state"]
    if sp not in SPEAKERS:
        raise web.HTTPConflict()
    return sp


async def pauze(request):
    s = request.app["http"]
    sp = await huidige_speaker(s)
    actie = "media_play" if (await ha(s, "GET", f"/api/states/{sp}"))["state"] == "paused" else "media_pause"
    if actie == "media_play" and (await ha(s, "GET", f"/api/states/{RUST}")).get("state") == "on":
        raise web.HTTPConflict(text="De knop slaapt.")    # 's nachts alleen pauze, niet weer aanzetten
    await ha(s, "POST", f"/api/services/media_player/{actie}", {"entity_id": sp})
    return web.json_response({"ok": True})


async def speaker(request):
    sp = (await request.json()).get("speaker")
    if sp not in SPEAKERS:
        raise web.HTTPBadRequest()
    await ha(request.app["http"], "POST", "/api/services/input_select/select_option",
             {"entity_id": "input_select.knop_kind_speaker", "option": sp})
    return web.json_response({"ok": True})


async def link(request):
    """Geplakte link (ook spotify.link-korte links) -> titel en hoesje."""
    u = request.query.get("u", "").strip()
    s = request.app["http"]
    host = urlparse(u).hostname or ""
    if not ontleed(u) and host in ("spotify.link", "spotify.app.link"):
        try:
            async with s.get(u, allow_redirects=True, max_redirects=5,
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                u = " ".join(str(h.url) for h in itertools.chain(r.history, [r]))
        except (aiohttp.ClientError, TimeoutError):
            pass
    p = ontleed(u)
    if not p:
        return web.json_response({"ok": False})
    titel, hoesje = await oembed(s, *p)
    item = {"spotify": f"spotify:{p[0]}:{p[1]}", "soort": p[0], "titel": titel or "Liedje", "hoesje": hoesje}
    onthoud(item)
    return web.json_response({"ok": True, **item})


async def eerder(request):
    return web.json_response({"items": lees(EERDER, [])})


def wekker_nummer(request):
    try:
        k = int(request.match_info["k"])
    except ValueError:
        raise web.HTTPNotFound()
    if k not in WEKKERS:
        raise web.HTTPNotFound()
    return k


async def wekkers(request):
    s = request.app["http"]
    alle = {x["entity_id"]: x for x in await ha(s, "GET", "/api/states")}
    hoesjes = lees_hoesjes()
    st = lambda e: (alle.get(e, {}).get("state") or "").strip()
    uit = []
    for k in WEKKERS:
        p = ontleed(st(f"input_text.kind_wekker_{k}_link"))
        hoesje = ""
        if p:
            hoesje = hoesjes.get(f"{p[0]}:{p[1]}", "")
            if not hoesje:
                _, hoesje = await oembed(s, *p)
                bewaar_hoesje(f"{p[0]}:{p[1]}", hoesje)
        uit.append({"nummer": k, "tijd": st(f"input_datetime.kind_wekker_{k}")[:5],
                    "aan": st(f"input_boolean.kind_wekker_{k}_aan") == "on",
                    "dagen": [d for d in st(f"input_text.kind_wekker_{k}_dagen").split(",") if d in DAGEN],
                    "vol": bool(p), "spotify": f"spotify:{p[0]}:{p[1]}" if p else "", "soort": p[0] if p else "",
                    "naam": st(f"input_text.kind_wekker_{k}_naam") if p else "", "hoesje": hoesje})
    return web.json_response({"wekkers": uit, "vroegst": VROEGST, "laatst": LAATST})


def goede_tijd(t):
    t = str(t)
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t) or not (VROEGST <= t <= LAATST):
        raise web.HTTPBadRequest(text=f"Kies een tijd tussen {VROEGST} en {LAATST}.")
    return t


async def wekker_zetten(request):
    """Alles optioneel: tijd, aan, dagen, spotify (+naam, hoesje) of leeg=true."""
    k = wekker_nummer(request)
    body = await request.json()
    s = request.app["http"]
    if "tijd" in body:
        t = goede_tijd(body["tijd"])
        await ha(s, "POST", "/api/services/input_datetime/set_datetime",
                 {"entity_id": f"input_datetime.kind_wekker_{k}", "time": t + ":00"})
    if "dagen" in body:
        dagen = [d for d in DAGEN if d in (body["dagen"] or [])]
        await ha(s, "POST", "/api/services/input_text/set_value",
                 {"entity_id": f"input_text.kind_wekker_{k}_dagen", "value": ",".join(dagen)})
    if body.get("leeg"):
        for veld in ("link", "naam"):
            await ha(s, "POST", "/api/services/input_text/set_value",
                     {"entity_id": f"input_text.kind_wekker_{k}_{veld}", "value": ""})
        body["aan"] = False
    elif body.get("spotify"):
        p = ontleed(body["spotify"])
        if not p:
            raise web.HTTPBadRequest(text="Dat is geen Spotify-liedje.")
        naam, hoesje = schoon(body.get("naam")), str(body.get("hoesje") or "")
        if not naam or not hoesje.startswith("https://"):
            t, h = await oembed(s, *p)
            naam = naam or schoon(t) or "Liedje"
            hoesje = hoesje if hoesje.startswith("https://") else h
        bewaar_hoesje(f"{p[0]}:{p[1]}", hoesje)
        onthoud({"spotify": f"spotify:{p[0]}:{p[1]}", "soort": p[0], "titel": naam, "hoesje": hoesje})
        await ha(s, "POST", "/api/services/input_text/set_value",
                 {"entity_id": f"input_text.kind_wekker_{k}_link", "value": f"https://open.spotify.com/{p[0]}/{p[1]}"})
        await ha(s, "POST", "/api/services/input_text/set_value",
                 {"entity_id": f"input_text.kind_wekker_{k}_naam", "value": naam})
        body.setdefault("aan", True)          # liedje kiezen = wekker aan
    if "aan" in body:
        await ha(s, "POST", f"/api/services/input_boolean/{'turn_on' if body['aan'] else 'turn_off'}",
                 {"entity_id": f"input_boolean.kind_wekker_{k}_aan"})
    return web.json_response({"ok": True})


async def wekker_probeer(request):
    k = wekker_nummer(request)
    await ha(request.app["http"], "POST", "/api/services/script/kind_wekker", {"nummer": k})
    return web.json_response({"ok": True})


async def index(request):
    return web.FileResponse(HIER / "index.html", headers={"Cache-Control": "no-cache"})


async def start(app):
    app["http"] = aiohttp.ClientSession()


async def stop(app):
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
    app.router.add_get("/api/eerder", eerder)
    app.router.add_get("/api/link", link)
    app.router.add_get("/api/wekkers", wekkers)
    app.router.add_post("/api/wekker/{k}", wekker_zetten)
    app.router.add_post("/api/wekker/{k}/probeer", wekker_probeer)
    app.router.add_static("/static", HIER / "static")
    return app


if __name__ == "__main__":
    web.run_app(maak_app(), host="0.0.0.0", port=POORT, access_log=None)
