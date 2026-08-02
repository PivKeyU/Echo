from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from bot.sql_helper import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class DouluoSetting(Base):
    __tablename__ = "douluo_settings"

    setting_key = Column(String(64), primary_key=True)
    setting_value = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DouluoProfile(Base):
    __tablename__ = "douluo_profiles"
    __table_args__ = (
        Index("ix_douluo_profiles_realm", "realm_stage", "realm_stars"),
        Index("ix_douluo_profiles_updated", "updated_at"),
    )

    tg = Column(BigInteger, primary_key=True, autoincrement=False)
    display_name = Column(String(128), nullable=True)
    username = Column(String(64), nullable=True)

    realm_stage = Column(String(32), default="魂士", nullable=False)
    realm_stars = Column(Integer, default=1, nullable=False)
    soul_power = Column(Integer, default=0, nullable=False)
    coin = Column(Integer, default=0, nullable=False)
    spirit_power = Column(Integer, default=0, nullable=False)

    # 武魂
    innate_soul_power = Column(Integer, default=0, nullable=False)
    wuhun_key = Column(String(64), nullable=True)
    wuhun_name = Column(String(64), nullable=True)
    wuhun_system = Column(String(16), nullable=True)
    wuhun_quality = Column(String(16), nullable=True)
    reforge_at = Column(DateTime, nullable=True)

    # 进阶
    breakthrough_failures = Column(Integer, default=0, nullable=False)

    # 宗门
    sect_key = Column(String(64), nullable=True)
    sect_contribution = Column(Integer, default=0, nullable=False)
    sect_position = Column(String(32), nullable=True)
    last_salary_at = Column(DateTime, nullable=True)

    # 战绩
    boss_score = Column(Integer, default=0, nullable=False)
    arena_wins = Column(Integer, default=0, nullable=False)
    arena_losses = Column(Integer, default=0, nullable=False)
    total_hunts = Column(Integer, default=0, nullable=False)

    last_train_at = Column(DateTime, nullable=True)
    last_breakthrough_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DouluoSoulRing(Base):
    __tablename__ = "douluo_soul_rings"
    __table_args__ = (
        UniqueConstraint("tg", "slot", name="uq_douluo_soul_ring_slot"),
        Index("ix_douluo_soul_rings_tg", "tg"),
        Index("ix_douluo_soul_rings_tg_years", "tg", "years"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    slot = Column(Integer, nullable=False)
    years = Column(Integer, default=0, nullable=False)
    tier = Column(String(16), nullable=False)
    color = Column(String(16), nullable=False)
    skill_name = Column(String(64), nullable=True)
    attack = Column(Integer, default=0, nullable=False)
    defense = Column(Integer, default=0, nullable=False)
    speed = Column(Integer, default=0, nullable=False)
    spirit = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DouluoInventoryItem(Base):
    __tablename__ = "douluo_inventory_items"
    __table_args__ = (
        UniqueConstraint("tg", "item_key", name="uq_douluo_inventory_tg_item"),
        Index("ix_douluo_inventory_tg_category", "tg", "category"),
        Index("ix_douluo_inventory_tg_equipped", "tg", "equipped_slot"),
        Index("ix_douluo_inventory_updated", "updated_at"),
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


class DouluoItemDefinition(Base):
    __tablename__ = "douluo_item_definitions"
    __table_args__ = (
        Index("ix_douluo_item_definitions_category", "category", "enabled"),
        Index("ix_douluo_item_definitions_updated", "updated_at"),
    )

    item_key = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    category = Column(String(32), nullable=False)
    rarity = Column(String(32), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(512), nullable=True)
    equipment_slot = Column(String(32), nullable=True)
    attack = Column(Integer, default=0, nullable=False)
    defense = Column(Integer, default=0, nullable=False)
    speed = Column(Integer, default=0, nullable=False)
    spirit = Column(Integer, default=0, nullable=False)
    trigger_chance = Column(Float, nullable=True)
    skill = Column(String(64), nullable=True)
    recipe_config = Column(JSON, nullable=True)
    drop_sources = Column(JSON, nullable=True)
    version = Column(Integer, default=1, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    is_builtin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DouluoDailyActionCounter(Base):
    __tablename__ = "douluo_daily_action_counters"
    __table_args__ = (
        UniqueConstraint("tg", "day_key", "action_type", name="uq_douluo_counter"),
        Index("ix_douluo_counters_tg_day", "tg", "day_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    day_key = Column(String(16), nullable=False)
    action_type = Column(String(64), nullable=False)
    used_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DouluoJournal(Base):
    __tablename__ = "douluo_journals"
    __table_args__ = (
        Index("ix_douluo_journals_tg_created", "tg", "created_at"),
        Index("ix_douluo_journals_action", "action_type", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    action_type = Column(String(32), nullable=False)
    title = Column(String(128), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class DouluoSectMember(Base):
    __tablename__ = "douluo_sect_members"
    __table_args__ = (
        Index("ix_douluo_sect_members_sect", "sect_key", "contribution"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, unique=True, nullable=False)
    sect_key = Column(String(64), nullable=False)
    position = Column(String(32), default="弟子", nullable=False)
    contribution = Column(Integer, default=0, nullable=False)
    total_contribution = Column(Integer, default=0, nullable=False)
    last_salary_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DouluoDailyTask(Base):
    __tablename__ = "douluo_daily_tasks"
    __table_args__ = (
        UniqueConstraint("tg", "day_key", "task_key", name="uq_douluo_daily_task"),
        Index("ix_douluo_daily_tasks_tg_day", "tg", "day_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    day_key = Column(String(16), nullable=False)
    task_key = Column(String(64), nullable=False)
    progress = Column(Integer, default=0, nullable=False)
    claimed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DouluoAuctionListing(Base):
    __tablename__ = "douluo_auction_listings"
    __table_args__ = (
        Index("ix_douluo_auctions_seller", "seller_tg", "status"),
        Index("ix_douluo_auctions_status_ends", "status", "ends_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    seller_tg = Column(BigInteger, nullable=False)
    item_key = Column(String(64), nullable=False)
    item_name = Column(String(128), nullable=False)
    category = Column(String(32), nullable=False)
    rarity = Column(String(32), nullable=True)
    start_price = Column(Integer, default=0, nullable=False)
    current_bid = Column(Integer, default=0, nullable=False)
    bidder_tg = Column(BigInteger, nullable=True)
    bidder_display = Column(String(128), nullable=True)
    fee_paid = Column(Integer, default=0, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    status = Column(String(16), default="open", nullable=False)
    bids = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DouluoBossRecord(Base):
    __tablename__ = "douluo_boss_records"
    __table_args__ = (
        UniqueConstraint("tg", "boss_key", name="uq_douluo_boss_record"),
        Index("ix_douluo_boss_records_tg", "tg"),
        Index("ix_douluo_boss_records_boss", "boss_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False)
    boss_key = Column(String(64), nullable=False)
    boss_name = Column(String(64), nullable=False)
    times = Column(Integer, default=0, nullable=False)
    wins = Column(Integer, default=0, nullable=False)
    best_score = Column(Integer, default=0, nullable=False)
    last_result = Column(String(16), nullable=True)
    last_fought_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
