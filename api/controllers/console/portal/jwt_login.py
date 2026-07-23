"""Portal JWT 控制台登录 — Dify 后端端点（REQ-DIFY-007）

POST /console/api/portal/jwt-login
  Headers: X-Portal-API-Key: <shared-secret>
  Body:   { "token": "<RS256 JWT issued by Portal>" }

行为：
  1. 校验 X-Portal-API-Key（共享密钥）
  2. 用 Portal 公钥验签 JWT（RS256, aud=dify-console, TTL≤60s）
  3. 从 claims 取 email，查 Account 表
  4. 调用 AccountService.login() 获取 token triplet
  5. 设置 3 个 Cookie（access_token, refresh_token, csrf_token）
  6. 返回 200

注意：
  - 本端点仅由 Dify 前端 /auth/jwt Route Handler 调用
  - 不创建新账号 — 账号已在 REQ-DIFY-006 创建租户时同步
  - 隔离策略：位于 controllers/console/portal/ 独立包中
  - 使用 console_ns (flask-restx) 而非 console_router，因为需要返回带 Cookie 的 Flask Response
"""

import logging
import os

import jwt as pyjwt
from flask import make_response, request
from flask_restx import Resource
from pydantic import BaseModel, Field
from werkzeug.exceptions import Forbidden, Unauthorized

from controllers.common.fields import SimpleResultResponse
from controllers.console import console_ns
from extensions.ext_database import db
from libs.helper import extract_remote_ip
from libs.token import (
    set_access_token_to_cookie,
    set_csrf_token_to_cookie,
    set_refresh_token_to_cookie,
)
from models.account import Account
from services.account_service import AccountService

logger = logging.getLogger(__name__)

# ── 共享密钥（Portal 侧通过 PORTAL_DIFY_PORTAL_API_KEY 配置）──
PORTAL_API_KEY = os.getenv("PORTAL_API_KEY", "")

# ── 公钥路径 — 由环境变量配置，Dify docker-compose 挂载 ──
_PORTAL_PUBLIC_KEY_PATH = os.getenv("PORTAL_JWT_PUBLIC_KEY_PATH", "/etc/dify/portal-public.pem")
_portal_public_key_pem: str | None = None


def _get_portal_public_key() -> str:
    """懒加载 Portal 公钥（缓存到模块变量）"""
    global _portal_public_key_pem
    if _portal_public_key_pem is None:
        with open(_PORTAL_PUBLIC_KEY_PATH, "r") as f:
            _portal_public_key_pem = f.read()
    return _portal_public_key_pem


def _check_portal_api_key() -> None:
    """校验 X-Portal-API-Key 请求头"""
    if not PORTAL_API_KEY:
        logger.error("PORTAL_API_KEY not configured on Dify side")
        raise Forbidden("Portal API key not configured")

    provided = request.headers.get("X-Portal-API-Key", "")
    if not provided or provided != PORTAL_API_KEY:
        raise Forbidden("Invalid portal API key")


# ── Schema ──


class JwtLoginPayload(BaseModel):
    token: str = Field(..., description="Portal 签发的 console 免登 JWT (RS256)")


# ── 端点 ──


@console_ns.route("/portal/jwt-login")
class PortalJwtLoginApi(Resource):
    """Portal 控制台免登：验签 JWT → 查 Account → 设 Cookie。"""

    @console_ns.response(200, "Success", console_ns.models[SimpleResultResponse.__name__])
    def post(self):
        """验签 Portal 控制台 JWT 并登录。

        调用方：Dify 前端 /auth/jwt Route Handler（服务端代理）
        认证方式：X-Portal-API-Key + JWT 双重校验
        """
        _check_portal_api_key()

        body = request.get_json(silent=True) or {}
        token = body.get("token", "")
        if not token:
            raise Unauthorized("Missing JWT token")

        # 1. 验签 JWT
        try:
            public_key_pem = _get_portal_public_key()
            claims = pyjwt.decode(
                token,
                public_key_pem,
                algorithms=["RS256"],
                audience="dify-console",
                leeway=30,
            )
        except pyjwt.InvalidAudienceError:
            logger.warning("JWT login: audience mismatch (expected dify-console)")
            raise Unauthorized("JWT audience is invalid")
        except pyjwt.ExpiredSignatureError:
            logger.warning("JWT login: token expired")
            raise Unauthorized("JWT token has expired")
        except pyjwt.InvalidTokenError as e:
            logger.warning("JWT login: invalid token — %s", e)
            raise Unauthorized(f"JWT token is invalid: {e}")
        except FileNotFoundError:
            logger.error("JWT login: Portal public key not found at %s", _PORTAL_PUBLIC_KEY_PATH)
            raise Unauthorized("JWT verification is not configured")

        # 2. TTL 上限校验（≤ 60s）
        ttl = int(claims.get("exp", 0)) - int(claims.get("iat", 0))
        if ttl > 60:
            logger.warning("JWT login: TTL %ds exceeds 60s limit", ttl)
            raise Unauthorized("JWT TTL exceeds 60s limit")

        # 3. 提取 email，查 Account
        email = claims.get("email")
        if not email:
            raise Unauthorized("JWT missing required claim: email")

        account = AccountService.get_user_through_email(email, session=db.session())
        if account is None:
            logger.warning("JWT login: account not found for email=%s", email)
            raise Unauthorized(f"No account found for email: {email}")

        # 4. 登录并获取 token triplet
        session = db.session()
        token_pair = AccountService.login(
            account=account,
            session=session,
            ip_address=extract_remote_ip(request),
        )

        # 5. 设置 Cookie 并返回（与 login.py 返回格式一致）
        # response-contract:ignore cookie-bearing Flask response
        response = make_response(
            SimpleResultResponse(result="success").model_dump(mode="json")
        )
        set_access_token_to_cookie(request, response, token_pair.access_token)
        set_refresh_token_to_cookie(request, response, token_pair.refresh_token)
        set_csrf_token_to_cookie(request, response, token_pair.csrf_token)

        logger.info(
            "JWT login: account=%s email=%s ip=%s",
            account.id, email, extract_remote_ip(request),
        )

        return response
