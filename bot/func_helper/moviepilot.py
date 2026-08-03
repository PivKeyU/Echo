import asyncio

import aiohttp

from bot import LOGGER, moviepilot, save_config


# 添加配置类
class MoviePilot:
    def __init__(self):
        self.url = moviepilot.url
        self.username = moviepilot.username
        self.password = moviepilot.password
        self.access_token = moviepilot.access_token or ''


mp = MoviePilot()

TIMEOUT = 30

# 应用生命周期内复用的 ClientSession（惰性创建，shutdown 时调用 close_moviepilot_session 关闭）
_session: aiohttp.ClientSession | None = None
_session_lock = asyncio.Lock()

# 登录 single-flight：并发请求共享同一次登录，避免 401/403 时并发重复登录
_login_future = None


async def _get_session():
    """惰性创建并在应用生命周期内复用的 ClientSession。"""
    global _session
    async with _session_lock:
        if _session is None or _session.closed:
            timeout = aiohttp.ClientTimeout(total=TIMEOUT, connect=10)
            connector = aiohttp.TCPConnector(
                limit=10,
                limit_per_host=4,
                keepalive_timeout=30,
                enable_cleanup_closed=True,
                ttl_dns_cache=300,
            )
            _session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return _session


async def close_moviepilot_session():
    """关闭复用的 MoviePilot ClientSession。

    应用 shutdown 时调用（与 emby.shutdown() 同理），可安全重复调用；
    调用后再次发起请求会自动重建新会话。
    """
    global _session
    async with _session_lock:
        session = _session
        _session = None
    if session is not None and not session.closed:
        await session.close()
        LOGGER.info("MoviePilot 会话已关闭")


async def login():
    """登录 MoviePilot 并保存 token。

    single-flight：同一时刻只发起一次真实登录，并发调用方共享同一次登录结果。
    Returns:
        bool: 是否登录成功
    """
    global _login_future
    if _login_future is not None:
        return await _login_future
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    _login_future = future
    try:
        ok = await _do_login()
        if not future.done():
            future.set_result(ok)
        return ok
    except asyncio.CancelledError:
        # 领导方被取消（如应用关停）时，等待方共享同一 future 会永久挂起；
        # 先以失败结果唤醒所有等待方，再继续传播取消。
        if not future.done():
            future.set_result(False)
        raise
    except Exception as e:
        LOGGER.error(f"MP 登录异常: {str(e)}")
        if not future.done():
            future.set_result(False)
        return False
    finally:
        if _login_future is future:
            _login_future = None


async def _do_login():
    url = f"{mp.url}/api/v1/login/access-token"
    headers = {'accept': 'application/json'}
    session = await _get_session()
    try:
        # data 传 dict，aiohttp 会以 application/x-www-form-urlencoded 安全编码
        async with session.post(
            url,
            data={'username': mp.username, 'password': mp.password},
            headers=headers,
        ) as response:
            if response.status != 200:
                LOGGER.error(f"MP 登录请求失败: HTTP {response.status}")
                return False
            content_type = response.headers.get('Content-Type', '')
            if 'json' not in content_type.lower():
                LOGGER.error(f"MP 登录响应不是 JSON (Content-Type: {content_type})")
                return False
            try:
                result = await response.json(content_type=None)
            except (aiohttp.ClientError, ValueError, asyncio.TimeoutError) as e:
                LOGGER.error(f"MP 登录响应 JSON 解析失败: {e}")
                return False
            if not isinstance(result, dict) or not result.get('access_token'):
                LOGGER.error(f"MP 登录失败: {result}")
                return False
            token_type = result.get('token_type') or 'bearer'
            mp.access_token = f"{token_type} {result['access_token']}"
            moviepilot.access_token = mp.access_token
            save_config()
            LOGGER.info("MP 登录成功, token已保存")
            return True
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        LOGGER.error(f"MP 登录异常: {str(e)}")
        return False


async def _do_request(request, _refreshed=False):
    """执行 MoviePilot API 请求。

    - 401/403: 最多刷新一次 token 并重试一次（_refreshed=True 后不再刷新）
    - 429/5xx/非 JSON/HTML 响应: 明确失败并返回 None，绝不向上抛出异常
    - 参数安全编码: GET 用 params、JSON 用 json=、form 用 dict data，由 aiohttp 统一编码
    """
    session = await _get_session()
    method = request['method']
    url = request['url']
    headers = dict(request.get('headers') or {})
    if mp.access_token:
        # 始终使用当前 token，刷新后重试能自动带上新 token
        headers['Authorization'] = mp.access_token
    kwargs = {'headers': headers}
    if request.get('json') is not None:
        kwargs['json'] = request['json']
    elif request.get('data') is not None:
        kwargs['data'] = request['data']
    if request.get('params'):
        kwargs['params'] = request['params']
    try:
        async with session.request(method, url, **kwargs) as response:
            if response.status in (401, 403):
                if _refreshed:
                    LOGGER.error(f"MP 刷新token后仍返回 HTTP {response.status}: {url}")
                    return None
                LOGGER.warning("MP Token过期, 尝试重新登录.")
                if not await login():
                    return None
                return await _do_request(request, _refreshed=True)
            if response.status == 429:
                LOGGER.warning(f"MP 请求被限流(HTTP 429): {url}")
                return None
            if response.status >= 500:
                LOGGER.error(f"MP 服务端错误(HTTP {response.status}): {url}")
                return None
            if response.status >= 400:
                LOGGER.error(f"MP 请求失败(HTTP {response.status}): {url}")
                return None
            content_type = response.headers.get('Content-Type', '')
            if 'json' not in content_type.lower():
                LOGGER.error(f"MP 响应不是 JSON (HTTP {response.status}, Content-Type: {content_type}): {url}")
                return None
            try:
                return await response.json(content_type=None)
            except (aiohttp.ClientError, ValueError, asyncio.TimeoutError) as e:
                LOGGER.error(f"MP 响应 JSON 解析失败: {e}")
                return None
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        LOGGER.error(f"MP 请求异常: {e}")
        return None


