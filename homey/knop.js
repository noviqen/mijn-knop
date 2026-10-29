// HomeyScript voor Mijn knop. Maak dit script één keer aan in de HomeyScript-app (naam: "Mijn knop").
// In een Flow: "Voer script uit met argument" -> Mijn knop, met als argument:
//   1 t/m 4  = knop 1-4 kort drukken
//   5 t/m 8  = knop 1-4 lang drukken
//   op / neer = draaiknop harder / zachter
const SERVER = 'http://SERVER-IP:8857';   // <- installeer.sh vult dit in

const a = String((args && args[0]) || '').trim().toLowerCase();
let pad;
if (a === 'op' || a === 'neer') pad = `/api/draai/${a}`;
else if (/^[1-8]$/.test(a)) pad = `/api/druk/${a}`;
else throw new Error(`Onbekend argument "${a}". Gebruik 1-8, op of neer.`);

const r = await fetch(SERVER + pad, { method: 'POST' });
if (!r.ok) throw new Error(`Mijn knop gaf ${r.status}: ${await r.text()}`);
return true;
