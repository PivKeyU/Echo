import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit
from pydantic import BaseModel, Field
from sqlalchemy.engine import make_url
from typing import Dict, List, Optional, Union

# 嵌套式的数据设计，规范数据 config.json

MAX_INT_VALUE = 2147483647  # 2^31 - 1
MIN_INT_VALUE = -2147483648  # -2^31

DEFAULT_DB_HOST = "127.0.0.1"
DEFAULT_DB_USER = "echo"
DEFAULT_DB_PASSWORD = "echo"
DEFAULT_DB_NAME = "echo"
DEFAULT_DB_BACKEND = "postgresql"
DEFAULT_DB_PORTS = {
    "postgresql": 5432,
    "mysql": 3306,
}
DEFAULT_CONFIG_PATH = Path("data/config.json")
LEGACY_CONFIG_PATH = Path("config.json")
CONFIG_EXAMPLE_PATH = Path("config_example.json")
PLACEHOLDER_OWNER_API_VALUES = {0, 73711, 12345678}


def _normalize_backend_name(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"postgres", "postgresql", "pgsql"}:
        return "postgresql"
    if normalized in {"mysql", "mariadb"}:
        return "mysql"
    return DEFAULT_DB_BACKEND


def _infer_backend_from_legacy_config(config: dict) -> str:
    raw_url = str(config.get("db_url") or "").strip()
    if raw_url:
        try:
            backend = make_url(raw_url).get_backend_name()
            return _normalize_backend_name(backend)
        except Exception:
            pass

    docker_name = str(config.get("db_docker_name") or "").strip().lower()
    if docker_name in {"mysql", "mariadb"}:
        return "mysql"
    if docker_name in {"postgres", "postgresql", "pgsql"}:
        return "postgresql"

    raw_port = config.get("db_port")
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        port = None

    if port == DEFAULT_DB_PORTS["mysql"]:
        return "mysql"
    if port == DEFAULT_DB_PORTS["postgresql"]:
        return "postgresql"

    return DEFAULT_DB_BACKEND


def _normalize_text(value) -> str:
    return str(value or "").strip()


def _is_placeholder_text(value) -> bool:
    normalized = _normalize_text(value).lower()
    if not normalized:
        return True
    return (
        "replace_with" in normalized
        or normalized == "your_bot_username_without_at"
        or normalized == "your_main_group_username"
        or normalized == "your_channel_username"
        or normalized.startswith("1234567890:")
        or normalized.startswith("5701:aa")
    )


def _is_placeholder_owner_api(value) -> bool:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return True
    return normalized <= 0 or normalized in PLACEHOLDER_OWNER_API_VALUES


def _read_env_text(*names: str) -> Optional[str]:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        normalized = str(raw).strip()
        if normalized:
            return normalized
    return None


def _read_env_int(*names: str) -> Optional[int]:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        normalized = str(raw).strip()
        if not normalized:
            continue
        try:
            return int(normalized)
        except ValueError:
            continue
    return None

class ExDate(BaseModel):
    mon: int = 30
    sea: int = 90
    half: int = 180
    year: int = 365
    used: int = 0
    unused: int = -1
    code: str = 'code'
    link: str = 'link'


# class UserBuy(BaseModel):
#     stat: StrictBool
#
#     # 转换 字符串为布尔
#     @field_validator('stat', mode='before')
#     def convert_to_bool(cls, v):
#         if isinstance(v, str):
#             return v.lower() == 'y'
#         return v
#
#     text: bool
#     button: List[str]


class Open(BaseModel):
    stat: bool
    open_us: int = 30
    all_user: int
    timing: int = 0
    tem: Optional[int] = 0
    # allow_code: StrictBool
    # @field_validator('allow_code', mode='before')
    # def convert_to_bool(cls, v):
    #     if isinstance(v, str):
    #         return v.lower() == 'y'
    #     return v

    checkin: bool
    checkin_lv: Optional[str] = 'd'
    exchange: bool
    whitelist: bool
    invite: bool
    invite_lv: Optional[str] = 'b'
    leave_ban: bool
    uplays: bool = True
    checkin_reward: Optional[List[int]] = [1, 10]
    exchange_cost: int = 300
    whitelist_cost: int = 9999
    invite_cost: int = 1000
    srank_cost: int = 5
    change_pwd2_cost: int = 100

    # timing 持久化到 config.json 中，不再在初始化时强制重置。
    # 若重启前有活跃的计时任务，会在 bot 启动时由 _reset_stale_timing() 清理。


