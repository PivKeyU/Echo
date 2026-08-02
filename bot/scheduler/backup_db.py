import os

import asyncio

from bot import bot, owner, LOGGER, config, db_backend, db_is_docker, db_docker_name, db_host, db_name, db_user, db_pwd, \
    db_backup_dir, db_backup_maxcount, db_port
from bot.func_helper.backup_db_utils import BackupDBUtils


class DbBackupUtils:
    # 数据库的相关配置
    host = db_host
    user = db_user
    port = db_port
    password = db_pwd
    database_name = db_name
    backup_dir = db_backup_dir
    max_backup_count = db_backup_maxcount
    docker_mode = os.environ.get('DOCKER_MODE') == "1"
    docker_name = db_docker_name
    _backup_lock = asyncio.Lock()

    @classmethod
    async def _backup_db_unlocked(cls):
        backup_file = None
        backend = str(db_backend or "postgresql").strip().lower()
        use_local_client = os.environ.get('DOCKER_MODE') == "1" or not db_is_docker

        if backend in {"postgres", "postgresql", "pgsql"}:
            if use_local_client:
                backup_file = await BackupDBUtils.backup_postgres_db(
                    host=db_host,
                    port=db_port,
                    user=db_user,
                    password=db_pwd,
                    database_name=db_name,
                    backup_dir=db_backup_dir,
                    max_backup_count=db_backup_maxcount
                )
            else:
                backup_file = await BackupDBUtils.backup_postgres_db_docker(
                    container_name=db_docker_name,
                    user=db_user,
                    password=db_pwd,
                    database_name=db_name,
                    backup_dir=db_backup_dir,
                    max_backup_count=db_backup_maxcount
                )
        else:
            if use_local_client:
                backup_file = await BackupDBUtils.backup_mysql_db(
                    host=db_host,
                    port=db_port,
                    user=db_user,
                    password=db_pwd,
                    database_name=db_name,
                    backup_dir=db_backup_dir,
                    max_backup_count=db_backup_maxcount
                )
            else:
                backup_file = await BackupDBUtils.backup_mysql_db_docker(
                    container_name=db_docker_name,
                    user=db_user,
                    password=db_pwd,
                    database_name=db_name,
                    backup_dir=db_backup_dir,
                    max_backup_count=db_backup_maxcount
                )
        return backup_file

    @classmethod
    async def backup_db(cls):
        if cls._backup_lock.locked():
            LOGGER.warning("BOT数据库上一轮备份尚未完成，跳过重复备份请求")
            return None
        async with cls._backup_lock:
            return await cls._backup_db_unlocked()

    @staticmethod
    async def auto_backup_db():
        LOGGER.info("BOT数据库备份开始")
        backup_file = await DbBackupUtils.backup_db()
        if backup_file is not None:
            LOGGER.info(f'BOT数据库备份完毕')
            try:
                await asyncio.gather(bot.send_document(
                    chat_id=owner,
                    document=backup_file,
                    caption=f'BOT数据库备份完毕',
                    disable_notification=True  # 勿打扰
                ), bot.send_document(
                    chat_id=owner,
                    document=str(config.resolve_config_path()),
                    caption=f'config备份完毕',
                    disable_notification=True  # 勿打扰
                ))
            except Exception as e:
                LOGGER.info(f'发送到owner失败，文件保存在本地:{e}')
        else:
            LOGGER.error(f'BOT数据库手动备份失败，请尽快检查相关配置')
