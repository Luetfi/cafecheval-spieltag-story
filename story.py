"""Erzeugt die Spieltag-Stories für einen Tag.

    python story.py                 # heute (deutsche Zeit)
    python story.py 2026-10-17      # bestimmter Tag
    python story.py 2026-10-17 --ohne-ki   # Hintergrund aus dem Vorrat statt neu generieren

Ergebnis: ausgabe/<datum>/<anstoss>-<heim>-<gast>.jpg (1080 × 1920, JPEG wie von Instagram verlangt)
"""
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.parse
import urllib.request

from PIL import Image

import hintergrund
import spielplan

HIER = pathlib.Path(__file__).resolve().parent
VORLAGE = HIER / 'vorlage' / 'story.html'
WAPPEN = HIER / 'cache' / 'wappen'
AUSGABE = HIER / 'ausgabe'

WOCHENTAGE = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
MONATE = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']


def chrome():
    kandidaten = [os.environ.get('CHROME'),
                  r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                  r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                  shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chromium-browser')]
    for k in kandidaten:
        if k and pathlib.Path(k).exists():
            return k
    raise RuntimeError('Chrome nicht gefunden (Umgebungsvariable CHROME setzen)')


def slug(text):
    t = text.lower().translate(str.maketrans({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss', 'ø': 'o'}))
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')


def ist_flagge(bild):
    """Flaggen sind rechteckig und deckend, Wappen haben transparente Ecken."""
    a = bild.getchannel('A')
    w, h = bild.size
    return w > h * 1.2 and all(a.getpixel(p) > 200 for p in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)))


def wappen(team):
    """Lädt das Wappen einmalig in den Cache, schneidet transparente Ränder ab.
    Gibt (Datei, ist_flagge) zurück. Bei Flaggen wird der schmale dunkle Rahmen von ESPN entfernt."""
    WAPPEN.mkdir(parents=True, exist_ok=True)
    datei = WAPPEN / f"{team['id']}.png"
    if not datei.exists() and team.get('logo'):
        req = urllib.request.Request(team['logo'], headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            datei.write_bytes(r.read())
        bild = Image.open(datei).convert('RGBA')
        bild = bild.crop(bild.getchannel('A').getbbox() or (0, 0, *bild.size))
        if ist_flagge(bild):
            rand = max(2, round(min(bild.size) * 0.03))
            bild = bild.crop((rand, rand, bild.width - rand, bild.height - rand))
        bild.save(datei)
    return datei, ist_flagge(Image.open(datei).convert('RGBA'))


def rendern(daten, ziel: pathlib.Path, vorlage=VORLAGE):
    url = vorlage.as_uri() + '?d=' + urllib.parse.quote(json.dumps(daten, ensure_ascii=False))
    png = ziel.with_suffix('.png')
    ziel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([chrome(), '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
                    '--allow-file-access-from-files', '--virtual-time-budget=4000',
                    '--window-size=1080,1920', f'--screenshot={png}', url],
                   check=True, capture_output=True, timeout=90)
    Image.open(png).convert('RGB').save(ziel, 'JPEG', quality=92, optimize=True)
    png.unlink()
    return ziel


def kicker(s, heute: dt.date):
    """„Heute live bei uns“, „Morgen live bei uns“, „Samstag live bei uns“ (bzw. „… Nacht …“ bei Anstoß nach Mitternacht)."""
    tage = (s['tag'] - heute).days
    if tage <= 0:
        wann = 'Heute Nacht' if s['nacht'] else 'Heute'
    elif tage == 1:
        wann = 'Morgen Nacht' if s['nacht'] else 'Morgen'
    else:
        wann = WOCHENTAGE[s['tag'].weekday()] + ('nacht' if s['nacht'] else '')
    return f'{wann} live bei uns'


def story_bauen(s, heute: dt.date, ki=True, hintergruende=None, nr=0, wunsch=None, kicker_text=None):
    """Rendert die Story für ein Spiel nach ausgabe/<spieltag>/. `hintergruende` (dict) teilt einen
    KI-Hintergrund zwischen allen Spielen eines Wettbewerbs am selben Tag, das spart Kosten.
    `wunsch`: eigene Beschreibung für einen neuen KI-Hintergrund (wird dann nicht geteilt).
    Gibt das Spiel plus `datei` und `daten` (alle Bausteine, für spätere Änderungen) zurück."""
    ordner = AUSGABE / s['tag'].isoformat()
    name = f"{s['anstoss']:%H%M}-{slug(s['heim']['name'])}-{slug(s['gast']['name'])}"
    schluessel = (s['tag'], s['wettbewerb'])
    if hintergruende is not None and schluessel in hintergruende and not wunsch:
        bg = hintergruende[schluessel]
    else:
        bg = hintergrund.hintergrund(s, ordner / 'hintergrund' / f'{name}.png', nr=s['tag'].toordinal() + nr, ki=ki,
                                     wunsch=wunsch)
        if hintergruende is not None and not wunsch:
            hintergruende[schluessel] = bg
    a = s['anstoss']
    daten = {
        'kicker': kicker_text or kicker(s, heute),
        'wettbewerb': s['wettbewerb'],
        'runde': s['runde'],
        'leg': s['leg'],
        'uhrzeit': f'{a:%H:%M}',
        'datum': f'{WOCHENTAGE[a.weekday()]} · {a.day}. {MONATE[a.month - 1]}',
        'hintergrund': bg.as_uri() if bg else '',
    }
    for k in ('heim', 'gast'):
        datei, flagge = wappen(s[k])
        daten[k] = {'name': s[k]['name'], 'wappen': datei.as_uri(), 'flagge': flagge}
    ziel = rendern(daten, ordner / f'{name}.jpg')
    print('Story:', ziel)
    return {**s, 'datei': ziel, 'daten': daten}


def pfade_reparieren(daten, logos):
    """Nach einem Neustart fehlen Cache-Dateien (Wappen, KI-Hintergrund). Lädt Wappen neu bzw. nimmt
    einen Hintergrund aus dem Vorrat. `logos`: {Team-ID: Logo-URL}."""
    def pruefen(wert, schluessel=''):
        if isinstance(wert, dict):
            return {k: pruefen(v, k) for k, v in wert.items()}
        if isinstance(wert, list):
            return [pruefen(v) for v in wert]
        if isinstance(wert, str) and wert.startswith('file:'):
            pfad = pathlib.Path(urllib.request.url2pathname(urllib.parse.urlparse(wert).path))
            if pfad.exists():
                return wert
            if pfad.parent == WAPPEN and pfad.stem in logos:
                return wappen({'id': pfad.stem, 'logo': logos[pfad.stem]})[0].as_uri()
            if schluessel == 'hintergrund':
                ersatz = hintergrund.aus_vorrat()
                return ersatz.as_uri() if ersatz else ''
        return wert
    return pruefen(daten)


def stories(tag: dt.date, ki=True):
    """Alle Stories für den Morgen von `tag` (empfohlene zuerst)."""
    geteilt = {}
    ergebnisse = [story_bauen(s, tag, ki, geteilt, nr) for nr, s in enumerate(spielplan.spiele(tag))]
    if not ergebnisse:
        print(f'{tag}: keine Spiele mit Story')
    return ergebnisse


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    tag = dt.date.fromisoformat(args[0]) if args else dt.datetime.now(spielplan.BERLIN).date()
    stories(tag, ki='--ohne-ki' not in sys.argv)
