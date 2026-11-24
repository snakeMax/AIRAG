"""Editions: personal desktop, Android and (later) enterprise.

Groundwork only. The personal editions behave exactly as before. Enterprise (browser/server, Docker) will
add sign-in, admin vs user settings, per-user limits with "request more", shared company library with
approval and remote vaults; none of that is switched on here. Code that will differ between editions asks
this module instead of checking platforms itself, so the three builds stay separate.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from . import paths

PERSONAL = ("desktop", "android")


def edition() -> str:
    """'android', 'desktop' or 'enterprise'. Enterprise only when the server build sets AIRAG_EDITION."""
    if paths.ANDROID:
        return "android"
    if os.environ.get("AIRAG_EDITION", "").strip().lower() == "enterprise":
        return "enterprise"
    return "desktop"


def is_enterprise() -> bool:
    return edition() == "enterprise"


@dataclass(frozen=True)
class User:
    id: str
    name: str
    admin: bool


LOCAL_USER = User("local", "You", True)


def current_user(request=None) -> User:
    """The person using AIRAG. Personal editions have one local user who may change everything."""
    if not is_enterprise():
        return LOCAL_USER
    raise NotImplementedError("Enterprise sign-in arrives with the enterprise edition")


# what an admin can lock or limit for users in the enterprise edition (names only, for now)
ADMIN_POLICIES = (
    "providers",          # which AI services and models users may pick
    "monthly_budget",     # per-user budget, with "request more"
    "web_access",         # search engines / offline only
    "tools",              # agent tools users may switch on
    "library",            # shared company library (read / propose additions)
    "export",             # export and sharing
)


def allowed(action: str, user: Optional[User] = None) -> bool:
    """May this user do `action`? Personal editions: always (the user owns the app)."""
    user = user or current_user()
    if not is_enterprise():
        return True
    return user.admin            # enterprise: real policy checks come with the edition
