"""Einstieg für den Zeitplan (GitHub Actions) und für Tests von Hand.

    python lauf.py morgen [JJJJ-MM-TT]   # alle Spiele des Tages als Story schicken, dann als Bot weiterlaufen
    python lauf.py morgen JJJJ-MM-TT --ohne-bot   # nur erzeugen und schicken
    python lauf.py bot                   # Bot: Knöpfe und Spiel-Anfragen live bearbeiten
    python lauf.py freigaben             # einmal Knopfdrücke abholen (ohne Warten)
    python lauf.py token                 # Instagram-Token verlängern (läuft wöchentlich)

Der Bot läuft von morgens bis 23 Uhr. Weil GitHub einen Lauf nach 6 Stunden beendet, hört jeder Lauf
nach knapp 5¾ Stunden auf und legt die Datei `status/weiter` an. Der Workflow startet dann den nächsten Lauf.

Spiel anfordern: dem Bot den Namen schreiben, z. B. „Gala Barça“ oder „VfB“. Er sucht in den nächsten
14 Tagen, erstellt die Story sofort (bei späteren Tagen mit „Samstag live bei uns“) und schickt sie zur Freigabe.

`status/gepostet.txt` merkt sich bereits gepostete Bilder, damit nichts doppelt rausgeht.
`status/morgen.txt` merkt sich den letzten Morgen-Lauf, damit mehrere Weckzeiten nichts doppelt schicken.
"""
import datetime as dt
import html
import pathlib
import sys
import time
import traceback

import instagram
import spielplan
import telegram_bot
import umgebung

HIER = pathlib.Path(__file__).resolve().parent
STATUS = HIER / 'status'
GEPOSTET = STATUS / 'gepostet.txt'
MORGEN = STATUS / 'morgen.txt'
WEITER = STATUS / 'weiter'
KURZ = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
LAUFZEIT = dt.timedelta(hours=5, minutes=40)   # GitHub bricht Läufe nach 6 Stunden ab
FEIERABEND = dt.time(23, 0)                     # danach hört der Bot bis zum nächsten Morgen auf
MAX_TREFFER = 8
MAX_LISTE = 60          # Telegram erlaubt höchstens 100 Knöpfe pro Nachricht
LISTE_TAGE = 10

HILFE = ('<b>Story für ein bestimmtes Spiel:</b> Schreib mir die Mannschaften, z. B. <i>Gala Barça</i>, '
         '<i>VfB</i> oder <i>England Spanien</i>. Ich suche in den nächsten 14 Tagen.\n\n'
         '<b>Alle Spiele eines Wettbewerbs:</b> Schreib z. B. <i>Champions League</i>, <i>Bundesliga</i>, '
         '<i>Premier League</i> oder <i>WM</i>, oder tippe /ligen für die Auswahl.\n\n'
         '/heute schickt alle Spiele von heute noch einmal.')


def jetzt():
    return dt.datetime.now(spielplan.BERLIN)


def lade_gepostet():
    return set(GEPOSTET.read_text(encoding='utf-8').split()) if GEPOSTET.exists() else set()


def speichere_gepostet(gepostet):
    STATUS.mkdir(exist_ok=True)
    GEPOSTET.write_text('\n'.join(sorted(gepostet)[-300:]) + '\n', encoding='utf-8')


