from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status

from .schemas import Role


@dataclass(frozen=True)
class Actor:
    id: str
    role: Role


def current_actor(
    x_actor_id: str = Header(default="local-user"),
    x_role: Role = Header(default=Role.WORKSPACE_USER),
) -> Actor:
    """Development identity adapter; replace with verified OIDC claims before deployment."""
    return Actor(id=x_actor_id, role=x_role)


def require_administrator(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.role != Role.ADMINISTRATOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required for this workspace operation.",
        )
    return actor


def authorize_workspace(workspace_id: UUID, actor: Actor = Depends(current_actor)) -> Actor:
    del workspace_id
    return actor