class Ranks(BaseModel):
    logo: str = "Echo"
    backdrop: bool = False


class Schedall(BaseModel):
    dayrank: bool = True
    weekrank: bool = True
    dayplayrank: bool = False
    weekplayrank: bool = True
    check_ex: bool = True
    low_activity: bool = False
    partition_check: bool = True
    day_ranks_message_id: int = 0
    week_ranks_message_id: int = 0
    restart_chat_id: int = 0
    restart_msg_id: int = 0
    backup_db: bool = True

    def __init__(self, **data):
        super().__init__(**data)
        if self.day_ranks_message_id == 0 or self.week_ranks_message_id == 0:
            if os.path.exists("log/rank.json"):
                with open("log/rank.json", "r") as f:
                    i = json.load(f)
                    self.day_ranks_message_id = i.get("day_ranks_message_id", 0)
                    self.week_ranks_message_id = i.get("week_ranks_message_id", 0)


class Proxy(BaseModel):
    scheme: Optional[str] = ""  # "socks4", "socks5" and "http" are supported
    hostname: Optional[str] = ""
    port: Optional[int] = None
    username: Optional[str] = ""
    password: Optional[str] = ""


class MP(BaseModel):
    status: bool = False
    url: Optional[str] = ""
    username: Optional[str] = ""
    password: Optional[str] = ""
    access_token: Optional[str] = ""
    price: int = 1
    download_log_chatid: Optional[int] = None
    lv: Optional[str] = "b"

class AutoUpdate(BaseModel):
    status: bool = True
    git_repo: Optional[str] = "PivKeyU/Echo"  # github仓库名/魔改的请填自己的仓库
    docker_image: Optional[str] = "echo/echo:latest"
    container_name: Optional[str] = "echo"
    compose_service: Optional[str] = "echo"
    check_interval_minutes: int = 30
    commit_sha: Optional[str] = None  # 最近一次commit
    image_digest: Optional[str] = None  # 最近一次已应用的镜像摘要
    last_remote_digest: Optional[str] = None  # 最近一次查询到的远端摘要
    last_checked_at: Optional[str] = None  # 最近一次检查时间
    last_remote_updated_at: Optional[str] = None  # 最近一次远端镜像更新时间
    last_status: Optional[str] = None  # 最近一次检查结果
    last_error: Optional[str] = None  # 最近一次错误
    up_description: Optional[str] = None  # 更新描述


class API(BaseModel):
    status: bool = False  # 默认关闭
    http_url: Optional[str] = "0.0.0.0"
    http_port: Optional[int] = 8838
    public_url: Optional[str] = ""
    miniapp_title: Optional[str] = "片刻面板"
    access_token: Optional[str] = ""
    admin_token: Optional[str] = ""
    # Webhook authentication is deliberately separate from both API tokens.
    webhook_secret: Optional[str] = ""
    webhook_replay_window: int = Field(default=300, ge=1, le=86400)
    webapp_auth_max_age: int = 86400
    allow_origins: Optional[List[Union[str, int]]] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.allow_origins is None:
            parsed = urlsplit(str(self.public_url or "").strip())
            self.allow_origins = [f"{parsed.scheme}://{parsed.netloc}"] if parsed.scheme and parsed.netloc else []


class RedEnvelope(BaseModel):
    status: bool = True  # 是否开启红包
    allow_private: bool = True # 是否允许专属红包


