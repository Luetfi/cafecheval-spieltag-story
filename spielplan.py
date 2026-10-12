"""Holt die Spiele eines Tages von ESPN und filtert die, die im Café eine Story bekommen."""
import datetime as dt
import gzip
import json
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


def deutsche_vereine():
    ids = set()
    for liga in ('ger.1', 'ger.2'):
        for t in get(f'{API}/{liga}/teams')['sports'][0]['leagues'][0]['teams']:
            ids.add(t['team']['id'])
    return ids


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


def zaehlt(w, runde, teams, deutsch):
    return runde in w.get('alle_ab', []) or any(treffer(r, teams, deutsch) for r in w['regeln'])


def wichtig(teams, deutsch):
    """VfB, Nationalmannschaft und deutsche Vereine gehen bei der Tagesgrenze vor."""
    return any(treffer(r, teams, deutsch) for r in ('vfb', 'deutschland', 'deutsch'))


def spiele(tag: dt.date):
    """Alle Story-Spiele des Abends von `tag` (deutsche Zeit, Anstoß bis 6 Uhr am Folgetag), sortiert nach Priorität und Uhrzeit."""
    deutsch = deutsche_vereine()
    # ESPN gruppiert nach US-Ortszeit, deshalb Vortag und Folgetag mit abfragen und selbst filtern.
    abfrage = [(tag + dt.timedelta(d)).strftime('%Y%m%d') for d in (-1, 0, 1)]
    gefunden, gesehen = [], set()
    for prio, w in enumerate(config.WETTBEWERBE):
        for datum in abfrage:
            try:
                events = get(f"{API}/{w['slug']}/scoreboard?dates={datum}").get('events', [])
            except Exception as e:  # ein Wettbewerb darf ausfallen, ohne den Rest zu blockieren
                print(f"Warnung: {w['slug']} {datum}: {e}")
                continue
            for e in events:
                if e['id'] in gesehen:
                    continue
                anstoss = dt.datetime.fromisoformat(e['date'].replace('Z', '+00:00')).astimezone(BERLIN)
                # Anstoß vor 6 Uhr (z. B. WM in Amerika) gehört zum Vorabend, sonst käme die Story erst nach dem Spiel.
                if (anstoss - NACHT).date() != tag:
                    continue
                comp = e['competitions'][0]
                if comp.get('status', e.get('status', {})).get('type', {}).get('name') in ('STATUS_POSTPONED', 'STATUS_CANCELED'):
                    continue
                teams = {c['homeAway']: c['team'] for c in comp['competitors']}
                runde = (e.get('season') or {}).get('slug', '')
                if not zaehlt(w, runde, list(teams.values()), deutsch):
                    continue
                gesehen.add(e['id'])
                notiz = next((n.get('headline') for n in comp.get('notes', []) if n.get('headline')), '')
                gefunden.append({
                    'id': e['id'],
                    'prio': (0 if wichtig(list(teams.values()), deutsch) else 1, prio),
                    'anstoss': anstoss,
                    'nacht': anstoss.date() != tag,
                    'wettbewerb': w['name'],
                    'runde': config.RUNDEN.get(runde, ''),
                    'leg': {'1st Leg': 'Hinspiel', '2nd Leg': 'Rückspiel'}.get(notiz, ''),
                    'heim': {'id': teams['home']['id'], 'name': name(teams['home']), 'logo': teams['home'].get('logo')},
                    'gast': {'id': teams['away']['id'], 'name': name(teams['away']), 'logo': teams['away'].get('logo')},
                })
    gefunden.sort(key=lambda s: (s['prio'], s['anstoss']))
    auswahl = gefunden[:config.MAX_PRO_TAG]
    auswahl.sort(key=lambda s: s['anstoss'])
    return auswahl


if __name__ == '__main__':
    import sys
    tag = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.datetime.now(BERLIN).date()
    for s in spiele(tag):
        print(s['anstoss'].strftime('%d.%m. %H:%M'), s['wettbewerb'], s['runde'], s['leg'], '|', s['heim']['name'], '–', s['gast']['name'])
