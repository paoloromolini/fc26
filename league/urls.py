from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('punti/', views.points, name='points'),
    path('andamento/', views.trend, name='trend'),
    path('rivalita/', views.rivalry, name='rivalry'),
    path('coppie/', views.pairs, name='pairs'),
    path('partite/', views.matches, name='matches'),
    path('partite/nuova/', views.match_new, name='match_new'),
    path('partite/<int:pk>/risultato/', views.match_result, name='match_result'),
    path('partite/<int:pk>/elimina/', views.match_delete, name='match_delete'),
    path('giocatori/', views.players, name='players'),
    path('giocatori/<int:pk>/elimina/', views.player_delete, name='player_delete'),
]
