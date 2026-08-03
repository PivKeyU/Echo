"""
基本的sql操作
"""
import os
from datetime import datetime, timezone, timedelta

from bot.func_helper import redis_cache
from bot.sql_helper import Base, Session
from bot.sql_helper.credential_crypto import CredentialType, decrypt_credential, encrypt_credential
from sqlalchemy import Column, BigInteger, String, DateTime, Integer, case
from sqlalchemy import func
from sqlalchemy import or_
from bot import LOGGER

EMBY_CACHE_TTL = max(int(os.getenv("PIVKEYU_REDIS_EMBY_TTL", "300") or 300), 1)
EMBY_CACHE_MISS_TTL = max(int(os.getenv("PIVKEYU_REDIS_EMBY_MISS_TTL", "60") or 60), 1)
_CACHE_ABSENT = object()
SHANGHAI_TZ = timezone(timedelta(hours=8))



class Emby(Base):
    """
    emby表，tg主键，默认值lv，us，iv
    """
    __tablename__ = 'emby'
    tg = Column(BigInteger, primary_key=True, autoincrement=False)
    embyid = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)
    pwd = Column(CredentialType(), nullable=True)
    pwd2 = Column(CredentialType(), nullable=True)
    lv = Column(String(1), default='d')
    cr = Column(DateTime, nullable=True)
    ex = Column(DateTime, nullable=True)
    us = Column(Integer, default=0)
    iv = Column(BigInteger, default=0)
    ch = Column(DateTime, nullable=True)


def _normalize_lookup_value(value) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _emby_record_cache_key(tg: int | str) -> str:
    return redis_cache.build_key("emby", "record", int(tg))


def _emby_lookup_cache_key(value) -> str:
    return redis_cache.build_key("emby", "lookup", _normalize_lookup_value(value))


def _serialize_emby_row(emby: Emby) -> dict:
    return {
        "tg": int(emby.tg),
        "embyid": emby.embyid,
        "name": emby.name,
        "pwd": encrypt_credential(emby.pwd),
        "pwd2": encrypt_credential(emby.pwd2),
        "lv": emby.lv,
        "cr": emby.cr.isoformat() if emby.cr else None,
        "ex": emby.ex.isoformat() if emby.ex else None,
        "us": int(emby.us or 0),
        "iv": int(emby.iv or 0),
        "ch": emby.ch.isoformat() if emby.ch else None,
    }


def _restore_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _deserialize_emby_row(payload: dict) -> Emby:
    normalized = dict(payload or {})
    for field in ("cr", "ex", "ch"):
        normalized[field] = _restore_datetime(normalized.get(field))
    for field in ("pwd", "pwd2"):
        normalized[field] = decrypt_credential(normalized.get(field))
    if normalized.get("tg") is not None:
        normalized["tg"] = int(normalized["tg"])
    for field in ("us", "iv"):
        if normalized.get(field) is not None:
            normalized[field] = int(normalized[field])
    return Emby(**normalized)


def _to_shanghai_date(value: datetime | None):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(SHANGHAI_TZ).date()


def _normalize_lookup_candidates(query) -> tuple[int | None, str | None]:
    numeric_tg = None
    text_value = None

    if isinstance(query, int) and not isinstance(query, bool):
        numeric_tg = int(query)
        text_value = str(query)
        return numeric_tg, text_value

    raw = str(query or "").strip()
    if not raw:
        return None, None

    text_value = raw
    if raw.lstrip("-").isdigit():
        try:
            numeric_tg = int(raw)
        except ValueError:
            numeric_tg = None

    return numeric_tg, text_value


def _lookup_aliases_from_payload(payload: dict | None) -> set[str]:
    aliases: set[str] = set()
    if not payload:
        return aliases

    for value in (payload.get("tg"), payload.get("name"), payload.get("embyid")):
        normalized = _normalize_lookup_value(value)
        if normalized:
            aliases.add(normalized)
    return aliases


