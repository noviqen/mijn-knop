# Overdracht: "Mijn knop" op Homey zetten

Voor de Claude (T3) van wie dit pakket krijgt. Lees dit helemaal voordat je bouwt.
Dit is een werkende app die op Home Assistant draait. Jouw taak: dezelfde app laten werken met **Homey** en **Sonos** in jouw huis. Kijk eerst wat je eigenaar precies heeft (Homey-model, speakers, welke knop) en vraag niets wat je zelf kunt nakijken.

Kijk eerst naar `demo/mijn-knop-demo.mp4`: zo hoort het eruit te zien en zo hoort het te werken.

---

## 0. Eerst controleren (verplicht, vóór je iets bouwt)

1. Draai `python3 controle.py` in deze map. Het script kijkt alleen en verandert niets. Het controleert Python, de pakketten, het thuisnetwerk, internet, de Sonos, of de app altijd kan blijven draaien, en of de poort vrij is.
2. Staat er **FOUT** in de uitslag? Stop dan en leg je eigenaar in gewone woorden uit wat er mist en wat hij moet doen. Bouw niet verder.
3. Kijk zelf na, of vraag als het niet anders kan:
   - Heeft hij een **Homey Pro** met de app **HomeyScript**?
   - Welke **knop** is het, en staat die in Homey?
   - Is **Spotify gekoppeld in de Sonos-app**?
4. Speel als allereerste proef **één liedje zacht** af op de Sonos met SoCo (ShareLinkPlugin). Lukt dat niet, dan heeft de rest geen zin: los dat eerst op.

---

## 1. Wat de app doet (dit zijn vaste keuzes, niet aan tornen zonder je eigenaar)

- Een kind heeft een draaiknop met 4 knoppen aan de muur (bij ons een Philips **Hue Tap Dial**). Op een iPad richt het kind de knop zelf in.
- **8 plekken:** knop 1–4 **kort** drukken = plek 1–4, knop 1–4 **lang** drukken = plek 5–8.
- **Liedje toevoegen = Spotify-link plakken.** De iPad van het kind heeft een eigen Spotify-account, dus de bibliotheek van het huisaccount laten we niet zien. In Spotify: ••• → Delen → Link kopiëren → in de app plakken. Titel en hoesje komen gratis van Spotify oEmbed (`https://open.spotify.com/oembed?url=…`), dus er is geen Spotify-sleutel nodig.
- **Slepen of tikken:** het kind sleept een liedje naar een plek, of tikt op een liedje en daarna op een plek. Plekken kun je onderling wisselen door te slepen. Een naam pas je aan door erop te tikken (hooguit 40 tekens). Weghalen kan, met een knop "Terugzetten".
- **"Eerder toegevoegd":** alles wat ooit geplakt is, blijft staan om opnieuw te gebruiken.
- **Dezelfde knop nog een keer indrukken = pauze**, nog een keer = verder.
- **Na het liedje stopt hij.** Niets mag doorspelen: de wachtrij wordt vervangen, en herhalen en shuffle staan uit. Een album of afspeellijst speelt helemaal af en stopt dan.
- **Draaien = harder of zachter**, in stappen van 3%, nooit harder dan 60%.
- **Rusttijd:** de knop "slaapt" doordeweeks van 21:00 tot 07:00, en in het weekend van 22:00 tot 09:00 (vrijdag- en zaterdagavond, zaterdag- en zondagochtend).
  - Tijdens de rusttijd start er niets: een knop doet alleen pauze, draaien gaat alleen zachter, en in de app kan het kind niet afspelen of hervatten.
  - De app toont dan "De knop slaapt tot 07:00".
  - Alleen de ouder stelt deze tijden in, niet in de kinder-app.
