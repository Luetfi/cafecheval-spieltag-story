"""Assistent für freie Nachrichten an den Bot: Claude Haiku 5.5 versteht den Wunsch und nutzt Werkzeuge.

Claude kann Spiele suchen, Stories erstellen und bestehende Stories ändern, aber nicht posten:
Gepostet wird nur über den Knopf „Posten“ in Telegram.

Jede Nachricht ist eine eigene, kurze Anfrage. Was vorher war (die letzten Stories mit ihren Texten und
die letzten Dialoge), steht als Kontext in der Nachricht. So bleibt jede Anfrage klein und günstig.
"""
import datetime as dt
import html
import json
import re

import anthropic

import allgemein
import spielplan
import telegram_bot
import umgebung

MODELL = 'claude-haiku-5-5'
MAX_RUNDEN = 8   # höchstens so viele Werkzeug-Runden pro Nachricht

SYSTEM = """Du bist der Assistent im Telegram-Bot vom Café Cheval, einer Cocktailbar in Ludwigsburg \
(Asperger Str. 16, täglich ab 14 Uhr, sonntags bis donnerstags bis 3 Uhr, freitags und samstags bis 5 Uhr). \
Im Café laufen Fußballspiele live auf großer Leinwand (Bundesliga auf Sky, dazu Champions League, Pokal, \
Länderspiele und mehr). Es gibt Cocktails und Longdrinks, aber kein Essen und keinen Kaffee.

Deine Aufgabe: Instagram-Stories für das Café erstellen und auf Wunsch ändern. Dafür hast du Werkzeuge. \
Jede Story kommt mit den Knöpfen „Posten“ und „Verwerfen“ in den Chat. Du selbst kannst nicht posten; \
das macht der Mensch mit dem Knopf. Sag das, wenn jemand dich bittet zu posten. Ausnahme: Morgens markiert \
der Bot beliebte Spiele mit 🤖 und einer Uhrzeit, die postet er dann von selbst, außer jemand tippt vorher \
auf „Verwerfen“. Änderst du so eine Story, bleibt die automatische Uhrzeit für die neue Version erhalten.

So arbeitest du:
- Spiele, Termine und Uhrzeiten immer über die Werkzeuge suchen, nie raten oder erfinden.
- Bezieht sich eine Nachricht auf eine bestehende Story („die Story“, „die letzte“, „mach das anders“, \
eine Antwort auf eine Story), ändere sie mit story_aendern. Ohne genauere Angabe ist die neueste noch \
offene Story gemeint. Ändere nur, was gewünscht ist.
- Passen bei einer Suche mehrere Spiele und ist nicht klar welches gemeint ist, zeig sie mit \
auswahl_anzeigen als Knöpfe, statt selbst zu wählen. Will der Mensch Spiele sehen („welche Spiele laufen …“), \
zeig sie ebenfalls mit auswahl_anzeigen, dann reicht als Antwort ein kurzer Satz.
- Story-Texte kurz, auf Deutsch, im Ton einer gemütlichen Bar. *Wort* hebt ein Wort hervor, \
im Titel bricht | die Zeile um.
- Keine Inhalte über Dinge, die es im Café nicht gibt (Essen, Kaffee, Angebote, Preise), außer der \
Mensch nennt sie ausdrücklich.
- Einige allgemeine Stories postet der Bot automatisch nach Zeitplan. Sagt der Mensch, dass das Café \
geschlossen ist (Ruhetag, Urlaub, Feiertag), pausiere den Zeitplan für die passenden Tage mit dem Werkzeug \
zeitplan und sag, bis wann.
- Wünsche für einen neuen KI-Hintergrund formulierst du als kurze englische Bildbeschreibung ohne Text, \
Logos oder erkennbare Personen.
- Antworte danach in ein bis zwei kurzen Sätzen auf Deutsch, ohne Formatierung. Nenne die Nummer der \
neuen Story. Ist ein Wunsch unklar, frag kurz nach, statt zu raten. Kannst du etwas nicht \
(zum Beispiel das Layout umbauen), sag das ehrlich."""

FOTO_ARTEN = list(allgemein.FOTO_ARTEN)  # bar, cocktails, fassade, stadion
VORLAGEN = list(allgemein.VORLAGEN) + ['wettbewerb_heute', 'eigen']
WETTBEWERBE = [slug for _, slug in spielplan.ligen()]
WETTBEWERB_TEXT = ', '.join(f'{slug} = {name}' for name, slug in spielplan.ligen())