def _cache_emby_payload(payload: dict, query=None) -> None:
    if not redis_cache.redis_enabled() or not payload:
        return

    tg = payload.get("tg")
    if tg is None:
        return

    redis_cache.set_json(_emby_record_cache_key(tg), payload, EMBY_CACHE_TTL)

    aliases = _lookup_aliases_from_payload(payload)
    normalized_query = _normalize_lookup_value(query)
    if normalized_query:
        aliases.add(normalized_query)

    for alias in aliases:
        redis_cache.set_json(_emby_lookup_cache_key(alias), {"hit": True, "tg": int(tg)}, EMBY_CACHE_TTL)


def _cache_emby_miss(query) -> None:
    normalized = _normalize_lookup_value(query)
    if not normalized or not redis_cache.redis_enabled():
        return
    redis_cache.set_json(_emby_lookup_cache_key(normalized), {"hit": False}, EMBY_CACHE_MISS_TTL)


def _invalidate_emby_payload(payload: dict | None) -> None:
    if not payload or not redis_cache.redis_enabled():
        return

    keys = []
    tg = payload.get("tg")
    if tg is not None:
        keys.append(_emby_record_cache_key(tg))
    keys.extend(_emby_lookup_cache_key(alias) for alias in _lookup_aliases_from_payload(payload))
    redis_cache.delete_keys(*keys)


def _invalidate_emby_namespace() -> None:
    if not redis_cache.redis_enabled():
        return
    redis_cache.delete_pattern(
        redis_cache.build_key("emby", "record", "*"),
        redis_cache.build_key("emby", "lookup", "*"),
    )


def _get_cached_emby(query):
    normalized = _normalize_lookup_value(query)
    if not normalized or not redis_cache.redis_enabled():
        return _CACHE_ABSENT

    lookup_key = _emby_lookup_cache_key(normalized)
    cached, lookup_payload = redis_cache.get_json(lookup_key)
    if not cached:
        return _CACHE_ABSENT

    if not isinstance(lookup_payload, dict):
        redis_cache.delete_keys(lookup_key)
        return _CACHE_ABSENT

    if lookup_payload.get("hit") is False:
        return None

    tg = lookup_payload.get("tg")
    if tg is None:
        redis_cache.delete_keys(lookup_key)
        return _CACHE_ABSENT

    record_key = _emby_record_cache_key(tg)
    record_cached, record_payload = redis_cache.get_json(record_key)
    if not record_cached or not isinstance(record_payload, dict):
        redis_cache.delete_keys(lookup_key, record_key)
        return _CACHE_ABSENT

    try:
        restored = _deserialize_emby_row(record_payload)
        # Rewrite legacy plaintext cache entries (and entries encrypted with an
        # older envelope) before returning the object.  Redis should never keep
        # a credential-bearing payload in the legacy format beyond one read.
        _cache_emby_payload(_serialize_emby_row(restored), query=query)
        return restored
    except (TypeError, ValueError, UnicodeError):
        # A cache written with a different key or malformed encoding must not
        # prevent the database path from serving the user.
        redis_cache.delete_keys(lookup_key, record_key)
        return _CACHE_ABSENT

def sql_add_emby(tg: int):
    """
    添加一条emby记录，如果tg已存在则忽略
    """
    with Session() as session:
        try:
            emby = Emby(tg=tg)
            session.add(emby)
            session.commit()
            _invalidate_emby_payload({"tg": tg})
        except:
            pass

def sql_delete_emby_by_tg(tg):
    """
    根据tg删除一条emby记录
    """
    with Session() as session:
        try:
            emby = session.query(Emby).filter(Emby.tg == tg).first()
            if emby:
                cached_payload = _serialize_emby_row(emby)
                session.delete(emby)
                session.commit()
                _invalidate_emby_payload(cached_payload)
                LOGGER.info(f"删除数据库记录成功 {tg}")
                return True
            else:
                LOGGER.info(f"数据库记录不存在 {tg}")
                return False
        except Exception as e:
            LOGGER.error(f"删除数据库记录时发生异常 {e}")
            session.rollback()
            return False

def sql_clear_emby_iv():
    """
    清除所有emby的iv
    """
    with Session() as session:
        try:
            session.query(Emby).update({Emby.iv: 0})
            session.commit()
            _invalidate_emby_namespace()
            return True
        except Exception as e:
            LOGGER.error(f"清除所有emby的iv时发生异常 {e}")
            return False

