"""Holt Spiele von ESPN: alle Spiele eines Tages (mit Empfehlung) und die Suche nach einem bestimmten Spiel."""
import concurrent.futures as cf
import datetime as dt
import gzip
import json
import re
import unicodedata
import urllib.request
from zoneinfo import ZoneInfo

import config

BERLIN = ZoneInfo('Europe/Berlin')
API = 'https://site.api.espn.com/apis/site/v2/sports/soccer'
NACHT = dt.timedelta(hours=6)


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)


_deutsch = None


def deutsche_vereine():
    global _deutsch
    if _deutsch is None:
        _deutsch = set()
        for liga in ('ger.1', 'ger.2'):
            for t in get(f'{API}/{liga}/teams')['sports'][0]['leagues'][0]['teams']:
                _deutsch.add(t['team']['id'])
    return _deutsch


def name(team):
    n = team.get('displayName') or team.get('name')
    return config.NAMEN.get(n, n)


def treffer(regel, teams, deutsch):
    ids = {t['id'] for t in teams}
    namen = {t.get('displayName') for t in teams}
    return {
        'alle': True,
        'vfb': config.VFB_ID in ids,
        'topspiel': ids <= config.TOPVEREINE,
        'deutsch': bool(ids & deutsch),
        'deutschland': config.DEUTSCHLAND in namen,
        'topnation': bool(namen & config.TOPNATIONEN),
    }[regel]


def wichtig(teams, deutsch):
    """VfB, Nationalmannschaft und deutsche Vereine gehen bei der Tagesgrenze vor."""
    return any(treffer(r, teams, deutsch) for r in ('vfb', 'deutschland', 'deutsch'))


def spieltag(anstoss):
    """Anstoß vor 6 Uhr (z. B. WM in Amerika) gehört zum Vorabend, sonst käme die Story erst nach dem Spiel."""
    return (anstoss - NACHT).date()


def events(slug, datum):
    """Spiele eines Wettbewerbs an einem ESPN-Datum (JJJJMMTT). Fehler werden gemeldet, nicht geworfen."""
    try:
        return get(f'{API}/{slug}/scoreboard?dates={datum}').get('events', [])
    except Exception as e:  # ein Wettbewerb darf ausfallen, ohne den Rest zu blockieren
        print(f'Warnung: {slug} {datum}: {e}')
        return []


def spiel(e, w, datum, deutsch):
    """ESPN-Event -> Spiel-Dict. None bei abgesagten oder schon laufenden/beendeten Spielen."""
    comp = e['competitions'][0]
    status = comp.get('status', e.get('status', {})).get('type', {})
    if status.get('name') in ('STATUS_POSTPONED', 'STATUS_CANCELED') or status.get('state') in ('in', 'post'):
        return None
    anstoss = dt.datetime.fromisoformat(e['date'].replace('Z', '+00:00')).astimezone(BERLIN)
    teams = {c['homeAway']: c['team'] for c in comp['competitors']}
    liste = list(teams.values())
    runde = (e.get('season') or {}).get('slug', '')
    notiz = next((n.get('headline') for n in comp.get('notes', []) if n.get('headline')), '')
    regeln = w.get('regeln', [])
    return {
        'id': e['id'],
        'slug': w['slug'],
        'datum': datum,
        'anstoss': anstoss,
        'tag': spieltag(anstoss),
        'nacht': anstoss.date() != spieltag(anstoss),
        'wettbewerb': w['name'],
        'runde': config.RUNDEN.get(runde, ''),
        'leg': {'1st Leg': 'Hinspiel', '2nd Leg': 'Rückspiel'}.get(notiz, ''),
        'empfohlen': runde in w.get('alle_ab', []) or any(treffer(r, liste, deutsch) for r in regeln),
        'angebot': runde in w.get('alle_ab', []) or any(treffer(r, liste, deutsch) for r in w.get('angebot', ['alle'])),
        'wichtig': wichtig(liste, deutsch),
        'beliebt': sum(t.get('displayName') in config.BELIEBTE for t in liste),
        'heim': {'id': teams['home']['id'], 'name': name(teams['home']), 'logo': teams['home'].get('logo'),
                 'such': [teams['home'].get(k) or '' for k in ('displayName', 'shortDisplayName', 'abbreviation')]},
        'gast': {'id': teams['away']['id'], 'name': name(teams['away']), 'logo': teams['away'].get('logo'),
                 'such': [teams['away'].get(k) or '' for k in ('displayName', 'shortDisplayName', 'abbreviation')]},
    }


