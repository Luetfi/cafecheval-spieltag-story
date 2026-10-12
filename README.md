# Spieltag-Stories für @cafechevallb

Erzeugt am Morgen eines Spieltags pro gezeigtem Spiel eine Instagram-Story (1080 × 1920 JPEG):
KI-Hintergrund von kie.ai, darüber Wappen, Wettbewerb, Uhrzeit und Datum im Marken-Design.
Die Stories kommen per Telegram-Bot (@cafecheval_story_bot) zur Freigabe. Erst nach „Posten“
gehen sie über die Instagram API auf @cafechevallb.

## Ablauf (GitHub Actions, `.github/workflows/spieltag-story.yml`)

- **Morgens** (Weckzeiten 5:00, 5:30, 6:00 UTC, der erste gewinnt): `python lauf.py morgen` schickt alle Spiele
  des Tages aus `WETTBEWERBE` als Story, empfohlene zuerst (⭐). Danach läuft derselbe Lauf als Bot weiter.
- **Bot** bis 23 Uhr: bearbeitet „Posten“/„Verwerfen“ sofort und beantwortet Anfragen. Nach 5:40 Stunden
  startet sich der Lauf selbst neu (GitHub erlaubt höchstens 6 Stunden pro Lauf).
- **Montags** 4:30 UTC: `python lauf.py token` verlängert den Instagram-Token.

Im Bot (nur für freigeschaltete Chat-IDs):
- Mannschaften schreiben, z. B. „Gala Barça“ oder „VfB“: Story für das passende Spiel der nächsten 14 Tage
  (bei mehreren Treffern Auswahl per Knopf). Bei späteren Tagen steht „Samstag live bei uns“ auf der Story.
- Wettbewerb schreiben, z. B. „Champions League“, oder `/ligen`: alle Spiele der nächsten 10 Tage als Knöpfe.
- `/heute`: alle Spiele von heute noch einmal.

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
| `telegram_bot.py` | Freigabe per Telegram (Knöpfe, Bild-Link steckt in der Bildunterschrift) |
| `instagram.py` | Story über graph.instagram.com posten, Token verlängern |
| `status/gepostet.txt` | Bereits gepostete Bilder, damit nichts doppelt rausgeht |
| `vorlage/story.html` | Das Story-Design |

Voraussetzungen lokal: Python 3.12 mit Pillow, Chrome oder Edge, Zugangsdaten als Umgebungsvariablen oder in `.env`.

Hinweise
- Die ESPN-API ist inoffiziell und kostenlos. Wenn sie ausfällt, gibt es an dem Tag keine Stories.
- Name falsch oder englisch? In `NAMEN` in `config.py` ergänzen.
- Spiele mit Anstoß vor 6 Uhr (z. B. WM in Amerika) bekommen ihre Story schon am Vortag, mit „Heute Nacht live bei uns“.