class Emotion(BaseModel):
    # 服务端 Emotion 集成适配器。凭据（integration credential）只由本服务持有，
    # 通过 HTTPS/私网 + Bearer 调用 Emotion /integration/v1 控制面，
    # 绝不返回给浏览器、Mini App 或普通 Telegram 请求。
    status: bool = False  # 是否启用 Emotion 联动
    url: Optional[str] = ""  # Emotion 服务地址，如 https://emotion.example.com
    credential: Optional[str] = ""  # Emotion 面板创建的 integration credential 明文（仅此配置持有）
    timeout: int = Field(default=10, ge=1, le=120)  # 请求超时（秒）
    max_retries: int = Field(default=1, ge=0, le=5)  # 失败后的额外重试次数
    # 追更事件轮询：领取/确认/释放订阅新集事件
    event_poll_interval: int = Field(default=60, ge=10, le=3600)  # 轮询间隔（秒）
    event_claim_limit: int = Field(default=50, ge=1, le=100)  # 单次领取上限
    notify_on_new_episode: bool = True  # 新集事件是否推送 TG 通知
class Config(BaseModel):
    bot_name: str
    bot_token: str
    owner_api: int
    owner_hash: str
    owner: int
    group: List[int]
    main_group: str
    chanel: str
    bot_photo: str
    open: Open
    admins: Optional[List[int]] = []
    money: str
    emby_api: str
    emby_url: str
    emby_block: Optional[List[str]] = []
    emby_line: str
    extra_emby_libs: Optional[List[str]] = []
    db_backend: str = DEFAULT_DB_BACKEND
    db_url: Optional[str] = None
    db_host: str = DEFAULT_DB_HOST
    db_user: str = DEFAULT_DB_USER
    db_pwd: str = DEFAULT_DB_PASSWORD
    db_name: str = DEFAULT_DB_NAME
    db_port: int = DEFAULT_DB_PORTS[DEFAULT_DB_BACKEND]
    tz_ad: Optional[str] = None
    tz_api: Optional[str] = None
    tz_id: Optional[List[Union[int, str]]] = []  # int for Nezha, str (UUID) for Komari
    tz_version: Optional[str] = "v0"  # "v0" for Nezha V0, "v1" for Nezha V1, "komari" for Komari
    tz_username: Optional[str] = None  # V1 API only
    tz_password: Optional[str] = None  # V1 API only
    ranks: Ranks
    schedall: Schedall
    db_is_docker: bool = False
    db_docker_name: str = "postgres"
    db_backup_dir: str = "./db_backup"
    db_backup_maxcount: int = 7
    # another_line: Optional[List[str]] = []
    # 如果使用的是 Python 3.10+ ，|运算符能用
    # w_anti_channel_ids: Optional[List[str | int]] = []
    w_anti_channel_ids: Optional[List[Union[str, int]]] = []
    proxy: Optional[Proxy] = Proxy()
    # kk指令中赠送资格的天数
    kk_gift_days: int = 30
    # 是否狙杀皮套人
    fuxx_pitao: bool = True
    # 活跃检测天数，默认21天
    activity_check_days: int = 21
    # 封存账号天数，默认5天
    freeze_days: int = 5
    # 白名单用户专属的emby线路
    emby_whitelist_line: Optional[str] = None
    # 被拦截的user-agent模式列表
    blocked_clients: Optional[List[str]] = None
    # 是否在检测到可疑客户端时终止会话
    client_filter_terminate_session: bool = True
    # 是否在检测到可疑客户端时封禁用户
    client_filter_block_user: bool = False
    # 分区名 -> 库名列表
    partition_libs: Dict[str, List[str]] = Field(default_factory=dict)
    moviepilot: MP = Field(default_factory=MP)
    auto_update: AutoUpdate = Field(default_factory=AutoUpdate)
    red_envelope: RedEnvelope = Field(default_factory=RedEnvelope)
    api: API = Field(default_factory=API)
    emotion: Emotion = Field(default_factory=Emotion)
    plugin_nav: Dict[str, bool] = Field(default_factory=dict)
    plugin_enabled: Dict[str, bool] = Field(default_factory=dict)
    # 全局 Emby 服务暂停开关：开启后所有用户的 Emby 账号将被禁用
    emby_service_suspended: bool = False

    def __init__(self, **data):
        super().__init__(**data)
        if self.owner in self.admins:
            self.admins.remove(self.owner)

    @classmethod
    def resolve_config_path(cls) -> Path:
        if DEFAULT_CONFIG_PATH.is_file():
            return DEFAULT_CONFIG_PATH

        if LEGACY_CONFIG_PATH.is_file():
            return LEGACY_CONFIG_PATH

        DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if CONFIG_EXAMPLE_PATH.is_file():
            shutil.copyfile(CONFIG_EXAMPLE_PATH, DEFAULT_CONFIG_PATH)
            return DEFAULT_CONFIG_PATH

        return LEGACY_CONFIG_PATH

    @classmethod
    def apply_runtime_defaults(cls, config: dict) -> dict:
        legacy_telegram_aliases = {
            "owner_api": ("api_id",),
            "owner_hash": ("api_hash",),
        }

        for target_key, alias_keys in legacy_telegram_aliases.items():
            current_value = config.get(target_key)
            needs_alias = (
                _is_placeholder_owner_api(current_value)
                if target_key == "owner_api"
                else _is_placeholder_text(current_value)
            )
            if not needs_alias:
                continue

            for alias_key in alias_keys:
                alias_value = config.get(alias_key)
                alias_invalid = (
                    _is_placeholder_owner_api(alias_value)
                    if target_key == "owner_api"
                    else _is_placeholder_text(alias_value)
                )
                if alias_invalid:
                    continue
                config[target_key] = int(alias_value) if target_key == "owner_api" else _normalize_text(alias_value)
                break

        telegram_env_candidates = {
            "bot_token": ("PIVKEYU_BOT_TOKEN", "BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
            "owner_api": ("PIVKEYU_OWNER_API", "OWNER_API", "API_ID"),
            "owner_hash": ("PIVKEYU_OWNER_HASH", "OWNER_HASH", "API_HASH"),
        }

        if _is_placeholder_text(config.get("bot_token")):
            env_bot_token = _read_env_text(*telegram_env_candidates["bot_token"])
            if env_bot_token and not _is_placeholder_text(env_bot_token):
                config["bot_token"] = env_bot_token

        if _is_placeholder_owner_api(config.get("owner_api")):
            env_owner_api = _read_env_int(*telegram_env_candidates["owner_api"])
            if env_owner_api is not None and not _is_placeholder_owner_api(env_owner_api):
                config["owner_api"] = env_owner_api

        if _is_placeholder_text(config.get("owner_hash")):
            env_owner_hash = _read_env_text(*telegram_env_candidates["owner_hash"])
            if env_owner_hash and not _is_placeholder_text(env_owner_hash):
                config["owner_hash"] = env_owner_hash

        defaults = {
            "db_backend": DEFAULT_DB_BACKEND,
            "db_host": DEFAULT_DB_HOST,
            "db_user": DEFAULT_DB_USER,
            "db_pwd": DEFAULT_DB_PASSWORD,
            "db_name": DEFAULT_DB_NAME,
        }

        for key, value in defaults.items():
            current = config.get(key)
            if current is None or not str(current).strip():
                config[key] = value

        raw_backend = config.get("db_backend")
        if raw_backend is None or not str(raw_backend).strip():
            backend = _infer_backend_from_legacy_config(config)
        else:
            backend = _normalize_backend_name(raw_backend)
        config["db_backend"] = backend

        current_port = config.get("db_port")
        if current_port in (None, ""):
            config["db_port"] = DEFAULT_DB_PORTS.get(backend, DEFAULT_DB_PORTS[DEFAULT_DB_BACKEND])

        current_docker_name = config.get("db_docker_name")
        if current_docker_name is None or not str(current_docker_name).strip():
            config["db_docker_name"] = "postgres" if backend == "postgresql" else "mysql"

        return config

    @classmethod
    def load_config(cls):
        config_path = cls.resolve_config_path()
        try:
            with open(config_path, "r", encoding="utf-8-sig") as f:
                config = cls.apply_runtime_defaults(json.load(f))
                return cls(**config)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"配置文件不是合法 JSON: {config_path} "
                f"(line {exc.lineno}, column {exc.colno})。"
            ) from exc

    def save_config(self):
        config_path = self.resolve_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=4, ensure_ascii=False)


class Yulv(BaseModel):
    wh_msg: List[str]
    red_bag: List[str]

    @classmethod
    def load_yulv(cls):
        with open("bot/func_helper/yvlu.json", "r", encoding="utf-8") as f:
            yulv = json.load(f)
            return cls(**yulv)
