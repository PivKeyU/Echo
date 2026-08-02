from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import ClientDisconnect

from bot.plugins.douluo_game.api_models import (
    AdminBootstrapPayload,
    AdminGameAccountStatePayload,
    AdminItemDefinitionPayload,
    AdminItemGrantPayload,
    AdminItemTogglePayload,
    AdminProfilePatchPayload,
    AdminSettingsPayload,
    AuctionBidPayload,
    AuctionListPayload,
    BossChallengePayload,
    DailyTaskClaimPayload,
    ExchangePayload,
    HuntPayload,
    InitDataPayload,
    InventoryEquipmentPayload,
    RankPayload,
    SectJoinPayload,
    WebAuthBindTelegramPayload,
    WebAuthLoginPayload,
    WebAuthRegisterPayload,
    WebAuthSessionPayload,
)
from bot.plugins.douluo_game.shared.request_helpers import (
    extract_init_data_from_body_bytes as _extract_init_data_from_body_bytes,
    verify_admin_from_credential as _verify_admin_credential,
    verify_user_from_auth as _verify_user_from_auth,
    verify_user_from_init_data as _verify_user_from_init_data,
)
from bot.plugins.douluo_game.features.miniapp_bundle import (
    build_action_result_bundle,
    build_exchange_result_bundle,
    build_user_bootstrap_bundle,
)
from bot.plugins.douluo_game.plugin_bot_handlers import (
    _push_result_broadcast_to_groups,
)
from bot.sql_helper.sql_douluo import (
    admin_get_overview,
    admin_grant_item,
    admin_list_players,
    admin_reset_profile,
    admin_set_profile,
    admin_toggle_item_definition,
    admin_update_settings,
    admin_upsert_item_definition,
    awaken_wuhun,
    breakthrough,
    build_douluo_leaderboard,
    challenge_boss,
    claim_daily_task,
    claim_salary,
    equip_inventory_item,
    exchange_currency,
    get_settings,
    hunt_soul_beast,
    join_sect,
    list_auction_listings,
    list_item_definitions,
    list_recent_journals,
    my_listings,
    place_auction_bid,
    place_auction_listing,
    reforge_wuhun,
    settle_expired_auctions,
    train_soul_power,
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
STATIC_ASSET_PATTERN = re.compile(r'(/plugins/douluo/static/([A-Za-z0-9_.-]+\.(?:css|js)))')


def register_web(app) -> None:
    user_router = APIRouter(prefix="/plugins/douluo", tags=["douluo-user"])
    admin_router = APIRouter(prefix="/plugins/douluo/admin-api", tags=["douluo-admin"])

    if STATIC_DIR.exists():
        app.mount("/plugins/douluo/static", StaticFiles(directory=STATIC_DIR), name="douluo-static")

    if not getattr(app.state, "douluo_request_context_middleware", False):
        @app.middleware("http")
        async def douluo_request_context_middleware(request: Request, call_next):
            path = str(request.url.path or "")
            if path.startswith("/plugins/douluo"):
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
                request.state.douluo_init_data = init_data
            return await call_next(request)

        app.state.douluo_request_context_middleware = True

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
    def douluo_root_page():
        return RedirectResponse(url="/plugins/douluo/app", status_code=302)

    @user_router.get("/app")
    def douluo_app_page():
        return render_versioned_static_page("app.html")

    @user_router.get("/admin")
    def douluo_admin_page():
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
    async def douluo_web_auth_register(payload: WebAuthRegisterPayload):
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
    async def douluo_web_auth_login(payload: WebAuthLoginPayload):
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
    async def douluo_web_auth_me(payload: WebAuthSessionPayload):
        token = _web_session_token_from_payload(payload)
        if not token:
            return {"code": 200, "data": {"account": None}}
        try:
            account = await run_in_threadpool(authenticate_xiuxian_web_session, token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return {"code": 200, "data": {"account": account}}

    @user_router.post("/api/auth/bind-telegram")
    async def douluo_web_auth_bind_telegram(payload: WebAuthBindTelegramPayload):
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
    async def douluo_web_auth_logout(payload: WebAuthSessionPayload):
        token = _web_session_token_from_payload(payload)
        ok = await run_in_threadpool(logout_xiuxian_web_session, token)
        return {"code": 200, "data": {"ok": ok}}

    @user_router.post("/api/bootstrap")
    async def douluo_bootstrap(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        bundle = await run_in_threadpool(build_user_bootstrap_bundle, int(telegram_user["id"]))
        return {
            "code": 200,
            "data": {
                "telegram_user": telegram_user,
                **bundle,
            },
        }

    @user_router.post("/api/train")
    async def douluo_train(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(train_soul_power, int(telegram_user["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/hunt")
    async def douluo_hunt(payload: HuntPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(hunt_soul_beast, int(telegram_user["id"]), payload.region_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _push_result_broadcast_to_groups(result)
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/breakthrough")
    async def douluo_breakthrough(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(breakthrough, int(telegram_user["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _push_result_broadcast_to_groups(result)
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/wuhun/awaken")
    async def douluo_wuhun_awaken(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(awaken_wuhun, int(telegram_user["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/wuhun/reforge")
    async def douluo_wuhun_reforge(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(reforge_wuhun, int(telegram_user["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/inventory/equip")
    async def douluo_inventory_equip(payload: InventoryEquipmentPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(equip_inventory_item, int(telegram_user["id"]), payload.item_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/inventory/unequip")
    async def douluo_inventory_unequip(payload: InventoryEquipmentPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(unequip_inventory_item, int(telegram_user["id"]), payload.slot)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/exchange")
    async def douluo_exchange(payload: ExchangePayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(
                exchange_currency, int(telegram_user["id"]), payload.direction, payload.amount
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_exchange_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/tasks/claim")
    async def douluo_task_claim(payload: DailyTaskClaimPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(claim_daily_task, int(telegram_user["id"]), payload.task_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/sect/join")
    async def douluo_sect_join(payload: SectJoinPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(join_sect, int(telegram_user["id"]), payload.sect_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/sect/salary")
    async def douluo_sect_salary(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(claim_salary, int(telegram_user["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/auction/listings")
    async def douluo_auction_listings(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        items = await run_in_threadpool(list_auction_listings, int(telegram_user["id"]), status="open")
        return {"code": 200, "data": {"listings": items}}

    @user_router.post("/api/auction/place")
    async def douluo_auction_place(payload: AuctionListPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(
                place_auction_listing, int(telegram_user["id"]), payload.item_key, payload.price, payload.duration_hours
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/auction/bid")
    async def douluo_auction_bid(payload: AuctionBidPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(place_auction_bid, int(telegram_user["id"]), payload.listing_id, payload.price)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/auction/my")
    async def douluo_auction_my(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        await run_in_threadpool(settle_expired_auctions)
        items = await run_in_threadpool(my_listings, int(telegram_user["id"]))
        return {"code": 200, "data": {"listings": items}}

    @user_router.post("/api/boss/challenge")
    async def douluo_boss_challenge(payload: BossChallengePayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        try:
            result = await run_in_threadpool(challenge_boss, int(telegram_user["id"]), payload.boss_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _push_result_broadcast_to_groups(result)
        return {"code": 200, "data": await run_in_threadpool(build_action_result_bundle, int(telegram_user["id"]), result)}

    @user_router.post("/api/rank")
    async def douluo_rank(payload: RankPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        data = await run_in_threadpool(build_douluo_leaderboard, payload.kind, 10)
        return {"code": 200, "data": data}

    @user_router.post("/api/journals")
    async def douluo_journals(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_auth, payload.init_data, payload.session_token)
        data = await run_in_threadpool(list_recent_journals, int(telegram_user["id"]), 20)
        return {"code": 200, "data": {"items": data}}

    @admin_router.post("/bootstrap")
    async def douluo_admin_bootstrap(payload: AdminBootstrapPayload):
        await run_in_threadpool(_verify_admin_credential, payload.token, payload.init_data)
        players = await run_in_threadpool(
            admin_list_players, payload.player_page_size, (payload.player_page - 1) * payload.player_page_size
        )
        data = {
            "overview": await run_in_threadpool(admin_get_overview),
            "players": players,
            "settings": await run_in_threadpool(get_settings),
            "item_definitions": await run_in_threadpool(list_item_definitions, include_disabled=True),
            "game_accounts": await run_in_threadpool(list_xiuxian_web_accounts, page=1, page_size=10),
        }
        return {"code": 200, "data": data}

    @admin_router.get("/accounts")
    async def douluo_admin_accounts(
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
    async def douluo_admin_account_state(account_id: int, payload: AdminGameAccountStatePayload, request: Request):
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
    async def douluo_admin_account_unbind(account_id: int, request: Request):
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
    async def douluo_admin_account_revoke_sessions(account_id: int, request: Request):
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
    async def douluo_admin_settings(payload: AdminSettingsPayload, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        patch = {key: value for key, value in payload.model_dump().items() if value is not None}
        return {"code": 200, "data": await run_in_threadpool(admin_update_settings, patch)}

    @admin_router.post("/items")
    async def douluo_admin_upsert_item(payload: AdminItemDefinitionPayload, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            data = await run_in_threadpool(admin_upsert_item_definition, payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    @admin_router.post("/items/{item_key}/toggle")
    async def douluo_admin_toggle_item(item_key: str, payload: AdminItemTogglePayload, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            data = await run_in_threadpool(admin_toggle_item_definition, item_key, payload.enabled)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    @admin_router.post("/players/{tg}/patch")
    async def douluo_admin_patch_player(tg: int, payload: AdminProfilePatchPayload, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        patch = {key: value for key, value in payload.model_dump().items() if value is not None}
        try:
            data = await run_in_threadpool(admin_set_profile, tg, patch)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    @admin_router.post("/players/{tg}/items/grant")
    async def douluo_admin_grant_player_item(tg: int, payload: AdminItemGrantPayload, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            data = await run_in_threadpool(admin_grant_item, tg, payload.item_key, payload.quantity)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    @admin_router.post("/players/{tg}/reset")
    async def douluo_admin_reset_player(tg: int, request: Request):
        await run_in_threadpool(
            _verify_admin_credential,
            request.headers.get("x-admin-token"),
            request.headers.get("x-telegram-init-data"),
        )
        try:
            data = await run_in_threadpool(admin_reset_profile, tg)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    app.include_router(user_router)
    app.include_router(admin_router)