def sql_delete_emby(tg=None, embyid=None, name=None):
    """
    根据tg, embyid或name删除一条emby记录
    至少需要提供一个参数，如果所有参数都为None，则返回False
    """
    with Session() as session:
        try:
            # 构建条件列表，只包含非None的参数
            conditions = []
            if tg is not None:
                conditions.append(Emby.tg == tg)
            if embyid is not None:
                conditions.append(Emby.embyid == embyid)
            if name is not None:
                conditions.append(Emby.name == name)
            
            # 如果所有参数都为None，返回False
            if not conditions:
                LOGGER.warning("sql_delete_emby: 所有参数都为None，无法删除记录")
                return False
            
            # 使用or_组合所有条件
            condition = or_(*conditions)
            LOGGER.debug(f"删除数据库记录，条件: tg={tg}, embyid={embyid}, name={name}")
            
            # 用filter来过滤，使用with_for_update锁定记录
            emby = session.query(Emby).filter(condition).with_for_update().first()
            if emby:
                cached_payload = _serialize_emby_row(emby)
                LOGGER.info(f"删除数据库记录 {emby.name} - {emby.embyid} - {emby.tg}")
                session.delete(emby)
                try:
                    session.commit()
                    _invalidate_emby_payload(cached_payload)
                    LOGGER.info(f"成功删除数据库记录: tg={tg}, embyid={embyid}, name={name}")
                    return True
                except Exception as e:
                    LOGGER.error(f"删除数据库记录时提交事务失败 {e}")
                    session.rollback()
                    return False
            else:
                LOGGER.info(f"数据库记录不存在: tg={tg}, embyid={embyid}, name={name}")
                return False
        except Exception as e:
            LOGGER.error(f"删除数据库记录时发生异常 {e}")
            session.rollback()
            return False


def sql_update_embys(some_list: list, method=None):
    """ 根据list中的tg值批量更新一些值 ，此方法不可更新主键"""
    with Session() as session:
        tg_values = []
        cache_snapshots: list[dict] = []
        if some_list:
            try:
                tg_values = [int(item[0]) for item in some_list if item and item[0] is not None]
            except (TypeError, ValueError):
                tg_values = []

        if tg_values:
            rows = session.query(Emby).filter(Emby.tg.in_(tg_values)).all()
            cache_snapshots = [_serialize_emby_row(row) for row in rows]

        if method == 'iv':
            try:
                mappings = [{"tg": c[0], "iv": c[1]} for c in some_list]
                session.bulk_update_mappings(Emby, mappings)
                session.commit()
                for payload in cache_snapshots:
                    _invalidate_emby_payload(payload)
                return True
            except:
                session.rollback()
                return False
        if method == 'ex':
            try:
                mappings = [{"tg": c[0], "ex": c[1]} for c in some_list]
                session.bulk_update_mappings(Emby, mappings)
                session.commit()
                for payload in cache_snapshots:
                    _invalidate_emby_payload(payload)
                return True
            except:
                session.rollback()
                return False
        if method == 'bind':
            try:
                # mappings = [{"name": c[0], "embyid": c[1]} for c in some_list] 没有主键不能插入的这是emby表
                mappings = [{"tg": c[0], "name": c[1], "embyid": c[2]} for c in some_list]
                session.bulk_update_mappings(Emby, mappings)
                session.commit()
                for payload in cache_snapshots:
                    _invalidate_emby_payload(payload)
                for mapping in mappings:
                    _invalidate_emby_payload(mapping)
                return True
            except Exception as e:
                print(e)
                session.rollback()
                return False


def sql_get_emby(tg):
    """
    查询一条emby记录，可以根据tg, embyid或者name来查询
    """
    cached_emby = _get_cached_emby(tg)
    if cached_emby is not _CACHE_ABSENT:
        return cached_emby

    numeric_tg, text_value = _normalize_lookup_candidates(tg)
    if numeric_tg is None and not text_value:
        return None

    with Session() as session:
        try:
            filters = []
            if numeric_tg is not None:
                filters.append(Emby.tg == numeric_tg)
            if text_value:
                filters.append(Emby.name == text_value)
                filters.append(Emby.embyid == text_value)

            emby = session.query(Emby).filter(or_(*filters)).first()
            if emby is not None:
                _cache_emby_payload(_serialize_emby_row(emby), query=tg)
            else:
                _cache_emby_miss(tg)
            return emby
        except Exception as exc:
            LOGGER.error(f"查询Emby记录失败: query={tg!r}, error={exc}")
            return None


