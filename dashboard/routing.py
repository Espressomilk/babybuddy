from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"^ws/track/(?P<child_slug>[\w-]+)/$", consumers.TrackConsumer.as_asgi()),
]
