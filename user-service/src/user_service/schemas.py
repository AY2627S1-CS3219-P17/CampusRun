# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated registration request and user response models with NUS email, username and password validation.
# Author review: <to be completed by author>

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints, field_validator

from user_service.tables import USERNAME_MAX_LENGTH

# Student and staff addresses; the platform is limited to the NUS community
ALLOWED_EMAIL_DOMAINS = frozenset({"u.nus.edu", "nus.edu.sg"})

USERNAME_MIN_LENGTH = 3
PASSWORD_MIN_LENGTH = 8
# Caps the work an attacker can force by sending a huge password to be hashed
PASSWORD_MAX_LENGTH = 128

Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=USERNAME_MIN_LENGTH,
        max_length=USERNAME_MAX_LENGTH,
        pattern=r"^[A-Za-z0-9_.-]+$",
    ),
]

# Not stripped: spaces are valid password characters
Password = Annotated[
    str,
    StringConstraints(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH),
]


class RegisterRequest(BaseModel):
    email: EmailStr
    username: Username
    password: Password

    @field_validator("email")
    @classmethod
    def check_nus_domain(cls, email: str) -> str:
        domain = email.rsplit("@", 1)[1].lower()
        if domain not in ALLOWED_EMAIL_DOMAINS:
            raise ValueError("must be an NUS email address (@u.nus.edu or @nus.edu.sg)")
        return email


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    email_verified_at: datetime | None
    created_at: datetime
