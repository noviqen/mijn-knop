# Overdracht: "Mijn knop" installeren (voor de Claude van de nieuwe eigenaar)

Lees dit helemaal. Kijk eerst naar `demo/mijn-knop-demo.mp4`: zo hoort het eruit te zien en te werken.
Vraag je eigenaar niets wat je zelf kunt nakijken. Werk stap voor stap en leg in gewone, korte taal uit wat je doet.

**Kort:** dit pakket is een kant-en-klare app. `installeer.sh` zet alles neer: Music Assistant (Docker), de app als dienst, en een HomeyScript voor de knop. Er blijven twee dingen over die de eigenaar zelf doet: **Spotify koppelen** in Music Assistant (inloggen in de browser) en **de Flows in Homey** maken (die kun je niet van buitenaf aanmaken).

---

## 1. Wat de app doet (vaste keuzes, niet veranderen zonder je eigenaar)

- Een kind heeft een knop met 4 knoppen en een draaiknop aan de muur (bij ons de Philips Hue Tap Dial). Het kind richt die zelf in op een iPad.
- **8 plekken:** knop 1–4 **kort** drukken = plek 1–4, **lang** drukken = plek 5–8.
- **Liedje toevoegen = Spotify-link plakken** (••• → Delen → Link kopiëren). Daarna sleept het kind het liedje naar een plek, of tikt het eerst op het liedje en dan op de plek. "Eerder toegevoegd" bewaart alles wat ooit geplakt is.
- **Dezelfde knop nog een keer indrukken = pauze**, nog een keer = verder. **Draaien** = 3% harder of zachter, nooit harder dan 60%.
- **Na het liedje is het stil:** de wachtrij wordt vervangen, en herhalen, shuffle en "autoplay" staan uit.
- **Rusttijd:** de knop slaapt doordeweeks van 21:00 tot 07:00 en in het weekend van 22:00 tot 09:00 (vr- en za-avond, za- en zo-ochtend). Dan start er niets: een knop doet alleen pauze, draaien gaat alleen zachter. De ouder stelt de tijden in via `app/config.json` → `rust`.
- **4 wekkers en slaapliedjes:** het kind stelt zelf de tijd (05:00–21:00), de dagen en het liedje in. Een wekker speelt zacht (22%).
- **Één systeem:** alle instellingen staan in de server (`app/data/`). Nooit ernaast een tweede wekker- of knopsysteem in Homey bouwen.

## 2. Hoe het in elkaar zit

```
iPad (Safari-app) ──► app/server_ma.py (deze server, alleen thuisnetwerk) ──► Music Assistant ──► speakers (Google Cast, Sonos, AirPlay …)
Knop aan de muur ──► Homey Flow ──► HomeyScript (homey/knop.js) ──► POST /api/druk/1-8 of /api/draai/op|neer
```
- `app/index.html`: de hele iPad-app.
- `app/server_ma.py`: de server. Hij slaat de instellingen op, regelt rusttijd en wekkers, en speelt af via de Music Assistant-API.
- `app/config.json`: wordt gemaakt door de installatie (op basis van `config.voorbeeld.json`). Hierin staan de speakers, de rusttijd en het volume.
- `installatie/`: `docker-compose.yml` voor Music Assistant en `ma_setup.py`, dat een gebruiker en een sleutel aanmaakt, de speakers zoekt en controleert of Spotify gekoppeld is.
- `app/server.py` + `ha-voorbeeld/`: de **Home Assistant-versie** waar het vandaan komt. Die heb je hier niet nodig; hij staat er alleen als voorbeeld.

## 3. Installeren

