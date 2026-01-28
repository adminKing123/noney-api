from pydantic import BaseModel, Field

class TitleSummary(BaseModel):
    title: str = Field(
        description="A short plain-text title under 100 characters"
    )