def sammeln(wettbewerbe, tage):
    """Alle kommenden Spiele der Wettbewerbe, deren Spieltag in `tage` liegt (parallel abgefragt)."""
    deutsch = deutsche_vereine()
    # ESPN gruppiert nach US-Ortszeit, deshalb Vortag und Folgetag mit abfragen und selbst filtern.
    daten = sorted({(t + dt.timedelta(d)).strftime('%Y%m%d') for t in tage for d in (-1, 0, 1)})
    auftraege = [(w, d) for w in wettbewerbe for d in daten]
    with cf.ThreadPoolExecutor(12) as pool:
        antworten = list(pool.map(lambda a: (a[0], a[1], events(a[0]['slug'], a[1])), auftraege))
    gefunden, gesehen = [], set()
    for w, datum, evs in antworten:
        for e in evs:
            if e['id'] in gesehen:
                continue
            s = spiel(e, w, datum, deutsch)
            if s and s['tag'] in tage:
                gesehen.add(e['id'])
                gefunden.append(s)
    return gefunden


def spiele(tag: dt.date):
    """Alle Spiele, die am Morgen von `tag` als Story kommen: empfohlene zuerst, dann der Rest nach Uhrzeit."""
    prio = {w['slug']: i for i, w in enumerate(config.WETTBEWERBE)}
    alle = [s for s in sammeln(config.WETTBEWERBE, {tag}) if s['angebot'] or s['empfohlen']]
    alle.sort(key=lambda s: (not s['empfohlen'], not s['wichtig'], -s['beliebt'], prio[s['slug']], s['anstoss']))
    return alle[:config.MAX_PRO_TAG]


def finden(slug, datum, event_id):
    """Ein bestimmtes Spiel wiederfinden (für Knöpfe in Telegram)."""
    w = wettbewerb(slug)
    if not w:
        return None
    e = next((e for e in events(slug, datum) if e['id'] == event_id), None)
    return spiel(e, w, datum, deutsche_vereine()) if e else None


def alle_wettbewerbe():
    return config.WETTBEWERBE + config.SUCH_WETTBEWERBE


def wettbewerb(slug):
    return next((w for w in alle_wettbewerbe() if w['slug'] == slug), None)


def ligen():
    """(Knopftext, Slug) je Wettbewerb, in der Reihenfolge von config.LIGEN."""
    gesehen, liste = set(), []
    for text, slug in config.LIGEN.items():
        if slug not in gesehen and wettbewerb(slug):
            gesehen.add(slug)
            liste.append((text, slug))
    return liste


def liga_erkennen(text):
    """Ist die Nachricht ein Wettbewerb („Champions League“, „alle Bundesliga Spiele“)? Dann dessen Slug."""
    woerter = [w for w in _norm(text).split() if w not in config.LISTEN_WOERTER]
    rest = ' '.join(woerter)
    namen = {_norm(k).strip(): v for k, v in config.LIGEN.items()}
    return namen.get(rest)


def spiele_im_wettbewerb(slug, ab: dt.date, tage=10):
    w = wettbewerb(slug)
    spiele_ = sammeln([w], {ab + dt.timedelta(i) for i in range(tage)}) if w else []
    spiele_.sort(key=lambda s: s['anstoss'])
    return spiele_


def _norm(text):
    t = unicodedata.normalize('NFKD', text.lower()).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9 ]+', ' ', t)


def suchen(text, ab: dt.date, tage=14):
    """Sucht Spiele in den nächsten `tage` Tagen, in denen jedes Suchwort zu einer Mannschaft passt."""
    woerter = [config.KUERZEL.get(w, w) for w in _norm(text).split() if w not in config.FUELLWOERTER]
    if not woerter:
        return []
    kandidaten = sammeln(alle_wettbewerbe(), {ab + dt.timedelta(i) for i in range(tage)})

    def passt(wort, team):
        return any(wort in _norm(n) for n in [team['name'], *team['such']])

    treffer_ = [s for s in kandidaten if all(passt(w, s['heim']) or passt(w, s['gast']) for w in woerter)]
    treffer_.sort(key=lambda s: s['anstoss'])
    return treffer_


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == 'suche':
        for s in suchen(' '.join(sys.argv[2:]), dt.datetime.now(BERLIN).date()):
            print(s['anstoss'].strftime('%d.%m. %H:%M'), s['wettbewerb'], '|', s['heim']['name'], '–', s['gast']['name'])
    else:
        tag = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.datetime.now(BERLIN).date()
        for s in spiele(tag):
            print('⭐' if s['empfohlen'] else '  ', s['anstoss'].strftime('%d.%m. %H:%M'), s['wettbewerb'], s['runde'], s['leg'],
                  '|', s['heim']['name'], '–', s['gast']['name'])
