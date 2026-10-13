"""Erzeugt Story-Hintergründe mit kie.ai (google/nano-banana, Text zu Bild, 9:16).

Jedes erzeugte Bild landet zusätzlich im Vorrat `hintergruende/`. Fällt kie.ai aus (kein Guthaben,
Zeitüberschreitung), nimmt die Story ein Bild aus dem Vorrat, damit trotzdem gepostet werden kann.
"""
import base64
import json
import pathlib
import random
import time
import urllib.request

import config
import umgebung

HIER = pathlib.Path(__file__).resolve().parent
VORRAT = HIER / 'hintergruende'
API = 'https://api.kie.ai'
MODELL = 'google/nano-banana'


def api_key():
    return umgebung.wert('KIE_AI_API_KEY')


def call(method, url, key, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def prompt(spiel, nr, wunsch=None):
    """`wunsch`: eigene Bildbeschreibung (englisch), z. B. vom Assistenten. Sonst eine der Stimmungen aus config."""
    stimmung = wunsch or config.STIMMUNGEN[nr % len(config.STIMMUNGEN)]
    return f'{stimmung}. Mood for a {spiel["wettbewerb"]} match night. {config.STIL}'


def erzeugen(spiel, ziel: pathlib.Path, nr=0, timeout=300, wunsch=None):
    """Erzeugt ein Bild nach `ziel`. Gibt den Pfad zurück oder None bei Fehler."""
    key = api_key()
    res = call('POST', f'{API}/api/v1/jobs/createTask', key, {
        'model': MODELL,
        'input': {'prompt': prompt(spiel, nr, wunsch), 'output_format': 'png', 'image_size': '9:16'}})
    if res.get('code') != 200:
        raise RuntimeError(f'kie.ai Task fehlgeschlagen: {res}')
    task = res['data']['taskId']
    ende = time.time() + timeout
    while time.time() < ende:
        info = call('GET', f'{API}/api/v1/jobs/recordInfo?taskId={task}', key)['data']
        if info.get('state') == 'success':
            url = json.loads(info['resultJson'])['resultUrls'][0]
            ziel.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(url, ziel)
            VORRAT.mkdir(exist_ok=True)
            (VORRAT / f'{task}.png').write_bytes(ziel.read_bytes())
            return ziel
        if info.get('state') == 'fail':
            raise RuntimeError(f'kie.ai: {info.get("failMsg")}')
        time.sleep(5)
    raise RuntimeError('kie.ai: Zeitüberschreitung')


def hintergrund(spiel, ziel: pathlib.Path, nr=0, ki=True, wunsch=None):
    if ki:
        try:
            return erzeugen(spiel, ziel, nr, wunsch=wunsch)
        except Exception as e:
            print(f'Warnung: KI-Hintergrund fehlgeschlagen ({e}), nehme Bild aus dem Vorrat')
    bilder = sorted(VORRAT.glob('*.png')) if VORRAT.exists() else []
    if not bilder:
        return None
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(random.choice(bilder).read_bytes())
    return ziel


def aus_vorrat():
    bilder = sorted(VORRAT.glob('*.png')) if VORRAT.exists() else []
    return random.choice(bilder) if bilder else None


def hochladen(datei: pathlib.Path, ordner='cafecheval-stories'):
    """Lädt ein JPEG zu kie.ai hoch und gibt die öffentliche URL zurück (bleibt einige Tage abrufbar).
    Instagram holt sich das Bild beim Posten von dort."""
    b64 = base64.b64encode(datei.read_bytes()).decode()
    res = call('POST', 'https://kieai.redpandaai.co/api/file-base64-upload', api_key(), {
        'base64Data': f'data:image/jpeg;base64,{b64}', 'uploadPath': ordner, 'fileName': datei.name})
    if not res.get('success'):
        raise RuntimeError(f'Upload fehlgeschlagen: {res}')
    return res['data']['downloadUrl']
