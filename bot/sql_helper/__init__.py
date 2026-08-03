"""
初始化数据库
"""
import os
import importlib
import time
from pathlib import Path

from bot import db_backend, db_host, db_user, db_pwd, db_name, db_port, db_url, db_docker_name
from bot import LOGGER
from sqlalchemy import MetaData, Integer, create_engine, func, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        LOGGER.warning(f"环境变量 {name}={raw!r} 不是有效整数，回退到默认值 {default}")
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# 创建engine对象
def _validate_db_config():
    configured_url = str(db_url or "").strip()
    if configured_url:
        return

    missing = []
    for key, value in {
        "db_host": db_host,
        "db_user": db_user,
        "db_name": db_name,
    }.items():
        if value is None or not str(value).strip():
            missing.append(key)

    if missing:
        raise RuntimeError(
            "数据库配置缺失: "
            + ", ".join(missing)
            + "。请在 config.json 中设置 db_host/db_user/db_pwd/db_name，例如 "
            + "db_host=127.0.0.1, db_user=echo, db_pwd=echo, db_name=echo"
        )

    normalized_backend = _normalize_db_backend(db_backend)
    docker_name = str(db_docker_name or "").strip().lower()

    try:
        port = int(db_port)
    except (TypeError, ValueError):
        raise RuntimeError(
            f"数据库端口配置无效: db_port={db_port!r}。"
            "请在 config.json 中填写有效整数，PostgreSQL 默认 5432，MySQL 默认 3306。"
        ) from None

    if normalized_backend == "postgresql" and port == 3306:
        raise RuntimeError(
            "数据库配置冲突: 当前使用的是 PostgreSQL 驱动，但 db_port=3306。"
            "3306 是 MySQL 默认端口，PostgreSQL 默认端口应为 5432。"
            "请把 data/config.json 中的 db_port 改为 5432；"
            "如果你实际上仍在使用 MySQL，请把 db_backend 改回 mysql。"
        )

    if normalized_backend == "mysql" and port == 5432:
        raise RuntimeError(
            "数据库配置冲突: 当前使用的是 MySQL 驱动，但 db_port=5432。"
            "5432 是 PostgreSQL 默认端口，MySQL 默认端口应为 3306。"
            "请把 data/config.json 中的 db_port 改为 3306；"
            "如果你实际上已经切换到 PostgreSQL，请把 db_backend 改为 postgresql。"
        )

    if normalized_backend == "postgresql" and docker_name == "mysql":
        LOGGER.warning(
            "检测到 db_backend=postgresql，但 db_docker_name 仍为 mysql。"
            "这会影响数据库备份/恢复容器名，请改为 postgres。"
        )

    if normalized_backend == "mysql" and docker_name == "postgres":
        LOGGER.warning(
            "检测到 db_backend=mysql，但 db_docker_name 仍为 postgres。"
            "这会影响数据库备份/恢复容器名，请改为 mysql。"
        )

def _normalize_db_backend(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"postgres", "postgresql", "pgsql"}:
        return "postgresql"
    if normalized in {"mysql", "mariadb"}:
        return "mysql"
    return "postgresql"


_validate_db_config()


def _build_database_url() -> str:
    raw_url = str(db_url or "").strip()
    if raw_url:
        return raw_url

    normalized_backend = _normalize_db_backend(db_backend)

    if normalized_backend == "mysql":
        return URL.create(
            "mysql+pymysql",
            username=db_user,
            password=db_pwd,
            host=db_host,
            port=int(db_port),
            database=db_name,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)

    if normalized_backend == "postgresql":
        return URL.create(
            "postgresql+psycopg",
            username=db_user,
            password=db_pwd,
            host=db_host,
            port=int(db_port),
            database=db_name,
        ).render_as_string(hide_password=False)

    raise RuntimeError(f"暂不支持的数据库后端: {db_backend}")


