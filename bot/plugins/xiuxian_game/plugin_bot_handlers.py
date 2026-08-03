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

from bot import LOGGER, admin_p, api as api_config, bot, config, group, owner, owner_p, prefixes, user_p
from bot.func_helper.runtime import get_or_create_event_loop
from bot.func_helper.moderation import (
    ModerationServiceError,
    get_chat_member_details,
    normalize_telegram_member_badge_text,
    set_chat_member_tag,
    set_chat_member_title,
)
from bot.func_helper.msg_utils import callAnswer
from bot.plugins.sdk import (
    build_bottom_nav,
    public_url_root,
    verify_admin_credential,
    verify_telegram_user,
)
from bot.web.api.miniapp import is_admin_user_id
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
    build_spirit_stone_commissions,
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
from bot.plugins.xiuxian_game.features.miniapp_bundle import (
    build_fishing_cast_bundle_patch,
    build_bootstrap_core_bundle,
    build_deferred_profile_sections,
    build_full_profile_bundle,
    build_profile_section_bundle,
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
)
from bot.plugins.xiuxian_game.achievement_service import (
    ACHIEVEMENT_METRIC_PRESETS,
    format_reward_summary,
    record_achievement_progress,
)


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
FULL_BUNDLE_TTL = max(int(os.getenv("PIVKEYU_XIUXIAN_FULL_BUNDLE_TTL", "45") or 45), 5)
DEFERRED_BUNDLE_TTL = max(int(os.getenv("PIVKEYU_XIUXIAN_DEFERRED_BUNDLE_TTL", "45") or 45), 5)
DUEL_MESSAGE_REFRESH_CACHE: dict[int, float] = {}
DUEL_SETTLEMENT_CACHE: dict[int, dict[str, Any]] = {}
PENDING_DUEL_INVITES: dict[tuple[int, int], dict[str, Any]] = {}
MESSAGE_AUTO_DELETE_TASKS: dict[tuple[int, int], asyncio.Task] = {}
AUCTION_FINALIZE_TASKS: dict[int, asyncio.Task] = {}
ARENA_FINALIZE_TASKS: dict[int, asyncio.Task] = {}
EVENT_SUMMARY_MESSAGES: dict[int, int] = {}
DEFERRED_BUNDLE_TASKS: dict[tuple[Any, ...], asyncio.Task] = {}
DEFERRED_SECTION_TASKS: dict[tuple[Any, ...], asyncio.Task] = {}
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


def _ensure_xiuxian_bot_commands() -> None:
    for command_list in (user_p, admin_p, owner_p):
        existing = {item.command for item in command_list}
        for command in XIUXIAN_BOT_COMMANDS:
            if command.command not in existing:
                command_list.append(command)
                existing.add(command.command)


def _schedule_command_refresh(bot_instance) -> None:
    try:
        loop = get_or_create_event_loop()
        def _refresh_safe() -> None:
            # call_later 回调运行在事件循环线程；bot 若在 5s 内开始关停，
            # create_task 可能抛 RuntimeError，此处吞掉避免未捕获异常告警。
            try:
                loop.create_task(BotCommands.set_commands(client=bot_instance))
            except Exception as exc:
                LOGGER.debug(f"xiuxian command refresh skipped: {exc}")

        loop.call_later(5, _refresh_safe)
    except Exception as exc:
        LOGGER.debug(f"xiuxian command refresh skipped: {exc}")


def _register_command_dispatch(message, command_name: str, *, ttl_seconds: int = 30) -> bool:
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    message_id = getattr(message, "id", None)
    if chat_id is None or message_id is None:
        return True

    now = time.monotonic()
    expire_before = now - max(int(ttl_seconds), 1)
    stale_keys = [key for key, seen_at in COMMAND_DISPATCH_CACHE.items() if seen_at < expire_before]
    for key in stale_keys:
        COMMAND_DISPATCH_CACHE.pop(key, None)

    cache_key = (int(chat_id), int(message_id), str(command_name or "").strip().lower())
    if cache_key in COMMAND_DISPATCH_CACHE:
        return False

    COMMAND_DISPATCH_CACHE[cache_key] = now
    return True


def _command_slow_threshold_seconds() -> float:
    raw = os.getenv("PIVKEYU_XIUXIAN_COMMAND_SLOW_SECONDS", "2")
    try:
        return max(float(raw or 0), 0.5)
    except (TypeError, ValueError):
        return 2.0


def _log_slow_group_command(command_name: str, message, started_at: float, **segments: float) -> None:
    elapsed = time.perf_counter() - started_at
    if elapsed < _command_slow_threshold_seconds():
        return
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    message_id = getattr(message, "id", None)
    user_id = getattr(getattr(message, "from_user", None), "id", None)
    segment_text = " ".join(f"{name}={value:.3f}s" for name, value in segments.items())
    LOGGER.warning(
        f"xiuxian command slow command={command_name} chat={chat_id} user={user_id} "
        f"message={message_id} total={elapsed:.3f}s {segment_text}".rstrip()
    )


def _parse_xiuxian_rank_args(command_parts: Iterable[str] | None) -> tuple[str, int]:
    kind = "stone"
    page = 1
    for raw_part in command_parts or []:
        part = str(raw_part or "").strip()
        if not part:
            continue
        alias = XIUXIAN_RANK_KIND_ALIASES.get(part.lower()) or XIUXIAN_RANK_KIND_ALIASES.get(part)
        if alias:
            kind = alias
            continue
        try:
            page = max(int(part), 1)
        except ValueError:
            continue
    return kind, page


def _xiuxian_basic_guide_text(consented: bool) -> str:
    lines = [
        f"《{PLUGIN_NAME}》当前版本：v{PLUGIN_VERSION}",
        "基础玩法：",
        "1. 私聊发送 /xiuxian 入道，抽取灵根并建立角色档案。",
        "2. 通过吐纳、闭关、丹药、功法与法宝持续提升修为和战力。",
        "3. 用探索、任务、宗门、坊市和红包获取资源，逐步扩展养成路线。",
        "4. 群内可使用 /duel、/servitudeduel、/leitai、/caibu、/rob、/gift 与其他道友互动。",
        "5. 完整的背包、炼制、宗门与商店功能请从修仙面板进入。",
    ]
    if not consented:
        lines.append("现在还未入道，点击下方按钮即可正式踏上仙途。")
    return "\n".join(lines)


def _telegram_identity_payload(user: Any) -> dict[str, str]:
    first_name = str(getattr(user, "first_name", "") or "").strip()
    last_name = str(getattr(user, "last_name", "") or "").strip()
    username = str(getattr(user, "username", "") or "").strip().lstrip("@")
    display_name = " ".join(part for part in [first_name, last_name] if part).strip()
    payload: dict[str, str] = {}
    if display_name:
        payload["display_name"] = display_name
    if username:
        payload["username"] = username
    return payload


def _telegram_user_display_name(user: Any, fallback: str = "道友") -> str:
    first_name = str(getattr(user, "first_name", "") or "").strip()
    last_name = str(getattr(user, "last_name", "") or "").strip()
    display_name = " ".join(part for part in [first_name, last_name] if part).strip()
    if display_name:
        return display_name
    username = str(getattr(user, "username", "") or "").strip().lstrip("@")
    if username:
        return f"@{username}"
    user_id = int(getattr(user, "id", 0) or 0)
    return f"TG {user_id}" if user_id > 0 else fallback


async def _refresh_profile_identity_from_telegram(tg: int) -> dict[str, str] | None:
    try:
        telegram_user = await bot.get_users(int(tg))
    except Exception as exc:
        LOGGER.warning(f"xiuxian admin failed to refresh telegram profile {tg}: {exc}")
        return None

    payload = _telegram_identity_payload(telegram_user)
    if not payload:
        return None

    from bot.sql_helper.sql_xiuxian import upsert_profile

    await run_in_threadpool(upsert_profile, int(tg), **payload)
    return payload


def _merge_profile_identity(profile: dict[str, Any], identity: dict[str, str] | None) -> dict[str, Any]:
    if not identity:
        return profile

    merged = dict(profile)
    if identity.get("display_name"):
        merged["display_name"] = identity["display_name"]
    if identity.get("username"):
        merged["username"] = identity["username"]

    if merged.get("display_name"):
        merged["display_label"] = merged["display_name"]
    elif merged.get("username"):
        merged["display_label"] = f"@{merged['username']}"
    elif merged.get("tg"):
        merged["display_label"] = f"TG {merged['tg']}"
    return merged


async def _admin_player_bundle_payload(tg: int) -> dict[str, Any]:
    bundle = await run_in_threadpool(build_admin_player_detail, tg)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Player not found")
    identity = await _refresh_profile_identity_from_telegram(tg)
    bundle["profile"] = _merge_profile_identity(bundle.get("profile") or {}, identity)
    bundle["emby_account"] = await run_in_threadpool(get_emby_account, tg)
    return bundle


async def _admin_player_search_payload(
    query: str | None = None,
    *,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    result = await run_in_threadpool(search_xiuxian_players, query=query or None, page=page, page_size=page_size)
    items = result.get("items") or []
    identities = await asyncio.gather(
        *(_refresh_profile_identity_from_telegram(int(item["tg"])) for item in items),
        return_exceptions=True,
    )
    result["items"] = [
        _merge_profile_identity(
            item,
            None if isinstance(identity, Exception) else identity,
        )
        for item, identity in zip(items, identities)
    ]
    return result


def _upsert_xiuxian_profile_identity(user: dict[str, Any]) -> None:
    display_name = " ".join(part for part in [user.get("first_name"), user.get("last_name")] if part).strip()
    upsert_fields = {}
    if display_name:
        upsert_fields["display_name"] = display_name
    if user.get("username"):
        upsert_fields["username"] = str(user["username"]).lstrip("@")
    if upsert_fields:
        from bot.sql_helper.sql_xiuxian import upsert_profile

        upsert_profile(int(user["id"]), **upsert_fields)


def _verify_user_from_init_data(init_data: str) -> dict[str, Any]:
    return verify_telegram_user(init_data, on_verified=_upsert_xiuxian_profile_identity)


def _verify_admin_credential(token: str | None, init_data: str | None) -> dict[str, Any]:
    return verify_admin_credential(token, init_data)


def _operation_name_from_request(request: Request) -> str:
    path = str(request.url.path or "").strip()
    if not path:
        return "未知操作"
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[-1].isdigit():
        parts = parts[:-1]
    if not parts:
        return path
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[-1]


def _extract_init_data_from_body_bytes(content_type: str, body: bytes) -> str | None:
    if not body:
        return None
    if "application/json" in content_type:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        return str(payload.get("init_data") or "").strip() or None
    if "application/x-www-form-urlencoded" in content_type:
        parsed = parse_qs(body.decode("utf-8", errors="ignore"), keep_blank_values=True)
        values = parsed.get("init_data")
        if values:
            return str(values[0] or "").strip() or None
    return None


def _actor_from_request(request: Request) -> dict[str, Any]:
    scope = "admin" if "/admin-api/" in str(request.url.path or "") else "user"
    init_data = getattr(request.state, "xiuxian_init_data", None)
    if not init_data:
        init_data = request.headers.get("x-telegram-init-data")
    if not init_data:
        return {"scope": scope}
    try:
        user = verify_telegram_user(init_data)
    except Exception:
        return {"scope": scope}
    return {
        "scope": scope,
        "tg": int(user.get("id") or 0) or None,
        "username": str(user.get("username") or "").strip() or None,
        "display_name": str(user.get("first_name") or user.get("last_name") or "").strip() or None,
    }


def _record_request_error(request: Request, exc: Exception, *, status_code: int, level: str) -> None:
    try:
        actor = _actor_from_request(request)
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[:12000]
        create_error_log(
            tg=actor.get("tg"),
            username=actor.get("username"),
            display_name=actor.get("display_name"),
            scope=actor.get("scope") or "user",
            level=level,
            operation=_operation_name_from_request(request),
            method=request.method,
            path=str(request.url.path or "")[:255] or None,
            status_code=status_code,
            message=str(exc) or exc.__class__.__name__,
            detail=detail,
        )
    except Exception as log_exc:
        LOGGER.warning(f"xiuxian error log persist failed: {log_exc}")


def _can_user_upload_images(user_id: int) -> tuple[bool, str]:
    if is_admin_user_id(user_id):
        return True, ""

    settings = get_xiuxian_settings()
    if bool(settings.get("allow_non_admin_image_upload", False)):
        return True, ""

    if has_image_upload_permission(user_id):
        return True, ""

    return False, "当前未开放普通用户上传图片，请联系主人开启总开关或单独授权。"


def _sanitize_upload_folder(folder: str | None) -> str:
    raw = (folder or "misc").strip().replace("\\", "/")
    parts = []
    for part in raw.split("/"):
        cleaned = "".join(ch for ch in part.lower() if ch.isalnum() or ch in {"-", "_"})
        if cleaned:
            parts.append(cleaned)
    return "/".join(parts[:3]) or "misc"


def _public_url_root(base_url: str | None = None) -> str:
    return public_url_root(base_url)


def _resolve_group_image_source(image_url: str | None) -> str | Path | None:
    if not image_url:
        return None
    image_url = str(image_url).strip()
    if not image_url:
        return None
    upload_path = image_url
    if image_url.startswith("http://") or image_url.startswith("https://"):
        parsed = urlsplit(image_url)
        upload_path = parsed.path or image_url
        if not upload_path.startswith("/plugins/xiuxian/uploads/"):
            return image_url
    if upload_path.startswith("/plugins/xiuxian/uploads/"):
        relative_path = upload_path.removeprefix("/plugins/xiuxian/uploads/").strip("/")
        local_path = UPLOAD_DIR.joinpath(*[part for part in relative_path.split("/") if part])
        if local_path.exists():
            return str(local_path)
        public_root = _public_url_root()
        if public_root:
            return f"{public_root}{upload_path}"
    return image_url


async def _save_uploaded_image(file: UploadFile, folder: str, base_url: str | None = None) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    content_type = (file.content_type or "").lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="仅支持 jpg、png、webp、gif 图片格式")

    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }
        suffix = mapping.get(content_type, ".jpg")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="上传的图片不能为空")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="图片大小不能超过 8MB")

    subdir = _sanitize_upload_folder(folder)
    target_dir = UPLOAD_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{suffix}"
    target = target_dir / filename
    target.write_bytes(payload)
    relative = Path(subdir) / filename
    relative_url = f"/plugins/xiuxian/uploads/{relative.as_posix()}"
    public_url = _public_url_root(base_url)
    return {
        "name": filename,
        "size": len(payload),
        "url": f"{public_url}{relative_url}" if public_url else relative_url,
        "relative_url": relative_url,
    }


def _format_profile_text(payload: dict[str, Any]) -> str:
    profile = payload["profile"]
    root_text = format_root(profile)
    effective_stats = payload.get("effective_stats") or {}
    equipped_artifacts = payload.get("equipped_artifacts") or []
    equip_limit = int(payload.get("settings", {}).get("artifact_equip_limit", 1) or 1)
    artifact_name = "、".join(item["name"] for item in equipped_artifacts) if equipped_artifacts else "暂无已装备法宝"
    talisman_name = payload["active_talisman"]["name"] if payload.get("active_talisman") else "暂无生效符箓"
    technique_name = payload["current_technique"]["name"] if payload.get("current_technique") else "暂无参悟功法"
    title_name = payload["current_title"]["name"] if payload.get("current_title") else "未佩戴称号"
    progress = payload.get("progress", {})
    threshold = progress.get("threshold", 0)
    remaining_text = progress.get("remaining", 0)
    combat_power = int(payload.get("combat_power") or 0)
    return (
        f"**修仙总览**\n"
        f"灵根：{_md_escape(root_text)}\n"
        f"灵根品质：{_md_escape(profile.get('root_quality') or '灵根未定')}\n"
        f"境界：`{profile['realm_stage']}{profile['realm_layer']}层`\n"
        f"修为：`{profile['cultivation']} / {threshold}`\n"
        f"距离下一层：`{remaining_text}`\n"
        f"灵石：`{profile['spiritual_stone']}`\n"
        f"丹毒：`{profile['dan_poison']}/100`\n"
        f"根骨 / 悟性 / 神识 / 机缘：`{effective_stats.get('bone', profile.get('bone', 0))} / {effective_stats.get('comprehension', profile.get('comprehension', 0))} / {effective_stats.get('divine_sense', profile.get('divine_sense', 0))} / {effective_stats.get('fortune', profile.get('fortune', 0))}`\n"
        f"气血 / 真元 / 身法：`{effective_stats.get('qi_blood', profile.get('qi_blood', 0))} / {effective_stats.get('true_yuan', profile.get('true_yuan', 0))} / {effective_stats.get('body_movement', profile.get('body_movement', 0))}`\n"
        f"攻击 / 防御 / 战力：`{effective_stats.get('attack_power', profile.get('attack_power', 0))} / {effective_stats.get('defense_power', profile.get('defense_power', 0))} / {combat_power}`\n"
        f"法宝：{_md_escape(artifact_name)} `({len(equipped_artifacts)}/{equip_limit})`\n"
        f"符箓：{_md_escape(talisman_name)}\n"
        f"功法：{_md_escape(technique_name)}\n"
        f"称号：{_md_escape(title_name)}"
    )


def _md_escape(value: Any) -> str:
    return MARKDOWN_ESCAPE_PATTERN.sub(r"\\\1", str(value or ""))


def _message_jump_url(chat_id: int | None, message_id: int | None) -> str | None:
    try:
        resolved_chat_id = int(chat_id or 0)
        resolved_message_id = int(message_id or 0)
    except (TypeError, ValueError):
        return None
    raw_chat_id = str(resolved_chat_id)
    if resolved_message_id <= 0 or not raw_chat_id.startswith("-100"):
        return None
    return f"https://t.me/c/{raw_chat_id[4:]}/{resolved_message_id}"


def _message_jump_link(label: str, chat_id: int | None, message_id: int | None) -> str:
    url = _message_jump_url(chat_id, message_id)
    safe_label = _md_escape(label)
    return f"[{safe_label}]({url})" if url else safe_label


def _format_notice_card(title: str, *, emoji: str, lines: Iterable[str], footer: str | None = None) -> str:
    rows = [f"{emoji} **{_md_escape(title)}**"]
    rows.extend(str(line).strip() for line in lines if str(line or "").strip())
    if footer:
        rows.extend(["", str(footer).strip()])
    return "\n".join(rows)


# 群播报卡片分隔线(与斗罗/斗破播报同款样式)
_MD_BROADCAST_DIVIDER = "━" * 18


def _format_broadcast_card(title: str, *, emoji: str, lines: Iterable[str], footer: str | None = None) -> str:
    """带分隔线边框的群播报卡片:图标标题 + 分隔线 + 正文 + 分隔线。"""
    rows = [f"{emoji} **{_md_escape(title)}** {emoji}", _MD_BROADCAST_DIVIDER]
    rows.extend(str(line).strip() for line in lines if str(line or "").strip())
    if footer:
        rows.extend([_MD_BROADCAST_DIVIDER, str(footer).strip()])
    else:
        rows.append(_MD_BROADCAST_DIVIDER)
    return "\n".join(rows)


def _format_layer_upgrade_line(upgraded_layers: list[int] | None, *, label: str = "层数提升") -> str:
    layers = [int(layer) for layer in (upgraded_layers or []) if int(layer) > 0]
    if not layers:
        return ""
    return f"🪜 {label}：{' → '.join(f'`{layer}层`' for layer in layers)}"


def _format_curse_event_line(curse_event: dict[str, Any] | None) -> str:
    if not isinstance(curse_event, dict):
        return ""
    message = str(curse_event.get("message") or "").strip()
    if not message:
        return ""
    return f"☠️ {_md_escape(message)}"


def _format_group_profile_showcase(payload: dict[str, Any], fallback_name: str | None = None) -> str:
    profile = payload["profile"]
    effective_stats = payload.get("effective_stats") or {}
    progress = payload.get("progress") or {}
    equipped_artifacts = payload.get("equipped_artifacts") or []
    active_talisman = payload.get("active_talisman") or {}
    current_technique = payload.get("current_technique") or {}
    current_title = payload.get("current_title") or {}
    display_name = (
        profile.get("display_name_with_title")
        or profile.get("display_label")
        or profile.get("display_name")
        or fallback_name
        or f"TG {profile['tg']}"
    )
    artifact_lines = [f"· {item['name']}" for item in equipped_artifacts[:3]]
    if len(equipped_artifacts) > 3:
        artifact_lines.append(f"· 其余 {len(equipped_artifacts) - 3} 件")
    if not artifact_lines:
        artifact_lines.append("· 暂无已装备法宝")
    retreat_text = "闭关中" if payload.get("capabilities", {}).get("is_in_retreat") else "自在行走"
    if profile.get("retreat_end_at") and payload.get("capabilities", {}).get("is_in_retreat"):
        retreat_end_at = _parse_shanghai_datetime(profile.get("retreat_end_at"))
        retreat_display = retreat_end_at.strftime("%m-%d %H:%M") if retreat_end_at else str(profile.get("retreat_end_at"))
        retreat_text = f"闭关中，预计 {retreat_display} 出关"
    return _format_notice_card(
        "修仙名帖",
        emoji="🌌",
        lines=[
            f"👤 道友：{_md_escape(display_name)}",
            f"🌱 灵根：{_md_escape(format_root(profile))}",
            f"🏯 境界：{_md_escape(str(profile['realm_stage']) + str(profile['realm_layer']) + '层')}",
            f"📈 当前修为：`{profile['cultivation']} / {progress.get('threshold', 0)}`",
            f"⏭️ 距下一层：`{progress.get('remaining', 0)}`",
            f"💎 灵石：`{profile['spiritual_stone']}`",
            f"☠️ 丹毒：`{profile['dan_poison']}/100`",
            f"🏷️ 称号：{_md_escape(current_title.get('name') or '未佩戴称号')}",
            f"⚔️ 战斗：`攻 {effective_stats.get('attack_power', profile.get('attack_power', 0))}` ｜ `防 {effective_stats.get('defense_power', profile.get('defense_power', 0))}` ｜ `战力 {payload.get('combat_power', 0)}`",
            f"🧭 资质：`根骨 {effective_stats.get('bone', profile.get('bone', 0))}` ｜ `悟性 {effective_stats.get('comprehension', profile.get('comprehension', 0))}` ｜ `神识 {effective_stats.get('divine_sense', profile.get('divine_sense', 0))}`",
            f"✨ 机缘向：`机缘 {effective_stats.get('fortune', profile.get('fortune', 0))}` ｜ `魅力 {effective_stats.get('charisma', profile.get('charisma', 0))}`",
            "🛡️ 法宝：",
            *[_md_escape(line) for line in artifact_lines],
            f"🧿 符箓：{_md_escape(active_talisman.get('name') or '暂无生效符箓')}",
            f"📜 功法：{_md_escape(current_technique.get('name') or '暂无参悟功法')}",
            f"🕰️ 状态：{_md_escape(retreat_text)}",
        ],
    )


def _build_bottom_nav() -> list[dict[str, str]]:
    return build_bottom_nav()


def _configured_group_chat_ids() -> list[int]:
    if group is None:
        return []
    raw_groups = [group] if isinstance(group, (str, int)) else group
    chat_ids: list[int] = []
    seen: set[int] = set()
    for item in raw_groups or []:
        try:
            chat_id = int(str(item or "").strip() or "0")
        except (TypeError, ValueError):
            continue
        if chat_id and chat_id not in seen:
            seen.add(chat_id)
            chat_ids.append(chat_id)
    return chat_ids


def _main_group_chat_id() -> int | None:
    chat_ids = _configured_group_chat_ids()
    return chat_ids[0] if chat_ids else None


def _encounter_auto_trigger_enabled(chat_id: int | None) -> bool:
    resolved_chat_id = int(chat_id or 0)
    if not resolved_chat_id:
        return False
    cached = ENCOUNTER_AUTO_CHAT_STATE.get(resolved_chat_id)
    if cached is not None:
        return cached

    allowed_chat_ids = set(_configured_group_chat_ids())
    main_chat_id = _main_group_chat_id()
    if main_chat_id:
        allowed_chat_ids.add(int(main_chat_id))

    enabled = resolved_chat_id in allowed_chat_ids or get_latest_group_encounter_time(resolved_chat_id) is not None
    ENCOUNTER_AUTO_CHAT_STATE[resolved_chat_id] = enabled
    return enabled


def _encounter_auto_dispatch_chat_ids(settings: dict[str, Any] | None = None) -> list[int]:
    source = settings if isinstance(settings, dict) else get_xiuxian_settings()
    chat_ids = _configured_group_chat_ids()
    last_dates = source.get("encounter_auto_dispatch_last_dates") if isinstance(source, dict) else {}
    if isinstance(last_dates, dict):
        for raw_chat_id in last_dates.keys():
            try:
                chat_id = int(str(raw_chat_id or "").strip() or "0")
            except (TypeError, ValueError):
                continue
            if chat_id:
                chat_ids.append(chat_id)

    deduped: list[int] = []
    seen: set[int] = set()
    for chat_id in chat_ids:
        if chat_id in seen:
            continue
        seen.add(chat_id)
        if _encounter_auto_trigger_enabled(chat_id):
            deduped.append(chat_id)
    return deduped


def _encounter_auto_dispatch_due(settings: dict[str, Any], now: datetime) -> bool:
    if not bool(settings.get("encounter_auto_dispatch_enabled", DEFAULT_SETTINGS.get("encounter_auto_dispatch_enabled", True))):
        return False
    try:
        hour = int(settings.get("encounter_auto_dispatch_hour", DEFAULT_SETTINGS.get("encounter_auto_dispatch_hour", 12)) or 0)
    except (TypeError, ValueError):
        hour = int(DEFAULT_SETTINGS.get("encounter_auto_dispatch_hour", 12))
    try:
        minute = int(settings.get("encounter_auto_dispatch_minute", DEFAULT_SETTINGS.get("encounter_auto_dispatch_minute", 0)) or 0)
    except (TypeError, ValueError):
        minute = int(DEFAULT_SETTINGS.get("encounter_auto_dispatch_minute", 0))
    hour = min(max(hour, 0), 23)
    minute = min(max(minute, 0), 59)
    return (now.hour, now.minute) >= (hour, minute)


def _encounter_auto_dispatch_last_date(settings: dict[str, Any], chat_id: int) -> str:
    raw_dates = settings.get("encounter_auto_dispatch_last_dates") if isinstance(settings, dict) else {}
    if not isinstance(raw_dates, dict):
        return ""
    return str(raw_dates.get(str(int(chat_id))) or raw_dates.get(int(chat_id)) or "").strip()


