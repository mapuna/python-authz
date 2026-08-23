from pydantic import BaseModel


class Project(BaseModel):
    id: str
    name: str


class Task(BaseModel):
    id: str
    project_id: str
    title: str
    assignee: str | None = None


projects: dict[str, Project] = {}
tasks: dict[str, Task] = {}


class CreateTaskRequest(BaseModel):
    title: str
    assignee: str | None = None


class UpdateTaskRequest(BaseModel):
    title: str | None = None
    assignee: str | None = None
