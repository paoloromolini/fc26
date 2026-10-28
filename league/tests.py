from django.test import TestCase

from .models import Match, Player
from .views import trends


class TrendTests(TestCase):
    def test_trend_series(self):
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        for s1, s2 in ((2, 0), (1, 1), (0, 3)):
            m = Match.objects.create(mode='1v1', played=True, score1=s1, score2=s2)
            m.team1.set([a]); m.team2.set([b])
        res = {s['name']: s['results'] for s in trends()}
        self.assertEqual([r['pts'] for r in res['A']], [3, 1, 0])
        self.assertEqual([r['cum_pct'] for r in res['A']], [100.0, 66.7, 44.4])
        self.assertEqual(res['B'][-1]['pts'], 3)
        self.assertEqual(self.client.get('/andamento/').status_code, 200)

    def test_trend_empty(self):
        self.assertEqual(self.client.get('/andamento/').status_code, 200)


class BadgeTests(TestCase):
    def test_tiers(self):
        from .badges import tier_for
        self.assertEqual(tier_for(1, 100)[1], 'Esordiente')  # poche partite: provvisorio
        self.assertEqual(tier_for(5, 0)[1], 'Matricola')
        self.assertEqual(tier_for(5, 33)[1], 'Titolare')
        self.assertEqual(tier_for(5, 50)[1], 'In forma')
        self.assertEqual(tier_for(5, 60)[1], 'Stella')
        self.assertEqual(tier_for(5, 100)[1], 'Leggenda')

    def test_badges_everywhere(self):
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        for _ in range(5):
            m = Match.objects.create(mode='1v1', played=True, score1=2, score2=0)
            m.team1.set([a]); m.team2.set([b])
        m2 = Match.objects.create(mode='1v1')
        m2.team1.set([a]); m2.team2.set([b])
        for url in ['/', '/punti/', '/partite/', '/coppie/', '/giocatori/', '/partite/nuova/', f'/partite/{m2.id}/risultato/']:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
        html = self.client.get('/').content.decode()
        self.assertIn('👑', html)   # A: 5 partite, 100%
        self.assertIn('🐣', html)   # B: 5 partite, 0%
        self.assertEqual(self.client.get('/andamento/').status_code, 200)


class DonkeyTests(TestCase):
    def test_donkey_goes_to_last(self):
        a, b, c = (Player.objects.create(name=n) for n in 'ABC')
        m = Match.objects.create(mode='1v1', played=True, score1=2, score2=0)
        m.team1.set([a]); m.team2.set([b])
        from .views import standings
        rows = {r['player'].name: r.get('donkey') for r in standings()}
        self.assertEqual(rows, {'A': None, 'B': True, 'C': None})  # C non ha giocato
        self.assertIn('🫏', self.client.get('/').content.decode())

    def test_no_donkey_when_all_equal(self):
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        m = Match.objects.create(mode='1v1', played=True, score1=1, score2=1)
        m.team1.set([a]); m.team2.set([b])
        from .views import standings
        self.assertFalse(any(r.get('donkey') for r in standings()))


class DeleteConfirmTests(TestCase):
    def test_delete_form_has_modal_hook(self):
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        m = Match.objects.create(mode='1v1')
        m.team1.set([a]); m.team2.set([b])
        html = self.client.get('/partite/').content.decode()
        self.assertIn('data-confirm="Eliminare la partita A vs B', html)
        self.assertIn('id="confirm-dialog"', html)
        self.assertNotIn("onsubmit=\"return confirm('Eliminare la partita", html)


