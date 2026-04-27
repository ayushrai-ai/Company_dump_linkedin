from __future__ import annotations

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator


class CompanyPost(BaseModel):
    posted_at: Optional[str] = None
    content: Optional[str] = None
    likes: Optional[int] = None
    comments: Optional[int] = None


class Company(BaseModel):
    linkedin_url: str
    name: Optional[str] = None
    tagline: Optional[str] = None
    description: Optional[str] = None

    website: Optional[str] = None
    phone: Optional[str] = None
    headquarters: Optional[str] = None
    founded: Optional[str] = None
    industry: Optional[str] = None
    company_type: Optional[str] = None
    company_size: Optional[str] = None
    specialties: Optional[str] = None
    posts: List[CompanyPost] = Field(default_factory=list)

    extra: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("linkedin_url")
    @classmethod
    def validate_linkedin_url(cls, v: str) -> str:
        if "linkedin.com/company/" not in v:
            raise ValueError("Must be a valid LinkedIn company URL (contains /company/)")
        return v

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def to_json(self, **kwargs) -> str:
        return self.model_dump_json(**kwargs)
