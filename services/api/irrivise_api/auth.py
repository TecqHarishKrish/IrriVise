"""Supabase-backed identity and feature authorization.

The browser supplies a Supabase access token.  This module verifies that token
against Supabase's `/auth/v1/user` endpoint, so a client-provided email is
never trusted as proof of identity.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import Depends, Header, HTTPException

from irrivise_api.storage import connect, many, now, one

PRIMARY_ADMIN_EMAIL = os.getenv("IRRIVISE_PRIMARY_ADMIN_EMAIL", "").strip().lower()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

FEATURES = (
    "projects", "weather", "digital_twin", "simulation", "training",
    "carat", "analytics", "reports", "analyst",
)


@dataclass(frozen=True)
class Actor:
    id: str
    email: str
    role: str


def configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY and PRIMARY_ADMIN_EMAIL)


def configuration_status() -> dict:
    return {
        "provider": "supabase",
        "configured": configured(),
        "primary_admin_email": PRIMARY_ADMIN_EMAIL,
        "features": list(FEATURES),
    }


def _verify_token(token: str) -> dict:
    if not configured():
        raise HTTPException(503, "Authentication is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY on the API server.")
    request = Request(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
    )
    try:
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        raise HTTPException(401, "Your login session is invalid or has expired. Please sign in again.")


def current_actor(authorization: str | None = Header(default=None)) -> Actor:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in is required.")
    claims = _verify_token(authorization.removeprefix("Bearer ").strip())
    user_id, email = claims.get("id"), str(claims.get("email", "")).strip().lower()
    if not user_id or not email or not claims.get("email_confirmed_at"):
        raise HTTPException(403, "Verify your email address before using IrriVise.")
    with connect() as db:
        item = one(db, "SELECT * FROM accounts WHERE id=?", (user_id,))
        if not item:
            role = "admin" if email == PRIMARY_ADMIN_EMAIL else "user"
            db.execute("INSERT INTO accounts(id,email,role,created_at,last_seen_at) VALUES (?,?,?,?,?)", (user_id, email, role, now(), now()))
            item = one(db, "SELECT * FROM accounts WHERE id=?", (user_id,))
            if role == "admin":
                db.execute("UPDATE projects SET account_id=? WHERE account_id IS NULL", (user_id,))
        else:
            db.execute("UPDATE accounts SET email=?, last_seen_at=? WHERE id=?", (email, now(), user_id))
            if email == PRIMARY_ADMIN_EMAIL and item["role"] != "admin":
                db.execute("UPDATE accounts SET role='admin' WHERE id=?", (user_id,))
                item["role"] = "admin"
    return Actor(id=user_id, email=email, role=item["role"])


def effective_actor(
    actor: Actor = Depends(current_actor),
    x_irrivise_support_account: str | None = Header(default=None),
) -> Actor:
    """Allow an administrator to open a user's enabled workspace for support."""
    if not x_irrivise_support_account or x_irrivise_support_account == actor.id:
        return actor
    if actor.role != "admin":
        raise HTTPException(403, "Only administrators can enter support mode.")
    with connect() as db:
        target = one(db, "SELECT id,email,role FROM accounts WHERE id=?", (x_irrivise_support_account,))
    if not target:
        raise HTTPException(404, "Support account not found")
    return Actor(id=target["id"], email=target["email"], role=target["role"])


def require_admin(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.role != "admin":
        raise HTTPException(403, "Administrator access is required.")
    return actor


def require_primary_admin(actor: Actor = Depends(require_admin)) -> Actor:
    if actor.email != PRIMARY_ADMIN_EMAIL:
        raise HTTPException(403, "Only the primary administrator can change administrator roles.")
    return actor


def enabled_features(account_id: str, role: str) -> list[str]:
    if role == "admin":
        return list(FEATURES)
    with connect() as db:
        rows = many(db, "SELECT feature_key FROM account_features WHERE account_id=? AND enabled=1", (account_id,))
    return [row["feature_key"] for row in rows]


def require_feature(feature: str):
    def dependency(actor: Actor = Depends(effective_actor)) -> Actor:
        if actor.role == "admin" or feature in enabled_features(actor.id, actor.role):
            return actor
        raise HTTPException(403, f"Your administrator has not enabled the {feature} feature for this account.")
    return dependency
