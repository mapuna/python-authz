from fastapi import APIRouter, Depends, HTTPException

from authz.integrations.fastapi import requires

from examples.sample_app import domain
from examples.sample_app.auth import get_authz_client, get_current_user

router = APIRouter()


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    _: None = Depends(
        requires("viewer", "task:{task_id}",
                 get_client=get_authz_client, get_subject=get_current_user)
    ),
):
    task = domain.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    body: domain.UpdateTaskRequest,
    _: None = Depends(
        requires("editor", "task:{task_id}",
                 get_client=get_authz_client, get_subject=get_current_user)
    ),
):
    task = domain.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if body.title is not None:
        task.title = body.title
    if body.assignee is not None:
        task.assignee = body.assignee
    return task
