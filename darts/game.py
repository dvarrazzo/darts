import re

from darts import models
from darts import cache

class GameError(Exception):
    pass

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
        pmap = dict((p.id, p) for p in players)

        leg_score = self.get_leg_score(leg)
        rounds = self.get_last_rounds(leg)
        rmap = dict((r.id, r.player_id) for r in rounds)  # round -> player
        throws = (models.Throw.objects
            .filter(round__in=rounds)
            .order_by('id'))

        # decorate players with leg score and throws
        for p in players:
            p.leg_score = leg_score[p.id]
            p.last_throws = []

        for t in throws:
            p = pmap[rmap[t.round_id]]
            p.last_throws.append(t)

        # complete the throws list with blank ones
        for p in players:
            nthrows = len(p.last_throws)
            assert nthrows <= 3
            p.last_throws += [ models.Throw()
                for i in range(3 - nthrows) ]

            if p == self.current_player and nthrows < 3:
                p.last_throws[nthrows].current = True

        return players

    @property
    @cache.cached_method
    def current_leg(self):
        leg = (models.Leg.objects
            .filter(match=self.match)
            .order_by('-number'))[0:1]

        if leg:
            leg = leg[0]
            if leg.winner_id is not None:
                leg = models.Leg(number=leg.number+1, match=self.match)

        else:
            leg = models.Leg(number=1, match=self.match)

        return leg

    @property
    @cache.cached_method
    def current_round(self):
        round = None
        leg = self.current_leg
        if leg.id is not None:
            round = (models.Round.objects
                .filter(leg=leg)
                .order_by('-number'))[0:1]

        if not round:
            # first round
            return models.Round(leg=leg, number=1,
                score_start=self.match.target_score,
                player=self._get_round_player(leg.number, 1))
        else:
            round = round[0]

        if round.score_end:
            # round is over, so have the next one
            player = self._get_round_player(leg.number, round.number + 1)
            prev_round = (models.Round.objects
                .filter(leg=leg, player=player)
                .order_by('-number'))[0:1]
            if prev_round:
                prev_score = prev_round[0].score_end
            else:
                prev_score = self.match.target_score

            round = models.Round(leg=leg, number=round.number + 1,
                score_start=prev_score, player=player)

        return round

    def _get_round_player(self, leg_number, round_number):
        players = self._get_players_leg_order(leg_number)
        return players[(round_number - 1) % len(players)]

    @property
    @cache.cached_method
    def current_player(self):
        round = self.current_round
        return round.player

    @property
    def players(self):
        return [ e.player for e in self.entrants ]

    @property
    @cache.cached_method
    def players_leg_order(self):
        leg = self.current_leg
        return self._get_players_leg_order(leg.number)

    def _get_players_leg_order(self, leg_number):
        players = self.players
        idx = (leg_number - 1) % len(players)
        return players[idx:] + players[:idx]

    def get_last_rounds(self, leg):
        curr = self.current_round
        if curr.id is None:
            nrounds = len(self.entrants) - 1
        else:
            nrounds = len(self.entrants)

        rv = list(models.Round.objects
            .filter(leg=leg)
            .order_by('-number'))[:nrounds]

        if curr.id is None:
            rv.append(curr)

        return rv

    def get_leg_score(self, leg):
        players = self.players
        rounds = self.get_last_rounds(leg)

        # map player id -> score
        smap = dict((p.id, self.match.target_score) for p in players)

        for round in rounds:
            if round.score_end is not None:
                smap[round.player_id] = round.score_end
            else:
                score = round.score_start
                throws = models.Throw.objects.filter(round=round)
                for t in throws:
                    score -= t.score

                smap[round.player_id] = score

        return smap

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

    def store_throw(self, throw_code,
            # for validation
            _player_id=None, _leg_number=None, _round_number=None,
            _throw_number=None, _throw_value=None, _leg_score=None,
            _win=None, _bust=None):

        # objects we need
        player = self.current_player
        leg = self.current_leg
        round = self.current_round
        if round.id is not None:
            throws = list(models.Throw.objects
                .filter(round=round)
                .order_by('number'))
        else:
            throws = []

        nthrow = len(throws) + 1

        prev_score = round.score_start
        value = self.throw_value(throw_code)
        round_score = sum(t.score for t in throws) + value
        new_score = prev_score - round_score

        # win/bust?
        win = new_score == 0 and bool(re.match(r'^(D\d+)|BULL$', throw_code))
        if (_win is not None and bool(_win) != win):
            raise GameError("we don't agree whether he has win")
        bust = not win and new_score <= 1
        if (_bust is not None and bool(_bust) != bust):
            raise GameError("we don't agree whether he his bust")

        if bust:
            new_score = prev_score

        # validate stuff
        if _player_id is not None and _player_id != player.id:
            raise GameError(
                'the player is %s, not $s' % (player.id, _player_id))

        if _leg_number is not None and _leg_number != leg.number:
            raise GameError(
                'we are at leg %s, not %s' % (leg.number, _leg_number))

        if _round_number is not None and _round_number != round.number:
            raise GameError(
                'we are at round %s, not %s' % (round.number, _round_number))

        if _throw_number is not None and _throw_number != nthrow:
            raise GameError(
                'we are at throw %s, not %s' % (nthrow, _throw_number))

        if _throw_value is not None and _throw_value != value:
            raise GameError(
                'value for %s is %s not %s' % (throw_code, value, _throw_value))

        if _leg_score is not None and new_score != _leg_score:
            raise GameError(
                'the leg score shoud be %s, not %s'
                % (new_score, _leg_score))

        # save the objects
        if leg.id is None:
            leg.save()
        if round.id is None:
            round.leg = leg     # need reiterate to store the leg id
            round.save()

        throw = models.Throw(round=round, number=nthrow,
            code=throw_code, score=value)
        throw.save()
        throws.append(throw)

        if nthrow == 3 or win or bust:
            round.score_end = new_score
            round.save()

        if win:
            leg.winner = player
            leg.save()

    def undo_throw(self):
        leg = (models.Leg.objects
            .filter(match=self.match)
            .order_by('-number'))[0:1]

        if not leg:
            # no leg has been played yet in the match.
            return

        leg = leg[0]

        rounds = list(models.Round.objects
            .filter(leg=leg)
            .order_by('-number'))[0:2]

        if not rounds:
            # no round has been played yet in the leg.
            return

        throw = (models.Throw.objects
            .filter(round__in=rounds)
            .order_by('-id'))[0:1]

        if not throw:
            # no throw played in the leg yet
            return

        throw = throw[0]

        # there shouldn't be a round without throws in the db, but just in
        # case...
        if rounds[0].id == throw.round_id:
            round = rounds[0]
        else:
            rounds[0].delete()
            round = rounds[1]
            assert round.id == throw.round_id

        if throw.number > 1:
            # easy stuff: we just drop one throw from the round
            throw.delete()
            if round.score_end is not None:
                round.score_end = None
                round.save()

        else:
            # we must delete the throw and its round
            throw.delete()
            round.delete()
            if round.number == 1:
                leg.delete()

        # if the last throw had made a winner, well, he is no more
        if leg.winner_id is not None:
            leg.winner_id = None
            leg.save()

    def throw_value(self, code):
        m = re.match(r'^(?:([DT])?(\d+))|(RING|BULL)$', code)
        if not m:
            return 0    # miss, void etc.
        if m.group(3) == 'RING':
            return 25
        elif m.group(3) == 'BULL':
            return 50

        value = int(m.group(2))
        if m.group(1) == 'D':
            value *= 2
        elif m.group(1) == 'T':
            value *= 3

        return value


class Score(object):
    def __init__(self, code, value, label=None):
        self.code = code
        self.label = label or code
        self.value = value

