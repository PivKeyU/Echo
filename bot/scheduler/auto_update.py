from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sys import argv, executable
from typing import Any

import aiohttp
from pyrogram.types import Message

from bot import LOGGER, auto_update, bot, group, save_config, schedall
from bot.func_helper.scheduler import scheduler


AUTO_UPDATE_JOB_ID = "auto_update_job"
_update_lock = asyncio.Lock()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHANGHAI_TZ = timezone(timedelta(hours=8))
GITHUB_REMOTE_RE = re.compile(
    r"(?:https://github\.com/|git@github\.com:)(?P<repo>[^/]+/[^/.]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def china_now() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def _iso_now() -> str:
    return china_now().isoformat()


def _short_sha(sha: str | None) -> str:
    return str(sha or "").strip()[:7] or "-"


def _normalize_commit_message(message: str | None) -> str:
    text = " ".join(str(message or "").strip().split())
    return text or "暂无更新说明"


def _parse_github_repo(raw: str | None) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    matched = GITHUB_REMOTE_RE.search(text)
    if matched:
        return matched.group("repo")
    if "/" in text and " " not in text:
        return text.removesuffix(".git").strip("/")
    return None


def _repo_from_origin() -> str | None:
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        LOGGER.debug(f"auto update git remote detect failed: {exc}")
        return None
    if result.returncode != 0:
        return None
    return _parse_github_repo(result.stdout)


def _normalize_git_repo() -> str:
    detected = _parse_github_repo(auto_update.git_repo)
    if detected and detected != "owner/echo":
        return detected
    return _repo_from_origin() or "PivKeyU/Echo"


def _normalize_docker_image() -> str:
    image = str(auto_update.docker_image or "").strip()
    return image or "echo/echo:latest"


def _normalize_container_name() -> str:
    container_name = str(auto_update.container_name or "").strip()
    if container_name:
        return container_name
    service = str(getattr(auto_update, "compose_service", "") or "").strip()
    return service or "echo"


def _normalize_compose_service() -> str:
    service = str(getattr(auto_update, "compose_service", "") or "").strip()
    if service:
        return service
    return _normalize_container_name()


def _normalize_interval() -> int:
    try:
        interval = int(auto_update.check_interval_minutes or 30)
    except (TypeError, ValueError):
        interval = 30
    return max(5, min(interval, 1440))


def _persist_normalized_auto_update() -> None:
    changed = False
    repo = _normalize_git_repo()
    image = _normalize_docker_image()
    container_name = _normalize_container_name()
    service = _normalize_compose_service()
    interval = _normalize_interval()
    if auto_update.git_repo != repo:
        auto_update.git_repo = repo
        changed = True
    if auto_update.docker_image != image:
        auto_update.docker_image = image
        changed = True
    if auto_update.container_name != container_name:
        auto_update.container_name = container_name
        changed = True
    if getattr(auto_update, "compose_service", None) != service:
        auto_update.compose_service = service
        changed = True
    if auto_update.check_interval_minutes != interval:
        auto_update.check_interval_minutes = interval
        changed = True
    if changed:
        save_config()


def serialize_auto_update_state() -> dict[str, Any]:
    _persist_normalized_auto_update()
    return {
        "status": bool(auto_update.status),
        "git_repo": _normalize_git_repo(),
        "docker_image": _normalize_docker_image(),
        "container_name": _normalize_container_name(),
        "compose_service": _normalize_compose_service(),
        "check_interval_minutes": _normalize_interval(),
        "commit_sha": auto_update.commit_sha,
        "image_digest": auto_update.image_digest,
        "last_remote_digest": auto_update.last_remote_digest,
        "last_checked_at": auto_update.last_checked_at,
        "last_remote_updated_at": auto_update.last_remote_updated_at,
        "last_status": auto_update.last_status,
        "last_error": auto_update.last_error,
        "up_description": auto_update.up_description,
        "job_enabled": bool(auto_update.status),
        "job_id": AUTO_UPDATE_JOB_ID,
    }


def update_auto_update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    if "status" in payload and payload["status"] is not None:
        auto_update.status = bool(payload["status"])
    if "git_repo" in payload and payload["git_repo"] is not None:
        auto_update.git_repo = str(payload["git_repo"]).strip()
    if "docker_image" in payload and payload["docker_image"] is not None:
        auto_update.docker_image = str(payload["docker_image"]).strip()
    if "container_name" in payload and payload["container_name"] is not None:
        auto_update.container_name = str(payload["container_name"]).strip()
    if "compose_service" in payload and payload["compose_service"] is not None:
        auto_update.compose_service = str(payload["compose_service"]).strip()
    if "check_interval_minutes" in payload and payload["check_interval_minutes"] is not None:
        try:
            auto_update.check_interval_minutes = int(payload["check_interval_minutes"])
        except (TypeError, ValueError):
            auto_update.check_interval_minutes = 30
    _persist_normalized_auto_update()
    auto_update.last_error = None
    ensure_auto_update_schedule()
    save_config()
    return serialize_auto_update_state()


async def _fetch_latest_commit(repo: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/commits?per_page=1"
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers={"Accept": "application/vnd.github+json"}) as response:
            if response.status != 200:
                raise RuntimeError(f"GitHub 仓库检查失败（HTTP {response.status}）")
            payload = await response.json()
    if not payload:
        raise RuntimeError("GitHub 仓库没有可用提交记录")
    item = payload[0]
    commit = item.get("commit") or {}
    author = commit.get("author") or {}
    return {
        "sha": item.get("sha"),
        "short_sha": _short_sha(item.get("sha")),
        "message": _normalize_commit_message(commit.get("message")),
        "date": author.get("date"),
        "url": item.get("html_url"),
    }


def _split_image_ref(image: str) -> tuple[str, str]:
    raw = str(image or "").strip()
    if not raw:
        return "echo/echo", "latest"
    name = raw
    tag = "latest"
    last_segment = raw.rsplit("/", 1)[-1]
    if ":" in last_segment:
        name, tag = raw.rsplit(":", 1)
    if "/" not in name:
        name = f"library/{name}"
    return name, tag


async def _fetch_remote_image(image: str) -> dict[str, Any]:
    repository, tag = _split_image_ref(image)
    namespace, repo_name = repository.split("/", 1)
    url = f"https://hub.docker.com/v2/repositories/{namespace}/{repo_name}/tags/{tag}"
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise RuntimeError(f"Docker 镜像检查失败（HTTP {response.status}）")
            payload = await response.json()
    images = payload.get("images") or []
    digest = ""
    if images:
        digest = str(images[0].get("digest") or "").strip()
    return {
        "repository": repository,
        "tag": tag,
        "digest": digest or None,
        "last_updated": payload.get("last_updated"),
        "raw_name": image,
    }


async def _run_command(*args: str, cwd: Path | None = None) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd or PROJECT_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return (
        process.returncode,
        stdout.decode("utf-8", errors="ignore").strip(),
        stderr.decode("utf-8", errors="ignore").strip(),
    )


async def _resolve_compose_command() -> list[str] | None:
    docker_bin = shutil.which("docker")
    if docker_bin:
        code, _, _ = await _run_command(docker_bin, "compose", "version")
        if code == 0:
            return [docker_bin, "compose"]
    docker_compose_bin = shutil.which("docker-compose")
    if docker_compose_bin:
        return [docker_compose_bin]
    return None


def _can_use_docker() -> bool:
    return bool(shutil.which("docker")) and Path("/var/run/docker.sock").exists()


def _format_update_notes(
    *,
    repo: str,
    image: str,
    latest_commit: dict[str, Any],
    image_info: dict[str, Any] | None,
    used_docker: bool,
    fallback_to_source: bool = False,
) -> str:
    lines = [
        "【自动更新说明】",
        f"仓库：{repo}",
        f"镜像：{image}",
        f"版本提交：{latest_commit.get('short_sha') or '-'}",
        f"中文更新注释：{latest_commit.get('message') or '暂无更新说明'}",
    ]
    if image_info and image_info.get("digest"):
        lines.append(f"镜像摘要：{image_info['digest']}")
    if used_docker:
        lines.append("更新方式：Docker 镜像拉取并重建服务")
    elif fallback_to_source:
        lines.append("更新方式：当前环境未满足 Docker 自更新条件，已回退为源码更新")
    else:
        lines.append("更新方式：源码拉取与依赖同步")
    return "\n".join(lines)


async def _prepare_restart_message(text: str, reply_message: Message | None = None) -> Message | None:
    if reply_message is not None:
        try:
            await reply_message.edit(text)
        except Exception:
            pass
        schedall.restart_chat_id = reply_message.chat.id
        schedall.restart_msg_id = reply_message.id
        save_config()
        return reply_message
    if not group:
        return None
    sent = await bot.send_message(chat_id=group[0], text=text)
    schedall.restart_chat_id = sent.chat.id
    schedall.restart_msg_id = sent.id
    save_config()
    return sent


def _restart_current_process() -> None:
    service_name = os.getenv("PIVKEYU_RESTART_SERVICE", "").strip()
    if service_name and os.path.exists("/bin/systemctl"):
        os.execl("/bin/systemctl", "systemctl", "restart", service_name)
    os.execl(executable, executable, *argv)


async def _apply_git_update() -> None:
    commands = [
        ("git", "fetch", "--all"),
        ("git", "pull", "--all"),
        (executable, "-m", "pip", "install", "-r", "requirements.txt"),
    ]
    for command in commands:
        code, stdout, stderr = await _run_command(*command)
        if code != 0:
            detail = stderr or stdout or "未知错误"
            raise RuntimeError(f"执行 {' '.join(command)} 失败：{detail}")


async def _apply_docker_update(image: str, service: str) -> None:
    docker_bin = shutil.which("docker")
    if not docker_bin:
        raise RuntimeError("当前环境缺少 docker 命令")
    compose_command = await _resolve_compose_command()
    if compose_command is None:
        raise RuntimeError("当前环境缺少 docker compose / docker-compose")
    code, stdout, stderr = await _run_command(docker_bin, "pull", image)
    if code != 0:
        detail = stderr or stdout or "未知错误"
        raise RuntimeError(f"Docker 拉取镜像失败：{detail}")
    compose_args = [*compose_command, "-f", str(PROJECT_ROOT / "docker-compose.yml"), "up", "-d", service]
    code, stdout, stderr = await _run_command(*compose_args)
    if code != 0:
        detail = stderr or stdout or "未知错误"
        raise RuntimeError(f"Docker 重建服务失败：{detail}")


def ensure_auto_update_schedule() -> None:
    _persist_normalized_auto_update()
    try:
        scheduler.remove_job(job_id=AUTO_UPDATE_JOB_ID, jobstore="default")
    except Exception:
        pass
    if not auto_update.status:
        return
    scheduler.add_job(
        _scheduled_auto_update_job,
        "interval",
        minutes=_normalize_interval(),
        id=AUTO_UPDATE_JOB_ID,
        replace_existing=True,
    )


async def _scheduled_auto_update_job() -> None:
    try:
        await run_auto_update(manual=False)
    except Exception as exc:
        LOGGER.error(f"scheduled auto update failed: {exc}")


async def run_auto_update(manual: bool = False, reply_message: Message | None = None, force: bool = False) -> dict[str, Any]:
    # 定时任务与手动 /update_bot 可能同时触发，加锁避免并发拉取/更新/重启
    if _update_lock.locked():
        if manual and reply_message is not None:
            try:
                await reply_message.edit("⏳ 已有自动更新任务正在运行，本次跳过。")
            except Exception:
                pass
        return {"updated": False, "skipped": True, "reason": "busy"}
    async with _update_lock:
        return await _run_auto_update_impl(manual=manual, reply_message=reply_message, force=force)


async def _run_auto_update_impl(manual: bool = False, reply_message: Message | None = None, force: bool = False) -> dict[str, Any]:
    try:
        _persist_normalized_auto_update()
        if not auto_update.status and not manual:
            return {"updated": False, "skipped": True, "reason": "disabled"}

        repo = _normalize_git_repo()
        image = _normalize_docker_image()
        auto_update.last_checked_at = _iso_now()
        latest_commit = await _fetch_latest_commit(repo)
        image_info = await _fetch_remote_image(image)
        remote_digest = image_info.get("digest")
        has_git_update = bool(force or latest_commit.get("sha") != auto_update.commit_sha)
        has_image_update = bool(remote_digest and remote_digest != auto_update.image_digest)

        auto_update.last_remote_digest = remote_digest
        auto_update.last_remote_updated_at = image_info.get("last_updated")

        if not has_git_update and not has_image_update:
            auto_update.last_status = "no_update"
            auto_update.last_error = None
            save_config()
            if manual and reply_message is not None:
                await reply_message.edit(
                    "✅ 未检测到新版本。\n"
                    f"当前提交：{_short_sha(auto_update.commit_sha)}\n"
                    f"最新提交：{latest_commit.get('short_sha')}\n"
                    f"最新中文注释：{latest_commit.get('message')}"
                )
            return {
                "updated": False,
                "latest_commit": latest_commit,
                "image_info": image_info,
            }

        use_docker = has_image_update and _can_use_docker()
        notes = _format_update_notes(
            repo=repo,
            image=image,
            latest_commit=latest_commit,
            image_info=image_info,
            used_docker=use_docker,
            fallback_to_source=has_image_update and not use_docker,
        )
        auto_update.up_description = notes
        auto_update.last_error = None

        if use_docker:
            pending_text = "🚀 检测到新的 Docker 镜像，正在拉取并重建服务。\n\n" + notes
            await _prepare_restart_message(pending_text, reply_message=reply_message)
            await _apply_docker_update(image, _normalize_compose_service())
            auto_update.commit_sha = latest_commit.get("sha")
            auto_update.image_digest = remote_digest
            auto_update.last_status = "updated_docker"
            save_config()
            os._exit(0)

        pending_text = "🚀 检测到新版本，正在执行源码更新并重启。\n\n" + notes
        await _prepare_restart_message(pending_text, reply_message=reply_message)
        await _apply_git_update()
        auto_update.commit_sha = latest_commit.get("sha")
        auto_update.last_status = "updated_source"
        save_config()
        _restart_current_process()
        return {
            "updated": True,
            "mode": "source",
            "latest_commit": latest_commit,
            "image_info": image_info,
            "notes": notes,
        }
    except Exception as exc:
        auto_update.last_status = "error"
        auto_update.last_error = str(exc)
        save_config()
        raise