class Bot:
    def __init__(self):
        self.gepostet = lade_gepostet()
        self.kopien = {}          # Bild-URL -> alle Telegram-Nachrichten mit dieser Story
        self.hintergruende = {}   # (Spieltag, Wettbewerb) -> gemeinsamer KI-Hintergrund

    # Stories erzeugen und schicken

    def story(self, s, chats=None):
        import hintergrund  # erst hier laden: braucht Pillow und Chrome
        import story
        r = story.story_bauen(s, jetzt().date(), hintergruende=self.hintergruende)
        url = hintergrund.hochladen(r['datei'], ordner=f"cafecheval-stories/{s['tag'].isoformat()}")
        a = s['anstoss']
        details = ' · '.join(filter(None, [s['wettbewerb'], s['runde'], s['leg'],
                                           f'{KURZ[a.weekday()]} {a:%d.%m.} {a:%H:%M} Uhr']))
        titel = f"{s['heim']['name']} – {s['gast']['name']}"
        self.kopien[url] = telegram_bot.story_senden(url, titel, details, s.get('empfohlen', False), chats)
        print('an Telegram geschickt:', r['datei'].name)

    def tagesstories(self, tag, chats=None):
        spiele = spielplan.spiele(tag)
        for s in spiele:
            self.story(s, chats)
        return len(spiele)

    # Eingänge bearbeiten

    def abschliessen(self, msg, url, vermerk):
        telegram_bot.abschliessen(msg, vermerk)
        for k in self.kopien.get(url, []):
            if (k['chat']['id'], k['message_id']) != (msg['chat']['id'], msg['message_id']):
                telegram_bot.abschliessen(k, vermerk)

    def posten(self, e):
        msg, url = e['nachricht'], telegram_bot.bild_url(e['nachricht'])
        if not url:
            return
        if url in self.gepostet:
            telegram_bot.antworten(e['query_id'], 'Ist schon gepostet')
            self.abschliessen(msg, url, '✅ Bereits gepostet')
            return
        telegram_bot.antworten(e['query_id'], 'Wird gepostet …')
        try:
            instagram.story_posten(url)
        except Exception as fehler:
            # Knöpfe bleiben stehen, man kann es später noch einmal versuchen.
            telegram_bot.text(f'⚠️ Posten fehlgeschlagen: {html.escape(str(fehler))}', chat=e['chat'])
            return
        self.gepostet.add(url)
        speichere_gepostet(self.gepostet)
        self.abschliessen(msg, url, f"✅ Gepostet von {e['von']} um {jetzt():%H:%M} Uhr")
        print('gepostet:', url)

    def verwerfen(self, e):
        url = telegram_bot.bild_url(e['nachricht'])
        telegram_bot.antworten(e['query_id'], 'Verworfen')
        self.abschliessen(e['nachricht'], url, f"❌ Verworfen von {e['von']}")

    def anfrage(self, e):
        text = e['text'].strip()
        befehl = text.split()[0].lower().split('@')[0] if text else ''
        if befehl in ('/start', '/hilfe', '/help'):
            telegram_bot.text(HILFE, chat=e['chat'])
            return
        if befehl == '/heute':
            telegram_bot.text('⏳ Ich erstelle die Stories für heute …', chat=e['chat'])
            if not self.tagesstories(jetzt().date(), [e['chat']]):
                telegram_bot.text('Heute laufen keine Spiele aus unseren Wettbewerben.', chat=e['chat'])
            return
        if befehl == '/ligen':
            telegram_bot.ligen_senden(e['chat'], spielplan.ligen())
            return
        slug = spielplan.liga_erkennen(text)
        if slug:
            self.liste(slug, e['chat'])
            return
        treffer = spielplan.suchen(text, jetzt().date())
        if not treffer:
            telegram_bot.text(f'Ich habe in den nächsten 14 Tagen kein Spiel zu „{html.escape(text)}“ gefunden. '
                              'Versuch es mit dem Vereinsnamen, z. B. <i>Bayern</i> oder <i>Galatasaray</i>.', chat=e['chat'])
        elif len(treffer) == 1:
            self.erstellen(treffer[0], e['chat'])
        else:
            telegram_bot.auswahl_senden(e['chat'], treffer[:MAX_TREFFER])

    def liste(self, slug, chat):
        name = next((t for t, s in spielplan.ligen() if s == slug), slug)
        spiele = spielplan.spiele_im_wettbewerb(slug, jetzt().date(), LISTE_TAGE)
        if not spiele:
            telegram_bot.text(f'{html.escape(name)}: In den nächsten {LISTE_TAGE} Tagen sind keine Spiele angesetzt.', chat=chat)
            return
        mehr = f' (die ersten {MAX_LISTE})' if len(spiele) > MAX_LISTE else ''
        telegram_bot.auswahl_senden(chat, spiele[:MAX_LISTE],
                                    f'<b>{html.escape(name)}</b>: Spiele der nächsten {LISTE_TAGE} Tage{mehr}. '
                                    'Tippe auf ein Spiel, dann erstelle ich die Story.')

    def liga(self, e):
        telegram_bot.antworten(e['query_id'], 'Einen Moment …')
        self.liste(e['daten'].split('|', 1)[1], e['chat'])

    def auswahl(self, e):
        _, slug, datum, event_id = e['daten'].split('|')
        telegram_bot.antworten(e['query_id'], 'Einen Moment …')
        telegram_bot.knoepfe_entfernen(e['nachricht'])
        s = spielplan.finden(slug, datum, event_id)
        if s:
            self.erstellen(s, e['chat'])
        else:
            telegram_bot.text('Das Spiel habe ich nicht mehr gefunden (schon angepfiffen?).', chat=e['chat'])

    def erstellen(self, s, chat):
        telegram_bot.text(f"⏳ Ich erstelle die Story für <b>{html.escape(s['heim']['name'])} – "
                          f"{html.escape(s['gast']['name'])}</b> …", chat=chat)
        self.story(s, [chat])

    def bearbeiten(self, e):
        try:
            {'posten': self.posten, 'verwerfen': self.verwerfen, 'spiel': self.auswahl,
             'liga': self.liga, 'text': self.anfrage}.get(e['aktion'], lambda _: None)(e)
        except Exception as fehler:
            traceback.print_exc()
            telegram_bot.text(f'⚠️ Das hat nicht geklappt: {html.escape(str(fehler))}', chat=e['chat'])

    def laufen(self, bis):
        print(f'Bot läuft bis {bis:%H:%M} Uhr')
        while jetzt() < bis:
            try:
                liste, bestaetigen = telegram_bot.entscheidungen(warten=(bis - jetzt()).total_seconds())
            except Exception as fehler:  # z. B. Netzwerk weg: kurz warten, weitermachen
                print('Warnung:', fehler)
                time.sleep(30)
                continue
            bestaetigen()  # sofort bestätigen, damit ein Fehler unten nicht zu Endlosschleifen führt
            for e in liste:
                self.bearbeiten(e)
        speichere_gepostet(self.gepostet)


