"""Story über die Instagram API (Instagram Login, graph.instagram.com) veröffentlichen.

Benötigt INSTAGRAM_TOKEN: langlebiger Instagram-User-Token mit den Rechten
instagram_business_basic und instagram_business_content_publish. Der Token gilt 60 Tage und wird
über `token_verlaengern()` regelmäßig verlängert.
"""
import json
import time
import urllib.parse
import urllib.request

import umgebung

API = 'https://graph.instagram.com/v23.0'


def _call(methode, pfad, **params):
    params['access_token'] = umgebung.wert('INSTAGRAM_TOKEN')
    daten = urllib.parse.urlencode(params)
    if methode == 'GET':
        req = urllib.request.Request(f'{API}/{pfad}?{daten}')
    else:
        req = urllib.request.Request(f'{API}/{pfad}', data=daten.encode(), method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Instagram {pfad}: {e.read().decode(errors="replace")}') from None


def konto():
    return _call('GET', 'me', fields='user_id,username')


def story_posten(bild_url):
    """Legt einen Story-Container an, wartet bis Instagram das Bild verarbeitet hat, und veröffentlicht ihn."""
    user = konto()['user_id']
    container = _call('POST', f'{user}/media', image_url=bild_url, media_type='STORIES')['id']
    for _ in range(30):
        status = _call('GET', container, fields='status_code').get('status_code')
        if status == 'FINISHED':
            break
        if status in ('ERROR', 'EXPIRED'):
            raise RuntimeError(f'Instagram konnte das Bild nicht verarbeiten ({status})')
        time.sleep(4)
    return _call('POST', f'{user}/media_publish', creation_id=container)['id']


def token_verlaengern():
    """Verlängert den Token um 60 Tage. Gibt (neuer_token, tage_gueltig) zurück."""
    alt = umgebung.wert('INSTAGRAM_TOKEN')
    url = 'https://graph.instagram.com/refresh_access_token?' + urllib.parse.urlencode(
        {'grant_type': 'ig_refresh_token', 'access_token': alt})
    with urllib.request.urlopen(url, timeout=60) as r:
        res = json.loads(r.read())
    return res['access_token'], res.get('expires_in', 0) // 86400