# def sql_get_emby_by_embyid(embyid):
#     """
#     Retrieve an Emby object from the database based on the provided Emby ID.
#
#     Parameters:
#         embyid : The Emby ID used to identify the Emby object.
#
#     Returns:
#         tuple: A tuple containing a boolean value indicating whether the retrieval was successful
#                and the retrieved Emby object. If the retrieval was unsuccessful, the boolean value
#                will be False and the Emby object will be None.
#     """
#     with Session() as session:
#         try:
#             emby = session.query(Emby).filter((Emby.embyid == embyid)).first()
#             return True, emby
#         except Exception as e:
#             return False, None


def get_all_emby(condition):
    """
    查询所有emby记录
    """
    with Session() as session:
        try:
            embies = session.query(Emby).filter(condition).all()
            return embies
        except:
            return None


def sql_adjust_emby_iv(tg: int | str, delta: int) -> int | None:
    """Atomically adjust a user's balance and return the resulting balance.

    A conditional SQL update prevents concurrent callers from overwriting one
    another or allowing a debit to make the balance negative.
    """
    try:
        numeric_tg = int(tg)
        amount = int(delta)
    except (TypeError, ValueError):
        return None

    with Session() as session:
        try:
            updated = (
                session.query(Emby)
                .filter(Emby.tg == numeric_tg)
                .filter(func.coalesce(Emby.iv, 0) + amount >= 0)
                .update(
                    {Emby.iv: func.coalesce(Emby.iv, 0) + amount},
                    synchronize_session=False,
                )
            )
            if updated != 1:
                session.rollback()
                return None
            session.commit()
            latest = session.query(Emby).filter(Emby.tg == numeric_tg).first()
            if latest is None:
                return None
            balance = int(latest.iv or 0)
            _invalidate_emby_payload({"tg": numeric_tg})
            _invalidate_emby_payload(_serialize_emby_row(latest))
            return balance
        except Exception as exc:
            session.rollback()
            LOGGER.error(f"原子调整 Emby 积分失败: tg={numeric_tg}, delta={amount}, error={exc}")
            return None


def sql_update_emby(condition, **kwargs):
    """
    更新一条emby记录，根据condition来匹配，然后更新其他的字段
    """
    with Session() as session:
        try:
            # 用filter来过滤，注意要加括号
            emby = session.query(Emby).filter(condition).first()
            if emby is None:
                return False
            before_payload = _serialize_emby_row(emby)
            # 然后用setattr方法来更新其他的字段，如果有就更新，如果没有就保持原样
            for k, v in kwargs.items():
                setattr(emby, k, v)
            session.commit()
            after_payload = _serialize_emby_row(emby)
            _invalidate_emby_payload(before_payload)
            _invalidate_emby_payload(after_payload)
            return True
        except Exception as e:
            LOGGER.error(e)
            return False


