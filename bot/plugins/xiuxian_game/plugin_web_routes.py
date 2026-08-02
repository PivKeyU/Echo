from __future__ import annotations

import asyncio
import json
import os
import re
import time
import traceback
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any, Iterable
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pyrogram import enums, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from starlette.requests import ClientDisconnect

from bot import LOGGER, admin_p, api as api_config, bot, config, group, owner, owner_p, prefixes, user_p
from bot.func_helper.moderation import (
    ModerationServiceError,
    get_chat_member_details,
    normalize_telegram_member_badge_text,
    set_chat_member_tag,
    set_chat_member_title,
)
from bot.func_helper.msg_utils import callAnswer
from bot.plugins import list_miniapp_plugins
from bot.sql_helper import Session
from bot.plugins.xiuxian_game.api_models import (
    AchievementPayload,
    AchievementProgressPayload,
    ActivateTalismanPayload,
    ActivateTechniquePayload,
    AdminBootstrapPayload,
    AdminSettingPayload,
    AdminSocialPatchPayload,
    AdminTaskPayload,
    ArtifactBindingPayload,
    ArtifactPayload,
    ArtifactSetPayload,
    BossChallengePayload,
    BossPayload,
    BossWorldSpawnPayload,
    BreakthroughPayload,
    ConsumePillPayload,
    CommissionClaimPayload,
    CraftPayload,
    EncounterDispatchPayload,
    EncounterPayload,
    EquipArtifactPayload,
    EventSummaryRefreshPayload,
    ErrorLogQueryPayload,
    ExchangePayload,
    FarmCarePayload,
    FurnaceHarvestPayload,
    GamblingExchangePayload,
    GamblingOpenPayload,
    FarmHarvestPayload,
    FarmPlantPayload,
    FarmUnlockPayload,
    FishingCastPayload,
    ExploreClaimPayload,
    ExploreStartPayload,
    GiftPayload,
    GenderSetPayload,
    GrantPayload,
    InitDataPayload,
    ItemGiftPayload,
    LeaderboardPayload,
    MarriageRequestActionPayload,
    MarriageRequestPayload,
    MaterialPayload,
    MentorshipRequestActionPayload,
    MentorshipRequestPayload,
    MentorshipTargetPayload,
    MentorshipTeachPayload,
    OfficialShopPatchPayload,
    OfficialRecycleBatchPayload,
    OfficialRecyclePayload,
    OfficialShopPayload,
    PersonalAuctionPayload,
    PersonalShopPayload,
    PillPayload,
    PlayerLookupPayload,
    PlayerInventoryPayload,
    PlayerPatchPayload,
    PlayerResourceGrantPayload,
    PlayerBatchResourcePayload,
    PlayerRevokePayload,
    PlayerSelectionPayload,
    PurchasePayload,
    RecipePayload,
    RecipeFragmentSynthesisPayload,
    RedEnvelopePayload,
    RetreatPayload,
    ScenePayload,
    SectDonatePayload,
    SectJoinPayload,
    SectPayload,
    SectRoleAssignPayload,
    SectTeachPayload,
    ShopCancelPayload,
    SocialModePayload,
    TalismanBindingPayload,
    TalismanPayload,
    TaskClaimPayload,
    TaskCancelPayload,
    TechniquePayload,
    TitleEquipPayload,
    TitleGrantPayload,
    TitleGroupSyncPayload,
    TitlePayload,
    UploadPermissionPayload,
    UserTaskPayload,
    WebAuthBindTelegramPayload,
    AdminGameAccountStatePayload,
    WebAuthLoginPayload,
    WebAuthRegisterPayload,
    WebAuthSessionPayload,
)
from bot.plugins.xiuxian_game.features.admin_ops import (
    admin_clear_all_xiuxian_data,
    admin_batch_update_player_resource,
    admin_grant_player_resource,
    admin_patch_player,
    admin_revoke_player_resource,
    admin_seed_demo_assets,
    admin_set_player_inventory,
    admin_set_player_selection,
    build_admin_player_detail,
    update_xiuxian_settings,
)
from bot.plugins.xiuxian_game.features.combat import (
    assert_duel_stake_affordable,
    build_leaderboard,
    cancel_group_arena,
    challenge_group_arena_for_user,
    compute_duel_odds,
    finalize_group_arena,
    format_duel_settlement_text,
    format_leaderboard_text,
    generate_duel_preview_text,
    get_active_group_arena,
    get_group_arena,
    list_group_arenas,
    open_group_arena_for_user,
    patch_group_arena,
    resolve_duel,
)
from bot.plugins.xiuxian_game.features.crafting import (
    build_recipe_catalog,
    craft_recipe_for_user,
    create_recipe_with_ingredients,
    patch_recipe_with_ingredients,
    synthesize_recipe_fragment_for_user,
)
from bot.plugins.xiuxian_game.features.economy import gift_inventory_item, gift_spirit_stone
from bot.plugins.xiuxian_game.features.encounters import (
    claim_group_encounter,
    create_encounter_template,
    delete_encounter_template,
    list_encounter_templates,
    mark_group_encounter_message,
    maybe_spawn_group_encounter,
    patch_encounter_template,
    render_group_encounter_success_text,
    render_group_encounter_text,
    spawn_group_encounter,
)
from bot.plugins.xiuxian_game.features.exploration import (
    _scene_requirement_state,
    claim_exploration_for_user,
    create_scene_with_drops,
    patch_scene_with_drops,
    start_exploration_for_user,
)
from bot.plugins.xiuxian_game.features.farm import (
    auto_harvest_farm_for_user,
    harvest_farm_plot_for_user,
    plant_crop_for_user,
    tend_farm_plot_for_user,
    unlock_farm_plot_for_user,
)
from bot.plugins.xiuxian_game.features.fishing import cast_fishing_line_for_user
from bot.plugins.xiuxian_game.features.gambling import (
    build_gambling_bundle,
    exchange_immortal_stones,
    open_immortal_stones,
)
from bot.plugins.xiuxian_game.features.growth import (
    claim_spirit_stone_commission,
    breakthrough_for_user,
    create_foundation_pill_for_user_if_missing,
    ensure_seed_data,
    format_root,
    init_path_for_user,
    maybe_gain_cultivation_from_chat,
    practice_for_user,
    serialize_full_profile,
)
from bot.plugins.xiuxian_game.features.inventory import (
    activate_talisman_for_user,
    activate_technique_for_user,
    bind_artifact_for_user,
    bind_talisman_for_user,
    equip_artifact_for_user,
    set_current_title_for_user,
    unbind_artifact_for_user,
    unbind_talisman_for_user,
)
from bot.plugins.xiuxian_game.features.mentorship import (
    consult_mentor_for_user,
    create_mentorship_request_for_user,
    dissolve_mentorship_for_user,
    graduate_mentorship_for_user,
    mentor_teach_for_user,
    respond_mentorship_request_for_user,
)
from bot.plugins.xiuxian_game.features.marriage import (
    create_marriage_request_for_user,
    divorce_with_spouse,
    dual_cultivate_with_spouse,
    respond_marriage_request_for_user,
    set_gender_for_user,
)
from bot.plugins.xiuxian_game.features.bundle_cache import bootstrap_cache_generation
from bot.plugins.xiuxian_game.features.miniapp_bundle import (
    build_craft_action_bundle_patch,
    build_fishing_cast_bundle_patch,
    build_gambling_action_bundle_patch,
    build_bootstrap_core_bundle,
    build_full_profile_bundle,
)
from bot.plugins.xiuxian_game.features.pills import consume_pill_for_user
from bot.plugins.xiuxian_game.features.retreat import finish_retreat_for_user, start_retreat_for_user
from bot.plugins.xiuxian_game.features.sects import (
    claim_sect_salary_for_user,
    create_sect_with_roles,
    donate_item_to_sect_treasury,
    join_sect_for_user,
    leave_sect_for_user,
    perform_sect_attendance,
    perform_sect_teach,
    set_user_sect_role,
)
from bot.plugins.xiuxian_game.features.shop import (
    cancel_personal_auction_listing,
    create_personal_auction_listing,
    convert_emby_coin_to_stone,
    convert_stone_to_emby_coin,
    create_official_shop_listing,
    create_personal_shop_listing,
    finalize_auction_listing,
    generate_shop_name,
    grant_item_to_user,
    list_public_shop_items,
    patch_auction_listing,
    patch_shop_listing,
    place_auction_bid,
    purchase_shop_item,
    recycle_items_to_official_shop,
    recycle_item_to_official_shop,
    search_xiuxian_players,
)
from bot.plugins.xiuxian_game.features.social import (
    cancel_duel_bet_pool,
    claim_red_envelope_for_user,
    create_duel_bet_pool_for_duel,
    create_red_envelope_for_user,
    format_duel_bet_board,
    harvest_furnace_for_user,
    place_duel_bet,
    rob_player,
    settle_duel_bet_pool,
    switch_social_mode_for_user,
    update_duel_bet_pool_message,
)
from bot.plugins.xiuxian_game.features.tasks import (
    cancel_task_for_user,
    claim_task_for_user,
    create_bounty_task,
    mark_task_group_message,
    resolve_quiz_answer,
)
from bot.plugins.xiuxian_game.features.ui import (
    build_plugin_url,
    duel_keyboard,
    leaderboard_keyboard,
    xiuxian_confirm_keyboard,
    xiuxian_profile_keyboard,
)
from bot.plugins.xiuxian_game.features.boss import (
    attack_world_boss,
    challenge_personal_boss,
    get_world_boss_status_for_user,
    list_personal_bosses_for_user,
    spawn_world_boss,
    try_spawn_world_boss,
)
from bot.plugins.xiuxian_game.features.world_bundle import build_world_bundle
from bot.plugins.xiuxian_game.wiki_service import build_wiki_bundle
from bot.ranks_helper.ranks_draw import RanksDraw
from bot.scheduler.bot_commands import BotCommands
from bot.sql_helper.sql_xiuxian import (
    DEFAULT_SETTINGS,
    REALM_ORDER,
    WebAuthRateLimitError,
    cancel_personal_shop_item,
    create_achievement,
    create_artifact,
    create_artifact_set,
    admin_patch_marriage,
    admin_patch_marriage_request,
    admin_patch_mentorship,
    admin_patch_mentorship_request,
    create_boss_config,
    create_error_log,
    create_journal,
    create_material,
    create_pill,
    create_talisman,
    delete_artifact,
    delete_artifact_set,
    delete_achievement,
    delete_boss_config,
    delete_material,
    delete_pill,
    delete_recipe,
    delete_scene,
    delete_sect,
    delete_technique,
    delete_title,
    delete_talisman,
    delete_task,
    create_technique,
    get_emby_account,
    get_latest_group_encounter_time,
    get_xiuxian_settings,
    grant_image_upload_permission,
    has_image_upload_permission,
    list_artifacts,
    list_materials,
    list_achievements,
    list_admin_marriage_requests,
    list_admin_marriages,
    list_admin_mentorship_requests,
    list_admin_mentorships,
    list_artifact_sets,
    list_auction_items,
    list_boss_configs,
    list_error_logs,
    list_pill_type_options,
    list_image_upload_permissions,
    list_pills,
    list_titles,
    list_recent_journals,
    list_recipes,
    list_recipe_ingredients,
    list_scene_drops,
    list_scenes,
    list_shop_items,
    list_sect_roles,
    list_sects,
    list_talismans,
    list_tasks,
    list_techniques,
    grant_title_to_user,
    mark_user_achievement_notification,
    patch_achievement,
    patch_artifact,
    patch_artifact_set,
    patch_boss_config,
    patch_material,
    patch_pill,
    patch_sect,
    patch_talisman,
    patch_technique,
    patch_title,
    replace_sect_roles,
    revoke_image_upload_permission,
    serialize_profile,
    set_xiuxian_settings,
    sync_title_by_name,
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
from bot.plugins.xiuxian_game.achievement_service import (
    ACHIEVEMENT_METRIC_PRESETS,
    format_reward_summary,
    record_achievement_progress,
)
from bot.plugins.xiuxian_game.shared.request_helpers import (
    actor_from_request as _actor_from_request,
    can_user_upload_images as _can_user_upload_images,
    extract_init_data_from_body_bytes as _extract_init_data_from_body_bytes,
    public_url_root_from as _public_url_root,
    resolve_group_image_source as _resolve_group_image_source,
    sanitize_upload_folder as _sanitize_upload_folder,
    save_uploaded_image as _save_uploaded_image,
    verify_admin_from_credential as _verify_admin_credential,
    verify_user_from_init_data as _verify_user_from_init_data,
)
from bot.web.api.miniapp import is_admin_user_id, verify_init_data


PLAIN_TEXT_MODE = enums.ParseMode.DISABLED
RICH_TEXT_MODE = enums.ParseMode.MARKDOWN


PLUGIN_ROOT = Path(__file__).resolve().parent
STATIC_DIR = PLUGIN_ROOT / "static"
DATA_DIR = PLUGIN_ROOT.parent.parent.parent / "data"
UPLOAD_DIR = DATA_DIR / "xiuxian_uploads"
PLUGIN_MANIFEST = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
PLUGIN_VERSION = str(PLUGIN_MANIFEST.get("version") or "0.1.0")
PLUGIN_NAME = str(PLUGIN_MANIFEST.get("name") or "修仙玩法")
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MARKDOWN_ESCAPE_PATTERN = re.compile(r"([_*\[`])")
SHANGHAI_TZ = timezone(timedelta(hours=8))
DUEL_MESSAGE_REFRESH_CACHE: dict[int, float] = {}
DUEL_SETTLEMENT_CACHE: dict[int, dict[str, Any]] = {}
PENDING_DUEL_INVITES: dict[tuple[int, int], dict[str, Any]] = {}
MESSAGE_AUTO_DELETE_TASKS: dict[tuple[int, int], asyncio.Task] = {}
AUCTION_FINALIZE_TASKS: dict[int, asyncio.Task] = {}
ARENA_FINALIZE_TASKS: dict[int, asyncio.Task] = {}
EVENT_SUMMARY_MESSAGES: dict[int, int] = {}
EVENT_SUMMARY_LAST_TEXTS: dict[int, str] = {}
EVENT_SUMMARY_PINNED_MESSAGES: dict[int, int] = {}
EVENT_SUMMARY_REFRESH_TASK: asyncio.Task | None = None
EVENT_SUMMARY_LOOP_TASK: asyncio.Task | None = None
ENCOUNTER_AUTO_DISPATCH_LOOP_TASK: asyncio.Task | None = None
ENCOUNTER_AUTO_DISPATCH_LOCK: asyncio.Lock | None = None
EVENT_SUMMARY_REFRESH_LOCK: asyncio.Lock | None = None
EVENT_SUMMARY_DIRTY_CHATS: set[int] = set()
EVENT_SUMMARY_FORCE_FULL_REFRESH = False
EVENT_SUMMARY_FORCE_CREATE = False
EVENT_SUMMARY_REQUEST_TOKEN = 0
EVENT_SUMMARY_SNAPSHOT_CACHE: dict[str, Any] | None = None
EVENT_SUMMARY_SNAPSHOT_CACHE_AT = 0.0
EVENT_SUMMARY_SNAPSHOT_TTL_SECONDS = 15.0
EVENT_SUMMARY_MESSAGE_MAP_KEY = "event_summary_message_map"
NOTICE_GROUP_RESOLUTION_CACHE: dict[str, dict[str, Any]] = {}
COMMAND_DISPATCH_CACHE: dict[tuple[int, int, str], float] = {}
ENCOUNTER_AUTO_CHAT_STATE: dict[int, bool] = {}
DUEL_SETTLEMENT_PAGE_SIZE = 10
STATIC_ASSET_PATTERN = re.compile(r'(/plugins/xiuxian/static/([A-Za-z0-9_.-]+\.(?:css|js)))')


def _env_int(name: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = max(minimum, int(raw))
        if maximum is not None:
            value = min(value, maximum)
        return value
    except (TypeError, ValueError):
        LOGGER.warning(f"环境变量 {name}={raw!r} 不是有效整数，回退到默认值 {default}")
        return default


XIUXIAN_API_MAX_CONCURRENCY = _env_int("PIVKEYU_XIUXIAN_API_MAX_CONCURRENCY", 48, minimum=1, maximum=512)
XIUXIAN_HEAVY_API_MAX_CONCURRENCY = _env_int("PIVKEYU_XIUXIAN_HEAVY_API_MAX_CONCURRENCY", 16, minimum=1, maximum=128)
XIUXIAN_VIEW_API_MAX_CONCURRENCY = _env_int("PIVKEYU_XIUXIAN_VIEW_API_MAX_CONCURRENCY", 32, minimum=1, maximum=128)
XIUXIAN_ACTION_API_MAX_CONCURRENCY = _env_int("PIVKEYU_XIUXIAN_ACTION_API_MAX_CONCURRENCY", 32, minimum=1, maximum=256)
XIUXIAN_API_ACQUIRE_TIMEOUT = _env_int("PIVKEYU_XIUXIAN_API_ACQUIRE_TIMEOUT", 5, minimum=1, maximum=30)
XIUXIAN_ACTION_API_ACQUIRE_TIMEOUT = _env_int("PIVKEYU_XIUXIAN_ACTION_API_ACQUIRE_TIMEOUT", 10, minimum=1, maximum=60)
_XIUXIAN_API_SEMAPHORE = asyncio.Semaphore(XIUXIAN_API_MAX_CONCURRENCY)
_XIUXIAN_VIEW_API_SEMAPHORE = asyncio.Semaphore(XIUXIAN_VIEW_API_MAX_CONCURRENCY)
_XIUXIAN_ACTION_API_SEMAPHORE = asyncio.Semaphore(XIUXIAN_ACTION_API_MAX_CONCURRENCY)
_XIUXIAN_VIEW_API_PREFIXES = (
    "/plugins/xiuxian/api/bootstrap",
    "/plugins/xiuxian/api/bootstrap/deferred",
    "/plugins/xiuxian/api/bootstrap/section/",
    "/plugins/xiuxian/api/wiki",
    "/plugins/xiuxian/api/boss/list",
    "/plugins/xiuxian/api/boss/world/status",
    "/plugins/xiuxian/api/player/search",
    "/plugins/xiuxian/admin-api/bootstrap",
)
_XIUXIAN_ACTION_API_PREFIXES = (
    "/plugins/xiuxian/api/gambling/exchange",
    "/plugins/xiuxian/api/gambling/open",
    "/plugins/xiuxian/api/fishing/cast",
    "/plugins/xiuxian/api/explore/start",
    "/plugins/xiuxian/api/explore/claim",
    "/plugins/xiuxian/api/boss/challenge",
    "/plugins/xiuxian/api/boss/world/attack",
    "/plugins/xiuxian/api/pill/use",
    "/plugins/xiuxian/api/retreat",
    "/plugins/xiuxian/api/sect/donate",
    "/plugins/xiuxian/api/farm/auto-harvest",
)
_XIUXIAN_USER_ACTION_LOCK = Lock()
_XIUXIAN_USER_ACTION_KEYS: set[tuple[str, int]] = set()
_XIUXIAN_WIKI_BUILD_TASK: asyncio.Task | None = None
_XIUXIAN_WIKI_BUILD_LOCK = asyncio.Lock()
_ADMIN_SEED_SYNC_LOCK = Lock()
_ADMIN_SEED_SYNC_AT = 0.0
_ADMIN_SEED_SYNC_INTERVAL = max(int(os.getenv("PIVKEYU_XIUXIAN_ADMIN_SEED_SYNC_INTERVAL", "300") or 300), 60)


def _ensure_seed_data_throttled(*, force: bool = False) -> None:
    global _ADMIN_SEED_SYNC_AT
    now = time.monotonic()
    if not force and now - _ADMIN_SEED_SYNC_AT < _ADMIN_SEED_SYNC_INTERVAL:
        return
    with _ADMIN_SEED_SYNC_LOCK:
        now = time.monotonic()
        if not force and now - _ADMIN_SEED_SYNC_AT < _ADMIN_SEED_SYNC_INTERVAL:
            return
        ensure_seed_data()
        _ADMIN_SEED_SYNC_AT = now


def _is_xiuxian_api_path(path: str) -> bool:
    return path.startswith("/plugins/xiuxian/api/") or path.startswith("/plugins/xiuxian/admin-api/")


def _is_view_xiuxian_api_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _XIUXIAN_VIEW_API_PREFIXES)


def _is_action_xiuxian_api_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _XIUXIAN_ACTION_API_PREFIXES)


