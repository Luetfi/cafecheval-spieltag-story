# Spieltag-Stories für @cafechevallb

Erzeugt am Morgen eines Spieltags pro gezeigtem Spiel eine Instagram-Story (1080 × 1920 JPEG):
KI-Hintergrund von kie.ai, darüber Wappen, Wettbewerb, Uhrzeit und Datum im Marken-Design.
Die Stories kommen per Telegram-Bot (@cafecheval_story_bot) zur Freigabe. Erst nach „Posten“
gehen sie über die Instagram API auf @cafechevallb.

## Ablauf (GitHub Actions, `.github/workflows/spieltag-story.yml`)

**Wecker:** GitHubs eigener Zeitplan (`schedule`) hat in diesem Repository nie zuverlässig ausgelöst. Deshalb
startet [cron-job.org](https://console.cron-job.org) (Konto des Betreuers) den Workflow per API:

| Uhrzeit (Europe/Berlin) | Body |
| --- | --- |
| 07:00 | `{"ref":"main","inputs":{"befehl":"morgen"}}` |
| 12:30 | `{"ref":"main","inputs":{"befehl":"bot"}}` (Sicherheitsnetz) |
| 17:30 | `{"ref":"main","inputs":{"befehl":"bot"}}` (Sicherheitsnetz) |

Jeweils `POST https://api.github.com/repos/Luetfi/cafecheval-spieltag-story/actions/workflows/spieltag-story.yml/dispatches`
mit den Headern `Authorization: Bearer <Fine-grained Token, nur dieses Repo, Actions: Read and write>`,
`Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`.
Läuft der Token ab, kommt der neue in alle drei Cronjobs. Läuft der Bot schon, ersetzt ein weiterer Start
nur den wartenden Lauf, es passiert nichts doppelt. GitHubs eigener `schedule` ist aus dem Workflow entfernt.

**Automatische allgemeine Stories** (`ZEITPLAN` in `config.py`) postet der Bot ohne Freigabe und schickt danach
eine Info in Telegram: täglich 14:00 „Wir haben geöffnet“, Di–Do 18:30 und Sa 19:00 „Zeit für einen Drink“,
Fr 17:00 „Endlich Wochenende“, So 16:00 „Feiern bei uns“. Die Texte wechseln täglich zwischen Varianten
(`allgemein.py`), die Fotos zufällig. `/pause` (heute), `/pause 7`, `/weiter`, `/zeitplan`, oder per Nachricht
(„wir haben morgen zu“). Verpasste Termine werden bis 60 Minuten später nachgeholt, nie doppelt
(`status/zeitplan.json`).

**Beliebte Spiele automatisch** (`AUTO_POSTEN` in `config.py`): Von den Spielen des Morgens werden bis zu
`AUTO_MAX_PRO_TAG` (4) ohne Freigabe gepostet, und zwar empfohlene (⭐) und solche mit einer Mannschaft aus
`BELIEBTE`. Sie kommen morgens wie alle anderen in Telegram an, mit dem Hinweis „🤖 Wird um … automatisch
gepostet“. Gepostet wird 3 Stunden vor Anstoß, frühestens 10 Uhr, spätestens 20 Uhr. Bis dahin lässt sich die
Story ändern (die Uhrzeit bleibt), sofort posten oder verwerfen (dann geht sie nicht raus). `/pause` gilt auch
hier, `/zeitplan` zeigt die geplanten Spiele.

**Instagram-Token:** gilt 60 Tage, beim Verlängern gibt Instagram einen neuen Token aus. Montags verlängert der
Morgen-Lauf ihn und speichert ihn als Secret, wenn das Secret `GH_PAT` existiert (Fine-grained Token, nur dieses
Repo, Rechte „Secrets: Read and write“). Ohne `GH_PAT` warnt der Bot in Telegram, sobald der zuletzt gespeicherte
Token (`status/token.txt`) 50 Tage alt ist.

- **Morgens** (cron-job.org 7:00, Reserve: GitHub-Zeitplan): `python lauf.py morgen` schickt alle Spiele
  des Tages aus `WETTBEWERBE` als Story, empfohlene zuerst (⭐). Danach läuft derselbe Lauf als Bot weiter.
- **Bot** bis 23 Uhr: bearbeitet „Posten“/„Verwerfen“ sofort und beantwortet Anfragen. Nach 5:40 Stunden
  startet sich der Lauf selbst neu (GitHub erlaubt höchstens 6 Stunden pro Lauf).

Im Bot (nur für freigeschaltete Chat-IDs):

**Freie Nachrichten** versteht Claude Haiku 5.5 (`ki.py`, Secret `ANTHROPIC_API_KEY`). Claude hat Werkzeuge zum
Suchen von Spielen, Erstellen von Spiel- und allgemeinen Stories und Ändern bestehender Stories (Texte, Foto,
Titelgröße, neuer KI-Hintergrund nach Wunsch), aber keins zum Posten. Jede Story hat eine Nummer (S12) und wird
mit ihren Bausteinen in `status/stories.json` gemerkt, damit „ändere oben den Text“ auch nach einem Neustart
funktioniert. Ohne Key oder wenn die API nicht erreichbar ist, greifen die festen Muster unten.

Feste Muster und Befehle:
- Mannschaften schreiben, z. B. „Gala Barça“ oder „VfB“: Story für das passende Spiel der nächsten 14 Tage
  (bei mehreren Treffern Auswahl per Knopf). Bei späteren Tagen steht „Samstag live bei uns“ auf der Story.
- Wettbewerb schreiben, z. B. „Champions League“, oder `/ligen`: alle Spiele der nächsten 10 Tage als Knöpfe.
- `/heute`: alle Spiele von heute noch einmal.
- `/allgemein`: allgemeine Stories auf echten Café-Fotos („Wir haben geöffnet“, „Zeit für einen Drink“,
  „Endlich Wochenende“, „Lust zu feiern?“, „Heute Fußball live“ und „Heute <Wettbewerb>“ mit Spieleliste).
  Stichwörter wie „geöffnet“ oder „Cocktails“ funktionieren auch. Texte und Fotos: `allgemein.py`.
- `/text Titel | Untertitel`: Story mit eigenem Text, *Wort* wird hervorgehoben.

Das Repository ist öffentlich, damit die Actions-Minuten nichts kosten. Zugangsdaten liegen nur in den Secrets:
`KIE_AI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS` (kommagetrennt), `INSTAGRAM_TOKEN`,
optional `GH_PAT` (darf Secrets schreiben, falls sich der Instagram-Token beim Verlängern ändert).
Neue Person für die Freigabe: Sie schreibt dem Bot, bekommt ihre Chat-ID zurück, die ID kommt in `TELEGRAM_CHAT_IDS`.

Von Hand starten: GitHub → Actions → Spieltag-Story → „Run workflow“ (`morgen` oder `bot`).

## Lokal testen

```bash
python story.py                 # heute
python story.py 2026-10-17      # bestimmter Tag
python story.py 2026-10-17 --ohne-ki   # Hintergrund aus dem Vorrat (kostet nichts)
python spielplan.py 2026-10-17  # nur anzeigen, welche Spiele eine Story bekämen
```

| Datei | Inhalt |
| --- | --- |
| `config.py` | Welche Wettbewerbe/Spiele (Regeln), deutsche Vereinsnamen, Bild-Prompts |
| `spielplan.py` | Spiele des Tages von der ESPN-API holen und filtern |
| `hintergrund.py` | Hintergrund mit kie.ai (`google/nano-banana`), Fallback auf `hintergruende/` |
| `story.py` | Wappen cachen, Vorlage füllen, mit Chrome headless rendern, Text „Heute/Morgen/Samstag live“ |
| `lauf.py` | Einstieg: `morgen`, `bot`, `freigaben`, `token` |
| `allgemein.py`, `vorlage/allgemein.html`, `assets/fotos/` | Allgemeine Stories |
| `ki.py` | Assistent für freie Nachrichten (Claude Haiku 5.5 mit Werkzeugen) |
| `status/stories.json` | Letzte Stories mit Bausteinen und letzte Dialoge (für Änderungen) |
| `telegram_bot.py` | Freigabe per Telegram (Knöpfe, Bild-Link steckt in der Bildunterschrift) |
| `instagram.py` | Story über graph.instagram.com posten, Token verlängern |
| `status/gepostet.txt` | Bereits gepostete Bilder, damit nichts doppelt rausgeht |
| `vorlage/story.html` | Das Story-Design |

Voraussetzungen lokal: Python 3.12 mit Pillow, Chrome oder Edge, Zugangsdaten als Umgebungsvariablen oder in `.env`.

Hinweise
- Die ESPN-API ist inoffiziell und kostenlos. Wenn sie ausfällt, gibt es an dem Tag keine Stories.
- Name falsch oder englisch? In `NAMEN` in `config.py` ergänzen.
- Spiele mit Anstoß vor 6 Uhr (z. B. WM in Amerika) bekommen ihre Story schon am Vortag, mit „Heute Nacht live bei uns“.