def ende_des_laufs(start):
    """Ende dieses Laufs: spätestens nach LAUFZEIT, spätestens um FEIERABEND."""
    feierabend = dt.datetime.combine(start.date(), FEIERABEND, spielplan.BERLIN)
    return min(start + LAUFZEIT, feierabend)


def bot(start):
    ende = ende_des_laufs(start)
    if ende <= jetzt():
        print('Feierabend, der Bot startet morgen früh wieder')
        return
    Bot().laufen(ende)
    if ende < dt.datetime.combine(start.date(), FEIERABEND, spielplan.BERLIN):
        WEITER.write_text('bot', encoding='utf-8')  # der Workflow startet den nächsten Lauf


def morgen(tag, start, als_bot=True):
    if MORGEN.exists() and MORGEN.read_text(encoding='utf-8').strip() == tag.isoformat():
        print(f'Stories für {tag} wurden schon geschickt')
        return  # ein früherer Weckruf hat das schon erledigt und läuft als Bot
    b = Bot()
    anzahl = b.tagesstories(tag)
    STATUS.mkdir(exist_ok=True)
    MORGEN.write_text(tag.isoformat(), encoding='utf-8')
    print(f'{anzahl} Stories für {tag} geschickt')
    if als_bot:
        ende = ende_des_laufs(start)
        b.laufen(ende)
        if ende < dt.datetime.combine(start.date(), FEIERABEND, spielplan.BERLIN):
            WEITER.write_text('bot', encoding='utf-8')


def freigaben():
    b = Bot()
    liste, bestaetigen = telegram_bot.entscheidungen()
    bestaetigen()
    for e in liste:
        b.bearbeiten(e)
    speichere_gepostet(b.gepostet)


def token():
    """Verlängert den Instagram-Token. Ändert er sich, landet er in `status/neuer_token` (nicht im Repo),
    und der Workflow trägt ihn als Secret ein."""
    if not umgebung.wert('INSTAGRAM_TOKEN', pflicht=False):
        print('Kein INSTAGRAM_TOKEN, nichts zu tun')
        return
    neu, tage = instagram.token_verlaengern()
    print(f'Instagram-Token gültig für {tage} Tage')
    if neu != umgebung.wert('INSTAGRAM_TOKEN'):
        STATUS.mkdir(exist_ok=True)
        (STATUS / 'neuer_token').write_text(neu, encoding='utf-8')


if __name__ == '__main__':
    befehl = sys.argv[1] if len(sys.argv) > 1 else ''
    start = jetzt()
    try:
        if befehl == 'morgen':
            args = [a for a in sys.argv[2:] if not a.startswith('--')]
            tag = dt.date.fromisoformat(args[0]) if args else start.date()
            morgen(tag, start, als_bot='--ohne-bot' not in sys.argv)
        elif befehl == 'bot':
            bot(start)
        elif befehl == 'freigaben':
            freigaben()
        elif befehl == 'token':
            token()
        else:
            raise SystemExit(__doc__)
    except Exception as fehler:
        traceback.print_exc()
        try:
            telegram_bot.text(f'⚠️ Spieltag-Story ({befehl}) fehlgeschlagen: {html.escape(str(fehler))}')
        except Exception:
            pass
        sys.exit(1)
