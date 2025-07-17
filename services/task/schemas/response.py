from typing import Any

from pydantic import BaseModel, Field
from starlette.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_400_BAD_REQUEST



class BaseResponse(BaseModel):
    status: int = HTTP_200_OK
    error: bool = False


class BaseCreateResponse(BaseModel):
    status: int = HTTP_201_CREATED
    error: bool = False


class BaseErrorResponse(BaseModel):
    status: int = HTTP_400_BAD_REQUEST
    error: bool = True
    details: Any = Field(..., examples=['Invalid input data'])
