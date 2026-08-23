from fastapi import APIRouter, Depends, HTTPException

from authz.integrations.fastapi import requires

from examples.sample_app import domain
from examples.sample_app.auth import get_authz_client, get_current_user

router = APIRouter()


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    _: None = Depends(
        requires("viewer", "project:{project_id}",
                 get_client=get_authz_client, get_subject=get_current_user)
    ),
):
    project = domain.projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.post("/projects/{project_id}/tasks", status_code=201)
async def create_task(
    project_id: str,
    body: domain.CreateTaskRequest,
    _: None = Depends(
        requires("editor", "project:{project_id}",
                 get_client=get_authz_client, get_subject=get_current_user)
    ),
):
    task_id = f"t{len(domain.tasks) + 1}"
    task = domain.Task(
        id=task_id, project_id=project_id, title=body.title, assignee=body.assignee
    )
    domain.tasks[task_id] = task
    return task
