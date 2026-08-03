from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import ClientDisconnect

from bot.plugins.doupo_game.api_models import (
    ActionRunPayload,
    AdminActionPayload,
    AdminBootstrapPayload,
    AdminGameAccountStatePayload,
    AdminItemDefinitionPayload,
    AdminItemGrantPayload,
    AdminItemRollbackPayload,
    AdminSettingsPayload,
    ExchangePayload,
    ExpeditionChoicePayload,
    ExpeditionStartPayload,
    InitDataPayload,
    InventoryEquipmentPayload,
    PlayerResourceGrantPayload,
    SectJoinPayload,
    SectLeavePayload,
    SectQuestClaimPayload,
    SectTransferPayload,
    WebAuthBindTelegramPayload,
    WebAuthLoginPayload,
    WebAuthRegisterPayload,
    WebAuthSessionPayload,
)
from bot.plugins.doupo_game.shared.request_helpers import (
    extract_init_data_from_body_bytes as _extract_init_data_from_body_bytes,
    verify_admin_from_credential as _verify_admin_credential,
    verify_user_from_auth as _verify_user_from_auth,
    verify_user_from_init_data as _verify_user_from_init_data,
)
from bot.plugins.doupo_game.features.miniapp_bundle import (
    build_action_result_bundle,
    build_exchange_result_bundle,
    build_user_bootstrap_bundle,
)
from bot.sql_helper.sql_doupo import (
    admin_bootstrap_payload,
    admin_get_player_bundle,
    admin_archive_item_definition,
    admin_grant_item,
    admin_grant_resource,
    admin_rollback_item_definition,
    admin_reset_all_player_data,
    admin_upsert_action,
    admin_upsert_item_definition,
    build_duel_standings,
    claim_sect_quest,
    exchange_currency,
    equip_inventory_item,
    choose_expedition_event,
    get_sect_panel,
    join_sect,
    leave_sect,
    list_duel_history,
    list_item_definition_versions,
    list_sect_members,
    retreat_expedition,
    run_action,
    set_settings,
    start_expedition,
    transfer_sect,
    unequip_inventory_item,
)
from bot.sql_helper.sql_xiuxian.web_auth import (
    WebAuthRateLimitError,
    authenticate_xiuxian_web_session,
    bind_xiuxian_web_account_to_telegram,
    login_xiuxian_web_account,
    logout_xiuxian_web_session,
    list_xiuxian_web_accounts,
    register_xiuxian_web_account,
    revoke_xiuxian_web_account_sessions,
    set_xiuxian_web_account_enabled,
    unbind_xiuxian_web_account,
)

PLUGIN_ROOT = Path(__file__).resolve().parent
STATIC_DIR = PLUGIN_ROOT / "static"
PLUGIN_MANIFEST = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
PLUGIN_VERSION = str(PLUGIN_MANIFEST.get("version") or "0.1.0")
STATIC_ASSET_PATTERN = re.compile(r'(/plugins/doupo/static/([A-Za-z0-9_.-]+\.(?:css|js)))')