class EloTests(TestCase):
    def test_elo_1v1(self):
        from .views import ELO_K, ELO_START, elo_ratings
        a, b, c = (Player.objects.create(name=n) for n in 'ABC')
        m = Match.objects.create(mode='1v1', played=True, score1=2, score2=0)
        m.team1.set([a]); m.team2.set([b])
        r = {x['player'].name: x for x in elo_ratings()}
        self.assertAlmostEqual(r['A']['rating'], ELO_START + ELO_K / 2)
        self.assertAlmostEqual(r['B']['rating'], ELO_START - ELO_K / 2)
        self.assertEqual(r['C']['rating'], ELO_START)
        self.assertIsNone(r['C']['last'])
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_elo_draw_equal_players_is_neutral(self):
        from .views import ELO_START, elo_ratings
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        m = Match.objects.create(mode='1v1', played=True, score1=1, score2=1)
        m.team1.set([a]); m.team2.set([b])
        self.assertEqual({x['rating'] for x in elo_ratings()}, {ELO_START})

    def test_elo_2v2_same_delta_for_teammates(self):
        from .views import elo_ratings
        a, b, c, d = (Player.objects.create(name=n) for n in 'ABCD')
        m = Match.objects.create(mode='2v2', played=True, score1=3, score2=1)
        m.team1.set([a, b]); m.team2.set([c, d])
        r = {x['player'].name: x['rating'] for x in elo_ratings()}
        self.assertEqual(r['A'], r['B'])
        self.assertEqual(r['C'], r['D'])
        self.assertAlmostEqual(r['A'] + r['C'], 2400)

    def test_elo_empty(self):
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_home_is_elo_and_points_moved(self):
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        m = Match.objects.create(mode='1v1', played=True, score1=2, score2=0)
        m.team1.set([a]); m.team2.set([b])
        self.assertIn('Classifica Elo', self.client.get('/').content.decode())
        self.assertIn('Classifica a punti', self.client.get('/punti/').content.decode())


class EloStakeTests(TestCase):
    def test_stake_before_result_and_exchange_after(self):
        from .views import with_elo
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        m = Match.objects.create(mode='1v1')
        m.team1.set([a]); m.team2.set([b])
        (m,) = with_elo(Match.objects.all())
        self.assertEqual(m.elo, {'t1': (16, 0, -16), 't2': (16, 0, -16)})
        html = self.client.get('/').content.decode()
        self.assertIn('vittoria', html)
        m.score1, m.score2, m.played = 2, 0, True
        m.save()
        (m,) = with_elo(Match.objects.all())
        self.assertEqual(m.elo, {'t1': 16, 't2': -16})
        self.assertIn('+16', self.client.get('/partite/').content.decode())

    def test_stake_favourite_risks_more(self):
        from .views import with_elo
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        for _ in range(3):
            m = Match.objects.create(mode='1v1', played=True, score1=2, score2=0)
            m.team1.set([a]); m.team2.set([b])
        m = Match.objects.create(mode='1v1')
        m.team1.set([a]); m.team2.set([b])
        (up,) = [x for x in with_elo(Match.objects.filter(played=False))]
        win, draw, loss = up.elo['t1']
        self.assertLess(win, 16)
        self.assertLess(loss, -16)
        self.assertGreater(up.elo['t2'][0], 16)

    def test_played_match_uses_rating_at_the_time(self):
        from .views import with_elo
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        for _ in range(2):
            m = Match.objects.create(mode='1v1', played=True, score1=2, score2=0)
            m.team1.set([a]); m.team2.set([b])
        first, second = sorted(with_elo(Match.objects.filter(played=True)), key=lambda x: x.id)
        self.assertEqual(first.elo['t1'], 16)
        self.assertLess(second.elo['t1'], 16)


def _play(mode, t1, t2, s1, s2):
    m = Match.objects.create(mode=mode, played=True, score1=s1, score2=s2)
    m.team1.set(t1); m.team2.set(t2)
    return m


class EloByModeTests(TestCase):
    def test_modes_are_independent(self):
        from .views import ELO_K, ELO_START, elo_ratings
        a, b, c, d = (Player.objects.create(name=n) for n in 'ABCD')
        _play('1v1', [a], [b], 2, 0)
        _play('2v2', [a, c], [b, d], 0, 1)
        r = {x['player'].name: x for x in elo_ratings()}
        self.assertAlmostEqual(r['A']['elo_1v1'], ELO_START + ELO_K / 2)
        self.assertAlmostEqual(r['A']['elo_2v2'], ELO_START - ELO_K / 2)  # il 2v2 parte da zero, non dal 1v1
        self.assertEqual(r['A']['elo_2v2_games'], 1)

    def test_none_when_mode_never_played(self):
        from .views import elo_ratings
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        _play('1v1', [a], [b], 1, 0)
        r = elo_ratings()[0]
        self.assertIsNone(r['elo_2v2'])
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_pair_elo(self):
        from .views import ELO_K, ELO_START, pair_standings
        a, b, c, d = (Player.objects.create(name=n) for n in 'ABCD')
        _play('2v2', [a, b], [c, d], 3, 1)
        _play('2v2', [d, c], [b, a], 0, 0)  # stessa coppia con ordine diverso
        rows = {r['name']: r['elo'] for r in pair_standings()}
        self.assertEqual(set(rows), {'A + B', 'C + D'})
        self.assertAlmostEqual(rows['A + B'] + rows['C + D'], 2 * ELO_START)
        self.assertGreater(rows['A + B'], ELO_START)
        self.assertEqual(self.client.get('/coppie/').status_code, 200)


