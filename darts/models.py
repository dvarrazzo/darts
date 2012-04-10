from django.db import models

class Player(models.Model):
    username = models.CharField(max_length=64, unique=True)
    avatar = models.ImageField(upload_to='darts_avatar', max_length=255)

    def __unicode__(self):
        return self.username or u'unnamed player'

    def __eq__(self, other):
        return self.id == other.id

    def __ne__(self, other):
        return not self.__eq__(other)

class Match(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    target_score = models.IntegerField()
    legs_number = models.IntegerField()
    winner = models.ForeignKey(Player, blank=True, null=True)

class Entrant(models.Model):
    match = models.ForeignKey(Match)
    player = models.ForeignKey(Player)
    order = models.IntegerField()
    result = models.IntegerField(blank=True, null=True)

class Leg(models.Model):
    match = models.ForeignKey(Match)
    started_at = models.DateTimeField(auto_now_add=True)
    number = models.IntegerField()
    winner = models.ForeignKey(Player, blank=True, null=True)

    def __eq__(self, other):
        if self.id is None:
            return other.id is None and other.number == self.number
        else:
            return self.id == other.id

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.id, self.number))

class Round(models.Model):
    leg = models.ForeignKey(Leg)
    number = models.IntegerField()
    player = models.ForeignKey(Player)
    score_start = models.IntegerField()
    score_end = models.IntegerField(blank=True, null=True)

class Throw(models.Model):
    round = models.ForeignKey(Round)
    number = models.IntegerField()
    code = models.CharField(max_length=16) # es. "8", "T20", "RING", "BULL",
    score = models.IntegerField()   # value of the throw


