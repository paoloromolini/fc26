from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .badges import MIN_GAMES, badges
from .forms import MatchForm, PlayerForm, ResultForm
from .models import Match, Player


def standings():
    rows = {p.id: {'player': p, 'points': 0, 'played': 0, 'wins': 0, 'losses': 0, 'draws': 0,
                   'gf': 0, 'ga': 0, 'max_points': 0} for p in Player.objects.all()}
    matches = Match.objects.filter(played=True).prefetch_related('team1', 'team2')
    for m in matches:
        for team, gf, ga in ((m.team1.all(), m.score1, m.score2), (m.team2.all(), m.score2, m.score1)):
            for p in team:
                r = rows[p.id]
                r['played'] += 1
                r['max_points'] += m.points_per_winner
                r['gf'] += gf
                r['ga'] += ga
                if gf > ga:
                    r['wins'] += 1
                    r['points'] += m.points_per_winner
                elif gf < ga:
                    r['losses'] += 1
                else:
                    r['draws'] += 1
                    r['points'] += 1
    out = list(rows.values())
    for r in out:
        r['gd'] = r['gf'] - r['ga']
        r['pct'] = round(100 * r['points'] / r['max_points']) if r['max_points'] else 0
    out.sort(key=lambda r: (-r['pct'], -r['points'], -r['wins'], -r['gd'], r['player'].name.lower()))
    # il ciuchino va a chi è ultimo (a pari merito, a tutti gli ultimi), se ha giocato e non sono tutti alla pari
    active = [r for r in out if r['played']]
    if len(active) > 1:
        worst = (active[-1]['pct'], active[-1]['points'], active[-1]['wins'], active[-1]['gd'])
        if worst != (active[0]['pct'], active[0]['points'], active[0]['wins'], active[0]['gd']):
            for r in active:
                if (r['pct'], r['points'], r['wins'], r['gd']) == worst:
                    r['donkey'] = True
    return out


def pair_standings():
    rows = {}
    matches = Match.objects.filter(played=True, mode=Match.TWO_V_TWO).prefetch_related('team1', 'team2')
    for m in matches:
        for team, gf, ga in ((m.team1.all(), m.score1, m.score2), (m.team2.all(), m.score2, m.score1)):
            players = sorted(team, key=lambda p: p.name.lower())
            key = tuple(p.id for p in players)
            r = rows.setdefault(key, {'name': ' + '.join(p.name for p in players), 'points': 0,
                                      'played': 0, 'wins': 0, 'losses': 0, 'draws': 0, 'gf': 0, 'ga': 0, 'players': players})
            r['played'] += 1
            r['gf'] += gf
            r['ga'] += ga
            if gf > ga:
                r['wins'] += 1
                r['points'] += m.points_per_winner
            elif gf < ga:
                r['losses'] += 1
            else:
                r['draws'] += 1
                r['points'] += 1
    out = list(rows.values())
    for r in out:
        r['gd'] = r['gf'] - r['ga']
        r['pct'] = round(100 * r['points'] / (3 * r['played']))
    out.sort(key=lambda r: (-r['pct'], -r['points'], -r['wins'], -r['gd'], r['name'].lower()))
    return out


ELO_START = 1200
ELO_K = 32


def _expected(rows, t1, t2):
    r1 = sum(rows[p.id]['rating'] for p in t1) / len(t1)
    r2 = sum(rows[p.id]['rating'] for p in t2) / len(t2)
    return 1 / (1 + 10 ** ((r2 - r1) / 400))


def _elo_replay():
    """Rating finali e, per ogni partita giocata, l'attesa di vittoria della squadra 1 al momento del match."""
    rows = {p.id: {'player': p, 'rating': ELO_START, 'peak': ELO_START, 'played': 0, 'last': None}
            for p in Player.objects.all()}
    expected = {}
    matches = (Match.objects.filter(played=True).order_by('scheduled_at', 'id')
               .prefetch_related('team1', 'team2'))
    for m in matches:
        t1, t2 = list(m.team1.all()), list(m.team2.all())
        if not t1 or not t2:
            continue
        e1 = expected[m.id] = _expected(rows, t1, t2)
        s1 = 1 if m.score1 > m.score2 else (0.5 if m.score1 == m.score2 else 0)
        for team, score, exp in ((t1, s1, e1), (t2, 1 - s1, 1 - e1)):
            delta = ELO_K * (score - exp)
            for p in team:
                r = rows[p.id]
                r['rating'] += delta
                r['peak'] = max(r['peak'], r['rating'])
                r['played'] += 1
                r['last'] = delta
    return rows, expected