def _datetime_shanghai_day_key(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(SHANGHAI_TZ).date().isoformat()


def _latest_group_encounter_day_key(chat_id: int) -> str:
    return _datetime_shanghai_day_key(get_latest_group_encounter_time(int(chat_id)))


def _mark_encounter_auto_dispatch_done(chat_id: int, day_key: str) -> None:
    settings = get_xiuxian_settings()
    raw_dates = settings.get("encounter_auto_dispatch_last_dates")
    last_dates = dict(raw_dates) if isinstance(raw_dates, dict) else {}
    last_dates[str(int(chat_id))] = str(day_key)
    set_xiuxian_settings({"encounter_auto_dispatch_last_dates": last_dates})


async def _dispatch_due_group_encounters() -> None:
    settings = get_xiuxian_settings()
    now = datetime.now(SHANGHAI_TZ)
    if not _encounter_auto_dispatch_due(settings, now):
        return
    day_key = now.date().isoformat()
    for chat_id in _encounter_auto_dispatch_chat_ids(settings):
        if _encounter_auto_dispatch_last_date(settings, chat_id) == day_key:
            continue
        if _latest_group_encounter_day_key(chat_id) == day_key:
            _mark_encounter_auto_dispatch_done(chat_id, day_key)
            continue
        try:
            payload = spawn_group_encounter(chat_id)
            await _push_group_encounter_notice(payload)
            _mark_encounter_auto_dispatch_done(chat_id, day_key)
        except ValueError as exc:
            if _latest_group_encounter_day_key(chat_id) == day_key:
                _mark_encounter_auto_dispatch_done(chat_id, day_key)
                continue
            message = str(exc)
            if "没有可投放" in message:
                _mark_encounter_auto_dispatch_done(chat_id, day_key)
            LOGGER.warning(f"xiuxian encounter auto dispatch skipped chat={chat_id}: {exc}")
        except Exception as exc:
            LOGGER.warning(f"xiuxian encounter auto dispatch failed chat={chat_id}: {exc}")


def _notice_group_setting_key(scope: str) -> str | None:
    key_map = {
        "shop": "shop_notice_group_id",
        "auction": "auction_notice_group_id",
        "arena": "arena_notice_group_id",
    }
    return key_map.get(str(scope or "").strip().lower())


def _notice_group_cache_raw(value: Any) -> str:
    return str(value or "").strip()


def _cached_notice_group_chat_id(cache_key: str | None, raw_value: Any) -> int:
    if not cache_key:
        return 0
    cached = NOTICE_GROUP_RESOLUTION_CACHE.get(cache_key) or {}
    if str(cached.get("raw") or "") != _notice_group_cache_raw(raw_value):
        return 0
    try:
        return int(cached.get("chat_id") or 0)
    except (TypeError, ValueError):
        return 0


def _store_notice_group_chat_id(cache_key: str | None, raw_value: Any, chat_id: int) -> None:
    if not cache_key:
        return
    resolved_chat_id = int(chat_id or 0)
    if resolved_chat_id == 0:
        NOTICE_GROUP_RESOLUTION_CACHE.pop(cache_key, None)
        return
    NOTICE_GROUP_RESOLUTION_CACHE[cache_key] = {
        "raw": _notice_group_cache_raw(raw_value),
        "chat_id": resolved_chat_id,
    }


def _clear_notice_group_cache(cache_key: str | None) -> None:
    if cache_key:
        NOTICE_GROUP_RESOLUTION_CACHE.pop(cache_key, None)


def _notice_group_chat_id(
    scope: str,
    fallback_chat_id: int | None = None,
    *,
    allow_main_fallback: bool = True,
) -> int | None:
    key = _notice_group_setting_key(scope)
    settings = get_xiuxian_settings()
    raw_value = settings.get(key, 0) if key else 0
    raw_text = str(raw_value or "").strip()
    configured = 0
    if key:
        try:
            _username, configured = _parse_notice_group_reference(raw_value)
        except HTTPException:
            configured = 0
        cached = _cached_notice_group_chat_id(key, raw_value)
        if configured:
            _store_notice_group_chat_id(key, raw_value, configured)
            return configured
        if cached:
            return cached
        if raw_text and raw_text not in {"0", "None"}:
            return None
    if fallback_chat_id:
        return int(fallback_chat_id)
    if allow_main_fallback:
        return _main_group_chat_id()
    return None


def _parse_notice_group_reference(value: Any) -> tuple[str | None, int]:
    raw = str(value or "").strip()
    if not raw:
        return None, 0
    if re.fullmatch(r"-?\d+", raw):
        return None, int(raw)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,}", raw):
        return raw, 0
    if raw.startswith("@"):
        username = raw[1:].strip()
        if not username:
            raise HTTPException(status_code=400, detail="群聊地址不能为空，请填写群 ID、@username 或 t.me 地址。")
        return username, 0

    candidate = raw
    if re.match(r"^(?:t\.me|telegram\.me|www\.t\.me|www\.telegram\.me)/", raw, flags=re.IGNORECASE):
        candidate = f"https://{raw}"
    parsed = urlsplit(candidate)
    host = str(parsed.netloc or "").strip().lower().split(":", 1)[0]
    if host not in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}:
        raise HTTPException(status_code=400, detail="群聊地址格式不正确，请填写群 ID、@username 或公开 t.me 地址。")
    parts = [part for part in str(parsed.path or "").split("/") if part]
    if not parts:
        raise HTTPException(status_code=400, detail="群聊地址格式不正确，请填写群 ID、@username 或公开 t.me 地址。")
    first = str(parts[0] or "").strip()
    if first.startswith("+") or first == "joinchat":
        raise HTTPException(status_code=400, detail="暂不支持邀请链接，请填写群 ID、@username 或公开 t.me 地址。")
    if first == "c":
        if len(parts) < 2 or not re.fullmatch(r"\d+", parts[1]):
            raise HTTPException(status_code=400, detail="群聊地址格式不正确，请填写群 ID、@username 或公开 t.me 地址。")
        return None, int(f"-100{parts[1]}")
    username = first.lstrip("@").strip()
    if not username:
        raise HTTPException(status_code=400, detail="群聊地址格式不正确，请填写群 ID、@username 或公开 t.me 地址。")
    return username, 0


async def _resolve_notice_group_reference_to_chat_id(
    value: Any,
    *,
    cache_key: str | None = None,
    raise_on_failure: bool = True,
) -> int:
    raw_text = _notice_group_cache_raw(value)
    username, chat_id = _parse_notice_group_reference(value)
    if chat_id:
        _store_notice_group_chat_id(cache_key, raw_text, chat_id)
        return chat_id
    if not username:
        _clear_notice_group_cache(cache_key)
        return 0
    try:
        chat = await bot.get_chat(f"@{username}")
    except Exception as exc:
        LOGGER.warning(f"xiuxian resolve notice group failed value={value!r}: {exc}")
        if raise_on_failure:
            raise HTTPException(status_code=400, detail="无法识别这个群聊地址，请确认机器人已加入该群且地址可访问。")
        return _cached_notice_group_chat_id(cache_key, raw_text)
    if getattr(chat, "type", None) not in {enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL}:
        if raise_on_failure:
            raise HTTPException(status_code=400, detail="这里只能填写群组或频道地址。")
        return 0
    resolved_chat_id = int(getattr(chat, "id", 0) or 0)
    _store_notice_group_chat_id(cache_key, raw_text, resolved_chat_id)
    return resolved_chat_id


async def _resolve_notice_group_chat_id(
    scope: str,
    fallback_chat_id: int | None = None,
    *,
    raise_on_failure: bool = False,
    allow_main_fallback: bool = True,
) -> int | None:
    key = _notice_group_setting_key(scope)
    settings = get_xiuxian_settings()
    raw_value = settings.get(key, 0) if key else 0
    raw_text = str(raw_value or "").strip()
    resolved_chat_id = await _resolve_notice_group_reference_to_chat_id(
        raw_value,
        cache_key=key,
        raise_on_failure=raise_on_failure,
    )
    if resolved_chat_id:
        return resolved_chat_id
    if raw_text and raw_text not in {"0", "None"}:
        return None
    if fallback_chat_id:
        return int(fallback_chat_id)
    if allow_main_fallback:
        return _main_group_chat_id()
    return None


async def _resolve_notice_group_setting_value(value: Any, *, allow_unresolved: bool = False) -> int | str:
    normalized_text = str(value or "").strip()
    if not normalized_text:
        return 0
    resolved_chat_id = await _resolve_notice_group_reference_to_chat_id(
        normalized_text,
        raise_on_failure=not allow_unresolved,
    )
    if resolved_chat_id:
        return resolved_chat_id
    return normalized_text if allow_unresolved else 0


async def _resolve_notice_group_settings_patch(patch: dict[str, Any]) -> dict[str, Any]:
    for key in ("shop_notice_group_id", "auction_notice_group_id", "arena_notice_group_id"):
        if key in patch:
            raw_value = patch.get(key)
            normalized_text = str(raw_value or "").strip()
            if not normalized_text:
                _clear_notice_group_cache(key)
                patch[key] = 0
                continue
            patch[key] = await _resolve_notice_group_setting_value(raw_value, allow_unresolved=True)
            if isinstance(patch[key], int):
                _store_notice_group_chat_id(key, raw_value, patch[key])
    return patch


def _event_summary_interval_minutes(settings: dict[str, Any] | None = None) -> int:
    source = settings if isinstance(settings, dict) else get_xiuxian_settings()
    try:
        value = int(source.get("event_summary_interval_minutes", DEFAULT_SETTINGS.get("event_summary_interval_minutes", 10)) or 0)
    except (TypeError, ValueError):
        value = int(DEFAULT_SETTINGS.get("event_summary_interval_minutes", 10))
    return max(value, 0)


def _admin_panel_url() -> str:
    return build_plugin_url("/plugins/xiuxian/admin") or "/plugins/xiuxian/admin"


async def _is_group_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception as exc:
        LOGGER.warning(f"xiuxian group admin check failed chat={chat_id} user={user_id}: {exc}")
        return False
    return member.status in {ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR}


def _chat_member_status_value(member: Any) -> str:
    if isinstance(member, dict):
        raw_status = member.get("status")
    else:
        raw_status = getattr(member, "status", None)
    return str(getattr(raw_status, "value", raw_status) or "").strip().lower()


def _chat_member_has_privilege(member: Any, privilege_name: str) -> bool:
    if isinstance(member, dict):
        return bool(member.get(privilege_name))
    direct = getattr(member, privilege_name, None)
    if direct is not None:
        return bool(direct)
    privileges = getattr(member, "privileges", None)
    return bool(getattr(privileges, privilege_name, False))


def _chat_member_can_manage_tags(member: Any) -> bool:
    if isinstance(member, dict):
        if "can_manage_tags" in member:
            return bool(member.get("can_manage_tags"))
        if "can_pin_messages" in member:
            return bool(member.get("can_pin_messages"))
        return True
    direct = getattr(member, "can_manage_tags", None)
    if direct is not None:
        return bool(direct)
    privileges = getattr(member, "privileges", None)
    if privileges is not None and getattr(privileges, "can_manage_tags", None) is not None:
        return bool(getattr(privileges, "can_manage_tags", False))
    if _chat_member_has_privilege(member, "can_pin_messages"):
        return True
    return not (
        getattr(member, "can_pin_messages", None) is False
        or getattr(getattr(member, "privileges", None), "can_pin_messages", None) is False
    )


async def _sync_xiuxian_title_to_group(chat_id: int, user_id: int, title_name: str) -> dict[str, Any]:
    safe_title = normalize_telegram_member_badge_text(title_name)
    if not safe_title:
        raise HTTPException(status_code=400, detail="称号不能为空，或仅包含 Telegram 不支持的特殊符号，无法同步到群成员标签。")

    try:
        me = await bot.get_me()
        bot_member = await get_chat_member_details(chat_id, int(me.id))
    except Exception as exc:
        LOGGER.warning(f"xiuxian title sync bot privilege check failed chat={chat_id}: {exc}")
        raise HTTPException(status_code=400, detail="无法确认 Bot 在目标群组中的管理权限。") from exc

    if _chat_member_status_value(bot_member) not in {"administrator", "owner", "creator"}:
        raise HTTPException(status_code=400, detail="Bot 需要先成为目标群组管理员，才能同步群成员标签。")

    try:
        target_member = await get_chat_member_details(chat_id, user_id)
    except Exception as exc:
        LOGGER.warning(f"xiuxian title sync target check failed chat={chat_id} user={user_id}: {exc}")
        raise HTTPException(status_code=400, detail="请先加入目标群组，再同步群成员标签。") from exc

    target_status = _chat_member_status_value(target_member)
    if target_status in {"left", "banned", "kicked"}:
        raise HTTPException(status_code=400, detail="请先加入目标群组，再同步群成员标签。")
    if target_status in {"owner", "creator"}:
        raise HTTPException(status_code=400, detail="群主头衔无法由 Bot 修改。")

    try:
        if target_status == "administrator":
            if not _chat_member_has_privilege(bot_member, "can_promote_members"):
                raise HTTPException(status_code=400, detail="Bot 缺少修改管理员头衔权限，请在群管理权限中开启提升管理员权限。")
            result = await set_chat_member_title(chat_id, user_id, safe_title)
            mode = "administrator_custom_title"
        else:
            if not _chat_member_can_manage_tags(bot_member):
                raise HTTPException(status_code=400, detail="Bot 缺少管理成员标签权限，请在群管理权限中开启 can_manage_tags。")
            result = await set_chat_member_tag(chat_id, user_id, safe_title)
            mode = "regular_member_tag"
    except HTTPException:
        raise
    except ModerationServiceError as exc:
        LOGGER.warning(f"xiuxian title sync set title failed chat={chat_id} user={user_id}: {exc}")
        raise HTTPException(
            status_code=400,
            detail=str(exc) or "群成员标签同步失败，请确认 Bot 拥有管理成员标签权限。",
        ) from exc

    return {
        "chat_id": chat_id,
        "title": safe_title,
        "mode": mode,
        "telegram_result": result,
    }


async def _can_manage_upload_permissions(client, msg) -> bool:
    if msg.from_user is None:
        return False
    if is_admin_user_id(msg.from_user.id):
        return True
    chat = getattr(msg, "chat", None)
    if chat is None:
        return False
    try:
        chat_id = int(chat.id)
    except (TypeError, ValueError):
        return False
    return chat_id < 0 and await _is_group_admin(client, chat_id, msg.from_user.id)


async def _require_message_user(message, *, action_text: str) -> Any | None:
    user = getattr(message, "from_user", None)
    if user is not None:
        return user
    if getattr(message, "sender_chat", None) is not None:
        await _reply_text(
            message,
            f"当前消息来自匿名管理员或频道身份，机器人拿不到真实 TG 账号，无法{action_text}。请关闭匿名发送后重试。",
            quote=True,
        )
    else:
        await _reply_text(message, f"当前无法识别你的 TG 身份，暂时不能{action_text}。", quote=True)
    return None


def _remember_journal(tg: int, action_type: str, title: str, detail: str | None = None) -> None:
    try:
        create_journal(tg, action_type, title, detail)
    except Exception as exc:
        LOGGER.warning(f"xiuxian journal write failed: {exc}")


def _achievement_private_text(unlock: dict[str, Any]) -> str:
    achievement = unlock.get("achievement") or {}
    reward_summary = unlock.get("reward_summary") or format_reward_summary(achievement.get("reward_config"))
    metric_label = unlock.get("metric_label") or achievement.get("metric_key") or "进度"
    metric_value = int(unlock.get("metric_value") or 0)
    return "\n".join(
        [
            "🏅 **成就达成**",
            f"你获得了 **{_md_escape(achievement.get('name') or '未知成就')}**",
            f"📖 说明：{_md_escape(achievement.get('description') or '达成指定目标。')}",
            f"📈 进度：{_md_escape(metric_label)} `已达到 {metric_value}/{achievement.get('target_value') or 0}`",
            f"🎁 奖励：{_md_escape(reward_summary)}",
        ]
    )


def _achievement_group_text(unlock: dict[str, Any]) -> str:
    achievement = unlock.get("achievement") or {}
    reward_summary = unlock.get("reward_summary") or format_reward_summary(achievement.get("reward_config"))
    display_name = unlock.get("display_name") or f"TG {unlock.get('tg')}"
    return _format_notice_card(
        "成就喜报",
        emoji="📣",
        lines=[
            f"👤 达成者：{_md_escape(display_name)}",
            f"🏅 成就：**{_md_escape(achievement.get('name') or '未知成就')}**",
            f"🎁 奖励：{_md_escape(reward_summary)}",
        ],
    )


async def _notify_achievement_unlocks(unlocks: list[dict[str, Any]] | None) -> None:
    if not unlocks:
        return
    group_chat_id = _main_group_chat_id()
    for unlock in unlocks:
        achievement = unlock.get("achievement") or {}
        achievement_id = int(achievement.get("id") or unlock.get("achievement_id") or 0)
        tg = int(unlock.get("tg") or 0)
        if achievement_id <= 0 or tg <= 0:
            continue
        if achievement.get("notify_private") and not unlock.get("private_notified_at"):
            try:
                await _send_message(
                    bot,
                    tg,
                    _achievement_private_text(unlock),
                    persistent=True,
                    parse_mode=RICH_TEXT_MODE,
                )
                await run_in_threadpool(mark_user_achievement_notification, tg, achievement_id, "private")
            except Exception as exc:
                LOGGER.warning(f"xiuxian achievement private notify failed tg={tg} achievement={achievement_id}: {exc}")
        if group_chat_id and achievement.get("notify_group") and not unlock.get("group_notified_at"):
            try:
                await _send_message(
                    bot,
                    group_chat_id,
                    _achievement_group_text(unlock),
                    parse_mode=RICH_TEXT_MODE,
                )
                await run_in_threadpool(mark_user_achievement_notification, tg, achievement_id, "group")
            except Exception as exc:
                LOGGER.warning(f"xiuxian achievement group notify failed tg={tg} achievement={achievement_id}: {exc}")


def _bundle_runtime_flags(tg: int) -> dict[str, Any]:
    can_upload_images, upload_reason = _can_user_upload_images(tg)
    is_admin = bool(is_admin_user_id(tg))
    return {
        "can_upload_images": can_upload_images,
        "upload_image_reason": upload_reason,
        "allow_non_admin_image_upload": bool(
            get_xiuxian_settings().get("allow_non_admin_image_upload", False)
        ),
        "is_admin": is_admin,
        "admin_panel_url": _admin_panel_url() if is_admin else None,
    }


def _xiuxian_user_version_groups(tg: int, *, include_catalog: bool = True) -> tuple[tuple[Any, ...], ...]:
    from bot.plugins.xiuxian_game.cache import catalog_version_groups

    groups: list[tuple[Any, ...]] = [("profile", tg), ("user-view", tg)]
    groups.extend(catalog_version_groups(include_all_catalog=include_catalog))
    return tuple(groups)


def _bootstrap_version_groups(tg: int) -> tuple[tuple[Any, ...], ...]:
    from bot.plugins.xiuxian_game.features.bundle_cache import bootstrap_version_groups

    return bootstrap_version_groups(tg)


def _full_bundle(tg: int) -> dict[str, Any]:
    from bot.plugins.xiuxian_game.cache import USER_VIEW_TTL, load_multi_versioned_json

    flags = _bundle_runtime_flags(tg)
    return load_multi_versioned_json(
        version_part_groups=_xiuxian_user_version_groups(tg),
        cache_parts=(
            "full-bundle",
            tg,
            int(bool(flags.get("can_upload_images"))),
            str(flags.get("upload_image_reason") or ""),
            int(bool(flags.get("allow_non_admin_image_upload"))),
            int(bool(flags.get("is_admin"))),
            str(flags.get("admin_panel_url") or ""),
        ),
        ttl=min(USER_VIEW_TTL, FULL_BUNDLE_TTL),
        loader=lambda: build_full_profile_bundle(tg, **flags),
    )


def _bootstrap_core_bundle(tg: int) -> dict[str, Any]:
    from bot.plugins.xiuxian_game.features.bundle_cache import load_cached_bootstrap_core_bundle

    return load_cached_bootstrap_core_bundle(tg, **_bundle_runtime_flags(tg))


def _deferred_bundle_sections(tg: int) -> dict[str, Any]:
    from bot.plugins.xiuxian_game.cache import USER_VIEW_TTL, load_multi_versioned_json

    flags = _bundle_runtime_flags(tg)
    return load_multi_versioned_json(
        version_part_groups=_xiuxian_user_version_groups(tg),
        cache_parts=(
            "deferred-bundle",
            tg,
            int(bool(flags.get("can_upload_images"))),
            str(flags.get("upload_image_reason") or ""),
            int(bool(flags.get("allow_non_admin_image_upload"))),
            int(bool(flags.get("is_admin"))),
            str(flags.get("admin_panel_url") or ""),
        ),
        ttl=min(USER_VIEW_TTL, DEFERRED_BUNDLE_TTL),
        loader=lambda: build_deferred_profile_sections(tg, **flags),
    )


def _deferred_bundle_section(tg: int, section: str) -> dict[str, Any]:
    from bot.plugins.xiuxian_game.cache import USER_VIEW_TTL, load_multi_versioned_json

    normalized = str(section or "").strip().replace("-", "_")
    flags = _bundle_runtime_flags(tg)
    return load_multi_versioned_json(
        version_part_groups=_xiuxian_user_version_groups(tg),
        cache_parts=(
            "deferred-section",
            normalized,
            tg,
            int(bool(flags.get("can_upload_images"))),
            str(flags.get("upload_image_reason") or ""),
            int(bool(flags.get("allow_non_admin_image_upload"))),
            int(bool(flags.get("is_admin"))),
            str(flags.get("admin_panel_url") or ""),
        ),
        ttl=min(USER_VIEW_TTL, DEFERRED_BUNDLE_TTL),
        loader=lambda: build_profile_section_bundle(tg, normalized, **flags),
    )


async def build_deferred_bundle_once(tg: int) -> dict[str, Any]:
    flags = _bundle_runtime_flags(tg)
    key = (
        "deferred-bundle",
        int(tg),
        int(bool(flags.get("can_upload_images"))),
        str(flags.get("upload_image_reason") or ""),
        int(bool(flags.get("allow_non_admin_image_upload"))),
        int(bool(flags.get("is_admin"))),
        str(flags.get("admin_panel_url") or ""),
    )
    task = DEFERRED_BUNDLE_TASKS.get(key)
    if task is None or task.done():
        task = asyncio.create_task(run_in_threadpool(_deferred_bundle_sections, tg))
        DEFERRED_BUNDLE_TASKS[key] = task

        def _cleanup(done_task: asyncio.Task) -> None:
            current = DEFERRED_BUNDLE_TASKS.get(key)
            if current is done_task:
                DEFERRED_BUNDLE_TASKS.pop(key, None)

        task.add_done_callback(_cleanup)
    return await task


async def build_deferred_section_once(tg: int, section: str) -> dict[str, Any]:
    normalized = str(section or "").strip().replace("-", "_")
    flags = _bundle_runtime_flags(tg)
    key = (
        "deferred-section",
        normalized,
        int(tg),
        int(bool(flags.get("can_upload_images"))),
        str(flags.get("upload_image_reason") or ""),
        int(bool(flags.get("allow_non_admin_image_upload"))),
        int(bool(flags.get("is_admin"))),
        str(flags.get("admin_panel_url") or ""),
    )
    task = DEFERRED_SECTION_TASKS.get(key)
    if task is None or task.done():
        task = asyncio.create_task(run_in_threadpool(_deferred_bundle_section, tg, normalized))
        DEFERRED_SECTION_TASKS[key] = task

        def _cleanup(done_task: asyncio.Task) -> None:
            current = DEFERRED_SECTION_TASKS.get(key)
            if current is done_task:
                DEFERRED_SECTION_TASKS.pop(key, None)

        task.add_done_callback(_cleanup)
    return await task


def _with_full_bundle(tg: int, payload: Any, *, field: str = "result") -> dict[str, Any]:
    if isinstance(payload, dict):
        data = dict(payload)
    else:
        data = {field: payload}
    data["bundle"] = _full_bundle(tg)
    data["bundle_mode"] = "full"
    return data


def _with_core_bundle(tg: int, payload: Any, *, field: str = "result") -> dict[str, Any]:
    if isinstance(payload, dict):
        data = dict(payload)
    else:
        data = {field: payload}
    data["bundle"] = _bootstrap_core_bundle(tg)
    data["bundle_mode"] = "core"
    return data


def _with_result_core_bundle(tg: int, result: Any) -> dict[str, Any]:
    return _with_core_bundle(tg, {"result": result})


def _message_auto_delete_seconds() -> int:
    raw = get_xiuxian_settings().get(
        "message_auto_delete_seconds",
        DEFAULT_SETTINGS.get("message_auto_delete_seconds", 180),
    )
    try:
        return max(int(raw or 0), 0)
    except (TypeError, ValueError):
        return int(DEFAULT_SETTINGS.get("message_auto_delete_seconds", 180))


async def _delete_message_after_delay(message, key: tuple[int, int], delay: int) -> None:
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        LOGGER.debug(f"xiuxian auto delete skipped chat={key[0]} message={key[1]}: {exc}")
    finally:
        task = MESSAGE_AUTO_DELETE_TASKS.get(key)
        if task is asyncio.current_task():
            MESSAGE_AUTO_DELETE_TASKS.pop(key, None)


def _apply_message_auto_delete(message, *, persistent: bool = False, seconds: int | None = None):
    if message is None:
        return None
    chat = getattr(message, "chat", None)
    message_id = getattr(message, "id", None)
    chat_id = getattr(chat, "id", None)
    if chat_id is None or message_id is None:
        return message
    key = (int(chat_id), int(message_id))
    existing = MESSAGE_AUTO_DELETE_TASKS.pop(key, None)
    if existing is not None:
        existing.cancel()
    delay = max(int(seconds if seconds is not None else _message_auto_delete_seconds()), 0)
    if persistent or delay <= 0:
        return message
    MESSAGE_AUTO_DELETE_TASKS[key] = asyncio.create_task(_delete_message_after_delay(message, key, delay))
    return message


async def _reply_text(message, text: str, *, persistent: bool = False, auto_delete_seconds: int | None = None, **kwargs):
    sent = await message.reply_text(text, **kwargs)
    return _apply_message_auto_delete(sent, persistent=persistent, seconds=auto_delete_seconds)


async def _delete_user_command_message(message) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except Exception as exc:
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        message_id = getattr(message, "id", None)
        LOGGER.debug(f"xiuxian command delete skipped chat={chat_id} message={message_id}: {exc}")


async def _send_message(client, chat_id: int, text: str, *, persistent: bool = False, auto_delete_seconds: int | None = None, **kwargs):
    sent = await client.send_message(chat_id, text, **kwargs)
    return _apply_message_auto_delete(sent, persistent=persistent, seconds=auto_delete_seconds)


async def _send_photo(client, chat_id: int, photo, *, persistent: bool = False, auto_delete_seconds: int | None = None, **kwargs):
    sent = await client.send_photo(chat_id, photo, **kwargs)
    return _apply_message_auto_delete(sent, persistent=persistent, seconds=auto_delete_seconds)


async def _edit_text(message, text: str, *, persistent: bool = False, auto_delete_seconds: int | None = None, **kwargs):
    edited = await message.edit_text(text, **kwargs)
    return _apply_message_auto_delete(edited, persistent=persistent, seconds=auto_delete_seconds)


async def _edit_caption(message, caption: str, *, persistent: bool = False, auto_delete_seconds: int | None = None, **kwargs):
    edited = await message.edit_caption(caption, **kwargs)
    return _apply_message_auto_delete(edited, persistent=persistent, seconds=auto_delete_seconds)


async def _edit_message_text(
    client,
    chat_id: int,
    message_id: int,
    text: str,
    *,
    persistent: bool = False,
    auto_delete_seconds: int | None = None,
    **kwargs,
):
    edited = await client.edit_message_text(chat_id, message_id, text, **kwargs)
    return _apply_message_auto_delete(edited, persistent=persistent, seconds=auto_delete_seconds)


