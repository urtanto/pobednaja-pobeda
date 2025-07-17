from typing import TYPE_CHECKING

from pydantic import UUID4, BaseModel, Field, PastDatetime, model_validator

from services.task.enums import Status


class TaskID(BaseModel):
    id: UUID4 = Field(..., description='Unique identifier of the task')


class UpdateTaskRequest(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=255, description='Title of the task')
    description: str | None = Field(None, description='Description of the task')
    status: Status | None = Field(None, description='Status of the task')
    author_id: UUID4 | None = Field(None, description='ID of the user who created the task')
    assignee_id: UUID4 | None = Field(None, description='ID of the user who assigned the task')

    @model_validator(mode='after')
    def ensure_at_least_one_field(self) -> 'UpdateTaskRequest':
        values = [
            self.title,
            self.description,
            self.status,
            self.author_id,
            self.assignee_id,
        ]

        if all(v is None for v in values):
            raise ValueError("At least one field must be provided for task update.")
        return self


class CreateTaskRequest(UpdateTaskRequest):
    title: str = Field(..., min_length=3, max_length=255, description='Title of the task')
    status: Status = Field(..., description='Status of the task')
    author_id: UUID4 = Field(..., description='ID of the user who created the task')


class TaskDB(TaskID, CreateTaskRequest):
    created_at: PastDatetime | None = Field(None, description='Date the task was created')
    watchers: list[UUID4] | None = Field(None, description='List of users who watched the task')
    executors: list[UUID4] | None = Field(None, description='List of users who execute the task')


class FilterTaskRequest(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=255, description='Title of the task')
    status: Status | None = Field(None, description='Status of the task')
    author_id: UUID4 | None = Field(None, description='ID of the user who created the task')


class TaskResponse(BaseModel):
    payload: TaskDB = Field(..., description='Task data')


class MultiTaskResponse(BaseModel):
    payload: list[TaskDB] = Field(..., description='List of tasks')
