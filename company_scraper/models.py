from __future__ import annotations

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator


class CompanyPost(BaseModel):
    posted_at: Optional[str] = None
    content: Optional[str] = None
    likes: Optional[int] = None
    comments: Optional[int] = None


class Experience(BaseModel):
    position_title: Optional[str] = None
    institution_name: Optional[str] = None
    linkedin_url: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    duration: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None


class Education(BaseModel):
    institution_name: Optional[str] = None
    degree: Optional[str] = None
    linkedin_url: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    description: Optional[str] = None


class Accomplishment(BaseModel):
    category: str
    title: str
    issuer: Optional[str] = None
    issued_date: Optional[str] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None


class Contact(BaseModel):
    type: str
    value: str
    label: Optional[str] = None


class PersonPost(BaseModel):
    posted_at: Optional[str] = None
    content: Optional[str] = None


class Person(BaseModel):
    linkedin_url: str
    name: Optional[str] = None
    location: Optional[str] = None
    open_to_work: bool = False
    about: Optional[str] = None
    experiences: List[Experience] = Field(default_factory=list)
    educations: List[Education] = Field(default_factory=list)
    accomplishments: List[Accomplishment] = Field(default_factory=list)
    contacts: List[Contact] = Field(default_factory=list)
    posts: List[PersonPost] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def to_json(self, **kwargs) -> str:
        return self.model_dump_json(**kwargs)


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