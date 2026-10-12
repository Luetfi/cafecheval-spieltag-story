"""Allgemeine Stories („Wir haben geöffnet“, „Heute Champions League bei uns“ …) auf echten Café-Fotos.

Texte: *Wort* wird kursiv in Kupfer (im Titel) bzw. fett (im Untertitel), | bricht den Titel um.
Fotos liegen in assets/fotos/ (9:16 zugeschnitten). Pro Story wird eins der passenden Fotos zufällig gewählt.
Fotos mit gut sichtbaren Spielautomaten sind bewusst nicht dabei: keine Werbung für Glücksspiel.
Fußball-Stories nehmen statt eines Fotos einen Stadion-Hintergrund aus dem KI-Vorrat (hintergruende/).
"""
import datetime as dt
import random

import spielplan
import story

FOTOS = story.HIER / 'assets' / 'fotos'
VORLAGE = story.HIER / 'vorlage' / 'allgemein.html'
TELEFON = '01520 8810101'

# Öffnungszeiten nach Wochentag (Mo = 0), wie auf der Website (src/data/site.ts)
ZEITEN = {0: ('14', '3'), 1: ('14', '3'), 2: ('14', '3'), 3: ('14', '3'), 4: ('14', '5'), 5: ('14', '5'), 6: ('14', '3')}

BAR = ['gastraum-bar', 'ludwigsburg-bar-abends', 'bar-samtsessel', 'tresen-barhocker', 'tische-kerzen']
COCKTAILS = ['cocktail-caipirinha', 'cocktail-cuba-libre', 'cocktail-long-island', 'cocktail-mojito',
             'cocktail-sex-on-the-beach']
FUSSBALL = 'ki-vorrat'


def _zeiten(tag):
    auf, zu = ZEITEN[tag.weekday()]
    return f'{auf} bis {zu} Uhr'


# Schlüssel -> Knopftext, Inhalt (Funktion des Tages) und Fotos
VORLAGEN = {
    'geoeffnet': {
        'knopf': '🟢 Wir haben geöffnet',
        'inhalt': lambda tag: {'kicker': 'Heute für euch da', 'titel': 'Wir haben *geöffnet*',
                               'unter': f'Heute von *{_zeiten(tag)}*. Kommt vorbei!'},
        'fotos': ['fassade-asperger-strasse'] + BAR,
    },
    'cocktails': {
        'knopf': '🍹 Zeit für einen Drink',
        'inhalt': lambda tag: {'kicker': 'Feierabend', 'titel': 'Zeit für einen *Drink*',
                               'unter': f'Cocktails und Longdrinks, heute von *{_zeiten(tag)}*.'},
        'fotos': COCKTAILS,
    },
    'wochenende': {
        'knopf': '🎉 Endlich Wochenende',
        'inhalt': lambda tag: {'kicker': 'Freitag & Samstag', 'titel': 'Endlich *Wochenende*',
                               'unter': 'Wir haben bis *5 Uhr* für euch geöffnet. Wir sehen uns!'},
        'fotos': BAR,
    },
    'feiern': {
        'knopf': '🥂 Feiern bei uns',
        'inhalt': lambda tag: {'kicker': 'Euer Anlass bei uns', 'titel': 'Lust zu *feiern*?',
                               'unter': f'Geburtstag, Abschied oder einfach so. Ruft uns an: *{TELEFON}*'},
        'fotos': BAR,
    },
    'fussball': {
        'knopf': '⚽ Heute Fußball live',
        'inhalt': lambda tag: {'kicker': 'Heute live bei uns', 'titel': 'Fußball *live*',
                               'unter': 'Alle Spiele auf großer Leinwand.'},
        'fotos': FUSSBALL,
        'spiele': 'alle',
    },
}
MAX_SPIELE = 5


def _foto(namen):
    if namen == 'ki-vorrat':
        return random.choice(sorted((story.HIER / 'hintergruende').glob('*.png'))).as_uri()
    return (FOTOS / f'{random.choice(namen)}.jpg').as_uri()


