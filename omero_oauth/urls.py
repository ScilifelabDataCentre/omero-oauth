#!/usr/bin/env python
from django.urls import re_path

from . import views

urlpatterns = [
    re_path(r"^$", views.OauthLoginView.as_view(), name="oauth_index"),
    re_path(
        r"^callback/(?P<name>[a-z][a-z0-9]+)$",
        views.OauthCallbackView.as_view(),
        name="oauth_callback",
    ),
    re_path(r"^confirm$", views.confirm, name="oauth_confirm"),
    re_path(r"^sessiontoken$", views.sessiontoken, name="oauth_sessiontoken"),
    re_path(r"^error$", views.error, name="oauth_error"),
]
