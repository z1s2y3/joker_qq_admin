from __future__ import annotations

import asyncio
import hmac
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from config import QQBotConfig, env_file_path, load_env_file, read_env_file, write_env_file
from features.catalog import FEATURES
from storage import SQLiteStore
from webhook import generate_signature, verify_signature

logger = logging.getLogger(__name__)


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Joker QQ Admin</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, "Microsoft YaHei", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #171717; color: #ededed; }
    header { padding: 24px 28px 18px; border-bottom: 1px solid #343434; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    h1, h2, p { margin: 0; }
    h1 { font-size: 22px; font-weight: 650; }
    h2 { font-size: 16px; font-weight: 600; margin-bottom: 14px; }
    .muted { color: #9d9d9d; font-size: 13px; }
    .status { display: inline-flex; align-items: center; gap: 8px; color: #9dffb0; font-size: 13px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #51d56a; }
    nav { display: flex; gap: 8px; padding: 14px 28px; border-bottom: 1px solid #2d2d2d; overflow-x: auto; }
    nav button, button { border: 1px solid #444; background: #242424; color: #eee; border-radius: 6px; padding: 9px 13px; cursor: pointer; }
    nav button.active, button.primary { background: #e86d3f; border-color: #e86d3f; color: white; }
    button:hover { border-color: #e86d3f; }
    main { max-width: 1180px; margin: 0 auto; padding: 24px 28px 48px; }
    .view { display: none; }
    .view.active { display: block; }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 24px; }
    .metric, .panel { border: 1px solid #363636; background: #202020; border-radius: 7px; }
    .metric { padding: 16px; min-height: 96px; }
    .metric strong { display: block; margin-top: 10px; font-size: 24px; font-weight: 600; }
    .panel { padding: 18px; margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 11px 9px; border-bottom: 1px solid #343434; text-align: left; vertical-align: top; }
    th { color: #a9a9a9; font-weight: 500; }
    tr:last-child td { border-bottom: 0; }
    .tag { display: inline-block; padding: 4px 8px; border-radius: 999px; background: #2d4734; color: #9dffb0; font-size: 12px; }
    .tag.limited { background: #4d3e26; color: #ffd58b; }
    .tag.blocked { background: #472c2c; color: #ff9b9b; }
    .form { display: grid; grid-template-columns: 1.5fr 1fr auto auto; gap: 10px; align-items: end; }
    label { display: grid; gap: 6px; color: #aaa; font-size: 12px; }
    input, select, textarea { width: 100%; border: 1px solid #444; border-radius: 5px; background: #151515; color: #eee; padding: 9px 10px; font: inherit; }
    textarea { min-height: 80px; resize: vertical; }
    .reply-form { display: grid; grid-template-columns: 1fr 2fr auto; gap: 10px; align-items: end; }
    .empty { padding: 28px 0; color: #909090; text-align: center; }
    .notice { border-left: 3px solid #e86d3f; padding: 10px 12px; color: #cfcfcf; background: #2a2420; margin-bottom: 16px; font-size: 13px; }
    @media (max-width: 800px) { header { padding: 18px; } nav { padding: 12px 18px; } main { padding: 18px; } .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .form, .reply-form { grid-template-columns: 1fr; } table { display: block; overflow-x: auto; white-space: nowrap; } }
  </style>
</head>
<body>
  <header>
    <div><h1>Joker QQ Admin</h1><p class="muted">QQ 官方机器人控制台</p></div>
    <div class="status"><span class="dot" id="status-dot"></span><span id="status-text">连接检查中</span></div>
  </header>
  <nav>
    <button class="active" data-view="overview">总览</button>
    <button data-view="groups">群组</button>
    <button data-view="replies">自动回复</button>
    <button data-view="features">功能</button>
    <button data-view="settings">设置</button>
  </nav>
  <main>
    <section class="view active" id="overview">
      <div class="grid">
        <div class="metric"><span class="muted">Gateway</span><strong id="gateway-state">-</strong></div>
        <div class="metric"><span class="muted">已接收事件</span><strong id="event-count">0</strong></div>
        <div class="metric"><span class="muted">已处理回复</span><strong id="reply-count">0</strong></div>
        <div class="metric"><span class="muted">群组记录</span><strong id="group-count">0</strong></div>
      </div>
      <div class="panel"><h2>运行信息</h2><p class="muted" id="last-event">暂无事件</p><p class="muted" id="last-error" style="margin-top:8px"></p></div>
      <div class="notice">群消息需要在 QQ 开放平台开启对应事件权限，并将官方机器人加入测试群。页面显示在线只代表进程运行，Gateway 状态才代表接口已连接。</div>
    </section>
    <section class="view" id="groups">
      <div class="panel"><h2>群组数据</h2><div id="groups-table"></div></div>
    </section>
    <section class="view" id="replies">
      <div class="panel"><h2>选择群组</h2><label>群组 OpenID<select id="reply-scope"></select></label></div>
      <div class="panel"><h2>添加自动回复</h2><div class="reply-form"><label>关键词<input id="reply-trigger" placeholder="关键词"></label><label>回复内容<input id="reply-response" placeholder="回复内容"></label><button class="primary" id="save-reply">保存</button></div></div>
      <div class="panel"><h2>已有回复</h2><div id="replies-table"></div></div>
    </section>
    <section class="view" id="features"><div class="panel"><h2>功能目录</h2><div id="features-table"></div></div></section>
    <section class="view" id="settings">
      <div class="panel"><h2>运行配置</h2><p class="muted" style="margin-bottom:14px">保存后机器人会自动重载，敏感字段不会回显。</p><div class="form" style="grid-template-columns:1fr 1fr 1fr"><label>接收方式<select id="setting-transport"><option value="webhook">Webhook</option><option value="websocket">WebSocket</option></select></label><label>AppID<input id="setting-app-id"></label><label>AppSecret<input id="setting-app-secret" type="password" placeholder="留空保持不变"></label><label>SCUM 中转地址<input id="setting-scum-url"></label><label>SCUM Key<input id="setting-scum-key" type="password" placeholder="留空保持不变"></label><label>控制台监听地址<input id="setting-dashboard-bind"></label><label>控制台端口<input id="setting-dashboard-port" type="number" min="1" max="65535"></label><label>控制台访问令牌<input id="setting-dashboard-token" type="password" placeholder="留空保持不变"></label></div><button class="primary" id="save-settings" style="margin-top:16px">保存并重载</button><p class="muted" id="settings-result" style="margin-top:10px"></p></div>
    </section>
  </main>
  <script>
    const token = new URLSearchParams(location.search).get('token') || '';
    const headers = token ? {'X-Dashboard-Token': token} : {};
    let groups = [];
    const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const request = async (url, options = {}) => {
      const response = await fetch(url, {...options, headers: {...headers, ...(options.headers || {})}});
      if (!response.ok) throw new Error(await response.text() || `HTTP ${response.status}`);
      return response.json();
    };
    const renderGroups = () => {
      const target = document.getElementById('groups-table');
      if (!groups.length) { target.innerHTML = '<div class="empty">还没有收到群消息</div>'; return; }
      target.innerHTML = `<table><thead><tr><th>群 OpenID</th><th>数字群号</th><th>SCUM 服务器</th><th>消息数</th><th>自动回复</th><th>操作</th></tr></thead><tbody>${groups.map((g, i) => `<tr><td>${esc(g.scope_id)}</td><td>${esc(g.numeric_group_id || '-')}</td><td><input data-server="${i}" value="${esc(g.server_id)}" placeholder="服务器ID"></td><td>${g.message_count}</td><td><select data-auto="${i}"><option value="1" ${g.auto_reply_enabled ? 'selected' : ''}>开启</option><option value="0" ${g.auto_reply_enabled ? '' : 'selected'}>关闭</option></select></td><td><button data-save-group="${i}">保存</button></td></tr>`).join('')}</tbody></table>`;
      target.querySelectorAll('[data-save-group]').forEach(button => button.onclick = async () => {
        const i = Number(button.dataset.saveGroup); const server = target.querySelector(`[data-server="${i}"]`).value; const enabled = target.querySelector(`[data-auto="${i}"]`).value === '1';
        await request('/api/group-settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id: groups[i].scope_id, server_id: server, auto_reply_enabled: enabled})});
        await loadGroups();
      });
    };
    const loadGroups = async () => { groups = await request('/api/groups'); renderGroups(); const select = document.getElementById('reply-scope'); select.innerHTML = groups.map(g => `<option value="${esc(g.scope_id)}">${esc(g.numeric_group_id || g.scope_id)}</option>`).join(''); await loadReplies(); };
    const loadReplies = async () => { const scope = document.getElementById('reply-scope').value; const target = document.getElementById('replies-table'); if (!scope) { target.innerHTML = '<div class="empty">请先让机器人收到一条群消息</div>'; return; } const rows = await request('/api/replies?scope_id=' + encodeURIComponent(scope)); target.innerHTML = rows.length ? `<table><thead><tr><th>关键词</th><th>回复内容</th><th>操作</th></tr></thead><tbody>${rows.map((r, i) => `<tr><td>${esc(r.trigger)}</td><td>${esc(r.response)}</td><td><button data-delete-reply="${i}">删除</button></td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无自动回复</div>'; target.querySelectorAll('[data-delete-reply]').forEach(button => button.onclick = async () => { const row = rows[Number(button.dataset.deleteReply)]; await request('/api/replies/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id:scope, trigger:row.trigger})}); await loadReplies(); }); };
    const loadFeatures = async () => { const rows = await request('/api/features'); document.getElementById('features-table').innerHTML = `<table><thead><tr><th>功能</th><th>目录</th><th>状态</th><th>说明</th></tr></thead><tbody>${rows.map(f => `<tr><td>${esc(f.label)}</td><td>${esc(f.folder)}</td><td><span class="tag ${f.status}">${esc(f.status_label)}</span></td><td>${esc(f.note)}</td></tr>`).join('')}</tbody></table>`; };
    const loadSettings = async () => { const data = await request('/api/settings'); document.getElementById('setting-transport').value = data.transport || 'webhook'; document.getElementById('setting-app-id').value = data.app_id || ''; document.getElementById('setting-scum-url').value = data.scum_relay_url || ''; document.getElementById('setting-dashboard-bind').value = data.dashboard_bind || ''; document.getElementById('setting-dashboard-port').value = data.dashboard_port || 8080; };
    const loadStatus = async () => { const data = await request('/api/status'); document.getElementById('gateway-state').textContent = data.gateway_state; document.getElementById('event-count').textContent = data.event_count; document.getElementById('reply-count').textContent = data.reply_count; document.getElementById('group-count').textContent = data.group_count; document.getElementById('status-text').textContent = data.gateway_state === 'connected' ? '官方接口已连接' : data.gateway_state; document.getElementById('last-event').textContent = data.last_event ? `最近事件：${data.last_event} ${data.last_event_at || ''}` : '暂无事件'; document.getElementById('last-error').textContent = data.last_error ? `最近错误：${data.last_error}` : ''; };
    document.querySelectorAll('nav button').forEach(button => button.onclick = () => { document.querySelectorAll('nav button').forEach(item => item.classList.remove('active')); document.querySelectorAll('.view').forEach(item => item.classList.remove('active')); button.classList.add('active'); document.getElementById(button.dataset.view).classList.add('active'); });
    document.getElementById('reply-scope').onchange = loadReplies;
    document.getElementById('save-reply').onclick = async () => { const scope = document.getElementById('reply-scope').value; const trigger = document.getElementById('reply-trigger').value.trim(); const response = document.getElementById('reply-response').value.trim(); if (!scope || !trigger || !response) return; await request('/api/replies', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id:scope, trigger, response})}); document.getElementById('reply-trigger').value = ''; document.getElementById('reply-response').value = ''; await loadReplies(); await loadGroups(); };
    document.getElementById('save-settings').onclick = async () => { const result = document.getElementById('settings-result'); result.textContent = '保存中...'; const payload = {transport: document.getElementById('setting-transport').value, app_id: document.getElementById('setting-app-id').value.trim(), app_secret: document.getElementById('setting-app-secret').value, scum_relay_url: document.getElementById('setting-scum-url').value.trim(), scum_relay_key: document.getElementById('setting-scum-key').value, dashboard_bind: document.getElementById('setting-dashboard-bind').value.trim(), dashboard_port: Number(document.getElementById('setting-dashboard-port').value), dashboard_token: document.getElementById('setting-dashboard-token').value}; try { const data = await request('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}); result.textContent = '已保存，机器人正在重载。'; setTimeout(() => location.href = '/?token=' + encodeURIComponent(data.access_token || token), 1500); } catch (error) { result.textContent = error.message; } };
    const loadAll = async () => { try { await Promise.all([loadStatus(), loadGroups(), loadFeatures(), loadSettings()]); } catch (error) { document.getElementById('status-text').textContent = error.message; } };
    loadAll(); setInterval(loadStatus, 5000); setInterval(loadGroups, 10000);
  </script>
</body>
</html>"""


class DashboardServer:
    def __init__(
        self,
        config: QQBotConfig,
        store: SQLiteStore,
        status: dict[str, Any],
        on_event: Callable[[str, dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.config = config
        self.store = store
        self.status = status
        self.on_event = on_event
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.add_routes(
            [
                web.get("/", self._page),
                web.post("/", self._webhook),
                web.post("/qqbot", self._webhook),
                web.get("/healthz", self._health),
                web.get("/api/status", self._status),
                web.get("/api/features", self._features),
                web.get("/api/groups", self._groups),
                web.get("/api/replies", self._replies),
                web.get("/api/settings", self._settings),
                web.post("/api/replies", self._save_reply),
                web.post("/api/replies/delete", self._delete_reply),
                web.post("/api/group-settings", self._save_group_settings),
                web.post("/api/settings", self._save_settings),
            ]
        )
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.config.dashboard_bind, self.config.dashboard_port)
        await site.start()
        logger.info("dashboard listening on %s:%s", self.config.dashboard_bind, self.config.dashboard_port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    def _authorized(self, request: web.Request) -> bool:
        if not self.config.dashboard_token:
            return True
        supplied = request.headers.get("X-Dashboard-Token") or request.query.get("token", "")
        return hmac.compare_digest(supplied, self.config.dashboard_token)

    def _require_auth(self, request: web.Request) -> web.Response | None:
        if self._authorized(request):
            return None
        return web.json_response({"error": "dashboard authentication required"}, status=401)

    async def _page(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.Response(text="Dashboard authentication required", status=401)
        return web.Response(text=PAGE, content_type="text/html")

    async def _webhook(self, request: web.Request) -> web.Response:
        body = await request.read()
        if not verify_signature(self.config.app_secret, request.headers, body):
            return web.json_response({"error": "invalid webhook signature"}, status=401)
        try:
            payload = await request.json()
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid webhook payload"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"error": "invalid webhook payload"}, status=400)

        try:
            operation = int(payload.get("op", -1))
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid webhook operation"}, status=400)

        if operation == 13:
            data = payload.get("d")
            if not isinstance(data, dict):
                return web.json_response({"error": "invalid validation payload"}, status=400)
            plain_token = str(data.get("plain_token", ""))
            event_ts = str(data.get("event_ts", ""))
            if not plain_token or not event_ts:
                return web.json_response({"error": "invalid validation payload"}, status=400)
            return web.json_response(
                {
                    "plain_token": plain_token,
                    "signature": generate_signature(self.config.app_secret, event_ts, plain_token.encode("utf-8")),
                }
            )

        if operation == 1:
            return web.json_response({"op": 11, "d": payload.get("d")})

        if operation == 0:
            event_type = str(payload.get("t", ""))
            data = payload.get("d")
            if event_type and isinstance(data, dict):
                self.status["gateway_state"] = "webhook_connected"
                asyncio.create_task(self.on_event(event_type, data))
            return web.json_response({"op": 12, "d": 0})

        return web.json_response({"op": 12, "d": 0})

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def _status(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        return web.json_response(
            {
                **self.status,
                "group_count": len(self.store.list_scopes()),
                "data_dir": str(self.config.data_dir),
                "app_id": self.config.app_id,
            }
        )

    async def _features(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        status_labels = {"implemented": "已启用", "limited": "受限", "blocked": "不可用", "migrate": "迁移中", "infrastructure": "基础设施"}
        return web.json_response([{**asdict(item), "status_label": status_labels[item.status]} for item in FEATURES])

    async def _groups(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        return web.json_response(self.store.list_scopes())

    async def _settings(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        values = read_env_file()
        return web.json_response(
            {
                "app_id": values.get("QQBOT_APP_ID", self.config.app_id),
                "transport": values.get("QQBOT_TRANSPORT", self.config.transport),
                "scum_relay_url": values.get("SCUM_RELAY_URL", self.config.scum_relay_url),
                "dashboard_bind": values.get("JOKER_DASHBOARD_BIND", self.config.dashboard_bind),
                "dashboard_port": int(values.get("JOKER_DASHBOARD_PORT", str(self.config.dashboard_port))),
                "env_file": str(env_file_path()),
            }
        )

    async def _replies(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        return web.json_response(
            [{"trigger": trigger, "response": response, "enabled": enabled} for trigger, response, enabled in self.store.list_replies(scope_id)]
        )

    async def _save_reply(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        trigger = str(payload.get("trigger", "")).strip()
        response = str(payload.get("response", "")).strip()
        if not scope_id or not trigger or not response:
            return web.json_response({"error": "scope_id, trigger and response are required"}, status=400)
        self.store.save_reply(scope_id, trigger, response)
        return web.json_response({"ok": True})

    async def _delete_reply(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        trigger = str(payload.get("trigger", "")).strip()
        if not scope_id or not trigger:
            return web.json_response({"error": "scope_id and trigger are required"}, status=400)
        return web.json_response({"ok": self.store.delete_reply(scope_id, trigger)})

    async def _save_group_settings(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        server_id = str(payload.get("server_id", "")).strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        if server_id:
            self.store.bind_server(scope_id, server_id)
        else:
            self.store.unbind_server(scope_id)
        self.store.set_setting(scope_id, "auto_reply_enabled", "1" if payload.get("auto_reply_enabled") else "0")
        return web.json_response({"ok": True})

    async def _save_settings(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        current = read_env_file()
        app_id = str(payload.get("app_id", "")).strip()
        transport = str(payload.get("transport", "webhook")).strip().lower() or "webhook"
        bind = str(payload.get("dashboard_bind", "127.0.0.1")).strip() or "127.0.0.1"
        try:
            port = int(payload.get("dashboard_port", 8080))
        except (TypeError, ValueError):
            return web.json_response({"error": "控制台端口必须是数字"}, status=400)
        if not app_id:
            return web.json_response({"error": "AppID 不能为空"}, status=400)
        if transport not in {"websocket", "webhook"}:
            return web.json_response({"error": "接收方式必须是 Webhook 或 WebSocket"}, status=400)
        if not 1 <= port <= 65535:
            return web.json_response({"error": "控制台端口范围为 1-65535"}, status=400)
        app_secret = str(payload.get("app_secret", ""))
        dashboard_token = str(payload.get("dashboard_token", ""))
        existing_token = current.get("JOKER_DASHBOARD_TOKEN", "")
        if bind not in {"127.0.0.1", "localhost", "::1"} and not (dashboard_token or existing_token):
            return web.json_response({"error": "远程访问必须设置控制台访问令牌"}, status=400)
        updates = {
            "QQBOT_APP_ID": app_id,
            "QQBOT_TRANSPORT": transport,
            "SCUM_RELAY_URL": str(payload.get("scum_relay_url", "")).strip(),
            "JOKER_DASHBOARD_BIND": bind,
            "JOKER_DASHBOARD_PORT": str(port),
        }
        if app_secret:
            updates["QQBOT_APP_SECRET"] = app_secret
        if dashboard_token:
            updates["JOKER_DASHBOARD_TOKEN"] = dashboard_token
        scum_key = str(payload.get("scum_relay_key", ""))
        if scum_key:
            updates["SCUM_RELAY_KEY"] = scum_key
        try:
            target = write_env_file(updates)
        except OSError as exc:
            logger.exception("dashboard settings save failed")
            return web.json_response({"error": f"配置文件无法写入：{exc}"}, status=500)
        asyncio.create_task(self._restart_process(target))
        return web.json_response({"ok": True, "restarting": True, "access_token": dashboard_token or existing_token})

    @staticmethod
    async def _restart_process(env_path: Any) -> None:
        await asyncio.sleep(0.8)
        load_env_file(env_path)
        os.execv(sys.executable, [sys.executable, *sys.argv])

    @staticmethod
    async def _json(request: web.Request) -> dict[str, Any]:
        try:
            data = await request.json()
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}


def initial_status() -> dict[str, Any]:
    return {
        "gateway_state": "starting",
        "event_count": 0,
        "reply_count": 0,
        "last_event": "",
        "last_event_at": "",
        "last_error": "",
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
