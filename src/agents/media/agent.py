"""Image and video creation and rendering specialist."""

from src.agents.base import BaseAgent
from src.context.state import ExecutionState


class MediaAgent(BaseAgent):
    name = "media"
    skillName = "media"
    capabilities = frozenset({
        "media", "image_generation", "text_to_image", "video_generation",
        "text_to_video", "video_composition", "keyframing", "timeline_editing",
        "asset_processing", "asset_rendering", "media_render", "image_editing",
    })

    async def execute(self, instruction: str, state: ExecutionState, task_id: int | None = None) -> str:
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.task", instruction)
        result = await self._dispatch(instruction, state, task_id)
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.status", "completed")
        self.send_message(state, "vision", "render_review_request", result, task_id, {
            "domain": "media", "requires_visual_qa": True,
        })
        return result