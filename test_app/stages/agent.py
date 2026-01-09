"""Agent stage with tool execution capabilities."""

import asyncio
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from stageflow import StageContext, StageKind, StageOutput
from stageflow.tools import get_tool_registry

from .toggle_tool import TogglePanelTool


@dataclass(frozen=True)
class Action:
    """Concrete action implementation for tool execution."""

    id: UUID
    type: str
    payload: dict[str, Any]


class AgentStage:
    """Agent stage that can execute tools based on user input."""

    name = "agent"
    kind = StageKind.TRANSFORM

    def __init__(self):
        self.registry = get_tool_registry()
        self._register_tools()

    def _register_tools(self) -> None:
        """Register available tools."""
        self.registry.register(TogglePanelTool())

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Execute agent with tool use."""
        inputs = ctx.config.get("inputs")
        if inputs:
            input_text = inputs.snapshot.input_text or ""
            route = inputs.get_from("dispatch", "route", default="agent")
        else:
            input_text = ctx.snapshot.input_text or ""
            route = "agent"

        if route != "agent":
            return StageOutput.skip(
                reason=f"routed_to_{route}",
                data={"route": route},
            )

        await asyncio.sleep(0.1)

        actions = self._parse_intent(input_text)
        results = []

        for action in actions:
            try:
                output = await self.registry.execute(action, ctx.to_dict())
                results.append({
                    "action": action.type,
                    "success": output.success if output else False,
                    "data": output.data if output else None,
                })
            except Exception as e:
                results.append({
                    "action": action.type,
                    "success": False,
                    "error": str(e),
                })

        response = self._generate_response(input_text, results)

        return StageOutput.ok(
            response=response,
            actions_executed=len(results),
            action_results=results,
        )

    def _parse_intent(self, input_text: str) -> list[Action]:
        """Parse user intent and create actions."""
        actions = []
        lower_text = input_text.lower().strip()

        print(f"[Agent] Parsing input: '{input_text}'")
        print(f"[Agent] Lowercased: '{lower_text}'")

        # Intent detection patterns (allowing variations like "turn it on")
        turn_on_patterns = [
            r"\bturn(?:\s+\w+)?\s+on\b",
            r"\benable\b",
            r"\bswitch(?:\s+\w+)?\s+on\b",
            r"\bactivate\b",
        ]
        turn_off_patterns = [
            r"\bturn(?:\s+\w+)?\s+off\b",
            r"\bdisable\b",
            r"\bswitch(?:\s+\w+)?\s+off\b",
            r"\bdeactivate\b",
        ]

        matched_on = any(re.search(pattern, lower_text) for pattern in turn_on_patterns)
        matched_off = any(re.search(pattern, lower_text) for pattern in turn_off_patterns)

        if matched_on or lower_text == "on":
            print("[Agent] Matched TURN ON")
            actions.append(Action(
                id=uuid4(),
                type="TOGGLE_PANEL",
                payload={"state": True},
            ))
        elif matched_off or lower_text == "off":
            print("[Agent] Matched TURN OFF")
            actions.append(Action(
                id=uuid4(),
                type="TOGGLE_PANEL",
                payload={"state": False},
            ))
        else:
            print("[Agent] No toggle pattern matched")

        print(f"[Agent] Created {len(actions)} actions")
        return actions

    def _generate_response(self, _input_text: str, results: list[dict]) -> str:
        """Generate response based on action results."""
        if not results:
            return "I didn't understand what you want me to do. Try asking me to turn something on or off."

        responses = []
        for result in results:
            if result["success"]:
                data = result.get("data", {})
                if "message" in data:
                    responses.append(data["message"])
                else:
                    responses.append(f"Executed {result['action']} successfully")
            else:
                error = result.get("error", "Unknown error")
                responses.append(f"Failed to execute {result['action']}: {error}")

        return " ".join(responses)


__all__ = ["AgentStage"]
