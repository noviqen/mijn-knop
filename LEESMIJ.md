# Mijn knop

Een app op de iPad waarmee je kind zelf liedjes uit Spotify op de knop aan de muur zet. Kort of lang drukken geeft 8 plekken. Daarbij eigen wekkers en slaapliedjes, een rusttijd 's nachts, en na het liedje is het stil.

Bekijk eerst het filmpje: `demo/mijn-knop-demo.mp4`

**Installeren:** zeg tegen je Claude in T3:

> Haal github.com/noviqen/mijn-knop op en installeer Mijn knop volgens OVERDRACHT.md.

Je Claude controleert je server en zet alles neer: Music Assistant, de app en het script voor Homey. Twee dingen doe je daarna zelf, en je Claude legt uit hoe:
1. **Spotify koppelen** in Music Assistant. Dat is één keer inloggen met je Spotify Premium-account.
2. **De Flows in Homey** maken: welke knop welk nummer krijgt.

**Wat je nodig hebt:**
- een server thuis met Docker
- Spotify Premium
- speakers die Music Assistant kent: Google/Nest, Sonos, AirPlay en meer
- een Homey met HomeyScript, of een ander systeem dat een webadres kan aanroepen
- een knop, bijvoorbeeld de Philips Hue Tap Dial

Gemaakt door Roy (noviqen).
