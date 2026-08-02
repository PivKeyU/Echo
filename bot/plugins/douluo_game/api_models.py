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


class HuntPayload(InitDataPayload):
    region_key: str = ""


class InventoryEquipmentPayload(InitDataPayload):
    item_key: str = ""
    slot: str = ""


class ExchangePayload(InitDataPayload):
    # coin_to_fragment: 金魂币 -> Emby 碎片
    # fragment_to_coin: Emby 碎片 -> 金魂币
    direction: Literal["coin_to_fragment", "fragment_to_coin"]
    amount: int = Field(ge=1)


class DailyTaskClaimPayload(InitDataPayload):
    task_key: str


class SectJoinPayload(InitDataPayload):
    sect_key: str


class AuctionListPayload(InitDataPayload):
    item_key: str
    price: int = Field(ge=1)
    duration_hours: int | None = None


class AuctionBidPayload(InitDataPayload):
    listing_id: int
    price: int = Field(ge=1)


class BossChallengePayload(InitDataPayload):
    boss_key: str = ""


class RankPayload(InitDataPayload):
    kind: str = "power"


class AdminBootstrapPayload(BaseModel):
    token: str | None = None
    init_data: str | None = None
    player_query: str | None = None
    player_page: int = 1
    player_page_size: int = 10


class AdminSettingsPayload(BaseModel):
    exchange_enabled: bool | None = None
    exchange_rate: int | None = None
    min_coin_to_exchange: int | None = None
    daily_action_points: int | None = None
    daily_action_limits: dict[str, int] | None = None
    action_point_costs: dict[str, int] | None = None
    daily_coin_soft_cap: int | None = None
    daily_coin_hard_cap: int | None = None
    daily_coin_overflow_percent: int | None = None
    daily_soul_power_soft_cap: int | None = None
    daily_soul_power_hard_cap: int | None = None
    soul_power_overflow_percent: int | None = None
    wuhun_awaken_coin: int | None = None
    wuhun_reforge_coin: int | None = None
    wuhun_reforge_cd_hours: int | None = None
    hunt_absorb_fee: int | None = None
    event_chance_percent: int | None = None
    auction_fee_percent: int | None = None
    auction_duration_hours: int | None = None
    duel_min_stake: int | None = None
    duel_max_stake: int | None = None
    duel_prepare_seconds: int | None = None
    broadcast_enabled: bool | None = None
    message_auto_delete_seconds: int | None = None


class AdminProfilePatchPayload(BaseModel):
    soul_power: int | None = None
    coin: int | None = None
    spirit_power: int | None = None
    innate_soul_power: int | None = None
    realm_stage: str | None = None
    realm_stars: int | None = None
    boss_score: int | None = None


class AdminItemDefinitionPayload(BaseModel):
    item_key: str
    name: str = ""
    category: str = "material"
    rarity: str = "凡品"
    description: str = ""
    icon: str = ""
    equipment_slot: str | None = None
    attack: int = Field(default=0, ge=0, le=2_000_000_000)
    defense: int = Field(default=0, ge=0, le=2_000_000_000)
    speed: int = Field(default=0, ge=0, le=2_000_000_000)
    spirit: int = Field(default=0, ge=0, le=2_000_000_000)
    trigger_chance: float | None = None
    skill: str | None = None
    recipe_config: dict = Field(default_factory=dict)
    drop_sources: list[dict] = Field(default_factory=list)
    enabled: bool = True


class AdminItemGrantPayload(BaseModel):
    item_key: str
    quantity: int = Field(default=1, ge=1, le=2_000_000_000)


class AdminItemTogglePayload(BaseModel):
    enabled: bool
