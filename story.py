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


def rendern(daten, ziel: pathlib.Path):
    url = VORLAGE.as_uri() + '?d=' + urllib.parse.quote(json.dumps(daten, ensure_ascii=False))
    png = ziel.with_suffix('.png')
    ziel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([chrome(), '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
                    '--allow-file-access-from-files', '--virtual-time-budget=4000',
                    '--window-size=1080,1920', f'--screenshot={png}', url],
                   check=True, capture_output=True, timeout=90)
    Image.open(png).convert('RGB').save(ziel, 'JPEG', quality=92, optimize=True)
    png.unlink()
    return ziel


def stories(tag: dt.date, ki=True):
    ordner = AUSGABE / tag.isoformat()
    ergebnisse = []
    for nr, s in enumerate(spielplan.spiele(tag)):
        name = f"{s['anstoss']:%H%M}-{slug(s['heim']['name'])}-{slug(s['gast']['name'])}"
        bg = hintergrund.hintergrund(s, ordner / 'hintergrund' / f'{name}.png', nr=tag.toordinal() + nr, ki=ki)
        a = s['anstoss']
        daten = {
            'kicker': 'Heute Nacht live bei uns' if s['nacht'] else 'Heute live bei uns',
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
        ergebnisse.append({**s, 'datei': ziel})
    if not ergebnisse:
        print(f'{tag}: keine Spiele mit Story')
    return ergebnisse


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    tag = dt.date.fromisoformat(args[0]) if args else dt.datetime.now(spielplan.BERLIN).date()
    stories(tag, ki='--ohne-ki' not in sys.argv)
