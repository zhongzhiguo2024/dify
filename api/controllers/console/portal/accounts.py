"""Portal 内部账号创建端点 — 独立于 Dify 原生控制器，避免上游合并冲突。

POST /console/api/portal/accounts
  Headers: X-Portal-API-Key: <shared-secret>
  Body:   { "email": "...", "password": "<base64>", "name": "..." }

行为：
  1. 校验 X-Portal-API-Key（共享密钥）
  2. Base64 解码密码（Dify 前端编码约定）
  3. 调用 AccountService.create_account(is_setup=True) 创建账号
  4. 调用 TenantService.create_owner_tenant_if_not_exist(is_setup=True) 创建默认 Workspace
  5. 返回 { id, email, name, tenant_id }

注意：
  - is_setup=True 用于绕过 SELF_HOSTED 模式的注册/创建工作空间限制。
    本端点仅由 Portal 内部调用，已通过 API Key 认证，不属于公开注册。
"""

import base64
import logging
import os

from flask import request
from pydantic import BaseModel, Field
from werkzeug.exceptions import Forbidden

from controllers.fastopenapi import console_router
from extensions.ext_database import db
from libs.helper import EmailStr
from services.account_service import AccountService, TenantService

logger = logging.getLogger(__name__)

# ── 共享密钥（Portal 侧通过 PORTAL_DIFY_PORTAL_API_KEY 配置）──
PORTAL_API_KEY = os.getenv("PORTAL_API_KEY", "")


def _check_portal_api_key() -> None:
    """校验 X-Portal-API-Key 请求头"""
    if not PORTAL_API_KEY:
        logger.error("PORTAL_API_KEY not configured on Dify side")
        raise Forbidden("Portal API key not configured")

    provided = request.headers.get("X-Portal-API-Key", "")
    if not provided or provided != PORTAL_API_KEY:
        raise Forbidden("Invalid portal API key")


# ── Schema ──


class PortalCreateAccountPayload(BaseModel):
    email: EmailStr = Field(..., description="账号邮箱")
    password: str = Field(..., description="密码（Base64 编码）")
    name: str = Field(..., max_length=30, description="显示名称")


class PortalCreateAccountResponse(BaseModel):
    id: str = Field(..., description="账号 UUID")
    email: str = Field(..., description="账号邮箱")
    name: str = Field(..., description="显示名称")
    tenant_id: str = Field(..., description="默认 Workspace UUID")


# ── 端点 ──


@console_router.post(
    "/portal/accounts",
    response_model=PortalCreateAccountResponse,
    tags=["portal"],
    status_code=201,
)
def create_portal_account(payload: PortalCreateAccountPayload) -> PortalCreateAccountResponse:
    """Portal 内部调用：创建 Dify 账号 + 默认 Workspace。

    调用方：Portal TenantService.create()
    认证方式：X-Portal-API-Key 共享密钥
    """
    _check_portal_api_key()

    # Base64 解码密码（匹配 Dify 前端编码约定）
    try:
        password_plain = base64.b64decode(payload.password).decode("utf-8")
    except Exception:
        raise ValueError("password must be valid Base64")

    normalized_email = payload.email.lower()

    # 检查重复
    from models.account import Account
    existing = db.session.query(Account).filter(Account.email == normalized_email).first()
    if existing:
        raise ValueError(f"Account with email '{normalized_email}' already exists")

    session = db.session()

    # 创建账号（is_setup=True 绕过 SELF_HOSTED 注册限制）
    account = AccountService.create_account(
        email=normalized_email,
        name=payload.name,
        interface_language="zh-Hans",
        password=password_plain,
        is_setup=True,
        session=session,
    )

    # 创建默认 Workspace（is_setup=True 绕过创建工作空间限制）
    TenantService.create_owner_tenant_if_not_exist(
        account=account, is_setup=True, session=session,
    )

    tenants = TenantService.get_join_tenants(account, session=session)
    default_tenant_id = str(tenants[0].id) if tenants else ""

    logger.info(
        "Portal created Dify account: email=%s id=%s tenant=%s",
        normalized_email, account.id, default_tenant_id,
    )

    return PortalCreateAccountResponse(
        id=str(account.id),
        email=normalized_email,
        name=payload.name,
        tenant_id=default_tenant_id,
    )
