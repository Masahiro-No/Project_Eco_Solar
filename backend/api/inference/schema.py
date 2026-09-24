from pydantic import BaseModel


class InferenceRequest(BaseModel):
    text: str
    model_name: str = "bert-base-cased_conll2003"
    version: str = "latest"  # "latest" หรือ "1", "2", "3", ...


class InferenceResponse(BaseModel):
    job_id: str
    status: str = "queued"


class EntityResult(BaseModel):
    entity_type: str   # "PER", "ORG", "LOC", "MISC"
    word: str
    score: float
    start: int | None = None
    end: int | None = None


class InferenceResultResponse(BaseModel):
    job_id: str
    status: str   # "queued" | "in_progress" | "complete" | "not_found"
    result: dict | None = None
