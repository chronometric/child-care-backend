from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CreateEventBody(BaseModel):
    event_name: str
    patient_name: str
    patient_personal_id: Optional[str] = Field(None, max_length=128)
    start_time: datetime
    end_time: datetime
    description: Optional[str] = Field(None, max_length=500)

class UpdateEventBody(BaseModel):
    event_name: Optional[str] = None
    patient_name: Optional[str] = None
    patient_personal_id: Optional[str] = Field(None, max_length=128)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = Field(None, max_length=500)
