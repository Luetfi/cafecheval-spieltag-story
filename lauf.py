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
import json
import pathlib
import random
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
STORIES = STATUS / 'stories.json'   # Bausteine der letzten Stories, damit sie sich ändern lassen
MAX_STORIES = 40
MAX_VERLAUF = 6                      # so viele letzte Dialoge pro Chat bekommt der Assistent als Kontext
KURZ = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
LAUFZEIT = dt.timedelta(hours=5, minutes=40)   # GitHub bricht Läufe nach 6 Stunden ab
FEIERABEND = dt.time(23, 0)                     # danach hört der Bot bis zum nächsten Morgen auf
MAX_TREFFER = 8
MAX_LISTE = 60          # Telegram erlaubt höchstens 100 Knöpfe pro Nachricht
LISTE_TAGE = 10

HILFE = ('Schreib mir einfach, was du brauchst, ganz normal, zum Beispiel:\n'
         '• <i>Mach eine Story für Gala gegen Barça</i>\n'
         '• <i>Welche Bundesliga-Spiele laufen am Samstag?</i>\n'
         '• <i>Story, dass wir heute geöffnet haben, mit Cocktail-Foto</i>\n'
         '• <i>Ändere oben den Text zu „Heute Abend bei uns“</i> (oder antworte direkt auf eine Story)\n'
         '• <i>Anderer Hintergrund, mehr Flutlicht und Regen</i>\n\n'
         'Gepostet wird nur, wenn du bei einer Story auf <b>Posten</b> tippst.\n\n'
         'Feste Befehle: /ligen (Spiele eines Wettbewerbs), /allgemein (Vorlagen), /heute (alle Spiele von heute), '
         '<code>/text Titel | Untertitel</code> (eigener Text).')


TEXT_HILFE = ('Schick mir den Text so: <code>/text Titel | Untertitel</code>\n'
              'Beispiel: <code>/text Poker-*Abend* | Heute ab *20 Uhr*, Anmeldung am Tresen</code>\n'
              '*Wort* wird hervorgehoben, der Untertitel ist optional.')


def jetzt():
    return dt.datetime.now(spielplan.BERLIN)


def lade_gepostet():
    return set(GEPOSTET.read_text(encoding='utf-8').split()) if GEPOSTET.exists() else set()


def speichere_gepostet(gepostet):
    STATUS.mkdir(exist_ok=True)
    GEPOSTET.write_text('\n'.join(sorted(gepostet)[-300:]) + '\n', encoding='utf-8')