class RivalryTests(TestCase):
    def setUp(self):
        self.a, self.b, self.c, self.d = (Player.objects.create(name=n) for n in 'ABCD')

    def test_head_to_head_and_teammates_excluded(self):
        from .rivalry import rivalries
        _play('1v1', [self.a], [self.b], 3, 0)
        _play('1v1', [self.b], [self.a], 1, 1)
        _play('2v2', [self.a, self.c], [self.b, self.d], 0, 2)
        t = rivalries()
        rec = t[(self.a.id, self.b.id)]
        self.assertEqual((rec['w'], rec['d'], rec['l'], rec['n']), (1, 1, 1, 3))
        self.assertEqual((rec['gf'], rec['ga']), (4, 3))
        mirror = t[(self.b.id, self.a.id)]
        self.assertEqual((mirror['w'], mirror['l']), (1, 1))
        self.assertNotIn((self.a.id, self.c.id), t)  # compagni di squadra
        self.assertEqual(rec['last'][0]['res'], 'l')  # il più recente per primo

    def test_nemesis_needs_enough_games(self):
        from .rivalry import nemeses, rivalries
        by_id = {p.id: p for p in Player.objects.all()}
        _play('1v1', [self.a], [self.b], 0, 1)
        _play('1v1', [self.a], [self.b], 0, 1)
        self.assertEqual(nemeses(rivalries(), by_id), [])
        _play('1v1', [self.a], [self.b], 0, 1)
        res = {n['player'].name: n for n in nemeses(rivalries(), by_id)}
        self.assertEqual(res['A']['nemesis'][0], self.b)
        self.assertIsNone(res['A']['prey'])
        self.assertEqual(res['B']['prey'][0], self.a)

    def test_pages(self):
        _play('1v1', [self.a], [self.b], 2, 1)
        for url in ('/rivalita/', f'/rivalita/?a={self.a.id}&b={self.b.id}', f'/rivalita/?a={self.b.id}&b={self.a.id}',
                    f'/rivalita/?a={self.a.id}&b={self.c.id}', f'/rivalita/?a={self.a.id}&b={self.a.id}',
                    '/rivalita/?a=x&b=999'):
            self.assertEqual(self.client.get(url).status_code, 200, url)


class AwardTests(TestCase):
    def titles(self):
        from .awards import awards
        return {a['title']: a for a in awards()}

    def test_no_awards_without_games(self):
        Player.objects.create(name='A')
        self.assertEqual(self.titles(), {})
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_wall_cannon_streak_and_thrashing(self):
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        for _ in range(5):
            _play('1v1', [a], [b], 5, 0)
        t = self.titles()
        self.assertEqual([p.name for p in t['Il Muro']['holders']], ['A'])
        self.assertEqual([p.name for p in t['Il Cannoniere']['holders']], ['A'])
        self.assertEqual(t['In fiamma']['detail'], '5 vittorie di fila')
        self.assertEqual([p.name for p in t['In caduta libera']['holders']], ['B'])
        self.assertEqual(t['Cappotto']['detail'], '5-0 contro B')
        self.assertIn('😱', self.client.get('/').content.decode())

    def test_streak_broken_by_draw(self):
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        for s in (2, 2, 2, 1):
            _play('1v1', [a], [b], s, 1 if s == 1 else 0)
        self.assertNotIn('In fiamma', self.titles())

    def test_needs_min_games(self):
        a, b = Player.objects.create(name='A'), Player.objects.create(name='B')
        _play('1v1', [a], [b], 1, 0)
        self.assertNotIn('Il Muro', self.titles())
