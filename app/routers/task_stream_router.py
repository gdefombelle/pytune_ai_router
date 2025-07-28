from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from pytune_llm.task_reporting.task_pubsub import get_queue
import asyncio

router = APIRouter(prefix="/api")

@router.get("/sse/tasks/{agent}", response_class=EventSourceResponse)
async def stream_agent_tasks(agent: str):
    queue = get_queue(agent)

    async def event_generator():
        while True:
            try:
                msg = await queue.get()
                yield {"event": "task", "data": msg}
            except asyncio.CancelledError:
                break  # proprement déconnecté

    return EventSourceResponse(event_generator())
