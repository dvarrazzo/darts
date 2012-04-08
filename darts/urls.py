from django.conf.urls import patterns, url
from django.views.generic.simple import redirect_to

urlpatterns = patterns('darts.views',
    url(r'^$', redirect_to, {'url': 'match/create/', 'permanent': False}),
    url(r'^match/^$', redirect_to, {'url': 'match/create/', 'permanent': False}),
    url(r'^match/create/$', 'match_create', name='darts_match_create'),
    url(r'^match/(\d+)/play/$', 'match_play', name='darts_match_play'),
)