async def _try_acquire_api_slot(semaphore: asyncio.Semaphore, timeout: int) -> bool:
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False


async def _acquire_xiuxian_api_slots(path: str) -> list[asyncio.Semaphore] | None:
    acquired: list[asyncio.Semaphore] = []
    if _is_view_xiuxian_api_path(path):
        semaphores = (_XIUXIAN_VIEW_API_SEMAPHORE,)
        timeout = XIUXIAN_API_ACQUIRE_TIMEOUT
    elif _is_action_xiuxian_api_path(path):
        semaphores = (_XIUXIAN_ACTION_API_SEMAPHORE,)
        timeout = XIUXIAN_ACTION_API_ACQUIRE_TIMEOUT
    else:
        semaphores = (_XIUXIAN_API_SEMAPHORE,)
        timeout = XIUXIAN_API_ACQUIRE_TIMEOUT
    for semaphore in semaphores:
        if not await _try_acquire_api_slot(semaphore, timeout):
            for item in reversed(acquired):
                item.release()
            return None
        acquired.append(semaphore)
    return acquired


def _release_xiuxian_api_slots(acquired: list[asyncio.Semaphore]) -> None:
    for semaphore in reversed(acquired):
        semaphore.release()


def _try_acquire_user_action(action: str, tg: int) -> tuple[str, int] | None:
    key = (str(action or "").strip(), int(tg or 0))
    if not key[0] or key[1] <= 0:
        return None
    with _XIUXIAN_USER_ACTION_LOCK:
        if key in _XIUXIAN_USER_ACTION_KEYS:
            return None
        _XIUXIAN_USER_ACTION_KEYS.add(key)
    return key


def _release_user_action(key: tuple[str, int] | None) -> None:
    if key is None:
        return
    with _XIUXIAN_USER_ACTION_LOCK:
        _XIUXIAN_USER_ACTION_KEYS.discard(key)


def _cached_wiki_bundle() -> dict[str, Any]:
    from bot.plugins.xiuxian_game.cache import CATALOG_TTL, load_multi_versioned_json

    return load_multi_versioned_json(
        version_part_groups=(
            ("catalog", "achievements"),
            ("catalog", "artifact-sets"),
            ("catalog", "artifacts"),
            ("catalog", "bosses"),
            ("catalog", "encounters"),
            ("catalog", "materials"),
            ("catalog", "pills"),
            ("catalog", "recipes"),
            ("catalog", "scenes"),
            ("catalog", "shop-items"),
            ("catalog", "talismans"),
            ("catalog", "tasks"),
            ("catalog", "techniques"),
            ("catalog", "titles"),
        ),
        cache_parts=("wiki-bundle",),
        ttl=min(CATALOG_TTL, 60),
        loader=build_wiki_bundle,
    )


async def _wiki_bundle_once() -> dict[str, Any]:
    global _XIUXIAN_WIKI_BUILD_TASK
    async with _XIUXIAN_WIKI_BUILD_LOCK:
        task = _XIUXIAN_WIKI_BUILD_TASK
        if task is None or task.done():
            task = asyncio.create_task(run_in_threadpool(_cached_wiki_bundle))
            _XIUXIAN_WIKI_BUILD_TASK = task

            def _cleanup(done_task: asyncio.Task) -> None:
                global _XIUXIAN_WIKI_BUILD_TASK
                if _XIUXIAN_WIKI_BUILD_TASK is done_task:
                    _XIUXIAN_WIKI_BUILD_TASK = None

            task.add_done_callback(_cleanup)
    return await task


