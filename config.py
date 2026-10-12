"""Welche Spiele eine Story bekommen und wie Vereine auf Deutsch heißen.

Quelle ist die (inoffizielle, kostenlose) ESPN-Scoreboard-API.

Morgens kommen alle Spiele des Tages aus WETTBEWERBE als Story zur Auswahl (bei `angebot` nur die passenden).
`regeln` bestimmt, welche davon als „⭐ Empfohlen“ markiert und zuerst geschickt werden.
Ein Spiel ist empfohlen, sobald eine Regel zutrifft:
  - 'alle'        jedes Spiel
  - 'vfb'         Spiele mit dem VfB
  - 'topspiel'    beide Vereine stehen in TOPVEREINE (z. B. Bayern gegen Dortmund)
  - 'deutsch'     Spiele mit einem Verein aus der 1. oder 2. Bundesliga
  - 'deutschland' Spiele der Nationalmannschaft
  - 'topnation'   mindestens eine Mannschaft steht in TOPNATIONEN
Dazu `alle_ab`: ab diesen Runden (ESPN-Slug) zählt jedes Spiel, z. B. ab dem Achtelfinale.
"""

VFB_ID = '134'
DEUTSCHLAND = 'Germany'

# ESPN-IDs: Bayern, Dortmund, Leverkusen, Leipzig, Frankfurt. Spiele zwischen zweien davon sind Topspiele.
TOPVEREINE = {'132', '124', '131', '11420', '125'}

# Bei WM und EM in der Gruppenphase: Spiele mit mindestens einer dieser Nationen (ESPN-Namen).
TOPNATIONEN = {'Spain', 'France', 'England', 'Brazil', 'Argentina', 'Portugal', 'Netherlands', 'Italy',
               'Belgium', 'Croatia'}

# Publikumsmagneten (ESPN-Namen): Ihre Spiele stehen bei gleicher Empfehlung weiter oben,
# morgens in der Reihenfolge und in Listen-Stories („Heute Champions League“).
BELIEBTE = {'Bayern Munich', 'Borussia Dortmund', 'VfB Stuttgart', 'Bayer Leverkusen', 'RB Leipzig', 'Eintracht Frankfurt',
            'Real Madrid', 'Barcelona', 'Atletico Madrid', 'Atlético Madrid', 'Paris Saint-Germain', 'Manchester City',
            'Liverpool', 'Arsenal', 'Manchester United', 'Chelsea', 'Tottenham Hotspur', 'Internazionale', 'Juventus',
            'AC Milan', 'Napoli', 'Galatasaray', 'Fenerbahce', 'Besiktas', 'Benfica', 'FC Porto',
            'Germany', 'Spain', 'France', 'England', 'Brazil', 'Argentina', 'Portugal', 'Netherlands', 'Italy', 'Turkey',
            'Türkiye', 'Croatia', 'Greece'}

KO_AB_ACHTELFINALE = ['round-of-16', 'quarterfinals', 'semifinals', '3rd-place-match', 'final']
KO_AB_VIERTELFINALE = ['quarterfinals', 'semifinals', '3rd-place-match', 'final']

# Reihenfolge = Priorität, falls an einem Tag mehr als MAX_PRO_TAG Spiele zusammenkommen.
# Innerhalb eines Wettbewerbs gehen VfB-, Deutschland- und Spiele deutscher Vereine vor.
WETTBEWERBE = [
    {'slug': 'ger.1', 'name': 'Bundesliga', 'regeln': ['vfb', 'topspiel']},
    {'slug': 'ger.playoff.relegation', 'name': 'Relegation', 'regeln': ['alle']},
    {'slug': 'ger.2.promotion.relegation', 'name': 'Relegation', 'regeln': ['alle']},
    {'slug': 'fifa.world', 'name': 'Weltmeisterschaft', 'regeln': ['deutschland', 'topnation'], 'alle_ab': KO_AB_ACHTELFINALE},
    {'slug': 'uefa.euro', 'name': 'Europameisterschaft', 'regeln': ['deutschland', 'topnation'], 'alle_ab': KO_AB_ACHTELFINALE},
    {'slug': 'ger.dfb_pokal', 'name': 'DFB-Pokal', 'regeln': ['vfb'], 'alle_ab': KO_AB_ACHTELFINALE},
    {'slug': 'uefa.champions', 'name': 'Champions League', 'regeln': ['deutsch'], 'alle_ab': KO_AB_ACHTELFINALE},
    {'slug': 'uefa.europa', 'name': 'Europa League', 'regeln': ['deutsch'], 'alle_ab': KO_AB_VIERTELFINALE},
    # Die Nations League hat kein Achtelfinale, die K.-o.-Phase beginnt mit dem Viertelfinale.
    {'slug': 'uefa.nations', 'name': 'Nations League', 'regeln': ['deutschland'], 'alle_ab': KO_AB_VIERTELFINALE,
     'angebot': ['deutschland', 'topnation']},
    {'slug': 'fifa.worldq.uefa', 'name': 'WM-Qualifikation', 'regeln': ['deutschland'], 'angebot': ['deutschland', 'topnation']},
    {'slug': 'uefa.euroq', 'name': 'EM-Qualifikation', 'regeln': ['deutschland'], 'angebot': ['deutschland', 'topnation']},
]

