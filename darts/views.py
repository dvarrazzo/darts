from django.db import transaction
from django.http import HttpResponse
from django.utils import simplejson
from django.shortcuts import render
from django.core.urlresolvers import reverse

from darts import models

def match_create(request):
    if request.method == 'POST':
        return match_create_post(request)

    players = models.Player.objects.order_by('username')
    return render(request, 'darts/match_create.tmpl',
        {'players': players})

@transaction.commit_manually
def match_create_post(request):
    score = request.POST.get('score')
    try:
        try:
            score = int(score)
            if score <= 0:
                raise Exception()
        except:
            raise ValueError("bad target score: '%s'" % score)

        nlegs = request.POST.get('legs')
        try:
            nlegs = int(nlegs)
            if nlegs <= 0:
                raise Exception()
        except:
            raise ValueError("bad legs number: '%s'" % nlegs)

        eids = request.POST.get('entrants')
        if not eids:
            raise ValueError("no player selected")

        try:
            eids = map(int, eids.split(','))
        except:
            raise ValueError("bad entrants: '%s'" % eids)

        if len(eids) != len(set(eids)):
            raise ValueError("duplicate entrants")

        players = []
        for eid in eids:
            try:
                players.append(models.Player.objects.get(id=eid))
            except models.Player.DoesNotExist:
                raise ValueError('player not found: %s' % eid)

        assert players

    except Exception, e:
        return HttpResponse(str(e),
            status=400, mimetype='plain/text')

    try:
        match = models.Match(
            target_score=score,
            legs_number=nlegs)
        match.save()

        for i, player in enumerate(players):
            e = models.Entrant(
                match=match,
                player=player,
                order=i + 1)
            e.save()

        transaction.commit()
    except Exception, e:
        transaction.rollback()
        raise

    resp = {'redirect': reverse('darts_match_play', args=[match.id])}

    return HttpResponse(simplejson.dumps(resp),
        mimetype='application/json')


def match_play(request, id):
    return HttpResponse('play')

