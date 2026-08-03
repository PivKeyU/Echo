from __future__ import annotations

import copy
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import event
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    BigInteger,
    String,
    Text,
    UniqueConstraint,
    Index,
    or_,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from bot.plugins.xiuxian_game import cache as xiuxian_cache
from bot.sql_helper import Base, Session
from bot.sql_helper.sql_emby import Emby
from .constants import *  # noqa: F401 F403


def utcnow() -> datetime:
    return datetime.utcnow()


class XiuxianSetting(Base):
    __tablename__ = "xiuxian_settings"

    setting_key = Column(String(64), primary_key=True)
    setting_value = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianImageUploadPermission(Base):
    __tablename__ = "xiuxian_image_upload_permissions"

    tg = Column(BigInteger, primary_key=True, autoincrement=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianWebAccount(Base):
    __tablename__ = "xiuxian_web_accounts"
    __table_args__ = (
        UniqueConstraint("username", name="uq_xiuxian_web_accounts_username"),
        UniqueConstraint("tg", name="uq_xiuxian_web_accounts_tg"),
        Index("ix_xiuxian_web_accounts_username", "username"),
        Index("ix_xiuxian_web_accounts_tg", "tg"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False)
    password_hash = Column(String(255), nullable=False)
    tg = Column(BigInteger, nullable=True)
    display_name = Column(String(128), nullable=True)
    telegram_username = Column(String(64), nullable=True)
    telegram_display_name = Column(String(128), nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)


class XiuxianWebSession(Base):
    __tablename__ = "xiuxian_web_sessions"
    __table_args__ = (
        Index("ix_xiuxian_web_sessions_account_id", "account_id"),
        Index("ix_xiuxian_web_sessions_expires_at", "expires_at"),
    )

    token_hash = Column(String(64), primary_key=True)
    account_id = Column(Integer, ForeignKey("xiuxian_web_accounts.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class XiuxianProfile(Base):
    __tablename__ = "xiuxian_profiles"
    __table_args__ = (
        Index("ix_xiuxian_profiles_consented", "consented"),
        Index("ix_xiuxian_profiles_master_tg", "master_tg"),
        Index("ix_xiuxian_profiles_sect_id", "sect_id"),
    )

    tg = Column(BigInteger, primary_key=True, autoincrement=False)
    display_name = Column(String(128), nullable=True)
    username = Column(String(64), nullable=True)
    consented = Column(Boolean, default=False, nullable=False)
    gender = Column(String(16), nullable=True)
    root_type = Column(String(32), nullable=True)
    root_primary = Column(String(8), nullable=True)
    root_secondary = Column(String(8), nullable=True)
    root_relation = Column(String(16), nullable=True)
    root_bonus = Column(Integer, default=0, nullable=False)
    root_quality = Column(String(32), nullable=True)
    root_quality_level = Column(Integer, default=1, nullable=False)
    root_quality_color = Column(String(32), nullable=True)
    realm_stage = Column(String(32), default=REALM_ORDER[0], nullable=False)
    realm_layer = Column(Integer, default=0, nullable=False)
    cultivation = Column(Integer, default=0, nullable=False)
    spiritual_stone = Column(Integer, default=0, nullable=False)
    bone = Column(Integer, default=12, nullable=False)
    comprehension = Column(Integer, default=12, nullable=False)
    divine_sense = Column(Integer, default=12, nullable=False)
    fortune = Column(Integer, default=12, nullable=False)
    willpower = Column(Integer, default=10, nullable=False)
    charisma = Column(Integer, default=10, nullable=False)
    karma = Column(Integer, default=10, nullable=False)
    qi_blood = Column(Integer, default=120, nullable=False)
    true_yuan = Column(Integer, default=120, nullable=False)
    body_movement = Column(Integer, default=12, nullable=False)
    attack_power = Column(Integer, default=12, nullable=False)
    defense_power = Column(Integer, default=12, nullable=False)
    insight_bonus = Column(Integer, default=0, nullable=False)
    sect_contribution = Column(Integer, default=0, nullable=False)
    dan_poison = Column(Integer, default=0, nullable=False)
    breakthrough_pill_uses = Column(Integer, default=0, nullable=False)
    sect_id = Column(Integer, nullable=True)
    sect_role_key = Column(String(32), nullable=True)
    last_salary_claim_at = Column(DateTime, nullable=True)
    sect_joined_at = Column(DateTime, nullable=True)
    sect_betrayal_until = Column(DateTime, nullable=True)
    last_sect_attendance_at = Column(DateTime, nullable=True)
    last_sect_attendance_method = Column(String(16), nullable=True)
    master_tg = Column(BigInteger, nullable=True)
    servitude_started_at = Column(DateTime, nullable=True)
    servitude_challenge_available_at = Column(DateTime, nullable=True)
    furnace_harvested_at = Column(DateTime, nullable=True)
    death_at = Column(DateTime, nullable=True)
    rebirth_count = Column(Integer, default=0, nullable=False)
    robbery_daily_count = Column(Integer, default=0, nullable=False)
    robbery_day_key = Column(String(16), nullable=True)
    explore_daily_count = Column(Integer, default=0, nullable=False)
    explore_day_key = Column(String(16), nullable=True)
    fish_daily_count = Column(Integer, default=0, nullable=False)
    fish_day_key = Column(String(16), nullable=True)
    encounter_daily_count = Column(Integer, default=0, nullable=False)
    encounter_day_key = Column(String(16), nullable=True)
    current_artifact_id = Column(Integer, nullable=True)
    active_talisman_id = Column(Integer, nullable=True)
    current_technique_id = Column(Integer, nullable=True)
    current_title_id = Column(Integer, nullable=True)
    technique_capacity = Column(Integer, default=DEFAULT_TECHNIQUE_CAPACITY, nullable=False)
    shop_name = Column(String(64), nullable=True)
    shop_broadcast = Column(Boolean, default=False, nullable=False)
    last_train_at = Column(DateTime, nullable=True)
    social_mode = Column(String(16), default="worldly", nullable=False)
    social_mode_updated_at = Column(DateTime, nullable=True)
    retreat_started_at = Column(DateTime, nullable=True)
    retreat_end_at = Column(DateTime, nullable=True)
    retreat_gain_per_minute = Column(Integer, default=0, nullable=False)
    retreat_cost_per_minute = Column(Integer, default=0, nullable=False)
    retreat_minutes_total = Column(Integer, default=0, nullable=False)
    retreat_minutes_resolved = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianJournal(Base):
    __tablename__ = "xiuxian_journals"
    __table_args__ = (
        Index("ix_xiuxian_journals_tg_action_title_created_id", "tg", "action_type", "title", "created_at", "id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    action_type = Column(String(32), nullable=False)
    title = Column(String(128), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class XiuxianErrorLog(Base):
    __tablename__ = "xiuxian_error_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=True)
    username = Column(String(64), nullable=True)
    display_name = Column(String(128), nullable=True)
    scope = Column(String(32), nullable=False, default="user")
    level = Column(String(16), nullable=False, default="ERROR")
    operation = Column(String(128), nullable=True)
    method = Column(String(16), nullable=True)
    path = Column(String(255), nullable=True)
    status_code = Column(Integer, nullable=True)
    message = Column(Text, nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class XiuxianTitle(Base):
    __tablename__ = "xiuxian_titles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    color = Column(String(255), nullable=True)
    image_url = Column(String(512), nullable=True)
    attack_bonus = Column(Integer, default=0, nullable=False)
    defense_bonus = Column(Integer, default=0, nullable=False)
    bone_bonus = Column(Integer, default=0, nullable=False)
    comprehension_bonus = Column(Integer, default=0, nullable=False)
    divine_sense_bonus = Column(Integer, default=0, nullable=False)
    fortune_bonus = Column(Integer, default=0, nullable=False)
    qi_blood_bonus = Column(Integer, default=0, nullable=False)
    true_yuan_bonus = Column(Integer, default=0, nullable=False)
    body_movement_bonus = Column(Integer, default=0, nullable=False)
    duel_rate_bonus = Column(Integer, default=0, nullable=False)
    cultivation_bonus = Column(Integer, default=0, nullable=False)
    breakthrough_bonus = Column(Integer, default=0, nullable=False)
    extra_effects = Column(JSON, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianUserTitle(Base):
    __tablename__ = "xiuxian_user_titles"
    __table_args__ = (UniqueConstraint("tg", "title_id", name="uq_xiuxian_user_title"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    title_id = Column(Integer, ForeignKey("xiuxian_titles.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(32), nullable=True)
    obtained_note = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianAchievement(Base):
    __tablename__ = "xiuxian_achievements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    achievement_key = Column(String(64), nullable=False, unique=True)
    name = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    metric_key = Column(String(64), nullable=False)
    target_value = Column(BigInteger, default=1, nullable=False)
    reward_config = Column(JSON, nullable=True)
    notify_group = Column(Boolean, default=True, nullable=False)
    notify_private = Column(Boolean, default=True, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianAchievementProgress(Base):
    __tablename__ = "xiuxian_achievement_progress"
    __table_args__ = (UniqueConstraint("tg", "metric_key", name="uq_xiuxian_achievement_progress"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    metric_key = Column(String(64), nullable=False)
    current_value = Column(BigInteger, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianUserAchievement(Base):
    __tablename__ = "xiuxian_user_achievements"
    __table_args__ = (UniqueConstraint("tg", "achievement_id", name="uq_xiuxian_user_achievement"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    achievement_id = Column(Integer, ForeignKey("xiuxian_achievements.id", ondelete="CASCADE"), nullable=False)
    reward_snapshot = Column(JSON, nullable=True)
    unlocked_at = Column(DateTime, default=utcnow, nullable=False)
    private_notified_at = Column(DateTime, nullable=True)
    group_notified_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianMentorship(Base):
    __tablename__ = "xiuxian_mentorships"
    __table_args__ = (UniqueConstraint("mentor_tg", "disciple_tg", name="uq_xiuxian_mentorship_pair"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    mentor_tg = Column(BigInteger, nullable=False)
    disciple_tg = Column(BigInteger, nullable=False)
    status = Column(String(16), default="active", nullable=False)
    bond_value = Column(Integer, default=0, nullable=False)
    teach_count = Column(Integer, default=0, nullable=False)
    consult_count = Column(Integer, default=0, nullable=False)
    last_teach_at = Column(DateTime, nullable=True)
    last_consult_at = Column(DateTime, nullable=True)
    mentor_realm_stage_snapshot = Column(String(32), nullable=True)
    mentor_realm_layer_snapshot = Column(Integer, default=0, nullable=False)
    disciple_realm_stage_snapshot = Column(String(32), nullable=True)
    disciple_realm_layer_snapshot = Column(Integer, default=0, nullable=False)
    graduated_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianMentorshipRequest(Base):
    __tablename__ = "xiuxian_mentorship_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sponsor_tg = Column(BigInteger, nullable=False)
    target_tg = Column(BigInteger, nullable=False)
    sponsor_role = Column(String(16), nullable=False)
    message = Column(String(255), nullable=True)
    status = Column(String(16), default="pending", nullable=False)
    expires_at = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianMarriage(Base):
    __tablename__ = "xiuxian_marriages"
    __table_args__ = (UniqueConstraint("husband_tg", "wife_tg", name="uq_xiuxian_marriage_pair"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    husband_tg = Column(BigInteger, nullable=False)
    wife_tg = Column(BigInteger, nullable=False)
    status = Column(String(16), default="active", nullable=False)
    bond_value = Column(Integer, default=0, nullable=False)
    dual_cultivation_count = Column(Integer, default=0, nullable=False)
    last_dual_cultivation_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianMarriageRequest(Base):
    __tablename__ = "xiuxian_marriage_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sponsor_tg = Column(BigInteger, nullable=False)
    target_tg = Column(BigInteger, nullable=False)
    message = Column(String(255), nullable=True)
    status = Column(String(16), default="pending", nullable=False)
    expires_at = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianSect(Base):
    __tablename__ = "xiuxian_sects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    camp = Column(String(16), default="orthodox", nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(512), nullable=True)
    min_realm_stage = Column(String(32), nullable=True)
    min_realm_layer = Column(Integer, default=1, nullable=False)
    min_stone = Column(Integer, default=0, nullable=False)
    min_bone = Column(Integer, default=0, nullable=False)
    min_comprehension = Column(Integer, default=0, nullable=False)
    min_divine_sense = Column(Integer, default=0, nullable=False)
    min_fortune = Column(Integer, default=0, nullable=False)
    min_willpower = Column(Integer, default=0, nullable=False)
    min_charisma = Column(Integer, default=0, nullable=False)
    min_karma = Column(Integer, default=0, nullable=False)
    min_body_movement = Column(Integer, default=0, nullable=False)
    min_combat_power = Column(Integer, default=0, nullable=False)
    attack_bonus = Column(Integer, default=0, nullable=False)
    defense_bonus = Column(Integer, default=0, nullable=False)
    duel_rate_bonus = Column(Integer, default=0, nullable=False)
    cultivation_bonus = Column(Integer, default=0, nullable=False)
    fortune_bonus = Column(Integer, default=0, nullable=False)
    body_movement_bonus = Column(Integer, default=0, nullable=False)
    pill_poison_resist = Column(Float, default=0.0, nullable=False)
    pill_poison_cap_bonus = Column(Integer, default=0, nullable=False)
    farm_growth_speed = Column(Float, default=0.0, nullable=False)
    explore_drop_rate = Column(Integer, default=0, nullable=False)
    craft_success_rate = Column(Integer, default=0, nullable=False)
    death_penalty_reduce = Column(Float, default=0.0, nullable=False)
    salary_min_stay_days = Column(Integer, default=30, nullable=False)
    entry_hint = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianSectRole(Base):
    __tablename__ = "xiuxian_sect_roles"
    __table_args__ = (UniqueConstraint("sect_id", "role_key", name="uq_xiuxian_sect_role_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    sect_id = Column(Integer, ForeignKey("xiuxian_sects.id", ondelete="CASCADE"), nullable=False)
    role_key = Column(String(32), nullable=False)
    role_name = Column(String(64), nullable=False)
    attack_bonus = Column(Integer, default=0, nullable=False)
    defense_bonus = Column(Integer, default=0, nullable=False)
    duel_rate_bonus = Column(Integer, default=0, nullable=False)
    cultivation_bonus = Column(Integer, default=0, nullable=False)
    monthly_salary = Column(Integer, default=0, nullable=False)
    can_publish_tasks = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianSectTreasuryItem(Base):
    __tablename__ = "xiuxian_sect_treasury_items"
    __table_args__ = (UniqueConstraint("sect_id", "item_kind", "item_ref_id", name="uq_xiuxian_sect_treasury_item"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    sect_id = Column(Integer, ForeignKey("xiuxian_sects.id", ondelete="CASCADE"), nullable=False)
    item_kind = Column(String(16), nullable=False)
    item_ref_id = Column(Integer, nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianMaterial(Base):
    __tablename__ = "xiuxian_materials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    quality_level = Column(Integer, default=1, nullable=False)
    image_url = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    can_plant = Column(Boolean, default=False, nullable=False)
    seed_price_stone = Column(Integer, default=0, nullable=False)
    growth_minutes = Column(Integer, default=0, nullable=False)
    yield_min = Column(Integer, default=0, nullable=False)
    yield_max = Column(Integer, default=0, nullable=False)
    unlock_realm_stage = Column(String(32), nullable=True)
    unlock_realm_layer = Column(Integer, default=1, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianMaterialInventory(Base):
    __tablename__ = "xiuxian_material_inventory"
    __table_args__ = (UniqueConstraint("tg", "material_id", name="uq_xiuxian_material_inventory"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    material_id = Column(Integer, ForeignKey("xiuxian_materials.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianFarmPlot(Base):
    __tablename__ = "xiuxian_farm_plots"
    __table_args__ = (UniqueConstraint("tg", "slot_index", name="uq_xiuxian_farm_plot_slot"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    slot_index = Column(Integer, nullable=False)
    unlocked = Column(Boolean, default=False, nullable=False)
    current_material_id = Column(Integer, ForeignKey("xiuxian_materials.id", ondelete="SET NULL"), nullable=True)
    planted_at = Column(DateTime, nullable=True)
    mature_at = Column(DateTime, nullable=True)
    harvest_deadline_at = Column(DateTime, nullable=True)
    base_yield = Column(Integer, default=0, nullable=False)
    needs_watering = Column(Boolean, default=False, nullable=False)
    watered = Column(Boolean, default=False, nullable=False)
    pest_risk = Column(Boolean, default=False, nullable=False)
    pest_cleared = Column(Boolean, default=False, nullable=False)
    fertilized = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianRecipe(Base):
    __tablename__ = "xiuxian_recipes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    recipe_kind = Column(String(16), nullable=False)
    result_kind = Column(String(16), nullable=False)
    result_ref_id = Column(Integer, nullable=False)
    result_quantity = Column(Integer, default=1, nullable=False)
    base_success_rate = Column(Integer, default=60, nullable=False)
    broadcast_on_success = Column(Boolean, default=False, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianUserRecipe(Base):
    __tablename__ = "xiuxian_user_recipes"
    __table_args__ = (UniqueConstraint("tg", "recipe_id", name="uq_xiuxian_user_recipe"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    recipe_id = Column(Integer, ForeignKey("xiuxian_recipes.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(32), nullable=True)
    obtained_note = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianRecipeIngredient(Base):
    __tablename__ = "xiuxian_recipe_ingredients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey("xiuxian_recipes.id", ondelete="CASCADE"), nullable=False)
    material_id = Column(Integer, ForeignKey("xiuxian_materials.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianScene(Base):
    __tablename__ = "xiuxian_scenes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(512), nullable=True)
    max_minutes = Column(Integer, default=60, nullable=False)
    min_realm_stage = Column(String(32), nullable=True)
    min_realm_layer = Column(Integer, default=1, nullable=False)
    min_combat_power = Column(Integer, default=0, nullable=False)
    event_pool = Column(JSON, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianSceneDrop(Base):
    __tablename__ = "xiuxian_scene_drops"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_id = Column(Integer, ForeignKey("xiuxian_scenes.id", ondelete="CASCADE"), nullable=False)
    reward_kind = Column(String(16), nullable=False)
    reward_ref_id = Column(Integer, nullable=True)
    quantity_min = Column(Integer, default=1, nullable=False)
    quantity_max = Column(Integer, default=1, nullable=False)
    weight = Column(Integer, default=1, nullable=False)
    stone_reward = Column(Integer, default=0, nullable=False)
    event_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianExploration(Base):
    __tablename__ = "xiuxian_explorations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    scene_id = Column(Integer, ForeignKey("xiuxian_scenes.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, default=utcnow, nullable=False)
    end_at = Column(DateTime, nullable=False)
    claimed = Column(Boolean, default=False, nullable=False)
    reward_kind = Column(String(16), nullable=True)
    reward_ref_id = Column(Integer, nullable=True)
    reward_quantity = Column(Integer, default=0, nullable=False)
    stone_reward = Column(Integer, default=0, nullable=False)
    event_text = Column(Text, nullable=True)
    outcome_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianTask(Base):
    __tablename__ = "xiuxian_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    task_scope = Column(String(16), nullable=False)
    task_type = Column(String(16), default="quiz", nullable=False)
    owner_tg = Column(BigInteger, nullable=True)
    sect_id = Column(Integer, nullable=True)
    question_text = Column(Text, nullable=True)
    answer_text = Column(String(255), nullable=True)
    image_url = Column(String(512), nullable=True)
    required_item_kind = Column(String(16), nullable=True)
    required_item_ref_id = Column(Integer, nullable=True)
    required_item_quantity = Column(Integer, default=0, nullable=False)
    reward_stone = Column(Integer, default=0, nullable=False)
    reward_cultivation = Column(Integer, default=0, nullable=False)
    reward_item_kind = Column(String(16), nullable=True)
    reward_item_ref_id = Column(Integer, nullable=True)
    reward_item_quantity = Column(Integer, default=0, nullable=False)
    reward_item_escrowed = Column(Boolean, default=False, nullable=False)
    reward_stone_escrowed = Column(Boolean, default=False, nullable=False)
    reward_scale_mode = Column(String(16), default="fixed", nullable=False)
    requirement_metric_key = Column(String(64), nullable=True)
    requirement_metric_target = Column(Integer, default=0, nullable=False)
    max_claimants = Column(Integer, default=1, nullable=False)
    claimants_count = Column(Integer, default=0, nullable=False)
    active_in_group = Column(Boolean, default=False, nullable=False)
    group_chat_id = Column(BigInteger, nullable=True)
    group_message_id = Column(Integer, nullable=True)
    winner_tg = Column(BigInteger, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    status = Column(String(16), default="open", nullable=False)
    deadline_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianTaskClaim(Base):
    __tablename__ = "xiuxian_task_claims"
    __table_args__ = (UniqueConstraint("task_id", "tg", name="uq_xiuxian_task_claim"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("xiuxian_tasks.id", ondelete="CASCADE"), nullable=False)
    tg = Column(BigInteger, nullable=False)
    status = Column(String(16), default="accepted", nullable=False)
    submitted_answer = Column(String(255), nullable=True)
    metric_start_value = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianEncounterTemplate(Base):
    __tablename__ = "xiuxian_encounter_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(512), nullable=True)
    button_text = Column(String(64), nullable=True)
    success_text = Column(Text, nullable=True)
    broadcast_text = Column(Text, nullable=True)
    weight = Column(Integer, default=1, nullable=False)
    active_seconds = Column(Integer, default=90, nullable=False)
    min_realm_stage = Column(String(32), nullable=True)
    min_realm_layer = Column(Integer, default=1, nullable=False)
    min_combat_power = Column(Integer, default=0, nullable=False)
    reward_stone_min = Column(Integer, default=0, nullable=False)
    reward_stone_max = Column(Integer, default=0, nullable=False)
    reward_cultivation_min = Column(Integer, default=0, nullable=False)
    reward_cultivation_max = Column(Integer, default=0, nullable=False)
    reward_item_kind = Column(String(16), nullable=True)
    reward_item_ref_id = Column(Integer, nullable=True)
    reward_item_quantity_min = Column(Integer, default=1, nullable=False)
    reward_item_quantity_max = Column(Integer, default=1, nullable=False)
    reward_willpower = Column(Integer, default=0, nullable=False)
    reward_charisma = Column(Integer, default=0, nullable=False)
    reward_karma = Column(Integer, default=0, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianEncounterInstance(Base):
    __tablename__ = "xiuxian_encounter_instances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("xiuxian_encounter_templates.id", ondelete="SET NULL"), nullable=True)
    template_name = Column(String(128), nullable=False)
    group_chat_id = Column(BigInteger, nullable=False)
    message_id = Column(Integer, nullable=True)
    button_text = Column(String(64), nullable=True)
    status = Column(String(16), default="active", nullable=False)
    reward_payload = Column(JSON, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    claimer_tg = Column(BigInteger, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianRedEnvelope(Base):
    __tablename__ = "xiuxian_red_envelopes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_tg = Column(BigInteger, nullable=False)
    cover_text = Column(String(255), nullable=True)
    image_url = Column(String(512), nullable=True)
    mode = Column(String(16), nullable=False)
    target_tg = Column(BigInteger, nullable=True)
    amount_total = Column(Integer, default=0, nullable=False)
    count_total = Column(Integer, default=1, nullable=False)
    remaining_amount = Column(Integer, default=0, nullable=False)
    remaining_count = Column(Integer, default=0, nullable=False)
    status = Column(String(16), default="active", nullable=False)
    group_chat_id = Column(BigInteger, nullable=True)
    message_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianRedEnvelopeClaim(Base):
    __tablename__ = "xiuxian_red_envelope_claims"
    __table_args__ = (UniqueConstraint("envelope_id", "tg", name="uq_xiuxian_red_envelope_claim"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    envelope_id = Column(Integer, ForeignKey("xiuxian_red_envelopes.id", ondelete="CASCADE"), nullable=False)
    tg = Column(BigInteger, nullable=False)
    amount = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class XiuxianDuelBetPool(Base):
    __tablename__ = "xiuxian_duel_bet_pools"

    id = Column(Integer, primary_key=True, autoincrement=True)
    challenger_tg = Column(BigInteger, nullable=False)
    defender_tg = Column(BigInteger, nullable=False)
    stake = Column(Integer, default=0, nullable=False)
    group_chat_id = Column(BigInteger, nullable=False)
    duel_message_id = Column(Integer, nullable=True)
    bet_message_id = Column(Integer, nullable=True)
    duel_mode = Column(String(16), default="standard", nullable=False)
    bets_close_at = Column(DateTime, nullable=False)
    resolved = Column(Boolean, default=False, nullable=False)
    winner_tg = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianDuelBet(Base):
    __tablename__ = "xiuxian_duel_bets"
    __table_args__ = (UniqueConstraint("pool_id", "tg", name="uq_xiuxian_duel_bet"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    pool_id = Column(Integer, ForeignKey("xiuxian_duel_bet_pools.id", ondelete="CASCADE"), nullable=False)
    tg = Column(BigInteger, nullable=False)
    side = Column(String(16), nullable=False)
    amount = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class XiuxianTechnique(Base):
    __tablename__ = "xiuxian_techniques"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    rarity = Column(String(32), default="凡品", nullable=False)
    technique_type = Column(String(16), default="balanced", nullable=False)
    image_url = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    attack_bonus = Column(Integer, default=0, nullable=False)
    defense_bonus = Column(Integer, default=0, nullable=False)
    bone_bonus = Column(Integer, default=0, nullable=False)
    comprehension_bonus = Column(Integer, default=0, nullable=False)
    divine_sense_bonus = Column(Integer, default=0, nullable=False)
    fortune_bonus = Column(Integer, default=0, nullable=False)
    qi_blood_bonus = Column(Integer, default=0, nullable=False)
    true_yuan_bonus = Column(Integer, default=0, nullable=False)
    body_movement_bonus = Column(Integer, default=0, nullable=False)
    duel_rate_bonus = Column(Integer, default=0, nullable=False)
    cultivation_bonus = Column(Integer, default=0, nullable=False)
    breakthrough_bonus = Column(Integer, default=0, nullable=False)
    combat_config = Column(JSON, nullable=True)
    min_realm_stage = Column(String(32), nullable=True)
    min_realm_layer = Column(Integer, default=1, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianUserTechnique(Base):
    __tablename__ = "xiuxian_user_techniques"
    __table_args__ = (UniqueConstraint("tg", "technique_id", name="uq_xiuxian_user_technique"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    technique_id = Column(Integer, ForeignKey("xiuxian_techniques.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(32), nullable=True)
    obtained_note = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianArtifactSet(Base):
    __tablename__ = "xiuxian_artifact_sets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    required_count = Column(Integer, default=2, nullable=False)
    attack_bonus = Column(Integer, default=0, nullable=False)
    defense_bonus = Column(Integer, default=0, nullable=False)
    bone_bonus = Column(Integer, default=0, nullable=False)
    comprehension_bonus = Column(Integer, default=0, nullable=False)
    divine_sense_bonus = Column(Integer, default=0, nullable=False)
    fortune_bonus = Column(Integer, default=0, nullable=False)
    qi_blood_bonus = Column(Integer, default=0, nullable=False)
    true_yuan_bonus = Column(Integer, default=0, nullable=False)
    body_movement_bonus = Column(Integer, default=0, nullable=False)
    duel_rate_bonus = Column(Integer, default=0, nullable=False)
    cultivation_bonus = Column(Integer, default=0, nullable=False)
    breakthrough_bonus = Column(Integer, default=0, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianArtifact(Base):
    __tablename__ = "xiuxian_artifacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    rarity = Column(String(32), default="凡品", nullable=False)
    image_url = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    attack_bonus = Column(Integer, default=0, nullable=False)
    defense_bonus = Column(Integer, default=0, nullable=False)
    bone_bonus = Column(Integer, default=0, nullable=False)
    comprehension_bonus = Column(Integer, default=0, nullable=False)
    divine_sense_bonus = Column(Integer, default=0, nullable=False)
    fortune_bonus = Column(Integer, default=0, nullable=False)
    qi_blood_bonus = Column(Integer, default=0, nullable=False)
    true_yuan_bonus = Column(Integer, default=0, nullable=False)
    body_movement_bonus = Column(Integer, default=0, nullable=False)
    artifact_type = Column(String(16), default="battle", nullable=False)
    artifact_role = Column(String(16), default="battle", nullable=False)
    equip_slot = Column(String(16), default="weapon", nullable=False)
    artifact_set_id = Column(Integer, ForeignKey("xiuxian_artifact_sets.id", ondelete="SET NULL"), nullable=True)
    unique_item = Column(Boolean, default=False, nullable=False)
    duel_rate_bonus = Column(Integer, default=0, nullable=False)
    cultivation_bonus = Column(Integer, default=0, nullable=False)
    combat_config = Column(JSON, nullable=True)
    min_realm_stage = Column(String(32), nullable=True)
    min_realm_layer = Column(Integer, default=1, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianPill(Base):
    __tablename__ = "xiuxian_pills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    rarity = Column(String(32), default="凡品", nullable=False)
    pill_type = Column(String(32), nullable=False)
    image_url = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    effect_value = Column(Integer, default=0, nullable=False)
    poison_delta = Column(Integer, default=0, nullable=False)
    attack_bonus = Column(Integer, default=0, nullable=False)
    defense_bonus = Column(Integer, default=0, nullable=False)
    bone_bonus = Column(Integer, default=0, nullable=False)
    comprehension_bonus = Column(Integer, default=0, nullable=False)
    divine_sense_bonus = Column(Integer, default=0, nullable=False)
    fortune_bonus = Column(Integer, default=0, nullable=False)
    qi_blood_bonus = Column(Integer, default=0, nullable=False)
    true_yuan_bonus = Column(Integer, default=0, nullable=False)
    body_movement_bonus = Column(Integer, default=0, nullable=False)
    min_realm_stage = Column(String(32), nullable=True)
    min_realm_layer = Column(Integer, default=1, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianTalisman(Base):
    __tablename__ = "xiuxian_talismans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    rarity = Column(String(32), default="凡品", nullable=False)
    image_url = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    attack_bonus = Column(Integer, default=0, nullable=False)
    defense_bonus = Column(Integer, default=0, nullable=False)
    bone_bonus = Column(Integer, default=0, nullable=False)
    comprehension_bonus = Column(Integer, default=0, nullable=False)
    divine_sense_bonus = Column(Integer, default=0, nullable=False)
    fortune_bonus = Column(Integer, default=0, nullable=False)
    qi_blood_bonus = Column(Integer, default=0, nullable=False)
    true_yuan_bonus = Column(Integer, default=0, nullable=False)
    body_movement_bonus = Column(Integer, default=0, nullable=False)
    duel_rate_bonus = Column(Integer, default=0, nullable=False)
    effect_uses = Column(Integer, default=1, nullable=False)
    combat_config = Column(JSON, nullable=True)
    min_realm_stage = Column(String(32), nullable=True)
    min_realm_layer = Column(Integer, default=1, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianArtifactInventory(Base):
    __tablename__ = "xiuxian_artifact_inventory"
    __table_args__ = (UniqueConstraint("tg", "artifact_id", name="uq_xiuxian_artifact_inventory"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    artifact_id = Column(Integer, ForeignKey("xiuxian_artifacts.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    bound_quantity = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianEquippedArtifact(Base):
    __tablename__ = "xiuxian_equipped_artifacts"
    __table_args__ = (
        UniqueConstraint("tg", "slot", name="uq_xiuxian_equipped_artifact_slot"),
        UniqueConstraint("tg", "artifact_id", name="uq_xiuxian_equipped_artifact_unique"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    artifact_id = Column(Integer, ForeignKey("xiuxian_artifacts.id", ondelete="CASCADE"), nullable=False)
    slot = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianPillInventory(Base):
    __tablename__ = "xiuxian_pill_inventory"
    __table_args__ = (UniqueConstraint("tg", "pill_id", name="uq_xiuxian_pill_inventory"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    pill_id = Column(Integer, ForeignKey("xiuxian_pills.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianTalismanInventory(Base):
    __tablename__ = "xiuxian_talisman_inventory"
    __table_args__ = (UniqueConstraint("tg", "talisman_id", name="uq_xiuxian_talisman_inventory"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    talisman_id = Column(Integer, ForeignKey("xiuxian_talismans.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    bound_quantity = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianShopItem(Base):
    __tablename__ = "xiuxian_shop_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_tg = Column(BigInteger, nullable=True)
    shop_name = Column(String(64), nullable=False)
    item_kind = Column(String(16), nullable=False)
    item_ref_id = Column(Integer, nullable=False)
    item_name = Column(String(64), nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    price_stone = Column(Integer, default=0, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    is_official = Column(Boolean, default=False, nullable=False)
    notice_group_chat_id = Column(BigInteger, nullable=True)
    notice_group_message_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianAuctionItem(Base):
    __tablename__ = "xiuxian_auction_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_tg = Column(BigInteger, nullable=False)
    owner_display_name = Column(String(128), nullable=True)
    item_kind = Column(String(16), nullable=False)
    item_ref_id = Column(Integer, nullable=False)
    item_name = Column(String(64), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    opening_price_stone = Column(Integer, default=0, nullable=False)
    current_price_stone = Column(Integer, default=0, nullable=False)
    bid_increment_stone = Column(Integer, default=1, nullable=False)
    buyout_price_stone = Column(Integer, nullable=True)
    fee_percent = Column(Integer, default=0, nullable=False)
    highest_bidder_tg = Column(BigInteger, nullable=True)
    highest_bidder_display_name = Column(String(128), nullable=True)
    winner_tg = Column(BigInteger, nullable=True)
    winner_display_name = Column(String(128), nullable=True)
    bid_count = Column(Integer, default=0, nullable=False)
    status = Column(String(16), default="active", nullable=False)
    group_chat_id = Column(BigInteger, nullable=True)
    group_message_id = Column(Integer, nullable=True)
    final_price_stone = Column(Integer, nullable=True)
    seller_income_stone = Column(Integer, nullable=True)
    fee_amount_stone = Column(Integer, nullable=True)
    end_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianAuctionBid(Base):
    __tablename__ = "xiuxian_auction_bids"

    id = Column(Integer, primary_key=True, autoincrement=True)
    auction_id = Column(Integer, ForeignKey("xiuxian_auction_items.id", ondelete="CASCADE"), nullable=False)
    bidder_tg = Column(BigInteger, nullable=False)
    bidder_display_name = Column(String(128), nullable=True)
    bid_amount_stone = Column(Integer, default=0, nullable=False)
    action_type = Column(String(16), default="bid", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class XiuxianArena(Base):
    __tablename__ = "xiuxian_arenas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_tg = Column(BigInteger, nullable=False)
    owner_display_name = Column(String(128), nullable=True)
    champion_tg = Column(BigInteger, nullable=False)
    champion_display_name = Column(String(128), nullable=True)
    group_chat_id = Column(BigInteger, nullable=False)
    group_message_id = Column(Integer, nullable=True)
    realm_stage = Column(String(32), nullable=False, default=REALM_ORDER[0])
    duration_minutes = Column(Integer, default=120, nullable=False)
    reward_cultivation = Column(Integer, default=0, nullable=False)
    challenge_count = Column(Integer, default=0, nullable=False)
    defense_success_count = Column(Integer, default=0, nullable=False)
    champion_change_count = Column(Integer, default=0, nullable=False)
    battle_in_progress = Column(Boolean, default=False, nullable=False)
    current_challenger_tg = Column(BigInteger, nullable=True)
    current_challenger_display_name = Column(String(128), nullable=True)
    last_winner_tg = Column(BigInteger, nullable=True)
    last_winner_display_name = Column(String(128), nullable=True)
    last_loser_tg = Column(BigInteger, nullable=True)
    last_loser_display_name = Column(String(128), nullable=True)
    latest_result_summary = Column(Text, nullable=True)
    status = Column(String(16), default="active", nullable=False)
    end_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianDuelRecord(Base):
    __tablename__ = "xiuxian_duel_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    challenger_tg = Column(BigInteger, nullable=False)
    defender_tg = Column(BigInteger, nullable=False)
    winner_tg = Column(BigInteger, nullable=False)
    loser_tg = Column(BigInteger, nullable=False)
    duel_mode = Column(String(16), default="standard", nullable=False)
    challenger_rate = Column(Integer, default=500, nullable=False)
    defender_rate = Column(Integer, default=500, nullable=False)
    summary = Column(Text, nullable=True)
    battle_log = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class XiuxianBossConfig(Base):
    __tablename__ = "xiuxian_boss_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    boss_type = Column(String(16), default="personal", nullable=False)
    realm_stage = Column(String(32), nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(512), nullable=True)
    hp = Column(Integer, default=500, nullable=False)
    attack_power = Column(Integer, default=30, nullable=False)
    defense_power = Column(Integer, default=15, nullable=False)
    body_movement = Column(Integer, default=10, nullable=False)
    divine_sense = Column(Integer, default=10, nullable=False)
    fortune = Column(Integer, default=10, nullable=False)
    qi_blood = Column(Integer, default=500, nullable=False)
    true_yuan = Column(Integer, default=200, nullable=False)
    skill_name = Column(String(64), nullable=True)
    skill_ratio_percent = Column(Integer, default=30, nullable=False)
    skill_hit_bonus = Column(Integer, default=0, nullable=False)
    passive_name = Column(String(64), nullable=True)
    passive_effect_kind = Column(String(16), nullable=True)
    passive_ratio_percent = Column(Integer, default=0, nullable=False)
    passive_chance = Column(Integer, default=25, nullable=False)
    loot_pills_json = Column(JSON, nullable=True)
    loot_materials_json = Column(JSON, nullable=True)
    loot_artifacts_json = Column(JSON, nullable=True)
    loot_talismans_json = Column(JSON, nullable=True)
    loot_recipes_json = Column(JSON, nullable=True)
    loot_techniques_json = Column(JSON, nullable=True)
    stone_reward_min = Column(Integer, default=0, nullable=False)
    stone_reward_max = Column(Integer, default=0, nullable=False)
    cultivation_reward = Column(Integer, default=0, nullable=False)
    daily_attempt_limit = Column(Integer, default=3, nullable=False)
    ticket_cost_stone = Column(Integer, default=100, nullable=False)
    flavor_text = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianBossDefeat(Base):
    __tablename__ = "xiuxian_boss_defeats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    boss_id = Column(Integer, nullable=False)
    defeat_count = Column(Integer, default=1, nullable=False)
    daily_attempts = Column(Integer, default=0, nullable=False)
    day_key = Column(String(16), default="", nullable=False)
    last_defeated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("tg", "boss_id", name="uq_boss_defeat_tg_boss"),)


class XiuxianWorldBossInstance(Base):
    __tablename__ = "xiuxian_world_boss_instances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    boss_id = Column(Integer, nullable=False)
    current_hp = Column(Integer, nullable=False)
    max_hp = Column(Integer, nullable=False)
    status = Column(String(16), default="active", nullable=False)
    spawned_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    defeated_at = Column(DateTime, nullable=True)
    notice_message_id = Column(Integer, nullable=True)
    notice_group_chat_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class XiuxianWorldBossDamage(Base):
    __tablename__ = "xiuxian_world_boss_damages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_id = Column(Integer, nullable=False)
    tg = Column(BigInteger, nullable=False)
    total_damage = Column(Integer, default=0, nullable=False)
    attack_count = Column(Integer, default=0, nullable=False)
    last_attack_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("instance_id", "tg", name="uq_world_boss_dmg_instance_tg"),)