def _spiele_daten(spiele):
    """Höchstens MAX_SPIELE Spiele (empfohlene zuerst), nach Anstoß sortiert, für die Vorlage."""
    auswahl = sorted(spiele, key=lambda s: (not s['empfohlen'], -s['beliebt'], s['anstoss']))[:MAX_SPIELE]
    auswahl.sort(key=lambda s: s['anstoss'])
    daten = [{'uhrzeit': f"{s['anstoss']:%H:%M}", 'heim': s['heim']['name'], 'gast': s['gast']['name'],
              'heim_wappen': story.wappen(s['heim'])[0].as_uri(), 'gast_wappen': story.wappen(s['gast'])[0].as_uri()}
             for s in auswahl]
    rest = len(spiele) - len(auswahl)
    mehr = ('… und 1 weiteres Spiel' if rest == 1 else f'… und {rest} weitere Spiele') if rest > 0 else ''
    return daten, mehr


# Stichwörter in einer Nachricht an den Bot -> Vorlage („wir haben geöffnet“, „cocktails“ …)
STICHWOERTER = {'geoffnet': 'geoeffnet', 'geoeffnet': 'geoeffnet', 'offen': 'geoeffnet', 'cocktail': 'cocktails',
                'cocktails': 'cocktails', 'drink': 'cocktails', 'drinks': 'cocktails', 'feierabend': 'cocktails',
                'wochenende': 'wochenende', 'weekend': 'wochenende', 'feiern': 'feiern', 'party': 'feiern',
                'geburtstag': 'feiern'}


def stichwort(text):
    woerter = spielplan._norm(text).split()
    return next((STICHWOERTER[w] for w in woerter if w in STICHWOERTER), None)


def knoepfe(tag, spiele_heute):
    """(Knopftext, Schlüssel) für /allgemein: feste Vorlagen plus ein Knopf je Wettbewerb mit Spielen heute."""
    liste = [(v['knopf'], k) for k, v in VORLAGEN.items() if k != 'fussball' or spiele_heute]
    gesehen = []
    for s in spiele_heute:
        if s['slug'] not in gesehen:
            gesehen.append(s['slug'])
    for slug in gesehen:
        anzahl = sum(s['slug'] == slug for s in spiele_heute)
        name = next(s['wettbewerb'] for s in spiele_heute if s['slug'] == slug)
        liste.append((f'⚽ Heute {name} ({anzahl})', f'w:{slug}'))
    liste.append(('✍️ Eigener Text', 'eigen'))
    return liste


def bauen(schluessel, tag: dt.date, text=None):
    """Rendert eine allgemeine Story. Gibt (Datei, Kurzbeschreibung) zurück.
    `schluessel`: Vorlage aus VORLAGEN, 'w:<Wettbewerb>' oder 'eigen' (dann `text` = 'Titel | Untertitel')."""
    if schluessel == 'eigen':
        titel, _, unter = (text or '').partition('|')
        if not titel.strip():
            raise ValueError('Kein Text angegeben')
        daten = {'kicker': '', 'titel': titel.strip(), 'unter': unter.strip(), 'hintergrund': _foto(BAR)}
        beschreibung = titel.replace('*', '').strip()
    elif schluessel.startswith('w:'):
        slug = schluessel[2:]
        spiele = [s for s in spielplan.spiele(tag) if s['slug'] == slug] or \
                 [s for s in spielplan.spiele_im_wettbewerb(slug, tag, 1) if s['tag'] == tag]
        if not spiele:
            raise ValueError('Heute keine Spiele in diesem Wettbewerb')
        name = spiele[0]['wettbewerb']
        liste, mehr = _spiele_daten(spiele)
        daten = {'kicker': 'Heute live bei uns', 'titel': name, 'unter': '', 'spiele': liste, 'mehr': mehr,
                 'hintergrund': _foto(FUSSBALL), 'weich': True}
        beschreibung = f'Heute {name}'
    else:
        v = VORLAGEN[schluessel]
        daten = {**v['inhalt'](tag), 'hintergrund': _foto(v['fotos']), 'weich': v['fotos'] == 'ki-vorrat'}
        if v.get('spiele'):
            spiele = spielplan.spiele(tag)
            if not spiele:
                raise ValueError('Heute keine Spiele')
            daten['spiele'], daten['mehr'] = _spiele_daten(spiele)
        beschreibung = v['knopf'].split(' ', 1)[1]
    name = f"{schluessel.replace(':', '-').replace('.', '-')}-{dt.datetime.now():%H%M%S}"
    ziel = story.AUSGABE / tag.isoformat() / 'allgemein' / f'{story.slug(name)}.jpg'
    return story.rendern(daten, ziel, VORLAGE), beschreibung


if __name__ == '__main__':
    import sys
    tag = dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else dt.date.today()
    print(bauen(sys.argv[1], tag, ' '.join(sys.argv[3:]) or None))
