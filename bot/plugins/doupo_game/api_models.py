from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InitDataPayload(BaseModel):
    init_data: str = ""
    session_token: str = ""


class WebAuthRegisterPayload(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    init_data: str = ""


class WebAuthLoginPayload(BaseModel):
    username: str
    password: str
    init_data: str = ""


class WebAuthSessionPayload(BaseModel):
    session_token: str = ""
    init_data: str = ""


class WebAuthBindTelegramPayload(WebAuthSessionPayload):
    init_data: str


class AdminGameAccountStatePayload(BaseModel):
    enabled: bool


class ActionRunPayload(InitDataPayload):
    action_key: str
    # Optional action-specific parameters reserved for admin-defined actions.
    params: dict = Field(default_factory=dict)


class InventoryEquipmentPayload(InitDataPayload):
    item_key: str


class ExpeditionStartPayload(InitDataPayload):
    region_key: str


class ExpeditionChoicePayload(InitDataPayload):
    choice_key: str
    focus_score: int = 50


class ExchangePayload(InitDataPayload):
    # coin_to_gold: Emby coin -> doupo gold
    # gold_to_coin: doupo gold -> Emby coin
    direction: Literal["coin_to_gold", "gold_to_coin"]
    amount: int


class SectJoinPayload(InitDataPayload):
    sect_key: str


class SectTransferPayload(InitDataPayload):
    sect_key: str


class SectLeavePayload(InitDataPayload):
    pass


class SectQuestClaimPayload(InitDataPayload):
    pass


class AdminBootstrapPayload(BaseModel):
    token: str | None = None
    init_data: str | None = None
    player_query: str | None = None
    player_page: int = 1
    player_page_size: int = 10


class AdminSettingsPayload(BaseModel):
    exchange_enabled: bool | None = None
    exchange_rate: int | None = None
    min_gold_to_exchange: int | None = None
    gold_min_to_buy: int | None = None
    daily_gold_action_cap: int | None = None
    daily_train_limit: int | None = None
    daily_expedition_limit: int | None = None
    daily_action_points: int | None = None
    daily_action_limits: dict[str, int] | None = None
    action_point_costs: dict[str, int] | None = None
    daily_douqi_soft_cap: int | None = None
    daily_douqi_hard_cap: int | None = None
    daily_douqi_overflow_percent: int | None = None
    breakthrough_failure_douqi_loss_percent: int | None = None
    duel_min_stake: int | None = None
    duel_max_stake: int | None = None
    duel_prepare_seconds: int | None = None
    broadcast_enabled: bool | None = None
    message_auto_delete_seconds: int | None = None
    expedition_boss_chance: int | None = None
    expedition_hidden_event_chance: int | None = None
    sect_transfer_cooldown_days: int | None = None
    sect_transfer_cost: int | None = None
    sect_transfer_contribution_retain: int | None = None
    sect_leave_gold_cost: int | None = None


class PlayerResourceGrantPayload(BaseModel):
    resource: Literal[
        "gold",
        "douqi",
        "fire_seed",
        "alchemy_exp",
        "beast_core",
        "sect_contribution",
        "pill_stock",
        "technique_level",
        "method_level",
        "fire_rank",
        "pet_level",
        "academy_fire_energy",
        "faction_reputation",
        "black_corner_infamy",
        "fire_progress",
        "boss_score",
        "tower_floor",
        "auction_credit",
        "realm_stage",
        "realm_stars",
        "fire_name",
    ] = "gold"
    amount: int = 1


class AdminItemDefinitionPayload(BaseModel):
    item_key: str
    name: str
    category: Literal["pill", "herb", "ore", "core", "fire", "technique", "method", "gear", "token"]
    rarity: str = "凡品"
    description: str = ""
    icon: str = ""
    tradable: bool = False
    stack_limit: int = Field(default=9999, ge=1, le=2_000_000_000)
    equipment_slot: Literal["weapon", "armor", "boots", "accessory", "ring", "cauldron"] | None = None
    attack: int = Field(default=0, ge=0, le=2_000_000_000)
    defense: int = Field(default=0, ge=0, le=2_000_000_000)
    agility: int = Field(default=0, ge=0, le=2_000_000_000)
    fire_bonus: int = Field(default=0, ge=0, le=2_000_000_000)
    alchemy_bonus: int = Field(default=0, ge=0, le=2_000_000_000)
    recipe_config: dict = Field(default_factory=dict)
    drop_sources: list[dict] = Field(default_factory=list)
    enabled: bool = True
    change_note: str = ""


class AdminItemRollbackPayload(BaseModel):
    version: int = Field(ge=1)


class AdminItemGrantPayload(BaseModel):
    item_key: str
    quantity: int = Field(default=1, ge=1, le=2_000_000_000)


class AdminActionPayload(BaseModel):
    action_key: str
    name: str
    description: str = ""
    action_type: Literal[
        "train",
        "adventure",
        "alchemy",
        "craft",
        "fire",
        "sect",
        "auction",
        "pill",
        "technique",
        "boss",
        "tower",
        "faction",
        "pet",
        "black_corner",
        "breakthrough",
    ] = "train"
    cooldown_seconds: int = 0
    reward_config: dict = Field(default_factory=dict)
    requirement_config: dict = Field(default_factory=dict)
    enabled: bool = True
    sort_order: int = 0
