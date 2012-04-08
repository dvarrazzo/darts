from django.db import models

class Player(models.Model):
    username = models.CharField(max_length=64, unique=True)
    avatar = models.ImageField(upload_to='darts_avatar', max_length=255)

    def __unicode__(self):
        return self.username or u'unnamed player'

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

class Round(models.Model):
    number = models.IntegerField()
    score = models.IntegerField(blank=True, null=True) # at end of the round

class Throw(models.Model):
    label = models.CharField(max_length=16) # es. "8", "T20", "IRIS", "BULL",
    score = models.IntegerField()   # value of the throw

