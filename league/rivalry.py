from .models import Match

MIN_H2H = 3  # scontri diretti minimi per eleggere una bestia nera / vittima


def rivalries():
    """{(id_x, id_y): record} dal punto di vista di x, per ogni coppia di giocatori che si è affrontata.

    Conta anche i 2v2 in cui x e y stanno su squadre opposte; i compagni di squadra non sono rivali."""
    table = {}
    matches = (Match.objects.filter(played=True).order_by('scheduled_at', 'id')
               .prefetch_related('team1', 'team2'))
    for m in matches:
        t1, t2 = list(m.team1.all()), list(m.team2.all())
        for mine, theirs, gf, ga in ((t1, t2, m.score1, m.score2), (t2, t1, m.score2, m.score1)):
            res = 'w' if gf > ga else ('l' if gf < ga else 'd')
            for x in mine:
                for y in theirs:
                    r = table.setdefault((x.id, y.id), {'n': 0, 'w': 0, 'd': 0, 'l': 0, 'gf': 0, 'ga': 0, 'games': []})
                    r['n'] += 1
                    r[res] += 1
                    r['gf'] += gf
                    r['ga'] += ga
                    r['games'].append({'date': m.scheduled_at, 'mode': m.mode, 'gf': gf, 'ga': ga, 'res': res})
    for r in table.values():
        r['pct'] = round(100 * (3 * r['w'] + r['d']) / (3 * r['n']))
        r['last'] = r['games'][::-1][:5]
    return table


def rivalry_list(table, by_id):
    """Una riga per coppia (a<b per id), le più giocate per prime."""
    rows = [{'a': by_id[x], 'b': by_id[y], 'rec': r} for (x, y), r in table.items() if x < y and x in by_id and y in by_id]
    rows.sort(key=lambda r: (-r['rec']['n'], r['a'].name.lower(), r['b'].name.lower()))
    return rows


def nemeses(table, by_id):
    """Per ogni giocatore: bestia nera (chi lo batte di più) e vittima preferita, con almeno MIN_H2H scontri."""
    out = []
    for pid, p in by_id.items():
        opp = [(y, r) for (x, y), r in table.items() if x == pid and r['n'] >= MIN_H2H and y in by_id]
        if not opp:
            continue
        worst = min(opp, key=lambda o: (o[1]['pct'], -o[1]['n'], by_id[o[0]].name.lower()))
        best = max(opp, key=lambda o: (o[1]['pct'], o[1]['n'], by_id[o[0]].name.lower()))
        out.append({'player': p,
                    'nemesis': (by_id[worst[0]], worst[1]) if worst[1]['pct'] < 50 else None,
                    'prey': (by_id[best[0]], best[1]) if best[1]['pct'] > 50 else None})
    out.sort(key=lambda r: r['player'].name.lower())
    return [r for r in out if r['nemesis'] or r['prey']]