TOOLS = [
    {
        'name': 'spiele_suchen',
        'description': 'Sucht kommende Spiele nach Mannschaftsnamen (deutsch oder englisch, auch Spitznamen wie '
                       '"Gala", "Barça", "BVB"). Gibt Spiele mit Referenz (ref) zurück, die du für '
                       'spiel_story_erstellen oder auswahl_anzeigen brauchst.',
        'input_schema': {'type': 'object', 'properties': {
            'suchtext': {'type': 'string', 'description': 'Ein oder mehrere Mannschaften, z. B. "Bayern Dortmund"'},
            'tage': {'type': 'integer', 'description': 'Wie viele Tage ab heute (Standard 14, höchstens 21)'},
        }, 'required': ['suchtext']},
    },
    {
        'name': 'spiele_eines_wettbewerbs',
        'description': f'Alle kommenden Spiele eines Wettbewerbs. Wettbewerbe: {WETTBEWERB_TEXT}.',
        'input_schema': {'type': 'object', 'properties': {
            'wettbewerb': {'type': 'string', 'enum': WETTBEWERBE},
            'tage': {'type': 'integer', 'description': 'Wie viele Tage ab heute (Standard 10, höchstens 21)'},
        }, 'required': ['wettbewerb']},
    },
    {
        'name': 'spiele_an_einem_tag',
        'description': 'Alle Spiele aus den Wettbewerben, die das Café typischerweise zeigt, an einem Tag '
                       '(empfohlene zuerst).',
        'input_schema': {'type': 'object', 'properties': {
            'datum': {'type': 'string', 'description': 'JJJJ-MM-TT'},
        }, 'required': ['datum']},
    },
    {
        'name': 'auswahl_anzeigen',
        'description': 'Zeigt Spiele als Knöpfe im Chat. Ein Tipp auf einen Knopf erstellt die Story. Nutze das, '
                       'wenn der Mensch eine Liste sehen will oder unklar ist, welches Spiel gemeint ist.',
        'input_schema': {'type': 'object', 'properties': {
            'refs': {'type': 'array', 'items': {'type': 'string'}, 'description': 'ref-Werte aus einer Suche'},
            'ueberschrift': {'type': 'string', 'description': 'Kurzer Text über den Knöpfen'},
        }, 'required': ['refs']},
    },
    {
        'name': 'spiel_story_erstellen',
        'description': 'Erstellt die Story für ein Spiel (Wappen, Uhrzeit, Datum, KI-Hintergrund) und schickt '
                       'sie in den Chat. Der Text oben („Heute live bei uns“, „Samstag live bei uns“) passt sich '
                       'automatisch an, kann aber mit kicker überschrieben werden.',
        'input_schema': {'type': 'object', 'properties': {
            'ref': {'type': 'string', 'description': 'ref eines Spiels aus einer Suche'},
            'kicker': {'type': 'string', 'description': 'Optional: eigener kurzer Text oben'},
            'hintergrund_wunsch': {'type': 'string',
                                   'description': 'Optional: englische Beschreibung für einen eigenen KI-Hintergrund'},
        }, 'required': ['ref']},
    },
    {
        'name': 'allgemeine_story_erstellen',
        'description': 'Erstellt eine allgemeine Story auf einem echten Café-Foto und schickt sie in den Chat. '
                       'Vorlagen: geoeffnet (Wir haben geöffnet, Zeiten passen sich dem Wochentag an), cocktails '
                       '(Zeit für einen Drink), wochenende, feiern (mit Telefonnummer), fussball (heutige Spiele als '
                       'Liste), wettbewerb_heute (heutige Spiele eines Wettbewerbs, dann wettbewerb angeben), '
                       'eigen (freier Text, dann titel und optional untertitel angeben).',
        'input_schema': {'type': 'object', 'properties': {
            'vorlage': {'type': 'string', 'enum': VORLAGEN},
            'wettbewerb': {'type': 'string', 'enum': WETTBEWERBE, 'description': 'Nur bei wettbewerb_heute'},
            'titel': {'type': 'string', 'description': 'Bei eigen Pflicht, sonst optional zum Überschreiben'},
            'untertitel': {'type': 'string'},
            'kicker': {'type': 'string', 'description': 'Kurzer Text über dem Titel, optional'},
            'foto': {'type': 'string', 'enum': FOTO_ARTEN, 'description': 'Optional: Art des Hintergrundfotos'},
        }, 'required': ['vorlage']},
    },
    {
        'name': 'zeitplan',
        'description': 'Automatische allgemeine Stories, die der Bot ohne Freigabe nach festem Plan postet '
                       '(z. B. täglich 14 Uhr „Wir haben geöffnet“). anzeigen = Plan und Pause-Status, pausieren = '
                       'aussetzen für tage Tage ab heute (1 = nur heute), fortsetzen = Pause aufheben.',
        'input_schema': {'type': 'object', 'properties': {
            'aktion': {'type': 'string', 'enum': ['anzeigen', 'pausieren', 'fortsetzen']},
            'tage': {'type': 'integer', 'description': 'Nur bei pausieren: Anzahl Tage ab heute'},
        }, 'required': ['aktion']},
    },
    {
        'name': 'story_aendern',
        'description': 'Erstellt eine geänderte Version einer bestehenden Story (die alte wird als ersetzt markiert) '
                       'und schickt sie in den Chat. Nur die angegebenen Felder ändern sich. Felder für Spiel-Stories: '
                       'kicker, wettbewerb, runde, heim, gast, uhrzeit, datum. Für allgemeine Stories: kicker, titel, '
                       'untertitel, titel_groesse, foto. Für beide: neuer_ki_hintergrund, hintergrund_wunsch.',
        'input_schema': {'type': 'object', 'properties': {
            'story': {'type': 'string', 'description': 'Nummer der Story, z. B. S12'},
            'kicker': {'type': 'string', 'description': 'Kurzer Text oben, z. B. „Heute Abend bei uns“'},
            'titel': {'type': 'string'},
            'untertitel': {'type': 'string'},
            'wettbewerb': {'type': 'string'},
            'runde': {'type': 'string', 'description': 'Zeile unter dem Wettbewerb, z. B. „Viertelfinale“, leer = keine'},
            'heim': {'type': 'string', 'description': 'Angezeigter Name der Heimmannschaft'},
            'gast': {'type': 'string', 'description': 'Angezeigter Name der Gastmannschaft'},
            'uhrzeit': {'type': 'string', 'description': 'z. B. 20:45'},
            'datum': {'type': 'string', 'description': 'z. B. „Samstag · 17. Oktober“'},
            'titel_groesse': {'type': 'string', 'enum': ['klein', 'normal', 'gross']},
            'foto': {'type': 'string', 'enum': FOTO_ARTEN, 'description': 'Anderes Café-Foto (allgemeine Stories)'},
            'neuer_ki_hintergrund': {'type': 'boolean', 'description': 'Neuen KI-Hintergrund erzeugen'},
            'hintergrund_wunsch': {'type': 'string', 'description': 'Englische Beschreibung für den neuen Hintergrund'},
        }, 'required': ['story']},
    },
]

