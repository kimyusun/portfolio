from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from pydantic import BaseModel, Field

from ai.emotion_policy import IDX2KOR, KOR2IDX, to_label_idx


class Place(BaseModel):
    placeId: int
    name: str
    category: str
    latitude: float
    longitude: float


class Memo(BaseModel):
    category: Optional[str] = None
    emotionLabel: Optional[Union[int, str]] = None
    emotionScore: Optional[float] = None
    createdAt: datetime


class RecentEmotion(BaseModel):
    label: Union[int, str]
    score: float = Field(0.0, ge=0, le=1)


class PlaceSignal(BaseModel):
    placeId: int
    posRatio: Optional[float] = Field(None, ge=0, le=1)
    followedPositiveCount: Optional[int] = Field(None, ge=0)
