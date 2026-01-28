from typing import Literal
from pydantic import BaseModel, Field

class TitleSummary(BaseModel):
    title: str = Field(
        description="A short plain-text title under 100 characters"
    )

ValidAspectRatio = Literal[
    "1:1",
    "16:9",
    "9:16",
    "4:3",
    "3:4",
    "21:9"
]

class AspectRatioDetection(BaseModel):
    aspect_ratio: ValidAspectRatio = Field(
        default="1:1",
        description=(
            "Aspect ratio decided from the prompt. "
            "Defaults to 1:1 if not explicitly inferred."
        )
    )
