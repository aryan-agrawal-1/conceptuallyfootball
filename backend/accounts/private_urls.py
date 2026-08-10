from django.urls import path

from accounts.api import editorial_workspace, operations_status


urlpatterns = [
    path("editorial/workspace", editorial_workspace, name="editorial-workspace"),
    path("operations/status", operations_status, name="operations-status"),
]