XIUXIAN_BOT_COMMANDS = (
    BotCommand("xiuxian", f"修仙玩法 v{PLUGIN_VERSION} [私聊]"),
    BotCommand("xiuxian_me", "展示修仙名帖 [群聊]"),
    BotCommand("xiuxian_rank", "查看修仙排行榜 [群聊]"),
    BotCommand("xiuxian_world", "查看修仙信息汇总 [群聊]"),
    BotCommand("train", "群内吐纳修炼 [群聊]"),
    BotCommand("work", "群内结算灵石委托，可一键完成 [群聊]"),
    BotCommand("salary", "群内领取宗门俸禄 [群聊]"),
    BotCommand("duel", "回复目标发起斗法 [群聊]"),
    BotCommand("deathduel", "回复目标发起生死斗 [群聊]"),
    BotCommand("servitudeduel", "回复目标发起炉鼎斗 [群聊]"),
    BotCommand("leitai", "开启分境界擂台 [群聊]"),
    BotCommand("caibu", "回复自己的炉鼎进行采补 [群聊]"),
    BotCommand("seek", "回复目标探查对方信息 [群聊]"),
    BotCommand("rob", "回复目标发起抢劫 [群聊]"),
    BotCommand("gift", "赠送灵石给其他玩家"),
)
GIFT_INLINE_AMOUNT_PATTERN = re.compile(r"^[\\/!\\.](?:gift)(?:@[A-Za-z0-9_]+)?(\d+)\s*$", re.IGNORECASE)
COMMISSION_COMMAND_ALIASES = {
    "work": "work",
    "打工": "work",
    "仙坊": "work",
    "仙坊打工": "work",
    "spirit_field": "spirit_field",
    "灵田": "spirit_field",
    "灵田照料": "spirit_field",
    "照料灵田": "spirit_field",
    "beast_hunt": "beast_hunt",
    "灵兽": "beast_hunt",
    "代捕灵兽": "beast_hunt",
    "caravan_guard": "caravan_guard",
    "商队": "caravan_guard",
    "护送": "caravan_guard",
    "护送商队": "caravan_guard",
    "formation_maintenance": "formation_maintenance",
    "阵法": "formation_maintenance",
    "检修护山阵": "formation_maintenance",
    "sword_repair": "sword_repair",
    "修剑": "sword_repair",
    "修补灵剑": "sword_repair",
    "rift_patrol": "rift_patrol",
    "裂隙": "rift_patrol",
    "前哨": "rift_patrol",
    "镇守裂隙前哨": "rift_patrol",
}
DUEL_COMMAND_MODES = {
    "duel": "standard",
    "deathduel": "death",
    "lifedeathduel": "death",
    "servitudeduel": "master",
    "furnaceduel": "master",
    "masterduel": "master",
    "slaveduel": "master",
}
XIUXIAN_RANK_KIND_ALIASES = {
    "stone": "stone",
    "stones": "stone",
    "stone_rank": "stone",
    "灵石": "stone",
    "灵石榜": "stone",
    "realm": "realm",
    "realms": "realm",
    "realm_rank": "realm",
    "境界": "realm",
    "境界榜": "realm",
    "修为": "realm",
    "修为榜": "realm",
    "artifact": "artifact",
    "artifacts": "artifact",
    "artifact_rank": "artifact",
    "法宝": "artifact",
    "法宝榜": "artifact",
    "装备": "artifact",
    "装备榜": "artifact",
}



# Import runtime contract shared by bot/web entries.
from .shared.runtime_contract import (  # noqa: F401
    _format_profile_text,
    _md_escape,
    _message_jump_url,
    _message_jump_link,
    _format_notice_card,
    _format_layer_upgrade_line,
    _build_bottom_nav,
    _admin_player_bundle_payload,
    _admin_player_search_payload,
    _resolve_notice_group_setting_value,
    _resolve_notice_group_settings_patch,
    _resolve_notice_group_chat_id,
    _resolve_notice_group_reference_to_chat_id,
    _notice_group_chat_id,
    _parse_notice_group_reference,
    _notice_group_setting_key,
    _notice_group_cache_raw,
    _cached_notice_group_chat_id,
    _store_notice_group_chat_id,
    _clear_notice_group_cache,
    _with_full_bundle,
    _with_core_bundle,
    _with_result_core_bundle,
    _full_bundle,
    _bootstrap_core_bundle,
    build_deferred_bundle_once,
    build_deferred_section_once,
    _bundle_runtime_flags,
    _is_group_admin,
    _main_group_chat_id,
    _configured_group_chat_ids,
    _message_auto_delete_seconds,
    _apply_message_auto_delete,
    _send_message,
    _reply_text,
    _send_photo,
    _edit_text,
    _edit_caption,
    _event_summary_interval_minutes,
    _queue_event_summary_refresh,
    _event_summary_snapshot,
    _refresh_all_event_summaries,
    _admin_panel_url,
    _remember_journal,
    _notify_achievement_unlocks,
    _resolve_notice_group_reference_to_chat_id,
    _resolve_notice_group_chat_id,
    _resolve_notice_group_setting_value,
    _resolve_notice_group_settings_patch,
    _duel_settlement_total_pages,
    _duel_profile_label,
    _duel_side_label,
    _sort_active_notice_arenas,
    _format_duration_seconds,
    _duel_mode_emoji,
    _duel_mode_label,
    _format_duel_stream_text,
    _stream_duel_battle,
    _duel_bet_settings,
    _duel_bet_keyboard,
    _duel_settlement_keyboard,
    _build_duel_result_private_message,
    _build_duel_bet_private_message,
    _notify_duel_participants,
    _notify_duel_bettors,
    _latest_visible_duel_statuses,
    _maybe_refresh_duel_bet_message,
    _red_envelope_keyboard,
    _encounter_keyboard,
    _shop_notice_text,
    _shop_notice_keyboard,
    _refresh_shop_notice_message,
    _push_shop_notice_to_group,
    _auction_time_text,
    _auction_group_text,
    _auction_bid_button_text,
    _auction_keyboard,
    _refresh_auction_group_message,
    _pin_auction_group_message,
    _unpin_auction_group_message,
    _drop_auction_finalize_task,
    _finalize_auction_flow,
    _queue_auction_finalize_task,
    _schedule_active_auction_finalize_tasks,
    _push_auction_to_group,
    _arena_remaining_text,
    _arena_keyboard,
    _arena_group_text,
    _refresh_arena_group_message,
    _pin_arena_group_message,
    _unpin_arena_group_message,
    _drop_arena_finalize_task,
    _finalize_arena_flow,
    _queue_arena_finalize_task,
    _schedule_active_arena_finalize_tasks,
    _push_arena_to_group,
    _quiz_task_text,
    _task_required_lines,
    _task_reward_lines,
    _task_group_text,
    _split_photo_caption,
    _build_red_envelope_generated_cover,
    _red_envelope_notice_photo,
    _red_envelope_notice_text,
    _push_quiz_task,
    _push_task_to_group,
    _safe_push_task_to_group,
    _push_red_envelope_notice,
    _push_group_encounter_notice,
    _maybe_broadcast_craft,
    _maybe_broadcast_gambling,
    _admin_world_snapshot,
    _parse_shanghai_datetime,
    _telegram_user_display_name,
    _telegram_identity_payload,
    _refresh_profile_identity_from_telegram,
    _merge_profile_identity,
    _format_group_profile_showcase,
    _delete_message_after_delay,
    _delete_user_command_message,
    _edit_message_text,
    _event_summary_message_map,
    _persist_event_summary_message,
    _stored_event_summary_message_id,
    _remember_event_summary_message,
    _forget_event_summary_message,
    _is_message_not_modified_error,
    _invalidate_event_summary_snapshot,
    _active_notice_shop_items,
    _active_notice_auctions,
    _active_notice_arenas,
    _event_summary_target_chat_ids,
    _event_summary_lock,
    _summary_remaining_text,
    _build_event_summary_text,
    _message_text_content,
    _message_id_value,
    _is_event_summary_message,
    _get_pinned_chat_message,
    _bound_existing_event_summary_message,
    _pin_event_summary_message,
    _refresh_event_summary_for_chat,
    _configured_event_summary_chat_ids,
    _normalize_event_summary_chat_ids,
    _register_command_dispatch,
    _parse_xiuxian_rank_args,
    _xiuxian_basic_guide_text,
    _encounter_auto_trigger_enabled,
    _encounter_auto_dispatch_chat_ids,
    _encounter_auto_dispatch_due,
    _encounter_auto_dispatch_last_date,
    _datetime_shanghai_day_key,
    _latest_group_encounter_day_key,
    _mark_encounter_auto_dispatch_done,
    _dispatch_due_group_encounters,
    _chat_member_status_value,
    _chat_member_has_privilege,
    _chat_member_can_manage_tags,
    _sync_xiuxian_title_to_group,
    _can_manage_upload_permissions,
    _require_message_user,
    _achievement_private_text,
    _achievement_group_text,
    _duel_refresh_interval,
    _normalize_duel_mode_arg,
    _duel_invite_timeout_seconds,
    _duel_invite_key,
    _duel_invite_message_key,
    _duel_invite_matches,
    _get_pending_duel_invite,
    _cancel_pending_duel_invite_task,
    _pop_pending_duel_invite,
    _format_duel_invite_footer,
    _format_duel_invite_closed_text,
    _expire_duel_invite,
    _register_pending_duel_invite,
    _duel_log_emoji,
    _duel_snapshot_line,
    _duel_snapshot_sources,
    _duel_loadout_line,
    _duel_compact_log_excerpt,
    _duel_find_source_excerpt,
    _duel_showcase_line,
    _latest_duel_impact_line,
    _normalize_commission_command_key,
    _select_group_commission,
    _select_group_commissions,
    _commission_selection_error,
    _minimal_player_lookup_payload,
    _resolve_gift_target_and_amount,
    _gift_group_broadcast_text,
    _format_attribute_growth_text,
    _effective_divine_sense,
    STATIC_DIR,
    UPLOAD_DIR,
    LOGGER,
)

from .shared.error_reporting import (
    operation_name_from_request as _operation_name_from_request,
    record_request_error as _record_request_error,
)

