from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DiscordProfile(BaseModel):
    id: str
    username: str
    global_name: str | None = None
    avatar: str | None = None
    discriminator: str | None = None

    model_config = {"extra": "allow"}


class DiscordTokenData(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    scope: str = ""
    expires_in: int | None = None

    model_config = {"extra": "allow"}


class SalesforceOpportunity(BaseModel):
    stageName: str | None = None
    termCode: str | None = None
    career: str | None = None
    type: str | None = None
    internationalStudent: Any = None
    firstGeneration: Any = None
    enrollmentDepositPaid: Any = None
    enrollmentDepositStatus: str | None = None
    collegeName: str | None = None
    locationName: str | None = None
    collegeProgramCode: str | None = None
    programCode: str | None = None
    createdDate: str | None = None
    currentLocation: str | None = None
    academicPlanName: str | None = None

    model_config = {"extra": "allow"}


class StudentProfile(BaseModel):
    asurite: str
    name: str = ""
    fullName: str = ""
    email: str | None = None
    state: str | None = None
    country: str | None = None
    contactId: str | None = None
    opportunities: list[SalesforceOpportunity] = Field(default_factory=list)
    inState: bool = False
    outOfState: bool = False
    # Summary fields populated when a matching opportunity is found
    college: str | None = None
    program: str | None = None
    career: str | None = None
    admitType: str | None = None
    firstTimeFreshman: bool = False
    transfer: bool = False
    collegeProgramCode: str | None = None
    is_international: bool = False
    international: bool = False
    stateOfResidence: str | None = None
    enrollmentDepositPaid: bool = False
    stageName: str | None = None
    current: bool | None = None
    firstYear: bool = False
    depositPaid: bool = False
    campus: str = "N/A"
    locationName: str = "N/A"
    termCode: str | None = None
    selectedOpportunity: SalesforceOpportunity | None = None
    type: str | None = None

    model_config = {"extra": "allow"}
