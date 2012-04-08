from darts import models
from darts import cache

class Game(object):
    """Represent the state of the game at a certain point.

    The object is to be used only once: create, fetch, use, destroy.
    """
    def fetch(self, id):
        self.match = models.Match.objects.get(id=id)
        self.entrants = (models.Entrant.objects
            .select_related('player')
            .filter(match=self.match)
            .order_by('order')).all()

    def get_players_and_leg_score(self):
        leg = self.current_leg
        players = self.players_leg_order
        leg_score = self.get_leg_score(leg)
        return [ (p, leg_score[p.id], [None, None, None]) for p in players ]

    @property
    @cache.cached_method
    def current_leg(self):
        leg = (models.Leg.objects
            .filter(match=self.match)
            .order_by('-number'))[0:1]

        if leg:
            leg = leg[0]
        else:
            leg = models.Leg(number=1, match=self.match)

        return leg

    @property
    @cache.cached_method
    def current_player(self):
        players = self.players_leg_order
        leg = self.current_leg
        if leg.id is not None:
            last_round = (models.Round.objects
                .filter(leg=leg)
                .order_by('-number'))[0:1]
            if not last_round:
                last_round = None

        else:
            last_round = None

        if last_round is None:
            # no round stored, so the current player is the first
            return players[0]

        round_player = [p for p in players if p.id == last_round.player__id][0]
        if last_round.score is None:
            # this round is not over yet: he is the current player
            return round_player

        else:
            # this round is over: it's the next player's turn
            return players[(players.index(round_player) + 1) % len(players)]

    @property
    def players(self):
        return [ e.player for e in self.entrants ]

    @property
    @cache.cached_method
    def players_leg_order(self):
        players = self.players
        leg = self.current_leg
        idx = (leg.number - 1) % self.match.legs_number
        return players[idx:] + players[:idx]

    def get_leg_score(self, leg):
        players = self.players
        rounds = (models.Round.objects
            .filter(leg=leg)
            .order_by('number'))

        # map player id -> score
        score = dict((p.id, self.match.target_score) for p in players)

        for round in rounds:
            if round.score is not None:
                score[round.player__id] = round.score

        return score

    def score_tables(self):
        return [
            [   [ Score('%s' % i, i) for i in range(1,11) ],
                [ Score('D%s' % i, 2 * i) for i in range(1,11) ],
                [ Score('T%s' % i, 3 * i) for i in range(1,11) ], ],
            [   [ Score('%s' % i, i) for i in range(11,21) ],
                [ Score('D%s' % i, 2 * i) for i in range(11,21) ],
                [ Score('T%s' % i, 3 * i) for i in range(11,21) ], ],
            [   [ Score('RING', 25, "Bull's Ring"),
                  Score('BULL', 50, "Bull's Eye"), ], ],
            [   [ Score('MISS', 0, "Miss"),
                  Score('WALL', 0, "Wall!"),
                  Score('FALL', 0, "Fallen"),
                  Score('FORE', 0, "Forfeit"), ], ], ]

class Score(object):
    def __init__(self, code, value, label=None):
        self.code = code
        self.label = label or code
        self.value = value

