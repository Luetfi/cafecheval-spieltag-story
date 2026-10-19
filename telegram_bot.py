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


def story_senden(bild_url, titel, details, empfohlen=False, chats=None):
    """Schickt die Story (an alle Empfänger oder an `chats`), mit den Knöpfen „Posten“ und „Verwerfen“.
    Gibt die gesendeten Nachrichten zurück (eine pro Empfänger)."""
    stern = '⭐ Empfohlen\n' if empfohlen else ''
    caption = (f'{stern}<b>{html.escape(titel)}</b>\n{html.escape(details)}\n\n'
               f'<a href="{html.escape(bild_url)}">Bild in voller Größe</a>')
    knoepfe = {'inline_keyboard': [[{'text': '✅ Posten', 'callback_data': POSTEN},
                                    {'text': '❌ Verwerfen', 'callback_data': VERWERFEN}]]}
    return [_api('sendPhoto', chat_id=c, photo=bild_url, caption=caption, parse_mode='HTML', reply_markup=knoepfe)
            for c in (chats or empfaenger())]


KURZ = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']


def auswahl_senden(chat, spiele, ueberschrift='Welches Spiel meinst du?'):
    """Ein Knopf pro Spiel. callback_data = s|Wettbewerb|ESPN-Datum|Event-ID (max. 64 Byte, Telegram erlaubt 100 Knöpfe)."""
    knoepfe = [[{'text': f"{KURZ[s['anstoss'].weekday()]} {s['anstoss']:%d.%m. %H:%M}  {s['heim']['name']} – {s['gast']['name']}"[:64],
                 'callback_data': f"s|{s['slug']}|{s['datum']}|{s['id']}"}] for s in spiele]
    _api('sendMessage', chat_id=chat, text=ueberschrift, parse_mode='HTML', reply_markup={'inline_keyboard': knoepfe})


def vorlagen_senden(chat, knoepfe_):
    """Knöpfe für allgemeine Stories, einer pro Zeile. callback_data = a|Schlüssel."""
    zeilen = [[{'text': text, 'callback_data': f'a|{k}'}] for text, k in knoepfe_]
    _api('sendMessage', chat_id=chat, text='Welche Story soll ich erstellen?', reply_markup={'inline_keyboard': zeilen})


def ligen_senden(chat, ligen):
    """Knöpfe für alle Wettbewerbe, zwei pro Zeile. callback_data = l|Slug."""
    knoepfe = [{'text': text, 'callback_data': f'l|{slug}'} for text, slug in ligen]
    zeilen = [knoepfe[i:i + 2] for i in range(0, len(knoepfe), 2)]
    _api('sendMessage', chat_id=chat, text='Welcher Wettbewerb?', reply_markup={'inline_keyboard': zeilen})


def info_senden(bild_url, text_html):
    """Bild mit Text, ohne Knöpfe, an alle Empfänger (z. B. „Automatisch gepostet“)."""
    for c in empfaenger():
        try:
            _api('sendPhoto', chat_id=c, photo=bild_url, caption=text_html, parse_mode='HTML')
        except RuntimeError as e:
            print('Warnung:', e)


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
            daten = q.get('data', '')
            aktion = {'s|': 'spiel', 'l|': 'liga', 'a|': 'allgemein'}.get(daten[:2], daten)
            ergebnis.append({'aktion': aktion, 'daten': daten,
                             'query_id': q['id'], 'nachricht': q['message'], 'chat': q['message']['chat']['id'],
                             'von': q['from'].get('first_name', '')})
        elif 'message' in u:
            m = u['message']
            chat = m['chat']['id']
            if chat in erlaubt and m.get('text'):
                ergebnis.append({'aktion': 'text', 'text': m['text'], 'chat': chat,
                                 'von': m.get('from', {}).get('first_name', ''),
                                 'antwort_auf': (m.get('reply_to_message') or {}).get('message_id')})
                continue
            # Hilfe beim Einrichten: Wer dem Bot schreibt, bekommt seine Chat-ID zurück.
            try:
                text(f'Deine Chat-ID: <code>{chat}</code> (ist noch nicht freigeschaltet).', chat=chat)
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


def tippt(chat):
    """Zeigt in Telegram „schreibt …“ an, solange der Bot arbeitet (hält ca. 5 Sekunden)."""
    try:
        _api('sendChatAction', chat_id=chat, action='typing')
    except RuntimeError:
        pass


def knoepfe_entfernen(nachricht):
    try:
        _api('editMessageReplyMarkup', chat_id=nachricht['chat']['id'], message_id=nachricht['message_id'],
             reply_markup={'inline_keyboard': []})
    except RuntimeError:
        pass


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