def _sort_active_notice_arenas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: REALM_ORDER.index(item.get("realm_stage")) if item.get("realm_stage") in REALM_ORDER else 999)


def _normalize_event_summary_chat_ids(chat_ids: int | Iterable[int] | None) -> set[int]:
    if chat_ids is None:
        return set()
    source = (chat_ids,) if isinstance(chat_ids, int) else chat_ids
    normalized: set[int] = set()
    for chat_id in source:
        value = int(chat_id or 0)
        if value:
            normalized.add(value)
    return normalized


def _event_summary_message_map() -> dict[int, int]:
    raw = get_xiuxian_settings().get(EVENT_SUMMARY_MESSAGE_MAP_KEY) or {}
    if not isinstance(raw, dict):
        return {}
    mapping: dict[int, int] = {}
    for chat_id, message_id in raw.items():
        try:
            resolved_chat_id = int(chat_id or 0)
            resolved_message_id = int(message_id or 0)
        except (TypeError, ValueError):
            continue
        if resolved_chat_id and resolved_message_id > 0:
            mapping[resolved_chat_id] = resolved_message_id
    return mapping


def _persist_event_summary_message(chat_id: int, message_id: int) -> None:
    resolved_chat_id = int(chat_id or 0)
    if not resolved_chat_id:
        return
    mapping = _event_summary_message_map()
    resolved_message_id = int(message_id or 0)
    if resolved_message_id > 0:
        mapping[resolved_chat_id] = resolved_message_id
    else:
        mapping.pop(resolved_chat_id, None)
    set_xiuxian_settings(
        {
            EVENT_SUMMARY_MESSAGE_MAP_KEY: {
                str(saved_chat_id): int(saved_message_id)
                for saved_chat_id, saved_message_id in sorted(mapping.items())
                if int(saved_chat_id or 0) != 0 and int(saved_message_id or 0) > 0
            }
        }
    )


def _stored_event_summary_message_id(chat_id: int) -> int:
    return int(_event_summary_message_map().get(int(chat_id or 0), 0) or 0)


def _remember_event_summary_message(chat_id: int, message_id: int, *, text: str | None = None) -> None:
    resolved_chat_id = int(chat_id or 0)
    resolved_message_id = int(message_id or 0)
    if not resolved_chat_id or resolved_message_id <= 0:
        return
    EVENT_SUMMARY_MESSAGES[resolved_chat_id] = resolved_message_id
    if text is not None:
        EVENT_SUMMARY_LAST_TEXTS[resolved_chat_id] = text
    _persist_event_summary_message(resolved_chat_id, resolved_message_id)


def _forget_event_summary_message(chat_id: int) -> None:
    resolved_chat_id = int(chat_id or 0)
    EVENT_SUMMARY_MESSAGES.pop(resolved_chat_id, None)
    EVENT_SUMMARY_LAST_TEXTS.pop(resolved_chat_id, None)
    EVENT_SUMMARY_PINNED_MESSAGES.pop(resolved_chat_id, None)
    if resolved_chat_id:
        _persist_event_summary_message(resolved_chat_id, 0)


def _is_message_not_modified_error(exc: Exception) -> bool:
    detail = str(exc or "").strip().lower()
    return "message is not modified" in detail or "message_not_modified" in detail


def _invalidate_event_summary_snapshot() -> None:
    global EVENT_SUMMARY_SNAPSHOT_CACHE, EVENT_SUMMARY_SNAPSHOT_CACHE_AT
    EVENT_SUMMARY_SNAPSHOT_CACHE = None
    EVENT_SUMMARY_SNAPSHOT_CACHE_AT = 0.0


def _event_summary_snapshot(
    force_refresh: bool = False,
    *,
    configured_notice_chat_ids: dict[str, int] | None = None,
) -> dict[str, Any]:
    global EVENT_SUMMARY_SNAPSHOT_CACHE, EVENT_SUMMARY_SNAPSHOT_CACHE_AT
    now_monotonic = time.monotonic()
    if (
        not force_refresh
        and EVENT_SUMMARY_SNAPSHOT_CACHE is not None
        and now_monotonic - EVENT_SUMMARY_SNAPSHOT_CACHE_AT < EVENT_SUMMARY_SNAPSHOT_TTL_SECONDS
    ):
        return EVENT_SUMMARY_SNAPSHOT_CACHE

    shop_rows_by_chat: dict[int, list[dict[str, Any]]] = defaultdict(list)
    auction_rows_by_chat: dict[int, list[dict[str, Any]]] = defaultdict(list)
    arena_rows_by_chat: dict[int, list[dict[str, Any]]] = defaultdict(list)
    all_shop_rows: list[dict[str, Any]] = []
    all_auction_rows: list[dict[str, Any]] = []
    all_arena_rows: list[dict[str, Any]] = []
    chat_ids = {int(chat_id) for chat_id in EVENT_SUMMARY_MESSAGES if int(chat_id or 0) != 0}
    chat_ids.update(_event_summary_message_map().keys())
    resolved_notice_chat_ids = {
        str(scope).strip().lower(): int(chat_id or 0)
        for scope, chat_id in (configured_notice_chat_ids or {}).items()
        if str(scope or "").strip() and int(chat_id or 0) != 0
    }

    for scope in ("shop", "auction", "arena"):
        configured = int(resolved_notice_chat_ids.get(scope) or _notice_group_chat_id(scope, allow_main_fallback=False) or 0)
        if configured:
            chat_ids.add(int(configured))
            resolved_notice_chat_ids[scope] = int(configured)

    shop_notice_chat_id = int(resolved_notice_chat_ids.get("shop") or 0)
    for row in list_shop_items(official_only=False, include_disabled=False):
        row_chat_id = int(row.get("notice_group_chat_id") or 0)
        row_message_id = int(row.get("notice_group_message_id") or 0)
        chat_id = row_chat_id or shop_notice_chat_id
        if chat_id == 0:
            continue
        chat_ids.add(chat_id)
        shop_rows_by_chat[chat_id].append(row)
        all_shop_rows.append(row)

    auction_notice_chat_id = int(resolved_notice_chat_ids.get("auction") or 0)
    for row in list_auction_items(status="active"):
        row_chat_id = int(row.get("group_chat_id") or 0)
        row_message_id = int(row.get("group_message_id") or 0)
        chat_id = row_chat_id or auction_notice_chat_id
        if chat_id == 0:
            continue
        chat_ids.add(chat_id)
        auction_rows_by_chat[chat_id].append(row)
        all_auction_rows.append(row)

    arena_notice_chat_id = int(resolved_notice_chat_ids.get("arena") or 0)
    for row in list_group_arenas(status="active"):
        row_chat_id = int(row.get("group_chat_id") or 0)
        row_message_id = int(row.get("group_message_id") or 0)
        chat_id = row_chat_id or arena_notice_chat_id
        if chat_id == 0:
            continue
        chat_ids.add(chat_id)
        arena_rows_by_chat[chat_id].append(row)
        all_arena_rows.append(row)

    snapshot = {
        "chat_ids": {chat_id for chat_id in chat_ids if chat_id},
        "shops": {chat_id: rows for chat_id, rows in shop_rows_by_chat.items()},
        "auctions": {chat_id: rows for chat_id, rows in auction_rows_by_chat.items()},
        "arenas": {chat_id: _sort_active_notice_arenas(rows) for chat_id, rows in arena_rows_by_chat.items()},
        "all_shops": all_shop_rows,
        "all_auctions": all_auction_rows,
        "all_arenas": _sort_active_notice_arenas(all_arena_rows),
    }
    EVENT_SUMMARY_SNAPSHOT_CACHE = snapshot
    EVENT_SUMMARY_SNAPSHOT_CACHE_AT = now_monotonic
    return snapshot