DATABASE_URL = _build_database_url()
DB_BACKEND = make_url(DATABASE_URL).get_backend_name()
DB_STARTUP_MAX_RETRIES = max(1, int(os.getenv("PIVKEYU_DB_STARTUP_MAX_RETRIES", "20")))
DB_STARTUP_RETRY_DELAY = max(0.5, float(os.getenv("PIVKEYU_DB_STARTUP_RETRY_DELAY", "3")))
DB_CONNECT_TIMEOUT = _env_int("PIVKEYU_DB_CONNECT_TIMEOUT", 5, 1)
DB_POOL_SIZE = _env_int("PIVKEYU_DB_POOL_SIZE", 32, 1)
DB_MAX_OVERFLOW = _env_int("PIVKEYU_DB_MAX_OVERFLOW", 32, 0)
DB_POOL_TIMEOUT = _env_int("PIVKEYU_DB_POOL_TIMEOUT", 30, 1)
DB_POOL_RECYCLE = _env_int("PIVKEYU_DB_POOL_RECYCLE", 60 * 15, 30)
DB_POOL_PRE_PING = _env_bool("PIVKEYU_DB_POOL_PRE_PING", True)
DB_POOL_USE_LIFO = _env_bool("PIVKEYU_DB_POOL_USE_LIFO", True)
DB_POOL_RESET_ON_RETURN = (os.getenv("PIVKEYU_DB_POOL_RESET_ON_RETURN", "rollback") or "rollback").strip()


def _build_connect_args() -> dict:
    if DB_BACKEND == "mysql":
        return {
            "init_command": "SET NAMES utf8mb4",
            "connect_timeout": DB_CONNECT_TIMEOUT,
        }

    if DB_BACKEND == "postgresql":
        return {
            "connect_timeout": DB_CONNECT_TIMEOUT,
        }

    return {}

engine = create_engine(
    DATABASE_URL,
    echo=False,
    echo_pool=False,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_recycle=DB_POOL_RECYCLE,
    pool_pre_ping=DB_POOL_PRE_PING,
    pool_use_lifo=DB_POOL_USE_LIFO,
    pool_reset_on_return=DB_POOL_RESET_ON_RETURN,
    connect_args=_build_connect_args(),
)

# 创建Base对象
Base = declarative_base()
Base.metadata.bind = engine

_MIGRATION_GUARD_ENV = "PIVKEYU_RUNNING_MIGRATIONS"


def _quote_postgresql_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _format_postgresql_relation_name(schema: str | None, table_name: str) -> str:
    if schema:
        return f"{_quote_postgresql_identifier(schema)}.{_quote_postgresql_identifier(table_name)}"
    return _quote_postgresql_identifier(table_name)


def sync_postgresql_sequences(*, table_names: set[str] | None = None, log_result: bool = False) -> dict[str, object]:
    if DB_BACKEND != "postgresql":
        return {"applied": False, "tables": []}

    metadata = MetaData()
    reflect_kwargs = {"only": sorted(table_names)} if table_names else {}
    metadata.reflect(bind=engine, **reflect_kwargs)
    repaired_tables: list[dict[str, object]] = []

    with engine.begin() as connection:
        for table in metadata.sorted_tables:
            if table_names and table.name not in table_names:
                continue

            primary_key_columns = list(table.primary_key.columns)
            if len(primary_key_columns) != 1:
                continue

            column = primary_key_columns[0]
            if not isinstance(column.type, Integer):
                continue

            qualified_table_name = _format_postgresql_relation_name(table.schema, table.name)
            try:
                sequence_name = connection.execute(
                    text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                    {"table_name": qualified_table_name, "column_name": column.name},
                ).scalar()
            except Exception:
                LOGGER.warning(
                    f"跳过 PostgreSQL 序列校正：无法获取 {qualified_table_name}.{column.name} 对应的序列"
                )
                continue
            if not sequence_name:
                continue

            max_id = connection.execute(select(func.max(column)).select_from(table)).scalar()
            if max_id is None:
                connection.execute(
                    text("SELECT setval(CAST(:sequence_name AS regclass), 1, false)"),
                    {"sequence_name": sequence_name},
                )
                next_value = 1
            else:
                current_value = int(max_id)
                connection.execute(
                    text("SELECT setval(CAST(:sequence_name AS regclass), :value, true)"),
                    {"sequence_name": sequence_name, "value": current_value},
                )
                next_value = current_value + 1

            repaired_tables.append(
                {
                    "table": table.name,
                    "column": column.name,
                    "sequence": sequence_name,
                    "next_value": next_value,
                }
            )

    if log_result and repaired_tables:
        LOGGER.info(f"PostgreSQL 自增序列校正完成，共处理 {len(repaired_tables)} 张表")
    return {"applied": bool(repaired_tables), "tables": repaired_tables}