- **4 wekkers** (tabblad Wekkers): elk met een eigen tijd (05:00–21:00), eigen dagen, aan/uit en een eigen liedje. Bijvoorbeeld 's ochtends wakker worden en 's avonds een slaapliedje. De wekker speelt zacht (22%), haalt de speaker eerst uit een groep en zet het geluid aan.
- **Speaker kiezen:** "Mijn kamer" of een tweede speaker.
- **Ontwerp "Gloed":** donker glas, warm amber (#FFB547). Het lettertype Sora staat lokaal in `app/static`. Het scherm is gemaakt voor de iPad, liggend én staand, en wordt via Safari → Delen → "Zet op beginscherm" een app.
- **Één systeem:** er is maar één plek waar de instellingen staan. Nooit een tweede wekker- of knopsysteem ernaast bouwen, anders gaan dingen dubbel af.

## 2. Hoe het nu werkt (Home Assistant-versie)

- `app/server.py` is een kleine Python-server (aiohttp) die alleen in het thuisnetwerk werkt. De HA-sleutel staat in een bestand op de server, nooit in de browser.
  - De server kent alleen deze acties, al het andere geeft 404: `/api/plekken`, `/api/plek/{n}` (zetten, weghalen, `/naam`, `/speel`), `/api/wissel`, `/api/pauze`, `/api/speaker`, `/api/link`, `/api/eerder`, `/api/wekkers`, `/api/wekker/{k}` (`/probeer`).
- `app/index.html` is de hele iPad-app: één bestand, geen framework. **Dit bestand kun je bijna 1-op-1 houden.** Het praat alleen met de API hierboven.
- In de HA-versie staan de instellingen in HA-helpers (`input_text.kind_knop_N`, `input_datetime.kind_wekker_N`, …). De logica zit in HA-scripts en -automatiseringen: zie `ha-voorbeeld/*.json`. Lees die om te zien wat er precies gebeurt bij drukken, pauze, rusttijd en wekker.

## 3. Plan voor Homey (zo zou ik het doen)

Homey heeft geen helpers zoals HA. Daarom komt alles **in de server zelf**: de server wordt het ene systeem.

1. **Opslag in de server:** één JSON-bestand (`data/staat.json`) met de 8 plekken, de 4 wekkers, de laatst gedrukte plek, de speakerkeuze en de rusttijd-instellingen. Schrijf het atomair weg (tmp-bestand en dan vervangen). De API naar de iPad blijft precies hetzelfde, zodat `index.html` niet hoeft te veranderen.
2. **Afspelen op Sonos met SoCo** (`pip install soco`). Gebruik de Homey Sonos-app hier niet voor: die speelt geplakte Spotify-links niet goed af.
   - Afspelen: `ShareLinkPlugin(speaker).add_share_link_to_queue(link)` na `speaker.clear_queue()`. Zet daarna `speaker.play_mode = "NORMAL"` (dus niet herhalen en niet shufflen) en `speaker.play_from_queue(0)`. Zo stopt hij na het liedje.
   - Voorwaarde: Spotify is gekoppeld in de Sonos-app van het huis. Test dit als allereerste.
   - Pauze, verder, volume en uit een groep halen (`unjoin`) gaan ook via SoCo.
   - Geen Sonos in huis? Overleg dan eerst met je eigenaar. Dan wordt het een andere route.
3. **Knop → server.** Gebruik in Homey per knop-actie een Flow met **HomeyScript** (officiële Athom-app), dat de server aanroept met `fetch`:
   - knop N kort → `POST http://<server>:<poort>/api/druk/N`
   - knop N lang → `POST …/api/druk/N+4`
   - draaien → `POST …/api/draai/+1` of `/-1`
   - De nieuwe endpoints `druk` en `draai` bevatten de logica die nu in `ha-voorbeeld/script_knop.json` en `automatisering_knop.json` staat: rusttijd, pauze bij dezelfde knop, volume hooguit 60%.
   - Zet de Flows zo op dat ze één keer werken en daarna nooit meer aangepast hoeven te worden: alle keuzes zitten in de server.
4. **Wekkers en rusttijd in de server:** een asyncio-lus die elke 20 seconden kijkt of een wekker moet afgaan, in tijdzone Europe/Amsterdam (de server zelf kan op UTC staan!). Onthoud welke wekker vandaag al is afgegaan. Rusttijd volgens de regels hierboven. Geef in `/api/plekken` `rust` en `rust_tot` mee: de app laat die al zien.
5. **Veiligheid:** de server werkt alleen in het thuisnetwerk (check het IP-adres van elke aanvraag). Er gaan geen poorten open naar internet en er komen geen sleutels in code of git. De server draait als `systemd --user`-dienst.

## 4. Wat je uit `server.py` haalt of vervangt

- Alles met `ha(...)`, `HA`, `TOKEN`, `input_*`, `script.*`, `binary_sensor.*` → vervangen door de JSON-opslag en SoCo.
- `SPEAKERS`: de namen van de Sonos-speakers in dit huis, met een vriendelijke naam ("Mijn kamer").
- `THUIS`: het eigen thuisnetwerk.
- Houd aan: `ontleed()` (Spotify-link herkennen, ook `intl-nl` en `spotify.link`-korte links), `oembed()`, hoesjes-cache, "Eerder toegevoegd", `schoon()` (namen inkorten), de tijdsgrenzen 05:00–21:00 voor wekkers.

## 5. Klaar is pas klaar als dit werkt (zelf testen, op het echte huis)

- [ ] Link plakken → titel en hoesje verschijnen → slepen naar plek 4 → kort drukken op knop 4 → liedje speelt in de kinderkamer
- [ ] Nog een keer knop 4 → pauze; nog een keer → verder
- [ ] Lang drukken op knop 1 → plek 5
- [ ] Liedje afgelopen → het is stil (er speelt niets anders verder)
- [ ] Draaien → volume ±3%, nooit boven 60%
- [ ] Rusttijd (zet hem voor de test even op nu) → knoppen doen alleen pauze, draaien alleen zachter, app toont "slaapt", ▶ is weg
- [ ] Wekker op over 2 minuten → speelt zacht af, één keer
- [ ] iPad liggend en staand: alles past, niets valt eruit
- [ ] Nergens staat een sleutel in de browser, en de server is van buiten het thuisnetwerk niet bereikbaar

Test met het geluid zacht, of als er niemand in de kinderkamer is. Laat je eigenaar pas daarna met het kind proberen.
