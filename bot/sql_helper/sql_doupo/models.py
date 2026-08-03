from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from bot.sql_helper import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class DoupoSetting(Base):
    __tablename__ = "doupo_settings"

    setting_key = Column(String(64), primary_key=True)
    setting_value = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DoupoProfile(Base):
    __tablename__ = "doupo_profiles"
    __table_args__ = (
        Index("ix_doupo_profiles_realm", "realm_stage", "realm_stars"),
        Index("ix_doupo_profiles_updated", "updated_at"),
    )

    tg = Column(BigInteger, primary_key=True, autoincrement=False)
    display_name = Column(String(128), nullable=True)
    username = Column(String(64), nullable=True)
    realm_stage = Column(String(32), default="斗之气", nullable=False)
    realm_stars = Column(Integer, default=1, nullable=False)
    douqi = Column(Integer, default=0, nullable=False)
    gold = Column(Integer, default=0, nullable=False)
    fire_seed = Column(Integer, default=0, nullable=False)
    alchemy_exp = Column(Integer, default=0, nullable=False)
    beast_core = Column(Integer, default=0, nullable=False)
    sect_name = Column(String(64), nullable=True)
    sect_contribution = Column(Integer, default=0, nullable=False)
    pill_stock = Column(Integer, default=0, nullable=False)
    technique_key = Column(String(64), nullable=True)
    technique_level = Column(Integer, default=0, nullable=False)
    method_level = Column(Integer, default=0, nullable=False)
    fire_name = Column(String(64), nullable=True)
    fire_progress = Column(Integer, default=0, nullable=False)
    fire_rank = Column(Integer, default=0, nullable=False)
    academy_fire_energy = Column(Integer, default=0, nullable=False)
    faction_reputation = Column(Integer, default=0, nullable=False)
    black_corner_infamy = Column(Integer, default=0, nullable=False)
    pet_key = Column(String(64), nullable=True)
    pet_level = Column(Integer, default=0, nullable=False)
    boss_score = Column(Integer, default=0, nullable=False)
    tower_floor = Column(Integer, default=0, nullable=False)
    auction_credit = Column(Integer, default=0, nullable=False)
    breakthrough_failures = Column(Integer, default=0, nullable=False)
    cooldown_map = Column(JSON, nullable=True)
    sect_changed_at = Column(DateTime, nullable=True)
    last_sect_quest_at = Column(DateTime, nullable=True)
    last_train_at = Column(DateTime, nullable=True)
    last_breakthrough_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DoupoInventoryItem(Base):
    __tablename__ = "doupo_inventory_items"
    __table_args__ = (
        UniqueConstraint("tg", "item_key", name="uq_doupo_inventory_tg_item"),
        Index("ix_doupo_inventory_tg_category", "tg", "category"),
        Index("ix_doupo_inventory_tg_equipped", "tg", "equipped_slot"),
        Index("ix_doupo_inventory_updated", "updated_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    item_key = Column(String(64), nullable=False)
    category = Column(String(32), nullable=False)
    name = Column(String(128), nullable=False)
    rarity = Column(String(32), nullable=True)
    quantity = Column(Integer, default=0, nullable=False)
    equipped_slot = Column(String(32), nullable=True)
    item_meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DoupoItemDefinition(Base):
    __tablename__ = "doupo_item_definitions"
    __table_args__ = (
        Index("ix_doupo_item_definitions_category", "category", "enabled"),
        Index("ix_doupo_item_definitions_updated", "updated_at"),
    )

    item_key = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    category = Column(String(32), nullable=False)
    rarity = Column(String(32), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(512), nullable=True)
    tradable = Column(Boolean, default=False, nullable=False)
    stack_limit = Column(Integer, default=9999, nullable=False)
    equipment_slot = Column(String(32), nullable=True)
    attack = Column(Integer, default=0, nullable=False)
    defense = Column(Integer, default=0, nullable=False)
    agility = Column(Integer, default=0, nullable=False)
    fire_bonus = Column(Integer, default=0, nullable=False)
    alchemy_bonus = Column(Integer, default=0, nullable=False)
    recipe_config = Column(JSON, nullable=True)
    drop_sources = Column(JSON, nullable=True)
    version = Column(Integer, default=1, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    is_builtin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DoupoItemDefinitionVersion(Base):
    __tablename__ = "doupo_item_definition_versions"
    __table_args__ = (
        UniqueConstraint("item_key", "version", name="uq_doupo_item_version"),
        Index("ix_doupo_item_versions_key_created", "item_key", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_key = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False)
    snapshot = Column(JSON, nullable=False)
    change_note = Column(String(255), nullable=True)
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class DoupoEconomyLedger(Base):
    __tablename__ = "doupo_economy_ledgers"
    __table_args__ = (
        UniqueConstraint("tg", "day_key", name="uq_doupo_economy_tg_day"),
        Index("ix_doupo_economy_day", "day_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    day_key = Column(String(16), nullable=False)
    gold_income = Column(Integer, default=0, nullable=False)
    gold_sink = Column(Integer, default=0, nullable=False)
    action_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DoupoDailyActionCounter(Base):
    __tablename__ = "doupo_daily_action_counters"
    __table_args__ = (
        UniqueConstraint("tg", "day_key", "action_type", name="uq_doupo_daily_counter_tg_day_type"),
        Index("ix_doupo_daily_counter_tg_day", "tg", "day_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    day_key = Column(String(16), nullable=False)
    action_type = Column(String(32), nullable=False)
    used_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DoupoDuelHistory(Base):
    __tablename__ = "doupo_duel_histories"
    __table_args__ = (
        Index("ix_doupo_duel_challenger", "challenger_tg", "created_at"),
        Index("ix_doupo_duel_defender", "defender_tg", "created_at"),
        Index("ix_doupo_duel_winner", "winner_tg", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    challenger_tg = Column(BigInteger, nullable=False)
    defender_tg = Column(BigInteger, nullable=False)
    winner_tg = Column(BigInteger, nullable=False)
    loser_tg = Column(BigInteger, nullable=False)
    stake_gold = Column(Integer, default=0, nullable=False)
    challenger_power = Column(Integer, default=0, nullable=False)
    defender_power = Column(Integer, default=0, nullable=False)
    challenger_win_rate = Column(Integer, default=50, nullable=False)
    roll = Column(Integer, default=0, nullable=False)
    battle_log = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class DoupoExpedition(Base):
    __tablename__ = "doupo_expeditions"
    __table_args__ = (
        Index("ix_doupo_expeditions_tg_status", "tg", "status"),
        Index("ix_doupo_expeditions_updated", "updated_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    region_key = Column(String(64), nullable=False)
    status = Column(String(24), default="active", nullable=False)
    step = Column(Integer, default=0, nullable=False)
    max_steps = Column(Integer, default=4, nullable=False)
    vitality = Column(Integer, default=100, nullable=False)
    max_vitality = Column(Integer, default=100, nullable=False)
    danger = Column(Integer, default=0, nullable=False)
    loot = Column(JSON, nullable=True)
    current_event_key = Column(String(64), nullable=True)
    history = Column(JSON, nullable=True)
    settlement = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class DoupoAction(Base):
    __tablename__ = "doupo_actions"
    __table_args__ = (
        UniqueConstraint("action_key", name="uq_doupo_action_key"),
        Index("ix_doupo_actions_enabled_order", "enabled", "sort_order"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_key = Column(String(64), nullable=False)
    name = Column(String(64), nullable=False)
    description = Column(String(255), nullable=True)
    # type: train|adventure|alchemy|fire|breakthrough
    action_type = Column(String(32), default="train", nullable=False)
    cooldown_seconds = Column(Integer, default=0, nullable=False)
    # 通用数值配置：例如 {"douqi_min":20,"douqi_max":60,"gold_min":5,"gold_max":20}
    reward_config = Column(JSON, nullable=True)
    # 通用门槛配置：例如 {"realm_stars_min":3,"gold_cost":100}
    requirement_config = Column(JSON, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DoupoJournal(Base):
    __tablename__ = "doupo_journals"
    __table_args__ = (
        Index("ix_doupo_journals_tg_created", "tg", "created_at"),
        Index("ix_doupo_journals_action", "action_type", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    action_type = Column(String(32), nullable=False)
    title = Column(String(128), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
