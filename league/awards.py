from statistics import pstdev

from .badges import MIN_GAMES
from .models import Match, Player

MIN_STREAK = 3
MIN_MARGIN = 4


def _holders(scores, best):
    """Giocatori a pari merito sul valore migliore (best = max o min); scores = {player: valore}."""
    if not scores:
        return [], None
    top = best(round(v, 6) for v in scores.values())
    return [p for p, v in scores.items() if round(v, 6) == top], top


def awards():
    """Premi che cambiano di mano a ogni partita: [{icon, title, desc, holders, detail}]."""
    players = {p.id: p for p in Player.objects.all()}
    st = {pid: {'games': 0, 'gf': 0, 'ga': 0, 'gds': [], 'res': []} for pid in players}
    biggest = None  # (scarto, gol vincitore, gol perdente, vincitori, sconfitti)
    matches = (Match.objects.filter(played=True).order_by('scheduled_at', 'id')
               .prefetch_related('team1', 'team2'))
    for m in matches:
        for team, gf, ga in ((m.team1.all(), m.score1, m.score2), (m.team2.all(), m.score2, m.score1)):
            for p in team:
                s = st[p.id]
                s['games'] += 1
                s['gf'] += gf
                s['ga'] += ga
                s['gds'].append(gf - ga)
                s['res'].append('w' if gf > ga else ('l' if gf < ga else 'd'))
        margin = abs(m.score1 - m.score2)
        if margin >= MIN_MARGIN and (biggest is None or margin >= biggest[0]):  # a parità vince il più recente
            win1 = m.score1 > m.score2
            biggest = (margin, max(m.score1, m.score2), min(m.score1, m.score2),
                       list(m.team1.all() if win1 else m.team2.all()), list(m.team2.all() if win1 else m.team1.all()))

    out = []
    regulars = {players[pid]: s for pid, s in st.items() if s['games'] >= MIN_GAMES}

    holders, v = _holders({p: s['ga'] / s['games'] for p, s in regulars.items()}, min)
    if holders:
        out.append({'icon': '🧱', 'title': 'Il Muro', 'holders': holders,
                    'desc': 'Meno gol subiti a partita', 'detail': f'{v:.2f} subiti a partita'})
    holders, v = _holders({p: s['gf'] / s['games'] for p, s in regulars.items()}, max)
    if holders:
        out.append({'icon': '💣', 'title': 'Il Cannoniere', 'holders': holders,
                    'desc': 'Più gol fatti a partita', 'detail': f'{v:.2f} fatti a partita'})
    holders, v = _holders({p: pstdev(s['gds']) for p, s in regulars.items()}, max)
    if holders and v > 0:
        out.append({'icon': '🎢', 'title': 'Montagne russe', 'holders': holders,
                    'desc': 'Il più imprevedibile: risultati ora enormi, ora disastrosi',
                    'detail': f'scarto reti ±{v:.1f}'})

    def run(res):
        n = 0
        for r in reversed(res):
            if r != res[-1]:
                break
            n += 1
        return n

    for kind, icon, title, desc, unit in (
            ('w', '🔥', 'In fiamma', 'Serie aperta di vittorie', 'vittorie di fila'),
            ('l', '🪦', 'In caduta libera', 'Serie aperta di sconfitte', 'sconfitte di fila')):
        runs = {players[pid]: run(s['res']) for pid, s in st.items() if s['res'] and s['res'][-1] == kind}
        holders, v = _holders({p: n for p, n in runs.items() if n >= MIN_STREAK}, max)
        if holders:
            out.append({'icon': icon, 'title': title, 'holders': holders, 'desc': desc, 'detail': f'{int(v)} {unit}'})

    if biggest:
        margin, hi, lo, winners, losers = biggest
        out.append({'icon': '😱', 'title': 'Cappotto', 'holders': winners, 'desc': 'La più grande imbarcata della lega',
                    'detail': f'{hi}-{lo} contro ' + ' + '.join(p.name for p in losers)})
    return out
