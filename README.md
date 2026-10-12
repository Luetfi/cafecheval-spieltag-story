# Spieltag-Stories für @cafechevallb

Erzeugt am Morgen eines Spieltags pro gezeigtem Spiel eine Instagram-Story (1080 × 1920 JPEG):
KI-Hintergrund von kie.ai, darüber Wappen, Wettbewerb, Uhrzeit und Datum im Marken-Design.
Die Stories kommen per Telegram-Bot (@cafecheval_story_bot) zur Freigabe. Erst nach „Posten“
gehen sie über die Instagram API auf @cafechevallb.

## Ablauf (GitHub Actions, `.github/workflows/spieltag-story.yml`)

| Wann (UTC) | Befehl | Was passiert |
| --- | --- | --- |
| täglich 6:00 | `python lauf.py morgen` | Stories erzeugen, Bild zu kie.ai hochladen (öffentliche URL), an Telegram schicken, dann live auf die Knöpfe warten (bis alle entschieden sind, höchstens bis 14 Uhr bzw. erstem Anstoß) |
| 6–20 Uhr alle 20 Min. | `python lauf.py freigaben` | Reserve für spätere Klicks (GitHub startet geplante Läufe oft verspätet) |
| montags 5:30 | `python lauf.py token` | Instagram-Token verlängern |

Das Repository ist öffentlich, damit die Actions-Minuten fürs Warten nichts kosten. Zugangsdaten liegen nur in den Secrets.

Von Hand starten: GitHub → Actions → Spieltag-Story → „Run workflow“.

Secrets: `KIE_AI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS` (kommagetrennt), `INSTAGRAM_TOKEN`,
optional `GH_PAT` (darf Secrets schreiben, falls sich der Instagram-Token beim Verlängern ändert).
Neue Person für die Freigabe: Sie schreibt dem Bot, bekommt ihre Chat-ID zurück, die ID kommt in `TELEGRAM_CHAT_IDS`.

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
| `story.py` | Wappen cachen, Vorlage füllen, mit Chrome headless rendern |
| `lauf.py` | Einstieg für den Zeitplan: `morgen`, `freigaben`, `token` |
| `telegram_bot.py` | Freigabe per Telegram (Knöpfe, Bild-Link steckt in der Bildunterschrift) |
| `instagram.py` | Story über graph.instagram.com posten, Token verlängern |
| `status/gepostet.txt` | Bereits gepostete Bilder, damit nichts doppelt rausgeht |
| `vorlage/story.html` | Das Story-Design |

Voraussetzungen lokal: Python 3.12 mit Pillow, Chrome oder Edge, Zugangsdaten als Umgebungsvariablen oder in `.env`.

Hinweise
- Die ESPN-API ist inoffiziell und kostenlos. Wenn sie ausfällt, gibt es an dem Tag keine Stories.
- Name falsch oder englisch? In `NAMEN` in `config.py` ergänzen.
- Spiele mit Anstoß vor 6 Uhr (z. B. WM in Amerika) bekommen ihre Story schon am Vortag, mit „Heute Nacht live bei uns“.
