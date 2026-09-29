from pydantic import BaseModel


class TextUploadRequest(BaseModel):
    filename: str
    content: str
