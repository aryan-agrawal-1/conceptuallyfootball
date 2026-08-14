from django.urls import path

from accounts.api import change_password, csrf_token, login_view, logout_view, save_writer_profile, session


urlpatterns = [
    path("csrf", csrf_token, name="staff-csrf"),
    path("session", session, name="staff-session"),
    path("login", login_view, name="staff-login"),
    path("logout", logout_view, name="staff-logout"),
    path("password", change_password, name="staff-change-password"),
    path("profile", save_writer_profile, name="staff-writer-profile"),
]
