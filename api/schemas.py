from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ScrapeRequest(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=5)
    region: str = Field(default="uae")
    max_products: int = Field(default=25, ge=1, le=100)
    headless: bool = True
    output: str = Field(default="excel")

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, value: list[str]) -> list[str]:
        cleaned = []
        seen = set()
        for item in value:
            item = " ".join(item.strip().split())
            if item and item.lower() not in seen:
                cleaned.append(item)
                seen.add(item.lower())
        if not cleaned:
            raise ValueError("At least one non-empty keyword is required")
        return cleaned

    @field_validator("region")
    @classmethod
    def valid_region(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"uae", "ksa", "both"}:
            raise ValueError("region must be uae, ksa, or both")
        return value

    @field_validator("output")
    @classmethod
    def valid_output(cls, value: str) -> str:
        value = value.lower().strip()
        if value != "excel":
            raise ValueError("output must be excel")
        return value
