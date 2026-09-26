# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated registration request and user response models with NUS email, username and password validation;
#        AI-added the profile update request model, and aligned the username and password rules with the web client (2026-09-27).
# Author review: reviewed by Nathan

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, StringConstraints, field_validator, model_validator

from user_service.tables import USERNAME_MAX_LENGTH

# Student and staff addresses; the platform is limited to the NUS community
ALLOWED_EMAIL_DOMAINS = frozenset({"u.nus.edu", "nus.edu.sg"})

USERNAME_MIN_LENGTH = 3
PASSWORD_MIN_LENGTH = 8
# Caps the work an attacker can force by sending a huge password to be hashed
PASSWORD_MAX_LENGTH = 128

# Character rules match the web client's (frontend/src/utils/validation.ts); keep the two in sync
Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=USERNAME_MIN_LENGTH,
        max_length=USERNAME_MAX_LENGTH,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]

# Each must match at least once. Whitespace is allowed but doesn't count as a special character.
PASSWORD_CHARACTER_CLASSES = (
    re.compile(r"[A-Z]"),
    re.compile(r"[a-z]"),
    re.compile(r"[0-9]"),
    re.compile(r"[^A-Za-z0-9\s]"),
)


def check_password_characters(password: str) -> str:
    if not all(character_class.search(password) for character_class in PASSWORD_CHARACTER_CLASSES):
        raise ValueError("must contain an uppercase letter, a lowercase letter, a number and a special character")
    return password


# Not stripped: spaces are valid password characters
Password = Annotated[
    str,
    StringConstraints(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH),
    AfterValidator(check_password_characters),
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


class UpdateUserRequest(BaseModel):
    # Omitted fields are left unchanged
    username: Username | None = None
    # Not length-checked here: check_password caps it, so a wrong password gets 400 rather than 422
    current_password: str | None = None
    new_password: Password | None = None

    @field_validator("username", mode="before")
    @classmethod
    def reject_null_username(cls, username: object) -> object:
        # Only runs when the field is sent, so an explicit null is an error rather than "no change"
        if username is None:
            raise ValueError("must not be null")
        return username

    @model_validator(mode="after")
    def check_passwords(self) -> "UpdateUserRequest":
        if self.new_password is None:
            return self
        if not self.current_password:
            raise ValueError("current_password is required to set a new password")
        # Otherwise the user asked for a change and "succeeds" with nothing changed.
        # Compares the two inputs only, so it reveals nothing about the stored password.
        if self.new_password == self.current_password:
            raise ValueError("new_password must be different from current_password")
        return self


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    email_verified_at: datetime | None
    created_at: datetime


class AdminResponse(BaseModel):
    id: int
    username: str
    created_at: datetime


class TokenResponse(BaseModel):
    # Field names are fixed by the OAuth2 spec; Swagger's Authorize button reads them
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    