TITEL_PX = {'klein': 96, 'normal': None, 'gross': 170}
WOCHENTAGE = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']


def ref(s):
    return f"{s['slug']}|{s['datum']}|{s['id']}"


def zeile(s):
    stern = ' (empfohlen)' if s.get('empfohlen') else ''
    return (f"ref={ref(s)} | {WOCHENTAGE[s['anstoss'].weekday()][:2]} {s['anstoss']:%d.%m. %H:%M} | "
            f"{s['wettbewerb']} {s['runde']} {s['leg']}".rstrip() + f" | {s['heim']['name']} – {s['gast']['name']}{stern}")


class Assistent:
    def __init__(self, bot):
        self.bot = bot
        self.client = anthropic.Anthropic(api_key=umgebung.wert('ANTHROPIC_API_KEY'), max_retries=3)
        self.gefunden = {}   # ref -> Spiel, damit Knöpfe und Stories ohne neue Abfrage gehen

    # Kontext

    def kontext(self, e):
        jetzt = dt.datetime.now(spielplan.BERLIN)
        teile = [f'Jetzt: {WOCHENTAGE[jetzt.weekday()]}, {jetzt:%d.%m.%Y %H:%M} Uhr.']
        meine = [s for s in self.bot.stories.values() if any(m['chat']['id'] == e['chat'] for m in s['nachrichten'])]
        meine.sort(key=lambda s: s['erstellt'])
        if meine:
            teile.append('Stories in diesem Chat (neueste zuletzt):')
            for s in meine[-8:]:
                d = s['daten']
                if s['vorlage'] == 'story':
                    felder = {'kicker': d.get('kicker'), 'wettbewerb': d.get('wettbewerb'),
                              'runde': ' '.join(filter(None, [d.get('runde'), d.get('leg')])),
                              'heim': d['heim']['name'], 'gast': d['gast']['name'], 'uhrzeit': d.get('uhrzeit'),
                              'datum': d.get('datum')}
                else:
                    felder = {'kicker': d.get('kicker'), 'titel': d.get('titel'), 'untertitel': d.get('unter'),
                              'spieleliste': len(d.get('spiele') or [])}
                art = 'Spiel-Story' if s['vorlage'] == 'story' else 'allgemeine Story'
                teile.append(f"- {s['id']} [{s['status']}] {art}: {json.dumps(felder, ensure_ascii=False)}")
        if e.get('antwort_auf'):
            bezug = next((s['id'] for s in meine if any(m['message_id'] == e['antwort_auf'] for m in s['nachrichten'])), None)
            if bezug:
                teile.append(f'Die Nachricht ist eine Antwort auf Story {bezug}.')
        verlauf = self.bot.verlauf.get(e['chat'], [])
        if verlauf:
            teile.append('Letzte Dialoge (älteste zuerst):')
            teile += [f'Mensch: {v[0]}\nDu: {v[1]}' for v in verlauf]
        return '\n'.join(teile)

    # Werkzeuge

    def ausfuehren(self, name, eingabe, chat):
        heute = dt.datetime.now(spielplan.BERLIN).date()
        if name == 'spiele_suchen':
            treffer = spielplan.suchen(eingabe['suchtext'], heute, min(int(eingabe.get('tage') or 14), 21))
            return self.liste(treffer, 'Keine Spiele gefunden.')
        if name == 'spiele_eines_wettbewerbs':
            treffer = spielplan.spiele_im_wettbewerb(eingabe['wettbewerb'], heute, min(int(eingabe.get('tage') or 10), 21))
            return self.liste(treffer, 'Keine Spiele in diesem Zeitraum.')
        if name == 'spiele_an_einem_tag':
            return self.liste(spielplan.spiele(dt.date.fromisoformat(eingabe['datum'])), 'An dem Tag keine Spiele.')
        if name == 'auswahl_anzeigen':
            spiele = [self.gefunden[r] for r in eingabe['refs'] if r in self.gefunden][:60]
            if not spiele:
                return 'Unbekannte refs. Erst suchen.'
            telegram_bot.auswahl_senden(chat, spiele, html.escape(eingabe.get('ueberschrift') or 'Welches Spiel?'))
            return f'{len(spiele)} Spiele als Knöpfe angezeigt.'
        if name == 'spiel_story_erstellen':
            s = self.gefunden.get(eingabe['ref']) or spielplan.finden(*eingabe['ref'].split('|'))
            if not s:
                return 'Spiel nicht gefunden (ref falsch oder schon angepfiffen).'
            telegram_bot.text(f"⏳ Ich erstelle die Story für {html.escape(s['heim']['name'])} – "
                              f"{html.escape(s['gast']['name'])} …", chat=chat)
            sid = self.bot.story(s, [chat], wunsch=eingabe.get('hintergrund_wunsch'), kicker_text=eingabe.get('kicker'))
            return f'Story {sid} erstellt und geschickt.'
        if name == 'allgemeine_story_erstellen':
            return self.allgemein(eingabe, chat, heute)
        if name == 'zeitplan':
            if eingabe['aktion'] == 'pausieren':
                return self.bot.pausieren(max(int(eingabe.get('tage') or 1), 1))
            if eingabe['aktion'] == 'fortsetzen':
                return self.bot.pausieren(0)
            return re.sub(r'<[^>]+>', '', self.bot.zeitplan_text())
        if name == 'story_aendern':
            felder = {k: eingabe[k] for k in ('kicker', 'titel', 'wettbewerb', 'runde', 'heim', 'gast', 'uhrzeit', 'datum')
                      if k in eingabe}
            if 'untertitel' in eingabe:
                felder['unter'] = eingabe['untertitel']
            if 'titel_groesse' in eingabe:
                felder['titel_px'] = TITEL_PX[eingabe['titel_groesse']]
            telegram_bot.text('⏳ Ich ändere die Story …', chat=chat)
            neu = self.bot.aendern(eingabe['story'], chat, felder, eingabe.get('foto'),
                                   bool(eingabe.get('neuer_ki_hintergrund')), eingabe.get('hintergrund_wunsch'))
            return f'Neue Version {neu} geschickt, {eingabe["story"]} ist als ersetzt markiert.'
        return f'Unbekanntes Werkzeug {name}'

    def liste(self, spiele, leer):
        for s in spiele:
            self.gefunden[ref(s)] = s
        if not spiele:
            return leer
        rest = f'\n… und {len(spiele) - 40} weitere' if len(spiele) > 40 else ''
        return '\n'.join(zeile(s) for s in spiele[:40]) + rest

    def allgemein(self, eingabe, chat, heute):
        vorlage = eingabe['vorlage']
        if vorlage == 'wettbewerb_heute':
            if not eingabe.get('wettbewerb'):
                return 'Bei wettbewerb_heute fehlt der Wettbewerb.'
            schluessel, text = f"w:{eingabe['wettbewerb']}", None
        elif vorlage == 'eigen':
            if not eingabe.get('titel'):
                return 'Bei eigen fehlt der Titel.'
            schluessel, text = 'eigen', f"{eingabe['titel']} | {eingabe.get('untertitel', '')}"
        else:
            schluessel, text = vorlage, None
        telegram_bot.text('⏳ Ich erstelle die Story …', chat=chat)
        try:
            d, beschreibung, logos = allgemein.daten(schluessel, heute, text)
        except ValueError as fehler:
            return f'Geht nicht: {fehler}.'
        for feld, ziel in (('titel', 'titel'), ('untertitel', 'unter'), ('kicker', 'kicker')):
            # bei „eigen“ stehen Titel und Untertitel schon im Text, nur der Kicker kommt dazu
            if eingabe.get(feld) and (vorlage != 'eigen' or feld == 'kicker'):
                d[ziel] = eingabe[feld]
        if eingabe.get('foto'):
            d['hintergrund'], d['weich'] = allgemein.foto(eingabe['foto'])
        datei = allgemein.rendern(d, heute, schluessel.replace(':', '-').replace('.', '-'))
        titel = str(d.get('titel', beschreibung)).replace('*', '').replace('|', ' ')
        sid = self.bot.senden('allgemein', d, 'allgemein', titel, 'Allgemeine Story', [chat], logos=logos, datei=datei,
                              tag=heute)
        return f'Story {sid} erstellt und geschickt.'

    # Ablauf

    def antworten(self, e):
        chat, text = e['chat'], e['text']
        telegram_bot.tippt(chat)
        nachrichten = [{'role': 'user', 'content': f'{self.kontext(e)}\n\nNeue Nachricht: {text}'}]
        antwort = None
        try:
            for _ in range(MAX_RUNDEN):
                r = self.client.messages.create(model=MODELL, max_tokens=4096, system=SYSTEM, tools=TOOLS,
                                                output_config={'effort': 'medium'}, messages=nachrichten)
                if r.stop_reason == 'refusal':
                    antwort = 'Dabei kann ich leider nicht helfen.'
                    break
                if r.stop_reason != 'tool_use':
                    antwort = ' '.join(b.text for b in r.content if b.type == 'text').strip()
                    if r.stop_reason == 'max_tokens' and not antwort:
                        antwort = 'Das war zu viel auf einmal. Versuch es bitte in kleineren Schritten.'
                    break
                nachrichten.append({'role': 'assistant', 'content': r.content})
                ergebnisse = []
                for block in r.content:
                    if block.type != 'tool_use':
                        continue
                    try:
                        inhalt, fehler = self.ausfuehren(block.name, block.input, chat), False
                    except Exception as f:  # Werkzeugfehler an Claude zurückgeben, nicht abbrechen
                        inhalt, fehler = f'Fehler: {f}', True
                    print('Werkzeug', block.name, json.dumps(block.input, ensure_ascii=False)[:200], '->', inhalt[:120])
                    ergebnisse.append({'type': 'tool_result', 'tool_use_id': block.id, 'content': inhalt,
                                       'is_error': fehler})
                nachrichten.append({'role': 'user', 'content': ergebnisse})
                telegram_bot.tippt(chat)
            else:
                antwort = 'Das hat zu viele Schritte gebraucht. Versuch es bitte noch einmal etwas genauer.'
        except anthropic.AuthenticationError:
            telegram_bot.text('⚠️ Der Anthropic-API-Key ist ungültig. Ich nutze die einfache Suche.', chat=chat)
            self.bot.suche_ohne_ki(text, chat)
            return
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APIStatusError) as f:
            print('Claude nicht erreichbar:', f)
            telegram_bot.text('⚠️ Die KI ist gerade nicht erreichbar, ich nutze die einfache Suche.', chat=chat)
            self.bot.suche_ohne_ki(text, chat)
            return
        antwort = antwort or 'Erledigt.'
        telegram_bot.text(html.escape(antwort), chat=chat)
        self.bot.verlauf.setdefault(chat, []).append([text[:300], antwort[:300]])
        self.bot.verlauf[chat] = self.bot.verlauf[chat][-6:]
        self.bot.speichern()
