"""Explicit team-name mapping from fixturedownload.com to football-data.co.uk names.

Names are never fuzzy-matched: a team missing here (and not already spelled the same in both
sources) leaves its fixture "unable to assess" until an alias is added.
"""

ALIASES = {
    # Premier League
    "Man Utd": "Man United",
    "Spurs": "Tottenham",
    "Nott'm Forest": "Nott'm Forest",
    "Nottingham Forest": "Nott'm Forest",
    "Wolves": "Wolves",
    "Newcastle Utd": "Newcastle",
    "Sheffield Utd": "Sheffield United",
    "Coventry City": "Coventry",
    "Hull City": "Hull",
    "Ipswich Town": "Ipswich",
    "Leicester City": "Leicester",
    "Luton Town": "Luton",
    "Norwich City": "Norwich",
    "Cardiff City": "Cardiff",
    "Stoke City": "Stoke",
    "Swansea City": "Swansea",
    # Serie A
    "Internazionale": "Inter",
    "AC Milan": "Milan",
    # La Liga
    "Athletic Club": "Ath Bilbao",
    "Atlético de Madrid": "Ath Madrid",
    "CA Osasuna": "Osasuna",
    "Deportivo Alavés": "Alaves",
    "Elche CF": "Elche",
    "FC Barcelona": "Barcelona",
    "Getafe CF": "Getafe",
    "Levante UD": "Levante",
    "Málaga CF": "Malaga",
    "R. Racing Club": "Santander",
    "RC Deportivo": "La Coruna",
    "RCD Espanyol de Barcelona": "Espanol",
    "RCD Mallorca": "Mallorca",
    "Rayo Vallecano": "Vallecano",
    "Real Betis": "Betis",
    "Real Sociedad": "Sociedad",
    "Real Valladolid CF": "Valladolid",
    "Real Oviedo": "Oviedo",
    "Sevilla FC": "Sevilla",
    "Valencia CF": "Valencia",
    "Villarreal CF": "Villarreal",
    "Girona FC": "Girona",
    "RC Celta": "Celta",
    "UD Las Palmas": "Las Palmas",
    "CD Leganés": "Leganes",
    # Bundesliga
    "1. FC Köln": "FC Koln",
    "1. FC Union Berlin": "Union Berlin",
    "1. FSV Mainz 05": "Mainz",
    "1. FC Heidenheim 1846": "Heidenheim",
    "Bayer 04 Leverkusen": "Leverkusen",
    "Borussia Dortmund": "Dortmund",
    "Borussia Mönchengladbach": "M'gladbach",
    "Eintracht Frankfurt": "Ein Frankfurt",
    "FC Augsburg": "Augsburg",
    "FC Bayern München": "Bayern Munich",
    "FC Schalke 04": "Schalke 04",
    "FC St. Pauli": "St Pauli",
    "Hamburger SV": "Hamburg",
    "Holstein Kiel": "Holstein Kiel",
    "SC Paderborn 07": "Paderborn",
    "SV Elversberg": "Elversberg",
    "SV Werder Bremen": "Werder Bremen",
    "Sport-Club Freiburg": "Freiburg",
    "TSG Hoffenheim": "Hoffenheim",
    "VfB Stuttgart": "Stuttgart",
    "VfL Wolfsburg": "Wolfsburg",
    "VfL Bochum 1848": "Bochum",
    # Ligue 1
    "AJ Auxerre": "Auxerre",
    "AS Monaco": "Monaco",
    "AS Saint-Étienne": "St Etienne",
    "Angers SCO": "Angers",
    "Estac Troyes": "Troyes",
    "FC Lorient": "Lorient",
    "FC Metz": "Metz",
    "FC Nantes": "Nantes",
    "Havre Athletic Club": "Le Havre",
    "LOSC Lille": "Lille",
    "Le Mans FC": "Le Mans",
    "Montpellier HSC": "Montpellier",
    "OGC Nice": "Nice",
    "Olympique Lyonnais": "Lyon",
    "Olympique de Marseille": "Marseille",
    "Paris Saint-Germain": "Paris SG",
    "Paris FC": "Paris FC",
    "RC Lens": "Lens",
    "RC Strasbourg Alsace": "Strasbourg",
    "Stade Brestois 29": "Brest",
    "Stade de Reims": "Reims",
    "Stade Rennais FC": "Rennes",
    "Toulouse FC": "Toulouse",
}