def _run_with_db_retry(action, description: str):
    last_error = None

    for attempt in range(1, DB_STARTUP_MAX_RETRIES + 1):
        try:
            return action()
        except OperationalError as exc:
            last_error = exc
            if attempt >= DB_STARTUP_MAX_RETRIES:
                break
            LOGGER.warning(
                f"{description}失败，数据库暂未就绪，"
                f"将在 {DB_STARTUP_RETRY_DELAY:g} 秒后重试 "
                f"({attempt}/{DB_STARTUP_MAX_RETRIES})：{exc}"
            )
            time.sleep(DB_STARTUP_RETRY_DELAY)

    raise last_error


def _legacy_create_all_tables():
    """
    在未安装 Alembic 或配置缺失时兜底建表，保证服务可启动。
    """
    from bot.sql_helper import sql_bot_access, sql_code, sql_emby, sql_emby2, sql_invite, sql_moderation, sql_partition, sql_plugin, sql_request_record, sql_shop, sql_xiuxian  # noqa: F401

    _run_with_db_retry(
        lambda: Base.metadata.create_all(bind=engine, checkfirst=True),
        "数据库建表",
    )


def run_migrations():
    """
    启动时自动执行数据库迁移到最新版本。
    """
    if os.getenv(_MIGRATION_GUARD_ENV) == "1":
        return

    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    if not alembic_ini.exists():
        LOGGER.warning(f"未找到 Alembic 配置文件，跳过自动迁移: {alembic_ini}")
        _legacy_create_all_tables()
        return

    os.environ[_MIGRATION_GUARD_ENV] = "1"
    try:
        try:
            alembic_command = importlib.import_module("alembic.command")
            alembic_config = importlib.import_module("alembic.config")
        except ImportError:
            LOGGER.warning("未安装 alembic，跳过自动迁移")
            _legacy_create_all_tables()
            return

        Config = getattr(alembic_config, "Config")
        config = Config(str(alembic_ini))
        config.set_main_option("sqlalchemy.url", DATABASE_URL)
        started_at = time.perf_counter()
        _run_with_db_retry(
            lambda: alembic_command.upgrade(config, "head"),
            "数据库自动迁移",
        )
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        LOGGER.info(f"数据库迁移完成，当前已升级到最新版本，耗时 {elapsed_ms}ms")
    except Exception as e:
        LOGGER.error(f"数据库自动迁移失败: {e}")
        fallback = os.getenv("PIVKEYU_DB_MIGRATE_FALLBACK", "").strip().lower()
        if fallback in {"1", "true", "yes", "on", "create_all", "create-all"}:
            # 可控降级：迁移脚本异常时允许以 Base.metadata.create_all 兜底建表
            # （仅补齐缺失表/列，不修改已有结构），保证服务可启动。
            # 生产环境应保持默认 fail-fast，迁移失败时人工介入修复。
            LOGGER.warning("检测到 PIVKEYU_DB_MIGRATE_FALLBACK，降级为 create_all 兜底建表")
            _legacy_create_all_tables()
            return
        raise
    finally:
        os.environ.pop(_MIGRATION_GUARD_ENV, None)


# 调用 sql_start() 返回一个轻量工厂。每次 Session() 都创建独立会话，
# 避免同线程嵌套 with Session() 时复用 scoped_session，导致内层 close()
# 把外层事务对象提前关闭，引发 "Instance ... is not persistent within this Session"。
class _SessionFactory:
    def __init__(self):
        self._maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def __call__(self):
        return self._maker()

    def remove(self) -> None:
        # 兼容旧调用路径；非 scoped_session 下无需显式移除线程本地会话。
        return None

    def close_all(self) -> None:
        self._maker.close_all()


def sql_start() -> _SessionFactory:
    return _SessionFactory()


Session = sql_start()


run_migrations()
if _env_bool("PIVKEYU_DB_SYNC_SEQUENCES_ON_STARTUP", False):
    sync_postgresql_sequences(log_result=True)