# Höchstens so viele Stories kommen morgens (empfohlene zuerst).
MAX_PRO_TAG = 20

# Nur für die Suche per Telegram-Nachricht, morgens kommen sie nicht automatisch.
SUCH_WETTBEWERBE = [
    {'slug': 'ger.2', 'name': '2. Bundesliga'},
    {'slug': 'eng.1', 'name': 'Premier League'},
    {'slug': 'esp.1', 'name': 'La Liga'},
    {'slug': 'ita.1', 'name': 'Serie A'},
    {'slug': 'fra.1', 'name': 'Ligue 1'},
    {'slug': 'tur.1', 'name': 'Süper Lig'},
    {'slug': 'uefa.europa.conf', 'name': 'Conference League'},
    {'slug': 'fifa.friendly', 'name': 'Länderspiel'},
]

# Wettbewerb per Nachricht abrufen („Champions League“, „alle Bundesliga Spiele“): Name -> ESPN-Slug.
# Reihenfolge = Reihenfolge der Knöpfe bei /ligen (erster Eintrag pro Slug ist der Knopftext).
LIGEN = {
    'Bundesliga': 'ger.1', 'buli': 'ger.1', 'bl': 'ger.1', '1 bundesliga': 'ger.1',
    '2. Bundesliga': 'ger.2', '2 liga': 'ger.2', 'zweite liga': 'ger.2', '2 bundesliga': 'ger.2',
    'DFB-Pokal': 'ger.dfb_pokal', 'pokal': 'ger.dfb_pokal', 'dfb pokal': 'ger.dfb_pokal',
    'Champions League': 'uefa.champions', 'cl': 'uefa.champions', 'champions': 'uefa.champions', 'ucl': 'uefa.champions',
    'Europa League': 'uefa.europa', 'el': 'uefa.europa', 'europa': 'uefa.europa',
    'Conference League': 'uefa.europa.conf', 'conference': 'uefa.europa.conf', 'ecl': 'uefa.europa.conf',
    'Premier League': 'eng.1', 'pl': 'eng.1', 'england liga': 'eng.1',
    'La Liga': 'esp.1', 'laliga': 'esp.1', 'spanien liga': 'esp.1',
    'Serie A': 'ita.1', 'italien liga': 'ita.1',
    'Ligue 1': 'fra.1', 'frankreich liga': 'fra.1',
    'Süper Lig': 'tur.1', 'super lig': 'tur.1', 'turkei liga': 'tur.1', 'tuerkei liga': 'tur.1',
    'Relegation': 'ger.playoff.relegation',
    'WM': 'fifa.world', 'weltmeisterschaft': 'fifa.world',
    'EM': 'uefa.euro', 'europameisterschaft': 'uefa.euro',
    'Nations League': 'uefa.nations', 'nations': 'uefa.nations',
    'WM-Quali': 'fifa.worldq.uefa', 'wm quali': 'fifa.worldq.uefa', 'wm qualifikation': 'fifa.worldq.uefa',
    'EM-Quali': 'uefa.euroq', 'em quali': 'uefa.euroq', 'em qualifikation': 'uefa.euroq',
    'Länderspiele': 'fifa.friendly', 'landerspiele': 'fifa.friendly', 'testspiele': 'fifa.friendly',
}
# Wörter, die beim Abruf eines Wettbewerbs ignoriert werden („zeig mir alle Spiele der Champions League“)
LISTEN_WOERTER = {'alle', 'spiele', 'spiel', 'liste', 'zeig', 'zeige', 'mir', 'der', 'die', 'das', 'aus', 'in',
                  'von', 'heute', 'diese', 'woche', 'bitte', 'naechste', 'nachste'}