def sql_try_daily_checkin(tg: int | str, reward: int, checkin_at: datetime | None = None) -> dict:
    """
    Atomically settle a daily check-in to prevent concurrent repeated sign-ins.

    Returns a dict with:
    - ok: whether the DB operation itself succeeded
    - exists: whether the target user exists
    - checked_in: whether this call granted the reward
    - already_checked: whether the user had already checked in today
    - balance: latest balance after settlement / current balance if already checked in
    - checkin_at: latest stored check-in datetime
    """
    try:
        numeric_tg = int(tg)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "exists": False,
            "checked_in": False,
            "already_checked": False,
            "balance": 0,
            "reward": 0,
            "checkin_at": None,
        }

    raw_settled_at = checkin_at or datetime.now(SHANGHAI_TZ)
    if raw_settled_at.tzinfo is not None:
        settled_at = raw_settled_at.astimezone(SHANGHAI_TZ).replace(tzinfo=None)
    else:
        settled_at = raw_settled_at
    today = settled_at.date()
    day_start = settled_at.replace(hour=0, minute=0, second=0, microsecond=0)
    normalized_reward = max(int(reward or 0), 0)

    with Session() as session:
        try:
            updated = (
                session.query(Emby)
                .filter(Emby.tg == numeric_tg)
                .filter(or_(Emby.ch.is_(None), Emby.ch < day_start))
                .update(
                    {
                        Emby.iv: func.coalesce(Emby.iv, 0) + normalized_reward,
                        Emby.ch: settled_at,
                    },
                    synchronize_session=False,
                )
            )
            session.commit()
            latest = session.query(Emby).filter(Emby.tg == numeric_tg).first()
            _invalidate_emby_payload({"tg": numeric_tg})
            if latest is not None:
                _invalidate_emby_payload(_serialize_emby_row(latest))
            if latest is None:
                return {
                    "ok": True,
                    "exists": False,
                    "checked_in": False,
                    "already_checked": False,
                    "balance": 0,
                    "reward": 0,
                    "checkin_at": None,
                }
            if updated > 0:
                return {
                    "ok": True,
                    "exists": True,
                    "checked_in": True,
                    "already_checked": False,
                    "balance": int(latest.iv or 0),
                    "reward": normalized_reward,
                    "checkin_at": latest.ch,
                }
            last_checkin_date = _to_shanghai_date(latest.ch)
            return {
                "ok": True,
                "exists": True,
                "checked_in": False,
                "already_checked": bool(last_checkin_date is not None and last_checkin_date >= today),
                "balance": int(latest.iv or 0),
                "reward": 0,
                "checkin_at": latest.ch,
            }
        except Exception as exc:
            LOGGER.error(f"每日签到结算失败: tg={numeric_tg}, error={exc}")
            session.rollback()
            return {
                "ok": False,
                "exists": True,
                "checked_in": False,
                "already_checked": False,
                "balance": 0,
                "reward": 0,
                "checkin_at": None,
            }


def sql_invalidate_emby_cache(tg: int | str) -> bool:
    """
    Invalidate cached Emby payload for a specific Telegram user.

    Some call sites update Emby rows inside their own session/transaction and
    cannot reuse sql_update_emby(). This helper lets those paths explicitly
    clear stale cache entries after they commit.
    """
    numeric_tg, _ = _normalize_lookup_candidates(tg)
    if numeric_tg is None:
        return False

    latest_payload = None
    with Session() as session:
        try:
            emby = session.query(Emby).filter(Emby.tg == numeric_tg).first()
            if emby is not None:
                latest_payload = _serialize_emby_row(emby)
        except Exception as exc:
            LOGGER.warning(f"读取 Emby 缓存失效快照失败: tg={numeric_tg}, error={exc}")

    _invalidate_emby_payload({"tg": numeric_tg})
    if latest_payload is not None:
        _invalidate_emby_payload(latest_payload)
    return True


def sql_invalidate_emby_namespace() -> bool:
    _invalidate_emby_namespace()
    return True


#
# def sql_change_emby(name, new_tg):
#     with Session() as session:
#         try:
#             emby = session.query(Emby).filter_by(name=name).first()
#             if emby is None:
#                 return False
#             emby.tg = new_tg
#             session.commit()
#             return True
#         except Exception as e:
#             print(e)
#             return False


def sql_count_emby():
    """
    # 检索有tg和embyid的emby记录的数量，以及Emby.lv =='a'条件下的数量
    # count = sql_count_emby()
    :return: int, int, int
    """
    with Session() as session:
        try:
            # 使用func.count来计算数量，使用filter来过滤条件
            count = session.query(
                func.count(Emby.tg).label("tg_count"),
                func.count(Emby.embyid).label("embyid_count"),
                func.count(case((Emby.lv == "a", 1))).label("lv_a_count")
            ).first()
        except Exception as e:
            # print(e)
            return None, None, None
        else:
            return count.tg_count, count.embyid_count, count.lv_a_count
