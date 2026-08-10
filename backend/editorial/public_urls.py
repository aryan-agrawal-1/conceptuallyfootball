from django.urls import path

from editorial.api import shared_preview


urlpatterns = [
    path("previews/<uuid:token>", shared_preview, name="editorial-shared-preview"),
]
