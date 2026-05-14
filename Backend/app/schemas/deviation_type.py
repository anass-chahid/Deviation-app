from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DeviationCategory


class DeviationTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: DeviationCategory = DeviationCategory.yard
    active: bool = True


class DeviationTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: DeviationCategory | None = None
    active: bool | None = None


class DeviationTypeRead(DeviationTypeCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)
