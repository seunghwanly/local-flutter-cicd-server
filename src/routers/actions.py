"""Webhook and trigger routes."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request

from ..core.dependencies import get_diagnostics, get_github_action_service, get_shorebird_action_service
from ..models import ActionResponse, ShorebirdWebhookRequest


router = APIRouter(prefix="/github-action", tags=["GitHub Actions"])


@router.post("/build", response_model=ActionResponse)
async def handle_github_build_action(
    request: Request,
    x_hub_signature_256: str = Header(None, description="GitHub webhook signature"),
    x_hub_signature: str = Header(None, description="GitHub webhook signature (sha1)"),
    x_github_event: str = Header(None, description="GitHub event type"),
    x_github_delivery: str = Header(None, description="GitHub delivery id"),
    diagnostics=Depends(get_diagnostics),
    github_action_service=Depends(get_github_action_service),
) -> ActionResponse:
    action_diagnostics = diagnostics.get_github_action_diagnostics()
    if not action_diagnostics.ready:
        raise HTTPException(
            status_code=503,
            detail=f"GitHub action is not configured. Missing: {', '.join(action_diagnostics.missing)}",
        )

    body = await request.body()
    if not github_action_service.verify_signature(body, x_hub_signature_256, x_hub_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    return github_action_service.handle(payload, x_github_event, x_github_delivery)


@router.post("/shorebird", response_model=ActionResponse)
async def handle_github_shorebird_action(
    request: Request,
    webhook_payload: ShorebirdWebhookRequest = Body(
        ...,
        description="GitHub가 전달하는 Shorebird webhook payload",
    ),
    x_hub_signature_256: str = Header(None, description="GitHub webhook signature"),
    x_hub_signature: str = Header(None, description="GitHub webhook signature (sha1)"),
    x_github_event: str = Header(None, description="GitHub event type"),
    x_github_delivery: str = Header(None, description="GitHub delivery id"),
    diagnostics=Depends(get_diagnostics),
    shorebird_action_service=Depends(get_shorebird_action_service),
) -> ActionResponse:
    action_diagnostics = diagnostics.get_shorebird_action_diagnostics()
    if not action_diagnostics.ready:
        raise HTTPException(
            status_code=503,
            detail=f"Shorebird action is not configured. Missing: {', '.join(action_diagnostics.missing)}",
        )

    body = await request.body()
    if not shorebird_action_service.verify_signature(body, x_hub_signature_256, x_hub_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    return shorebird_action_service.handle(
        webhook_payload.model_dump(exclude_none=True),
        x_github_event,
        x_github_delivery,
    )