def elo_ratings():
    """Classifica Elo: partite in ordine cronologico, rating di squadra = media dei giocatori (2v2)."""
    rows, _ = _elo_replay()
    out = list(rows.values())
    for r in out:
        r['provisional'] = r['played'] < MIN_GAMES
    out.sort(key=lambda r: (-r['rating'], r['player'].name.lower()))
    # il ciuchino va a chi è ultimo per Elo (a pari merito, a tutti gli ultimi), se non sono tutti alla pari
    active = [r for r in out if r['played']]
    if len(active) > 1 and round(active[-1]['rating']) != round(active[0]['rating']):
        for r in active:
            if round(r['rating']) == round(active[-1]['rating']):
                r['donkey'] = True
    return out


def with_elo(matches):
    """Annota ogni partita con m.elo, variazioni per squadra: t1 e t2.

    Giocata: scambio effettivo (int). Da giocare: (vittoria, pari, sconfitta) coi rating attuali."""
    rows, expected = _elo_replay()
    matches = list(matches)
    for m in matches:
        t1, t2 = list(m.team1.all()), list(m.team2.all())
        m.elo = None
        if not t1 or not t2:
            continue
        e1 = expected[m.id] if m.id in expected else _expected(rows, t1, t2)
        if m.played:
            s1 = 1 if m.score1 > m.score2 else (0.5 if m.score1 == m.score2 else 0)
            delta = round(ELO_K * (s1 - e1))
            m.elo = {'t1': delta, 't2': -delta}
        else:
            m.elo = {'t1': tuple(round(ELO_K * (s - e1)) for s in (1, 0.5, 0)),
                     't2': tuple(round(ELO_K * (s - (1 - e1))) for s in (1, 0.5, 0))}
    return matches


def trends():
    """Per ogni giocatore, i punti ottenuti partita per partita in ordine cronologico."""
    series = {p.id: {'name': p.name, 'results': []} for p in Player.objects.all()}
    matches = (Match.objects.filter(played=True).order_by('scheduled_at', 'id')
               .prefetch_related('team1', 'team2'))
    for m in matches:
        for team, gf, ga in ((m.team1.all(), m.score1, m.score2), (m.team2.all(), m.score2, m.score1)):
            pts = m.points_per_winner if gf > ga else (1 if gf == ga else 0)
            for p in team:
                series[p.id]['results'].append({'pts': pts, 'date': m.scheduled_at.strftime('%d/%m'),
                                                'mode': m.mode, 'score': f'{gf}-{ga}'})
    out = []
    for s in series.values():
        cum = 0
        for i, r in enumerate(s['results'], 1):
            cum += r['pts']
            last = s['results'][max(0, i - 5):i]
            r['cum_pct'] = round(100 * cum / (3 * i), 1)
            r['form_pct'] = round(100 * sum(x['pts'] for x in last) / (3 * len(last)), 1)
        out.append(s)
    b = badges()
    for s, pid in zip(out, series):
        s['badge'] = b[pid][0]
    return out


def trend(request):
    return render(request, 'league/trend.html', {'series': trends()})


def pairs(request):
    return render(request, 'league/pairs.html', {'standings': pair_standings()})


def points(request):
    return render(request, 'league/points.html', {'standings': standings()})


def home(request):
    upcoming = Match.objects.filter(played=False).order_by('scheduled_at').prefetch_related('team1', 'team2')
    recent = Match.objects.filter(played=True).prefetch_related('team1', 'team2')[:10]
    return render(request, 'league/home.html', {
        'ratings': elo_ratings(), 'elo_start': ELO_START, 'elo_k': ELO_K, 'min_games': MIN_GAMES,
        'upcoming': with_elo(upcoming), 'recent': with_elo(recent)})


def matches(request):
    qs = Match.objects.prefetch_related('team1', 'team2')
    return render(request, 'league/matches.html', {'matches': with_elo(qs)})


def match_new(request):
    form = MatchForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Partita creata.')
        return redirect('home')
    return render(request, 'league/match_form.html', {'form': form, 'players': Player.objects.exists()})


def match_result(request, pk):
    match = get_object_or_404(Match, pk=pk)
    form = ResultForm(request.POST or None, instance=match)
    if request.method == 'POST' and form.is_valid():
        m = form.save(commit=False)
        m.played = True
        m.save()
        messages.success(request, 'Risultato salvato.')
        return redirect('home')
    return render(request, 'league/result_form.html', {'form': form, 'match': match})


@require_POST
def match_delete(request, pk):
    get_object_or_404(Match, pk=pk).delete()
    messages.success(request, 'Partita eliminata.')
    return redirect('matches')


def players(request):
    form = PlayerForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Giocatore aggiunto.')
        return redirect('players')
    return render(request, 'league/players.html', {'form': form, 'players': Player.objects.all()})


@require_POST
def player_delete(request, pk):
    player = get_object_or_404(Player, pk=pk)
    if player.matches_as_team1.exists() or player.matches_as_team2.exists():
        messages.error(request, 'Il giocatore ha partite registrate: non eliminabile.')
    else:
        player.delete()
    return redirect('players')