def register_web(app) -> None:
    user_router = APIRouter(prefix="/plugins/xiuxian", tags=["xiuxian-user"])
    admin_router = APIRouter(prefix="/plugins/xiuxian/admin-api", tags=["xiuxian-admin"])

    if STATIC_DIR.exists():
        app.mount("/plugins/xiuxian/static", StaticFiles(directory=STATIC_DIR), name="xiuxian-static")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/plugins/xiuxian/uploads", StaticFiles(directory=UPLOAD_DIR), name="xiuxian-uploads")

    if not getattr(app.state, "xiuxian_request_context_middleware", False):
        @app.middleware("http")
        async def xiuxian_request_context_middleware(request: Request, call_next):
            path = str(request.url.path or "")
            acquired_slots: list[asyncio.Semaphore] = []
            if _is_xiuxian_api_path(path):
                slots = await _acquire_xiuxian_api_slots(path)
                if slots is None:
                    LOGGER.warning(f"xiuxian api busy path={path}")
                    return JSONResponse(
                        status_code=429,
                        content={
                            "code": 429,
                            "message": "当前请求较多，请稍后再试。",
                            "detail": "Too Many Requests",
                        },
                    )
                acquired_slots = slots
            try:
                if path.startswith("/plugins/xiuxian"):
                    init_data = request.headers.get("x-telegram-init-data")
                    if not init_data:
                        try:
                            body = await request.body()
                        except ClientDisconnect:
                            return JSONResponse(
                                status_code=499,
                                content={
                                    "code": 499,
                                    "message": "客户端已断开连接。",
                                    "detail": "Client Disconnect",
                                },
                            )
                        init_data = _extract_init_data_from_body_bytes(request.headers.get("content-type", ""), body)

                        async def receive():
                            return {"type": "http.request", "body": body, "more_body": False}

                        request = Request(request.scope, receive)
                    request.state.xiuxian_init_data = init_data
                return await call_next(request)
            finally:
                _release_xiuxian_api_slots(acquired_slots)

        app.state.xiuxian_request_context_middleware = True

    if not getattr(app.state, "xiuxian_value_error_handler", False):
        @app.exception_handler(ValueError)
        async def xiuxian_value_error_handler(request: Request, exc: ValueError):
            if str(request.url.path or "").startswith("/plugins/xiuxian"):
                _record_request_error(request, exc, status_code=400, level="WARNING")
            return JSONResponse(status_code=400, content={"code": 400, "message": str(exc), "detail": str(exc)})

        app.state.xiuxian_value_error_handler = True

    if not getattr(app.state, "xiuxian_http_exception_handler", False):
        @app.exception_handler(HTTPException)
        async def xiuxian_http_exception_handler(request: Request, exc: HTTPException):
            if str(request.url.path or "").startswith("/plugins/xiuxian"):
                level = "ERROR" if int(exc.status_code or 500) >= 500 else "WARNING"
                detail = str(exc.detail or exc.status_code)
                _record_request_error(request, Exception(detail), status_code=int(exc.status_code or 500), level=level)
            return JSONResponse(
                status_code=exc.status_code,
                content={"code": exc.status_code, "message": str(exc.detail), "detail": str(exc.detail)},
            )

        app.state.xiuxian_http_exception_handler = True

    if not getattr(app.state, "xiuxian_exception_handler", False):
        @app.exception_handler(Exception)
        async def xiuxian_exception_handler(request: Request, exc: Exception):
            if str(request.url.path or "").startswith("/plugins/xiuxian"):
                _record_request_error(request, exc, status_code=500, level="ERROR")
            LOGGER.exception(f"xiuxian api unhandled error: {exc}")
            return JSONResponse(
                status_code=500,
                content={
                    "code": 500,
                    "message": "内部服务暂时出了点岔子，请稍后再试。",
                    "detail": str(exc) or "Internal Server Error",
                },
            )

        app.state.xiuxian_exception_handler = True

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
    def xiuxian_root_page():
        return RedirectResponse(url="/plugins/xiuxian/app", status_code=302)

    @user_router.get("/app")
    def xiuxian_app_page():
        return render_versioned_static_page("app.html")

    @user_router.get("/admin")
    def xiuxian_admin_page():
        return render_versioned_static_page("admin.html")

    def _web_session_token_from_payload(payload: WebAuthSessionPayload | InitDataPayload | None) -> str:
        token = str(getattr(payload, "session_token", "") or "").strip()
        if token:
            return token
        init_data = str(getattr(payload, "init_data", "") or "").strip()
        if init_data.startswith("web_session:"):
            return init_data.removeprefix("web_session:").strip()
        return ""

    def _verify_telegram_bind_user(init_data: str) -> dict[str, Any]:
        raw = str(init_data or "").strip()
        if not raw:
            raise HTTPException(status_code=400, detail="缺少 Telegram 绑定凭证")
        if raw.startswith("web_session:"):
            raise HTTPException(status_code=400, detail="绑定 Telegram 需要从 Telegram 内打开一次")
        return verify_init_data(raw)["user"]

    def _auto_bind_web_auth_result(result: dict[str, Any], telegram_user: dict[str, Any] | None) -> dict[str, Any]:
        if not telegram_user:
            return result
        account = bind_xiuxian_web_account_to_telegram(str(result.get("session_token") or ""), telegram_user)
        patched = dict(result)
        patched["account"] = account
        patched["telegram_user"] = telegram_user
        return patched

    @user_router.post("/api/auth/register")
    async def xiuxian_web_auth_register(payload: WebAuthRegisterPayload):
        def _run():
            telegram_user = _verify_telegram_bind_user(payload.init_data) if str(payload.init_data or "").strip() else None
            result = register_xiuxian_web_account(
                payload.username,
                payload.password,
                display_name=payload.display_name,
            )
            return _auto_bind_web_auth_result(result, telegram_user)

        try:
            data = await run_in_threadpool(_run)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    @user_router.post("/api/auth/login")
    async def xiuxian_web_auth_login(payload: WebAuthLoginPayload):
        def _run():
            telegram_user = _verify_telegram_bind_user(payload.init_data) if str(payload.init_data or "").strip() else None
            result = login_xiuxian_web_account(payload.username, payload.password)
            return _auto_bind_web_auth_result(result, telegram_user)

        try:
            data = await run_in_threadpool(_run)
        except WebAuthRateLimitError as exc:
            raise HTTPException(
                status_code=429,
                detail=str(exc),
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return {"code": 200, "data": data}

    @user_router.post("/api/auth/me")
    async def xiuxian_web_auth_me(payload: WebAuthSessionPayload):
        token = _web_session_token_from_payload(payload)
        if not token:
            return {"code": 200, "data": {"account": None}}
        try:
            account = await run_in_threadpool(authenticate_xiuxian_web_session, token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return {"code": 200, "data": {"account": account}}

    @user_router.post("/api/auth/bind-telegram")
    async def xiuxian_web_auth_bind_telegram(payload: WebAuthBindTelegramPayload):
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
    async def xiuxian_web_auth_logout(payload: WebAuthSessionPayload):
        token = _web_session_token_from_payload(payload)
        ok = await run_in_threadpool(logout_xiuxian_web_session, token)
        return {"code": 200, "data": {"ok": ok}}

    @user_router.post("/api/bootstrap")
    async def xiuxian_bootstrap(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        profile, bottom_nav, cache_generation = await asyncio.gather(
            run_in_threadpool(_bootstrap_core_bundle, telegram_user["id"]),
            run_in_threadpool(_build_bottom_nav),
            run_in_threadpool(bootstrap_cache_generation, telegram_user["id"]),
        )
        return {
            "code": 200,
            "data": {
                "telegram_user": telegram_user,
                "profile_bundle": profile,
                "cache_generation": cache_generation,
                "app_url": build_plugin_url("/plugins/xiuxian/app"),
                "admin_panel_url": _admin_panel_url() if is_admin_user_id(telegram_user["id"]) else None,
                "home_url": build_plugin_url("/miniapp"),
                "bottom_nav": bottom_nav,
            },
        }

    @user_router.post("/api/bootstrap/deferred")
    async def xiuxian_bootstrap_deferred(payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        return {
            "code": 200,
            "data": await build_deferred_bundle_once(telegram_user["id"]),
        }

    @user_router.post("/api/bootstrap/section/{section}")
    async def xiuxian_bootstrap_section(section: str, payload: InitDataPayload):
        telegram_user = await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        try:
            data = await build_deferred_section_once(telegram_user["id"], section)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "code": 200,
            "data": data,
        }

    @user_router.post("/api/wiki")
    async def xiuxian_wiki_api(payload: InitDataPayload):
        await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        return {"code": 200, "data": await _wiki_bundle_once()}

    @user_router.post("/api/upload-image")
    async def xiuxian_upload_image_api(
        request: Request,
        init_data: str = Form(...),
        folder: str = Form("tasks"),
        file: UploadFile = File(...),
    ):
        def _verify_upload_permission():
            telegram_user = _verify_user_from_init_data(init_data)
            allowed, reason = _can_user_upload_images(telegram_user["id"])
            if not allowed:
                raise HTTPException(status_code=403, detail=reason)
            return telegram_user

        telegram_user = await run_in_threadpool(_verify_upload_permission)
        result = await _save_uploaded_image(file, f"user/{telegram_user['id']}/{folder}", str(request.base_url))
        return {"code": 200, "data": result}

    @user_router.post("/api/enter")
    async def xiuxian_enter(payload: InitDataPayload):
        def _run():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            init_path_for_user(telegram_user["id"])
            create_foundation_pill_for_user_if_missing(telegram_user["id"])
            return _bootstrap_core_bundle(telegram_user["id"])

        return {"code": 200, "data": await run_in_threadpool(_run)}

    @user_router.post("/api/train")
    async def xiuxian_train_api(payload: InitDataPayload):
        def _run():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = practice_for_user(telegram_user["id"])
            return _with_core_bundle(telegram_user["id"], result)

        return {"code": 200, "data": await run_in_threadpool(_run)}

    @user_router.post("/api/commission/claim")
    def xiuxian_commission_claim_api(payload: CommissionClaimPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = claim_spirit_stone_commission(telegram_user["id"], payload.commission_key)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/breakthrough")
    def xiuxian_breakthrough_api(payload: BreakthroughPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = breakthrough_for_user(telegram_user["id"], use_pill=payload.use_pill)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/pill/use")
    def xiuxian_use_pill_api(payload: ConsumePillPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = consume_pill_for_user(telegram_user["id"], payload.pill_id, quantity=payload.quantity)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/artifact/equip")
    def xiuxian_equip_api(payload: EquipArtifactPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = equip_artifact_for_user(telegram_user["id"], payload.artifact_id)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/artifact/bind")
    def xiuxian_bind_artifact_api(payload: ArtifactBindingPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = bind_artifact_for_user(telegram_user["id"], payload.artifact_id)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/artifact/unbind")
    def xiuxian_unbind_artifact_api(payload: ArtifactBindingPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = unbind_artifact_for_user(telegram_user["id"], payload.artifact_id)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/talisman/activate")
    def xiuxian_activate_talisman_api(payload: ActivateTalismanPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = activate_talisman_for_user(telegram_user["id"], payload.talisman_id)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/talisman/bind")
    def xiuxian_bind_talisman_api(payload: TalismanBindingPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = bind_talisman_for_user(telegram_user["id"], payload.talisman_id)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/talisman/unbind")
    def xiuxian_unbind_talisman_api(payload: TalismanBindingPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = unbind_talisman_for_user(telegram_user["id"], payload.talisman_id)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/technique/activate")
    def xiuxian_activate_technique_api(payload: ActivateTechniquePayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = activate_technique_for_user(telegram_user["id"], payload.technique_id)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/title/equip")
    def xiuxian_equip_title_api(payload: TitleEquipPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = set_current_title_for_user(telegram_user["id"], payload.title_id)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/title/group-sync")
    async def xiuxian_sync_title_to_group_api(payload: TitleGroupSyncPayload):
        def _prepare_title_sync():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            bundle = serialize_full_profile(telegram_user["id"])
            current_title = bundle.get("current_title") or {}
            title_name = str(current_title.get("name") or "").strip()
            if not title_name:
                raise HTTPException(status_code=400, detail="请先佩戴称号，再同步到群成员标签。")
            chat_id = int(payload.chat_id or _main_group_chat_id() or 0)
            if not chat_id:
                raise HTTPException(status_code=400, detail="当前未配置可同步的群组。")
            return telegram_user, title_name, chat_id

        telegram_user, title_name, chat_id = await run_in_threadpool(_prepare_title_sync)
        result = await _sync_xiuxian_title_to_group(chat_id, telegram_user["id"], title_name)
        data = await run_in_threadpool(_with_core_bundle, telegram_user["id"], result)
        return {
            "code": 200,
            "data": data,
        }

    @user_router.post("/api/retreat/start")
    def xiuxian_retreat_start_api(payload: RetreatPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = start_retreat_for_user(telegram_user["id"], payload.hours)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/retreat/finish")
    def xiuxian_retreat_finish_api(payload: InitDataPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = finish_retreat_for_user(telegram_user["id"])
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/social-mode")
    def xiuxian_social_mode_api(payload: SocialModePayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = switch_social_mode_for_user(telegram_user["id"], payload.social_mode)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/furnace/harvest")
    def xiuxian_furnace_harvest_api(payload: FurnaceHarvestPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = harvest_furnace_for_user(telegram_user["id"], payload.target_tg)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/mentorship/request")
    def xiuxian_mentorship_request_api(payload: MentorshipRequestPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = create_mentorship_request_for_user(
            telegram_user["id"],
            payload.target_tg,
            payload.sponsor_role,
            message=payload.message,
        )
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/mentorship/request/respond")
    async def xiuxian_mentorship_request_respond_api(payload: MentorshipRequestActionPayload):
        def _work():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = respond_mentorship_request_for_user(telegram_user["id"], payload.request_id, payload.action)
            return telegram_user, result, _with_result_core_bundle(telegram_user["id"], result)

        telegram_user, result, data = await run_in_threadpool(_work)
        await _notify_achievement_unlocks(result.get("achievement_unlocks"))
        return {"code": 200, "data": data}

    @user_router.post("/api/mentorship/teach")
    async def xiuxian_mentorship_teach_api(payload: MentorshipTeachPayload):
        def _work():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = mentor_teach_for_user(telegram_user["id"], payload.disciple_tg)
            return telegram_user, result, _with_result_core_bundle(telegram_user["id"], result)

        telegram_user, result, data = await run_in_threadpool(_work)
        await _notify_achievement_unlocks(result.get("achievement_unlocks"))
        return {"code": 200, "data": data}

    @user_router.post("/api/mentorship/consult")
    async def xiuxian_mentorship_consult_api(payload: InitDataPayload):
        def _work():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = consult_mentor_for_user(telegram_user["id"])
            return telegram_user, result, _with_result_core_bundle(telegram_user["id"], result)

        telegram_user, result, data = await run_in_threadpool(_work)
        await _notify_achievement_unlocks(result.get("achievement_unlocks"))
        return {"code": 200, "data": data}

    @user_router.post("/api/mentorship/graduate")
    async def xiuxian_mentorship_graduate_api(payload: MentorshipTargetPayload):
        def _work():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = graduate_mentorship_for_user(telegram_user["id"], payload.target_tg)
            return telegram_user, result, _with_result_core_bundle(telegram_user["id"], result)

        telegram_user, result, data = await run_in_threadpool(_work)
        await _notify_achievement_unlocks(result.get("achievement_unlocks"))
        return {"code": 200, "data": data}

    @user_router.post("/api/mentorship/dissolve")
    def xiuxian_mentorship_dissolve_api(payload: MentorshipTargetPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = dissolve_mentorship_for_user(telegram_user["id"], payload.target_tg)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/gender/set")
    def xiuxian_gender_set_api(payload: GenderSetPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = set_gender_for_user(telegram_user["id"], payload.gender)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/marriage/request")
    def xiuxian_marriage_request_api(payload: MarriageRequestPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = create_marriage_request_for_user(telegram_user["id"], payload.target_tg, message=payload.message)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/marriage/request/respond")
    def xiuxian_marriage_request_respond_api(payload: MarriageRequestActionPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = respond_marriage_request_for_user(telegram_user["id"], payload.request_id, payload.action)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/marriage/dual-cultivate")
    def xiuxian_marriage_dual_cultivate_api(payload: InitDataPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = dual_cultivate_with_spouse(telegram_user["id"])
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/marriage/divorce")
    def xiuxian_marriage_divorce_api(payload: InitDataPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = divorce_with_spouse(telegram_user["id"])
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/exchange")
    def xiuxian_exchange_api(payload: ExchangePayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        if payload.direction == "coin_to_stone":
            result = convert_emby_coin_to_stone(telegram_user["id"], payload.amount)
        elif payload.direction == "stone_to_coin":
            result = convert_stone_to_emby_coin(telegram_user["id"], payload.amount)
        else:
            raise HTTPException(status_code=400, detail="Unsupported exchange direction")
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/gambling/exchange")
    def xiuxian_gambling_exchange_api(payload: GamblingExchangePayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        action_key = _try_acquire_user_action("gambling-exchange", telegram_user["id"])
        if action_key is None:
            raise HTTPException(status_code=429, detail="上一次奇石兑换仍在处理中，请稍后再试。")
        try:
            result = exchange_immortal_stones(telegram_user["id"], payload.count)
            return {
                "code": 200,
                "data": {
                    "result": result,
                    "bundle_patch": build_gambling_action_bundle_patch(
                        telegram_user["id"],
                        **_bundle_runtime_flags(telegram_user["id"]),
                    ),
                },
            }
        finally:
            _release_user_action(action_key)

    @user_router.post("/api/gambling/open")
    async def xiuxian_gambling_open_api(payload: GamblingOpenPayload):
        def _work():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            action_key = _try_acquire_user_action("gambling-open", telegram_user["id"])
            if action_key is None:
                raise HTTPException(status_code=429, detail="上一次开石仍在处理中，请稍后再试。")
            try:
                result = open_immortal_stones(telegram_user["id"], payload.count)
                return telegram_user, result, {
                    "result": result,
                    "bundle_patch": build_gambling_action_bundle_patch(
                        telegram_user["id"],
                        **_bundle_runtime_flags(telegram_user["id"]),
                    ),
                }
            finally:
                _release_user_action(action_key)

        telegram_user, result, data = await run_in_threadpool(_work)
        await _maybe_broadcast_gambling(telegram_user["id"], result)
        return {"code": 200, "data": data}

    @user_router.post("/api/sect/join")
    def xiuxian_join_sect_api(payload: SectJoinPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = join_sect_for_user(telegram_user["id"], payload.sect_id)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], {"sect": result})}

    @user_router.post("/api/sect/leave")
    def xiuxian_leave_sect_api(payload: InitDataPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = leave_sect_for_user(telegram_user["id"])
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], {"sect": result})}

    @user_router.post("/api/sect/salary")
    def xiuxian_claim_salary_api(payload: InitDataPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = claim_sect_salary_for_user(telegram_user["id"])
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], {"salary": result["salary"]})}

    @user_router.post("/api/sect/attendance")
    def xiuxian_sect_attendance_api(payload: InitDataPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = perform_sect_attendance(telegram_user["id"])
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/sect/teach")
    def xiuxian_sect_teach_api(payload: SectTeachPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = perform_sect_teach(telegram_user["id"], payload.cultivation_amount)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/sect/donate")
    def xiuxian_sect_donate_api(payload: SectDonatePayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = donate_item_to_sect_treasury(
            telegram_user["id"],
            payload.item_kind,
            payload.item_ref_id,
            payload.quantity,
        )
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/task/create")
    async def xiuxian_create_task_api(payload: UserTaskPayload):
        def _create_task():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            task = create_bounty_task(
                actor_tg=telegram_user["id"],
                title=payload.title,
                description=payload.description,
                task_scope=payload.task_scope,
                task_type=payload.task_type,
                question_text=payload.question_text,
                answer_text=payload.answer_text,
                image_url=payload.image_url,
                required_item_kind=payload.required_item_kind,
                required_item_ref_id=payload.required_item_ref_id,
                required_item_quantity=payload.required_item_quantity,
                requirement_metric_key=payload.requirement_metric_key,
                requirement_metric_target=payload.requirement_metric_target,
                reward_stone=payload.reward_stone,
                reward_cultivation=payload.reward_cultivation,
                reward_scale_mode=payload.reward_scale_mode,
                reward_item_kind=payload.reward_item_kind,
                reward_item_ref_id=payload.reward_item_ref_id,
                reward_item_quantity=payload.reward_item_quantity,
                max_claimants=payload.max_claimants,
                active_in_group=payload.active_in_group,
                group_chat_id=payload.group_chat_id or _main_group_chat_id(),
            )
            return telegram_user, task

        telegram_user, task = await run_in_threadpool(_create_task)
        push_warning = None
        if task.get("active_in_group"):
            task, push_warning = await _safe_push_task_to_group(task)

        def _finish_task():
            _remember_journal(telegram_user["id"], "task", "发布任务", f"发布了任务【{task['title']}】")
            return _with_core_bundle(telegram_user["id"], {"task": task, "push_warning": push_warning})

        return {"code": 200, "data": await run_in_threadpool(_finish_task)}

    @user_router.post("/api/task/claim")
    def xiuxian_claim_task_api(payload: TaskClaimPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = claim_task_for_user(telegram_user["id"], payload.task_id)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/task/cancel")
    async def xiuxian_cancel_task_api(payload: TaskCancelPayload):
        def _cancel_task():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = cancel_task_for_user(telegram_user["id"], payload.task_id)
            return telegram_user, result

        telegram_user, result = await run_in_threadpool(_cancel_task)
        task = result.get("task") or {}
        try:
            task_chat_id = int(task.get("group_chat_id") or _main_group_chat_id() or 0)
            if task_chat_id and task.get("group_message_id"):
                summary = _task_group_text(task) + "\n\n发起者已主动撤销该任务。"
                if task.get("image_url"):
                    caption, _ = _split_photo_caption(summary)
                    await bot.edit_message_caption(
                        task_chat_id,
                        int(task["group_message_id"]),
                        caption or "任务已撤销",
                        parse_mode=RICH_TEXT_MODE,
                    )
                else:
                    await _edit_message_text(
                        bot,
                        task_chat_id,
                        int(task["group_message_id"]),
                        summary,
                        parse_mode=RICH_TEXT_MODE,
                        persistent=True,
                    )
        except Exception as exc:
            LOGGER.warning(f"xiuxian task cancel message refresh failed: {exc}")

        def _finish_cancel_task():
            return _with_result_core_bundle(telegram_user["id"], result)

        return {"code": 200, "data": await run_in_threadpool(_finish_cancel_task)}

    @user_router.post("/api/recipe/craft")
    async def xiuxian_craft_recipe_api(payload: CraftPayload):
        def _work():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = craft_recipe_for_user(telegram_user["id"], payload.recipe_id, payload.quantity)
            flags = _bundle_runtime_flags(telegram_user["id"])
            data = {
                "result": result,
                "bundle_patch": build_craft_action_bundle_patch(telegram_user["id"], **flags),
            }
            return telegram_user, result, data

        telegram_user, result, data = await run_in_threadpool(_work)
        await _maybe_broadcast_craft(telegram_user["id"], result)
        await _notify_achievement_unlocks(result.get("achievement_unlocks"))
        return {"code": 200, "data": data}

    @user_router.post("/api/recipe/synthesize")
    def xiuxian_recipe_fragment_synthesis_api(payload: RecipeFragmentSynthesisPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = synthesize_recipe_fragment_for_user(telegram_user["id"], payload.recipe_id)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/farm/plant")
    def xiuxian_farm_plant_api(payload: FarmPlantPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = plant_crop_for_user(telegram_user["id"], payload.slot_index, payload.material_id)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/farm/care")
    def xiuxian_farm_care_api(payload: FarmCarePayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = tend_farm_plot_for_user(telegram_user["id"], payload.slot_index, payload.action)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/farm/harvest")
    def xiuxian_farm_harvest_api(payload: FarmHarvestPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = harvest_farm_plot_for_user(telegram_user["id"], payload.slot_index)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/farm/auto-harvest")
    def xiuxian_farm_auto_harvest_api(payload: InitDataPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = auto_harvest_farm_for_user(telegram_user["id"])
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/farm/unlock")
    def xiuxian_farm_unlock_api(payload: FarmUnlockPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = unlock_farm_plot_for_user(telegram_user["id"], payload.slot_index)
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    # ── Boss API ──

    @user_router.post("/api/boss/list")
    def xiuxian_boss_list_api(payload: InitDataPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = list_personal_bosses_for_user(telegram_user["id"])
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/boss/challenge")
    def xiuxian_boss_challenge_api(payload: BossChallengePayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = challenge_personal_boss(telegram_user["id"], payload.boss_id)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/boss/world/status")
    def xiuxian_boss_world_status_api(payload: InitDataPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = get_world_boss_status_for_user(telegram_user["id"])
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/boss/world/attack")
    def xiuxian_boss_world_attack_api(payload: InitDataPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = attack_world_boss(telegram_user["id"])
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/fishing/cast")
    def xiuxian_fishing_cast_api(payload: FishingCastPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        action_key = _try_acquire_user_action("fishing-cast", telegram_user["id"])
        if action_key is None:
            raise HTTPException(status_code=429, detail="上一次抛竿仍在处理中，请稍后再试。")
        try:
            result = cast_fishing_line_for_user(telegram_user["id"], payload.spot_key)
            return {
                "code": 200,
                "data": {
                    "result": result,
                    "bundle_patch": build_fishing_cast_bundle_patch(
                        telegram_user["id"],
                        **_bundle_runtime_flags(telegram_user["id"]),
                    ),
                },
            }
        finally:
            _release_user_action(action_key)

    @user_router.post("/api/explore/start")
    def xiuxian_explore_start_api(payload: ExploreStartPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = start_exploration_for_user(telegram_user["id"], payload.scene_id, payload.minutes)
        return {"code": 200, "data": _with_core_bundle(telegram_user["id"], {"exploration": result})}

    @user_router.post("/api/explore/claim")
    async def xiuxian_explore_claim_api(payload: ExploreClaimPayload):
        def _work():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = claim_exploration_for_user(telegram_user["id"], payload.exploration_id)
            return telegram_user, result, _with_result_core_bundle(telegram_user["id"], result)

        telegram_user, result, data = await run_in_threadpool(_work)
        await _notify_achievement_unlocks(result.get("achievement_unlocks"))
        return {"code": 200, "data": data}

    @user_router.post("/api/red-envelope/create")
    async def xiuxian_create_red_envelope_api(payload: RedEnvelopePayload):
        def _create_red_envelope():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = create_red_envelope_for_user(
                tg=telegram_user["id"],
                cover_text=payload.cover_text,
                image_url=payload.image_url,
                mode=payload.mode,
                amount_total=payload.amount_total,
                count_total=payload.count_total,
                target_tg=payload.target_tg,
                group_chat_id=_main_group_chat_id(),
            )
            return telegram_user, result, _with_result_core_bundle(telegram_user["id"], result)

        telegram_user, result, data = await run_in_threadpool(_create_red_envelope)
        await _push_red_envelope_notice(result["envelope"])
        await _notify_achievement_unlocks(result.get("achievement_unlocks"))
        return {"code": 200, "data": data}

    @user_router.post("/api/shop/personal")
    async def xiuxian_personal_shop_api(payload: PersonalShopPayload):
        def _create_listing():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = create_personal_shop_listing(
                tg=telegram_user["id"],
                shop_name=payload.shop_name or generate_shop_name(telegram_user.get("first_name", "道友")),
                item_kind=payload.item_kind,
                item_ref_id=payload.item_ref_id,
                quantity=payload.quantity,
                price_stone=payload.price_stone,
                broadcast=payload.broadcast,
            )
            return telegram_user, result

        telegram_user, result = await run_in_threadpool(_create_listing)
        push_warning = None

        if payload.broadcast:
            try:
                listing, push_warning = await _push_shop_notice_to_group(result["listing"])
                result["listing"] = listing
            except Exception as exc:
                push_warning = str(exc) or "小铺通知推送失败。"
                LOGGER.warning(f"xiuxian shop notice push failed: {exc}")

        def _finish_listing():
            _remember_journal(telegram_user["id"], "shop", "上架商品", f"上架了【{result['listing']['item_name']}】")
            return _with_core_bundle(telegram_user["id"], {**result, "push_warning": push_warning})

        return {"code": 200, "data": await run_in_threadpool(_finish_listing)}

    @user_router.post("/api/auction/personal")
    async def xiuxian_personal_auction_api(payload: PersonalAuctionPayload):
        def _create_auction():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            seller_name = " ".join(
                part for part in [telegram_user.get("first_name"), telegram_user.get("last_name")] if part
            ).strip()
            if not seller_name:
                username = str(telegram_user.get("username") or "").strip()
                seller_name = f"@{username}" if username else f"TG {telegram_user['id']}"

            result = create_personal_auction_listing(
                tg=telegram_user["id"],
                seller_name=seller_name,
                item_kind=payload.item_kind,
                item_ref_id=payload.item_ref_id,
                quantity=payload.quantity,
                opening_price_stone=payload.opening_price_stone,
                bid_increment_stone=payload.bid_increment_stone,
                buyout_price_stone=payload.buyout_price_stone,
            )
            return telegram_user, result

        telegram_user, result = await run_in_threadpool(_create_auction)
        auction = dict(result.get("auction") or {})
        push_warning = None
        try:
            auction, push_warning = await _push_auction_to_group(auction)
        except Exception:
            try:
                await run_in_threadpool(cancel_personal_auction_listing, telegram_user["id"], int(auction.get("id") or 0))
            except Exception as rollback_exc:
                LOGGER.warning(f"xiuxian auction rollback failed auction={auction.get('id')}: {rollback_exc}")
            raise

        def _finish_auction():
            _remember_journal(
                telegram_user["id"],
                "auction",
                "发起拍卖",
                f"拍卖了【{auction.get('item_name') or '未知拍品'}】",
            )
            return _with_core_bundle(telegram_user["id"], {"auction": auction, "push_warning": push_warning})

        return {
            "code": 200,
            "data": await run_in_threadpool(_finish_auction),
        }

    @user_router.post("/api/shop/cancel")
    async def xiuxian_cancel_listing_api(payload: ShopCancelPayload):
        def _cancel_listing():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = cancel_personal_shop_item(telegram_user["id"], payload.item_id)
            return telegram_user, result

        telegram_user, result = await run_in_threadpool(_cancel_listing)
        await _refresh_shop_notice_message((result or {}).get("item") or {})
        _queue_event_summary_refresh(int(((result or {}).get("item") or {}).get("notice_group_chat_id") or 0) or None)

        def _finish_cancel_listing():
            _remember_journal(telegram_user["id"], "shop", "取消上架", f"取消了商品 #{payload.item_id} 的上架")
            return _with_result_core_bundle(telegram_user["id"], result)

        return {"code": 200, "data": await run_in_threadpool(_finish_cancel_listing)}

    @user_router.post("/api/shop/purchase")
    async def xiuxian_purchase_api(payload: PurchasePayload):
        def _purchase_listing():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = purchase_shop_item(telegram_user["id"], payload.item_id, payload.quantity)
            return telegram_user, result

        telegram_user, result = await run_in_threadpool(_purchase_listing)
        await _refresh_shop_notice_message((result or {}).get("item") or {})
        _queue_event_summary_refresh(int((result.get("item") or {}).get("notice_group_chat_id") or 0) or None)
        await run_in_threadpool(
            _remember_journal,
            telegram_user["id"],
            "shop",
            "购买商品",
            f"购买了【{result['item']['item_name']}】",
        )
        seller_tg = result.get("seller_tg")
        if seller_tg and int(seller_tg) != int(telegram_user["id"]):
            try:
                await _send_message(
                    bot,
                    int(seller_tg),
                    f"你的商品【{result['item']['item_name']}】已被 {result.get('buyer_name') or '道友'} 购买，到账 {result['total_cost']} 灵石。",
                )
            except Exception as exc:
                LOGGER.warning(f"xiuxian seller notify failed: {exc}")
        return {"code": 200, "data": await run_in_threadpool(_with_core_bundle, telegram_user["id"], result)}

    @user_router.post("/api/recycle/official")
    def xiuxian_official_recycle_api(payload: OfficialRecyclePayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = recycle_item_to_official_shop(
            tg=telegram_user["id"],
            item_kind=payload.item_kind,
            item_ref_id=payload.item_ref_id,
            quantity=payload.quantity,
        )
        net_stone_gain = result.get("net_stone_gain")
        received_stone = net_stone_gain if net_stone_gain is not None else result.get("total_price_stone") or 0
        _remember_journal(
            telegram_user["id"],
            "shop",
            "万宝归炉",
            f"归炉了【{result.get('item_name') or '未知物品'}】x{result.get('quantity') or 0}，到账 {received_stone} 灵石",
        )
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/recycle/official/batch")
    def xiuxian_official_recycle_batch_api(payload: OfficialRecycleBatchPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = recycle_items_to_official_shop(
            tg=telegram_user["id"],
            items=[item.model_dump() for item in payload.items],
        )
        if result.get("recycled_line_count"):
            _remember_journal(
                telegram_user["id"],
                "shop",
                "万宝归炉",
                str(result.get("summary_text") or "完成了一次批量归炉。"),
            )
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/player/search")
    def xiuxian_player_search_api(payload: PlayerLookupPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        keyword = str(payload.query or "").strip()
        if not keyword:
            return {"code": 200, "data": {"items": [], "page": payload.page, "page_size": payload.page_size, "total": 0}}
        result = search_xiuxian_players(query=keyword, page=payload.page, page_size=payload.page_size, include_secluded=False)
        return {"code": 200, "data": _minimal_player_lookup_payload(result, telegram_user["id"])}

    @user_router.post("/api/gift")
    async def xiuxian_gift_api(payload: GiftPayload):
        def _work():
            telegram_user = _verify_user_from_init_data(payload.init_data)
            result = gift_spirit_stone(telegram_user["id"], payload.target_tg, payload.amount)
            return telegram_user, result, _with_result_core_bundle(telegram_user["id"], result)

        telegram_user, result, data = await run_in_threadpool(_work)
        await _notify_achievement_unlocks(result.get("achievement_unlocks"))
        return {"code": 200, "data": data}

    @user_router.post("/api/gift/item")
    def xiuxian_item_gift_api(payload: ItemGiftPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        result = gift_inventory_item(
            telegram_user["id"],
            payload.target_tg,
            payload.item_kind,
            payload.item_ref_id,
            payload.quantity,
        )
        return {"code": 200, "data": _with_result_core_bundle(telegram_user["id"], result)}

    @user_router.post("/api/journal")
    def xiuxian_journal_api(payload: InitDataPayload):
        telegram_user = _verify_user_from_init_data(payload.init_data)
        return {"code": 200, "data": list_recent_journals(telegram_user["id"])}

    @user_router.post("/api/leaderboard")
    async def xiuxian_leaderboard_api(payload: LeaderboardPayload):
        await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        result = await run_in_threadpool(build_leaderboard, payload.kind, payload.page)
        return {"code": 200, "data": result}

    @user_router.get("/api/shop")
    def xiuxian_public_shop_api():
        return {"code": 200, "data": list_public_shop_items()}

    @admin_router.post("/bootstrap")
    async def xiuxian_admin_bootstrap(payload: AdminBootstrapPayload):
        def _admin_bootstrap_core():
            admin_user = _verify_admin_credential(payload.token, payload.init_data)
            _ensure_seed_data_throttled()
            return {
                "admin_user": admin_user,
                "settings": update_xiuxian_settings({}),
                "pill_type_options": list_pill_type_options(),
                "artifacts": list_artifacts(),
                "pills": list_pills(),
                "talismans": list_talismans(),
                "techniques": list_techniques(),
                "official_shop": list_shop_items(official_only=True, include_disabled=True),
                **_admin_world_snapshot(),
            }

        data = await run_in_threadpool(_admin_bootstrap_core)
        data["player_search"] = await _admin_player_search_payload(
            payload.player_query,
            page=max(int(payload.player_page or 1), 1),
            page_size=max(int(payload.player_page_size or 10), 1),
        )
        return {
            "code": 200,
            "data": data,
        }

    @admin_router.get("/accounts")
    async def xiuxian_admin_accounts(
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

        def _parse_filter(value: str) -> bool | None:
            normalized = str(value or "").strip().lower()
            if not normalized:
                return None
            return normalized in {"1", "true", "yes", "on", "bound", "enabled"}

        data = await run_in_threadpool(
            list_xiuxian_web_accounts,
            q,
            bound=_parse_filter(bound),
            enabled=_parse_filter(enabled),
            page=page,
            page_size=page_size,
        )
        return {"code": 200, "data": data}

    @admin_router.post("/accounts/{account_id}/state")
    async def xiuxian_admin_account_state(account_id: int, payload: AdminGameAccountStatePayload, request: Request):
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
    async def xiuxian_admin_account_unbind(account_id: int, request: Request):
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
    async def xiuxian_admin_account_revoke_sessions(account_id: int, request: Request):
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
    async def xiuxian_settings_api(payload: AdminSettingPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(_verify_admin_credential, token, init_data)
        patch = {key: value for key, value in payload.model_dump().items() if value is not None}
        patch = await _resolve_notice_group_settings_patch(patch)
        settings = await run_in_threadpool(update_xiuxian_settings, patch)
        if {
            "shop_notice_group_id",
            "auction_notice_group_id",
            "arena_notice_group_id",
            "event_summary_interval_minutes",
        } & set(patch):
            _queue_event_summary_refresh(delay_seconds=0.2, force_create=True)
        return {"code": 200, "data": settings}

    @admin_router.post("/event-summary/refresh")
    async def xiuxian_event_summary_refresh_api(payload: EventSummaryRefreshPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(_verify_admin_credential, token, init_data)
        target_chat_ids: set[int] = set()
        raw_chat_id = payload.chat_id
        if str(raw_chat_id or "").strip():
            resolved_chat_id = await _resolve_notice_group_reference_to_chat_id(raw_chat_id, raise_on_failure=True)
            if not resolved_chat_id:
                raise HTTPException(status_code=400, detail="无法解析目标群聊，请填写群 ID、@username 或 t.me 地址。")
            target_chat_ids.add(int(resolved_chat_id))
        else:
            target_chat_ids = await _configured_event_summary_chat_ids()
            if not target_chat_ids:
                raise HTTPException(status_code=400, detail="请先配置通知群，或手动填写一个群 ID / 地址。")
        await _refresh_all_event_summaries(
            target_chat_ids,
            force_snapshot_refresh=True,
            force_create=bool(payload.force_create),
            constrain_to_snapshot=False,
        )
        return {
            "code": 200,
            "data": {
                "target_chat_ids": sorted(target_chat_ids),
                "target_count": len(target_chat_ids),
            },
        }

    @admin_router.post("/error-logs")
    def xiuxian_error_logs_api(payload: ErrorLogQueryPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        return {
            "code": 200,
            "data": list_error_logs(
                limit=payload.limit,
                tg=payload.tg,
                level=payload.level,
                keyword=payload.keyword,
            ),
        }

    @admin_router.post("/upload-image")
    async def xiuxian_admin_upload_image_api(
        request: Request,
        folder: str = Form("admin"),
        file: UploadFile = File(...),
    ):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(_verify_admin_credential, token, init_data)
        result = await _save_uploaded_image(file, f"admin/{folder}", str(request.base_url))
        return {"code": 200, "data": result}

    @admin_router.post("/upload-permission/grant")
    def xiuxian_admin_grant_upload_permission_api(payload: UploadPermissionPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        if is_admin_user_id(payload.tg):
            return {"code": 200, "data": {"tg": payload.tg, "granted": True, "builtin": True}}
        grant_image_upload_permission(payload.tg)
        return {"code": 200, "data": {"tg": payload.tg, "granted": True, "builtin": False}}

    @admin_router.post("/upload-permission/revoke")
    def xiuxian_admin_revoke_upload_permission_api(payload: UploadPermissionPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        removed = revoke_image_upload_permission(payload.tg)
        return {"code": 200, "data": {"tg": payload.tg, "removed": removed}}

    @admin_router.post("/title")
    def xiuxian_title_api(payload: TitlePayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        return {"code": 200, "data": sync_title_by_name(**payload.model_dump())}

    @admin_router.patch("/title/{title_id}")
    def xiuxian_patch_title_api(title_id: int, payload: TitlePayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = patch_title(title_id, **payload.model_dump())
        if result is None:
            raise HTTPException(status_code=404, detail="Title not found")
        return {"code": 200, "data": result}

    @admin_router.post("/title/grant")
    def xiuxian_grant_title_api(payload: TitleGrantPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = grant_title_to_user(payload.tg, payload.title_id, source="admin", equip=payload.equip)
        return {"code": 200, "data": result}

    @admin_router.post("/achievement")
    def xiuxian_achievement_api(payload: AchievementPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        return {"code": 200, "data": create_achievement(**payload.model_dump())}

    @admin_router.patch("/achievement/{achievement_id}")
    def xiuxian_patch_achievement_api(achievement_id: int, payload: AchievementPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = patch_achievement(achievement_id, **payload.model_dump())
        if result is None:
            raise HTTPException(status_code=404, detail="Achievement not found")
        return {"code": 200, "data": result}

    @admin_router.post("/achievement/progress")
    async def xiuxian_achievement_progress_api(payload: AchievementProgressPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        def _record_progress():
            _verify_admin_credential(token, init_data)
            return record_achievement_progress(payload.tg, payload.increments, source=payload.source or "admin")

        result = await run_in_threadpool(_record_progress)
        await _notify_achievement_unlocks(result.get("unlocks"))
        return {"code": 200, "data": result}

    @admin_router.post("/artifact")
    def xiuxian_artifact_api(payload: ArtifactPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        artifact = create_artifact(**payload.model_dump())
        return {"code": 200, "data": artifact}

    @admin_router.patch("/artifact/{artifact_id}")
    def xiuxian_artifact_patch_api(artifact_id: int, payload: ArtifactPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = patch_artifact(artifact_id, **payload.model_dump())
        if result is None:
            raise HTTPException(status_code=404, detail="法宝不存在")
        return {"code": 200, "data": result}

    @admin_router.post("/pill")
    def xiuxian_pill_api(payload: PillPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        pill = create_pill(**payload.model_dump())
        return {"code": 200, "data": pill}

    @admin_router.patch("/pill/{pill_id}")
    def xiuxian_pill_patch_api(pill_id: int, payload: PillPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = patch_pill(pill_id, **payload.model_dump())
        if result is None:
            raise HTTPException(status_code=404, detail="丹药不存在")
        return {"code": 200, "data": result}

    @admin_router.post("/talisman")
    def xiuxian_talisman_api(payload: TalismanPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        talisman = create_talisman(**payload.model_dump())
        return {"code": 200, "data": talisman}

    @admin_router.patch("/talisman/{talisman_id}")
    def xiuxian_talisman_patch_api(talisman_id: int, payload: TalismanPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = patch_talisman(talisman_id, **payload.model_dump())
        if result is None:
            raise HTTPException(status_code=404, detail="符箓不存在")
        return {"code": 200, "data": result}

    @admin_router.post("/technique")
    def xiuxian_technique_api(payload: TechniquePayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        technique = create_technique(**payload.model_dump())
        return {"code": 200, "data": technique}

    @admin_router.patch("/technique/{technique_id}")
    def xiuxian_technique_patch_api(technique_id: int, payload: TechniquePayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = patch_technique(technique_id, **payload.model_dump())
        if result is None:
            raise HTTPException(status_code=404, detail="功法不存在")
        return {"code": 200, "data": result}

    @admin_router.post("/artifact-set")
    def xiuxian_artifact_set_api(payload: ArtifactSetPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        return {"code": 200, "data": create_artifact_set(**payload.model_dump())}

    @admin_router.patch("/artifact-set/{artifact_set_id}")
    def xiuxian_artifact_set_patch_api(artifact_set_id: int, payload: ArtifactSetPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = patch_artifact_set(artifact_set_id, **payload.model_dump())
        if result is None:
            raise HTTPException(status_code=404, detail="法宝套装不存在")
        return {"code": 200, "data": result}

    @admin_router.post("/sect")
    def xiuxian_sect_api(payload: SectPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        sect = create_sect_with_roles(
            name=payload.name,
            description=payload.description,
            image_url=payload.image_url,
            camp=payload.camp,
            min_realm_stage=payload.min_realm_stage,
            min_realm_layer=payload.min_realm_layer,
            min_stone=payload.min_stone,
            min_bone=payload.min_bone,
            min_comprehension=payload.min_comprehension,
            min_divine_sense=payload.min_divine_sense,
            min_fortune=payload.min_fortune,
            min_willpower=payload.min_willpower,
            min_charisma=payload.min_charisma,
            min_karma=payload.min_karma,
            min_body_movement=payload.min_body_movement,
            min_combat_power=payload.min_combat_power,
            attack_bonus=payload.attack_bonus,
            defense_bonus=payload.defense_bonus,
            duel_rate_bonus=payload.duel_rate_bonus,
            cultivation_bonus=payload.cultivation_bonus,
            fortune_bonus=payload.fortune_bonus,
            body_movement_bonus=payload.body_movement_bonus,
            salary_min_stay_days=payload.salary_min_stay_days,
            entry_hint=payload.entry_hint,
            roles=[item.model_dump() for item in payload.roles],
        )
        return {"code": 200, "data": sect}

    @admin_router.patch("/sect/{sect_id}")
    def xiuxian_patch_sect_api(sect_id: int, payload: SectPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = patch_sect(
            sect_id,
            name=payload.name,
            description=payload.description,
            image_url=payload.image_url,
            camp=payload.camp,
            min_realm_stage=payload.min_realm_stage,
            min_realm_layer=payload.min_realm_layer,
            min_stone=payload.min_stone,
            min_bone=payload.min_bone,
            min_comprehension=payload.min_comprehension,
            min_divine_sense=payload.min_divine_sense,
            min_fortune=payload.min_fortune,
            min_willpower=payload.min_willpower,
            min_charisma=payload.min_charisma,
            min_karma=payload.min_karma,
            min_body_movement=payload.min_body_movement,
            min_combat_power=payload.min_combat_power,
            attack_bonus=payload.attack_bonus,
            defense_bonus=payload.defense_bonus,
            duel_rate_bonus=payload.duel_rate_bonus,
            cultivation_bonus=payload.cultivation_bonus,
            fortune_bonus=payload.fortune_bonus,
            body_movement_bonus=payload.body_movement_bonus,
            salary_min_stay_days=payload.salary_min_stay_days,
            entry_hint=payload.entry_hint,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="宗门不存在")
        result["roles"] = replace_sect_roles(sect_id, [item.model_dump() for item in payload.roles])
        return {"code": 200, "data": result}

    @admin_router.post("/sect/role")
    def xiuxian_sect_role_assign_api(payload: SectRoleAssignPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        return {"code": 200, "data": set_user_sect_role(payload.tg, payload.sect_id, payload.role_key)}

    @admin_router.post("/material")
    def xiuxian_material_api(payload: MaterialPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        return {"code": 200, "data": create_material(**payload.model_dump())}

    @admin_router.patch("/material/{material_id}")
    def xiuxian_material_patch_api(material_id: int, payload: MaterialPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = patch_material(material_id, **payload.model_dump())
        if result is None:
            raise HTTPException(status_code=404, detail="材料不存在")
        return {"code": 200, "data": result}

    @admin_router.post("/recipe")
    def xiuxian_recipe_api(payload: RecipePayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        recipe = create_recipe_with_ingredients(
            name=payload.name,
            recipe_kind=payload.recipe_kind,
            result_kind=payload.result_kind,
            result_ref_id=payload.result_ref_id,
            result_quantity=payload.result_quantity,
            base_success_rate=payload.base_success_rate,
            broadcast_on_success=payload.broadcast_on_success,
            ingredients=[item.model_dump() for item in payload.ingredients],
        )
        return {"code": 200, "data": recipe}

    @admin_router.patch("/recipe/{recipe_id}")
    def xiuxian_recipe_patch_api(recipe_id: int, payload: RecipePayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        recipe = patch_recipe_with_ingredients(
            recipe_id,
            name=payload.name,
            recipe_kind=payload.recipe_kind,
            result_kind=payload.result_kind,
            result_ref_id=payload.result_ref_id,
            result_quantity=payload.result_quantity,
            base_success_rate=payload.base_success_rate,
            broadcast_on_success=payload.broadcast_on_success,
            ingredients=[item.model_dump() for item in payload.ingredients],
        )
        return {"code": 200, "data": recipe}

    @admin_router.post("/scene")
    def xiuxian_scene_api(payload: ScenePayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        scene = create_scene_with_drops(
            name=payload.name,
            description=payload.description,
            image_url=payload.image_url,
            max_minutes=payload.max_minutes,
            min_realm_stage=payload.min_realm_stage,
            min_realm_layer=payload.min_realm_layer,
            min_combat_power=payload.min_combat_power,
            event_pool=[item.model_dump() for item in payload.event_pool],
            drops=[item.model_dump() for item in payload.drops],
        )
        return {"code": 200, "data": scene}

    @admin_router.patch("/scene/{scene_id}")
    def xiuxian_scene_patch_api(scene_id: int, payload: ScenePayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        scene = patch_scene_with_drops(
            scene_id,
            name=payload.name,
            description=payload.description,
            image_url=payload.image_url,
            max_minutes=payload.max_minutes,
            min_realm_stage=payload.min_realm_stage,
            min_realm_layer=payload.min_realm_layer,
            min_combat_power=payload.min_combat_power,
            event_pool=[item.model_dump() for item in payload.event_pool],
            drops=[item.model_dump() for item in payload.drops],
        )
        return {"code": 200, "data": scene}

    @admin_router.post("/encounter")
    def xiuxian_encounter_api(payload: EncounterPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        encounter = create_encounter_template(**payload.model_dump())
        return {"code": 200, "data": encounter}

    @admin_router.patch("/encounter/{encounter_id}")
    def xiuxian_encounter_patch_api(encounter_id: int, payload: EncounterPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        encounter = patch_encounter_template(encounter_id, **payload.model_dump())
        if encounter is None:
            raise HTTPException(status_code=404, detail="Encounter not found")
        return {"code": 200, "data": encounter}

    @admin_router.post("/encounter/dispatch")
    async def xiuxian_encounter_dispatch_api(payload: EncounterDispatchPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")

        def _spawn_encounter():
            _verify_admin_credential(token, init_data)
            chat_id = int(payload.group_chat_id or _main_group_chat_id() or 0)
            if not chat_id:
                raise HTTPException(status_code=400, detail="当前未配置可投放奇遇的群组。")
            return spawn_group_encounter(chat_id, template_id=payload.template_id)

        encounter_payload = await run_in_threadpool(_spawn_encounter)
        message_payload = await _push_group_encounter_notice(encounter_payload)
        return {"code": 200, "data": {"encounter": encounter_payload, "message": message_payload}}

    @admin_router.post("/boss/world/spawn")
    async def xiuxian_admin_world_boss_spawn_api(payload: BossWorldSpawnPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        def _spawn_world_boss():
            _verify_admin_credential(token, init_data)
            return spawn_world_boss(payload.boss_id)

        result = await run_in_threadpool(_spawn_world_boss)
        instance = result.get("instance") or {}
        text = instance.get("broadcast_text")
        chat_id = int(instance.get("broadcast_chat_id") or 0)
        message_payload = None
        if text and chat_id:
            sent = await _send_message(bot, chat_id, text, persistent=True)
            message_payload = {"chat_id": chat_id, "message_id": int(sent.id)}
        return {"code": 200, "data": {"world_boss": result, "message": message_payload}}

    @admin_router.patch("/mentorship/{mentorship_id}")
    def xiuxian_admin_mentorship_patch_api(mentorship_id: int, payload: AdminSocialPatchPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = admin_patch_mentorship(
            mentorship_id,
            status=payload.status,
            bond_value=payload.bond_value,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="师徒关系不存在")
        return {"code": 200, "data": result}

    @admin_router.patch("/mentorship-request/{request_id}")
    def xiuxian_admin_mentorship_request_patch_api(request_id: int, payload: AdminSocialPatchPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = admin_patch_mentorship_request(request_id, status=payload.status)
        if result is None:
            raise HTTPException(status_code=404, detail="师徒请求不存在")
        return {"code": 200, "data": result}

    @admin_router.patch("/marriage/{marriage_id}")
    def xiuxian_admin_marriage_patch_api(marriage_id: int, payload: AdminSocialPatchPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = admin_patch_marriage(
            marriage_id,
            status=payload.status,
            bond_value=payload.bond_value,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="姻缘关系不存在")
        return {"code": 200, "data": result}

    @admin_router.patch("/marriage-request/{request_id}")
    def xiuxian_admin_marriage_request_patch_api(request_id: int, payload: AdminSocialPatchPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = admin_patch_marriage_request(request_id, status=payload.status)
        if result is None:
            raise HTTPException(status_code=404, detail="姻缘请求不存在")
        return {"code": 200, "data": result}

    @admin_router.post("/boss")
    def xiuxian_admin_boss_api(payload: BossPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        return {"code": 200, "data": create_boss_config(**payload.model_dump())}

    @admin_router.patch("/boss/{boss_id}")
    def xiuxian_admin_boss_patch_api(boss_id: int, payload: BossPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = patch_boss_config(boss_id, **payload.model_dump())
        if result is None:
            raise HTTPException(status_code=404, detail="Boss不存在")
        return {"code": 200, "data": result}

    @admin_router.post("/task")
    async def xiuxian_admin_task_api(payload: AdminTaskPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        def _create_admin_task():
            _verify_admin_credential(token, init_data)
            return create_bounty_task(
                actor_tg=None,
                title=payload.title,
                description=payload.description,
                task_scope=payload.task_scope,
                task_type=payload.task_type,
                question_text=payload.question_text,
                answer_text=payload.answer_text,
                image_url=payload.image_url,
                required_item_kind=payload.required_item_kind,
                required_item_ref_id=payload.required_item_ref_id,
                required_item_quantity=payload.required_item_quantity,
                requirement_metric_key=payload.requirement_metric_key,
                requirement_metric_target=payload.requirement_metric_target,
                reward_stone=payload.reward_stone,
                reward_cultivation=payload.reward_cultivation,
                reward_scale_mode=payload.reward_scale_mode,
                reward_item_kind=payload.reward_item_kind,
                reward_item_ref_id=payload.reward_item_ref_id,
                reward_item_quantity=payload.reward_item_quantity,
                max_claimants=payload.max_claimants,
                sect_id=payload.sect_id,
                active_in_group=payload.active_in_group,
                group_chat_id=payload.group_chat_id or _main_group_chat_id(),
            )

        task = await run_in_threadpool(_create_admin_task)
        if task.get("active_in_group"):
            task, push_warning = await _safe_push_task_to_group(task)
            if push_warning:
                task["push_warning"] = push_warning
        return {"code": 200, "data": task}

    @admin_router.post("/grant")
    def xiuxian_grant_api(payload: GrantPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = grant_item_to_user(payload.tg, payload.item_kind, payload.item_ref_id, payload.quantity)
        return {"code": 200, "data": result}

    @admin_router.post("/shop/official")
    async def xiuxian_official_shop_api(payload: OfficialShopPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = await run_in_threadpool(
            create_official_shop_listing,
            item_kind=payload.item_kind,
            item_ref_id=payload.item_ref_id,
            quantity=payload.quantity,
            price_stone=payload.price_stone,
            shop_name=payload.shop_name,
        )
        _queue_event_summary_refresh(delay_seconds=0.2, force_create=True)
        return {"code": 200, "data": result}

    @admin_router.patch("/shop/{item_id}")
    async def xiuxian_patch_shop_api(item_id: int, payload: OfficialShopPatchPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        patch = {key: value for key, value in payload.model_dump().items() if value is not None}
        result = await run_in_threadpool(patch_shop_listing, item_id, **patch)
        if result is None:
            raise HTTPException(status_code=404, detail="Shop item not found")
        _queue_event_summary_refresh(delay_seconds=0.2, force_create=True)
        return {"code": 200, "data": result}

    @admin_router.delete("/artifact/{artifact_id}")
    def xiuxian_delete_artifact_api(artifact_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_artifact(artifact_id):
            raise HTTPException(status_code=404, detail="Artifact not found")
        return {"code": 200, "data": {"deleted": True, "id": artifact_id}}

    @admin_router.delete("/artifact-set/{artifact_set_id}")
    def xiuxian_delete_artifact_set_api(artifact_set_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_artifact_set(artifact_set_id):
            raise HTTPException(status_code=404, detail="Artifact set not found")
        return {"code": 200, "data": {"deleted": True, "id": artifact_set_id}}

    @admin_router.delete("/pill/{pill_id}")
    def xiuxian_delete_pill_api(pill_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_pill(pill_id):
            raise HTTPException(status_code=404, detail="Pill not found")
        return {"code": 200, "data": {"deleted": True, "id": pill_id}}

    @admin_router.delete("/talisman/{talisman_id}")
    def xiuxian_delete_talisman_api(talisman_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_talisman(talisman_id):
            raise HTTPException(status_code=404, detail="Talisman not found")
        return {"code": 200, "data": {"deleted": True, "id": talisman_id}}

    @admin_router.delete("/technique/{technique_id}")
    def xiuxian_delete_technique_api(technique_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_technique(technique_id):
            raise HTTPException(status_code=404, detail="Technique not found")
        return {"code": 200, "data": {"deleted": True, "id": technique_id}}

    @admin_router.delete("/title/{title_id}")
    def xiuxian_delete_title_api(title_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_title(title_id):
            raise HTTPException(status_code=404, detail="Title not found")
        return {"code": 200, "data": {"deleted": True, "id": title_id}}

    @admin_router.delete("/achievement/{achievement_id}")
    def xiuxian_delete_achievement_api(achievement_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_achievement(achievement_id):
            raise HTTPException(status_code=404, detail="Achievement not found")
        return {"code": 200, "data": {"deleted": True, "id": achievement_id}}

    @admin_router.delete("/boss/{boss_id}")
    def xiuxian_delete_boss_api(boss_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_boss_config(boss_id):
            raise HTTPException(status_code=404, detail="Boss not found")
        return {"code": 200, "data": {"deleted": True, "id": boss_id}}

    @admin_router.delete("/sect/{sect_id}")
    def xiuxian_delete_sect_api(sect_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_sect(sect_id):
            raise HTTPException(status_code=404, detail="Sect not found")
        return {"code": 200, "data": {"deleted": True, "id": sect_id}}

    @admin_router.delete("/material/{material_id}")
    def xiuxian_delete_material_api(material_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_material(material_id):
            raise HTTPException(status_code=404, detail="Material not found")
        return {"code": 200, "data": {"deleted": True, "id": material_id}}

    @admin_router.delete("/recipe/{recipe_id}")
    def xiuxian_delete_recipe_api(recipe_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_recipe(recipe_id):
            raise HTTPException(status_code=404, detail="Recipe not found")
        return {"code": 200, "data": {"deleted": True, "id": recipe_id}}

    @admin_router.delete("/scene/{scene_id}")
    def xiuxian_delete_scene_api(scene_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_scene(scene_id):
            raise HTTPException(status_code=404, detail="Scene not found")
        return {"code": 200, "data": {"deleted": True, "id": scene_id}}

    @admin_router.delete("/encounter/{encounter_id}")
    def xiuxian_delete_encounter_api(encounter_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_encounter_template(encounter_id):
            raise HTTPException(status_code=404, detail="Encounter not found")
        return {"code": 200, "data": {"deleted": True, "id": encounter_id}}

    @admin_router.delete("/task/{task_id}")
    def xiuxian_delete_task_api(task_id: int, request: Request):
        _verify_admin_credential(request.headers.get("x-admin-token"), request.headers.get("x-telegram-init-data"))
        if not delete_task(task_id):
            raise HTTPException(status_code=404, detail="Task not found")
        return {"code": 200, "data": {"deleted": True, "id": task_id}}

    @admin_router.get("/players")
    async def xiuxian_admin_players_api(request: Request, q: str = "", page: int = 1, page_size: int = 10):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(_verify_admin_credential, token, init_data)
        result = await _admin_player_search_payload(q or None, page=page, page_size=page_size)
        return {"code": 200, "data": result}

    @admin_router.post("/system/reset-player-data")
    def xiuxian_admin_reset_player_data_api(request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        _verify_admin_credential(token, init_data)
        result = admin_clear_all_xiuxian_data()
        return {"code": 200, "data": result}

    @admin_router.get("/players/{tg}")
    async def xiuxian_admin_player_detail_api(tg: int, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(_verify_admin_credential, token, init_data)
        return {"code": 200, "data": await _admin_player_bundle_payload(tg)}

    @admin_router.patch("/players/{tg}")
    async def xiuxian_admin_player_patch_api(tg: int, payload: PlayerPatchPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        def _patch_player():
            _verify_admin_credential(token, init_data)
            patch = {key: value for key, value in payload.model_dump().items() if value is not None}
            result = admin_patch_player(tg, **patch)
            if result is None:
                raise HTTPException(status_code=404, detail="Player not found")
            create_journal(tg, "admin", "主人修改", f"主人修改了属性: {', '.join(patch.keys())}")

        await run_in_threadpool(_patch_player)
        return {"code": 200, "data": await _admin_player_bundle_payload(tg)}

    @admin_router.post("/players/{tg}/resource/grant")
    async def xiuxian_admin_player_grant_resource_api(tg: int, payload: PlayerResourceGrantPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        def _grant_resource():
            _verify_admin_credential(token, init_data)
            admin_grant_player_resource(
                tg,
                payload.item_kind,
                payload.item_ref_id,
                quantity=payload.quantity,
                equip=payload.equip,
            )
            create_journal(tg, "admin", "主人发放", f"主人发放了 {payload.item_kind}:{payload.item_ref_id}")

        await run_in_threadpool(_grant_resource)
        return {"code": 200, "data": await _admin_player_bundle_payload(tg)}

    @admin_router.post("/players/{tg}/resource/inventory")
    async def xiuxian_admin_player_inventory_api(tg: int, payload: PlayerInventoryPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        def _set_inventory():
            _verify_admin_credential(token, init_data)
            admin_set_player_inventory(
                tg,
                payload.item_kind,
                payload.item_ref_id,
                payload.quantity,
                bound_quantity=payload.bound_quantity,
            )
            create_journal(tg, "admin", "主人调包", f"主人调整了背包: {payload.item_kind}:{payload.item_ref_id}")

        await run_in_threadpool(_set_inventory)
        return {"code": 200, "data": await _admin_player_bundle_payload(tg)}

    @admin_router.post("/players/{tg}/resource/select")
    async def xiuxian_admin_player_select_resource_api(tg: int, payload: PlayerSelectionPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        def _set_selection():
            _verify_admin_credential(token, init_data)
            admin_set_player_selection(tg, payload.selection_kind, payload.item_ref_id)
            target = f"{payload.selection_kind}:{payload.item_ref_id or 0}"
            create_journal(tg, "admin", "主人设定", f"主人切换了当前配置: {target}")

        await run_in_threadpool(_set_selection)
        return {"code": 200, "data": await _admin_player_bundle_payload(tg)}

    @admin_router.post("/players/{tg}/resource/revoke")
    async def xiuxian_admin_player_revoke_resource_api(tg: int, payload: PlayerRevokePayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        def _revoke_resource():
            _verify_admin_credential(token, init_data)
            admin_revoke_player_resource(tg, payload.item_kind, payload.item_ref_id)
            create_journal(tg, "admin", "主人回收", f"主人移除了 {payload.item_kind}:{payload.item_ref_id}")

        await run_in_threadpool(_revoke_resource)
        return {"code": 200, "data": await _admin_player_bundle_payload(tg)}

    @admin_router.post("/players/resource/batch")
    async def xiuxian_admin_player_batch_resource_api(payload: PlayerBatchResourcePayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")

        def _batch_update():
            _verify_admin_credential(token, init_data)
            return admin_batch_update_player_resource(
                payload.item_kind,
                payload.item_ref_id,
                payload.quantity,
                operation=payload.operation,
                equip=payload.equip,
            )

        result = await run_in_threadpool(_batch_update)
        if payload.announce_in_group:
            chat_id = _main_group_chat_id()
            if chat_id:
                action_label = "发放" if payload.operation == "grant" else "扣除"
                lines = [
                    "📣 批量物资调整",
                    f"主人已对全体修士批量{action_label}：{payload.item_kind}:{payload.item_ref_id} × {payload.quantity}",
                    f"成功 {result.get('success_count', 0)} 人，跳过 {result.get('skipped_count', 0)} 人，失败 {result.get('failed_count', 0)} 人。",
                ]
                asyncio.create_task(_send_message(bot, chat_id, "\n".join(lines), persistent=True))
        return {"code": 200, "data": result}

    app.include_router(user_router)
    app.include_router(admin_router)
