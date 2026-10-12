"""Telegram-Bot für die Freigabe: schickt Stories mit Knöpfen und liest später die Entscheidungen aus.

Der öffentliche Bild-Link steckt als Link in der Bildunterschrift. Drückt jemand „Posten“, liefert
Telegram die Nachricht samt Link mit, deshalb muss zwischen zwei Läufen nichts gespeichert werden.
"""
import html
import json
import urllib.parse
import urllib.request

import umgebung

POSTEN, VERWERFEN = 'posten', 'verwerfen'


def _api(methode, **params):
    token = umgebung.wert('TELEGRAM_BOT_TOKEN')
    daten = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items() if v is not None}
    req = urllib.request.Request(f'https://api.telegram.org/bot{token}/{methode}',
                                 data=urllib.parse.urlencode(daten).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())['result']
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Telegram {methode}: {e.read().decode(errors="replace")}') from None


def empfaenger():
    return [int(x) for x in umgebung.wert('TELEGRAM_CHAT_IDS').replace(';', ',').split(',') if x.strip()]


def text(nachricht, chat=None):
    for c in ([chat] if chat else empfaenger()):
        _api('sendMessage', chat_id=c, text=nachricht, parse_mode='HTML', disable_web_page_preview=True)


def story_senden(bild_url, titel, details):
    """Schickt die Story an alle Empfänger, mit den Knöpfen „Posten“ und „Verwerfen“.
    Gibt die gesendeten Nachrichten zurück (eine pro Empfänger)."""
    caption = (f'<b>{html.escape(titel)}</b>\n{html.escape(details)}\n\n'
               f'<a href="{html.escape(bild_url)}">Bild in voller Größe</a>')
    knoepfe = {'inline_keyboard': [[{'text': '✅ Posten', 'callback_data': POSTEN},
                                    {'text': '❌ Verwerfen', 'callback_data': VERWERFEN}]]}
    return [_api('sendPhoto', chat_id=c, photo=bild_url, caption=caption, parse_mode='HTML', reply_markup=knoepfe)
            for c in empfaenger()]


def bild_url(nachricht):
    for e in nachricht.get('caption_entities', []):
        if e.get('type') == 'text_link':
            return e['url']
    return None


def entscheidungen(warten=0):
    """Liest neue Knopfdrücke und Nachrichten. Gibt (Liste der Entscheidungen, Bestätigungs-Funktion) zurück.
    Mit `warten` (Sekunden, höchstens 50) hält Telegram die Anfrage offen, bis etwas passiert (Long Polling).
    Erst nach dem Bestätigen gelten die Updates bei Telegram als abgeholt."""
    updates = _api('getUpdates', timeout=max(0, min(int(warten), 50)), allowed_updates=['message', 'callback_query'])
    erlaubt = set(empfaenger())
    ergebnis = []
    for u in updates:
        if 'callback_query' in u:
            q = u['callback_query']
            if q['from']['id'] not in erlaubt and q['message']['chat']['id'] not in erlaubt:
                continue
            ergebnis.append({'aktion': q['data'], 'query_id': q['id'], 'nachricht': q['message'],
                             'von': q['from'].get('first_name', '')})
        elif 'message' in u:
            m = u['message']
            chat = m['chat']['id']
            # Hilfe beim Einrichten: Wer dem Bot schreibt, bekommt seine Chat-ID zurück.
            status = 'ist freigeschaltet' if chat in erlaubt else 'ist noch nicht freigeschaltet'
            try:
                text(f'Deine Chat-ID: <code>{chat}</code> ({status}).', chat=chat)
            except RuntimeError:
                pass

    def bestaetigen():
        if updates:
            _api('getUpdates', offset=updates[-1]['update_id'] + 1, timeout=0)

    return ergebnis, bestaetigen


def antworten(query_id, hinweis):
    try:
        _api('answerCallbackQuery', callback_query_id=query_id, text=hinweis)
    except RuntimeError:
        pass  # ältere Knopfdrücke lassen sich nicht mehr beantworten, das ist egal


def abschliessen(nachricht, vermerk):
    """Entfernt die Knöpfe und hängt einen Vermerk an die Bildunterschrift."""
    caption = html.escape(nachricht.get('caption', '').split('\n\n')[0])
    url = bild_url(nachricht)
    link = f'\n\n<a href="{html.escape(url)}">Bild in voller Größe</a>' if url else ''
    try:
        _api('editMessageCaption', chat_id=nachricht['chat']['id'], message_id=nachricht['message_id'],
             caption=f'{caption}{link}\n\n{html.escape(vermerk)}', parse_mode='HTML',
             reply_markup={'inline_keyboard': []})
    except RuntimeError as e:
        print('Warnung:', e)