# Spitznamen in Suchanfragen -> Wort, das im Vereinsnamen vorkommt
KUERZEL = {
    'gala': 'galatasaray', 'barca': 'barcelona', 'bvb': 'dortmund', 'fcb': 'bayern', 'hsv': 'hamburg',
    'sge': 'frankfurt', 'b04': 'leverkusen', 'bayer': 'leverkusen', 'rbl': 'leipzig', 'gladbach': 'gladbach',
    'fener': 'fenerbahce', 'bjk': 'besiktas', 'psg': 'paris', 'manu': 'manchester united', 'city': 'manchester city',
    'juve': 'juventus', 'inter': 'inter', 'milan': 'milan', 'atletico': 'atletico', 'koeln': 'koln', 'muenchen': 'munchen',
    'dfb': 'deutschland', 'nati': 'deutschland',
}
FUELLWOERTER = {'gegen', 'vs', 'v', 'und', 'spiel', 'story', 'fc', 'the', 'bitte', 'mach', 'mal', 'eine', 'fur', 'fuer'}

# Runden-Slugs von ESPN -> Untertitel auf der Story
RUNDEN = {
    'league-phase': 'Ligaphase',
    'group-stage': 'Gruppenphase',
    'knockout-round-playoffs': 'Play-offs',
    'first-round': '1. Runde',
    'second-round': '2. Runde',
    'round-of-32': 'Sechzehntelfinale',
    'round-of-16': 'Achtelfinale',
    'quarterfinals': 'Viertelfinale',
    'semifinals': 'Halbfinale',
    '3rd-place-match': 'Spiel um Platz 3',
    'final': 'Finale',
}

