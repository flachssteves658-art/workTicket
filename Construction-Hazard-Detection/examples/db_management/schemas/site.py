from __future__ import annotations

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class SiteCreate(BaseModel):
    """Schema representing the data required to create a new site."""

    name: str = Field(min_length=1, max_length=80)
    group_id: int | None = None
    model_config = ConfigDict(str_strip_whitespace=True)


class SiteUpdate(BaseModel):
    """Schema for updating the name of an existing site."""

    site_id: int
    new_name: str = Field(min_length=1, max_length=80)
    model_config = ConfigDict(str_strip_whitespace=True)


class SiteDelete(BaseModel):
    """Schema representing the identifier of a site to be deleted."""

    site_id: int


class SiteUserOp(BaseModel):
    """Operations involving adding or removing a user from a site."""

    site_id: int
    user_id: int


class SiteRead(BaseModel):
    """Details of a site retrieved from the database."""

    id: int
    name: str
    group_id: int | None = None
    group_name: str | None = None
    user_ids: list[int]
