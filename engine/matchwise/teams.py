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


def canonical(name: str, known: set[str]) -> str | None:
    """football-data.co.uk name for a fixturedownload.com name, or None if unknown."""
    name = name.strip()
    if name in known:
        return name
    alias = ALIASES.get(name)
    return alias if alias in known else None