1. `python3 controle.py`. Staat er een **FOUT**? Los die eerst op, of leg je eigenaar uit wat er moet gebeuren.
2. `./installeer.sh`. Zonder opties zet hij Music Assistant neer en laat hij **alle gevonden speakers** zien.
3. Vraag je eigenaar welke speaker in de kinderkamer staat (of leid het af uit de namen). Draai dan:
   `./installeer.sh --speaker "<naam of id>"`. Een tweede `--speaker` wordt een extra keuze in de app.
   - Komt een naam twee keer voor (bijv. een Google- en een Sonos-speaker), gebruik dan het id.
   - Is poort 8857 bezet, voeg dan `--poort 88xx` toe (kies tussen 8700 en 8899).
4. **Spotify koppelen (eigenaar, eenmalig):** stuur je eigenaar de link naar Music Assistant (`http://<server>:8095`). De inloggegevens staan in `~/.config/mijn-knop/music-assistant-inlog.txt`. Daar: Instellingen → Muziekbronnen → Spotify toevoegen → inloggen. **Spotify Premium is nodig.** Draai daarna `./installeer.sh --speaker …` nog een keer: dan moet er "Spotify is gekoppeld" staan.
   Had de eigenaar Music Assistant al? Dan maakt het script geen nieuwe gebruiker. In dat geval maakt de eigenaar een token aan (Instellingen → Profiel → Tokens) en zet het in `~/.config/mijn-knop/ma.token`.
5. **Eerste echte proef:** zet het volume laag en speel één liedje via de app. Lukt dat niet, los het dan eerst op. Kijk in `journalctl --user -u mijn-knop -n 50` en in de log van Music Assistant (`docker logs music-assistant`). Bij Google- of Nest-speakers: kijk of de speaker in Music Assistant staat en of hij daar zelf afspeelt.

## 4. Homey koppelen (de eigenaar klikt, jij legt uit)

1. Installeer de app **HomeyScript** (van Athom) op de Homey.
2. Maak in HomeyScript een script **"Mijn knop"** met de inhoud van `homey/knop-ingevuld.js`. Dat bestand heeft het installatiescript al ingevuld met het juiste serveradres.
3. Maak de Flows. Voor de Hue Tap Dial zijn dat er 10, of één geavanceerde Flow:
   - **Als** knop 1 kort ingedrukt → **Dan** HomeyScript "Voer script uit met argument" → *Mijn knop*, argument `1`. Doe hetzelfde voor knop 2–4 (argument `2`–`4`).
   - **Als** knop 1 lang ingedrukt → argument `5`. Knop 2–4 lang → argument `6`–`8`.
   - **Als** draaiknop rechtsom → argument `op`. **Als** linksom → argument `neer`.
   - Heet een knop-trigger in Homey anders (bijv. "ingedrukt" en "losgelaten"), kies dan de variant die **één keer** per druk afgaat.
4. Test elke knop zelf (het volume laag) en kijk of het werkt.

## 5. iPad

Open `http://<server>:<poort>` in Safari en kies Delen → **Zet op beginscherm**. De app werkt alleen via de wifi thuis.

## 6. Klaar is pas klaar als dit werkt (zelf testen, op het echte huis)

- [ ] Link plakken → titel en hoesje verschijnen → slepen naar plek 4 → knop 4 kort → het liedje speelt in de kinderkamer
- [ ] Knop 4 nog een keer → pauze; nog een keer → verder
- [ ] Knop 1 lang → plek 5
- [ ] Liedje afgelopen → het is stil
- [ ] Draaien → volume ±3%, nooit boven 60%
- [ ] Rusttijd (zet `rust.vanaf` even op nu, herstart de dienst) → knop alleen pauze, draaien alleen zachter, app toont "slaapt"; zet het daarna terug
- [ ] Wekker op over 2 minuten → speelt zacht af, één keer
- [ ] iPad liggend en staand: alles past
- [ ] Van buiten het thuisnetwerk niet bereikbaar; geen sleutels in git of in de browser

**Bijwerken:** `git pull` en daarna `./installeer.sh --speaker "<zelfde>"`. De instellingen in `app/data/` blijven bewaard.
