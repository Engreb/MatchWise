/* Club colours and short codes for monogram badges (no trademarked crests).
   [code, background, text]. Unknown teams fall back to initials on a neutral colour. */
window.TEAM_META = {
  // Premier League
  'Man City': ['MCI', '#6CABDD', '#0B1F3A'], 'Arsenal': ['ARS', '#EF0107', '#FFFFFF'], 'Liverpool': ['LIV', '#C8102E', '#FFFFFF'],
  'Brighton': ['BHA', '#0057B8', '#FFFFFF'], 'Man United': ['MUN', '#DA291C', '#FFFFFF'], 'Chelsea': ['CHE', '#034694', '#FFFFFF'],
  'Newcastle': ['NEW', '#241F20', '#FFFFFF'], 'Brentford': ['BRE', '#E30613', '#FFFFFF'], 'Aston Villa': ['AVL', '#670E36', '#95BFE5'],
  'Bournemouth': ['BOU', '#B50E12', '#FFFFFF'], 'Leeds': ['LEE', '#FFFFFF', '#1D428A'], "Nott'm Forest": ['NFO', '#DD0000', '#FFFFFF'],
  'Everton': ['EVE', '#003399', '#FFFFFF'], 'Hull': ['HUL', '#F5A12D', '#111111'], 'Fulham': ['FUL', '#FFFFFF', '#111111'],
  'Crystal Palace': ['CRY', '#1B458F', '#FFFFFF'], 'Tottenham': ['TOT', '#132257', '#FFFFFF'], 'Sunderland': ['SUN', '#EB172B', '#FFFFFF'],
  'Coventry': ['COV', '#59CBE8', '#0B2240'], 'Ipswich': ['IPS', '#0044A9', '#FFFFFF'],
  'West Ham': ['WHU', '#7A263A', '#1BB1E7'], 'Wolves': ['WOL', '#FDB913', '#231F20'], 'Burnley': ['BUR', '#6C1D45', '#99D6EA'],
  'Leicester': ['LEI', '#003090', '#FDBE11'], 'Southampton': ['SOU', '#D71920', '#FFFFFF'], 'Sheffield United': ['SHU', '#EE2737', '#FFFFFF'],
  // La Liga
  'Barcelona': ['BAR', '#A50044', '#EDBB00'], 'Real Madrid': ['RMA', '#FFFFFF', '#00529F'], 'Ath Madrid': ['ATM', '#CB3524', '#FFFFFF'],
  'Villarreal': ['VIL', '#FFE667', '#005187'], 'Betis': ['BET', '#0BB363', '#FFFFFF'], 'Ath Bilbao': ['ATH', '#EE2523', '#FFFFFF'],
  'Celta': ['CEL', '#8AC3EE', '#0B2A4A'], 'Sociedad': ['RSO', '#0067B1', '#FFFFFF'], 'Vallecano': ['RAY', '#FFFFFF', '#E53027'],
  'Alaves': ['ALA', '#0761AF', '#FFFFFF'], 'Sevilla': ['SEV', '#FFFFFF', '#D4021D'], 'La Coruna': ['DEP', '#1D5EA8', '#FFFFFF'],
  'Elche': ['ELC', '#05642C', '#FFFFFF'], 'Osasuna': ['OSA', '#D91A21', '#FFFFFF'], 'Levante': ['LEV', '#B4053F', '#FFFFFF'],
  'Getafe': ['GET', '#005999', '#FFFFFF'], 'Valencia': ['VAL', '#FFFFFF', '#111111'], 'Espanol': ['ESP', '#007FC8', '#FFFFFF'],
  'Santander': ['RAC', '#FFFFFF', '#00804A'], 'Malaga': ['MAL', '#4A9BD5', '#FFFFFF'], 'Girona': ['GIR', '#CD2534', '#FFFFFF'],
  'Mallorca': ['MLL', '#E20613', '#111111'], 'Las Palmas': ['LPA', '#FFE400', '#0047AB'], 'Valladolid': ['VLL', '#5B2C83', '#FFFFFF'],
  'Leganes': ['LEG', '#005BAC', '#FFFFFF'], 'Oviedo': ['OVI', '#0055A5', '#FFFFFF'],
  // Serie A
  'Inter': ['INT', '#010E80', '#FFFFFF'], 'Roma': ['ROM', '#8E1F2F', '#F0BC42'], 'Juventus': ['JUV', '#111111', '#FFFFFF'],
  'Como': ['COM', '#0E4C92', '#FFFFFF'], 'Napoli': ['NAP', '#12A0D7', '#FFFFFF'], 'Atalanta': ['ATA', '#1E71B8', '#FFFFFF'],
  'Milan': ['MIL', '#FB090B', '#111111'], 'Lazio': ['LAZ', '#87D8F7', '#0B2A4A'], 'Bologna': ['BOL', '#A21C26', '#FFFFFF'],
  'Fiorentina': ['FIO', '#482E92', '#FFFFFF'], 'Udinese': ['UDI', '#FFFFFF', '#111111'], 'Sassuolo': ['SAS', '#00A752', '#FFFFFF'],
  'Cagliari': ['CAG', '#A6192E', '#FFFFFF'], 'Torino': ['TOR', '#881F19', '#FFFFFF'], 'Genoa': ['GEN', '#A3051F', '#FFFFFF'],
  'Frosinone': ['FRO', '#FFE000', '#0047AB'], 'Parma': ['PAR', '#FFD200', '#1B3A8C'], 'Lecce': ['LEC', '#FFE200', '#D7172F'],
  'Monza': ['MON', '#E30613', '#FFFFFF'], 'Venezia': ['VEN', '#111111', '#F26522'], 'Empoli': ['EMP', '#005CA9', '#FFFFFF'],
  'Verona': ['VER', '#FFD500', '#003C82'], 'Pisa': ['PIS', '#111111', '#FFFFFF'], 'Cremonese': ['CRE', '#C8102E', '#9E9E9E'],
  // Bundesliga
  'Bayern Munich': ['FCB', '#DC052D', '#FFFFFF'], 'Dortmund': ['BVB', '#FDE100', '#111111'], 'Leverkusen': ['B04', '#E32221', '#FFFFFF'],
  'RB Leipzig': ['RBL', '#FFFFFF', '#DD0741'], 'Stuttgart': ['VFB', '#FFFFFF', '#E32219'], 'Freiburg': ['SCF', '#111111', '#FFFFFF'],
  'Mainz': ['M05', '#C3141E', '#FFFFFF'], 'Ein Frankfurt': ['SGE', '#111111', '#E1000F'], 'Hoffenheim': ['TSG', '#1C63B7', '#FFFFFF'],
  'Elversberg': ['SVE', '#111111', '#FFFFFF'], 'Augsburg': ['FCA', '#BA3733', '#FFFFFF'], 'Werder Bremen': ['SVW', '#1D9053', '#FFFFFF'],
  'FC Koln': ['KOE', '#FFFFFF', '#ED1C24'], "M'gladbach": ['BMG', '#FFFFFF', '#111111'], 'Hamburg': ['HSV', '#0A3F86', '#FFFFFF'],
  'Union Berlin': ['FCU', '#EB1923', '#FFFFFF'], 'Schalke 04': ['S04', '#004D9D', '#FFFFFF'], 'Paderborn': ['SCP', '#005CA9', '#FFFFFF'],
  'Wolfsburg': ['WOB', '#65B32E', '#FFFFFF'], 'Heidenheim': ['FCH', '#E2001A', '#003B79'], 'St Pauli': ['STP', '#6B4C3B', '#FFFFFF'],
  'Bochum': ['BOC', '#005CA9', '#FFFFFF'], 'Holstein Kiel': ['KSV', '#003D86', '#FFFFFF'],
  // Ligue 1
  'Paris SG': ['PSG', '#004170', '#FFFFFF'], 'Lens': ['RCL', '#FFE600', '#D01D21'], 'Marseille': ['OM', '#2FAEE0', '#FFFFFF'],
  'Lille': ['LIL', '#E01E13', '#FFFFFF'], 'Monaco': ['ASM', '#E51B22', '#FFFFFF'], 'Lyon': ['OL', '#FFFFFF', '#1D3A8F'],
  'Rennes': ['SRF', '#E13327', '#FFFFFF'], 'Paris FC': ['PFC', '#0A1A3C', '#FFFFFF'], 'Strasbourg': ['RCS', '#009FE3', '#FFFFFF'],
  'Toulouse': ['TFC', '#5B2C83', '#FFFFFF'], 'Brest': ['SB29', '#E2001A', '#FFFFFF'], 'Nice': ['NIC', '#C8102E', '#FFFFFF'],
  'Lorient': ['FCL', '#F58113', '#111111'], 'Le Mans': ['LMF', '#D7141A', '#FFDD00'], 'Auxerre': ['AJA', '#FFFFFF', '#0055A4'],
  'Le Havre': ['HAC', '#6CB4E4', '#0A2240'], 'Angers': ['SCO', '#111111', '#FFFFFF'], 'Troyes': ['ETR', '#005BAC', '#FFFFFF'],
  'Nantes': ['FCN', '#FCD405', '#007A3D'], 'Metz': ['FCM', '#8A1538', '#FFFFFF'], 'Montpellier': ['MHSC', '#F58025', '#0B2A5B'],
  'Reims': ['SDR', '#E2001A', '#FFFFFF'], 'St Etienne': ['ASSE', '#009639', '#FFFFFF'],
};

window.teamMeta = function (name) {
  const m = window.TEAM_META[name];
  if (m) return { code: m[0], bg: m[1], fg: m[2] };
  const words = name.replace(/[^A-Za-zÀ-ÿ ]/g, '').split(/\s+/).filter(Boolean);
  const code = (words.length > 1 ? words.map(w => w[0]).join('') : name.slice(0, 3)).slice(0, 3).toUpperCase();
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
  return { code, bg: `hsl(${h} 35% 38%)`, fg: '#FFFFFF' };
};

/* Very light or very dark badges need an outline to stay visible on light/dark surfaces. */
function luma(hex) {
  if (!hex.startsWith('#')) return 0.5;
  const n = parseInt(hex.slice(1), 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}
window.isLightColor = hex => luma(hex) > 0.8;
window.isDarkColor = hex => luma(hex) < 0.12;
