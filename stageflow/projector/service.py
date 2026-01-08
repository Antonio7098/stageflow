import logging
import uuid
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger("ws_projector")


def _coerce_uuid_str(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except Exception:
        return None


class WSMetadata(BaseModel):
    pipeline_run_id: str
    request_id: str
    org_id: str | None = None


class WSOutboundMessage(BaseModel):
    type: str
    payload: Any | None = None
    metadata: WSMetadata


class WSStatusUpdatePayload(BaseModel):
    service: str
    status: str
    metadata: dict[str, Any] | None = None


class WSMessageProjector:
    def project(
        self,
        message: dict[str, Any],
        *,
        connection_org_id: Any | None,
        context_request_id: Any | None,
        context_pipeline_run_id: Any | None,
    ) -> dict[str, Any]:
        msg_type = message.get("type")
        payload = message.get("payload")
        metadata = message.get("metadata")

        payload_dict = payload if isinstance(payload, dict) else None

        req_id = (
            _coerce_uuid_str(
                (metadata or {}).get("request_id") if isinstance(metadata, dict) else None
            )
            or _coerce_uuid_str(payload_dict.get("request_id") if payload_dict else None)
            or _coerce_uuid_str(payload_dict.get("requestId") if payload_dict else None)
            or _coerce_uuid_str(
                ((payload_dict.get("metadata") or {}).get("request_id"))
                if payload_dict and isinstance(payload_dict.get("metadata"), dict)
                else None
            )
            or _coerce_uuid_str(
                ((payload_dict.get("metadata") or {}).get("requestId"))
                if payload_dict and isinstance(payload_dict.get("metadata"), dict)
                else None
            )
            or _coerce_uuid_str(context_request_id)
            or str(uuid.uuid4())
        )

        run_id = (
            _coerce_uuid_str(
                (metadata or {}).get("pipeline_run_id") if isinstance(metadata, dict) else None
            )
            or _coerce_uuid_str(payload_dict.get("pipeline_run_id") if payload_dict else None)
            or _coerce_uuid_str(payload_dict.get("pipelineRunId") if payload_dict else None)
            or _coerce_uuid_str(
                ((payload_dict.get("metadata") or {}).get("pipeline_run_id"))
                if payload_dict and isinstance(payload_dict.get("metadata"), dict)
                else None
            )
            or _coerce_uuid_str(
                ((payload_dict.get("metadata") or {}).get("pipelineRunId"))
                if payload_dict and isinstance(payload_dict.get("metadata"), dict)
                else None
            )
            or _coerce_uuid_str(context_pipeline_run_id)
            or str(uuid.uuid4())
        )

        org_id = _coerce_uuid_str(connection_org_id)

        projected = dict(message)
        projected["metadata"] = {
            "pipeline_run_id": run_id,
            "request_id": req_id,
        }
        if org_id:
            projected["metadata"]["org_id"] = org_id

        if msg_type == "status.update":
            if not isinstance(payload, dict):
                raise ValueError("status.update payload must be an object")
            WSStatusUpdatePayload.model_validate(payload)

        try:
            validated = WSOutboundMessage.model_validate(projected)
        except Exception as exc:
            logger.error(
                "WS projector validation failed",
                extra={
                    "service": "ws_projector",
                    "message_type": msg_type,
                    "error": str(exc),
                },
            )
            raise

        return validated.model_dump(exclude_none=True)


# Backward compatibility alias
ProjectorService = WSMessageProjector


__all__ = [
    "_coerce_uuid_str",
    "WSMetadata",
    "WSOutboundMessage",
    "WSStatusUpdatePayload",
    "WSMessageProjector",
    # Backward compatibility
    "ProjectorService",
]
