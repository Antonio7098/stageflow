"""Toggle tool for agent to control UI panel state."""

from typing import Any

from stageflow.tools import BaseTool, ToolInput, ToolOutput


class TogglePanelTool(BaseTool):
    """Tool for toggling a UI panel on or off."""

    @property
    def name(self) -> str:
        return "toggle_panel"

    @property
    def description(self) -> str:
        return "Toggle a UI panel on or off"

    @property
    def action_type(self) -> str:
        return "TOGGLE_PANEL"

    async def execute(self, input: ToolInput, _ctx: dict[str, Any]) -> ToolOutput:
        """Handle toggle panel action."""
        state = input.action.payload.get("state", False)

        return ToolOutput(
            success=True,
            data={
                "panel_state": state,
                "message": f"Panel turned {'on' if state else 'off'}",
            },
        )


__all__ = ["TogglePanelTool"]
