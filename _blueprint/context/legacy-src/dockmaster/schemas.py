"""Pydantic models for Dockmaster."""
from typing import Annotated
from datetime import datetime, timezone

import isodate
from pydantic import BaseModel, Field
from pydantic import BeforeValidator, PlainSerializer
from pydantic import ConfigDict

#### Customizations to Pydantic base class ####
# - Custom datetime validator and serializer
DockmasterDatetime = Annotated[
    datetime,
    BeforeValidator(lambda x: datetime.astimezone(tz=timezone.utc)),
    PlainSerializer(lambda x: isodate.datetime_isoformat(x))
]

class DockmasterBaseModel(BaseModel):
    """Custom global configurations"""
    
    model_config = ConfigDict(
        extra='ignore',
    )

#### Pydantic Classes ####
class DockmasterUserToken(BaseModel):
    """JWT token payload"""
    email: str = Field(..., description="User email used as User ID")
    exp: DockmasterDatetime = Field(..., description="Token expiration datetime ISO format")
