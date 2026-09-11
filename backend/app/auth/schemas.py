from __future__ import annotations

from pydantic import BaseModel, EmailStr, ConfigDict


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    college_id: str | None
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserOut
