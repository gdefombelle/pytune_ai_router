from pydantic import BaseModel
from typing import Optional, List

class ModelHypothesis(BaseModel):
    name: Optional[str]
    variant: Optional[str]
    confidence: Optional[float]

class PianoGuessInput(BaseModel):
    brand: Optional[str]
    distributor: Optional[str]
    serial_number: Optional[str]
    year_estimated: Optional[int]
    category: Optional[str]
    type: Optional[str]
    size_cm: Optional[int]
    nb_notes: Optional[int]
    model_hypothesis: Optional[ModelHypothesis]
    photos: Optional[List[str]]  # noms ou types des photos
