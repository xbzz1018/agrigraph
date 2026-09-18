"""模型、检索和 API 之间共享的结构化农业对象。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AgricultureQuery(BaseModel):
    crop: Literal["番茄", "水稻", "未知"] = "未知"
    taskType: Literal["ENTITY", "SYMPTOM", "PATHOGEN", "CONDITION", "CONTROL", "RELATION"] = "SYMPTOM"
    diseaseName: str = Field(default="", max_length=120)
    symptoms: list[str] = Field(default_factory=list, max_length=12)
    plantParts: list[str] = Field(default_factory=list, max_length=8)
    target: str = Field(default="候选病虫害", max_length=120)

    @field_validator("symptoms", "plantParts")
    @classmethod
    def clean_terms(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(str(value).strip()[:80] for value in values if str(value).strip()))

    def retrieval_text(self, original: str = "") -> str:
        terms = [self.crop, self.diseaseName, *self.plantParts, *self.symptoms, self.target, original]
        return " ".join(dict.fromkeys(term for term in terms if term and term != "未知"))[:2000]


class VisionObservation(BaseModel):
    crop: Literal["番茄", "水稻", "未知"] = "未知"
    plantParts: list[str] = Field(default_factory=list, max_length=8)
    symptoms: list[str] = Field(default_factory=list, max_length=12)
    qualityWarnings: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("plantParts", "symptoms", "qualityWarnings")
    @classmethod
    def clean_terms(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(str(value).strip()[:120] for value in values if str(value).strip()))

    def to_query(self) -> AgricultureQuery:
        return AgricultureQuery(
            crop=self.crop,
            taskType="SYMPTOM",
            # 视觉模型可能在质量提示中给出“疑似某虫害”的弱线索；它仍只是检索词，不是最终诊断。
            symptoms=list(dict.fromkeys([*self.symptoms, *self.qualityWarnings])),
            plantParts=self.plantParts,
            target="根据可见症状召回候选病虫害",
        )


class AnswerClaim(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    evidenceIds: list[str] = Field(default_factory=list, max_length=8)


class AnswerDraft(BaseModel):
    answer: str = Field(min_length=1, max_length=5000)
    claims: list[AnswerClaim] = Field(default_factory=list, max_length=12)
