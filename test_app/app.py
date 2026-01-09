"""Flask application for testing stageflow pipelines."""

import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit

# Add parent directory to path for stageflow imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipelines import PIPELINES
from services.groq_client import GroqClient

from stageflow import Pipeline, StageOutput, StageStatus
from stageflow.context import ContextSnapshot
from stageflow.context.types import Message
from stageflow.core import create_stage_context

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

groq_client = GroqClient()

conversation_history: list[Message] = []


def get_dag_structure(pipeline: Pipeline) -> dict:
    """Extract DAG structure from pipeline for visualization."""
    nodes = []
    edges = []

    for name, spec in pipeline.stages.items():
        nodes.append({
            "id": name,
            "label": name,
            "kind": spec.kind.value if spec.kind else "unknown",
        })
        for dep in spec.dependencies:
            edges.append({
                "source": dep,
                "target": name,
            })

    return {"nodes": nodes, "edges": edges}


class SocketIOEventSink:
    """Event sink that emits events to SocketIO clients."""

    def __init__(self, socketio_instance: SocketIO, run_id: str):
        self.socketio = socketio_instance
        self.run_id = run_id

    async def emit(self, *, type: str, data: dict | None) -> None:
        self.try_emit(type=type, data=data)

    def try_emit(self, *, type: str, data: dict | None) -> None:
        event_data = {
            "run_id": self.run_id,
            "type": type,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.socketio.emit("pipeline_event", event_data)
        logger.info(f"Event: {type} - {json.dumps(data or {})[:200]}")


async def run_pipeline_async(
    pipeline_id: str,
    input_text: str,
    run_id: str,
) -> dict:
    """Run a pipeline asynchronously and emit events."""
    global conversation_history

    pipeline_config = PIPELINES.get(pipeline_id)
    if not pipeline_config:
        return {"error": f"Unknown pipeline: {pipeline_id}"}

    if pipeline_id in ("llm", "full"):
        pipeline = pipeline_config["create"](groq_client=groq_client)
    else:
        pipeline = pipeline_config["create"]()

    event_sink = SocketIOEventSink(socketio, run_id)

    snapshot = ContextSnapshot(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=uuid4(),
        interaction_id=uuid4(),
        topology=pipeline_id,
        channel="web",
        execution_mode="test",
        messages=list(conversation_history),
        input_text=input_text,
    )

    create_stage_context(snapshot=snapshot, config={})

    graph = pipeline.build()

    event_sink.try_emit(
        type="pipeline.started",
        data={
            "pipeline_id": pipeline_id,
            "stages": [s.name for s in graph.stage_specs],
        },
    )

    results = {}
    errors = []

    stages_by_name = {s.name: s for s in graph.stage_specs}
    in_degree = {s.name: len(s.dependencies) for s in graph.stage_specs}
    completed_outputs: dict[str, StageOutput] = {}

    async def run_stage(stage_name: str) -> tuple[str, StageOutput]:
        spec = stages_by_name[stage_name]

        event_sink.try_emit(
            type=f"stage.{stage_name}.started",
            data={"stage": stage_name, "kind": spec.kind.value if spec.kind else None},
        )

        try:
            prior_outputs = {
                dep: completed_outputs[dep]
                for dep in spec.dependencies
                if dep in completed_outputs
            }

            from stageflow.stages.inputs import create_stage_inputs
            from stageflow.stages.ports import CorePorts

            inputs = create_stage_inputs(
                snapshot=snapshot,
                prior_outputs=prior_outputs,
                ports=CorePorts(),
            )

            stage_ctx = create_stage_context(
                snapshot=snapshot,
                config={"inputs": inputs},
            )

            if isinstance(spec.runner, type):
                stage_instance = spec.runner()
                output = await stage_instance.execute(stage_ctx)
            elif hasattr(spec.runner, "execute"):
                output = await spec.runner.execute(stage_ctx)
            else:
                output = await spec.runner(stage_ctx)

            if not isinstance(output, StageOutput):
                output = StageOutput.ok(data=output if isinstance(output, dict) else {})

            event_sink.try_emit(
                type=f"stage.{stage_name}.completed",
                data={
                    "stage": stage_name,
                    "status": output.status.value,
                    "data": output.data,
                },
            )

            return stage_name, output

        except Exception as e:
            logger.exception(f"Stage {stage_name} failed")
            event_sink.try_emit(
                type=f"stage.{stage_name}.failed",
                data={"stage": stage_name, "error": str(e)},
            )
            return stage_name, StageOutput.fail(error=str(e))

    ready = [name for name, deg in in_degree.items() if deg == 0]
    pending = set(stages_by_name.keys())

    while pending:
        if not ready:
            break

        tasks = [asyncio.create_task(run_stage(name)) for name in ready]
        ready = []

        done_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in done_results:
            if isinstance(result, Exception):
                errors.append(str(result))
                continue

            stage_name, output = result
            completed_outputs[stage_name] = output
            pending.discard(stage_name)

            results[stage_name] = {
                "status": output.status.value,
                "data": output.data,
                "error": output.error,
            }

            if output.status == StageStatus.CANCEL:
                event_sink.try_emit(
                    type="pipeline.cancelled",
                    data={
                        "stage": stage_name,
                        "reason": output.data.get("cancel_reason", ""),
                    },
                )
                pending.clear()
                break

            for other_name in list(pending):
                other_spec = stages_by_name[other_name]
                if stage_name in other_spec.dependencies:
                    in_degree[other_name] -= 1
                    if in_degree[other_name] == 0:
                        ready.append(other_name)

    final_response = None
    for stage_name in ["output_guard", "llm", "summarize", "echo"]:
        if stage_name in results:
            data = results[stage_name].get("data", {})
            final_response = data.get("response") or data.get("text") or data.get("echo") or data.get("message")
            if final_response:
                break

    if final_response:
        conversation_history.append(Message(role="user", content=input_text))
        conversation_history.append(Message(role="assistant", content=final_response))
        if len(conversation_history) > 20:
            conversation_history = conversation_history[-20:]

    event_sink.try_emit(
        type="pipeline.completed",
        data={
            "stages_completed": list(results.keys()),
            "response": final_response,
            "errors": errors,
        },
    )

    return {
        "run_id": run_id,
        "pipeline_id": pipeline_id,
        "results": results,
        "response": final_response,
        "errors": errors,
    }


def get_pipeline_metadata() -> dict:
    """Return JSON-serializable metadata for each pipeline."""
    return {
        pid: {
            "name": cfg["name"],
            "description": cfg["description"],
            "instructions": cfg.get("instructions", ""),
        }
        for pid, cfg in PIPELINES.items()
    }


@app.route("/")
def index():
    """Render the main page."""
    return render_template(
        "index.html",
        pipelines=PIPELINES,
        pipeline_meta=get_pipeline_metadata(),
    )


@app.route("/api/pipelines")
def list_pipelines():
    """List available pipelines."""
    return jsonify({
        pid: {
            "name": p["name"],
            "description": p["description"],
        }
        for pid, p in PIPELINES.items()
    })


@app.route("/api/pipelines/<pipeline_id>/dag")
def get_pipeline_dag(pipeline_id: str):
    """Get DAG structure for a pipeline."""
    pipeline_config = PIPELINES.get(pipeline_id)
    if not pipeline_config:
        return jsonify({"error": "Pipeline not found"}), 404

    pipeline = pipeline_config["create"]()
    dag = get_dag_structure(pipeline)
    return jsonify(dag)


@app.route("/api/chat", methods=["POST"])
def chat():
    """Handle chat messages."""
    data = request.json
    pipeline_id = data.get("pipeline_id", "simple")
    message = data.get("message", "")
    run_id = str(uuid4())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            run_pipeline_async(pipeline_id, message, run_id)
        )
    finally:
        loop.close()

    return jsonify(result)


@app.route("/api/clear-history", methods=["POST"])
def clear_history():
    """Clear conversation history."""
    global conversation_history
    conversation_history = []
    return jsonify({"status": "ok"})


@socketio.on("connect")
def handle_connect():
    """Handle client connection."""
    logger.info("Client connected")
    emit("connected", {"status": "ok"})


@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection."""
    logger.info("Client disconnected")


@socketio.on("run_pipeline")
def handle_run_pipeline(data):
    """Handle pipeline execution request via WebSocket."""
    pipeline_id = data.get("pipeline_id", "simple")
    message = data.get("message", "")
    run_id = str(uuid4())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            run_pipeline_async(pipeline_id, message, run_id)
        )
    finally:
        loop.close()

    emit("pipeline_result", result)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Stageflow Test Application")
    print("=" * 60)
    print(f"Available pipelines: {', '.join(PIPELINES.keys())}")
    print(f"Groq API Key: {'Set' if os.getenv('GROQ_API_KEY') else 'Not set'}")
    print("=" * 60)
    print("Starting server at http://localhost:5000")
    print("=" * 60 + "\n")

    socketio.run(app, host="0.0.0.0", port=3003, debug=True)
