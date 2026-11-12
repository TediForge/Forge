"""Image and video perception specialist."""

from typing import Any, Callable

from src.agents.base import AgentExecutionError, BaseAgent
from src.context.state import ExecutionState


class VisionAgent(BaseAgent):
    name = "vision"
    skillName = "vision"
    capabilities = frozenset({
        "vision", "image_analysis", "image_understanding", "video_analysis",
        "video_understanding", "keyframe_extraction", "frame_sampling", "ocr",
        "spatial_extraction", "object_detection", "visual_reasoning",
    })

    async def execute(self, instruction: str, state: ExecutionState, task_id: int | None = None) -> str:
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.task", instruction)
        images = [
            attachment
            for attachment in state.getVariable("inlineAttachments", [])
            if attachment.get("mimeType", "").casefold().startswith("image/")
        ]
        if images:
            analyze_image: Callable[..., Any] | None = getattr(self.dispatcher, "analyze_image", None)
            if not callable(analyze_image):
                raise AgentExecutionError(
                    "Vision attachments require a dispatcher with analyze_image support"
                )
            result = await self._normalize_result(analyze_image(
                prompt=self.build_prompt(instruction, state, task_id),
                system_prompt=self.system_prompt,
                images=images,
            ))
        else:
            result = await self._dispatch(instruction, state, task_id)
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.status", "completed")
        self.send_message(state, "document", "perception_result", result, task_id, {
            "domain": "vision", "source_types": ["image", "video"],
        })
        return result