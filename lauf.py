"""Einstieg für den Zeitplan (GitHub Actions) und für Tests von Hand.

    python lauf.py morgen [JJJJ-MM-TT]   # Stories erzeugen, hochladen, zur Freigabe an Telegram schicken
    python lauf.py freigaben             # Knopfdrücke abholen, freigegebene Stories auf Instagram posten
    python lauf.py token                 # Instagram-Token verlängern (läuft wöchentlich)

`status/gepostet.txt` merkt sich bereits gepostete Bilder. Haben mehrere Personen die Nachricht,
wird eine Story trotzdem nur einmal gepostet. GitHub Actions committet die Datei nach jedem Lauf.
"""
import datetime as dt
import pathlib
import sys
import traceback

import instagram
import spielplan
import telegram_bot
import umgebung

HIER = pathlib.Path(__file__).resolve().parent
GEPOSTET = HIER / 'status' / 'gepostet.txt'
KURZ = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']


def jetzt():
    return dt.datetime.now(spielplan.BERLIN)


def morgen(tag):
    import hintergrund  # erst hier laden: braucht Pillow und Chrome, die Freigabe-Läufe nicht
    import story
    for s in story.stories(tag):
        url = hintergrund.hochladen(s['datei'], ordner=f'cafecheval-stories/{tag.isoformat()}')
        a = s['anstoss']
        details = ' · '.join(filter(None, [s['wettbewerb'], s['runde'], s['leg'],
                                           f'{KURZ[a.weekday()]} {a:%d.%m.} {a:%H:%M} Uhr']))
        telegram_bot.story_senden(url, f"{s['heim']['name']} – {s['gast']['name']}", details)
        print('an Telegram geschickt:', s['datei'].name)


def freigaben():
    gepostet = set(GEPOSTET.read_text(encoding='utf-8').split()) if GEPOSTET.exists() else set()
    liste, bestaetigen = telegram_bot.entscheidungen()
    for e in liste:
        msg, url = e['nachricht'], telegram_bot.bild_url(e['nachricht'])
        if e['aktion'] == telegram_bot.VERWERFEN:
            telegram_bot.antworten(e['query_id'], 'Verworfen')
            telegram_bot.abschliessen(msg, f"❌ Verworfen von {e['von']}")
        elif e['aktion'] == telegram_bot.POSTEN and url:
            if url in gepostet:
                telegram_bot.antworten(e['query_id'], 'Ist schon gepostet')
                telegram_bot.abschliessen(msg, '✅ Bereits gepostet')
                continue
            try:
                instagram.story_posten(url)
            except Exception as fehler:
                # Knöpfe bleiben stehen, man kann es später noch einmal versuchen.
                telegram_bot.antworten(e['query_id'], 'Posten fehlgeschlagen')
                telegram_bot.text(f'⚠️ Posten fehlgeschlagen: {fehler}', chat=msg['chat']['id'])
                continue
            gepostet.add(url)
            telegram_bot.antworten(e['query_id'], 'Gepostet')
            telegram_bot.abschliessen(msg, f"✅ Gepostet von {e['von']} um {jetzt():%H:%M} Uhr")
            print('gepostet:', url)
    GEPOSTET.parent.mkdir(exist_ok=True)
    GEPOSTET.write_text('\n'.join(sorted(gepostet)[-300:]) + '\n', encoding='utf-8')
    bestaetigen()


def token():
    """Verlängert den Instagram-Token. Ändert er sich, landet er in `status/neuer_token` (nicht im Repo),
    und der Workflow trägt ihn als Secret ein."""
    if not umgebung.wert('INSTAGRAM_TOKEN', pflicht=False):
        print('Kein INSTAGRAM_TOKEN, nichts zu tun')
        return
    neu, tage = instagram.token_verlaengern()
    print(f'Instagram-Token gültig für {tage} Tage')
    if neu != umgebung.wert('INSTAGRAM_TOKEN'):
        (HIER / 'status').mkdir(exist_ok=True)
        (HIER / 'status' / 'neuer_token').write_text(neu, encoding='utf-8')


if __name__ == '__main__':
    befehl = sys.argv[1] if len(sys.argv) > 1 else ''
    try:
        if befehl == 'morgen':
            tag = dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else jetzt().date()
            morgen(tag)
        elif befehl == 'freigaben':
            freigaben()
        elif befehl == 'token':
            token()
        else:
            raise SystemExit(__doc__)
    except Exception as fehler:
        traceback.print_exc()
        try:
            telegram_bot.text(f'⚠️ Spieltag-Story ({befehl}) fehlgeschlagen: {fehler}')
        except Exception:
            pass
        sys.exit(1)
