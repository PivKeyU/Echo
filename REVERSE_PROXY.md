# 自动反代与 HTTPS

当前仓库已内置 `Caddy` 自动反代服务，定义在 `docker-compose.yml` 里的 `echo-caddy`。

## 作用

- 自动把 `80/443` 反代到 bot 的 `127.0.0.1:8838`
- 自动申请和续期 HTTPS 证书
- 提供 `/admin`、`/miniapp`、`/health` 的外网入口

## 前提

1. 一个已经解析到当前服务器公网 IP 的域名
2. 服务器放行 `80` 和 `443`
3. 服务器上没有其它程序占用 `80` 或 `443`

## 使用方法

1. 复制 `.env.example` 为 `.env`
2. 修改 `.env`

```dotenv
PIVKEYU_PUBLIC_DOMAIN=bot.example.com
PIVKEYU_UPSTREAM=127.0.0.1:8838
```

3. 修改 `data/config.json`

```json
"api": {
  "status": true,
  "http_url": "0.0.0.0",
  "http_port": 8838,
  "public_url": "https://bot.example.com",
  "miniapp_title": "片刻面板",
  "admin_token": "replace-with-your-own-token",
  "webapp_auth_max_age": 86400,
  "allow_origins": ["*"]
}
```

4. 启动

```bash
docker compose up -d
```

## 相关文件

- `caddy/Caddyfile`
- `caddy/data`
- `caddy/config`

## 验证

```bash
curl http://127.0.0.1:8838/health
curl -I http://你的域名
curl -I https://你的域名
```

浏览器打开：

- `https://你的域名/admin`
- `https://你的域名/miniapp`
