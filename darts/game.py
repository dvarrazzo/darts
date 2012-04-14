import re
from collections import defaultdict

from darts import models
from darts import cache

class GameError(Exception):
    pass

class Game(object):
    """Represent the state of the game at a certain point.

    The object is to be used only once: create, fetch, use, destroy.
    """
    def __init__(self, id):
        self._match_id = id

    @property
    @cache.cached_method
    def match(self):
        return models.Match.objects.get(id=self._match_id)

    @property
    @cache.cached_method
    def entrants(self):
        return (models.Entrant.objects
            .select_related('player')
            .filter(match=self.match)
            .order_by('order')).all()

    def get_players_and_leg_score(self):
        players = self.players_leg_order
        pmap = dict((p.id, p) for p in players)

        leg_score = self.current_leg_score
        rounds = self.last_rounds
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
            if leg.winner_id is not None and self.match.winner_id is None:
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
                player_id=self._get_round_player_id(leg.number, 1))
        else:
            round = round[0]

        if round.score_end:
            # round is over, so have the next one
            player_id = self._get_round_player_id(leg.number, round.number + 1)
            prev_round = (models.Round.objects
                .filter(leg=leg, player_id=player_id)
                .order_by('-number'))[0:1]
            if prev_round:
                prev_score = prev_round[0].score_end
            else:
                prev_score = self.match.target_score

            round = models.Round(leg=leg, number=round.number + 1,
                score_start=prev_score, player_id=player_id)

        return round

    def _get_round_player_id(self, leg_number, round_number):
        ents = self._get_entrants_leg_order(leg_number)
        return ents[(round_number - 1) % len(ents)].player_id

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
        return [e.player for e in self._get_entrants_leg_order(leg.number)]

    def _get_entrants_leg_order(self, leg_number):
        players = self.entrants
        idx = (leg_number - 1) % len(players)
        return players[idx:] + players[:idx]

    @property
    @cache.cached_method
    def last_rounds(self):
        leg = self.current_leg
        curr = self.current_round
        if curr.id is None:
            nrounds = len(self.entrants) - 1
        else:
            nrounds = len(self.entrants)

        rv = list(models.Round.objects
            .filter(leg=leg)
            .order_by('-number')[:nrounds])

        if curr.id is None:
            rv.append(curr)

        return rv

    @property
    @cache.cached_method
    def current_leg_score(self):
        players = self.players
        rounds = self.last_rounds

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

    def throw(self, throw_code):
        if self.match.winner_id is not None:
            raise GameError('this game is over')

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
        bust = not win and new_score <= 1

        if bust:
            new_score = prev_score

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
            if not win:
                next_round = round.number + 1
                next_throw = 1
        else:
            next_round = round.number
            next_throw= nthrow + 1

        if win:
            leg.winner = self.current_player
            leg.save()

            mwid = self._get_match_winner_id()
            if mwid is not None:
                self.match.winner_id = mwid
                self.match.save()

        else:
            if nthrow == 3 or bust:
                next_player = self._get_round_player_id(leg.number, next_round)
            else:
                next_player = self.current_round.player_id

        rv = {}
        rv['leg_score'] = new_score
        rv['throws'] = [ { 'code': t.code, 'score': t.score } for t in throws ]

        if bust:
            rv['bust'] = True

        if win:
            rv['leg_winner'] = self.current_player.id
            if mwid is not None:
                rv['match_winner'] = mwid
        else:
            # note: not defined if win
            rv['next_player'] = next_player
            rv['next_throw'] = next_throw

        return rv

    def _get_match_winner_id(self):
        legs = (models.Leg.objects
            .filter(match=self.match, winner__isnull=False)).all()
        pids = [ e.player_id for e in self.entrants ]
        assert len(pids) > 0

        # special case: if there is a single players, he'll play all the legs
        if len(pids) == 1:
            if len(legs) >= self.match.legs_number:
                return pids[0]
            else:
                return None

        player_score = defaultdict(int)
        for leg in legs:
            player_score[leg.winner_id] += 1

        rank = [ (player_score[pid], pid) for pid in pids ]
        rank.sort(reverse=True)

        # if the second can't get the first, the first is the winner
        if rank[1][0] + (self.match.legs_number - len(legs)) < rank[0][0]:
            for pid in pids:
                if pid == rank[0][1]:
                    return pid
            else:
                assert False
        else:
            return None


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

        # ditto for the match
        if self.match.winner_id is not None:
            self.match.winner_id = None
            self.match.save()

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

