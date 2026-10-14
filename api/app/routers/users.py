"""Managing who may use the dashboards.

The owner manages everyone. An admin manages members: adds them, switches them
off and removes them, but cannot make admins or touch another admin -- otherwise
any admin could make themselves the equal of the person who appointed them, or
lock the others out. The owner's own row is not editable here at all; it comes
from AUTH_OWNER_EMAIL.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import users
from ..auth import User, _allowed, _domain_list, require_admin

router = APIRouter(dependencies=[Depends(require_admin)])

GRANTABLE = ("admin", "member")


def _check_role(actor: User, role: str) -> None:
    if role not in GRANTABLE:
        raise HTTPException(400, f"role must be one of {', '.join(GRANTABLE)}")
    if role == "admin" and actor.role != "owner":
        raise HTTPException(403, "only the owner can make admins")


def _target(actor: User, email: str) -> dict:
    """The row `actor` is about to change, if they may change it."""
    row = users.get(email)
    if row is None:
        raise HTTPException(404, f"{users.normalise(email)} is not on the user list")
    if row["role"] == "owner":
        raise HTTPException(403, "the owner is set by AUTH_OWNER_EMAIL and cannot be changed here")
    if row["email"] == actor.email:
        raise HTTPException(403, "you cannot change your own access")
    if actor.role != "owner" and row["role"] != "member":
        raise HTTPException(403, "only the owner can change an admin")
    return row


class NewUser(BaseModel):
    email: str
    role: str = "member"


class Change(BaseModel):
    role: str | None = None
    active: bool | None = None


@router.get("")
def list_users():
    return users.list_all()


@router.post("", status_code=201)
def add_user(body: NewUser, actor: User = Depends(require_admin)):
    email = users.normalise(body.email)
    if not _allowed(email):
        raise HTTPException(400, f"only {_domain_list()} addresses can be added")
    _check_role(actor, body.role)
    row = users.add(email, body.role, actor.email)
    if row is None:
        raise HTTPException(409, f"{email} is already on the user list")
    return row


@router.patch("/{email}")
def change_user(email: str, body: Change, actor: User = Depends(require_admin)):
    _target(actor, email)
    if body.role is not None:
        _check_role(actor, body.role)
    return users.update(email, role=body.role, active=body.active)


@router.delete("/{email}", status_code=204)
def remove_user(email: str, actor: User = Depends(require_admin)):
    _target(actor, email)
    users.remove(email)
