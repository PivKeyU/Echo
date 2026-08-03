from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, UniqueConstraint, and_, or_
from sqlalchemy.exc import IntegrityError

from bot.sql_helper import Base, Session


class PartitionCode(Base):
    __tablename__ = "partition_codes"

    code = Column(String(50), primary_key=True, autoincrement=False)
    partition = Column(String(64), nullable=False)
    duration_days = Column(Integer, nullable=False, default=1)
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class PartitionGrant(Base):
    __tablename__ = "partition_grants"
    # 同一用户同一分区至多一条授权，配合 Alembic 迁移 uq_partition_grants_tg_partition 保证并发下不重复
    __table_args__ = (
        UniqueConstraint("tg", "partition", name="uq_partition_grants_tg_partition"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=False, index=True)
    embyid = Column(String(255), nullable=True)
    embyname = Column(String(255), nullable=True)
    partition = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    status = Column(String(20), default="active", index=True)
    code = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

def sql_add_partition_codes(items: List[Dict]) -> bool:
    """批量插入分区码记录。items 需包含 code/partition/duration_days/created_by/expires_at(optional)。"""
    with Session() as session:
        try:
            rows = [PartitionCode(**item) for item in items]
            session.add_all(rows)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False


def sql_get_partition_code(code: str) -> Optional[PartitionCode]:
    with Session() as session:
        return session.query(PartitionCode).filter(PartitionCode.code == code).first()


def sql_delete_partition_code(code: str) -> bool:
    """使用后删除分区码，防止重复使用。"""
    with Session() as session:
        row = session.query(PartitionCode).filter(PartitionCode.code == code).first()
        if not row:
            return False
        try:
            session.delete(row)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False


def _refresh_grant(grant: PartitionGrant, *, expires_at: datetime, code: str, embyname: str, overwrite_code: bool = False) -> None:
    """刷新一条已存在授权：延长到期时间（取较大者）并恢复为 active。"""
    if expires_at > grant.expires_at:
        grant.expires_at = expires_at
    grant.status = "active"
    if overwrite_code or code:
        grant.code = code
    if embyname:
        grant.embyname = embyname
    grant.updated_at = datetime.now()


def sql_upsert_partition_grant(
    tg: int,
    embyid: str,
    partition: str,
    expires_at: datetime,
    code: str = None,
    embyname: str = None,
) -> bool:
    """插入或延长分区授权。若已有该用户同分区记录则延长到新的 expires_at (取较大者)。

    并发安全：优先走行锁更新；插入路径若撞上 (tg, partition) 唯一约束
    （另一事务抢先插入），回滚后重试一次转为更新路径，保证并发下不产生重复授权。
    """
    for attempt in range(2):
        with Session() as session:
            try:
                grant = (
                    session.query(PartitionGrant)
                    .filter(PartitionGrant.tg == tg, PartitionGrant.partition == partition)
                    .with_for_update()
                    .first()
                )
                if grant:
                    _refresh_grant(grant, expires_at=expires_at, code=code, embyname=embyname)
                else:
                    session.add(
                        PartitionGrant(
                            tg=tg,
                            embyid=embyid,
                            embyname=embyname,
                            partition=partition,
                            expires_at=expires_at,
                            status="active",
                            code=code,
                        )
                    )
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                if attempt >= 1:
                    return False
                continue
            except Exception:
                session.rollback()
                return False
    return False


def sql_get_active_grants_by_user(tg: int, now: datetime) -> List[PartitionGrant]:
    with Session() as session:
        return (
            session.query(PartitionGrant)
            .filter(
                PartitionGrant.tg == tg,
                PartitionGrant.status == "active",
                PartitionGrant.expires_at > now,
            )
            .all()
        )


def sql_get_active_grants_for_users(user_ids: List[int], now: datetime) -> Dict[int, List[PartitionGrant]]:
    if not user_ids:
        return {}
    with Session() as session:
        rows = (
            session.query(PartitionGrant)
            .filter(
                PartitionGrant.tg.in_(user_ids),
                PartitionGrant.status == "active",
                PartitionGrant.expires_at > now,
            )
            .all()
        )
    result: Dict[int, List[PartitionGrant]] = {}
    for row in rows:
        result.setdefault(row.tg, []).append(row)
    return result


def sql_get_expired_grants(now: datetime) -> List[PartitionGrant]:
    """查询已到期且尚未最终收回的授权：active 及上一轮进程崩溃遗留的 revoking。"""
    with Session() as session:
        return (
            session.query(PartitionGrant)
            .filter(
                PartitionGrant.status.in_(("active", "revoking")),
                PartitionGrant.expires_at <= now,
            )
            .all()
        )


# 崩溃后（claim 已提交但 mark/restore 未执行）遗留的 revoking 授权视为可重新领取。
# 阈值远大于单次收回流程耗时（Emby 请求超时 10s、单轮最多分钟级），
# 不会误抢仍在处理中的授权。
_CLAIM_STALE_AFTER = timedelta(hours=1)


def sql_claim_expired_grants(ids: List[int], now: datetime) -> List[int]:
    """领取已到期授权：把 status 从 active 置为 revoking，返回本次实际领取的 id 列表。

    并发安全：同一事务内先 SELECT ... FOR UPDATE 锁定候选行（按 id 排序保证多
    worker 加锁顺序一致、避免死锁），再条件 UPDATE。锁定读在等待其它事务提交后
    会按最新已提交数据重新过滤 WHERE（PostgreSQL EvalPlanQual / InnoDB 锁定读），
    已被其它 worker 领取（revoking）的行不会再次返回，保证每条授权同一时刻只有一个
    worker 处理。已过期且长期停留在 revoking（上一轮进程崩溃遗留）的行会被重新领取。
    """
    if not ids:
        return []
    stale_before = now - _CLAIM_STALE_AFTER
    with Session() as session:
        try:
            claimed = (
                session.query(PartitionGrant.id)
                .filter(
                    PartitionGrant.id.in_(ids),
                    PartitionGrant.expires_at <= now,
                    or_(
                        PartitionGrant.status == "active",
                        and_(
                            PartitionGrant.status == "revoking",
                            or_(
                                PartitionGrant.updated_at.is_(None),
                                PartitionGrant.updated_at <= stale_before,
                            ),
                        ),
                    ),
                )
                .order_by(PartitionGrant.id)
                .with_for_update()
                .all()
            )
            claimed_ids = [int(row[0]) for row in claimed]
            if not claimed_ids:
                return []
            session.query(PartitionGrant).filter(
                PartitionGrant.id.in_(claimed_ids)
            ).update(
                {PartitionGrant.status: "revoking", PartitionGrant.updated_at: datetime.now()},
                synchronize_session=False,
            )
            session.commit()
            return claimed_ids
        except Exception:
            session.rollback()
            return []


def sql_get_pending_grants(now: datetime) -> List[PartitionGrant]:
    """查询待激活的授权（分区码已兑换、Emby 媒体库尚未开通成功），供调度器自动重试。"""
    with Session() as session:
        return (
            session.query(PartitionGrant)
            .filter(
                PartitionGrant.status == "pending_activation",
                PartitionGrant.expires_at > now,
            )
            .all()
        )


def sql_clear_expired_pending_grants(now: datetime) -> int:
    """清理已过期且长期无法激活的 pending 授权，返回清理行数。

    激活一直失败且授权已到期的 pending 记录会永久滞留（无任何重试/回收路径），
    这里把它们标记为 expired，避免状态机死胡同与统计污染。
    """
    with Session() as session:
        try:
            updated = (
                session.query(PartitionGrant)
                .filter(
                    PartitionGrant.status == "pending_activation",
                    PartitionGrant.expires_at <= now,
                )
                .update(
                    {PartitionGrant.status: "expired", PartitionGrant.updated_at: datetime.now()},
                    synchronize_session=False,
                )
            )
            session.commit()
            return int(updated or 0)
        except Exception:
            session.rollback()
            return 0




def sql_restore_grants_active(ids: List[int]) -> bool:
    if not ids:
        return True
    with Session() as session:
        try:
            session.query(PartitionGrant).filter(
                PartitionGrant.id.in_(ids), PartitionGrant.status == "revoking"
            ).update(
                {PartitionGrant.status: "active", PartitionGrant.updated_at: datetime.now()},
                synchronize_session=False,
            )
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False


def sql_mark_grants_expired(ids: List[int]) -> None:
    if not ids:
        return
    with Session() as session:
        try:
            session.query(PartitionGrant).filter(
                PartitionGrant.id.in_(ids),
                PartitionGrant.status == "revoking",
            ).update(
                {PartitionGrant.status: "expired", PartitionGrant.updated_at: datetime.now()},
                synchronize_session=False,
            )
            session.commit()
        except Exception:
            session.rollback()

def sql_list_partition_codes(limit: int = 50, offset: int = 0) -> List[PartitionCode]:
    with Session() as session:
        return (
            session.query(PartitionCode)
            .order_by(PartitionCode.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )


def sql_list_partition_grants(limit: int = 50, offset: int = 0) -> List[PartitionGrant]:
    with Session() as session:
        return (
            session.query(PartitionGrant)
            .order_by(PartitionGrant.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )


def sql_count_partition_codes() -> int:
    with Session() as session:
        return session.query(PartitionCode).count()


def sql_count_partition_grants() -> int:
    with Session() as session:
        return session.query(PartitionGrant).count()


def sql_delete_partition_code_or_grant_by_code(code: str) -> Tuple[int, int]:
    with Session() as session:
        try:
            now = datetime.now()
            unused_deleted = session.query(PartitionCode).filter(PartitionCode.code == code).delete(synchronize_session=False)
            used_deleted = (
                session.query(PartitionGrant)
                .filter(
                    PartitionGrant.code == code,
                    ((PartitionGrant.status != "active") | (PartitionGrant.expires_at <= now)),
                )
                .delete(synchronize_session=False)
            )
            session.commit()
            return unused_deleted, used_deleted
        except Exception:
            session.rollback()
            return 0, 0


def sql_clear_unused_partition_codes() -> int:
    with Session() as session:
        try:
            count = session.query(PartitionCode).delete(synchronize_session=False)
            session.commit()
            return count
        except Exception:
            session.rollback()
            return 0


def sql_set_partition_grant_status(tg: int, partition: str, status: str) -> bool:
    """Transition a grant status after the Emby side effect succeeds/fails."""
    if status not in {"active", "pending_activation", "revoking", "expired"}:
        return False
    with Session() as session:
        try:
            updated = session.query(PartitionGrant).filter(
                PartitionGrant.tg == int(tg),
                PartitionGrant.partition == str(partition),
            ).update(
                {PartitionGrant.status: status, PartitionGrant.updated_at: datetime.now()},
                synchronize_session=False,
            )
            session.commit()
            return updated == 1
        except Exception:
            session.rollback()
            return False


def sql_clear_used_partition_grants() -> int:
    with Session() as session:
        try:
            now = datetime.now()
            count = (
                session.query(PartitionGrant)
                .filter((PartitionGrant.status != "active") | (PartitionGrant.expires_at <= now))
                .delete(synchronize_session=False)
            )
            session.commit()
            return count
        except Exception:
            session.rollback()
            return 0


def sql_clear_all_partition_data() -> int:
    """清空全部分区数据：同一事务内同时删除分区码与分区授权。返回删除的分区码数量以兼容调用方文案。"""
    with Session() as session:
        try:
            code_count = session.query(PartitionCode).delete(synchronize_session=False)
            session.query(PartitionGrant).delete(synchronize_session=False)
            session.commit()
            return code_count
        except Exception:
            session.rollback()
            return 0


def sql_redeem_partition_code_atomic(
    code: str,
    tg: int,
    embyid: str,
    now: datetime,
    embyname: str,
) -> Tuple[bool, Optional[str], Optional[datetime]]:
    """
    原子化兑换分区码：同一事务内完成 校验码->写入/延长授权->删除分区码。
    返回 (ok, partition, expires_at)。

    并发安全：同一分区码的并发兑换由分区码行锁串行化；不同分区码并发兑换同一
    (tg, partition) 时，插入路径可能撞上唯一约束，回滚后重试一次转为更新路径
    （延长授权），不会误报"码无效"。
    """
    for attempt in range(2):
        with Session() as session:
            try:
                record = (
                    session.query(PartitionCode)
                    .filter(PartitionCode.code == code)
                    .with_for_update()
                    .first()
                )
                if not record:
                    return False, None, None

                partition = record.partition
                grant = (
                    session.query(PartitionGrant)
                    .filter(PartitionGrant.tg == tg, PartitionGrant.partition == partition)
                    .with_for_update()
                    .first()
                )

                start_from = grant.expires_at if grant and grant.expires_at > now else now
                expires_at = start_from + timedelta(days=record.duration_days)

                if grant:
                    _refresh_grant(grant, expires_at=expires_at, code=code, embyname=embyname, overwrite_code=True)
                    grant.status = "pending_activation"
                else:
                    session.add(
                        PartitionGrant(
                            tg=tg,
                            embyid=embyid,
                            embyname=embyname,
                            partition=partition,
                            expires_at=expires_at,
                            status="pending_activation",
                            code=code,
                        )
                    )

                session.delete(record)
                session.commit()
                return True, partition, expires_at
            except IntegrityError:
                session.rollback()
                if attempt >= 1:
                    return False, None, None
                continue
            except Exception:
                session.rollback()
                return False, None, None
    return False, None, None
