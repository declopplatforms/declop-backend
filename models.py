from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ─── Request / Response Schemas ───────────────────────────────────────────────

class PostCreate(BaseModel):
    """Schema for creating a new post (form fields — image handled separately)."""
    title:                str
    description:          str
    by:                   str
    resource1:            str
    regions:              Optional[List[str]] = []
    languages:            Optional[List[str]] = []
    segment:              Optional[str]       = None
    cta:                  Optional[str]       = None
    resource2:            Optional[str]       = None
    resource3:            Optional[str]       = None

    scheduled_date:       Optional[str]       = None


class PostOut(BaseModel):
    """Schema for a post returned from Supabase."""
    id:                   str
    title:                str
    description:          str
    by:                   str
    image_url:            str
    regions:              Optional[List[str]] = []
    languages:            Optional[List[str]] = []
    segment:              Optional[str]       = None
    cta:                  Optional[str]       = None
    resource1:            Optional[str]       = None
    resource2:            Optional[str]       = None
    resource3:            Optional[str]       = None

    scheduled_date:       Optional[str]       = None
    created_at:           Optional[datetime]  = None
    expires_at:           Optional[datetime]  = None

    class Config:
        from_attributes = True
