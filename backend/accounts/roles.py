from __future__ import annotations

from django.contrib.auth.models import Group, User

from accounts.models import StaffRole


ROLE_GROUPS = {
    StaffRole.WRITER: "Editorial Writers",
    StaffRole.APPROVER: "Editorial Approvers",
    StaffRole.OPERATIONS: "Operations Users",
}


def configure_user_role(user: User, role: str) -> None:
    role_group_names = tuple(ROLE_GROUPS.values())
    user.groups.remove(*Group.objects.filter(name__in=role_group_names))
    user.groups.add(Group.objects.get(name=ROLE_GROUPS[role]))

    should_be_staff = role == StaffRole.OPERATIONS
    if not user.is_superuser and user.is_staff != should_be_staff:
        user.is_staff = should_be_staff
        user.save(update_fields=("is_staff",))