# The Odds API spellings (only those that differ from the entries above).
ALIASES.update({
    # Premier League
    "Manchester City": "Man City", "Manchester United": "Man United", "Tottenham Hotspur": "Tottenham",
    "Brighton and Hove Albion": "Brighton", "Newcastle United": "Newcastle", "Leeds United": "Leeds",
    "Wolverhampton Wanderers": "Wolves", "West Ham United": "West Ham", "AFC Bournemouth": "Bournemouth",
    "Leicester City": "Leicester",
    # La Liga
    "Athletic Bilbao": "Ath Bilbao", "Atlético Madrid": "Ath Madrid", "Real Racing Club de Santander": "Santander", "Atletico Madrid": "Ath Madrid",
    "Celta Vigo": "Celta", "Alavés": "Alaves", "Espanyol": "Espanol", "Racing Santander": "Santander",
    "Deportivo La Coruña": "La Coruna", "Deportivo La Coruna": "La Coruna", "Málaga": "Malaga",
    # Serie A
    "Inter Milan": "Inter", "AS Roma": "Roma", "Atalanta BC": "Atalanta", "Hellas Verona": "Verona",
    # Bundesliga
    "Borussia Monchengladbach": "M'gladbach", "Borussia Mönchengladbach": "M'gladbach",
    "SC Freiburg": "Freiburg", "FSV Mainz 05": "Mainz", "Mainz 05": "Mainz", "Bayer Leverkusen": "Leverkusen",
    "Werder Bremen": "Werder Bremen", "Augsburg": "Augsburg", "1. FC Heidenheim": "Heidenheim",
    "SC Paderborn": "Paderborn", "Schalke 04": "Schalke 04", "1. FC Union Berlin": "Union Berlin",
    "Eintracht Frankfurt": "Ein Frankfurt", "VfL Wolfsburg": "Wolfsburg", "FC St. Pauli": "St Pauli",
    # Ligue 1
    "Paris Saint Germain": "Paris SG", "RC Lens": "Lens", "AS Monaco": "Monaco", "Olympique Marseille": "Marseille",
    "Olympique Lyonnais": "Lyon", "Stade Rennais": "Rennes", "Stade Brestois 29": "Brest", "Brest": "Brest",
    "RC Strasbourg": "Strasbourg", "Le Havre AC": "Le Havre", "Saint Etienne": "St Etienne",
})


# Championship, Scottish Premiership, Eredivisie and Primeira Liga (schedule + odds spellings).
ALIASES.update({
    # Championship
    "Birmingham City": "Birmingham", "Blackburn Rovers": "Blackburn", "Bolton Wanderers": "Bolton",
    "Charlton Athletic": "Charlton", "Derby County": "Derby", "Lincoln City": "Lincoln",
    "Preston North End": "Preston", "Queens Park Rangers": "QPR", "West Bromwich Albion": "West Brom",
    "Wrexham AFC": "Wrexham", "Sheffield Wednesday": "Sheffield Weds", "Oxford United": "Oxford",
    "Plymouth Argyle": "Plymouth", "Hull City": "Hull", "Coventry City": "Coventry",
    # Scottish Premiership
    "Heart of Midlothian": "Hearts", "St. Johnstone": "St Johnstone", "St. Mirren": "St Mirren",
    "Ross County": "Ross County", "Dundee FC": "Dundee", "Livingston": "Livingston",
    # Eredivisie
    "ADO Den Haag": "Den Haag", "AZ": "AZ Alkmaar", "Excelsior Rotterdam": "Excelsior", "FC Groningen": "Groningen",
    "FC Twente": "Twente", "FC Utrecht": "Utrecht", "Fortuna Sittard": "For Sittard", "N.E.C. Nijmegen": "Nijmegen",
    "NEC Nijmegen": "Nijmegen", "PEC Zwolle": "Zwolle", "PSV": "PSV Eindhoven", "SC Cambuur": "Cambuur",
    "sc Heerenveen": "Heerenveen", "SC Heerenveen": "Heerenveen", "NAC Breda": "Breda", "Heracles Almelo": "Heracles",
    "Willem II Tilburg": "Willem II", "FC Volendam": "Volendam", "Almere City FC": "Almere City",
    # Primeira Liga
    "Académico": "Academico Viseu", "CD Nacional": "Nacional", "Casa Pia AC": "Casa Pia",
    "Estoril Praia": "Estoril", "Estrela Amadora": "Estrela", "FC Alverca": "Alverca", "FC Arouca": "Arouca",
    "FC Famalicão": "Famalicao", "FC Porto": "Porto", "Gil Vicente FC": "Gil Vicente", "Marítimo M.": "Maritimo",
    "Moreirense FC": "Moreirense", "Rio Ave FC": "Rio Ave", "SC Braga": "Sp Braga", "SL Benfica": "Benfica",
    "Sporting CP": "Sp Lisbon", "Vitória SC": "Guimaraes", "Sporting Lisbon": "Sp Lisbon", "Braga": "Sp Braga",
    "Vitoria Guimaraes": "Guimaraes", "Famalicao": "Famalicao", "CF Estrela": "Estrela", "AVS Futebol SAD": "AVS",
    "Boavista Porto": "Boavista", "Farense": "Farense",
})


