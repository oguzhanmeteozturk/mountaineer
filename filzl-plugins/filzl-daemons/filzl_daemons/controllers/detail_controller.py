from collections import defaultdict
from fastapi import Depends, Request
from sqlalchemy import text
from filzl import ManagedViewPath
from filzl.database import DatabaseDependencies
from filzl.render import Metadata, RenderBase
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from filzl_daemons.controllers.base_controller import DaemonControllerBase
from filzl_daemons.views import get_daemons_view_path
from datetime import datetime
from filzl_daemons.models import QueableStatus

class ActionResult(BaseModel):
    exception: str | None
    exception_stack: str | None
    result_body: str | None


class Action(BaseModel):
    input_body: str | None
    status: QueableStatus

    started_datetime: datetime | None
    ended_datetime: datetime | None

    retry_current_attempt: int
    retry_max_attempts: int | None

    results: list[ActionResult]

class DaemonDetailRender(RenderBase):
    input_body: str
    result_body: str | None
    exception: str | None
    exception_stack: str | None
    actions: list[Action]


class DaemonDetailController(DaemonControllerBase):
    url = "/admin/daemons/{instance_id}"
    view_path = (
        ManagedViewPath.from_view_root(
            get_daemons_view_path(""), package_root_link=None
        )
        / "daemons/detail/page.tsx"
    )

    async def render(
        self,
        instance_id: int,
        request: Request,
        db: AsyncSession = Depends(DatabaseDependencies.get_db_session),
    ) -> DaemonDetailRender:
        await self.require_admin(request)

        instance_query = select(self.local_model_definition.DaemonWorkflowInstance).where(
            self.local_model_definition.DaemonWorkflowInstance.id == instance_id
        )
        result = await db.execute(instance_query)
        instance = result.scalars().first()
        if instance is None:
            raise ValueError(f"Instance with id {instance_id} not found")

        actions_query = select(self.local_model_definition.DaemonAction).where(
            self.local_model_definition.DaemonAction.instance_id == instance_id
        )
        result = await db.execute(actions_query)
        actions = result.scalars().all()

        action_results_query = select(self.local_model_definition.DaemonActionResult).where(
            self.local_model_definition.DaemonActionResult.instance_id == instance_id
        )
        result = await db.execute(action_results_query)
        action_results = result.scalars().all()

        action_results_by_action = defaultdict(list)
        for action_result in action_results:
            action_results_by_action[action_result.action_id].append(action_result)

        return DaemonDetailRender(
            input_body=instance.input_body,
            result_body=instance.result_body,
            exception=instance.exception,
            exception_stack=instance.exception_stack,
            actions=[
                Action(
                    input_body=action.input_body,
                    status=action.status,
                    started_datetime=action.started_datetime,
                    ended_datetime=action.ended_datetime,
                    retry_current_attempt=action.retry_current_attempt,
                    retry_max_attempts=action.retry_max_attempts,
                    results=[
                        ActionResult(
                            exception=result.exception,
                            exception_stack=result.exception_stack,
                            result_body=result.result_body,
                        )
                        for result in action_results_by_action[action.id]
                    ],
                )
                for action in actions
            ]
        )