def register_web(app) -> None:
    user_router = APIRouter(prefix="/plugins/doupo", tags=["doupo-user"])
    admin_router = APIRouter(prefix="/plugins/doupo/admin-api", tags=["doupo-admin"])

    if STATIC_DIR.exists():
        app.mount("/plugins/doupo/static", StaticFiles(directory=STATIC_DIR), name="doupo-static")

    if not getattr(app.state, "doupo_request_context_middleware", False):
        @app.middleware("http")
        async def doupo_request_context_middleware(request: Request, call_next):
            path = str(request.url.path or "")
            if path.startswith("/plugins/doupo"):
                init_data = request.headers.get("x-telegram-init-data")
                if not init_data:
                    try:
                        body = await request.body()
                    except ClientDisconnect:
                        return JSONResponse(status_code=499, content={"code": 499, "message": "客户端已断开连接。"})
                    init_data = _extract_init_data_from_body_bytes(request.headers.get("content-type", ""), body)

                    async def receive():
                        return {"type": "http.request", "body": body, "more_body": False}

                    request = Request(request.scope, receive)
                request.state.doupo_init_data = init_data
            return await call_next(request)

        app.state.doupo_request_context_middleware = True

    def render_versioned_static_page(filename: str) -> HTMLResponse:
        html_path = STATIC_DIR / filename
        content = html_path.read_text(encoding="utf-8")

        def replace_asset(match: re.Match[str]) -> str:
            asset_url = match.group(1)
            asset_name = match.group(2)
            asset_path = STATIC_DIR / asset_name
            try:
                asset_version = f"{PLUGIN_VERSION}-{int(asset_path.stat().st_mtime)}"
            except OSError:
                asset_version = PLUGIN_VERSION
            return f"{asset_url}?v={asset_version}"

        rendered = STATIC_ASSET_PATTERN.sub(replace_asset, content)
        return HTMLResponse(
            rendered,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @user_router.get("/", include_in_schema=False)
    def doupo_root_page():
        return RedirectResponse(url="/plugins/doupo/app", status_code=302)

    @user_router.get("/app")
    def doupo_app_page():
        return render_versioned_static_page("app.html")

    @user_router.get("/admin")
    def doupo_admin_page():
        return render_versioned_static_page("admin.html")

    def _web_session_token_from_payload(payload: WebAuthSessionPayload | InitDataPayload | None) -> str:
        token = str(getattr(payload, "session_token", "") or "").strip()
        if token:
            return token
        init_data = str(getattr(payload, "init_data", "") or "").strip()
        if init_data.startswith("web_session:"):
            return init_data.removeprefix("web_session:").strip()
        return ""

    def _verify_telegram_bind_user(init_data: str) -> dict:
        raw = str(init_data or "").strip()
        if not raw:
            raise HTTPException(status_code=400, detail="缺少 Telegram 绑定凭证")
        if raw.startswith("web_session:"):
            raise HTTPException(status_code=400, detail="绑定 Telegram 需要从 Telegram 内打开一次")
        return _verify_user_from_init_data(raw)

    def _auto_bind_web_auth_result(result: dict, telegram_user: dict | None) -> dict:
        if not telegram_user:
            return result
        account = bind_xiuxian_web_account_to_telegram(str(result.get("session_token") or ""), telegram_user)
        patched = dict(result)
        patched["account"] = account
        patched["telegram_user"] = telegram_user
        return patched

    @user_router.post("/api/auth/register")
    async def doupo_web_auth_register(payload: WebAuthRegisterPayload):
        def _run():
            telegram_user = _verify_telegram_bind_user(payload.init_data) if str(payload.init_data or "").strip() else None
            result = register_xiuxian_web_account(
                payload.username,
                payload.password,
                display_name=payload.display_name,
            )
            return _auto_bind_web_auth_result(result, telegram_user)

        try:
            return {"code": 200, "data": await run_in_threadpool(_run)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @user_router.post("/api/auth/login")
    async def doupo_web_auth_login(payload: WebAuthLoginPayload):
        def _run():
            telegram_user = _verify_telegram_bind_user(payload.init_data) if str(payload.init_data or "").strip() else None
            result = login_xiuxian_web_account(payload.username, payload.password)
            return _auto_bind_web_auth_result(result, telegram_user)

        try:
            return {"code": 200, "data": await run_in_threadpool(_run)}
        except WebAuthRateLimitError as exc:
            raise HTTPException(
                status_code=429,
                detail=str(exc),
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @user_router.post("/api/auth/me")
    async def doupo_web_auth_me(payload: WebAuthSessionPayload):
        token = _web_session_token_from_payload(payload)
        if not token:
            return {"code": 200, "data": {"account": None}}
        try:
            account = await run_in_threadpool(authenticate_xiuxian_web_session, token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return {"code": 200, "data": {"account": account}}

    @user_router.post("/api/auth/bind-telegram")
    async def doupo_web_auth_bind_telegram(payload: WebAuthBindTelegramPayload):
        token = _web_session_token_from_payload(payload)
        if not token:
            raise HTTPException(status_code=401, detail="请先登录网页账号")
        try:
            telegram_user = await run_in_threadpool(_verify_telegram_bind_user, payload.init_data)
            account = await run_in_threadpool(bind_xiuxian_web_account_to_telegram, token, telegram_user)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"code": 200, "data": {"account": account, "telegram_user": telegram_user}}

    @user_router.post("/api/auth/logout")
    async def doupo_web_auth_logout(payload: WebAuthSessionPayload):
        token = _web_session_token_from_payload(payload)
        ok = await run_in_threadpool(logout_xiuxian_web_session, token)
        return {"code": 200, "data": {"ok": ok}}

    @user_router.post("/api/bootstrap")
    async def doupo_bootstrap(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        bundle = await run_in_threadpool(build_user_bootstrap_bundle, int(telegram_user["id"]))
        return {
            "code": 200,
            "data": {
                "telegram_user": telegram_user,
                **bundle,
            },
        }

    @user_router.post("/api/action/run")
    async def doupo_action_run(payload: ActionRunPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(run_action, int(telegram_user["id"]), payload.action_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        bundle = await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)
        return {
            "code": 200,
            "data": bundle,
        }

    @user_router.post("/api/inventory/equip")
    async def doupo_inventory_equip(payload: InventoryEquipmentPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(equip_inventory_item, int(telegram_user["id"]), payload.item_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/inventory/unequip")
    async def doupo_inventory_unequip(payload: InventoryEquipmentPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(unequip_inventory_item, int(telegram_user["id"]), payload.item_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/exchange")
    async def doupo_exchange(payload: ExchangePayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(exchange_currency, int(telegram_user["id"]), payload.direction, payload.amount)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        bundle = await run_in_threadpool(build_exchange_result_bundle, int(telegram_user["id"]), result)
        return {
            "code": 200,
            "data": bundle,
        }

    @user_router.post("/api/expedition/start")
    async def doupo_expedition_start(payload: ExpeditionStartPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(start_expedition, int(telegram_user["id"]), payload.region_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/expedition/choose")
    async def doupo_expedition_choose(payload: ExpeditionChoicePayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(
                choose_expedition_event,
                int(telegram_user["id"]),
                payload.choice_key,
                payload.focus_score,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/expedition/retreat")
    async def doupo_expedition_retreat(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(retreat_expedition, int(telegram_user["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/sect/join")
    async def doupo_sect_join(payload: SectJoinPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(join_sect, int(telegram_user["id"]), payload.sect_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        bundle = await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)
        return {
            "code": 200,
            "data": bundle,
        }

    @user_router.post("/api/sect/transfer")
    async def doupo_sect_transfer(payload: SectTransferPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(transfer_sect, int(telegram_user["id"]), payload.sect_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/sect/leave")
    async def doupo_sect_leave(payload: SectLeavePayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(leave_sect, int(telegram_user["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/sect/quest/claim")
    async def doupo_sect_quest_claim(payload: SectQuestClaimPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(claim_sect_quest, int(telegram_user["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/sect/members")
    async def doupo_sect_members(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        panel = await run_in_threadpool(get_sect_panel, int(telegram_user["id"]))
        return {"code": 200, "data": panel}

    @user_router.post("/api/duel/history")
    async def doupo_duel_history(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        return {"code": 200, "data": await run_in_threadpool(list_duel_history, int(telegram_user["id"]), 20)}

    @user_router.post("/api/duel/standings")
    async def doupo_duel_standings(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        return {"code": 200, "data": await run_in_threadpool(build_duel_standings, int(telegram_user["id"]))}

    @admin_router.post("/bootstrap")
    async def doupo_admin_bootstrap(payload: AdminBootstrapPayload):
        await run_in_threadpool(_verify_admin_credential, payload.token, payload.init_data)
        data = await run_in_threadpool(
            admin_bootstrap_payload,
            payload.player_query,
            payload.player_page,
            payload.player_page_size,
        )
        data["game_accounts"] = await run_in_threadpool(list_xiuxian_web_accounts, page=1, page_size=10)
        return {"code": 200, "data": data}

    @admin_router.get("/accounts")
    async def doupo_admin_accounts(
        request: Request,
        q: str = "",
        bound: str = "",
        enabled: str = "",
        page: int = 1,
        page_size: int = 20,
    ):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        parse_filter = lambda value: None if not str(value or "").strip() else str(value).strip().lower() in {"1", "true", "yes", "on", "bound", "enabled"}
        data = await run_in_threadpool(
            list_xiuxian_web_accounts,
            q,
            bound=parse_filter(bound),
            enabled=parse_filter(enabled),
            page=page,
            page_size=page_size,
        )
        return {"code": 200, "data": data}

    @admin_router.post("/accounts/{account_id}/state")
    async def doupo_admin_account_state(account_id: int, payload: AdminGameAccountStatePayload, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            account = await run_in_threadpool(set_xiuxian_web_account_enabled, account_id, payload.enabled)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"code": 200, "data": {"account": account}}

    @admin_router.post("/accounts/{account_id}/unbind")
    async def doupo_admin_account_unbind(account_id: int, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            account = await run_in_threadpool(unbind_xiuxian_web_account, account_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"code": 200, "data": {"account": account}}

    @admin_router.post("/accounts/{account_id}/sessions/revoke")
    async def doupo_admin_account_revoke_sessions(account_id: int, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            count = await run_in_threadpool(revoke_xiuxian_web_account_sessions, account_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"code": 200, "data": {"revoked_sessions": count}}

    @admin_router.post("/settings")
    async def doupo_admin_settings(payload: AdminSettingsPayload, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        patch = {key: value for key, value in payload.model_dump().items() if value is not None}
        return {"code": 200, "data": await run_in_threadpool(set_settings, patch)}

    @admin_router.post("/actions")
    async def doupo_admin_upsert_action(payload: AdminActionPayload, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            data = await run_in_threadpool(
                admin_upsert_action,
                payload.action_key,
                name=payload.name,
                description=payload.description,
                action_type=payload.action_type,
                cooldown_seconds=payload.cooldown_seconds,
                reward_config=payload.reward_config,
                requirement_config=payload.requirement_config,
                enabled=payload.enabled,
                sort_order=payload.sort_order,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    @admin_router.post("/items")
    async def doupo_admin_upsert_item(payload: AdminItemDefinitionPayload, request: Request):
        admin = await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            data = await run_in_threadpool(
                admin_upsert_item_definition,
                payload.item_key,
                name=payload.name,
                category=payload.category,
                rarity=payload.rarity,
                description=payload.description,
                icon=payload.icon,
                tradable=payload.tradable,
                stack_limit=payload.stack_limit,
                equipment_slot=payload.equipment_slot,
                attack=payload.attack,
                defense=payload.defense,
                agility=payload.agility,
                fire_bonus=payload.fire_bonus,
                alchemy_bonus=payload.alchemy_bonus,
                recipe_config=payload.recipe_config,
                drop_sources=payload.drop_sources,
                enabled=payload.enabled,
                change_note=payload.change_note,
                created_by=int(admin.get("id") or 0) or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    @admin_router.get("/items/{item_key}/versions")
    async def doupo_admin_item_versions(item_key: str, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        return {"code": 200, "data": {"items": await run_in_threadpool(list_item_definition_versions, item_key)}}

    @admin_router.post("/items/{item_key}/rollback")
    async def doupo_admin_item_rollback(item_key: str, payload: AdminItemRollbackPayload, request: Request):
        admin = await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            data = await run_in_threadpool(
                admin_rollback_item_definition,
                item_key,
                payload.version,
                created_by=int(admin.get("id") or 0) or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    @admin_router.post("/items/{item_key}/archive")
    async def doupo_admin_item_archive(item_key: str, request: Request):
        admin = await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            data = await run_in_threadpool(
                admin_archive_item_definition,
                item_key,
                created_by=int(admin.get("id") or 0) or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    @admin_router.get("/players/{tg}")
    async def doupo_admin_player_detail(tg: int, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        return {"code": 200, "data": await run_in_threadpool(admin_get_player_bundle, tg)}

    @admin_router.post("/players/{tg}/resource/grant")
    async def doupo_admin_grant_resource(tg: int, payload: PlayerResourceGrantPayload, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            data = await run_in_threadpool(admin_grant_resource, tg, payload.resource, payload.amount)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    @admin_router.post("/players/{tg}/items/grant")
    async def doupo_admin_grant_player_item(tg: int, payload: AdminItemGrantPayload, request: Request):
        admin = await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            data = await run_in_threadpool(
                admin_grant_item,
                tg,
                payload.item_key,
                payload.quantity,
                created_by=int(admin.get("id") or 0) or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    @admin_router.post("/system/reset-player-data")
    async def doupo_admin_reset_player_data(request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        return {"code": 200, "data": await run_in_threadpool(admin_reset_all_player_data)}

    app.include_router(user_router)
    app.include_router(admin_router)