class Bot:
    """Der Telegram-Bot. Jede verschickte Story bekommt eine Nummer (S1, S2 …) und wird mit allen Bausteinen
    in status/stories.json gemerkt, damit sie sich später ändern lässt, auch nach einem Neustart."""

    def __init__(self):
        self.gepostet = lade_gepostet()
        self.hintergruende = {}   # (Spieltag, Wettbewerb) -> gemeinsamer KI-Hintergrund
        gespeichert = json.loads(STORIES.read_text(encoding='utf-8')) if STORIES.exists() else {}
        self.stories = gespeichert.get('stories', {})
        self.nr = gespeichert.get('nr', 0)
        self.verlauf = {int(k): v for k, v in gespeichert.get('verlauf', {}).items()}  # Chat -> letzte Dialoge
        self._assistent = None

    def speichern(self):
        STATUS.mkdir(exist_ok=True)
        neueste = dict(sorted(self.stories.items(), key=lambda kv: kv[1]['erstellt'])[-MAX_STORIES:])
        self.stories = neueste
        STORIES.write_text(json.dumps({'nr': self.nr, 'stories': neueste,
                                       'verlauf': {str(k): v[-MAX_VERLAUF:] for k, v in self.verlauf.items()}},
                                      ensure_ascii=False, indent=1), encoding='utf-8')

    # Stories erzeugen, merken und schicken

    def senden(self, art, daten, vorlage, titel, details, chats=None, empfohlen=False, logos=None, datei=None,
               tag=None, wettbewerb=''):
        """Rendert (falls nötig), lädt hoch, schickt mit Knöpfen und merkt sich die Story. Gibt die Nummer zurück."""
        import hintergrund
        import story
        tag = tag or jetzt().date()
        if datei is None:
            ziel = story.AUSGABE / tag.isoformat() / 'aenderung' / f'{self.nr + 1}-{dt.datetime.now():%H%M%S}.jpg'
            datei = story.rendern(daten, ziel, story.HIER / 'vorlage' / f'{vorlage}.html')
        url = hintergrund.hochladen(datei, ordner=f'cafecheval-stories/{tag.isoformat()}')
        self.nr += 1
        sid = f'S{self.nr}'
        nachrichten = telegram_bot.story_senden(url, titel, f'{details} · {sid}', empfohlen, chats)
        self.stories[sid] = {
            'id': sid, 'art': art, 'vorlage': vorlage, 'titel': titel, 'details': details, 'url': url,
            'daten': daten, 'logos': logos or {}, 'tag': tag.isoformat(), 'wettbewerb': wettbewerb,
            'status': 'offen', 'erstellt': jetzt().isoformat(),
            'nachrichten': [{k: m.get(k) for k in ('message_id', 'chat', 'caption', 'caption_entities')}
                            for m in nachrichten],
        }
        self.speichern()
        print('an Telegram geschickt:', sid, titel)
        return sid

    def story(self, s, chats=None, wunsch=None, kicker_text=None):
        import story
        r = story.story_bauen(s, jetzt().date(), hintergruende=self.hintergruende, wunsch=wunsch,
                              kicker_text=kicker_text)
        a = s['anstoss']
        details = ' · '.join(filter(None, [s['wettbewerb'], s['runde'], s['leg'],
                                           f'{KURZ[a.weekday()]} {a:%d.%m.} {a:%H:%M} Uhr']))
        logos = {s[k]['id']: s[k].get('logo') for k in ('heim', 'gast')}
        return self.senden('spiel', r['daten'], 'story', f"{s['heim']['name']} – {s['gast']['name']}", details,
                           chats, s.get('empfohlen', False), logos, r['datei'], s['tag'], s['wettbewerb'])

    def tagesstories(self, tag, chats=None):
        spiele = spielplan.spiele(tag)
        for s in spiele:
            self.story(s, chats)
        return len(spiele)

    def allgemeine_story(self, schluessel, chat, text=None):
        """Gibt die Story-Nummer zurück. ValueError, wenn es die Vorlage gerade nicht gibt (z. B. keine Spiele)."""
        import allgemein
        heute = jetzt().date()
        datei, beschreibung, daten, logos = allgemein.bauen(schluessel, heute, text)
        return self.senden('allgemein', daten, 'allgemein', beschreibung, 'Allgemeine Story', [chat], logos=logos,
                           datei=datei, tag=heute)

    def aendern(self, sid, chat, felder=None, foto=None, neuer_hintergrund=False, wunsch=None):
        """Neue Version einer Story mit geänderten Bausteinen. Die alte Version wird als ersetzt markiert.
        `felder`: z. B. {'kicker': …, 'titel': …}. Gibt die neue Nummer zurück."""
        import allgemein
        import hintergrund
        import story
        alt = self.stories.get(sid)
        if not alt:
            raise ValueError(f'Story {sid} kenne ich nicht (mehr)')
        daten = json.loads(json.dumps(alt['daten']))
        for feld, wert in (felder or {}).items():
            if feld in ('heim', 'gast'):
                daten[feld]['name'] = wert
            elif feld == 'runde':
                daten['runde'], daten['leg'] = wert, ''
            else:
                daten[feld] = wert
        if foto:
            daten['hintergrund'], daten['weich'] = allgemein.foto(foto)
        if neuer_hintergrund or wunsch:
            tag = dt.date.fromisoformat(alt['tag'])
            ziel = story.AUSGABE / tag.isoformat() / 'hintergrund' / f'{sid}-neu-{dt.datetime.now():%H%M%S}.png'
            bg = hintergrund.hintergrund({'wettbewerb': alt.get('wettbewerb') or 'football'}, ziel,
                                         nr=random.randint(0, 99), wunsch=wunsch)
            if bg:
                daten['hintergrund'] = bg.as_uri()
                if alt['vorlage'] == 'allgemein':
                    daten['weich'] = True
        daten = story.pfade_reparieren(daten, alt['logos'])
        titel = alt['titel']
        if alt['vorlage'] == 'story' and ('heim' in (felder or {}) or 'gast' in (felder or {})):
            titel = f"{daten['heim']['name']} – {daten['gast']['name']}"
        elif alt['vorlage'] == 'allgemein' and 'titel' in (felder or {}):
            titel = str(daten['titel']).replace('*', '').replace('|', ' ')
        neu = self.senden(alt['art'], daten, alt['vorlage'], titel, alt['details'], [chat], logos=alt['logos'],
                          tag=dt.date.fromisoformat(alt['tag']), wettbewerb=alt.get('wettbewerb', ''))
        if alt['status'] == 'offen':
            alt['status'] = 'ersetzt'
            for m in alt['nachrichten']:
                telegram_bot.abschliessen(m, f'↪️ Ersetzt durch {neu}')
        self.speichern()
        return neu

    # Eingänge bearbeiten

    def story_zu_url(self, url):
        return next((s for s in self.stories.values() if s['url'] == url), None)

    def abschliessen(self, msg, url, vermerk, status):
        telegram_bot.abschliessen(msg, vermerk)
        eintrag = self.story_zu_url(url)
        if eintrag:
            eintrag['status'] = status
            for m in eintrag['nachrichten']:
                if (m['chat']['id'], m['message_id']) != (msg['chat']['id'], msg['message_id']):
                    telegram_bot.abschliessen(m, vermerk)
            self.speichern()

    def posten(self, e):
        msg, url = e['nachricht'], telegram_bot.bild_url(e['nachricht'])
        if not url:
            return
        if url in self.gepostet:
            telegram_bot.antworten(e['query_id'], 'Ist schon gepostet')
            self.abschliessen(msg, url, '✅ Bereits gepostet', 'gepostet')
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
        self.abschliessen(msg, url, f"✅ Gepostet von {e['von']} um {jetzt():%H:%M} Uhr", 'gepostet')
        print('gepostet:', url)

    def verwerfen(self, e):
        url = telegram_bot.bild_url(e['nachricht'])
        telegram_bot.antworten(e['query_id'], 'Verworfen')
        self.abschliessen(e['nachricht'], url, f"❌ Verworfen von {e['von']}", 'verworfen')

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
        if befehl == '/allgemein':
            import allgemein
            heute = jetzt().date()
            telegram_bot.vorlagen_senden(e['chat'], allgemein.knoepfe(heute, spielplan.spiele(heute)))
            return
        if befehl == '/text':
            eigener = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ''
            if not eigener:
                telegram_bot.text(TEXT_HILFE, chat=e['chat'])
                return
            self.allgemein_erstellen('eigen', e['chat'], eigener)
            return
        if befehl == '/ligen':
            telegram_bot.ligen_senden(e['chat'], spielplan.ligen())
            return
        if umgebung.wert('ANTHROPIC_API_KEY', pflicht=False):
            self.assistent().antworten(e)  # freie Nachricht: Claude versteht und handelt
            return
        self.suche_ohne_ki(text, e['chat'])

    def assistent(self):
        if self._assistent is None:
            import ki
            self._assistent = ki.Assistent(self)
        return self._assistent

    def suche_ohne_ki(self, text, chat):
        """Feste Muster, falls kein ANTHROPIC_API_KEY gesetzt ist."""
        slug = spielplan.liga_erkennen(text)
        if slug:
            self.liste(slug, chat)
            return
        import allgemein
        vorlage = allgemein.stichwort(text)
        if vorlage:
            self.allgemein_erstellen(vorlage, chat)
            return
        treffer = spielplan.suchen(text, jetzt().date())
        if not treffer:
            telegram_bot.text(f'Ich habe in den nächsten 14 Tagen kein Spiel zu „{html.escape(text)}“ gefunden. '
                              'Versuch es mit dem Vereinsnamen, z. B. <i>Bayern</i> oder <i>Galatasaray</i>.', chat=chat)
        elif len(treffer) == 1:
            self.erstellen(treffer[0], chat)
        else:
            telegram_bot.auswahl_senden(chat, treffer[:MAX_TREFFER])

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

    def allgemein_erstellen(self, schluessel, chat, text=None):
        telegram_bot.text('⏳ Ich erstelle die Story …', chat=chat)
        try:
            self.allgemeine_story(schluessel, chat, text)
        except ValueError as fehler:
            telegram_bot.text(f'Das geht gerade nicht: {html.escape(str(fehler))}.', chat=chat)

    def allgemein(self, e):
        schluessel = e['daten'].split('|', 1)[1]
        telegram_bot.antworten(e['query_id'], 'Einen Moment …')
        if schluessel == 'eigen':
            telegram_bot.text(TEXT_HILFE, chat=e['chat'])
            return
        self.allgemein_erstellen(schluessel, e['chat'])

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
             'liga': self.liga, 'allgemein': self.allgemein, 'text': self.anfrage}.get(e['aktion'], lambda _: None)(e)
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
        self.speichern()


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