# ESPN-Namen -> Name auf der Story. Nicht aufgeführte Namen werden unverändert übernommen.
NAMEN = {
    # Vereine
    'Bayern Munich': 'FC Bayern München',
    'FC Cologne': '1. FC Köln',
    'Hamburg SV': 'Hamburger SV',
    'Borussia Monchengladbach': "Borussia M'gladbach",
    'Borussia Mönchengladbach': "Borussia M'gladbach",
    'Mainz': '1. FSV Mainz 05',
    'Schalke 04': 'FC Schalke 04',
    'Werder Bremen': 'SV Werder Bremen',
    'Hertha Berlin': 'Hertha BSC',
    'Kaiserslautern': '1. FC Kaiserslautern',
    'St. Pauli': 'FC St. Pauli',
    'VfL Osnabruck': 'VfL Osnabrück',
    'SpVgg Greuther Fürth': 'Greuther Fürth',
    'TSV Eintracht Braunschweig': 'Eintracht Braunschweig',
    '1. FC Heidenheim 1846': '1. FC Heidenheim',
    'Internazionale': 'Inter Mailand',
    'AC Milan': 'AC Mailand',
    'Juventus': 'Juventus Turin',
    'Napoli': 'SSC Neapel',
    'AS Roma': 'AS Rom',
    'Lazio': 'Lazio Rom',
    'Sporting CP': 'Sporting Lissabon',
    'Benfica': 'Benfica Lissabon',
    'FC Porto': 'FC Porto',
    'Red Bull Salzburg': 'RB Salzburg',
    'Club Brugge': 'FC Brügge',
    'Fenerbahce': 'Fenerbahçe',
    'Besiktas': 'Beşiktaş',
    'Atletico Madrid': 'Atlético Madrid',
    'Sevilla': 'FC Sevilla',
    'Valencia': 'FC Valencia',
    'Barcelona': 'FC Barcelona',
    'Paris Saint-Germain': 'Paris Saint-Germain',
    'Tottenham Hotspur': 'Tottenham',
    'Copenhagen': 'FC Kopenhagen',
    'Bodo/Glimt': 'Bodø/Glimt',
    'Slavia Prague': 'Slavia Prag',
    'Sparta Prague': 'Sparta Prag',
    'Shakhtar Donetsk': 'Schachtar Donezk',
    'Dinamo Zagreb': 'Dinamo Zagreb',
    'Celtic': 'Celtic Glasgow',
    'Rangers': 'Glasgow Rangers',
    'Olympiacos': 'Olympiakos Piräus',
    'PAOK Salonika': 'PAOK Thessaloniki',
    'Basel': 'FC Basel',
    'Young Boys': 'Young Boys Bern',
    # Nationalteams
    'Germany': 'Deutschland',
    'Austria': 'Österreich',
    'Switzerland': 'Schweiz',
    'France': 'Frankreich',
    'Spain': 'Spanien',
    'Italy': 'Italien',
    'England': 'England',
    'Netherlands': 'Niederlande',
    'Belgium': 'Belgien',
    'Denmark': 'Dänemark',
    'Sweden': 'Schweden',
    'Norway': 'Norwegen',
    'Finland': 'Finnland',
    'Iceland': 'Island',
    'Poland': 'Polen',
    'Czechia': 'Tschechien',
    'Czech Republic': 'Tschechien',
    'Slovakia': 'Slowakei',
    'Slovenia': 'Slowenien',
    'Hungary': 'Ungarn',
    'Romania': 'Rumänien',
    'Bulgaria': 'Bulgarien',
    'Greece': 'Griechenland',
    'Türkiye': 'Türkei',
    'Turkey': 'Türkei',
    'Croatia': 'Kroatien',
    'Serbia': 'Serbien',
    'Bosnia-Herzegovina': 'Bosnien-Herzegowina',
    'Montenegro': 'Montenegro',
    'North Macedonia': 'Nordmazedonien',
    'Albania': 'Albanien',
    'Kosovo': 'Kosovo',
    'Ukraine': 'Ukraine',
    'Russia': 'Russland',
    'Belarus': 'Belarus',
    'Lithuania': 'Litauen',
    'Latvia': 'Lettland',
    'Estonia': 'Estland',
    'Scotland': 'Schottland',
    'Wales': 'Wales',
    'Northern Ireland': 'Nordirland',
    'Republic of Ireland': 'Irland',
    'Ireland': 'Irland',
    'Cyprus': 'Zypern',
    'Georgia': 'Georgien',
    'Armenia': 'Armenien',
    'Azerbaijan': 'Aserbaidschan',
    'Luxembourg': 'Luxemburg',
    'Liechtenstein': 'Liechtenstein',
    'Malta': 'Malta',
    'Faroe Islands': 'Färöer',
    'Moldova': 'Moldau',
    'Israel': 'Israel',
    'Kazakhstan': 'Kasachstan',
    'Brazil': 'Brasilien',
    'Argentina': 'Argentinien',
    'Uruguay': 'Uruguay',
    'Colombia': 'Kolumbien',
    'Mexico': 'Mexiko',
    'United States': 'USA',
    'USA': 'USA',
    'Canada': 'Kanada',
    'Japan': 'Japan',
    'South Korea': 'Südkorea',
    'Saudi Arabia': 'Saudi-Arabien',
    'Morocco': 'Marokko',
    'Egypt': 'Ägypten',
    'Senegal': 'Senegal',
    'Nigeria': 'Nigeria',
    'Ghana': 'Ghana',
    'Cameroon': 'Kamerun',
    'Ivory Coast': 'Elfenbeinküste',
    "Côte d'Ivoire": 'Elfenbeinküste',
    'Tunisia': 'Tunesien',
    'Algeria': 'Algerien',
    'Australia': 'Australien',
    'Iran': 'Iran',
    'Qatar': 'Katar',
    'Congo DR': 'DR Kongo',
    'South Africa': 'Südafrika',
    'New Zealand': 'Neuseeland',
    'Ecuador': 'Ecuador',
    'Paraguay': 'Paraguay',
    'Panama': 'Panama',
    'Haiti': 'Haiti',
    'Jordan': 'Jordanien',
    'Uzbekistan': 'Usbekistan',
    'Cape Verde': 'Kap Verde',
    'Curacao': 'Curaçao',
}

# Stimmungen für den KI-Hintergrund. Pro Story wird eine davon gewählt (abwechselnd).
# Wichtig: keine Schrift, keine Logos, keine erkennbaren Personen, das Bild bleibt reine Kulisse.
STIMMUNGEN = [
    'a packed football stadium at night seen from high in the stands, floodlights glowing through light haze, '
    'pitch in deep green, crowd as soft bokeh',
    'low angle across a wet grass pitch at night, a football small in the bottom left corner, floodlights '
    'reflecting, shallow depth of field, stadium blurred behind',
    'cosy dark cocktail bar interior with a large screen showing a football match out of focus, warm copper lamps, '
    'glasses on a wooden counter in the foreground, no people in focus',
    'empty football stadium tunnel looking out onto a brightly lit pitch at night, dramatic light, mist',
    'aerial view of a football stadium at dusk, city lights around it, deep blue and green sky',
]
STIL = (
    'Cinematic photograph, vertical 9:16, moody and premium, dark tones of racing green and black with warm '
    'copper and cognac highlights, film grain. Darker at the top and bottom thirds so text can sit on top. '
    'Keep the centre of the image calm and uncluttered, no main subject in the middle. '
    'Absolutely no text, no letters, no numbers, no logos, no club crests, no jerseys with names, no watermark.'
)
