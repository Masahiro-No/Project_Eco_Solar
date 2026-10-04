from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


class UpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Literal["operator", "admin"] | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateUserRequest":
        if self.email is None and self.password is None and self.role is None:
            raise ValueError("At least one of 'email', 'password' or 'role' must be provided")
        return self