async def search(title):
    """搜索资源

    Args:
        title: 搜索关键词
    Returns:
        (success, results)
        success: bool 是否成功
        results: list 搜索结果列表
    """
    if title is None:
        return False, []

    url = f"{mp.url}/api/v1/search/title"
    request = {
        'method': 'GET',
        'url': url,
        'headers': {'accept': 'application/json'},
        'params': {'keyword': title},  # 由 aiohttp 安全编码
    }
    try:
        data = await _do_request(request)
        if not isinstance(data, dict) or not data.get("success", False):
            LOGGER.error(f"MP 搜索失败: {data}")
            return False, []
        results = []
        for item in (data.get("data") or []):
            if not isinstance(item, dict):
                continue
            meta_info = item.get("meta_info") or {}
            torrent_info = item.get("torrent_info") or {}

            seeders = torrent_info.get("seeders", "0")
            try:
                seeders = int(seeders) if seeders else 0
            except (ValueError, TypeError):
                seeders = 0
            result = {
                "title": meta_info.get("title", ""),
                "year": meta_info.get("year", ""),
                "type": meta_info.get("type", ""),
                "resource_pix": meta_info.get("resource_pix", ""),
                "video_encode": meta_info.get("video_encode", ""),
                "audio_encode": meta_info.get("audio_encode", ""),
                "resource_team": meta_info.get("resource_team", ""),
                "seeders": seeders,
                "size": torrent_info.get("size", "0"),
                "labels": torrent_info.get("labels", ""),
                "description": torrent_info.get("description", ""),
                "torrent_info": torrent_info,
            }
            results.append(result)

        # 只按做种数排序,移除数量限制
        results.sort(key=lambda x: x["seeders"], reverse=True)

        LOGGER.info("MP Search successful!")
        return True, results
    except Exception as e:
        LOGGER.error(f"MP Search failed: {str(e)}")
        return False, []


async def add_download_task(param):
    """添加下载任务

    Args:
        param: 下载参数 dict
    Returns:
        (success, download_id)
        success: bool 是否成功
        download_id: str 下载ID，失败为 None
    """
    if param is None:
        return False, None
    url = f"{mp.url}/api/v1/download/add"
    request = {
        'method': 'POST',
        'url': url,
        'headers': {'accept': 'application/json'},
        'json': param,  # 由 aiohttp 安全序列化并设置 Content-Type
    }
    try:
        result = await _do_request(request)
        if not isinstance(result, dict) or not result.get("success", False):
            LOGGER.error(f"MP 添加下载任务失败: {result}")
            return False, None
        data = result.get("data")
        if not isinstance(data, dict):
            LOGGER.error(f"MP 添加下载任务响应缺少 data: {result}")
            return False, None
        download_id = data.get("download_id")
        if not download_id:
            LOGGER.error(f"MP 添加下载任务响应缺少 download_id: {result}")
            return False, None
        LOGGER.info(f"MP 添加下载任务成功, ID: {download_id}")
        return True, download_id
    except Exception as e:
        LOGGER.error(f"MP 添加下载任务失败: {e}")
        return False, None


async def get_download_task():
    """获取下载任务列表

    Returns:
        list[dict] | None: 下载任务列表；请求失败返回 None
        每个任务: {'download_id', 'state', 'progress', 'left_time'}
    """
    url = f"{mp.url}/api/v1/download"
    request = {
        'method': 'GET',
        'url': url,
        'headers': {'accept': 'application/json'},
        'params': {'name': '下载'},
    }
    try:
        result = await _do_request(request)
        if not isinstance(result, list):
            LOGGER.error(f"MP 获取下载任务响应格式异常: {result}")
            return None
        data = []
        for item in result:
            if not isinstance(item, dict):
                continue
            data.append({
                'download_id': item.get('hash'),
                'state': item.get('state'),
                'progress': item.get('progress'),
                'left_time': item.get('left_time'),
            })
        return data
    except Exception as e:
        LOGGER.error(f"MP 获取下载任务失败: {e}")
        return None


async def get_history_transfer_task_by_title_download_id(title, download_id, page=1, count=50):
    """查询历史转移任务状态

    Returns:
        str | None: 转移状态（如 'success'/'failed'）；未查到或请求失败返回 None
    """
    url = f"{mp.url}/api/v1/history/transfer"
    request = {
        'method': 'GET',
        'url': url,
        'headers': {'accept': 'application/json'},
        'params': {'title': title or '', 'page': page, 'count': count},
    }
    try:
        result = await _do_request(request)
        if not isinstance(result, dict) or not result.get("success", False):
            LOGGER.error(f"MP 获取历史转移任务失败: {result}")
            return None
        data = result.get("data")
        if not isinstance(data, dict):
            LOGGER.error(f"MP 获取历史转移任务响应缺少 data: {result}")
            return None
        for item in (data.get("list") or []):
            if not isinstance(item, dict):
                continue
            if item.get('download_hash') == download_id:
                return item.get('status')
        return None
    except Exception as e:
        LOGGER.error(f"MP 获取历史转移任务失败: {e}")
        return None
