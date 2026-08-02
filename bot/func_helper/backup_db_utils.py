import asyncio
import os
from datetime import datetime
from pathlib import Path

from bot import LOGGER


class BackupDBUtils:
    @staticmethod
    def _ensure_backup_dir(backup_dir: str) -> Path:
        target = Path(backup_dir).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _safe_name(value: str) -> str:
        normalized = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(value or ""))
        return normalized.strip("._") or "database"

    @staticmethod
    def _backup_path(backup_dir: str, database_name: str, suffix: str) -> Path:
        root = BackupDBUtils._ensure_backup_dir(backup_dir)
        safe_database_name = BackupDBUtils._safe_name(database_name)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S-%f")
        return root / f"{safe_database_name}-{timestamp}.{suffix}"

    @staticmethod
    def _rotate_backups(backup_dir: str, database_name: str, suffix: str, max_backup_count: int) -> None:
        root = BackupDBUtils._ensure_backup_dir(backup_dir)
        prefix = f"{BackupDBUtils._safe_name(database_name)}-"
        expected_suffix = f".{suffix.lstrip('.')}"
        all_backups = sorted(
            item
            for item in root.iterdir()
            if item.is_file() and item.name.startswith(prefix) and item.name.endswith(expected_suffix)
        )
        # Always retain the backup just created; a zero/invalid retention value
        # must not turn a successful backup into a missing file for the caller.
        keep_count = max(int(max_backup_count or 1), 1)
        while len(all_backups) > keep_count:
            all_backups.pop(0).unlink(missing_ok=True)

    @staticmethod
    async def _run_dump(*args: str, output_path: Path, env: dict[str, str] | None = None) -> tuple[int, str]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output_path.open("wb") as output_file:
                process = await asyncio.create_subprocess_exec(
                    *args,
                    env=env,
                    stdout=output_file,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await process.communicate()
        except Exception:
            output_path.unlink(missing_ok=True)
            raise

        return_code = int(process.returncode or 0)
        error_text = (stderr or b"").decode("utf-8", errors="replace").strip()
        if return_code != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
            output_path.unlink(missing_ok=True)
            return return_code or 1, error_text or "备份命令未生成有效文件"
        return 0, error_text

    @staticmethod
    def _log_failure(return_code: int, error_text: str) -> None:
        detail = f": {error_text}" if error_text else ""
        LOGGER.error(f"BOT数据库备份失败, error code: {return_code}{detail}")

    @staticmethod
    async def backup_mysql_db(host, port, user, password, database_name, backup_dir, max_backup_count):
        backup_file = BackupDBUtils._backup_path(backup_dir, database_name, "sql")
        env = dict(os.environ)
        env["MYSQL_PWD"] = str(password)
        base_args = (
            "mysqldump",
            "-h",
            str(host),
            "-P",
            str(port),
            "-u",
            str(user),
            "--no-tablespaces",
        )
        try:
            return_code, error_text = await BackupDBUtils._run_dump(
                *base_args,
                str(database_name),
                output_path=backup_file,
                env=env,
            )
            if return_code != 0:
                LOGGER.warning("BOT数据库备份失败，使用 skip-ssl 方式尝试备份")
                return_code, error_text = await BackupDBUtils._run_dump(
                    *base_args,
                    "--skip-ssl",
                    str(database_name),
                    output_path=backup_file,
                    env=env,
                )
            if return_code != 0:
                BackupDBUtils._log_failure(return_code, error_text)
                return None
        except Exception as exc:
            LOGGER.error(f"BOT数据库备份失败, error: {exc}")
            return None

        LOGGER.info(f"BOT数据库备份成功,文件保存为 {backup_file}")
        BackupDBUtils._rotate_backups(backup_dir, database_name, "sql", max_backup_count)
        return str(backup_file)

    @staticmethod
    async def backup_mysql_db_docker(container_name, user, password, database_name, backup_dir, max_backup_count):
        backup_file = BackupDBUtils._backup_path(backup_dir, database_name, "sql")
        env = dict(os.environ)
        env["MYSQL_PWD"] = str(password)
        base_args = (
            "docker",
            "exec",
            "-e",
            "MYSQL_PWD",
            str(container_name),
            "mysqldump",
            "--no-tablespaces",
            "-u",
            str(user),
        )
        try:
            return_code, error_text = await BackupDBUtils._run_dump(
                *base_args,
                str(database_name),
                output_path=backup_file,
                env=env,
            )
            if return_code != 0:
                LOGGER.warning("BOT数据库备份失败，使用 skip-ssl 方式尝试备份")
                return_code, error_text = await BackupDBUtils._run_dump(
                    *base_args,
                    "--skip-ssl",
                    str(database_name),
                    output_path=backup_file,
                    env=env,
                )
            if return_code != 0:
                BackupDBUtils._log_failure(return_code, error_text)
                return None
        except Exception as exc:
            LOGGER.error(f"BOT数据库备份失败, error: {exc}")
            return None

        LOGGER.info(f"BOT数据库备份成功,文件保存为 {backup_file}")
        BackupDBUtils._rotate_backups(backup_dir, database_name, "sql", max_backup_count)
        return str(backup_file)

    @staticmethod
    async def backup_postgres_db(host, port, user, password, database_name, backup_dir, max_backup_count):
        backup_file = BackupDBUtils._backup_path(backup_dir, database_name, "dump")
        env = dict(os.environ)
        env["PGPASSWORD"] = str(password)
        try:
            return_code, error_text = await BackupDBUtils._run_dump(
                "pg_dump",
                "-h",
                str(host),
                "-p",
                str(port),
                "-U",
                str(user),
                "-d",
                str(database_name),
                "-F",
                "c",
                output_path=backup_file,
                env=env,
            )
            if return_code != 0:
                BackupDBUtils._log_failure(return_code, error_text)
                return None
        except Exception as exc:
            LOGGER.error(f"BOT数据库备份失败, error: {exc}")
            return None

        LOGGER.info(f"BOT数据库备份成功,文件保存为 {backup_file}")
        BackupDBUtils._rotate_backups(backup_dir, database_name, "dump", max_backup_count)
        return str(backup_file)

    @staticmethod
    async def backup_postgres_db_docker(container_name, user, password, database_name, backup_dir, max_backup_count):
        backup_file = BackupDBUtils._backup_path(backup_dir, database_name, "dump")
        env = dict(os.environ)
        env["PGPASSWORD"] = str(password)
        try:
            return_code, error_text = await BackupDBUtils._run_dump(
                "docker",
                "exec",
                "-e",
                "PGPASSWORD",
                str(container_name),
                "pg_dump",
                "-U",
                str(user),
                "-d",
                str(database_name),
                "-F",
                "c",
                output_path=backup_file,
                env=env,
            )
            if return_code != 0:
                BackupDBUtils._log_failure(return_code, error_text)
                return None
        except Exception as exc:
            LOGGER.error(f"BOT数据库备份失败, error: {exc}")
            return None

        LOGGER.info(f"BOT数据库备份成功,文件保存为 {backup_file}")
        BackupDBUtils._rotate_backups(backup_dir, database_name, "dump", max_backup_count)
        return str(backup_file)