# League One, League Two, Ligue 2 and Süper Lig (schedule spellings). The other added leagues
# have no full schedule source, so they only use football-data's own names.
ALIASES.update({
    # League One
    "Bradford City": "Bradford", "Burton Albion": "Burton", "Cambridge United": "Cambridge",
    "Doncaster Rovers": "Doncaster", "Huddersfield Town": "Huddersfield", "MK Dons": "Milton Keynes Dons",
    "Mansfield Town": "Mansfield", "Peterborough United": "Peterboro", "Stockport County": "Stockport",
    "Wigan Athletic": "Wigan", "Wycombe Wanderers": "Wycombe",
    # League Two
    "Accrington Stanley": "Accrington", "Bristol Rovers": "Bristol Rvs", "Cheltenham Town": "Cheltenham",
    "Colchester United": "Colchester", "Crewe Alexandra": "Crewe", "Exeter City": "Exeter",
    "Grimsby Town": "Grimsby", "Northampton Town": "Northampton", "Oldham Athletic": "Oldham",
    "Rotherham United": "Rotherham", "Salford City": "Salford", "Shrewsbury Town": "Shrewsbury",
    "Swindon Town": "Swindon", "Tranmere Rovers": "Tranmere", "York City": "York",
    # Ligue 2
    "AS Nancy Lorraine": "Nancy", "Clermont Foot 63": "Clermont", "Dijon FCO": "Dijon",
    "EN Avant Guingamp": "Guingamp", "FC Annecy": "Annecy", "FC Sochaux-Montbéliard": "Sochaux",
    "Grenoble Foot 38": "Grenoble", "Montpellier Hérault SC": "Montpellier", "Red Star FC": "Red Star",
    "Rodez Aveyron Football": "Rodez", "Stade DE Reims": "Reims", "Stade Lavallois MFC": "Laval",
    "US Boulogne CO": "Boulogne", "USL Dunkerque": "Dunkerque",
    # Süper Lig
    "Eyüpspor": "Eyupspor", "Fenerbahçe": "Fenerbahce", "Gençlerbirligi": "Genclerbirligi",
    "Göztepe": "Goztep", "Istanbul Basaksehir": "Buyuksehyr", "Çaykur Rizespor": "Rizespor", "Çorum": "Corum",
})


# Understat spellings (xG history for the top five leagues).
ALIASES.update({
    "Real Valladolid": "Valladolid", "SD Huesca": "Huesca", "Parma Calcio 1913": "Parma",
    "Arminia Bielefeld": "Bielefeld", "Borussia M.Gladbach": "M'gladbach", "FC Cologne": "FC Koln",
    "FC Heidenheim": "Heidenheim", "Greuther Fuerth": "Greuther Furth", "Hertha Berlin": "Hertha",
    "RasenBallsport Leipzig": "RB Leipzig", "St. Pauli": "St Pauli", "Clermont Foot": "Clermont",
    "Saint-Etienne": "St Etienne",
})


def canonical(name: str, known: set[str]) -> str | None:
    """football-data.co.uk name for a fixturedownload.com name, or None if unknown."""
    name = name.strip()
    if name in known:
        return name
    alias = ALIASES.get(name)
    return alias if alias in known else None