def _active_notice_shop_items(chat_id: int, shop_rows_by_chat: dict[int, list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    if shop_rows_by_chat is not None:
        return shop_rows_by_chat.get(int(chat_id), [])
    snapshot = _event_summary_snapshot()
    return snapshot["shops"].get(int(chat_id), [])


def _active_notice_auctions(chat_id: int, auction_rows_by_chat: dict[int, list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    if auction_rows_by_chat is not None:
        return auction_rows_by_chat.get(int(chat_id), [])
    snapshot = _event_summary_snapshot()
    return snapshot["auctions"].get(int(chat_id), [])


def _active_notice_arenas(chat_id: int, arena_rows_by_chat: dict[int, list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    if arena_rows_by_chat is not None:
        return arena_rows_by_chat.get(int(chat_id), [])
    snapshot = _event_summary_snapshot()
    return snapshot["arenas"].get(int(chat_id), [])


def _event_summary_target_chat_ids(snapshot: dict[str, Any] | None = None) -> set[int]:
    if snapshot is None:
        snapshot = _event_summary_snapshot()
    return set(snapshot.get("chat_ids") or set())


def _event_summary_lock() -> asyncio.Lock:
    global EVENT_SUMMARY_REFRESH_LOCK
    if EVENT_SUMMARY_REFRESH_LOCK is None:
        EVENT_SUMMARY_REFRESH_LOCK = asyncio.Lock()
    return EVENT_SUMMARY_REFRESH_LOCK


def _summary_remaining_text(end_at: str | None) -> str:
    target = _parse_shanghai_datetime(end_at)
    if target is None:
        return "剩余未知"
    remaining = max(int((target - datetime.now(SHANGHAI_TZ)).total_seconds()), 0)
    if remaining <= 0:
        return "已到时"
    hours, rem = divmod(remaining, 3600)
    minutes = max(rem // 60, 0)
    if hours > 0:
        return f"剩 {hours}时{minutes}分"
    return f"剩 {max(minutes, 1)}分"


def _build_event_summary_text(
    chat_id: int,
    *,
    auction_rows_by_chat: dict[int, list[dict[str, Any]]] | None = None,
    arena_rows_by_chat: dict[int, list[dict[str, Any]]] | None = None,
    shop_rows_by_chat: dict[int, list[dict[str, Any]]] | None = None,
) -> str:
    auctions = _active_notice_auctions(chat_id, auction_rows_by_chat)
    arenas = _active_notice_arenas(chat_id, arena_rows_by_chat)
    shops = _active_notice_shop_items(chat_id, shop_rows_by_chat)
    total_count = len(auctions) + len(arenas) + len(shops)
    lines = [
        "🧭 **仙界汇总**",
        f"🕰️ 更新时间：`{datetime.now(SHANGHAI_TZ).strftime('%m-%d %H:%M')}`",
        f"📊 进行中：拍卖 `{len(auctions)}` ｜ 擂台 `{len(arenas)}` ｜ 小铺 `{len(shops)}` ｜ 合计 `{total_count}`",
    ]
    if not auctions and not arenas and not shops:
        lines.append("")
        lines.append("📭 当前暂无进行中的拍卖、擂台或小铺通知。")
        lines.append("后续一旦有新群播，本条汇总会自动刷新并保持置顶。")
        return "\n".join(lines)

    if auctions:
        lines.append("")
        lines.append(f"🏺 **拍卖行** · `共 {len(auctions)} 场`")
        for row in auctions[:6]:
            label = f"{row.get('item_name') or '未知拍品'}"
            current_price = int(row.get("current_display_price_stone") or 0)
            detail = _summary_remaining_text(row.get("end_at"))
            lines.append(f"• {_message_jump_link(label, int(row.get('group_chat_id') or 0), int(row.get('group_message_id') or 0))}")
            lines.append(f"↳ 💰 当前价：`{current_price}` 灵石 ｜ ⏳ {detail}")
        if len(auctions) > 6:
            lines.append(f"• 其余还有 `{len(auctions) - 6}` 场拍卖进行中")

    if arenas:
        lines.append("")
        lines.append(f"🏟️ **擂台战** · `共 {len(arenas)} 座`")
        for row in arenas[:6]:
            champion_name = str(row.get("champion_display_name") or "").strip() or f"TG {int(row.get('champion_tg') or 0)}"
            label = f"{row.get('realm_stage') or '未知'}擂台"
            detail = _summary_remaining_text(row.get("end_at"))
            lines.append(f"• {_message_jump_link(label, int(row.get('group_chat_id') or 0), int(row.get('group_message_id') or 0))}")
            lines.append(f"↳ 👑 擂主：{_md_escape(champion_name)} ｜ ⏳ {detail}")
        if len(arenas) > 6:
            lines.append(f"• 其余还有 `{len(arenas) - 6}` 座擂台开放中")

    if shops:
        lines.append("")
        lines.append(f"🏪 **坊市小铺** · `共 {len(shops)} 条`")
        for row in shops[:6]:
            label = f"{row.get('shop_name') or '游仙小铺'} · {row.get('item_name') or '未知商品'}"
            detail = f"`{int(row.get('price_stone') or 0)}` 灵石 / 库存 `{int(row.get('quantity') or 0)}`"
            lines.append(f"• {_message_jump_link(label, int(row.get('notice_group_chat_id') or 0), int(row.get('notice_group_message_id') or 0))}")
            lines.append(f"↳ 🛒 价格 / 库存：{detail}")
        if len(shops) > 6:
            lines.append(f"• 其余还有 `{len(shops) - 6}` 条小铺通知")

    lines.append("")
    lines.append("👇 点击蓝字可直接跳转原消息，继续购买、竞拍或攻擂。")
    return "\n".join(lines)


def _message_text_content(message: Any) -> str:
    return str(getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()


def _message_id_value(message: Any) -> int:
    return int(getattr(message, "id", None) or getattr(message, "message_id", None) or 0)


def _is_event_summary_message(message: Any) -> bool:
    text = _message_text_content(message)
    return "修仙汇总" in text or "仙界汇总" in text


async def _get_pinned_chat_message(chat_id: int) -> Any | None:
    resolved_chat_id = int(chat_id or 0)
    if not resolved_chat_id:
        return None
    try:
        chat = await bot.get_chat(resolved_chat_id)
    except Exception as exc:
        LOGGER.warning(f"xiuxian event summary get chat failed chat={resolved_chat_id}: {exc}")
        return None
    return getattr(chat, "pinned_message", None)


async def _bound_existing_event_summary_message(chat_id: int) -> int:
    resolved_chat_id = int(chat_id or 0)
    if not resolved_chat_id:
        return 0
    pinned_message = await _get_pinned_chat_message(resolved_chat_id)
    if pinned_message is None or not _is_event_summary_message(pinned_message):
        return 0
    message_id = _message_id_value(pinned_message)
    if message_id <= 0:
        return 0
    _remember_event_summary_message(resolved_chat_id, message_id)
    EVENT_SUMMARY_PINNED_MESSAGES[resolved_chat_id] = message_id
    return message_id


async def _pin_event_summary_message(chat_id: int, message_id: int) -> None:
    if not chat_id or not message_id:
        return
    resolved_chat_id = int(chat_id)
    resolved_message_id = int(message_id)
    current_pinned_message = await _get_pinned_chat_message(resolved_chat_id)
    current_pinned_id = _message_id_value(current_pinned_message)
    if current_pinned_id > 0 and _is_event_summary_message(current_pinned_message):
        EVENT_SUMMARY_PINNED_MESSAGES[resolved_chat_id] = current_pinned_id
        if current_pinned_id == resolved_message_id:
            return

    if current_pinned_id > 0 and current_pinned_id != resolved_message_id and _is_event_summary_message(current_pinned_message):
        try:
            await bot.unpin_chat_message(chat_id=resolved_chat_id, message_id=current_pinned_id)
        except Exception as exc:
            LOGGER.warning(f"xiuxian event summary unpin failed chat={resolved_chat_id} message={current_pinned_id}: {exc}")
    try:
        await bot.pin_chat_message(chat_id=resolved_chat_id, message_id=resolved_message_id, disable_notification=True)
        EVENT_SUMMARY_PINNED_MESSAGES[resolved_chat_id] = resolved_message_id
    except Exception as exc:
        LOGGER.warning(f"xiuxian event summary pin failed chat={resolved_chat_id} message={resolved_message_id}: {exc}")


async def _refresh_event_summary_for_chat(
    chat_id: int,
    *,
    auction_rows_by_chat: dict[int, list[dict[str, Any]]] | None = None,
    arena_rows_by_chat: dict[int, list[dict[str, Any]]] | None = None,
    shop_rows_by_chat: dict[int, list[dict[str, Any]]] | None = None,
    force_create: bool = False,
) -> None:
    resolved_chat_id = int(chat_id or 0)
    if not resolved_chat_id:
        return
    text = _build_event_summary_text(
        resolved_chat_id,
        auction_rows_by_chat=auction_rows_by_chat,
        arena_rows_by_chat=arena_rows_by_chat,
        shop_rows_by_chat=shop_rows_by_chat,
    )
    message_id = int(EVENT_SUMMARY_MESSAGES.get(resolved_chat_id) or _stored_event_summary_message_id(resolved_chat_id) or 0)
    if message_id <= 0:
        message_id = await _bound_existing_event_summary_message(resolved_chat_id)
    if message_id > 0:
        if EVENT_SUMMARY_LAST_TEXTS.get(resolved_chat_id) == text:
            if int(EVENT_SUMMARY_PINNED_MESSAGES.get(resolved_chat_id) or 0) != message_id:
                await _pin_event_summary_message(resolved_chat_id, message_id)
            return
        try:
            await _edit_message_text(
                bot,
                resolved_chat_id,
                message_id,
                text,
                parse_mode=RICH_TEXT_MODE,
                persistent=True,
            )
            _remember_event_summary_message(resolved_chat_id, message_id, text=text)
            await _pin_event_summary_message(resolved_chat_id, message_id)
            return
        except Exception as exc:
            if _is_message_not_modified_error(exc):
                EVENT_SUMMARY_LAST_TEXTS[resolved_chat_id] = text
                await _pin_event_summary_message(resolved_chat_id, message_id)
                return
            LOGGER.warning(f"xiuxian event summary refresh failed chat={resolved_chat_id} message={message_id}: {exc}")
            _forget_event_summary_message(resolved_chat_id)
    has_active_rows = any(
        (
            _active_notice_auctions(resolved_chat_id, auction_rows_by_chat),
            _active_notice_arenas(resolved_chat_id, arena_rows_by_chat),
            _active_notice_shop_items(resolved_chat_id, shop_rows_by_chat),
        )
    )
    if not has_active_rows and not force_create:
        return
    sent = await _send_message(bot, resolved_chat_id, text, parse_mode=RICH_TEXT_MODE, persistent=True)
    _remember_event_summary_message(resolved_chat_id, int(sent.id), text=text)
    await _pin_event_summary_message(resolved_chat_id, int(sent.id))


async def _configured_event_summary_chat_ids() -> set[int]:
    chat_ids = set(_event_summary_message_map().keys())
    for scope in ("shop", "auction", "arena"):
        resolved_chat_id = await _resolve_notice_group_chat_id(scope, allow_main_fallback=False)
        if resolved_chat_id:
            chat_ids.add(int(resolved_chat_id))
    return {chat_id for chat_id in chat_ids if int(chat_id or 0) != 0}


async def _refresh_all_event_summaries(
    chat_ids: int | Iterable[int] | None = None,
    *,
    force_snapshot_refresh: bool = False,
    force_create: bool = False,
    constrain_to_snapshot: bool = True,
) -> None:
    async with _event_summary_lock():
        resolved_notice_chat_ids: dict[str, int] = {}
        for scope in ("shop", "auction", "arena"):
            resolved_chat_id = await _resolve_notice_group_chat_id(scope, allow_main_fallback=False)
            if resolved_chat_id:
                resolved_notice_chat_ids[scope] = int(resolved_chat_id)
        snapshot = _event_summary_snapshot(
            force_refresh=force_snapshot_refresh,
            configured_notice_chat_ids=resolved_notice_chat_ids,
        )
        auction_rows_by_chat = snapshot.get("auctions") or {}
        arena_rows_by_chat = snapshot.get("arenas") or {}
        shop_rows_by_chat = snapshot.get("shops") or {}
        all_auction_rows = list(snapshot.get("all_auctions") or [])
        all_arena_rows = list(snapshot.get("all_arenas") or [])
        all_shop_rows = list(snapshot.get("all_shops") or [])
        snapshot_chat_ids = _event_summary_target_chat_ids(snapshot)
        target_chat_ids = _normalize_event_summary_chat_ids(chat_ids)
        if not target_chat_ids:
            target_chat_ids = set(snapshot_chat_ids)
        elif constrain_to_snapshot and not force_create:
            target_chat_ids &= snapshot_chat_ids
        if force_create:
            if chat_ids is None:
                target_chat_ids.update(await _configured_event_summary_chat_ids())
            elif not target_chat_ids:
                target_chat_ids = await _configured_event_summary_chat_ids()
        if not target_chat_ids:
            return
        for chat_id in sorted(target_chat_ids):
            per_chat_auction_rows = auction_rows_by_chat
            per_chat_arena_rows = arena_rows_by_chat
            per_chat_shop_rows = shop_rows_by_chat
            if (
                chat_ids is not None
                and not constrain_to_snapshot
                and not any(
                    (
                        auction_rows_by_chat.get(chat_id),
                        arena_rows_by_chat.get(chat_id),
                        shop_rows_by_chat.get(chat_id),
                    )
                )
            ):
                per_chat_auction_rows = {**auction_rows_by_chat, chat_id: all_auction_rows}
                per_chat_arena_rows = {**arena_rows_by_chat, chat_id: all_arena_rows}
                per_chat_shop_rows = {**shop_rows_by_chat, chat_id: all_shop_rows}
            try:
                await _refresh_event_summary_for_chat(
                    chat_id,
                    auction_rows_by_chat=per_chat_auction_rows,
                    arena_rows_by_chat=per_chat_arena_rows,
                    shop_rows_by_chat=per_chat_shop_rows,
                    force_create=force_create,
                )
            except Exception as exc:
                LOGGER.warning(f"xiuxian event summary update failed chat={chat_id}: {exc}")


def _queue_event_summary_refresh(
    chat_ids: int | Iterable[int] | None = None,
    delay_seconds: float = 1.5,
    invalidate_snapshot: bool = True,
    force_create: bool = False,
) -> None:
    global EVENT_SUMMARY_REFRESH_TASK, EVENT_SUMMARY_FORCE_FULL_REFRESH, EVENT_SUMMARY_FORCE_CREATE, EVENT_SUMMARY_REQUEST_TOKEN
    normalized_chat_ids = _normalize_event_summary_chat_ids(chat_ids)
    if normalized_chat_ids:
        EVENT_SUMMARY_DIRTY_CHATS.update(normalized_chat_ids)
    else:
        EVENT_SUMMARY_FORCE_FULL_REFRESH = True
    if force_create:
        EVENT_SUMMARY_FORCE_CREATE = True
    if invalidate_snapshot:
        _invalidate_event_summary_snapshot()
    EVENT_SUMMARY_REQUEST_TOKEN += 1
    existing = EVENT_SUMMARY_REFRESH_TASK
    if existing is not None and not existing.done():
        return

    async def runner() -> None:
        global EVENT_SUMMARY_FORCE_FULL_REFRESH, EVENT_SUMMARY_FORCE_CREATE
        try:
            next_delay = delay_seconds
            while True:
                request_token = EVENT_SUMMARY_REQUEST_TOKEN
                pending_chat_ids = set(EVENT_SUMMARY_DIRTY_CHATS)
                force_full = EVENT_SUMMARY_FORCE_FULL_REFRESH or not pending_chat_ids
                force_create_now = EVENT_SUMMARY_FORCE_CREATE
                if next_delay > 0:
                    await asyncio.sleep(next_delay)
                await _refresh_all_event_summaries(
                    None if force_full else pending_chat_ids,
                    force_snapshot_refresh=True,
                    force_create=force_create_now,
                    constrain_to_snapshot=not force_create_now,
                )
                if EVENT_SUMMARY_REQUEST_TOKEN == request_token:
                    if force_full:
                        EVENT_SUMMARY_FORCE_FULL_REFRESH = False
                        EVENT_SUMMARY_DIRTY_CHATS.clear()
                    else:
                        EVENT_SUMMARY_DIRTY_CHATS.difference_update(pending_chat_ids)
                    EVENT_SUMMARY_FORCE_CREATE = False
                    break
                next_delay = 0.2
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.warning(f"xiuxian event summary queue refresh failed: {exc}")
        finally:
            if EVENT_SUMMARY_REFRESH_TASK is asyncio.current_task():
                globals()["EVENT_SUMMARY_REFRESH_TASK"] = None

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = get_or_create_event_loop()
    EVENT_SUMMARY_REFRESH_TASK = loop.create_task(runner())


def _duel_settlement_total_pages(bet_settlement: dict[str, Any] | None) -> int:
    rows = list((bet_settlement or {}).get("entries") or [])
    return max((len(rows) + DUEL_SETTLEMENT_PAGE_SIZE - 1) // DUEL_SETTLEMENT_PAGE_SIZE, 1)


def _effective_divine_sense(payload: dict[str, Any]) -> int:
    profile = payload.get("profile") or {}
    effective_stats = payload.get("effective_stats") or {}
    return int(effective_stats.get("divine_sense", profile.get("divine_sense", 0)) or 0)


def _duel_profile_label(profile: dict[str, Any] | None) -> str:
    profile = profile or {}
    return (
        str(profile.get("display_name_with_title") or "").strip()
        or str(profile.get("display_label") or "").strip()
        or str(profile.get("display_name") or "").strip()
        or (f"@{profile['username']}" if str(profile.get("username") or "").strip() else f"TG {profile.get('tg', 0)}")
    )


def _duel_side_label(side: str | None) -> str:
    return "挑战者" if side == "challenger" else "应战者"


def _gift_group_broadcast_text(sender_name: str, receiver: dict[str, Any], amount: int) -> str:
    receiver_label = (
        str(receiver.get("display_name_with_title") or "").strip()
        or str(receiver.get("display_label") or "").strip()
        or str(receiver.get("display_name") or "").strip()
        or (f"@{receiver['username']}" if str(receiver.get("username") or "").strip() else f"TG {receiver.get('tg', 0)}")
    )
    return _format_broadcast_card(
        "灵石赠礼",
        emoji="🎁",
        lines=[
            f"👤 赠礼人：{_md_escape(sender_name)}",
            f"🎯 收礼人：{_md_escape(receiver_label)}",
            f"💎 金额：`{int(amount or 0)}` 灵石",
        ],
        footer="✨ 一份机缘已经当众完成交接。",
    )


def _format_attribute_growth_text(changes: list[dict[str, Any]] | None, *, prefix: str = "小幅成长") -> str:
    rows = []
    for item in changes or []:
        label = str(item.get("label") or item.get("key") or "属性").strip()
        value = int(item.get("value") or 0)
        if value <= 0:
            continue
        rows.append(f"{label} +{value}")
    if not rows:
        return ""
    return f"🌱 {prefix}：{' ｜ '.join(rows)}"


def _normalize_commission_command_key(raw: str | None) -> str | None:
    token = str(raw or "").strip()
    if not token:
        return None
    normalized = token.lower()
    return COMMISSION_COMMAND_ALIASES.get(normalized) or COMMISSION_COMMAND_ALIASES.get(token)


def _select_group_commission(bundle: dict[str, Any], requested_key: str | None = None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    commissions = list(bundle.get("commissions") or [])
    if requested_key:
        for item in commissions:
            if str(item.get("key") or "").strip() == requested_key:
                return item, commissions
        return None, commissions
    available = [item for item in commissions if item.get("available")]
    available.sort(
        key=lambda item: (
            int(item.get("reward_stone_max") or 0),
            int(item.get("reward_cultivation_max") or 0),
            int(item.get("min_realm_layer") or 0),
        ),
        reverse=True,
    )
    return (available[0] if available else None), commissions


def _select_group_commissions(bundle: dict[str, Any], requested_key: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    commissions = list(bundle.get("commissions") or [])
    if requested_key:
        selected, rows = _select_group_commission(bundle, requested_key=requested_key)
        if selected and selected.get("available"):
            return [selected], rows
        return [], rows

    available = [item for item in commissions if item.get("available")]
    available.sort(
        key=lambda item: (
            int(item.get("reward_stone_max") or 0),
            int(item.get("reward_cultivation_max") or 0),
            int(item.get("min_realm_layer") or 0),
        ),
        reverse=True,
    )
    return available, commissions


def _commission_selection_error(bundle: dict[str, Any], requested_key: str | None = None) -> str:
    selected, commissions = _select_group_commission(bundle, requested_key=requested_key)
    if selected and selected.get("available"):
        return ""
    if requested_key:
        for item in commissions:
            if str(item.get("key") or "").strip() == requested_key:
                reason = str(item.get("reason") or "").strip() or "当前暂不可承接。"
                return _format_notice_card(
                    "灵石委托未解锁",
                    emoji="🧾",
                    lines=[
                        f"📌 委托：{_md_escape(item.get('name') or '该委托')}",
                        f"⚠️ 原因：{_md_escape(reason)}",
                        "🧭 示例：`/work` ｜ `/work 灵田` ｜ `/work 修剑`",
                    ],
                )
        return _format_notice_card(
            "未找到灵石委托",
            emoji="🧾",
            lines=["🧭 示例：`/work` ｜ `/work 灵田` ｜ `/work 修剑`"],
        )
    locked_rows = commissions[:3]
    if not locked_rows:
        return _format_notice_card("当前暂无可接委托", emoji="🧾", lines=["📭 稍后再来看看新的灵石路子。"])
    preview = [
        f"• {_md_escape(item.get('name') or item.get('key') or '委托')}：{_md_escape(str(item.get('reason') or '暂不可承接').strip())}"
        for item in locked_rows
    ]
    return _format_notice_card(
        "当前暂无可接委托",
        emoji="🧾",
        lines=["📌 最近受限项目：", *preview],
    )


def _minimal_player_lookup_payload(result: dict[str, Any], self_tg: int) -> dict[str, Any]:
    rows = []
    skipped_self = 0
    skipped_secluded = 0
    for item in result.get("items") or []:
        tg_value = int(item.get("tg") or 0)
        if tg_value <= 0:
            continue
        if tg_value == int(self_tg):
            skipped_self += 1
            continue
        if bool(item.get("is_secluded")):
            skipped_secluded += 1
            continue
        username = str(item.get("username") or "").strip().lstrip("@")
        display_name = str(item.get("display_name") or "").strip()
        display_label = display_name or (f"@{username}" if username else f"TG {tg_value}")
        rows.append(
            {
                "tg": tg_value,
                "display_label": display_label,
                "username": username or None,
                "hint": f"@{username}" if username else f"TG {tg_value}",
            }
        )
    total = max(int(result.get("total") or len(rows)) - skipped_self - skipped_secluded, 0)
    return {
        "items": rows,
        "page": int(result.get("page") or 1),
        "page_size": int(result.get("page_size") or len(rows) or 1),
        "total": total,
    }


def _resolve_gift_target_and_amount(msg, inline_amount: int | None = None) -> tuple[int, int]:
    reply_user = getattr(getattr(msg, "reply_to_message", None), "from_user", None)
    args = [str(item).strip() for item in (msg.command or [])[1:] if str(item or "").strip()]
    if inline_amount is not None:
        if reply_user is None:
            raise ValueError("请先回复收礼道友，再使用 /gift100 或 /gift 100。")
        if getattr(reply_user, "is_bot", False):
            raise ValueError("不能给机器人赠送灵石。")
        return int(reply_user.id), int(inline_amount)
    if reply_user is not None and len(args) == 1:
        if getattr(reply_user, "is_bot", False):
            raise ValueError("不能给机器人赠送灵石。")
        return int(reply_user.id), int(args[0])
    if len(args) >= 2:
        return int(args[0]), int(args[1])
    raise ValueError("用法：回复目标后发送 /gift <灵石数量>；或使用 /gift <TGID> <灵石数量>")


def _build_duel_result_private_message(result: dict[str, Any], recipient_tg: int) -> str:
    challenger = (result.get("challenger") or {}).get("profile") or {}
    defender = (result.get("defender") or {}).get("profile") or {}
    is_challenger = int(recipient_tg) == int(challenger.get("tg") or 0)
    recipient = challenger if is_challenger else defender
    opponent = defender if is_challenger else challenger
    won = int(result.get("winner_tg") or 0) == int(recipient_tg)
    lines = [
        "⚔️ **斗法结果通知**",
        f"对手：{_md_escape(_duel_profile_label(opponent))}",
        f"结果：**{'胜出' if won else '落败'}**",
        f"🧾 {_md_escape(str(result.get('summary') or '本场斗法已完成结算。'))}",
    ]

    stake = int(result.get("stake") or 0)
    if stake > 0:
        lines.append(f"{'💰' if won else '💸'} 赌斗结果：{'赢得' if won else '输掉'} `{stake}` 灵石")

    plunder_amount = int(result.get("plunder_amount") or 0)
    if plunder_amount > 0:
        lines.append(f"🪙 额外灵石：{'掠夺' if won else '被掠夺'} `{plunder_amount}` 灵石")

    artifact_payload = ((result.get("artifact_plunder") or {}).get("artifact") or {})
    if artifact_payload:
        artifact_name = artifact_payload.get("name", "未知法宝")
        lines.append(f"🗡️ 法宝结果：{'夺得' if won else '被夺走'} `{_md_escape(artifact_name)}`")

    lines.append(f"📦 当前灵石：`{int(recipient.get('spiritual_stone') or 0)}`")
    return "\n".join(lines)


def _build_duel_bet_private_message(result: dict[str, Any], entry: dict[str, Any]) -> str:
    challenger = (result.get("challenger") or {}).get("profile") or {}
    defender = (result.get("defender") or {}).get("profile") or {}
    winner_tg = int(result.get("winner_tg") or 0)
    winner_profile = challenger if int(challenger.get("tg") or 0) == winner_tg else defender
    won = str(entry.get("result") or "") == "win"
    lines = [
        "🎯 **斗法押注结算**",
        f"对局：{_md_escape(_duel_profile_label(challenger))} vs {_md_escape(_duel_profile_label(defender))}",
        f"胜者：{_md_escape(_duel_profile_label(winner_profile))}",
        f"你押：{_md_escape(_duel_side_label(str(entry.get('side') or '')))}",
        f"下注：`{int(entry.get('bet_amount') or 0)}` 灵石",
        f"结果：**{'押中' if won else '押错'}**",
    ]
    if won:
        lines.append(f"💰 返还：`{int(entry.get('amount') or 0)}` 灵石")
        lines.append(f"📈 净赚：`{int(entry.get('net_profit') or 0)}` 灵石")
    else:
        lines.append(f"📉 净亏：`{abs(int(entry.get('net_profit') or 0))}` 灵石")
    return "\n".join(lines)


async def _notify_duel_participants(result: dict[str, Any]) -> None:
    challenger = (result.get("challenger") or {}).get("profile") or {}
    defender = (result.get("defender") or {}).get("profile") or {}
    for profile in (challenger, defender):
        target_tg = int(profile.get("tg") or 0)
        if target_tg <= 0:
            continue
        try:
            await _send_message(
                bot,
                target_tg,
                _build_duel_result_private_message(result, target_tg),
                persistent=True,
                parse_mode=RICH_TEXT_MODE,
            )
        except Exception as exc:
            LOGGER.warning(f"xiuxian duel participant notify failed tg={target_tg}: {exc}")


async def _notify_duel_bettors(result: dict[str, Any], bet_settlement: dict[str, Any] | None) -> None:
    for entry in list((bet_settlement or {}).get("entries") or []):
        target_tg = int(entry.get("tg") or 0)
        if target_tg <= 0:
            continue
        try:
            await _send_message(
                bot,
                target_tg,
                _build_duel_bet_private_message(result, entry),
                persistent=True,
                parse_mode=RICH_TEXT_MODE,
            )
        except Exception as exc:
            LOGGER.warning(f"xiuxian duel bettor notify failed tg={target_tg}: {exc}")


def _duel_bet_keyboard(pool_id: int) -> InlineKeyboardMarkup | None:
    bet_settings = _duel_bet_settings()
    if not bet_settings["enabled"] or not bet_settings["amount_options"]:
        return None
    rows = []
    for amount in bet_settings["amount_options"]:
        rows.append(
            [
                InlineKeyboardButton(f"押挑战者 {amount}", callback_data=f"xiuxian:bet:{pool_id}:challenger:{amount}"),
                InlineKeyboardButton(f"押应战者 {amount}", callback_data=f"xiuxian:bet:{pool_id}:defender:{amount}"),
            ]
        )
    return InlineKeyboardMarkup(rows)


def _duel_settlement_keyboard(pool_id: int, page: int, total_pages: int) -> InlineKeyboardMarkup | None:
    if total_pages <= 1:
        return None
    rows = [[]]
    if page > 1:
        rows[0].append(InlineKeyboardButton("上一页", callback_data=f"xiuxian:settlement:{pool_id}:{page - 1}"))
    rows[0].append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data=f"xiuxian:settlement:{pool_id}:{page}"))
    if page < total_pages:
        rows[0].append(InlineKeyboardButton("下一页", callback_data=f"xiuxian:settlement:{pool_id}:{page + 1}"))
    return InlineKeyboardMarkup(rows)


def _red_envelope_keyboard(envelope_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("领取红包", callback_data=f"xiuxian:red:{envelope_id}")]]
    )


def _encounter_keyboard(instance_id: int, button_text: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(button_text or "争抢机缘", callback_data=f"xiuxian:encounter:{instance_id}")]]
    )


def _shop_notice_text(item: dict[str, Any]) -> str:
    item = item or {}
    quantity = max(int(item.get("quantity") or 0), 0)
    enabled = bool(item.get("enabled")) and quantity > 0
    status_text = "火热上架" if enabled else "本单已结"
    status_emoji = "🟢" if enabled else "⚪️"
    lines = [
        "🏪 **坊市小铺上新**",
        f"🛍️ 店名：{_md_escape(item.get('shop_name') or '游仙小铺')}",
        f"✨ 商品：**{_md_escape(item.get('item_name') or '未知商品')}**",
        f"📚 类型：`{_md_escape(item.get('item_kind_label') or item.get('item_kind') or '商品')}`",
        f"💰 单价：`{int(item.get('price_stone') or 0)}` 灵石 / 件",
        f"📦 库存：`{quantity}`",
        f"{status_emoji} 状态：{_md_escape(status_text)}",
    ]
    if enabled:
        lines.append("👇 点击下方按钮可直接购买 1 件，成交后库存会自动刷新。")
    else:
        lines.append("📪 本条小铺通知已经结束，按钮会自动关闭。")
    return "\n".join(lines)


def _shop_notice_keyboard(item: dict[str, Any]) -> InlineKeyboardMarkup | None:
    item = item or {}
    if not bool(item.get("enabled")) or int(item.get("quantity") or 0) <= 0:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"🛒 购买 1 件 · {int(item.get('price_stone') or 0)} 灵石", callback_data=f"xiuxian:shop:buy:{int(item.get('id') or 0)}")]]
    )


async def _refresh_shop_notice_message(item: dict[str, Any]) -> None:
    item = item or {}
    chat_id = int(item.get("notice_group_chat_id") or 0)
    message_id = int(item.get("notice_group_message_id") or 0)
    if not chat_id or not message_id:
        return
    try:
        await _edit_message_text(
            bot,
            chat_id,
            message_id,
            _shop_notice_text(item),
            reply_markup=_shop_notice_keyboard(item),
            parse_mode=RICH_TEXT_MODE,
            persistent=True,
        )
    except Exception as exc:
        LOGGER.warning(f"xiuxian shop notice refresh failed item={item.get('id')} chat={chat_id}: {exc}")


async def _push_shop_notice_to_group(item: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    chat_id = int(item.get("notice_group_chat_id") or await _resolve_notice_group_chat_id("shop") or 0)
    if not chat_id:
        raise ValueError("未配置小铺通知群，无法推送商品通知。")
    sent = await _send_message(
        bot,
        chat_id,
        _shop_notice_text(item),
        reply_markup=_shop_notice_keyboard(item),
        parse_mode=RICH_TEXT_MODE,
        persistent=True,
    )
    updated = await run_in_threadpool(
        patch_shop_listing,
        int(item["id"]),
        notice_group_chat_id=chat_id,
        notice_group_message_id=sent.id,
    ) or {
        **item,
        "notice_group_chat_id": chat_id,
        "notice_group_message_id": sent.id,
    }
    _queue_event_summary_refresh(chat_id, delay_seconds=0.2)
    return updated, None


def _auction_time_text(value: str | None) -> str:
    dt = _parse_shanghai_datetime(value)
    if dt is None:
        return str(value or "未设置")
    return dt.strftime("%m-%d %H:%M")


def _auction_group_text(auction: dict[str, Any]) -> str:
    auction = auction or {}
    seller_name = str(auction.get("owner_display_name") or "").strip() or f"TG {auction.get('owner_tg', 0)}"
    item_name = str(auction.get("item_name") or "未知拍品")
    item_kind = str(auction.get("item_kind_label") or auction.get("item_kind") or "拍品")
    quantity = max(int(auction.get("quantity") or 0), 0)
    opening_price = int(auction.get("opening_price_stone") or 0)
    current_price = int(auction.get("current_display_price_stone") or opening_price)
    increment = max(int(auction.get("bid_increment_stone") or 0), 1)
    buyout = int(auction.get("buyout_price_stone") or 0)
    fee_percent = max(int(auction.get("fee_percent") or 0), 0)
    bid_count = max(int(auction.get("bid_count") or 0), 0)
    leader_name = str(auction.get("highest_bidder_display_name") or "").strip()
    winner_name = str(auction.get("winner_display_name") or "").strip()
    end_text = _auction_time_text(auction.get("end_at"))
    status = str(auction.get("status") or "active")

    if status == "sold":
        final_price = int(auction.get("final_price_stone") or current_price)
        fee_amount = int(auction.get("fee_amount_stone") or 0)
        seller_income = int(auction.get("seller_income_stone") or 0)
        winner_label = winner_name or f"TG {auction.get('winner_tg', 0)}"
        return "\n".join(
            [
                "🏁 **拍卖已成交**",
                f"🧿 拍品：**{_md_escape(item_name)}** × `{quantity}`",
                f"👤 卖家：{_md_escape(seller_name)}",
                f"🏆 得主：{_md_escape(winner_label)}",
                f"💰 成交价：`{final_price}` 灵石",
                f"🧾 手续费：`{fee_amount}` 灵石（`{fee_percent}%`）",
                f"📥 卖家到账：`{seller_income}` 灵石",
            ]
        )

    if status == "expired":
        return "\n".join(
            [
                "⌛ **拍卖已流拍**",
                f"🧿 拍品：**{_md_escape(item_name)}** × `{quantity}`",
                f"👤 卖家：{_md_escape(seller_name)}",
                "📭 本场无人出价，拍品已原路退回卖家。",
            ]
        )

    if status == "cancelled":
        return "\n".join(
            [
                "🛑 **拍卖已取消**",
                f"🧿 拍品：**{_md_escape(item_name)}** × `{quantity}`",
                f"👤 卖家：{_md_escape(seller_name)}",
                "♻️ 拍品与竞拍灵石均已按规则退回。",
            ]
        )

    leader_line = f"👑 当前领先：{_md_escape(leader_name)} `({current_price} 灵石)`" if leader_name else "👑 当前领先：暂无"
    buyout_line = f"⚡ 一口价：`{buyout}` 灵石" if buyout > 0 else "⚡ 一口价：未设置"
    return "\n".join(
        [
            "🏺 **群内拍卖进行中**",
            f"🧿 拍品：**{_md_escape(item_name)}** × `{quantity}`",
            f"📚 类型：`{_md_escape(item_kind)}`",
            f"👤 卖家：{_md_escape(seller_name)}",
            f"💰 起拍价：`{opening_price}` 灵石",
            f"📈 当前价：`{current_price}` 灵石",
            f"🔺 加价档：`{increment}` 灵石",
            buyout_line,
            f"🧾 成交手续费：`{fee_percent}%`",
            f"🪧 出价次数：`{bid_count}`",
            f"⏳ 结束时间：`{end_text}`",
            leader_line,
            "👇 点击下方按钮即可出价，竞拍面板会自动刷新。",
        ]
    )


def _auction_bid_button_text(auction: dict[str, Any]) -> str:
    next_bid_price = int(auction.get("next_bid_price_stone") or auction.get("opening_price_stone") or 0)
    if int(auction.get("bid_count") or 0) <= 0:
        return f"出价 {next_bid_price} 灵石"
    return f"加价到 {next_bid_price} 灵石"


def _auction_return_destination_text(auction: dict[str, Any]) -> str:
    item_kind = str((auction or {}).get("item_kind") or "").strip()
    if item_kind == "technique":
        return "功法栏"
    if item_kind == "material":
        return "材料背包"
    if item_kind == "recipe":
        return "配方栏"
    return "背包"


def _auction_keyboard(auction: dict[str, Any]) -> InlineKeyboardMarkup | None:
    auction = auction or {}
    if str(auction.get("status") or "active") != "active":
        return None

    rows = [[InlineKeyboardButton(_auction_bid_button_text(auction), callback_data=f"xiuxian:auction:bid:{auction['id']}")]]
    buyout_price = int(auction.get("buyout_price_stone") or 0)
    current_price = int(auction.get("current_display_price_stone") or 0)
    if buyout_price > 0 and current_price < buyout_price:
        rows.append([InlineKeyboardButton(f"一口价 {buyout_price} 灵石", callback_data=f"xiuxian:auction:buyout:{auction['id']}")])
    return InlineKeyboardMarkup(rows)


async def _refresh_auction_group_message(auction: dict[str, Any]) -> None:
    auction = auction or {}
    chat_id = int(auction.get("group_chat_id") or 0)
    message_id = int(auction.get("group_message_id") or 0)
    if not chat_id or not message_id:
        return
    try:
        await _edit_message_text(
            bot,
            chat_id,
            message_id,
            _auction_group_text(auction),
            reply_markup=_auction_keyboard(auction),
            parse_mode=RICH_TEXT_MODE,
            persistent=True,
        )
    except Exception as exc:
        LOGGER.warning(f"xiuxian auction message refresh failed auction={auction.get('id')} chat={chat_id}: {exc}")


async def _pin_auction_group_message(chat_id: int, message_id: int) -> str | None:
    try:
        await bot.pin_chat_message(chat_id=chat_id, message_id=message_id, disable_notification=True)
    except Exception as exc:
        LOGGER.warning(f"xiuxian auction pin failed chat={chat_id} message={message_id}: {exc}")
        return "拍卖消息已推送到群里，但置顶失败，请检查机器人是否具备置顶权限。"
    return None


async def _unpin_auction_group_message(auction: dict[str, Any]) -> None:
    auction = auction or {}
    chat_id = int(auction.get("group_chat_id") or 0)
    message_id = int(auction.get("group_message_id") or 0)
    if not chat_id or not message_id:
        return
    try:
        await bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
    except Exception as exc:
        LOGGER.warning(f"xiuxian auction unpin failed auction={auction.get('id')} chat={chat_id}: {exc}")


def _drop_auction_finalize_task(auction_id: int) -> None:
    task = AUCTION_FINALIZE_TASKS.pop(int(auction_id), None)
    if task is not None and task is not asyncio.current_task() and not task.done():
        task.cancel()


async def _finalize_auction_flow(result: dict[str, Any] | None) -> None:
    if not result:
        return
    auction = result.get("auction") or {}
    if not auction:
        return
    _drop_auction_finalize_task(int(auction.get("id") or 0))
    await _refresh_auction_group_message(auction)
    await _unpin_auction_group_message(auction)

    outcome = str(result.get("result") or "")
    chat_id = int(auction.get("group_chat_id") or await _resolve_notice_group_chat_id("auction") or 0)
    winner_tg = int(result.get("winner_tg") or 0)
    seller_tg = int(result.get("seller_tg") or 0)
    item_name = str(auction.get("item_name") or "未知拍品")

    if outcome == "sold":
        winner_name = str(result.get("winner_display_name") or auction.get("winner_display_name") or "").strip() or f"TG {winner_tg}"
        final_price = int(auction.get("final_price_stone") or result.get("final_price_stone") or 0)
        seller_income = int(result.get("seller_income_stone") or auction.get("seller_income_stone") or 0)
        fee_amount = int(result.get("fee_amount_stone") or auction.get("fee_amount_stone") or 0)
        if chat_id:
            await _send_message(
                bot,
                chat_id,
                _format_notice_card(
                    "拍卖成交",
                    emoji="🎉",
                    lines=[
                        f"🏆 得主：{_md_escape(winner_name)}",
                        f"🧿 拍品：**{_md_escape(item_name)}**",
                        f"💰 成交价：`{final_price}` 灵石",
                        f"🧾 手续费：`{fee_amount}` 灵石",
                        f"📥 卖家入账：`{seller_income}` 灵石",
                    ],
                ),
                parse_mode=RICH_TEXT_MODE,
                persistent=True,
            )
        if winner_tg > 0:
            try:
                await _send_message(
                    bot,
                    winner_tg,
                    f"🎉 恭喜你拍得【{item_name}】，成交价 {final_price} 灵石。",
                    persistent=True,
                )
            except Exception as exc:
                LOGGER.warning(f"xiuxian auction winner notify failed tg={winner_tg}: {exc}")
        if seller_tg > 0:
            try:
                await _send_message(
                    bot,
                    seller_tg,
                    f"💰 你的拍卖【{item_name}】已成交，到账 {seller_income} 灵石，手续费 {fee_amount} 灵石。",
                    persistent=True,
                )
            except Exception as exc:
                LOGGER.warning(f"xiuxian auction seller notify failed tg={seller_tg}: {exc}")
        _queue_event_summary_refresh(chat_id)
        return

    if outcome == "expired" and seller_tg > 0:
        try:
            destination = _auction_return_destination_text(auction)
            await _send_message(bot, seller_tg, f"⌛ 你的拍卖【{item_name}】已流拍，拍品已退回{destination}。", persistent=True)
        except Exception as exc:
            LOGGER.warning(f"xiuxian auction expire notify failed tg={seller_tg}: {exc}")
    _queue_event_summary_refresh(chat_id)


def _queue_auction_finalize_task(auction: dict[str, Any] | None) -> None:
    auction = auction or {}
    auction_id = int(auction.get("id") or 0)
    if auction_id <= 0 or str(auction.get("status") or "") != "active":
        return
    existing = AUCTION_FINALIZE_TASKS.get(auction_id)
    if existing is not None and not existing.done():
        return
    end_at = _parse_shanghai_datetime(auction.get("end_at"))
    if end_at is None:
        return

    loop = get_or_create_event_loop()

    async def runner() -> None:
        try:
            remaining = max((end_at - datetime.now(SHANGHAI_TZ)).total_seconds(), 0)
            if remaining > 0:
                await asyncio.sleep(remaining)
            result = await run_in_threadpool(finalize_auction_listing, auction_id, force=True)
            if result and str(result.get("result") or "") not in {"noop", ""}:
                await _finalize_auction_flow(result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.warning(f"xiuxian auction finalize task failed auction={auction_id}: {exc}")
        finally:
            task = AUCTION_FINALIZE_TASKS.get(auction_id)
            if task is asyncio.current_task():
                AUCTION_FINALIZE_TASKS.pop(auction_id, None)

    AUCTION_FINALIZE_TASKS[auction_id] = loop.create_task(runner())


def _schedule_active_auction_finalize_tasks() -> None:
    for auction in list_auction_items(status="active"):
        _queue_auction_finalize_task(auction)


async def _push_auction_to_group(auction: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    chat_id = int(auction.get("group_chat_id") or await _resolve_notice_group_chat_id("auction") or 0)
    if not chat_id:
        raise ValueError("未配置拍卖通知群，无法推送拍卖消息。")
    sent = await _send_message(
        bot,
        chat_id,
        _auction_group_text(auction),
        reply_markup=_auction_keyboard(auction),
        parse_mode=RICH_TEXT_MODE,
        persistent=True,
    )
    updated = await run_in_threadpool(
        patch_auction_listing,
        int(auction["id"]),
        group_chat_id=chat_id,
        group_message_id=sent.id,
    ) or {
        **auction,
        "group_chat_id": chat_id,
        "group_message_id": sent.id,
    }
    _queue_auction_finalize_task(updated)
    _queue_event_summary_refresh(chat_id, delay_seconds=0.2)
    return updated, None


def _arena_remaining_text(arena: dict[str, Any]) -> str:
    end_at = _parse_shanghai_datetime(arena.get("end_at"))
    if end_at is None:
        return "未知"
    remaining = max(int((end_at - datetime.now(SHANGHAI_TZ)).total_seconds()), 0)
    if remaining <= 0:
        return "已到时"
    hours, rem = divmod(remaining, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        return f"{hours}时{minutes}分{seconds}秒"
    if minutes > 0:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


def _arena_keyboard(arena: dict[str, Any]) -> InlineKeyboardMarkup | None:
    arena = arena or {}
    if str(arena.get("status") or "") != "active":
        return None
    button_text = "⏳ 有人攻擂中" if bool(arena.get("battle_in_progress")) else "⚔️ 挑战擂台"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(button_text, callback_data=f"xiuxian:arena:challenge:{int(arena.get('id') or 0)}")]]
    )


def _arena_group_text(arena: dict[str, Any]) -> str:
    arena = arena or {}
    arena_stage = str(arena.get("realm_stage") or "炼气").strip() or "炼气"
    champion_tg = int(arena.get("champion_tg") or 0)
    champion_name = str(arena.get("champion_display_name") or "").strip() or f"TG {champion_tg}"
    settings = get_xiuxian_settings()
    arena_open_fee_stone = max(int(settings.get("arena_open_fee_stone", DEFAULT_SETTINGS.get("arena_open_fee_stone", 0)) or 0), 0)
    arena_challenge_fee_stone = max(int(settings.get("arena_challenge_fee_stone", DEFAULT_SETTINGS.get("arena_challenge_fee_stone", 0)) or 0), 0)
    profile = {}
    bundle = {}
    if champion_tg > 0:
        try:
            bundle = serialize_full_profile(champion_tg)
            profile = bundle.get("profile") or {}
            champion_name = _duel_profile_label(profile) or champion_name
        except Exception as exc:
            LOGGER.warning(f"xiuxian arena champion profile load failed tg={champion_tg}: {exc}")
    effective_stats = bundle.get("effective_stats") or {}
    realm_text = "未知境界"
    if profile:
        realm_text = f"{profile.get('realm_stage') or '炼气'}{profile.get('realm_layer') or 0}层"
    combat_power = int(bundle.get("combat_power") or effective_stats.get("attack_power") or profile.get("attack_power") or 0)
    opener_name = str(arena.get("owner_display_name") or "").strip() or champion_name
    challenge_count = int(arena.get("challenge_count") or 0)
    defense_count = int(arena.get("defense_success_count") or 0)
    change_count = int(arena.get("champion_change_count") or 0)
    latest_summary = str(arena.get("latest_result_summary") or "").strip()
    end_at = _parse_shanghai_datetime(arena.get("end_at"))
    end_text = end_at.strftime("%m-%d %H:%M") if end_at else "未知"
    status_label = str(arena.get("status_label") or "开放挑战").strip()
    footer = f"仅限 {arena_stage} 大境界修士点击下方按钮攻擂，修为过高或过低都无法参加。"
    if str(arena.get("status") or "") != "active":
        footer = "本期擂台已经落幕，等待下一位擂主重新开坛。"
    return "\n".join(
        [
            f"🏟️ **{_md_escape(arena_stage)}擂台开启**",
            f"🎯 准入：仅限 `{_md_escape(arena_stage)}` 修士",
            f"👑 当前擂主：{_md_escape(champion_name)}",
            f"🏯 擂主境界：{_md_escape(realm_text)}",
            f"⚔️ 擂主战力：`{combat_power}`",
            f"📣 开擂者：{_md_escape(opener_name)}",
            f"🛡️ 守擂成功：`{defense_count}` ｜ 🔁 易主：`{change_count}`",
            f"⚔️ 总挑战：`{challenge_count}`",
            f"⏳ 状态：{_md_escape(status_label)} ｜ 剩余：`{_arena_remaining_text(arena)}`",
            "🎁 实战修为会在每场攻擂后即时结算，胜负与对手强度都会影响收益",
            (
                f"🎫 手续费：开擂 `{arena_open_fee_stone}` 灵石 ｜ 攻擂 `{arena_challenge_fee_stone}` 灵石"
                if arena_open_fee_stone > 0 or arena_challenge_fee_stone > 0
                else "🎫 手续费：当前未收取开擂 / 攻擂手续费"
            ),
            f"🕰️ 结算时刻：`{end_text}`",
            (f"📝 最新战报：{_md_escape(latest_summary)}" if latest_summary else "📝 最新战报：尚无人攻擂，擂主正在静候群雄。"),
            f"👇 {footer}",
        ]
    )


async def _refresh_arena_group_message(arena: dict[str, Any]) -> None:
    arena = arena or {}
    chat_id = int(arena.get("group_chat_id") or 0)
    message_id = int(arena.get("group_message_id") or 0)
    if not chat_id or not message_id:
        return
    try:
        text = await run_in_threadpool(_arena_group_text, arena)
        await _edit_message_text(
            bot,
            chat_id,
            message_id,
            text,
            reply_markup=_arena_keyboard(arena),
            parse_mode=RICH_TEXT_MODE,
            persistent=True,
        )
    except Exception as exc:
        LOGGER.warning(f"xiuxian arena message refresh failed arena={arena.get('id')} chat={chat_id}: {exc}")


async def _pin_arena_group_message(chat_id: int, message_id: int) -> str | None:
    try:
        await bot.pin_chat_message(chat_id=chat_id, message_id=message_id, disable_notification=True)
    except Exception as exc:
        LOGGER.warning(f"xiuxian arena pin failed chat={chat_id} message={message_id}: {exc}")
        return "擂台消息已推送到群里，但置顶失败，请检查机器人是否具备置顶权限。"
    return None


async def _unpin_arena_group_message(arena: dict[str, Any]) -> None:
    arena = arena or {}
    chat_id = int(arena.get("group_chat_id") or 0)
    message_id = int(arena.get("group_message_id") or 0)
    if not chat_id or not message_id:
        return
    try:
        await bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
    except Exception as exc:
        LOGGER.warning(f"xiuxian arena unpin failed arena={arena.get('id')} chat={chat_id}: {exc}")


def _drop_arena_finalize_task(arena_id: int) -> None:
    task = ARENA_FINALIZE_TASKS.pop(int(arena_id), None)
    if task is not None and task is not asyncio.current_task() and not task.done():
        task.cancel()


async def _finalize_arena_flow(result: dict[str, Any] | None) -> None:
    if not result:
        return
    arena = result.get("arena") or {}
    if not arena:
        return
    _drop_arena_finalize_task(int(arena.get("id") or 0))
    await _refresh_arena_group_message(arena)
    await _unpin_arena_group_message(arena)

    outcome = str(result.get("result") or "")
    chat_id = int(arena.get("group_chat_id") or await _resolve_notice_group_chat_id("arena") or 0)
    if chat_id and outcome == "finished":
        await _send_message(
            bot,
            chat_id,
            _format_notice_card(
                "擂台落幕",
                emoji="🏁",
                lines=[
                    f"🏟️ 境界：`{_md_escape(arena.get('realm_stage') or '炼气')}`",
                    f"👑 最终擂主：{_md_escape(result.get('champion_name') or arena.get('champion_display_name') or '未知擂主')}",
                    f"🛡️ 守擂成功：`{int(result.get('defense_success_count') or 0)}`",
                    f"⚔️ 总挑战：`{int(result.get('challenge_count') or 0)}`",
                    f"💎 期满灵石：`+{int(result.get('stone_reward') or 0)}`",
                    f"🌿 期满修为：`+{int(result.get('cultivation_reward') or 0)}`",
                ],
            ),
            parse_mode=RICH_TEXT_MODE,
            persistent=True,
        )
    elif chat_id and outcome == "finished_no_reward":
        await _send_message(
            bot,
            chat_id,
            _format_notice_card(
                "擂台落幕",
                emoji="🏁",
                lines=[
                    "⌛ 本期擂台虽然到时，但最终已无合格擂主可领取奖励。",
                    "🔁 待下次有人重新开擂，再看谁能守到最后。",
                ],
            ),
            parse_mode=RICH_TEXT_MODE,
            persistent=True,
        )
    elif chat_id and outcome == "cancelled":
        await _send_message(
            bot,
            chat_id,
            "🛑 **本期擂台已取消**",
            parse_mode=RICH_TEXT_MODE,
            persistent=True,
        )

    await _notify_achievement_unlocks(result.get("achievement_unlocks"))
    _queue_event_summary_refresh(chat_id)


def _queue_arena_finalize_task(arena: dict[str, Any] | None) -> None:
    arena = arena or {}
    arena_id = int(arena.get("id") or 0)
    if arena_id <= 0 or str(arena.get("status") or "") != "active":
        return
    existing = ARENA_FINALIZE_TASKS.get(arena_id)
    if existing is not None and not existing.done():
        return
    end_at = _parse_shanghai_datetime(arena.get("end_at"))
    if end_at is None:
        return

    loop = get_or_create_event_loop()

    async def runner() -> None:
        try:
            remaining = max((end_at - datetime.now(SHANGHAI_TZ)).total_seconds(), 0)
            if remaining > 0:
                await asyncio.sleep(remaining)
            while True:
                result = await run_in_threadpool(finalize_group_arena, arena_id, force=True)
                if not result:
                    break
                if str(result.get("result") or "") == "busy":
                    await asyncio.sleep(5)
                    continue
                if str(result.get("result") or "") not in {"noop", ""}:
                    await _finalize_arena_flow(result)
                break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.warning(f"xiuxian arena finalize task failed arena={arena_id}: {exc}")
        finally:
            task = ARENA_FINALIZE_TASKS.get(arena_id)
            if task is asyncio.current_task():
                ARENA_FINALIZE_TASKS.pop(arena_id, None)

    ARENA_FINALIZE_TASKS[arena_id] = loop.create_task(runner())


def _schedule_active_arena_finalize_tasks() -> None:
    for arena in list_group_arenas(status="active"):
        _queue_arena_finalize_task(arena)


async def _push_arena_to_group(arena: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    chat_id = int(arena.get("group_chat_id") or await _resolve_notice_group_chat_id("arena") or 0)
    if not chat_id:
        raise ValueError("未配置擂台通知群，无法推送擂台消息。")
    text = await run_in_threadpool(_arena_group_text, arena)
    sent = await _send_message(
        bot,
        chat_id,
        text,
        reply_markup=_arena_keyboard(arena),
        parse_mode=RICH_TEXT_MODE,
        persistent=True,
    )
    updated = await run_in_threadpool(
        patch_group_arena,
        int(arena["id"]),
        group_chat_id=chat_id,
        group_message_id=sent.id,
    ) or {
        **arena,
        "group_chat_id": chat_id,
        "group_message_id": sent.id,
    }
    _queue_arena_finalize_task(updated)
    _queue_event_summary_refresh(chat_id, delay_seconds=0.2)
    return updated, None


def _quiz_task_text(task: dict[str, Any]) -> str:
    reward_lines = _task_reward_lines(task)
    scale_line = "📈 奖励按完成者当前境界折算" if str(task.get("reward_scale_mode") or "fixed") == "realm" else ""
    return _format_notice_card(
        "答题悬赏",
        emoji="🧩",
        lines=[
            f"📌 范围：{_md_escape(task.get('task_scope_label') or '官方任务')}",
            f"🧭 标题：**{_md_escape(task['title'])}**",
            f"📝 说明：{_md_escape(task.get('description') or '请完成任务后领取奖励。')}",
            f"❓ 题目：{_md_escape(task.get('question_text') or '请直接在群里回复正确答案。')}",
            *( [scale_line] if scale_line else [] ),
            "🎁 奖励：",
            *reward_lines,
        ],
        footer="🥇 首位答对的道友即可完成任务并领取奖励。",
    )


def _task_required_lines(task: dict[str, Any]) -> list[str]:
    if str(task.get("task_type") or "") == "metric":
        metric_label = task.get("metric_label") or task.get("requirement_metric_key") or "计数指标"
        metric_target = int(task.get("requirement_metric_target") or task.get("metric_target") or 0)
        if metric_target > 0:
            return [f"• {_md_escape(metric_label)} 累计达到 `{metric_target}` 次"]
        return []
    if not task.get("required_item_kind") or not int(task.get("required_item_quantity") or 0):
        return []
    item = task.get("required_item") or {}
    item_name = item.get("name") or task.get("required_item_kind_label") or task.get("required_item_kind") or "物品"
    return [f"• 提交 `{int(task.get('required_item_quantity') or 0)}` 个 {_md_escape(item_name)}"]


def _task_reward_lines(task: dict[str, Any]) -> list[str]:
    reward_parts: list[str] = []
    if int(task.get("reward_stone") or 0):
        reward_parts.append(f"• 💎 `+{int(task['reward_stone'])}` 灵石")
    if int(task.get("reward_cultivation") or 0):
        reward_parts.append(f"• 📈 `+{int(task['reward_cultivation'])}` 修为")
    if task.get("reward_item_kind") and task.get("reward_item_quantity"):
        reward_item = task.get("reward_item") or {}
        reward_name = reward_item.get("name") or task.get("reward_item_kind_label") or task.get("reward_item_kind")
        reward_parts.append(f"• 🎒 `{int(task['reward_item_quantity'])}` 个 {_md_escape(reward_name)}")
    reward_text = reward_parts or ["• 暂未设置奖励"]
    if str(task.get("reward_scale_mode") or "fixed") == "realm":
        reward_text.append("• 📐 奖励会按完成者当前境界折算")
    return reward_text


def _task_group_text(task: dict[str, Any]) -> str:
    if task.get("task_type") == "quiz":
        return _quiz_task_text(task)

    reward_lines = _task_reward_lines(task)
    required_lines = _task_required_lines(task)
    return _format_notice_card(
        "悬赏委托",
        emoji="📜",
        lines=[
            f"📌 范围：{_md_escape(task.get('task_scope_label') or '任务')}",
            f"🧭 标题：**{_md_escape(task['title'])}**",
            f"📝 说明：{_md_escape(task.get('description') or '请前往修仙面板领取或完成任务。')}",
            *(["📦 要求：", *required_lines] if required_lines else []),
            "🎁 奖励：",
            *reward_lines,
        ],
        footer="🧭 道友们可前往修仙面板查看详情。",
    )


def _split_photo_caption(text: str, limit: int = 1024) -> tuple[str, str]:
    content = str(text or "").strip()
    if len(content) <= limit:
        return content, ""
    lines = content.split("\n")
    head_lines: list[str] = []
    current_length = 0
    for index, line in enumerate(lines):
        addition = len(line) if not head_lines else len(line) + 1
        if head_lines and current_length + addition > limit:
            return "\n".join(head_lines).rstrip(), "\n".join(lines[index:]).lstrip()
        if not head_lines and addition > limit:
            break
        head_lines.append(line)
        current_length += addition
    candidate = content[:limit]
    cut = -1
    for marker in ("\n\n", "\n", "。", "，", " "):
        pos = candidate.rfind(marker)
        if pos >= int(limit * 0.6):
            cut = pos + len(marker)
            break
    if cut <= 0:
        cut = limit
    head = content[:cut].rstrip()
    tail = content[cut:].lstrip()
    return head, tail


async def _build_red_envelope_generated_cover(envelope: dict[str, Any]) -> BytesIO | None:
    sender_name = "道友"
    sender_photo = None
    creator_tg = int(envelope.get("creator_tg") or 0)
    if creator_tg:
        try:
            telegram_user = await bot.get_users(creator_tg)
            identity = _telegram_identity_payload(telegram_user)
            sender_name = identity.get("display_name") or identity.get("username") or sender_name
            photo = getattr(telegram_user, "photo", None)
            file_id = getattr(photo, "big_file_id", None)
            if file_id:
                sender_photo = await bot.download_media(file_id, in_memory=True)
        except Exception as exc:
            LOGGER.warning(f"xiuxian red envelope cover fallback failed tg={creator_tg}: {exc}")
    try:
        cover = await RanksDraw.hb_test_draw(
            max(int(envelope.get("amount_total") or 0), 1),
            max(int(envelope.get("count_total") or 1), 1),
            user_pic=sender_photo,
            first_name=(sender_name or "道友")[:12],
        )
    except Exception as exc:
        LOGGER.warning(f"xiuxian red envelope generated cover failed envelope={envelope.get('id')}: {exc}")
        return None
    if isinstance(cover, BytesIO):
        cover.name = "xiuxian_red_envelope.png"
        cover.seek(0)
    return cover if isinstance(cover, BytesIO) else None


async def _red_envelope_notice_photo(envelope: dict[str, Any]) -> str | Path | BytesIO | None:
    image_source = _resolve_group_image_source(envelope.get("image_url"))
    if image_source:
        return image_source
    return await _build_red_envelope_generated_cover(envelope)


def _red_envelope_notice_text(envelope: dict[str, Any], claims: list[dict[str, Any]] | None = None) -> str:
    lines = [
        "🧧 **灵石红包**",
        f"🖼️ 封面：{_md_escape(envelope.get('cover_text') or '福运临门')}",
        f"🎛️ 模式：{_md_escape(envelope.get('mode_label') or envelope.get('mode'))}",
        f"💎 总额：`{envelope.get('amount_total')}` 灵石",
        f"🧩 红包数：`{envelope.get('count_total')}` 个",
    ]
    target_tg = int(envelope.get("target_tg") or 0)
    if target_tg:
        target_label = str(envelope.get("target_display_name") or "").strip() or f"TG {target_tg}"
        lines.append(f"🎯 专属对象：{_md_escape(target_label)}")
    if claims is None:
        lines.append("👇 道友们请点击下方按钮领取红包。")
        return "\n".join(lines)
    lines.append(f"📦 剩余灵石：`{envelope.get('remaining_amount')}`")
    lines.append(f"🧾 剩余份数：`{envelope.get('remaining_count')}`")
    if claims:
        claim_lines = []
        for row in claims[-5:]:
            claimant_name = row.get("name") or f"TG {row['tg']}"
            claim_lines.append(f"• {_md_escape(claimant_name)}：`{row['amount']}` 灵石")
        lines.append("📜 最近领取记录：")
        lines.extend(claim_lines)
    else:
        lines.append("📜 最近领取记录：暂无")
    return "\n".join(lines)


async def _push_quiz_task(task: dict[str, Any]) -> dict[str, Any] | None:
    chat_id = int(task.get("group_chat_id") or _main_group_chat_id() or 0)
    if not chat_id:
        return None
    text = _task_group_text(task)
    image_source = _resolve_group_image_source(task.get("image_url"))
    if image_source:
        caption, overflow = _split_photo_caption(text)
        try:
            sent = await _send_photo(
                bot,
                chat_id,
                image_source,
                caption=caption or None,
                parse_mode=RICH_TEXT_MODE,
                persistent=True,
            )
        except Exception as exc:
            LOGGER.warning(f"xiuxian task photo push fallback task={task.get('id')} chat={chat_id}: {exc}")
            sent = await _send_photo(bot, chat_id, image_source, persistent=True)
            overflow = text
        if overflow:
            await _send_message(
                bot,
                chat_id,
                overflow,
                reply_to_message_id=sent.id,
                parse_mode=RICH_TEXT_MODE,
                persistent=True,
            )
    else:
        sent = await _send_message(bot, chat_id, text, parse_mode=RICH_TEXT_MODE, persistent=True)
    return await run_in_threadpool(mark_task_group_message, task["id"], chat_id, sent.id)


async def _push_task_to_group(task: dict[str, Any]) -> dict[str, Any] | None:
    return await _push_quiz_task(task)


async def _safe_push_task_to_group(task: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    try:
        pushed_task = await _push_task_to_group(task)
        return pushed_task or task, None
    except Exception as exc:
        LOGGER.warning(f"xiuxian task push failed task={task.get('id')} chat={task.get('group_chat_id')}: {exc}")
        return task, "任务已创建，但群内推送失败。Telegram 当前可能波动，请稍后重试。"


async def _push_red_envelope_notice(envelope: dict[str, Any]) -> None:
    chat_id = int(envelope.get("group_chat_id") or _main_group_chat_id() or 0)
    if not chat_id:
        return
    text = _red_envelope_notice_text(envelope)
    photo = await _red_envelope_notice_photo(envelope)
    if photo:
        caption, overflow = _split_photo_caption(text)
        try:
            sent = await _send_photo(
                bot,
                chat_id,
                photo,
                caption=caption or None,
                reply_markup=_red_envelope_keyboard(envelope["id"]),
                parse_mode=RICH_TEXT_MODE,
                persistent=True,
            )
        except Exception as exc:
            LOGGER.warning(f"xiuxian red envelope photo push fallback envelope={envelope.get('id')} chat={chat_id}: {exc}")
            sent = await _send_message(
                bot,
                chat_id,
                text,
                reply_markup=_red_envelope_keyboard(envelope["id"]),
                parse_mode=RICH_TEXT_MODE,
                persistent=True,
            )
        else:
            if overflow:
                await _send_message(
                    bot,
                    chat_id,
                    overflow,
                    reply_to_message_id=sent.id,
                    parse_mode=RICH_TEXT_MODE,
                    persistent=True,
                )
    else:
        sent = await _send_message(
            bot,
            chat_id,
            text,
            reply_markup=_red_envelope_keyboard(envelope["id"]),
            parse_mode=RICH_TEXT_MODE,
            persistent=True,
        )
    LOGGER.info(f"xiuxian red envelope sent to group {chat_id}, message={sent.id}")


async def _push_group_encounter_notice(payload: dict[str, Any]) -> dict[str, Any] | None:
    template = payload.get("template") or {}
    instance = payload.get("instance") or {}
    chat_id = int(instance.get("group_chat_id") or _main_group_chat_id() or 0)
    if not chat_id:
        return None
    ENCOUNTER_AUTO_CHAT_STATE[chat_id] = True
    text = render_group_encounter_text(template, instance)
    image_source = _resolve_group_image_source(template.get("image_url"))
    if image_source:
        caption, overflow = _split_photo_caption(text)
        try:
            sent = await _send_photo(
                bot,
                chat_id,
                image_source,
                caption=caption or None,
                reply_markup=_encounter_keyboard(instance["id"], instance.get("button_text")),
                parse_mode=RICH_TEXT_MODE,
                persistent=True,
            )
        except Exception as exc:
            LOGGER.warning(f"xiuxian encounter photo push fallback id={instance.get('id')} chat={chat_id}: {exc}")
            sent = await _send_photo(bot, chat_id, image_source, persistent=True)
            overflow = text
        if overflow:
            await _send_message(
                bot,
                chat_id,
                overflow,
                reply_to_message_id=sent.id,
                reply_markup=_encounter_keyboard(instance["id"], instance.get("button_text")),
                parse_mode=RICH_TEXT_MODE,
                persistent=True,
            )
    else:
        sent = await _send_message(
            bot,
            chat_id,
            text,
            reply_markup=_encounter_keyboard(instance["id"], instance.get("button_text")),
            parse_mode=RICH_TEXT_MODE,
            persistent=True,
        )
    return await run_in_threadpool(mark_group_encounter_message, int(instance["id"]), int(sent.id))


async def _maybe_broadcast_craft(actor_tg: int, result: dict[str, Any]) -> None:
    if not result.get("should_broadcast"):
        return
    chat_id = _main_group_chat_id()
    if not chat_id:
        return
    result_item = result.get("result_item") or {}
    item_name = result_item.get("name") or "未知物品"
    quality_label = str(result_item.get("quality_label") or result_item.get("rarity") or f"{int(result.get('result_quality') or 0)}阶").strip()
    actor_profile = (await run_in_threadpool(serialize_full_profile, actor_tg) or {}).get("profile") or {}
    success_count = max(int(result.get("success_count") or 0), 0)
    failure_count = max(int(result.get("failure_count") or 0), 0)
    total_quantity = max(int(result.get("total_reward_quantity") or 0), 0)
    recipe_name = str((result.get("recipe") or {}).get("name") or "未知配方").strip()
    await _send_message(
        bot,
        chat_id,
        _format_broadcast_card(
            "天地异象显化",
            emoji="🌠",
            lines=[
                f"🧑‍🏭 炼制者：{_md_escape(_duel_profile_label(actor_profile))}",
                f"📜 配方：{_md_escape(recipe_name)}",
                f"🎁 成品：**{_md_escape(item_name)}** × `{total_quantity or max(success_count, 1)}`",
                f"✨ 品阶：`{_md_escape(quality_label or '高品')}`",
                f"🔥 炉次：成功 `{success_count}` ｜ 失败 `{failure_count}`",
            ],
            footer="🎉 高品质成品出炉，群中灵机为之一振。",
        ),
        parse_mode=RICH_TEXT_MODE,
    )


async def _maybe_broadcast_gambling(actor_tg: int, result: dict[str, Any]) -> None:
    rare_rows = [row for row in (result.get("summary") or result.get("results") or []) if row.get("broadcasted")]
    if not rare_rows:
        return
    chat_id = _main_group_chat_id()
    if not chat_id:
        return
    actor_profile = (await run_in_threadpool(serialize_full_profile, actor_tg) or {}).get("profile") or {}
    opened_count = max(int(result.get("opened_count") or 0), 0)
    fortune_hint = str(result.get("fortune_hint") or "").strip()
    lines = [
        f"🧑‍🎲 开石者：{_md_escape(_duel_profile_label(actor_profile))}",
        f"🪨 本次开启：`{opened_count}` 枚仙界奇石",
        (f"🍀 机缘提示：{_md_escape(fortune_hint)}" if fortune_hint else "🍀 机缘提示：本次未额外显示机缘说明"),
        "🌠 **稀有收获**",
    ]
    for row in rare_rows[:5]:
        quality_label = str(row.get("quality_label") or "凡品").strip() or "凡品"
        item_name = str(row.get("item_name") or "未知物品").strip() or "未知物品"
        quantity = max(int(row.get("quantity") or 0), 1)
        lines.append(f"• `{_md_escape(quality_label)}` ｜ **{_md_escape(item_name)}** × `{quantity}`")
    if len(rare_rows) > 5:
        lines.append(f"• 其余还有 `{len(rare_rows) - 5}` 项高品奖励")
    await _send_message(
        bot,
        chat_id,
        _format_broadcast_card(
            "赌坊异象",
            emoji="🎰",
            lines=lines,
            footer="🎉 群播已记录本次高品掉落，道友们快来围观手气。",
        ),
        parse_mode=RICH_TEXT_MODE,
    )


def _admin_world_snapshot() -> dict[str, Any]:
    sects = list_sects()
    for sect in sects:
        sect["roles"] = list_sect_roles(sect["id"])
    recipes = build_recipe_catalog()
    scenes = list_scenes()
    for scene in scenes:
        scene["drops"] = list_scene_drops(scene["id"])
    return {
        "sects": sects,
        "materials": list_materials(),
        "recipes": recipes,
        "scenes": scenes,
        "encounters": list_encounter_templates(),
        "bosses": list_boss_configs(enabled_only=False),
        "mentorships": list_admin_mentorships(),
        "mentorship_requests": list_admin_mentorship_requests(),
        "marriages": list_admin_marriages(),
        "marriage_requests": list_admin_marriage_requests(),
        "tasks": list_tasks(),
        "auctions": list_auction_items(include_inactive=True, limit=100),
        "techniques": list_techniques(),
        "titles": list_titles(),
        "achievements": list_achievements(),
        "artifact_sets": list_artifact_sets(),
        "achievement_metric_presets": ACHIEVEMENT_METRIC_PRESETS,
        "upload_permissions": list_image_upload_permissions(),
        "error_logs": list_error_logs(limit=100),
    }


def _parse_shanghai_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(SHANGHAI_TZ)


def _duel_refresh_interval(remaining_seconds: int | None = None) -> int:
    if remaining_seconds is None:
        return 15
    if remaining_seconds > 180:
        return 45
    if remaining_seconds > 60:
        return 30
    if remaining_seconds > 20:
        return 15
    return 8


def _normalize_duel_mode_arg(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    aliases = {
        "": "standard",
        "standard": "standard",
        "normal": "standard",
        "master": "master",
        "furnace": "master",
        "slave": "master",
        "servant": "master",
        "主仆": "master",
        "炉鼎": "master",
        "death": "death",
        "dead": "death",
        "生死": "death",
    }
    return aliases.get(value, "standard")


def _duel_mode_emoji(mode: str | None) -> str:
    return {
        "standard": "⚔️",
        "master": "⛓️",
        "death": "☠️",
    }.get(_normalize_duel_mode_arg(mode), "⚔️")


def _duel_mode_label(mode: str | None) -> str:
    return {
        "standard": "斗法",
        "master": "炉鼎对决",
        "death": "生死斗",
    }.get(_normalize_duel_mode_arg(mode), "斗法")


def _duel_invite_timeout_seconds(settings: dict[str, Any] | None = None) -> int:
    source = settings if isinstance(settings, dict) else get_xiuxian_settings()
    raw = source.get("duel_invite_timeout_seconds", DEFAULT_SETTINGS.get("duel_invite_timeout_seconds", 90))
    return min(max(int(raw or DEFAULT_SETTINGS.get("duel_invite_timeout_seconds", 90)), 10), 1800)


def _format_duration_seconds(total_seconds: int) -> str:
    seconds = max(int(total_seconds or 0), 0)
    if seconds <= 0:
        return "0 秒"
    hours, rem = divmod(seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    parts: list[str] = []
    if hours > 0:
        parts.append(f"{hours} 小时")
    if minutes > 0:
        parts.append(f"{minutes} 分")
    if seconds > 0 or not parts:
        parts.append(f"{seconds} 秒")
    return "".join(parts)


def _duel_bet_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    source = settings if isinstance(settings, dict) else get_xiuxian_settings()
    options: list[int] = []
    for value in list(source.get("duel_bet_amount_options") or []):
        try:
            amount = int(value or 0)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            options.append(amount)
    minimum = max(int(source.get("duel_bet_min_amount", DEFAULT_SETTINGS.get("duel_bet_min_amount", 10)) or 0), 1)
    maximum = max(int(source.get("duel_bet_max_amount", DEFAULT_SETTINGS.get("duel_bet_max_amount", 100)) or 0), minimum)
    if not options:
        midpoint = (minimum + maximum) // 2
        options = [minimum]
        if midpoint not in {minimum, maximum}:
            options.append(midpoint)
        if maximum != minimum:
            options.append(maximum)
    return {
        "enabled": bool(source.get("duel_bet_enabled", DEFAULT_SETTINGS.get("duel_bet_enabled", True))),
        "seconds": min(max(int(source.get("duel_bet_seconds", DEFAULT_SETTINGS.get("duel_bet_seconds", 120)) or 0), 10), 3600),
        "min_amount": minimum,
        "max_amount": maximum,
        "amount_options": sorted(set(options)),
    }


def _duel_invite_key(chat_id: Any, message_id: Any) -> tuple[int, int] | None:
    if chat_id is None or message_id is None:
        return None
    return (int(chat_id), int(message_id))


def _duel_invite_message_key(message: Any) -> tuple[int, int] | None:
    return _duel_invite_key(
        getattr(getattr(message, "chat", None), "id", None),
        getattr(message, "id", None),
    )


def _duel_invite_matches(
    invite: dict[str, Any] | None,
    *,
    challenger_tg: int,
    defender_tg: int,
    duel_mode: str,
    stake: int,
    bet_seconds: int,
) -> bool:
    if not isinstance(invite, dict):
        return False
    return (
        int(invite.get("challenger_tg") or 0) == int(challenger_tg)
        and int(invite.get("defender_tg") or 0) == int(defender_tg)
        and int(invite.get("stake") or 0) == int(stake)
        and int(invite.get("bet_seconds") or 0) == int(bet_seconds)
        and _normalize_duel_mode_arg(invite.get("duel_mode")) == _normalize_duel_mode_arg(duel_mode)
    )


def _get_pending_duel_invite(
    message: Any,
    *,
    challenger_tg: int,
    defender_tg: int,
    duel_mode: str,
    stake: int,
    bet_seconds: int,
) -> tuple[tuple[int, int] | None, dict[str, Any] | None]:
    key = _duel_invite_message_key(message)
    if key is None:
        return None, None
    invite = PENDING_DUEL_INVITES.get(key)
    if not _duel_invite_matches(
        invite,
        challenger_tg=challenger_tg,
        defender_tg=defender_tg,
        duel_mode=duel_mode,
        stake=stake,
        bet_seconds=bet_seconds,
    ):
        return key, None
    return key, invite


def _cancel_pending_duel_invite_task(task: asyncio.Task | None) -> None:
    if task is None or task.done() or task is asyncio.current_task():
        return
    task.cancel()


def _pop_pending_duel_invite(key: tuple[int, int] | None) -> dict[str, Any] | None:
    if key is None:
        return None
    invite = PENDING_DUEL_INVITES.pop(key, None)
    if invite:
        _cancel_pending_duel_invite_task(invite.get("task"))
    return invite


def _format_duel_invite_footer(timeout_seconds: int, bet_settings: dict[str, Any]) -> str:
    if not bet_settings.get("enabled", True):
        bet_line = "🎲 当前后台已关闭赌斗下注，接受后将直接开战。"
    else:
        amount_options = " / ".join(str(value) for value in list(bet_settings.get("amount_options") or []))
        bet_line = (
            f"🎲 接受后将开放 `{_format_duration_seconds(int(bet_settings.get('seconds') or 0))}` 押注。"
            f"\n💰 下注范围 `{int(bet_settings.get('min_amount') or 0)}` - `{int(bet_settings.get('max_amount') or 0)}` 灵石"
            f"；挡位 `{amount_options}`。"
        )
    return "\n".join(
        [
            "",
            f"⏳ 请应战者在 `{timeout_seconds}` 秒内作出回应，超时将自动撤销邀请。",
            bet_line,
            "🛑 发起者可点击下方按钮主动撤回本场邀请。",
        ]
    )


def _format_duel_invite_closed_text(mode: str, headline: str, detail_lines: list[str]) -> str:
    return "\n".join([f"{_duel_mode_emoji(mode)} **{headline}**", "", *detail_lines])


async def _expire_duel_invite(chat_id: int, message_id: int, duel_mode: str, timeout_seconds: int) -> None:
    try:
        await asyncio.sleep(max(int(timeout_seconds or 0), 1))
    except asyncio.CancelledError:
        return

    key = _duel_invite_key(chat_id, message_id)
    invite = _pop_pending_duel_invite(key)
    if invite is None:
        return

    try:
        await _edit_message_text(
            bot,
            chat_id,
            message_id,
            _format_duel_invite_closed_text(
                duel_mode,
                f"{_duel_mode_label(duel_mode)}邀请已超时撤销",
                [
                    f"对方未在 `{timeout_seconds}` 秒内应战，本场邀请已自动失效。",
                    "📭 发起者可重新发起新的挑战。",
                ],
            ),
            persistent=True,
            reply_markup=None,
            parse_mode=RICH_TEXT_MODE,
        )
    except Exception as exc:
        LOGGER.warning(f"xiuxian duel invite timeout update failed chat={chat_id} message={message_id}: {exc}")


def _register_pending_duel_invite(
    message: Any,
    *,
    challenger_tg: int,
    defender_tg: int,
    duel_mode: str,
    stake: int,
    bet_seconds: int,
    timeout_seconds: int,
) -> None:
    key = _duel_invite_message_key(message)
    if key is None:
        return
    _pop_pending_duel_invite(key)
    PENDING_DUEL_INVITES[key] = {
        "challenger_tg": int(challenger_tg),
        "defender_tg": int(defender_tg),
        "duel_mode": _normalize_duel_mode_arg(duel_mode),
        "stake": int(stake),
        "bet_seconds": int(bet_seconds),
        "timeout_seconds": int(timeout_seconds),
        "task": asyncio.create_task(
            _expire_duel_invite(
                key[0],
                key[1],
                duel_mode=_normalize_duel_mode_arg(duel_mode),
                timeout_seconds=int(timeout_seconds),
            )
        ),
    }


def _duel_log_emoji(kind: str | None) -> str:
    return {
        "opening": "🌀",
        "round": "⏱️",
        "dot": "🔥",
        "dodge": "💨",
        "shield": "🛡️",
        "state": "📊",
        "finish": "🏁",
    }.get(str(kind or "").strip(), "⚔️")


def _latest_visible_duel_statuses(result: dict[str, Any], visible_count: int) -> tuple[dict[str, Any], dict[str, Any]]:
    challenger_status: dict[str, Any] = {}
    defender_status: dict[str, Any] = {}
    battle_log = list(result.get("battle_log") or [])
    shown = min(max(int(visible_count or 0), 0), len(battle_log))
    for row in reversed(battle_log[:shown]):
        if not challenger_status and isinstance(row.get("challenger_status"), dict):
            challenger_status = dict(row.get("challenger_status") or {})
        if not defender_status and isinstance(row.get("defender_status"), dict):
            defender_status = dict(row.get("defender_status") or {})
        if challenger_status and defender_status:
            break
    return challenger_status, defender_status


def _duel_snapshot_line(label: str, snapshot: dict[str, Any], status: dict[str, Any] | None = None) -> str:
    stats = snapshot.get("stats") or {}
    status = status or {}
    qi_blood = int(status.get("hp") or stats.get("qi_blood") or 0)
    max_qi_blood = int(status.get("max_hp") or stats.get("qi_blood") or 0)
    true_yuan = int(status.get("mp") or stats.get("true_yuan") or 0)
    max_true_yuan = int(status.get("max_mp") or stats.get("true_yuan") or 0)
    effect_text = str(status.get("effects_text") or "无")
    return (
        f"{label} {_md_escape(str(snapshot.get('name') or '道友'))}"
        f" ｜ 气血 `{qi_blood}/{max_qi_blood}`"
        f" ｜ 真元 `{true_yuan}/{max_true_yuan}`"
        f" ｜ 状态 {_md_escape(effect_text)}"
    )


def _duel_snapshot_sources(snapshot: dict[str, Any]) -> dict[str, Any]:
    technique_name = str(snapshot.get("technique_name") or "").strip()
    if technique_name == "未修功法":
        technique_name = ""
    talisman_name = str(snapshot.get("talisman_name") or "").strip()
    if talisman_name == "未备符箓":
        talisman_name = ""
    artifact_names = [
        item.strip()
        for item in str(snapshot.get("artifact_names") or "").split("、")
        if item.strip() and item.strip() != "未装备法宝"
    ]
    return {
        "technique": technique_name,
        "talisman": talisman_name,
        "artifacts": artifact_names[:3],
    }


def _duel_loadout_line(label: str, snapshot: dict[str, Any]) -> str:
    sources = _duel_snapshot_sources(snapshot)
    parts: list[str] = []
    if sources["technique"]:
        parts.append(f"功法《{_md_escape(sources['technique'])}》")
    if sources["talisman"]:
        parts.append(f"符箓【{_md_escape(sources['talisman'])}】")
    if sources["artifacts"]:
        parts.append("法宝【" + "、".join(_md_escape(item) for item in sources["artifacts"]) + "】")
    return f"{label} " + (" ｜ ".join(parts) if parts else "暂无明显底牌显化")


def _duel_compact_log_excerpt(text: str, source_name: str = "", limit: int = 30) -> str:
    excerpt = re.sub(r"\s+", " ", str(text or "")).strip()
    if source_name:
        for marker in (f"{source_name}：", f"{source_name}:"):
            if marker in excerpt:
                excerpt = excerpt.split(marker, 1)[1].strip()
                break
        else:
            excerpt = excerpt.replace(source_name, "", 1).strip()
    excerpt = excerpt.lstrip("，。；：,: ")
    if len(excerpt) > limit:
        excerpt = excerpt[: max(limit - 1, 1)].rstrip("，。；：,: ") + "…"
    return excerpt or "气机已经显化。"


def _duel_find_source_excerpt(
    battle_log: list[dict[str, Any]],
    shown: int,
    source_names: list[str],
) -> tuple[str, str]:
    visible_rows = battle_log[:shown]
    for excluded_kinds in ({"state", "round", "opening"}, {"state", "round"}):
        for row in visible_rows:
            if str(row.get("kind") or "").strip() in excluded_kinds:
                continue
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            for source_name in source_names:
                if source_name and source_name in text:
                    return source_name, _duel_compact_log_excerpt(text, source_name=source_name)
    return "", ""


def _duel_showcase_line(label: str, snapshot: dict[str, Any], battle_log: list[dict[str, Any]], shown: int) -> str:
    sources = _duel_snapshot_sources(snapshot)
    segments: list[str] = []
    technique_name = str(sources.get("technique") or "").strip()
    talisman_name = str(sources.get("talisman") or "").strip()
    artifact_names = list(sources.get("artifacts") or [])
    if technique_name:
        _, excerpt = _duel_find_source_excerpt(battle_log, shown, [technique_name])
        if excerpt:
            segments.append(f"功法《{_md_escape(technique_name)}》{_md_escape(excerpt)}")
    if talisman_name:
        _, excerpt = _duel_find_source_excerpt(battle_log, shown, [talisman_name])
        if excerpt:
            segments.append(f"符箓【{_md_escape(talisman_name)}】{_md_escape(excerpt)}")
    if artifact_names:
        artifact_name, excerpt = _duel_find_source_excerpt(battle_log, shown, artifact_names)
        if artifact_name and excerpt:
            segments.append(f"法宝【{_md_escape(artifact_name)}】{_md_escape(excerpt)}")
    if not segments:
        return ""
    return f"{label} " + "；".join(segments[:3])


def _latest_duel_impact_line(battle_log: list[dict[str, Any]], shown: int) -> str:
    for row in reversed(battle_log[:shown]):
        kind = str(row.get("kind") or "").strip()
        if kind in {"state", "round"}:
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        prefix = _duel_log_emoji(kind)
        round_no = int(row.get("round") or 0)
        round_text = f"第{round_no}回合：" if round_no > 0 and kind != "opening" else ""
        return f"{prefix} {_md_escape(round_text + _duel_compact_log_excerpt(text, limit=42))}"
    return ""


def _format_duel_stream_text(result: dict[str, Any], visible_count: int) -> str:
    challenger = (result.get("challenger") or {}).get("profile") or {}
    defender = (result.get("defender") or {}).get("profile") or {}
    challenger_snapshot = result.get("challenger_snapshot") or {}
    defender_snapshot = result.get("defender_snapshot") or {}
    battle_log = list(result.get("battle_log") or [])
    total = len(battle_log)
    shown = min(max(int(visible_count or 0), 0), total)
    challenger_status, defender_status = _latest_visible_duel_statuses(result, shown)
    current_round = max((int(row.get("round") or 0) for row in battle_log[:shown]), default=0)
    challenger_showcase = _duel_showcase_line("🟥 显化：", challenger_snapshot, battle_log, shown)
    defender_showcase = _duel_showcase_line("🟦 显化：", defender_snapshot, battle_log, shown)
    latest_impact = _latest_duel_impact_line(battle_log, shown)
    lines = [
        "⚔️ **斗法简报**",
        f"对局：{_md_escape(_duel_profile_label(challenger))} vs {_md_escape(_duel_profile_label(defender))}",
        f"回合：`{current_round}/{int(result.get('round_count') or max(current_round, 1))}` ｜ 记录：`{shown}/{total}`",
        "战况：仅保留关键显化，避免群内连续刷屏。",
    ]
    stake = int(result.get("stake") or 0)
    if stake > 0:
        lines.append(f"赌斗：每人 `{stake}` 灵石")
    lines.extend(
        [
            "",
            _duel_snapshot_line("🟥", challenger_snapshot, challenger_status),
            _duel_snapshot_line("🟦", defender_snapshot, defender_status),
            "",
        ]
    )
    lines.append(_duel_loadout_line("🟥 底牌：", challenger_snapshot))
    lines.append(_duel_loadout_line("🟦 底牌：", defender_snapshot))
    if challenger_showcase or defender_showcase or latest_impact:
        lines.extend(["", "关键显化："])
        if challenger_showcase:
            lines.append(challenger_showcase)
        if defender_showcase:
            lines.append(defender_showcase)
        if latest_impact:
            lines.append(f"📣 最新波动：{latest_impact}")
    if shown < total:
        lines.extend(["", "⏳ 余波尚未散尽，结算即将落下。"])
    else:
        lines.extend(["", f"🏁 **胜负已分**", _md_escape(str(result.get('summary') or '斗法结束。'))])
    return "\n".join(lines)


async def _stream_duel_battle(message, result: dict[str, Any]) -> None:
    battle_log = list(result.get("battle_log") or [])
    if not battle_log:
        return
    try:
        await _edit_text(
            message,
            _format_duel_stream_text(result, len(battle_log)),
            persistent=True,
            parse_mode=RICH_TEXT_MODE,
        )
    except Exception as exc:
        LOGGER.warning(f"xiuxian duel stream update failed: {exc}")
        return
    await asyncio.sleep(2)


async def _maybe_refresh_duel_bet_message(pool_id: int, message, remaining_seconds: int | None = None, force: bool = False) -> bool:
    now_monotonic = time.monotonic()
    interval = _duel_refresh_interval(remaining_seconds)
    last_refresh = DUEL_MESSAGE_REFRESH_CACHE.get(pool_id, 0.0)
    if not force and now_monotonic - last_refresh < interval:
        return False
    try:
        await _edit_text(
            message,
            format_duel_bet_board(pool_id),
            reply_markup=_duel_bet_keyboard(pool_id),
            persistent=True,
            parse_mode=RICH_TEXT_MODE,
        )
    except Exception:
        return False
    DUEL_MESSAGE_REFRESH_CACHE[pool_id] = now_monotonic
    return True


def register_bot(bot_instance) -> None:
    global EVENT_SUMMARY_LOOP_TASK, ENCOUNTER_AUTO_DISPATCH_LOOP_TASK, ENCOUNTER_AUTO_DISPATCH_LOCK
    _ensure_xiuxian_bot_commands()
    _schedule_command_refresh(bot_instance)

    async def _delayed_startup_tasks() -> None:
        await asyncio.sleep(20)
        try:
            _schedule_active_auction_finalize_tasks()
            _schedule_active_arena_finalize_tasks()
            _queue_event_summary_refresh(delay_seconds=0, force_create=True)
        except Exception as exc:
            LOGGER.warning(f"xiuxian delayed startup tasks failed: {exc}")

    loop = get_or_create_event_loop()
    loop.create_task(_delayed_startup_tasks())

    if EVENT_SUMMARY_LOOP_TASK is None or EVENT_SUMMARY_LOOP_TASK.done():
        async def refresh_event_summary_loop() -> None:
            while True:
                try:
                    interval_minutes = _event_summary_interval_minutes()
                    if interval_minutes > 0:
                        await _refresh_all_event_summaries()
                        await asyncio.sleep(interval_minutes * 60)
                    else:
                        await asyncio.sleep(60)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    LOGGER.warning(f"xiuxian event summary loop failed: {exc}")
                    await asyncio.sleep(60)

        EVENT_SUMMARY_LOOP_TASK = loop.create_task(refresh_event_summary_loop())

    if ENCOUNTER_AUTO_DISPATCH_LOCK is None:
        ENCOUNTER_AUTO_DISPATCH_LOCK = asyncio.Lock()
    if ENCOUNTER_AUTO_DISPATCH_LOOP_TASK is None or ENCOUNTER_AUTO_DISPATCH_LOOP_TASK.done():
        loop = get_or_create_event_loop()

        async def encounter_auto_dispatch_loop() -> None:
            await asyncio.sleep(30)
            while True:
                try:
                    lock = ENCOUNTER_AUTO_DISPATCH_LOCK
                    if lock is None:
                        await asyncio.sleep(60)
                        continue
                    async with lock:
                        await _dispatch_due_group_encounters()
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    LOGGER.warning(f"xiuxian encounter auto dispatch loop failed: {exc}")
                    await asyncio.sleep(60)

        ENCOUNTER_AUTO_DISPATCH_LOOP_TASK = loop.create_task(encounter_auto_dispatch_loop())

    # 世界 Boss 定时器
    _WORLD_BOSS_LOOP_TASK = globals().get("_WORLD_BOSS_LOOP_TASK")
    if _WORLD_BOSS_LOOP_TASK is None or _WORLD_BOSS_LOOP_TASK.done():
        loop = get_or_create_event_loop()

        async def world_boss_loop() -> None:
            # 启动后稍等片刻再首次生成，确保 bot 已完全就绪
            await asyncio.sleep(30)
            while True:
                try:
                    from bot.plugins.xiuxian_game.features.boss import settle_expired_world_bosses as _settle_expired
                    from bot.plugins.xiuxian_game.features.boss import try_spawn_world_boss as _spawn
                    _settle_expired()
                    result = _spawn()
                    if result:
                        instance = result.get("instance") or {}
                        text = instance.get("broadcast_text")
                        chat_id = instance.get("broadcast_chat_id")
                        if text and chat_id:
                            asyncio.create_task(_send_message(bot_instance, chat_id, text, parse_mode=RICH_TEXT_MODE, persistent=True))
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    LOGGER.warning(f"xiuxian world boss loop failed: {exc}")
                    await asyncio.sleep(60)

        globals()["_WORLD_BOSS_LOOP_TASK"] = loop.create_task(world_boss_loop())

    async def refresh_duel_bet_countdown(pool_id: int, message, bets_close_at: str | None) -> None:
        close_at = _parse_shanghai_datetime(bets_close_at)
        if close_at is None:
            return
        while True:
            remaining = max(int((close_at - datetime.now(SHANGHAI_TZ)).total_seconds()), 0)
            if remaining <= 0:
                break
            await asyncio.sleep(min(_duel_refresh_interval(remaining), remaining))
            remaining = max(int((close_at - datetime.now(SHANGHAI_TZ)).total_seconds()), 0)
            if remaining <= 0:
                break
            await _maybe_refresh_duel_bet_message(pool_id, message, remaining_seconds=remaining)

    async def finalize_duel_after_betting(
        pool_id: int | None,
        challenger_tg: int,
        defender_tg: int,
        stake: int,
        duel_mode: str,
        message,
        bets_close_at: str | None,
    ) -> None:
        close_at = _parse_shanghai_datetime(bets_close_at)
        if close_at is not None:
            await asyncio.sleep(max((close_at - datetime.now(SHANGHAI_TZ)).total_seconds(), 0))
        try:
            def _resolve_duel_flow():
                result = resolve_duel(challenger_tg, defender_tg, stake, duel_mode=duel_mode)
                bet_settlement = settle_duel_bet_pool(pool_id, result["winner_tg"]) if pool_id is not None else None
                return result, bet_settlement

            result, bet_settlement = await run_in_threadpool(_resolve_duel_flow)
            if pool_id is not None:
                DUEL_MESSAGE_REFRESH_CACHE.pop(pool_id, None)
            total_pages = _duel_settlement_total_pages(bet_settlement)
            if pool_id is not None and total_pages > 1:
                DUEL_SETTLEMENT_CACHE[pool_id] = {
                    "result": result,
                    "bet_settlement": bet_settlement,
                }
            elif pool_id is not None:
                DUEL_SETTLEMENT_CACHE.pop(pool_id, None)
            try:
                try:
                    await _edit_text(
                        message,
                        "⏳ **斗法推演开始**\n\n关键战况整理中……" if pool_id is None else "⏳ **赌池已封盘**\n\n斗法推演开始，关键战况整理中……",
                        persistent=True,
                        parse_mode=RICH_TEXT_MODE,
                    )
                except Exception as exc:
                    LOGGER.warning(f"xiuxian duel stream opening update failed: {exc}")
                await _stream_duel_battle(message, result)
                await _edit_text(
                    message,
                    format_duel_settlement_text(
                        result,
                        bet_settlement,
                        page=1,
                        page_size=DUEL_SETTLEMENT_PAGE_SIZE,
                    ),
                    reply_markup=_duel_settlement_keyboard(pool_id, 1, total_pages) if pool_id is not None else None,
                    parse_mode=RICH_TEXT_MODE,
                )
            except Exception as exc:
                LOGGER.warning(f"xiuxian duel settlement message update failed: {exc}")
            await _notify_duel_participants(result)
            await _notify_duel_bettors(result, bet_settlement)
            await _notify_achievement_unlocks(result.get("achievement_unlocks"))
        except ValueError as exc:
            if pool_id is not None:
                DUEL_MESSAGE_REFRESH_CACHE.pop(pool_id, None)
                DUEL_SETTLEMENT_CACHE.pop(pool_id, None)
                try:
                    cancel_duel_bet_pool(pool_id, str(exc))
                except Exception as refund_exc:
                    LOGGER.warning(f"xiuxian duel refund failed: {refund_exc}")
            try:
                await _edit_text(
                    message,
                    (
                        f"⚠️ **赌斗已取消**\n\n{_md_escape(str(exc))}\n\n围观押注若已扣除，现已原路退回。"
                        if pool_id is not None
                        else f"⚠️ **斗法已取消**\n\n{_md_escape(str(exc))}"
                    ),
                    persistent=True,
                    parse_mode=RICH_TEXT_MODE,
                )
            except Exception as message_exc:
                LOGGER.warning(f"xiuxian duel cancel message update failed: {message_exc}")
        except Exception as exc:
            if pool_id is not None:
                DUEL_MESSAGE_REFRESH_CACHE.pop(pool_id, None)
                DUEL_SETTLEMENT_CACHE.pop(pool_id, None)
                try:
                    cancel_duel_bet_pool(pool_id, str(exc))
                except Exception as refund_exc:
                    LOGGER.warning(f"xiuxian duel finalize fallback refund failed: {refund_exc}")
            LOGGER.warning(f"xiuxian duel finalize failed: {exc}")
            try:
                await _edit_text(
                    message,
                    (
                        "⚠️ **赌斗结算异常**\n\n本场斗法未能正常落盘，赌池已自动撤销，已参与押注的灵石会原路退回。"
                        if pool_id is not None
                        else "⚠️ **斗法结算异常**\n\n本场斗法未能正常落盘，请稍后重试。"
                    ),
                    persistent=True,
                    parse_mode=RICH_TEXT_MODE,
                )
            except Exception as message_exc:
                LOGGER.warning(f"xiuxian duel finalize error message update failed: {message_exc}")

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:entry$"))
    async def xiuxian_entry(_, call):
        await callAnswer(call, "正在展开仙途卷轴……")
        await _edit_text(
            call.message,
            "是否愿意踏入仙途？确认后会抽取灵根，并为你建立专属修仙档案。",
            reply_markup=xiuxian_confirm_keyboard(),
        )

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:return$"))
    async def xiuxian_return(_, call):
        profile = await run_in_threadpool(serialize_full_profile, call.from_user.id)
        await callAnswer(call, "已回到修仙主页。")
        await _edit_text(call.message, _format_profile_text(profile), reply_markup=xiuxian_profile_keyboard(), parse_mode=RICH_TEXT_MODE)

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:confirm$"))
    async def xiuxian_confirm(_, call):
        try:
            def _enter_path():
                profile = init_path_for_user(call.from_user.id)
                create_foundation_pill_for_user_if_missing(call.from_user.id)
                return profile

            profile = await run_in_threadpool(_enter_path)
            await callAnswer(call, "仙途已启，命格已定。")
            await _edit_text(call.message, _format_profile_text(profile), reply_markup=xiuxian_profile_keyboard(), parse_mode=RICH_TEXT_MODE)
        except Exception as exc:
            await callAnswer(call, str(exc), True)

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:train$"))
    async def xiuxian_train(_, call):
        try:
            def _train_text():
                result = practice_for_user(call.from_user.id)
                upgraded = ""
                if result["upgraded_layers"]:
                    upgraded = "\n层数提升：" + "、".join(f"{layer}层" for layer in result["upgraded_layers"])
                growth_text = _format_attribute_growth_text(result.get("attribute_growth"))
                growth_line = f"\n{growth_text}" if growth_text else ""
                curse_line = ""
                curse_text = _format_curse_event_line(result.get("curse_event"))
                if curse_text:
                    curse_line = f"\n{curse_text}"
                return (
                    f"吐纳修炼完成。\n"
                    f"本次获得：修为 +{result['gain']}、灵石 +{result['stone_gain']}"
                    f"{upgraded}{growth_line}{curse_line}\n\n"
                    f"{_format_profile_text(result['profile'])}"
                )

            text = await run_in_threadpool(_train_text)
            await callAnswer(call, "吐纳已完成。")
            await _edit_text(call.message, text, reply_markup=xiuxian_profile_keyboard(), parse_mode=RICH_TEXT_MODE)
        except Exception as exc:
            await callAnswer(call, str(exc), True)

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:break$"))
    async def xiuxian_break(_, call):
        try:
            def _breakthrough_text():
                result = breakthrough_for_user(call.from_user.id, use_pill=False)
                return (
                    f"突破掷点：{result['roll']} / 当前成功率 {result['success_rate']}%\n"
                    f"{'突破成功，气机贯通。' if result['success'] else '突破失败，灵力回落。'}\n\n"
                    f"{_format_profile_text(result['profile'])}"
                )

            text = await run_in_threadpool(_breakthrough_text)
            await callAnswer(call, "突破结果已出。")
            await _edit_text(call.message, text, reply_markup=xiuxian_profile_keyboard(), parse_mode=RICH_TEXT_MODE)
        except Exception as exc:
            await callAnswer(call, str(exc), True)

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:noop$"))
    async def xiuxian_noop(_, call):
        await callAnswer(call, "这个按钮暂时还没有开放。")

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:settlement:(\d+):(\d+)$"))
    async def xiuxian_duel_settlement_callback(_, call):
        pool_id = int(call.matches[0].group(1))
        requested_page = int(call.matches[0].group(2))
        cached = DUEL_SETTLEMENT_CACHE.get(pool_id)
        if not cached:
            return await callAnswer(call, "这份结算记录已过期。", True)
        bet_settlement = cached["bet_settlement"]
        total_pages = _duel_settlement_total_pages(bet_settlement)
        page = min(max(requested_page, 1), total_pages)
        await _edit_text(
            call.message,
            format_duel_settlement_text(
                cached["result"],
                bet_settlement,
                page=page,
                page_size=DUEL_SETTLEMENT_PAGE_SIZE,
            ),
            reply_markup=_duel_settlement_keyboard(pool_id, page, total_pages),
            parse_mode=RICH_TEXT_MODE,
        )
        await callAnswer(call, f"已切换到第 {page} 页。")

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:rank:(stone|realm|artifact):(\d+)$"))
    async def xiuxian_rank_callback(_, call):
        try:
            kind, page = call.matches[0].group(1), int(call.matches[0].group(2))
            result = await run_in_threadpool(build_leaderboard, kind, page)
            await _edit_text(
                call.message,
                format_leaderboard_text(result),
                reply_markup=leaderboard_keyboard(result["kind"], result["page"], result["total_pages"]),
                parse_mode=RICH_TEXT_MODE,
            )
            await callAnswer(call, "排行榜已刷新。")
        except Exception as exc:
            LOGGER.exception(f"xiuxian rank callback failed: {exc}")
            await callAnswer(call, "排行榜刷新失败，请稍后重试。", True)

    @bot_instance.on_message(filters.command(["xiuxian"], prefixes) & filters.private)
    async def xiuxian_command(_, msg):
        try:
            profile = await run_in_threadpool(serialize_full_profile, msg.from_user.id)
            if not profile["profile"]["consented"]:
                await _reply_text(
                    msg,
                    _xiuxian_basic_guide_text(False),
                    reply_markup=xiuxian_confirm_keyboard(),
                )
                return

            await _reply_text(
                msg,
                _format_profile_text(profile) + "\n\n" + _xiuxian_basic_guide_text(True),
                reply_markup=xiuxian_profile_keyboard(),
                parse_mode=RICH_TEXT_MODE,
            )
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(["xiuxian"], prefixes) & filters.chat(group))
    async def xiuxian_group_command(_, msg):
        try:
            if not _register_command_dispatch(msg, "xiuxian"):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command=xiuxian"
                )
                return
            bot_username = str(getattr(bot, "username", "") or "").strip()
            if not bot_username:
                try:
                    bot_info = await bot.get_me()
                    bot_username = str(getattr(bot_info, "username", "") or "").strip()
                except Exception as exc:
                    LOGGER.warning(f"xiuxian group command failed to resolve bot username: {exc}")
            private_url = f"https://t.me/{bot_username}?start=xiuxian" if bot_username else None
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("私聊开启修仙", url=private_url)]]
            ) if private_url else None
            await _reply_text(
                msg,
                _format_notice_card(
                    "前往私聊",
                    emoji="🧭",
                    lines=[
                        "修仙总览需要在私聊中打开。",
                        "点击下方按钮进入私聊后发送 /xiuxian，即可踏入仙途或查看名帖。",
                    ],
                ),
                quote=True,
                parse_mode=RICH_TEXT_MODE,
                reply_markup=reply_markup,
            )
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(["help"], prefixes))
    async def xiuxian_help_command(_, msg):
        try:
            help_text = (
                "可用命令如下：\n"
                "/start - 打开主面板与功能入口\n"
                "/help - 查看命令帮助\n"
                "/xiuxian - 打开修仙总览\n"
                "/xiuxian_me - 在群里展示自己的修仙信息\n"
                "/xiuxian_rank [stone|realm|artifact|灵石榜|境界榜|法宝榜] [页码] - 查看修仙排行榜\n"
                "/xiuxian_world - 查看修仙信息汇总跳转链接\n"
                "/train - 群里直接完成一次吐纳修炼\n"
                "/work [委托名] - 群里直接结算灵石委托；不填委托名时一键完成当前全部可接委托\n"
                "/salary - 群里领取一次宗门俸禄\n"
                "/duel [赌注] [下注秒数] - 回复某位道友发起斗法\n"
                "/deathduel [赌注] [下注秒数] - 回复某位道友发起生死斗\n"
                "/servitudeduel [赌注] [下注秒数] - 回复某位道友发起炉鼎斗\n"
                "/leitai [持续分钟] - 在群里开启一座公开擂台\n"
                "/caibu - 回复自己的炉鼎进行采补\n"
                "/seek - 回复某位道友探查信息\n"
                "/rob - 回复某位道友发起抢劫\n"
                "/gift <灵石数量> - 回复某位道友直接赠石\n"
                "/gift <TGID> <灵石数量> - 旧版 TGID 赠石写法\n"
                "/allow_upload - 主人回复用户后授予上传权限\n"
                "/remove_upload - 主人回复用户后移除上传权限\n"
                f"\n{_xiuxian_basic_guide_text(True)}\n"
                "其余修仙操作、任务、探索、红包、宗门与店铺功能请直接从 Mini App 进入。"
            )
            await _reply_text(msg, help_text)
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(["xiuxian_me", "xiuxian_info"], prefixes) & filters.chat(group))
    async def xiuxian_me_command(_, msg):
        try:
            if not _register_command_dispatch(msg, "xiuxian_me"):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command=xiuxian_me"
                )
                return
            if msg.from_user is None:
                return
            LOGGER.info(
                f"xiuxian me command received chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                f"actor={getattr(getattr(msg, 'from_user', None), 'id', None)}"
            )
            profile = await run_in_threadpool(serialize_full_profile, msg.from_user.id)
            if not profile["profile"]["consented"]:
                return await _reply_text(msg, "道途未启，仙缘未至。请先私聊机器人点击 /xiuxian 踏入仙途。")
            fallback_name = msg.from_user.first_name or f"TG {msg.from_user.id}"
            await _reply_text(msg, _format_group_profile_showcase(profile, fallback_name), parse_mode=RICH_TEXT_MODE)
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(["xiuxian_rank"], prefixes) & filters.chat(group))
    async def xiuxian_rank_command(_, msg):
        try:
            if not _register_command_dispatch(msg, "xiuxian_rank"):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command=xiuxian_rank"
                )
                return
            kind, page = _parse_xiuxian_rank_args(msg.command[1:])
            result = await run_in_threadpool(build_leaderboard, kind, page)
            await _reply_text(
                msg,
                format_leaderboard_text(result),
                reply_markup=leaderboard_keyboard(result["kind"], result["page"], result["total_pages"]),
                parse_mode=RICH_TEXT_MODE,
            )
        except Exception as exc:
            LOGGER.exception(
                f"xiuxian rank command failed chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                f"actor={getattr(getattr(msg, 'from_user', None), 'id', None)}: {exc}"
            )
            await _reply_text(msg, "排行榜加载失败，请稍后重试。")
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(["xiuxian_world"], prefixes))
    async def xiuxian_world_command(_, msg):
        try:
            if getattr(getattr(msg, "chat", None), "id", None) and getattr(getattr(msg, "chat", None), "type", None) in {
                enums.ChatType.GROUP,
                enums.ChatType.SUPERGROUP,
            }:
                if not _register_command_dispatch(msg, "xiuxian_world"):
                    LOGGER.warning(
                        f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                        f"message={getattr(msg, 'id', None)} command=xiuxian_world"
                    )
                    return
            current_chat_id = int(getattr(getattr(msg, "chat", None), "id", 0) or 0)
            configured_chat_ids = list(await _configured_event_summary_chat_ids())
            mapping = _event_summary_message_map()
            candidate_chat_ids = [
                chat_id
                for chat_id in configured_chat_ids
                if int(chat_id or 0) != 0 and int(chat_id or 0) != current_chat_id and int(mapping.get(int(chat_id), 0) or 0) > 0
            ]
            if not candidate_chat_ids:
                candidate_chat_ids = [
                    chat_id
                    for chat_id, message_id in mapping.items()
                    if int(chat_id or 0) != 0 and int(chat_id or 0) != current_chat_id and int(message_id or 0) > 0
                ]
            if not candidate_chat_ids and int(mapping.get(current_chat_id) or 0) > 0:
                candidate_chat_ids = [current_chat_id]
            target_chat_id = int(candidate_chat_ids[0]) if candidate_chat_ids else 0
            target_message_id = int(mapping.get(target_chat_id) or 0)
            target_url = _message_jump_url(target_chat_id, target_message_id)
            if not target_url:
                await _reply_text(msg, "当前还没有可跳转的修仙信息汇总消息，请先在目标群生成仙界汇总。", quote=True)
                return
            link_text = _format_notice_card(
                "修仙信息汇总",
                emoji="🔗",
                lines=[
                    f"🧭 快捷跳转：{_message_jump_link('修仙信息汇总', target_chat_id, target_message_id)}",
                    "📱 点击下方按钮可直接进入目标群汇总消息。",
                ],
            )
            await _reply_text(
                msg,
                link_text,
                quote=True,
                parse_mode=RICH_TEXT_MODE,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("修仙信息汇总", url=target_url)]]
                ),
            )
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(["train", "practice"], prefixes) & filters.chat(group))
    async def xiuxian_train_group_command(_, msg):
        started_at = time.perf_counter()
        require_elapsed = 0.0
        settle_elapsed = 0.0
        reply_elapsed = 0.0
        delete_elapsed = 0.0
        try:
            if not _register_command_dispatch(msg, "train"):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command=train"
                )
                return
            segment_started_at = time.perf_counter()
            actor = await _require_message_user(msg, action_text="吐纳修炼")
            require_elapsed = time.perf_counter() - segment_started_at
            if actor is None:
                return
            segment_started_at = time.perf_counter()
            result = await run_in_threadpool(practice_for_user, actor.id)
            settle_elapsed = time.perf_counter() - segment_started_at
            lines = [
                f"📈 修为：`+{result['gain']}`",
                f"💎 灵石：`+{result['stone_gain']}`",
            ]
            layer_line = _format_layer_upgrade_line(result.get("upgraded_layers"))
            if layer_line:
                lines.append(layer_line)
            growth_text = _format_attribute_growth_text(result.get("attribute_growth"))
            if growth_text:
                lines.append(growth_text)
            curse_text = _format_curse_event_line(result.get("curse_event"))
            if curse_text:
                lines.append(curse_text)
            segment_started_at = time.perf_counter()
            await _reply_text(
                msg,
                _format_notice_card("吐纳完成", emoji="🫧", lines=lines),
                quote=True,
                parse_mode=RICH_TEXT_MODE,
            )
            reply_elapsed = time.perf_counter() - segment_started_at
        except Exception as exc:
            segment_started_at = time.perf_counter()
            await _reply_text(msg, str(exc) or "吐纳修炼失败，请稍后重试。", quote=True)
            reply_elapsed = time.perf_counter() - segment_started_at
        finally:
            segment_started_at = time.perf_counter()
            await _delete_user_command_message(msg)
            delete_elapsed = time.perf_counter() - segment_started_at
            _log_slow_group_command(
                "train",
                msg,
                started_at,
                require=require_elapsed,
                settle=settle_elapsed,
                reply=reply_elapsed,
                delete=delete_elapsed,
            )

    @bot_instance.on_message(filters.command(["work"], prefixes) & filters.chat(group))
    async def xiuxian_work_group_command(_, msg):
        started_at = time.perf_counter()
        require_elapsed = 0.0
        settle_elapsed = 0.0
        reply_elapsed = 0.0
        delete_elapsed = 0.0
        try:
            if not _register_command_dispatch(msg, "work"):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command=work"
                )
                return
            segment_started_at = time.perf_counter()
            actor = await _require_message_user(msg, action_text="承接灵石委托")
            require_elapsed = time.perf_counter() - segment_started_at
            if actor is None:
                return
            requested_key = _normalize_commission_command_key(msg.command[1] if len(msg.command or []) > 1 else None)
            def _claim_work():
                commission_rows = build_spirit_stone_commissions(actor.id)
                commission_bundle = {"commissions": commission_rows}
                selected_rows, _ = _select_group_commissions(commission_bundle, requested_key=requested_key)
                if not selected_rows:
                    return None, _commission_selection_error(commission_bundle, requested_key=requested_key)

                total_stone = 0
                total_cultivation = 0
                detail_rows: list[str] = []
                growth_rows: list[str] = []
                upgraded_layers: list[int] = []
                for selected in selected_rows:
                    result = claim_spirit_stone_commission(actor.id, str(selected.get("key") or ""), include_profile=False)
                    commission = result.get("commission") or {}
                    stone_gain = int(commission.get("stone_gain") or 0)
                    cultivation_gain = int(commission.get("cultivation_gain") or 0)
                    total_stone += stone_gain
                    total_cultivation += cultivation_gain
                    detail_rows.append(
                        f"• {_md_escape(commission.get('name') or selected.get('name') or '灵石委托')}：💎 `+{stone_gain}` ｜ 📈 `+{cultivation_gain}`"
                    )
                    detail = str(commission.get("detail") or "").strip()
                    if detail:
                        detail_rows.append(f"↳ {_md_escape(detail)}")
                    curse_text = _format_curse_event_line(result.get("curse_event"))
                    if curse_text:
                        detail_rows.append(f"↳ {curse_text}")
                    growth_text = _format_attribute_growth_text(
                        commission.get("attribute_growth"),
                        prefix=f"{commission.get('name') or selected.get('name') or '灵石委托'}成长",
                    )
                    if growth_text:
                        growth_rows.append(growth_text)
                    for layer in result.get("upgraded_layers") or []:
                        if int(layer) not in upgraded_layers:
                            upgraded_layers.append(int(layer))

                if len(selected_rows) == 1:
                    lines = detail_rows
                else:
                    lines = [
                        f"🧾 本次连做 `{len(selected_rows)}` 项委托",
                        f"💎 合计灵石：`+{total_stone}`",
                        f"📈 合计修为：`+{total_cultivation}`",
                        "",
                        "📋 明细：",
                    ]
                    lines.extend(detail_rows)
                lines.extend(growth_rows)
                layer_line = _format_layer_upgrade_line(upgraded_layers)
                if layer_line:
                    lines.append(layer_line)
                return "\n".join(lines), None

            segment_started_at = time.perf_counter()
            result_text, error_text = await run_in_threadpool(_claim_work)
            settle_elapsed = time.perf_counter() - segment_started_at
            if error_text:
                segment_started_at = time.perf_counter()
                await _reply_text(msg, error_text, quote=True, parse_mode=RICH_TEXT_MODE)
                reply_elapsed = time.perf_counter() - segment_started_at
                return
            if result_text is None:
                return
            segment_started_at = time.perf_counter()
            await _reply_text(
                msg,
                _format_notice_card("灵石委托完成", emoji="💼", lines=result_text.splitlines()),
                quote=True,
                parse_mode=RICH_TEXT_MODE,
            )
            reply_elapsed = time.perf_counter() - segment_started_at
        except Exception as exc:
            segment_started_at = time.perf_counter()
            await _reply_text(msg, str(exc) or "灵石委托结算失败，请稍后重试。", quote=True)
            reply_elapsed = time.perf_counter() - segment_started_at
        finally:
            segment_started_at = time.perf_counter()
            await _delete_user_command_message(msg)
            delete_elapsed = time.perf_counter() - segment_started_at
            _log_slow_group_command(
                "work",
                msg,
                started_at,
                require=require_elapsed,
                settle=settle_elapsed,
                reply=reply_elapsed,
                delete=delete_elapsed,
            )

    @bot_instance.on_message(filters.command(["salary"], prefixes) & filters.chat(group))
    async def xiuxian_salary_group_command(_, msg):
        try:
            if not _register_command_dispatch(msg, "salary"):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command=salary"
                )
                return
            actor = await _require_message_user(msg, action_text="领取宗门俸禄")
            if actor is None:
                return
            def _salary_text():
                result = claim_sect_salary_for_user(actor.id)
                role = result.get("role") or {}
                role_name = str(role.get("role_name") or "宗门职位").strip()
                return result.get("salary", 0), role_name

            salary, role_name = await run_in_threadpool(_salary_text)
            await _reply_text(
                msg,
                _format_notice_card(
                    "宗门俸禄到账",
                    emoji="🏯",
                    lines=[
                        f"💎 本次领取：`{salary}` 灵石",
                        f"🎖️ 当前身份：{_md_escape(role_name)}",
                    ],
                ),
                quote=True,
                parse_mode=RICH_TEXT_MODE,
            )
        except Exception as exc:
            await _reply_text(msg, str(exc) or "领取宗门俸禄失败，请稍后重试。", quote=True)
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(["leitai", "arena", "擂台"], prefixes) & filters.chat(group))
    async def xiuxian_arena_open_command(_, msg):
        try:
            command_name = str((msg.command or ["leitai"])[0]).split("@", 1)[0].strip().lower()
            if not _register_command_dispatch(msg, command_name or "leitai"):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command={command_name or 'leitai'}"
                )
                return
            actor = await _require_message_user(msg, action_text="开设擂台")
            if actor is None:
                return
            if len(msg.command or []) > 1:
                return await _reply_text(msg, "新版擂台时长改为后台按境界配置，直接使用 /leitai 即可。", quote=True)
            actor_name = _telegram_user_display_name(actor, f"TG {actor.id}")

            try:
                def _open_arena():
                    return open_group_arena_for_user(
                        actor.id,
                        group_chat_id=_notice_group_chat_id("arena", fallback_chat_id=msg.chat.id) or msg.chat.id,
                        champion_display_name=actor_name,
                    )

                opened = await run_in_threadpool(_open_arena)
                arena_payload = opened.get("arena") or {}
                try:
                    arena_payload, pin_warning = await _push_arena_to_group(arena_payload)
                except Exception:
                    try:
                        await run_in_threadpool(
                            cancel_group_arena,
                            int(arena_payload.get("id") or 0),
                            owner_tg=actor.id,
                            reason="擂台消息推送失败，已自动撤销。",
                            refund_open_fee_stone=int(opened.get("open_fee_stone") or 0),
                        )
                    except Exception as rollback_exc:
                        LOGGER.warning(f"xiuxian arena rollback failed arena={arena_payload.get('id')}: {rollback_exc}")
                    raise
                await _notify_achievement_unlocks(opened.get("achievement_unlocks"))
                end_at = _parse_shanghai_datetime(arena_payload.get("end_at"))
                end_text = end_at.strftime("%m-%d %H:%M") if end_at else str(arena_payload.get("end_at") or "未知")
                success_lines = [
                    f"🏟️ 境界：`{_md_escape(arena_payload.get('realm_stage') or '炼气')}`",
                    f"⏳ 持续：约 `{int(arena_payload.get('duration_minutes') or 0)}` 分钟",
                    f"👑 你已成为首任擂主",
                    f"🕰️ 预计结算：`{end_text}`",
                    "🌿 修为改为每场攻擂后即时结算，不再在落幕时一次性发大量修为。",
                ]
                if int(opened.get("open_fee_stone") or 0) > 0:
                    success_lines.append(f"🎫 已扣除：`{int(opened.get('open_fee_stone') or 0)}` 灵石开擂手续费")
                if pin_warning:
                    success_lines.append(f"📌 {pin_warning}")
                await _reply_text(
                    msg,
                    _format_notice_card("擂台已开启", emoji="🏟️", lines=success_lines),
                    quote=True,
                    parse_mode=RICH_TEXT_MODE,
                )
            except Exception as exc:
                await _reply_text(msg, str(exc) or "开设擂台失败，请稍后重试。", quote=True)
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(list(DUEL_COMMAND_MODES.keys()), prefixes) & filters.chat(group))
    async def xiuxian_duel_command(_, msg):
        try:
            command_name = str((msg.command or [""])[0]).split("@", 1)[0].strip().lower()
            command_args = [str(item) for item in (msg.command[1:] if len(msg.command or []) > 1 else [])]
            if not _register_command_dispatch(msg, command_name):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command={command_name}"
                )
                return
            duel_mode = DUEL_COMMAND_MODES.get(command_name)
            if duel_mode is None:
                return
            LOGGER.info(
                f"xiuxian duel command received chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                f"actor={getattr(getattr(msg, 'from_user', None), 'id', None)} "
                f"cmd={command_name} reply_to={getattr(getattr(getattr(msg, 'reply_to_message', None), 'from_user', None), 'id', None)}"
            )
            actor = await _require_message_user(msg, action_text="发起斗法")
            if actor is None:
                return
            try:
                def _prepare_duel_preview():
                    settings = get_xiuxian_settings()
                    bet_settings = _duel_bet_settings(settings)
                    bet_seconds = int(bet_settings.get("seconds") or 120)
                    invite_timeout_seconds = _duel_invite_timeout_seconds(settings)
                    stake = 0
                    numeric_args: list[str] = []
                    for arg in command_args:
                        raw = str(arg or "").strip()
                        if not raw:
                            continue
                        if not re.fullmatch(r"-?\d+", raw):
                            if command_name == "duel":
                                raise ValueError(
                                    "普通斗法请使用 /duel [赌注] [下注秒数]；生死斗请用 /deathduel，炉鼎斗请用 /servitudeduel。"
                                )
                            raise ValueError("赌注和下注秒数必须填写整数。")
                        numeric_args.append(raw)
                    if numeric_args:
                        stake = max(int(numeric_args[0]), 0)
                        if len(numeric_args) > 1:
                            bet_seconds = max(min(int(numeric_args[1]), 3600), 10)
                    if msg.reply_to_message is None or msg.reply_to_message.from_user is None:
                        raise ValueError("请先回复一位目标道友，再发起斗法邀请。")
                    defender_tg = int(msg.reply_to_message.from_user.id)
                    if defender_tg == actor.id:
                        raise ValueError("你不能自己和自己斗法。")
                    duel = compute_duel_odds(actor.id, defender_tg, duel_mode=duel_mode)
                    mode_context = duel.get("mode_context") or {}
                    is_break_free_duel = bool(
                        _normalize_duel_mode_arg(duel_mode) == "master"
                        and int(mode_context.get("break_free_tg") or 0) == int(actor.id)
                        and int(mode_context.get("owner_tg") or 0) == defender_tg
                    )
                    if is_break_free_duel:
                        stake = 0
                    min_stake = int(bet_settings.get("min_amount") or 0)
                    max_stake = int(bet_settings.get("max_amount") or min_stake)
                    if not is_break_free_duel and stake < min_stake:
                        raise ValueError(f"斗法赌注至少需要 {min_stake} 灵石。")
                    if stake > max_stake:
                        raise ValueError(f"斗法赌注最多只能设置为 {max_stake} 灵石。")
                    assert_duel_stake_affordable(duel["challenger"]["profile"], duel["defender"]["profile"], stake)
                    preview = generate_duel_preview_text(duel, stake, duel_mode=duel_mode)
                    if is_break_free_duel:
                        preview += "\n\n⛓️ 脱离挑战已强制发起，无需主人接受，本场将直接开战。"
                    else:
                        preview += _format_duel_invite_footer(
                            invite_timeout_seconds,
                            {**bet_settings, "seconds": bet_seconds},
                        )
                    return preview, stake, bet_seconds, invite_timeout_seconds, defender_tg, is_break_free_duel

                preview, stake, bet_seconds, invite_timeout_seconds, defender_tg, is_break_free_duel = await run_in_threadpool(_prepare_duel_preview)
                sent = await _reply_text(
                    msg,
                    preview,
                    reply_markup=None if is_break_free_duel else duel_keyboard(actor.id, defender_tg, stake, bet_seconds, duel_mode=duel_mode),
                    persistent=True,
                    parse_mode=RICH_TEXT_MODE,
                )
                if is_break_free_duel:
                    asyncio.create_task(finalize_duel_after_betting(None, actor.id, defender_tg, stake, duel_mode, sent, None))
                else:
                    _register_pending_duel_invite(
                        sent,
                        challenger_tg=actor.id,
                        defender_tg=defender_tg,
                        duel_mode=duel_mode,
                        stake=stake,
                        bet_seconds=bet_seconds,
                        timeout_seconds=invite_timeout_seconds,
                    )
            except Exception as exc:
                await _reply_text(msg, str(exc), quote=True)
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:duel:(accept|reject|cancel):([a-z_]+):(\d+):(\d+):(\d+):(\d+)$"))
    async def xiuxian_duel_callback(_, call):
        action = call.matches[0].group(1)
        duel_mode = _normalize_duel_mode_arg(call.matches[0].group(2))
        challenger_tg = int(call.matches[0].group(3))
        defender_tg = int(call.matches[0].group(4))
        stake = int(call.matches[0].group(5))
        bet_seconds = int(call.matches[0].group(6))

        key, invite = _get_pending_duel_invite(
            call.message,
            challenger_tg=challenger_tg,
            defender_tg=defender_tg,
            duel_mode=duel_mode,
            stake=stake,
            bet_seconds=bet_seconds,
        )
        if invite is None:
            return await callAnswer(call, "这场斗法邀请已失效或已被处理。", True)

        if action == "cancel":
            if call.from_user.id != challenger_tg:
                return await callAnswer(call, "只有发起斗法的一方才能主动撤销邀请。", True)
            _pop_pending_duel_invite(key)
            await _edit_text(
                call.message,
                _format_duel_invite_closed_text(
                    duel_mode,
                    f"{_duel_mode_label(duel_mode)}邀请已主动撤销",
                    [
                        "🛑 发起者已收回这场挑战。",
                        "📭 若仍想开战，可重新发起新的斗法邀请。",
                    ],
                ),
                persistent=True,
                reply_markup=None,
                parse_mode=RICH_TEXT_MODE,
            )
            return await callAnswer(call, "斗法邀请已撤销。")

        if call.from_user.id != defender_tg:
            return await callAnswer(call, "只有被邀请的应战者才能处理这场斗法。", True)

        if action == "reject":
            _pop_pending_duel_invite(key)
            await _edit_text(
                call.message,
                _format_duel_invite_closed_text(
                    duel_mode,
                    f"{_duel_mode_label(duel_mode)}邀请已被拒绝",
                    [
                        "🚫 应战者选择了拒绝，本场挑战到此作废。",
                        "📭 发起者可稍后重新发起新的邀请。",
                    ],
                ),
                persistent=True,
                reply_markup=None,
                parse_mode=RICH_TEXT_MODE,
            )
            return await callAnswer(call, "斗法已取消。")

        _pop_pending_duel_invite(key)
        try:
            def _prepare_duel_accept():
                duel_preview = compute_duel_odds(challenger_tg, defender_tg, duel_mode=duel_mode)
                assert_duel_stake_affordable(
                    duel_preview["challenger"]["profile"],
                    duel_preview["defender"]["profile"],
                    stake,
                )
                current_bet_settings = _duel_bet_settings()
                return duel_preview, current_bet_settings

            duel_preview, current_bet_settings = await run_in_threadpool(_prepare_duel_accept)
            if current_bet_settings["enabled"]:
                pool = await run_in_threadpool(
                    create_duel_bet_pool_for_duel,
                    challenger_tg=challenger_tg,
                    defender_tg=defender_tg,
                    stake=stake,
                    duel_mode=duel_mode,
                    bet_seconds=bet_seconds,
                    group_chat_id=call.message.chat.id,
                    duel_message_id=call.message.id,
                )
                sent = await _edit_text(
                    call.message,
                    f"{_duel_mode_emoji(duel_mode)} {_duel_mode_label(duel_mode)}邀请已接受，押注通道开放 {_format_duration_seconds(pool.get('bet_seconds', bet_seconds))}。\n\n"
                    + format_duel_bet_board(pool["id"]),
                    reply_markup=_duel_bet_keyboard(pool["id"]),
                    persistent=True,
                    parse_mode=RICH_TEXT_MODE,
                )
                DUEL_MESSAGE_REFRESH_CACHE[pool["id"]] = time.monotonic()
                try:
                    await run_in_threadpool(update_duel_bet_pool_message, pool["id"], getattr(sent, "id", call.message.id))
                except Exception as exc:
                    LOGGER.warning(f"xiuxian duel bet message update failed: {exc}")
                await callAnswer(call, "斗法已开始，押注倒计时启动。")
                asyncio.create_task(refresh_duel_bet_countdown(pool["id"], sent, pool.get("bets_close_at")))
                asyncio.create_task(finalize_duel_after_betting(pool["id"], challenger_tg, defender_tg, stake, duel_mode, sent, pool.get("bets_close_at")))
            else:
                sent = await _edit_text(
                    call.message,
                    f"{_duel_mode_emoji(duel_mode)} {_duel_mode_label(duel_mode)}邀请已接受，当前后台已关闭赌斗下注，本场直接开战。",
                    reply_markup=None,
                    persistent=True,
                    parse_mode=RICH_TEXT_MODE,
                )
                await callAnswer(call, "斗法已开始，当前不开放下注。")
                asyncio.create_task(finalize_duel_after_betting(None, challenger_tg, defender_tg, stake, duel_mode, sent, None))
        except Exception as exc:
            try:
                await _edit_text(
                    call.message,
                    f"⚠️ **{_duel_mode_label(duel_mode)}邀请已取消**\n\n{_md_escape(str(exc))}",
                    persistent=True,
                    reply_markup=None,
                    parse_mode=RICH_TEXT_MODE,
                )
            except Exception as message_exc:
                LOGGER.warning(f"xiuxian duel accept error message update failed: {message_exc}")
            await callAnswer(call, str(exc), True)

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:bet:(\d+):(challenger|defender):(\d+)$"))
    async def xiuxian_duel_bet_callback(_, call):
        pool_id = int(call.matches[0].group(1))
        side = call.matches[0].group(2)
        amount = int(call.matches[0].group(3))
        try:
            await run_in_threadpool(place_duel_bet, pool_id, call.from_user.id, side, amount)
            refreshed = await _maybe_refresh_duel_bet_message(pool_id, call.message)
            answer_text = f"已下注 {amount} 灵石。"
            if not refreshed:
                answer_text += " 赌池信息将稍后自动刷新。"
            await callAnswer(call, answer_text)
        except Exception as exc:
            await callAnswer(call, str(exc), True)

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:shop:buy:(\d+)$"))
    async def xiuxian_shop_buy_callback(_, call):
        item_id = int(call.matches[0].group(1))
        buyer = getattr(call, "from_user", None)
        if buyer is None:
            return await callAnswer(call, "当前无法识别你的 TG 身份。", True)
        try:
            result = await run_in_threadpool(purchase_shop_item, buyer.id, item_id, 1)
        except Exception as exc:
            return await callAnswer(call, str(exc) or "购买失败", True)

        item = result.get("item") or {}
        await _refresh_shop_notice_message(item)
        _queue_event_summary_refresh(int(item.get("notice_group_chat_id") or 0) or None)
        _remember_journal(buyer.id, "shop", "购买商品", f"购买了【{item.get('item_name') or '未知商品'}】")
        seller_tg = int(result.get("seller_tg") or 0)
        if seller_tg > 0 and seller_tg != int(buyer.id):
            try:
                await _send_message(
                    bot,
                    seller_tg,
                    f"你的商品【{item.get('item_name') or '未知商品'}】已被 {result.get('buyer_name') or '道友'} 购买，到账 {int(result.get('total_cost') or 0)} 灵石。",
                    persistent=True,
                )
            except Exception as exc:
                LOGGER.warning(f"xiuxian shop seller notify failed tg={seller_tg}: {exc}")
        remaining = int(item.get("quantity") or 0)
        if remaining > 0:
            return await callAnswer(call, f"购买成功，剩余库存 {remaining}。")
        return await callAnswer(call, "购买成功，这件商品已经售罄。")

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:auction:(bid|buyout):(\d+)$"))
    async def xiuxian_auction_callback(_, call):
        action = str(call.matches[0].group(1) or "bid").strip().lower()
        auction_id = int(call.matches[0].group(2))
        bidder = getattr(call, "from_user", None)
        if bidder is None:
            return await callAnswer(call, "当前无法识别你的 TG 身份。", True)

        bidder_name = _telegram_user_display_name(bidder, f"TG {bidder.id}")

        try:
            result = await run_in_threadpool(
                place_auction_bid,
                bidder.id,
                auction_id,
                bidder_name=bidder_name,
                use_buyout=action == "buyout",
            )
        except Exception as exc:
            message = str(exc) or "竞拍失败"
            if "拍卖已经结束" in message:
                finalized = await run_in_threadpool(finalize_auction_listing, auction_id, force=True)
                if finalized and str(finalized.get("result") or "") not in {"noop", ""}:
                    await _finalize_auction_flow(finalized)
                return await callAnswer(call, "这场拍卖已经结束，面板已尝试刷新。", True)
            return await callAnswer(call, message, True)

        auction = result.get("auction") or {}
        outcome = str(result.get("result") or "")
        if outcome == "bid":
            await _refresh_auction_group_message(auction)
            _queue_event_summary_refresh(int(auction.get("group_chat_id") or 0) or None)
            current_price = int(auction.get("current_display_price_stone") or 0)
            return await callAnswer(call, f"已出价，当前价格 {current_price} 灵石。")

        if outcome == "sold":
            await _finalize_auction_flow(result)
            return await callAnswer(call, "拍卖已成交。")

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:arena:challenge:(\d+)$"))
    async def xiuxian_arena_callback(_, call):
        arena_id = int(call.matches[0].group(1))
        challenger = getattr(call, "from_user", None)
        if challenger is None:
            return await callAnswer(call, "当前无法识别你的 TG 身份。", True)

        challenger_name = _telegram_user_display_name(challenger, f"TG {challenger.id}")

        try:
            result = await run_in_threadpool(
                challenge_group_arena_for_user,
                arena_id,
                challenger.id,
                challenger_display_name=challenger_name,
            )
        except Exception as exc:
            message = str(exc) or "攻擂失败"
            if "已经结束" in message or "已经到期" in message:
                finalized = await run_in_threadpool(finalize_group_arena, arena_id, force=True)
                if finalized and str(finalized.get("result") or "") not in {"noop", "busy", ""}:
                    await _finalize_arena_flow(finalized)
                return await callAnswer(call, "这座擂台已经结束，群消息已尝试刷新。", True)
            return await callAnswer(call, message, True)

        arena = result.get("arena") or {}
        if result.get("ended"):
            finalized = await run_in_threadpool(finalize_group_arena, arena_id, force=True)
            if finalized and str(finalized.get("result") or "") not in {"noop", "busy", ""}:
                await _finalize_arena_flow(finalized)
        else:
            await _refresh_arena_group_message(arena)
            _queue_event_summary_refresh(int(arena.get("group_chat_id") or 0) or None)

        await _notify_achievement_unlocks(result.get("achievement_unlocks"))
        fee_notice = int(result.get("challenge_fee_stone") or 0)
        fee_prefix = f"已扣 {fee_notice} 灵石攻擂手续费，" if fee_notice > 0 else ""
        challenger_cultivation_reward = int(result.get("challenger_cultivation_reward") or 0)
        reward_suffix = f"，你本场获得 {challenger_cultivation_reward} 修为" if challenger_cultivation_reward > 0 else ""

        if str(result.get("result") or "") == "forfeit":
            return await callAnswer(call, f"{fee_prefix}旧擂主已失去守擂资格，你已直接接掌擂台。")
        if bool(result.get("champion_changed")):
            return await callAnswer(call, f"{fee_prefix}攻擂成功，你已成为新擂主{reward_suffix}。")
        return await callAnswer(call, f"{fee_prefix}守擂者胜，擂主未易{reward_suffix}。")

    @bot_instance.on_message(filters.text & filters.group & ~filters.regex(r"^[\\/!\\.，。]"))
    async def xiuxian_group_quiz_answer(_, msg):
        if msg.from_user is None or getattr(msg.from_user, "is_bot", False):
            return
        if not getattr(msg, "text", None):
            return
        try:
            result = await run_in_threadpool(resolve_quiz_answer, msg.chat.id, msg.from_user.id, msg.text)
        except Exception as exc:
            LOGGER.warning(f"xiuxian quiz resolve failed: {exc}")
            return
        if not result:
            return

        task = result["task"]
        reward = result["reward"] or {}
        reward_lines = []
        if int(reward.get("reward_stone") or 0):
            reward_lines.append(f"{reward['reward_stone']} 灵石")
        if int(reward.get("reward_cultivation") or 0):
            reward_lines.append(f"{reward['reward_cultivation']} 修为")
        if reward.get("reward_item"):
            reward_item = reward["reward_item"] or {}
            if reward_item.get("duplicate_converted"):
                reward_lines.append(f"重复{reward_item.get('item_kind_label') or '物品'}折灵石 {int(reward_item.get('stone_compensation') or 0)}")
            else:
                reward_lines.append(
                    f"{reward_item.get('quantity', 1)} 个{(reward_item.get('artifact') or reward_item.get('pill') or reward_item.get('talisman') or reward_item.get('material') or reward_item.get('technique') or reward_item.get('recipe') or {}).get('name', '物品')}"
                )
        reward_text = "、".join(reward_lines) if reward_lines else "任务奖励"
        winner_name = msg.from_user.first_name or f"TG {msg.from_user.id}"
        success_lines = [
            f"🏆 完成者：{_md_escape(winner_name)}",
            f"📜 任务：**{_md_escape(task['title'])}**",
            f"🎁 奖励：{_md_escape(reward_text)}",
        ]
        reward_payload = result.get("reward") or {}
        reward_layer_line = _format_layer_upgrade_line(reward_payload.get("upgraded_layers"))
        if reward_layer_line:
            success_lines.append(reward_layer_line)
        if int(reward_payload.get("cultivation_efficiency_percent") or 100) < 100:
            success_lines.append(
                f"📉 修为效率：`{int(reward_payload.get('cultivation_efficiency_percent') or 100)}%`（避世折算后）"
            )
        success_text = _format_notice_card("答题完成", emoji="🧩", lines=success_lines)
        try:
            await _reply_text(msg, success_text, quote=True, parse_mode=RICH_TEXT_MODE)
        except Exception as exc:
            LOGGER.warning(f"xiuxian quiz completion reply failed: {exc}")
            await _send_message(
                bot_instance,
                msg.chat.id,
                success_text,
                reply_to_message_id=msg.id,
                parse_mode=RICH_TEXT_MODE,
            )
        try:
            task_chat_id = int(task.get("group_chat_id") or msg.chat.id)
            if task.get("group_message_id"):
                summary = _task_group_text(task) + f"\n\n✅ 已完成：{_md_escape(winner_name)}"
                if task.get("image_url"):
                    caption, _ = _split_photo_caption(summary)
                    await bot_instance.edit_message_caption(
                        task_chat_id,
                        int(task["group_message_id"]),
                        caption or "任务已完成",
                        parse_mode=RICH_TEXT_MODE,
                    )
                else:
                    await _edit_message_text(
                        bot_instance,
                        task_chat_id,
                        int(task["group_message_id"]),
                        summary,
                        parse_mode=RICH_TEXT_MODE,
                        persistent=True,
                    )
            else:
                await _send_message(
                    bot_instance,
                    task_chat_id,
                    _format_notice_card(
                        "任务完成",
                        emoji="✅",
                        lines=[
                            f"📜 任务：**{_md_escape(task['title'])}**",
                            f"🏆 完成者：{_md_escape(winner_name)}",
                        ],
                    ),
                    parse_mode=RICH_TEXT_MODE,
                )
        except Exception as exc:
            LOGGER.warning(f"xiuxian quiz task message refresh failed: {exc}")

    @bot_instance.on_message(filters.text & filters.group & ~filters.regex(r"^[\\/!\\.，。]"))
    async def xiuxian_group_encounter_trigger(_, msg):
        if msg.from_user is None or getattr(msg.from_user, "is_bot", False):
            return
        if not getattr(msg, "text", None):
            return
        if not _encounter_auto_trigger_enabled(getattr(getattr(msg, "chat", None), "id", None)):
            return
        text = str(msg.text or "").strip()
        if not text or text.startswith(("/", "!", ".")):
            return
        try:
            payload = await run_in_threadpool(maybe_spawn_group_encounter, msg.chat.id)
            if payload:
                await _push_group_encounter_notice(payload)
        except Exception as exc:
            LOGGER.warning(f"xiuxian encounter trigger failed chat={getattr(msg.chat, 'id', None)}: {exc}")

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:red:(\d+)$"))
    async def xiuxian_red_envelope_callback(_, call):
        envelope_id = int(call.matches[0].group(1))
        try:
            result = await run_in_threadpool(claim_red_envelope_for_user, envelope_id, call.from_user.id)
            envelope = result["envelope"]
            notice_text = _red_envelope_notice_text(envelope, result.get("claims", []))
            is_active = envelope.get("status") == "active"
            if getattr(call.message, "photo", None):
                caption, _ = _split_photo_caption(notice_text)
                await _edit_caption(
                    call.message,
                    caption or "红包状态已更新",
                    reply_markup=_red_envelope_keyboard(envelope_id) if is_active else None,
                    parse_mode=RICH_TEXT_MODE,
                    persistent=is_active,
                )
            else:
                await _edit_text(
                    call.message,
                    notice_text,
                    reply_markup=_red_envelope_keyboard(envelope_id) if is_active else None,
                    parse_mode=RICH_TEXT_MODE,
                    persistent=is_active,
                )
            await callAnswer(call, f"成功领取 {result['amount']} 灵石。")
        except Exception as exc:
            await callAnswer(call, str(exc), True)

    @bot_instance.on_callback_query(filters.regex(r"^xiuxian:encounter:(\d+)$"))
    async def xiuxian_group_encounter_callback(_, call):
        instance_id = int(call.matches[0].group(1))
        try:
            result = await run_in_threadpool(claim_group_encounter, instance_id, call.from_user.id)
            winner_name = call.from_user.first_name or f"TG {call.from_user.id}"
            success_text = render_group_encounter_success_text(result, winner_name)
            if getattr(call.message, "photo", None):
                caption, overflow = _split_photo_caption(success_text)
                await _edit_caption(
                    call.message,
                    caption or "奇遇已结算",
                    parse_mode=RICH_TEXT_MODE,
                    persistent=True,
                )
                if overflow:
                    await _send_message(
                        bot,
                        call.message.chat.id,
                        overflow,
                        reply_to_message_id=call.message.id,
                        parse_mode=RICH_TEXT_MODE,
                        persistent=True,
                    )
            else:
                await _edit_text(
                    call.message,
                    success_text,
                    parse_mode=RICH_TEXT_MODE,
                    persistent=True,
                )
            await callAnswer(call, "手速惊人，这桩机缘归你了。")
        except Exception as exc:
            await callAnswer(call, str(exc), True)

    @bot_instance.on_message(filters.command(["xiuxian_seed"], prefixes) & filters.private)
    async def xiuxian_seed_user(_, msg):
        try:
            if not is_admin_user_id(msg.from_user.id):
                return await _reply_text(msg, "只有主人才能使用这个演示资源指令。")
            if len(msg.command) < 2 or not msg.command[1].isdigit():
                return await _reply_text(msg, "用法：/xiuxian_seed <tg_id>")
            payload = admin_seed_demo_assets(int(msg.command[1]))
            await _reply_text(msg, f"演示资源已经发放完成。\n{_format_profile_text(payload)}", parse_mode=RICH_TEXT_MODE)
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(["allow_upload"], prefixes) & filters.reply)
    async def xiuxian_allow_upload(client, msg):
        try:
            if not await _can_manage_upload_permissions(client, msg):
                return await _reply_text(msg, "只有后台主人或本群主人才能授予上传权限。")
            target_user = getattr(getattr(msg, "reply_to_message", None), "from_user", None)
            if target_user is None or getattr(target_user, "is_bot", False):
                return await _reply_text(msg, "请先回复一位真实用户，再授予上传权限。")
            if is_admin_user_id(target_user.id):
                return await _reply_text(msg, "主人默认就拥有上传权限。")
            grant_image_upload_permission(target_user.id)
            await _reply_text(msg, f"已为 {target_user.first_name}（{target_user.id}）开启图片上传权限。")
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(["remove_upload", "delete_upload"], prefixes) & filters.reply)
    async def xiuxian_remove_upload(client, msg):
        try:
            if not await _can_manage_upload_permissions(client, msg):
                return await _reply_text(msg, "只有后台主人或本群主人才能移除上传权限。")
            target_user = getattr(getattr(msg, "reply_to_message", None), "from_user", None)
            if target_user is None or getattr(target_user, "is_bot", False):
                return await _reply_text(msg, "请先回复一位真实用户，再移除上传权限。")
            removed = revoke_image_upload_permission(target_user.id)
            if removed:
                await _reply_text(msg, f"已移除 {target_user.first_name}（{target_user.id}）的图片上传权限。")
            else:
                await _reply_text(msg, "这个用户当前没有额外的上传权限记录。")
        finally:
            await _delete_user_command_message(msg)

    async def _handle_xiuxian_gift_command(msg, inline_amount: int | None = None) -> None:
        actor = await _require_message_user(msg, action_text="赠送灵石")
        if actor is None:
            return
        try:
            target_tg, amount = _resolve_gift_target_and_amount(msg, inline_amount=inline_amount)
        except ValueError as exc:
            return await _reply_text(msg, str(exc), quote=True)
        if int(target_tg) == int(actor.id):
            return await _reply_text(msg, "不能给自己赠送灵石。", quote=True)
        try:
            result = await run_in_threadpool(gift_spirit_stone, actor.id, target_tg, amount)
            if int(getattr(getattr(msg, "chat", None), "id", 0) or 0) < 0:
                await _send_message(
                    bot,
                    msg.chat.id,
                    _gift_group_broadcast_text(actor.first_name or f"TG {actor.id}", result.get("receiver") or {}, amount),
                    parse_mode=RICH_TEXT_MODE,
                    persistent=True,
                )
            else:
                await _reply_text(
                    msg,
                    f"赠送成功，已向 {result['receiver'].get('display_label') or f'TG {target_tg}'} 送出 {amount} 灵石。",
                    quote=True,
                )
            await _notify_achievement_unlocks(result.get("achievement_unlocks"))
        except Exception as exc:
            await _reply_text(msg, str(exc) or "赠送灵石失败，请稍后重试。", quote=True)

    @bot_instance.on_message(filters.command(["rob"], prefixes) & filters.chat(group))
    async def xiuxian_rob_command(_, msg):
        try:
            if not _register_command_dispatch(msg, "rob"):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command=rob"
                )
                return
            LOGGER.info(
                f"xiuxian rob command received chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                f"actor={getattr(getattr(msg, 'from_user', None), 'id', None)} "
                f"reply_to={getattr(getattr(getattr(msg, 'reply_to_message', None), 'from_user', None), 'id', None)}"
            )
            actor = await _require_message_user(msg, action_text="发起抢劫")
            if actor is None:
                return
            if msg.reply_to_message is None or msg.reply_to_message.from_user is None:
                return await _reply_text(msg, "请先回复目标道友，再尝试发起抢劫。", quote=True)
            if msg.reply_to_message.from_user.is_bot:
                return await _reply_text(msg, "不能对机器人发起抢劫。", quote=True)
            if int(msg.reply_to_message.from_user.id) == int(actor.id):
                return await _reply_text(msg, "你不能抢劫自己。", quote=True)
            try:
                result = await run_in_threadpool(rob_player, actor.id, msg.reply_to_message.from_user.id)
                if result["success"]:
                    if int(result["amount"] or 0) > 0:
                        lines = [f"💎 掠得灵石：`+{result['amount']}`"]
                    else:
                        lines = ["💎 抢劫成功，但对方身上已没剩多少灵石。"]
                    artifact_payload = ((result.get("artifact_plunder") or {}).get("artifact") or {})
                    if artifact_payload:
                        lines.append(f"🗡️ 额外夺得：{_md_escape(artifact_payload.get('name', '未知法宝'))}")
                    lines.append(f"🎯 判定成功率：`{round(float(result.get('success_rate', 0)) * 100, 1)}%`")
                    text = _format_notice_card("抢劫得手", emoji="🦹", lines=lines)
                else:
                    text = _format_notice_card(
                        "抢劫失手",
                        emoji="🚫",
                        lines=[
                            f"💸 赔付灵石：`{-int(result['amount'])}`",
                            f"🎯 判定成功率：`{round(float(result.get('success_rate', 0)) * 100, 1)}%`",
                        ],
                    )
                await _reply_text(msg, text, quote=True, parse_mode=RICH_TEXT_MODE)
                await _notify_achievement_unlocks(result.get("achievement_unlocks"))
            except Exception as exc:
                LOGGER.warning(
                    f"xiuxian rob failed attacker={getattr(actor, 'id', None)} "
                    f"target={getattr(getattr(getattr(msg, 'reply_to_message', None), 'from_user', None), 'id', None)}: {exc}"
                )
                await _reply_text(msg, str(exc) or "抢劫失败，请稍后重试。", quote=True)
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(["caibu"], prefixes) & filters.chat(group))
    async def xiuxian_furnace_harvest_command(_, msg):
        try:
            if not _register_command_dispatch(msg, "caibu"):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command=caibu"
                )
                return
            actor = await _require_message_user(msg, action_text="采补炉鼎")
            if actor is None:
                return
            if msg.reply_to_message is None or msg.reply_to_message.from_user is None:
                return await _reply_text(msg, "请先回复自己的炉鼎，再进行采补。", quote=True)
            if msg.reply_to_message.from_user.is_bot:
                return await _reply_text(msg, "不能对机器人进行采补。", quote=True)
            if int(msg.reply_to_message.from_user.id) == int(actor.id):
                return await _reply_text(msg, "你不能采补自己。", quote=True)
            try:
                result = await run_in_threadpool(harvest_furnace_for_user, actor.id, msg.reply_to_message.from_user.id)
                lines = [
                    f"📝 {_md_escape(str(result.get('message') or '本次采补已完成。').strip())}",
                    f"📈 主人修为：`+{int(result.get('master_gain') or 0)}`",
                    f"📉 炉鼎修为：`-{int(result.get('furnace_loss') or 0)}`",
                ]
                layer_line = _format_layer_upgrade_line(result.get("upgraded_layers"))
                if layer_line:
                    lines.append(layer_line)
                await _reply_text(
                    msg,
                    _format_notice_card("采补完成", emoji="🩸", lines=lines),
                    quote=True,
                    parse_mode=RICH_TEXT_MODE,
                )
            except Exception as exc:
                await _reply_text(msg, str(exc) or "采补失败，请稍后重试。", quote=True)
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(["seek"], prefixes) & filters.chat(group))
    async def xiuxian_seek_command(_, msg):
        try:
            if not _register_command_dispatch(msg, "seek"):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command=seek"
                )
                return
            LOGGER.info(
                f"xiuxian seek command received chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                f"actor={getattr(getattr(msg, 'from_user', None), 'id', None)} "
                f"reply_to={getattr(getattr(getattr(msg, 'reply_to_message', None), 'from_user', None), 'id', None)}"
            )
            try:
                actor = await _require_message_user(msg, action_text="探查对方信息")
                if actor is None:
                    return
                if msg.reply_to_message is None or msg.reply_to_message.from_user is None:
                    return await _reply_text(msg, "请先回复目标道友，再尝试探查。", quote=True)
                if msg.reply_to_message.from_user.is_bot:
                    return await _reply_text(msg, "机器人没有可供探查的修仙信息。", quote=True)
                if int(msg.reply_to_message.from_user.id) == int(actor.id):
                    return await _reply_text(msg, "你观照己身即可，无需对自己施展探查。", quote=True)

                seeker = await run_in_threadpool(serialize_full_profile, actor.id)
                if not seeker["profile"]["consented"]:
                    return await _reply_text(msg, "道途未启，仙缘未至。请先私聊机器人点击 /xiuxian 踏入仙途。", quote=True)

                target = await run_in_threadpool(serialize_full_profile, msg.reply_to_message.from_user.id)
                if not target["profile"]["consented"]:
                    return await _reply_text(msg, "对方尚未踏入仙途，探查不到任何灵息。", quote=True)

                seeker_divine_sense = _effective_divine_sense(seeker)
                target_divine_sense = _effective_divine_sense(target)
                if seeker_divine_sense <= target_divine_sense:
                    return await _reply_text(
                        msg,
                        f"神识强度不够，无法看破对方虚实。你的神识 {seeker_divine_sense}，对方神识 {target_divine_sense}。",
                        quote=True,
                    )

                fallback_name = msg.reply_to_message.from_user.first_name or f"TG {msg.reply_to_message.from_user.id}"
                lines = [
                    f"🧠 你的神识：`{seeker_divine_sense}`",
                    f"🔍 对方神识：`{target_divine_sense}`",
                    "",
                    _format_group_profile_showcase(target, fallback_name),
                ]
                await _reply_text(msg, "\n".join(lines), quote=True, parse_mode=RICH_TEXT_MODE)
            except Exception as exc:
                LOGGER.warning(
                    f"xiuxian seek failed seeker={getattr(actor, 'id', None)} "
                    f"target={getattr(getattr(msg.reply_to_message, 'from_user', None), 'id', None)}: {exc}"
                )
                await _reply_text(msg, f"探查失败：{exc or '请稍后重试。'}", quote=True)
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.command(["gift"], prefixes))
    async def xiuxian_gift_command(_, msg):
        try:
            if not _register_command_dispatch(msg, "gift"):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command=gift"
                )
                return
            await _handle_xiuxian_gift_command(msg)
        finally:
            await _delete_user_command_message(msg)

    @bot_instance.on_message(filters.regex(GIFT_INLINE_AMOUNT_PATTERN))
    async def xiuxian_gift_inline_command(_, msg):
        try:
            if not _register_command_dispatch(msg, "gift"):
                LOGGER.warning(
                    f"xiuxian command duplicate skipped chat={getattr(getattr(msg, 'chat', None), 'id', None)} "
                    f"message={getattr(msg, 'id', None)} command=gift-inline"
                )
                return
            text = str(getattr(msg, "text", None) or "").strip()
            match = GIFT_INLINE_AMOUNT_PATTERN.match(text)
            if match is None:
                return
            await _handle_xiuxian_gift_command(msg, inline_amount=int(match.group(1)))
        finally:
            await _delete_user_command_message(msg)
