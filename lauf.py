"""Einstieg für den Zeitplan (GitHub Actions) und für Tests von Hand.

    python lauf.py morgen [JJJJ-MM-TT]   # Stories erzeugen, an Telegram schicken, dann live auf Klicks warten
    python lauf.py morgen JJJJ-MM-TT --ohne-warten   # nur erzeugen und schicken
    python lauf.py freigaben             # Knopfdrücke abholen, freigegebene Stories auf Instagram posten
    python lauf.py token                 # Instagram-Token verlängern (läuft wöchentlich)

Nach dem Verschicken wartet `morgen` live auf die Knöpfe, bis jede Story entschieden ist, höchstens bis
14 Uhr bzw. bis zum ersten Anstoß. Spätere Klicks holt der Zeitplan mit `freigaben` ab.

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
    """Erzeugt und verschickt die Stories. Gibt ({Bild-URL: [Telegram-Nachrichten]}, erster Anstoß) zurück."""
    import hintergrund  # erst hier laden: braucht Pillow und Chrome, die Freigabe-Läufe nicht
    import story
    kopien, erster = {}, None
    for s in story.stories(tag):
        url = hintergrund.hochladen(s['datei'], ordner=f'cafecheval-stories/{tag.isoformat()}')
        a = s['anstoss']
        details = ' · '.join(filter(None, [s['wettbewerb'], s['runde'], s['leg'],
                                           f'{KURZ[a.weekday()]} {a:%d.%m.} {a:%H:%M} Uhr']))
        kopien[url] = telegram_bot.story_senden(url, f"{s['heim']['name']} – {s['gast']['name']}", details)
        erster = min(erster or a, a)
        print('an Telegram geschickt:', s['datei'].name)
    return kopien, erster


def lade_gepostet():
    return set(GEPOSTET.read_text(encoding='utf-8').split()) if GEPOSTET.exists() else set()


def speichere_gepostet(gepostet):
    GEPOSTET.parent.mkdir(exist_ok=True)
    GEPOSTET.write_text('\n'.join(sorted(gepostet)[-300:]) + '\n', encoding='utf-8')


def verarbeiten(liste, gepostet, kopien=None):
    """Führt die Knopfdrücke aus. Gibt die Bild-URLs zurück, über die jetzt entschieden ist.
    `kopien`: gleiche Story bei anderen Empfängern, deren Knöpfe ebenfalls entfernt werden."""
    entschieden = set()

    def abschliessen(msg, url, vermerk):
        telegram_bot.abschliessen(msg, vermerk)
        for k in (kopien or {}).get(url, []):
            if (k['chat']['id'], k['message_id']) != (msg['chat']['id'], msg['message_id']):
                telegram_bot.abschliessen(k, vermerk)

    for e in liste:
        msg, url = e['nachricht'], telegram_bot.bild_url(e['nachricht'])
        if not url:
            continue
        if e['aktion'] == telegram_bot.VERWERFEN:
            telegram_bot.antworten(e['query_id'], 'Verworfen')
            abschliessen(msg, url, f"❌ Verworfen von {e['von']}")
            entschieden.add(url)
        elif e['aktion'] == telegram_bot.POSTEN:
            if url in gepostet:
                telegram_bot.antworten(e['query_id'], 'Ist schon gepostet')
                abschliessen(msg, url, '✅ Bereits gepostet')
                entschieden.add(url)
                continue
            telegram_bot.antworten(e['query_id'], 'Wird gepostet …')
            try:
                instagram.story_posten(url)
            except Exception as fehler:
                # Knöpfe bleiben stehen, man kann es später noch einmal versuchen.
                telegram_bot.text(f'⚠️ Posten fehlgeschlagen: {fehler}', chat=msg['chat']['id'])
                continue
            gepostet.add(url)
            speichere_gepostet(gepostet)
            abschliessen(msg, url, f"✅ Gepostet von {e['von']} um {jetzt():%H:%M} Uhr")
            entschieden.add(url)
            print('gepostet:', url)
    return entschieden


def freigaben():
    gepostet = lade_gepostet()
    liste, bestaetigen = telegram_bot.entscheidungen()
    verarbeiten(liste, gepostet)
    speichere_gepostet(gepostet)
    bestaetigen()


def zuhoeren(kopien, bis):
    """Wartet live auf Knopfdrücke, bis alle Stories entschieden sind oder `bis` erreicht ist."""
    offen = set(kopien)
    gepostet = lade_gepostet()
    print(f'warte auf Freigaben bis {bis:%H:%M} Uhr')
    while offen and jetzt() < bis:
        liste, bestaetigen = telegram_bot.entscheidungen(warten=(bis - jetzt()).total_seconds())
        offen -= verarbeiten(liste, gepostet, kopien)
        bestaetigen()
    speichere_gepostet(gepostet)
    print('alle Stories entschieden' if not offen else f'{len(offen)} Stories noch offen, der Zeitplan übernimmt')


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
            args = [a for a in sys.argv[2:] if not a.startswith('--')]
            tag = dt.date.fromisoformat(args[0]) if args else jetzt().date()
            kopien, erster = morgen(tag)
            if kopien and '--ohne-warten' not in sys.argv:
                bis = min(dt.datetime.combine(jetzt().date(), dt.time(14), spielplan.BERLIN), erster)
                if bis <= jetzt():  # von Hand am Nachmittag gestartet
                    bis = jetzt() + dt.timedelta(minutes=30)
                zuhoeren(kopien, bis)
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
