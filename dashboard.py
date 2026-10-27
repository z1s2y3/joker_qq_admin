from __future__ import annotations

import asyncio
from email.message import EmailMessage
import hmac
import logging
import os
import smtplib
import ssl
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from api import QQBotAPI, QQBotAPIError
from config import QQBotConfig, env_file_path, load_env_file, read_env_file, write_env_file
from dashboard_overlays import ADMIN_UI_OVERLAY, AUTH_UI_OVERLAY, FUNCTION_USAGE_OVERLAY, GROUP_UI_OVERLAY
from features.catalog import FEATURES
from storage import SQLiteStore
from webhook import generate_signature, verify_signature

logger = logging.getLogger(__name__)


_ADMIN_UI_ENHANCEMENT = r"""
<style id="joker-admin-ui-enhancement">
  .ui-workbench { margin-top: 16px; border: 1px solid #2e4d49; background: linear-gradient(135deg, rgba(20, 97, 90, .18), rgba(24, 29, 37, .72)); border-radius: 14px; padding: 18px; }
  .ui-workbench-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 14px; }
  .ui-workbench h2 { margin: 0; font-size: 17px; }
  .ui-workbench p { margin: 6px 0 0; }
  .ui-action-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
  .ui-action { min-height: 92px; text-align: left; border: 1px solid #354452; background: rgba(17, 24, 34, .72); border-radius: 12px; padding: 14px; color: inherit; }
  .ui-action:hover { border-color: #2bb5a8; transform: translateY(-1px); }
  .ui-action strong, .ui-action span { display: block; }
  .ui-action strong { margin-bottom: 7px; font-size: 14px; }
  .ui-action span { color: #9aa7b6; font-size: 12px; line-height: 1.6; }
  .ui-table-tools { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 12px 0; }
  .ui-table-tools input { max-width: 300px; }
  .ui-table-tools .muted { margin: 0; }
  .ui-health { display: inline-flex; align-items: center; gap: 7px; padding: 7px 10px; border: 1px solid #3b5344; border-radius: 999px; background: rgba(50, 119, 74, .14); color: #9fdbab; font-size: 12px; white-space: nowrap; }
  .ui-health.is-warn { border-color: #765737; background: rgba(154, 103, 30, .14); color: #ffd291; }
  @media (max-width: 880px) { .ui-action-grid { grid-template-columns: 1fr; } .ui-workbench-head, .ui-table-tools { align-items: stretch; flex-direction: column; } .ui-table-tools input { max-width: none; } }
</style>
<script>
(() => {
  if (document.getElementById('joker-admin-ui-ready')) return;
  const marker = document.createElement('meta'); marker.id = 'joker-admin-ui-ready'; document.head.append(marker);
  const go = (view) => document.querySelector(`[data-view="${view}"]`)?.click();
  const addFinder = (targetId, hint) => {
    const target = document.getElementById(targetId);
    if (!target || document.getElementById(`${targetId}-finder`)) return;
    const tools = document.createElement('div');
    tools.className = 'ui-table-tools'; tools.id = `${targetId}-finder`;
    tools.innerHTML = `<p class="muted">输入关键字可快速定位记录</p><input aria-label="筛选列表" placeholder="${hint}">`;
    target.before(tools);
    const input = tools.querySelector('input');
    const apply = () => {
      const keyword = input.value.trim().toLowerCase();
      target.querySelectorAll('tbody tr').forEach((row) => { row.hidden = !!keyword && !row.innerText.toLowerCase().includes(keyword); });
    };
    input.addEventListener('input', apply);
    new MutationObserver(apply).observe(target, { childList: true, subtree: true });
  };
  const addWorkbench = () => {
    const overview = document.getElementById('overview');
    if (!overview || document.getElementById('admin-workbench')) return;
    const workbench = document.createElement('section');
    workbench.className = 'ui-workbench'; workbench.id = 'admin-workbench';
    workbench.innerHTML = `
      <div class="ui-workbench-head"><div><h2>管理工作台</h2><p class="muted">按顺序完成授权、用户管理和机器人服务检查。</p></div><span class="ui-health" id="admin-health">正在读取服务状态</span></div>
      <div class="ui-action-grid">
        <button class="ui-action" data-console-go="cards"><strong>生成机器人授权卡</strong><span>创建卡密后交给客户完成注册与邮箱验证。</span></button>
        <button class="ui-action" data-console-go="users"><strong>查看分群用户</strong><span>筛选账号、查看绑定群，并处理停用或密码重置。</span></button>
        <button class="ui-action" data-console-go="runtime"><strong>检查运行状态</strong><span>确认网关、事件处理和最近错误是否正常。</span></button>
      </div>`;
    overview.append(workbench);
    workbench.querySelectorAll('[data-console-go]').forEach((button) => button.addEventListener('click', () => go(button.dataset.consoleGo)));
    const refresh = () => {
      const status = (document.getElementById('status')?.textContent || '').trim();
      const health = document.getElementById('admin-health');
      if (!health) return;
      const warning = /错误|失败|关闭|断开/.test(status);
      health.classList.toggle('is-warn', warning);
      health.textContent = warning ? `需检查：${status || '服务状态异常'}` : `服务正常：${status || '已连接'}`;
    };
    new MutationObserver(refresh).observe(document.getElementById('status') || workbench, { childList: true, characterData: true, subtree: true });
    refresh();
  };
  const init = () => { addWorkbench(); addFinder('cards-table', '搜索卡密或状态'); addFinder('users-table', '搜索账号、邮箱或群号'); };
  init(); setTimeout(init, 500); setTimeout(init, 1400);
})();
</script>
"""

_GROUP_UI_ENHANCEMENT = r"""
<style id="joker-group-ui-enhancement">
  .ui-group-workspace { border: 1px solid #254f4b; background: linear-gradient(135deg, rgba(17, 111, 100, .16), rgba(18, 24, 34, .82)); border-radius: 14px; padding: 18px; margin-bottom: 16px; }
  .ui-group-workspace-head { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:14px; }
  .ui-group-workspace h2 { margin:0; font-size:17px; }.ui-group-workspace p { margin:6px 0 0; }
  .ui-group-summary { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin:14px 0; }
  .ui-group-summary > div { min-height:76px; padding:12px; border:1px solid #334753; border-radius:10px; background:rgba(13,21,30,.56); }
  .ui-group-summary span,.ui-group-summary strong { display:block; }.ui-group-summary span { color:#9ca9b7; font-size:12px; }.ui-group-summary strong { margin-top:7px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:14px; }
  .ui-group-steps { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
  .ui-group-step { display:flex; gap:10px; align-items:flex-start; padding:12px; border-radius:10px; background:rgba(12,19,28,.52); }
  .ui-group-step b { display:inline-flex; flex:0 0 24px; height:24px; justify-content:center; align-items:center; border-radius:50%; background:#0f8176; color:white; font-size:12px; }.ui-group-step span { color:#adb7c4; font-size:12px; line-height:1.6; }
  .ui-group-actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }.ui-feature-filter { margin:0 0 12px; max-width:360px; }
  .ui-member-panel { display:grid; gap:14px; }.ui-member-toolbar { display:flex; flex-wrap:wrap; gap:10px; align-items:end; }.ui-member-toolbar label { flex:1 1 220px; }.ui-member-toolbar .button { flex:0 0 auto; }
  .ui-member-note { padding:10px 12px; border-radius:9px; background:rgba(24, 86, 80, .18); color:#c1d7d4; font-size:12px; line-height:1.65; }.ui-member-result { min-height:20px; color:#9fd9c9; font-size:13px; }.ui-member-result.error { color:#ffb0a8; }
  .ui-member-list { overflow:auto; }.ui-member-list td:last-child { white-space:nowrap; }.ui-member-actions { display:flex; flex-wrap:wrap; gap:8px; }
  @media (max-width:900px) { .ui-group-summary { grid-template-columns:repeat(2,minmax(0,1fr)); }.ui-group-steps { grid-template-columns:1fr; }.ui-group-workspace-head { flex-direction:column; } }
  @media (max-width:520px) { .ui-group-summary { grid-template-columns:1fr; } }
</style>
<script>
(() => {
  if (document.getElementById('joker-group-ui-ready')) return;
  const marker = document.createElement('meta'); marker.id = 'joker-group-ui-ready'; document.head.append(marker);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const request = async (url) => { const response = await fetch(url, { headers: { 'Accept': 'application/json' } }); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '读取配置失败'); return data; };
  const postJson = async (url, payload) => { const response = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'}, body:JSON.stringify(payload) }); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '操作失败'); return data; };
  const go = (view) => document.querySelector(`[data-view="${view}"]`)?.click();
  let memberScope = ''; let members = [];
  const currentScope = () => document.getElementById('scope-switch')?.value || '';
  const memberId = (member) => String(member?.member_openid || member?.user_openid || member?.openid || '').trim();
  const memberRole = (member) => ({owner:'群主',admin:'管理员',member:'普通成员'})[String(member?.member_role || 'member').toLowerCase()] || '群成员';
  const memberName = (member, fallback = '群成员') => String(member?.username || member?.nick || member?.nickname || fallback).trim() || fallback;
  const memberNameById = (userId, fallback = '已离群成员') => memberName(members.find((member) => memberId(member) === String(userId)) || {}, fallback);
  const memberOptions = (selected = '') => ['<option value="">请选择群成员</option>'].concat(members.map((member) => { const id = memberId(member); if (!id) return ''; const label = `${memberName(member)} · ${memberRole(member)}${member.bot ? ' · 机器人' : ''}`; return `<option value="${esc(id)}" ${id === selected ? 'selected' : ''}>${esc(label)}</option>`; })).join('');
  const result = (id, text, isError = false) => { const target = document.getElementById(id); if (!target) return; target.textContent = text || ''; target.classList.toggle('error', isError); };
  const fillMemberSelects = () => document.querySelectorAll('[data-member-select]').forEach((select) => { const previous = select.value; select.innerHTML = memberOptions(previous); if (previous) select.value = previous; });
  const memberValue = (selectId, inputId) => String(document.getElementById(inputId)?.value || document.getElementById(selectId)?.value || '').trim();
  const loadMembers = async (force = false) => {
    const scope = currentScope();
    if (!scope) { members = []; memberScope = ''; fillMemberSelects(); return []; }
    if (!force && memberScope === scope && members.length) return members;
    const data = await request('/api/group-members?scope_id=' + encodeURIComponent(scope) + '&all=1');
    members = Array.isArray(data.members) ? data.members.filter((member) => memberId(member)) : [];
    memberScope = scope; fillMemberSelects(); return members;
  };
  const build = () => {
    const groupsView = document.getElementById('groups');
    if (!groupsView || document.getElementById('group-workspace')) return;
    const panel = document.createElement('section'); panel.className = 'ui-group-workspace'; panel.id = 'group-workspace';
    panel.innerHTML = `
      <div class="ui-group-workspace-head"><div><h2>当前群配置</h2><p class="muted">每个官方群独立保存功能、规则和服务器信息。</p></div><span class="tag" id="group-workspace-state">读取中</span></div>
      <div class="ui-group-summary" id="group-workspace-summary"><div><span>已授权群</span><strong>-</strong></div><div><span>当前群号</span><strong>-</strong></div><div><span>已开启功能</span><strong>-</strong></div><div><span>SCUM 服务器</span><strong>-</strong></div></div>
      <div class="ui-group-steps"><div class="ui-group-step"><b>1</b><span>先在目标群发送 <code>/绑定官方群 数字QQ群号</code>，让机器人记录官方群。</span></div><div class="ui-group-step"><b>2</b><span>在这里填写同一个 QQ 群号，完成当前账号与官方群绑定。</span></div><div class="ui-group-step"><b>3</b><span>选择功能并进入对应设置页，规则只作用于当前群。</span></div></div>
      <div class="ui-group-actions"><button class="button primary" data-group-go="bind">绑定官方群</button><button class="button" data-group-go="switches">配置功能</button><button class="button" data-group-go="server">设置 SCUM</button></div>`;
    groupsView.prepend(panel);
    panel.querySelectorAll('[data-group-go]').forEach((button) => button.addEventListener('click', () => go(button.dataset.groupGo)));
  };
  const addFeatureSearch = () => {
    const list = document.getElementById('switch-list');
    if (!list || document.getElementById('ui-feature-filter')) return;
    const input = document.createElement('input'); input.className = 'ui-feature-filter'; input.id = 'ui-feature-filter'; input.placeholder = '搜索功能，例如 关键词、入群、禁言'; input.setAttribute('aria-label', '搜索功能');
    list.before(input);
    const apply = () => { const keyword = input.value.trim().toLowerCase(); list.querySelectorAll('.card').forEach((card) => { card.hidden = !!keyword && !card.innerText.toLowerCase().includes(keyword); }); };
    input.addEventListener('input', apply); new MutationObserver(apply).observe(list, { childList:true, subtree:true });
  };
  const refresh = async () => {
    const summary = document.getElementById('group-workspace-summary'); const state = document.getElementById('group-workspace-state');
    if (!summary || !state) return;
    try {
      const groups = await request('/api/groups');
      const currentScope = document.getElementById('scope-switch')?.value || groups[0]?.scope_id || '';
      if (!groups.length || !currentScope) { state.textContent = '尚未绑定'; summary.innerHTML = '<div><span>已授权群</span><strong>0</strong></div><div><span>当前群号</span><strong>未绑定</strong></div><div><span>已开启功能</span><strong>-</strong></div><div><span>SCUM 服务器</span><strong>-</strong></div>'; return; }
      const current = groups.find((item) => item.scope_id === currentScope) || groups[0];
      const config = await request('/api/group-config?scope_id=' + encodeURIComponent(current.scope_id));
      const enabled = (config.features || []).filter((item) => item.enabled).length;
      state.textContent = '已授权';
      summary.innerHTML = `<div><span>已授权群</span><strong>${esc(groups.length)} 个</strong></div><div><span>当前群号</span><strong title="${esc(current.numeric_group_id || current.scope_id)}">${esc(current.numeric_group_id || current.scope_id)}</strong></div><div><span>已开启功能</span><strong>${esc(enabled)} 项</strong></div><div><span>SCUM 服务器</span><strong title="${esc(config.server_id || '未设置')}">${esc(config.server_id || '未设置')}</strong></div>`;
    } catch (error) { state.textContent = '读取失败'; }
  };
  const renderBlacklist = async () => {
    const target = document.getElementById('member-blacklist-list'); const scope = currentScope(); if (!target || !scope) return;
    try { const rows = await request('/api/blacklist?scope_id=' + encodeURIComponent(scope)); target.innerHTML = rows.length ? `<table><thead><tr><th>成员</th><th>原因</th><th></th></tr></thead><tbody>${rows.map((row) => `<tr><td>${esc(memberNameById(row.user_id, '已拉黑成员'))}</td><td>${esc(row.reason || '-')}</td><td><button class="button" data-remove-blacklist="${esc(row.user_id)}">解除黑名单</button></td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无黑名单成员</div>'; target.querySelectorAll('[data-remove-blacklist]').forEach((button) => button.onclick = async () => { try { await postJson('/api/blacklist', {scope_id:scope,user_id:button.dataset.removeBlacklist,action:'remove'}); result('member-blacklist-result','已解除黑名单'); await renderBlacklist(); } catch (error) { result('member-blacklist-result',error.message,true); } }); } catch (error) { target.innerHTML = `<div class="empty">${esc(error.message)}</div>`; }
  };
  const renderMessages = async () => {
    const target = document.getElementById('member-message-list'); const scope = currentScope(); if (!target || !scope) return;
    try { const rows = await request('/api/messages?scope_id=' + encodeURIComponent(scope) + '&limit=100'); target.innerHTML = rows.length ? `<table><thead><tr><th>时间</th><th>成员</th><th>内容</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${esc(row.created_at || '')}</td><td>${esc(memberNameById(row.user_id, '已记录成员'))}</td><td>${esc(row.content || '')}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无已记录消息</div>'; } catch (error) { target.innerHTML = `<div class="empty">${esc(error.message)}</div>`; }
  };
  const renderGroupAdmins = async () => {
    const target = document.getElementById('member-admin-list'); const scope = currentScope(); if (!target || !scope) return;
    try { const rows = await request('/api/group-admins?scope_id=' + encodeURIComponent(scope)); target.innerHTML = rows.length ? `<table><thead><tr><th>成员</th><th>备注</th><th></th></tr></thead><tbody>${rows.map((row) => `<tr><td>${esc(memberNameById(row.user_id, row.display_name || '群成员'))}</td><td>${esc(row.display_name || '-')}</td><td><button class="button danger" data-remove-group-admin="${esc(row.user_id)}">删除</button></td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无分管管理员</div>'; target.querySelectorAll('[data-remove-group-admin]').forEach((button) => button.onclick = async () => { try { await postJson('/api/group-admins', {scope_id:scope,user_id:button.dataset.removeGroupAdmin,action:'remove'}); await renderGroupAdmins(); } catch (error) { result('member-admin-result',error.message,true); } }); } catch (error) { target.innerHTML = `<div class="empty">${esc(error.message)}</div>`; }
  };
  const renderUserReplies = async () => {
    const target = document.getElementById('member-user-reply-list'); const scope = currentScope(); if (!target || !scope) return;
    try { const rows = await request('/api/user-replies?scope_id=' + encodeURIComponent(scope)); target.innerHTML = rows.length ? `<table><thead><tr><th>成员</th><th>关键词</th><th>回复</th><th></th></tr></thead><tbody>${rows.map((row) => `<tr><td>${esc(memberNameById(row.user_id, '已记录成员'))}</td><td>${esc(row.trigger || '')}</td><td>${esc(row.response || '')}</td><td><button class="button danger" data-remove-user-reply="${esc(row.user_id)}" data-trigger="${esc(row.trigger)}">删除</button></td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无专属回复</div>'; target.querySelectorAll('[data-remove-user-reply]').forEach((button) => button.onclick = async () => { try { await postJson('/api/user-replies/delete', {scope_id:scope,user_id:button.dataset.removeUserReply,trigger:button.dataset.trigger}); await renderUserReplies(); } catch (error) { result('member-user-reply-result',error.message,true); } }); } catch (error) { target.innerHTML = `<div class="empty">${esc(error.message)}</div>`; }
  };
  const renderApproval = async () => {
    const target = document.getElementById('member-approval-list'); const scope = currentScope(); if (!target || !scope) return;
    try { const data = await request('/api/join-requests?scope_id=' + encodeURIComponent(scope)); const rows = Array.isArray(data) ? data : (data.join_requests || data.items || data.list || data.data || []); target.innerHTML = rows.length ? `<table><thead><tr><th>申请成员</th><th>申请说明</th><th></th></tr></thead><tbody>${rows.map((row) => { const userId = String(row.member_openid || row.user_openid || row.openid || ''); const requestId = String(row.join_request_id || row.request_id || row.id || ''); return `<tr><td>${esc(row.username || row.nick || '申请成员')}</td><td>${esc(row.message || row.apply_reason || '-')}</td><td class="ui-member-actions"><button class="button primary" data-approval="approve" data-member="${esc(userId)}" data-request="${esc(requestId)}">同意</button><button class="button danger" data-approval="decline" data-member="${esc(userId)}" data-request="${esc(requestId)}">拒绝</button></td></tr>`; }).join('')}</tbody></table>` : '<div class="empty">暂无待处理申请</div>'; target.querySelectorAll('[data-approval]').forEach((button) => button.onclick = async () => { try { const payload = {scope_id:scope,member_openid:button.dataset.member,join_request_id:button.dataset.request,operation:button.dataset.approval}; if (payload.operation === 'decline') payload.reject_reason = window.prompt('拒绝原因（可留空）') || ''; await postJson('/api/join-requests/approve', payload); result('member-approval-result','审核操作已提交'); await renderApproval(); } catch (error) { result('member-approval-result',error.message,true); } }); } catch (error) { target.innerHTML = `<div class="empty">${esc(error.message)}</div>`; }
  };
  const setupMemberPanels = () => {
     const moderation = document.getElementById('moderation'); if (moderation && !moderation.dataset.memberUi) { moderation.dataset.memberUi = '1'; moderation.innerHTML = `<div class="split"><div class="panel ui-member-panel"><div class="panel-head"><div><h2>手动群管</h2><p class="muted">可直接输入成员 QQ 号或 OpenID，也可以从官方群成员中选择。官方群主、管理员和机器人不能被禁言。</p></div><button class="button" id="member-reload">读取群成员</button></div><div class="ui-member-note">官方接口只接受 OpenID；如果成员列表没有返回 QQ 号映射，请填写官方 OpenID 或使用群消息中的成员引用。</div><div class="form"><label>成员 QQ号或官方 OpenID<input id="member-moderation-direct" placeholder="直接输入，或从列表选择"></label><label>选择成员<select id="member-moderation-select" data-member-select></select></label><label>操作<select id="member-moderation-action"><option value="mute">禁言</option><option value="unmute">解除禁言</option><option value="kick">踢出群聊</option><option value="blacklist">踢出并加入黑名单</option></select></label><label>禁言时长（秒）<input id="member-moderation-seconds" type="number" min="1" max="2592000" value="600"></label></div><div class="ui-member-actions"><button class="button danger" id="member-run-moderation">执行成员操作</button><button class="button" id="member-mute-all">全体禁言</button><button class="button" id="member-unmute-all">解除全体禁言</button></div><div class="ui-member-result" id="member-moderation-result"></div></div></div>`; }
     const blacklist = document.getElementById('blacklist'); if (blacklist && !blacklist.dataset.memberUi) { blacklist.dataset.memberUi = '1'; blacklist.innerHTML = `<div class="split"><div class="panel ui-member-panel"><div class="panel-head"><div><h2>群黑名单</h2><p class="muted">先移出成员，再调用 QQ 官方群黑名单接口添加。接口未获白名单权限时会明确提示。</p></div></div><div class="form two"><label>成员 QQ号或官方 OpenID<input id="member-blacklist-direct" placeholder="直接输入，或从列表选择"></label><label>选择成员<select id="member-blacklist-select" data-member-select></select></label><label>原因（可选）<input id="member-blacklist-reason" maxlength="500"></label></div><button class="button danger" id="member-add-blacklist">移出并拉黑</button><div class="ui-member-result" id="member-blacklist-result"></div></div><div class="panel"><h3>当前黑名单</h3><div class="ui-member-list" id="member-blacklist-list"></div><div id="blacklist-list" hidden></div></div></div>`; }
     const messages = document.getElementById('messages'); if (messages && !messages.dataset.memberUi) { messages.dataset.memberUi = '1'; messages.innerHTML = `<div class="split"><div class="panel ui-member-panel"><div class="panel-head"><div><h2>按成员撤回消息</h2><p class="muted">只会请求撤回该成员 2 分钟内的已记录消息；机器人必须是群管理员，超时消息会自动跳过。</p></div><button class="button" id="member-refresh-messages">刷新记录</button></div><div class="form two"><label>成员 QQ号或官方 OpenID<input id="member-recall-direct" placeholder="直接输入，或从列表选择"></label><label>选择成员<select id="member-recall-select" data-member-select></select></label><label>最多撤回条数<input id="member-recall-limit" type="number" min="1" max="100" value="20"></label></div><button class="button danger" id="member-recall-user">撤回该成员消息</button><div class="ui-member-result" id="member-message-result"></div></div><div class="panel"><h3>已记录消息</h3><div class="ui-member-list" id="member-message-list"></div><div id="message-list" hidden></div></div></div>`; }
     const userReplies = document.getElementById('user-replies'); if (userReplies && !userReplies.dataset.memberUi) { userReplies.dataset.memberUi = '1'; userReplies.innerHTML = `<div class="split"><div class="panel ui-member-panel"><div class="panel-head"><div><h2>用户专属回复</h2><p class="muted">可直接输入成员 QQ 号或 OpenID，也可以从列表选择。</p></div></div><div class="form"><label>成员 QQ号或官方 OpenID<input id="member-user-reply-direct" placeholder="直接输入，或从列表选择"></label><label>选择成员<select id="member-user-reply-select" data-member-select></select></label><label>关键词<input id="member-user-reply-trigger" maxlength="128"></label><label>回复内容<input id="member-user-reply-response" maxlength="2000"></label></div><button class="button primary" id="member-add-user-reply">保存专属回复</button><div class="ui-member-result" id="member-user-reply-result"></div></div><div class="panel"><h3>已配置回复</h3><div class="ui-member-list" id="member-user-reply-list"></div><div id="user-reply-list" hidden></div></div></div>`; }
     const groupAdmins = document.getElementById('group-admins'); if (groupAdmins && !groupAdmins.dataset.memberUi) { groupAdmins.dataset.memberUi = '1'; groupAdmins.innerHTML = `<div class="split"><div class="panel ui-member-panel"><div class="panel-head"><div><h2>分管管理员</h2><p class="muted">可直接输入成员 QQ 号或 OpenID，也可以从列表选择。仅用于机器人内部命令授权。</p></div></div><div class="form two"><label>成员 QQ号或官方 OpenID<input id="member-admin-direct" placeholder="直接输入，或从列表选择"></label><label>选择成员<select id="member-admin-select" data-member-select></select></label><label>备注（可选）<input id="member-admin-name" maxlength="100"></label></div><button class="button primary" id="member-add-group-admin">添加分管管理员</button><div class="ui-member-result" id="member-admin-result"></div></div><div class="panel"><h3>当前分管管理员</h3><div class="ui-member-list" id="member-admin-list"></div><div id="group-admin-list" hidden></div></div></div>`; }
    const approval = document.getElementById('approval'); if (approval && !approval.dataset.memberUi) { approval.dataset.memberUi = '1'; approval.innerHTML = `<div class="panel ui-member-panel"><div class="panel-head"><div><h2>入群审核</h2><p class="muted">通过 QQ 官方审核接口处理入群申请。</p></div><div class="ui-member-actions"><button class="button primary" id="member-direct-approval">开启直接入群</button><button class="button" id="member-disable-direct-approval">关闭直接入群</button><button class="button" id="member-refresh-approval">刷新申请</button></div></div><div class="ui-member-list" id="member-approval-list"></div><div class="ui-member-result" id="member-approval-result"></div><div id="approval-list" hidden></div></div>`; }
    fillMemberSelects();
    document.getElementById('member-reload')?.addEventListener('click', async () => { try { await loadMembers(true); result('member-moderation-result',`已读取 ${members.length} 名群成员`); } catch (error) { result('member-moderation-result',error.message,true); } });
     document.getElementById('member-run-moderation')?.addEventListener('click', async () => { const userId = memberValue('member-moderation-select','member-moderation-direct'); const action = document.getElementById('member-moderation-action')?.value || ''; if (!userId) { result('member-moderation-result','请填写成员 QQ号或官方 OpenID',true); return; } try { const data = await postJson('/api/moderation',{scope_id:currentScope(),user_id:userId,action,duration_seconds:Number(document.getElementById('member-moderation-seconds')?.value || 600)}); result('member-moderation-result',data.message || '群管操作已提交'); if (action === 'blacklist' || action === 'kick') { await loadMembers(true); await renderBlacklist(); } } catch (error) { result('member-moderation-result',error.message,true); } });
    document.getElementById('member-mute-all')?.addEventListener('click', async () => { if (!window.confirm('确认禁言所有普通成员吗？群主、管理员和机器人会被跳过。')) return; try { const data = await postJson('/api/moderation',{scope_id:currentScope(),action:'mute_all',duration_seconds:Number(document.getElementById('member-moderation-seconds')?.value || 600)}); result('member-moderation-result',data.message || '全体禁言已提交'); } catch (error) { result('member-moderation-result',error.message,true); } });
    document.getElementById('member-unmute-all')?.addEventListener('click', async () => { if (!window.confirm('确认解除所有普通成员的禁言吗？')) return; try { const data = await postJson('/api/moderation',{scope_id:currentScope(),action:'unmute_all'}); result('member-moderation-result',data.message || '已解除全体禁言'); } catch (error) { result('member-moderation-result',error.message,true); } });
     document.getElementById('member-add-blacklist')?.addEventListener('click', async () => { const userId = memberValue('member-blacklist-select','member-blacklist-direct'); if (!userId) { result('member-blacklist-result','请填写成员 QQ号或官方 OpenID',true); return; } if (!window.confirm('确认移出该成员并加入官方群黑名单吗？')) return; try { await postJson('/api/blacklist',{scope_id:currentScope(),user_id,reason:document.getElementById('member-blacklist-reason')?.value.trim() || ''}); result('member-blacklist-result','已移出成员并加入黑名单'); await loadMembers(true); await renderBlacklist(); } catch (error) { result('member-blacklist-result',error.message,true); } });
    document.getElementById('member-refresh-messages')?.addEventListener('click', renderMessages);
     document.getElementById('member-recall-user')?.addEventListener('click', async () => { const userId = memberValue('member-recall-select','member-recall-direct'); if (!userId) { result('member-message-result','请填写成员 QQ号或官方 OpenID',true); return; } try { const data = await postJson('/api/moderation',{scope_id:currentScope(),user_id:userId,action:'recall_user',recall_limit:Number(document.getElementById('member-recall-limit')?.value || 20)}); result('member-message-result',data.message || '撤回请求已提交'); await renderMessages(); } catch (error) { result('member-message-result',error.message,true); } });
     document.getElementById('member-add-user-reply')?.addEventListener('click', async () => { const userId = memberValue('member-user-reply-select','member-user-reply-direct'); if (!userId) { result('member-user-reply-result','请填写成员 QQ号或官方 OpenID',true); return; } try { await postJson('/api/user-replies',{scope_id:currentScope(),user_id:userId,trigger:document.getElementById('member-user-reply-trigger')?.value.trim() || '',response:document.getElementById('member-user-reply-response')?.value.trim() || ''}); result('member-user-reply-result','专属回复已保存'); await renderUserReplies(); } catch (error) { result('member-user-reply-result',error.message,true); } });
     document.getElementById('member-add-group-admin')?.addEventListener('click', async () => { const userId = memberValue('member-admin-select','member-admin-direct'); if (!userId) { result('member-admin-result','请填写成员 QQ号或官方 OpenID',true); return; } try { await postJson('/api/group-admins',{scope_id:currentScope(),user_id:userId,display_name:document.getElementById('member-admin-name')?.value.trim() || ''}); result('member-admin-result','分管管理员已保存'); await renderGroupAdmins(); } catch (error) { result('member-admin-result',error.message,true); } });
    document.getElementById('member-refresh-approval')?.addEventListener('click', renderApproval);
    document.getElementById('member-direct-approval')?.addEventListener('click', async () => { try { await postJson('/api/join-approval/direct',{scope_id:currentScope(),enabled:true}); result('member-approval-result','已开启官方直接入群策略'); } catch (error) { result('member-approval-result',error.message,true); } });
    document.getElementById('member-disable-direct-approval')?.addEventListener('click', async () => { try { await postJson('/api/join-approval/direct',{scope_id:currentScope(),enabled:false}); result('member-approval-result','已关闭官方直接入群策略'); } catch (error) { result('member-approval-result',error.message,true); } });
  };
  const hydrateMemberPanels = async () => { try { await loadMembers(); await Promise.all([renderBlacklist(),renderMessages(),renderGroupAdmins(),renderUserReplies(),renderApproval()]); } catch (error) { result('member-moderation-result',error.message,true); } };
  const init = () => { build(); addFeatureSearch(); setupMemberPanels(); refresh(); const select = document.getElementById('scope-switch'); if (select && !select.dataset.uiSummaryBound) { select.dataset.uiSummaryBound = '1'; select.addEventListener('change', () => { memberScope = ''; members = []; setTimeout(() => { refresh(); hydrateMemberPanels(); }, 120); }); } hydrateMemberPanels(); };
  init(); setTimeout(init, 600); setTimeout(init, 1600);
})();
</script>
"""


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
      <div class="panel"><h2>运行信息</h2><p class="muted" id="last-event">暂无事件</p><p class="muted" id="message-mode" style="margin-top:8px">群消息模式检查中</p><p class="muted" id="last-error" style="margin-top:8px"></p></div>
      <div class="panel"><h2>服务操作</h2><button class="primary" id="restart-service">重启机器人服务</button><p class="muted" id="restart-result" style="margin-top:10px"></p></div>
      <div class="notice">只有状态显示“全量群消息已收到”时，非 @ 消息才会进入机器人。若一直显示“当前仅收到 @ 消息”，还需要在 QQ 开放平台和目标群开启全量消息权限。</div>
    </section>
    <section class="view" id="groups">
      <div class="panel"><h2>群组数据</h2><div id="groups-table"></div></div>
      <div class="panel"><h2>分群配置</h2><label>选择群组<select id="group-config-scope"></select></label><div id="group-config" style="margin-top:14px"></div><button class="primary" id="save-group-config" style="margin-top:14px">保存群设置</button><p class="muted" id="group-config-result" style="margin-top:10px"></p></div>
      <div class="panel"><h2>分管管理员</h2><div class="form"><label>用户 OpenID<input id="group-admin-user" placeholder="用户 OpenID"></label><label>显示名称<input id="group-admin-name" placeholder="可选"></label><button id="save-group-admin">添加</button></div><div id="group-admins-table" style="margin-top:14px"></div></div>
      <div class="panel"><h2>用户专属回复</h2><div class="form"><label>用户 OpenID<input id="user-reply-user" placeholder="用户 OpenID"></label><label>关键词<input id="user-reply-trigger" placeholder="关键词"></label><label>回复内容<input id="user-reply-response" placeholder="回复内容"></label><button id="save-user-reply">保存</button></div><div id="user-replies-table" style="margin-top:14px"></div></div>
      <div class="panel"><h2>定时消息</h2><div class="form"><label>间隔分钟<input id="schedule-interval" type="number" min="1" value="60"></label><label>消息内容<input id="schedule-content" placeholder="消息内容"></label><button id="save-schedule">添加</button></div><div id="schedules-table" style="margin-top:14px"></div></div>
      <div class="panel"><h2>群消息记录</h2><div id="messages-table"></div></div>
    </section>
    <section class="view" id="replies">
      <div class="panel"><h2>选择群组</h2><label>群组 OpenID<select id="reply-scope"></select></label></div>
      <div class="panel"><h2>添加自动回复</h2><div class="reply-form"><label>关键词<input id="reply-trigger" placeholder="关键词"></label><label>回复内容<input id="reply-response" placeholder="回复内容"></label><button class="primary" id="save-reply">保存</button></div></div>
      <div class="panel"><h2>已有回复</h2><div id="replies-table"></div></div>
    </section>
    <section class="view" id="features"><div class="panel"><h2>功能目录</h2><div id="features-table"></div></div></section>
    <section class="view" id="settings">
      <div class="panel"><h2>运行配置</h2><p class="muted" style="margin-bottom:14px">保存后机器人会自动重载，敏感字段不会回显。</p><div class="form" style="grid-template-columns:1fr 1fr 1fr"><label>接收方式<select id="setting-transport"><option value="webhook">Webhook</option><option value="websocket">WebSocket</option></select></label><label>AppID<input id="setting-app-id"></label><label>官方 API 地址<input id="setting-api-base" placeholder="https://api.bot.qq.com"></label><label>AppSecret<input id="setting-app-secret" type="password" placeholder="留空保持不变"></label><label>SCUM 中转地址<input id="setting-scum-url"></label><label>SCUM Key<input id="setting-scum-key" type="password" placeholder="留空保持不变"></label><label>网页版操作台<input id="setting-portal-url" placeholder="https://web.yooyun.top"></label><label>控制台监听地址<input id="setting-dashboard-bind"></label><label>控制台端口<input id="setting-dashboard-port" type="number" min="1" max="65535"></label><label>控制台访问令牌<input id="setting-dashboard-token" type="password" placeholder="留空保持不变"></label></div><button class="primary" id="save-settings" style="margin-top:16px">保存并重载</button><a id="portal-link" href="https://web.yooyun.top" target="_blank" rel="noopener" style="display:inline-block;margin:16px 0 0 10px;color:#ff9b76">打开网页版操作台</a><p class="muted" id="settings-result" style="margin-top:10px"></p></div>
    </section>
  </main>
  <script>
    const token = new URLSearchParams(location.search).get('token') || '';
    const headers = token ? {'X-Dashboard-Token': token} : {};
    let groups = [];
     let selectedGroupScope = '';
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
     const renderGroupConfig = data => { const target = document.getElementById('group-config'); target.innerHTML = `<div class="form" style="grid-template-columns:1fr 1fr 1fr"><label>SCUM 服务器 ID<input id="config-server-id" value="${esc(data.server_id || '')}" placeholder="服务器 ID"></label><label>自动回复<select id="config-auto-reply"><option value="1" ${data.auto_reply_enabled ? 'selected' : ''}>开启</option><option value="0" ${data.auto_reply_enabled ? '' : 'selected'}>关闭</option></select></label><label>群消息记录<select id="config-message-records"><option value="1" ${data.features.find(f => f.key === 'message_records')?.enabled ? 'selected' : ''}>开启</option><option value="0" ${data.features.find(f => f.key === 'message_records')?.enabled ? '' : 'selected'}>关闭</option></select></label></div><div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:14px">${data.features.filter(f => f.key !== 'message_records').map(f => `<label style="display:flex;align-items:center;gap:8px"><input type="checkbox" data-feature="${esc(f.key)}" ${f.enabled ? 'checked' : ''}>${esc(f.label)}</label>`).join('')}</div>`; };
     const loadGroupConfig = async () => { const scope = document.getElementById('group-config-scope').value; selectedGroupScope = scope; if (!scope) { document.getElementById('group-config').innerHTML = '<div class="empty">还没有群组数据</div>'; document.getElementById('messages-table').innerHTML = ''; return; } const data = await request('/api/group-config?scope_id=' + encodeURIComponent(scope)); renderGroupConfig(data); const admins = await request('/api/group-admins?scope_id=' + encodeURIComponent(scope)); document.getElementById('group-admins-table').innerHTML = admins.length ? `<table><thead><tr><th>名称</th><th>OpenID</th><th>操作</th></tr></thead><tbody>${admins.map(row => `<tr><td>${esc(row.display_name)}</td><td>${esc(row.user_id)}</td><td><button data-remove-admin="${esc(row.user_id)}">删除</button></td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无分管管理员</div>'; document.querySelectorAll('[data-remove-admin]').forEach(button => button.onclick = async () => { await request('/api/group-admins', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id:scope, user_id:button.dataset.removeAdmin, action:'remove'})}); await loadGroupConfig(); }); const userReplies = await request('/api/user-replies?scope_id=' + encodeURIComponent(scope)); document.getElementById('user-replies-table').innerHTML = userReplies.length ? `<table><thead><tr><th>用户 OpenID</th><th>关键词</th><th>回复</th><th>操作</th></tr></thead><tbody>${userReplies.map(row => `<tr><td>${esc(row.user_id)}</td><td>${esc(row.trigger)}</td><td>${esc(row.response)}</td><td><button data-remove-user-reply="${esc(row.user_id)}" data-remove-user-trigger="${esc(row.trigger)}">删除</button></td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无用户专属回复</div>'; document.querySelectorAll('[data-remove-user-reply]').forEach(button => button.onclick = async () => { await request('/api/user-replies/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id:scope, user_id:button.dataset.removeUserReply, trigger:button.dataset.removeUserTrigger})}); await loadGroupConfig(); }); const schedules = await request('/api/schedules?scope_id=' + encodeURIComponent(scope)); document.getElementById('schedules-table').innerHTML = schedules.length ? `<table><thead><tr><th>编号</th><th>间隔</th><th>消息</th><th>状态</th><th>操作</th></tr></thead><tbody>${schedules.map(row => `<tr><td>${row.schedule_id}</td><td>${Math.floor(row.interval_seconds / 60)} 分钟</td><td>${esc(row.content)}</td><td>${row.enabled ? '开启' : '关闭'}</td><td><button data-remove-schedule="${row.schedule_id}">删除</button></td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无定时消息</div>'; document.querySelectorAll('[data-remove-schedule]').forEach(button => button.onclick = async () => { await request('/api/schedules/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id:scope, schedule_id:Number(button.dataset.removeSchedule)})}); await loadGroupConfig(); }); const messages = await request('/api/messages?scope_id=' + encodeURIComponent(scope)); document.getElementById('messages-table').innerHTML = messages.length ? `<table><thead><tr><th>时间</th><th>用户 OpenID</th><th>消息 ID</th><th>内容</th></tr></thead><tbody>${messages.map(row => `<tr><td>${esc(row.created_at)}</td><td>${esc(row.user_id)}</td><td>${esc(row.message_id)}</td><td>${esc(row.content)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无群消息记录</div>'; };
     const loadGroups = async () => { groups = await request('/api/groups'); renderGroups(); const select = document.getElementById('reply-scope'); select.innerHTML = groups.map(g => `<option value="${esc(g.scope_id)}">${esc(g.numeric_group_id || g.scope_id)}</option>`).join(''); const configSelect = document.getElementById('group-config-scope'); configSelect.innerHTML = groups.map(g => `<option value="${esc(g.scope_id)}">${esc(g.numeric_group_id || g.scope_id)}</option>`).join(''); if (selectedGroupScope && groups.some(g => g.scope_id === selectedGroupScope)) configSelect.value = selectedGroupScope; await loadReplies(); await loadGroupConfig(); };
    const loadReplies = async () => { const scope = document.getElementById('reply-scope').value; const target = document.getElementById('replies-table'); if (!scope) { target.innerHTML = '<div class="empty">请先让机器人收到一条群消息</div>'; return; } const rows = await request('/api/replies?scope_id=' + encodeURIComponent(scope)); target.innerHTML = rows.length ? `<table><thead><tr><th>关键词</th><th>回复内容</th><th>操作</th></tr></thead><tbody>${rows.map((r, i) => `<tr><td>${esc(r.trigger)}</td><td>${esc(r.response)}</td><td><button data-delete-reply="${i}">删除</button></td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无自动回复</div>'; target.querySelectorAll('[data-delete-reply]').forEach(button => button.onclick = async () => { const row = rows[Number(button.dataset.deleteReply)]; await request('/api/replies/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id:scope, trigger:row.trigger})}); await loadReplies(); }); };
    const loadFeatures = async () => { const rows = await request('/api/features'); document.getElementById('features-table').innerHTML = `<table><thead><tr><th>功能</th><th>目录</th><th>状态</th><th>说明</th></tr></thead><tbody>${rows.map(f => `<tr><td>${esc(f.label)}</td><td>${esc(f.folder)}</td><td><span class="tag ${f.status}">${esc(f.status_label)}</span></td><td>${esc(f.note)}</td></tr>`).join('')}</tbody></table>`; };
    const loadSettings = async () => { const data = await request('/api/settings'); document.getElementById('setting-transport').value = data.transport || 'webhook'; document.getElementById('setting-app-id').value = data.app_id || ''; document.getElementById('setting-api-base').value = data.api_base_url || 'https://api.bot.qq.com'; document.getElementById('setting-scum-url').value = data.scum_relay_url || ''; document.getElementById('setting-portal-url').value = data.portal_url || ''; document.getElementById('portal-link').href = data.portal_url || 'https://web.yooyun.top'; document.getElementById('setting-dashboard-bind').value = data.dashboard_bind || ''; document.getElementById('setting-dashboard-port').value = data.dashboard_port || 8080; };
     const loadStatus = async () => { const data = await request('/api/status'); document.getElementById('gateway-state').textContent = data.gateway_state; document.getElementById('event-count').textContent = data.event_count; document.getElementById('reply-count').textContent = data.reply_count; document.getElementById('group-count').textContent = data.group_count; document.getElementById('status-text').textContent = data.gateway_state === 'connected' ? '官方接口已连接' : data.gateway_state; document.getElementById('last-event').textContent = data.last_event ? `最近事件：${data.last_event} ${data.last_event_at || ''}` : '暂无事件'; const fullCount = Number(data.full_message_event_count || 0); const atCount = Number(data.at_message_event_count || 0); document.getElementById('message-mode').textContent = fullCount ? `全量群消息已收到（${fullCount}）` : atCount ? `当前仅收到 @ 消息（${atCount}），请在 QQ 开放平台和目标群开启全量消息权限` : '尚未收到群消息'; document.getElementById('last-error').textContent = data.last_error ? `最近错误：${data.last_error}` : ''; };
    document.querySelectorAll('nav button').forEach(button => button.onclick = () => { document.querySelectorAll('nav button').forEach(item => item.classList.remove('active')); document.querySelectorAll('.view').forEach(item => item.classList.remove('active')); button.classList.add('active'); document.getElementById(button.dataset.view).classList.add('active'); });
    document.getElementById('reply-scope').onchange = loadReplies;
     document.getElementById('group-config-scope').onchange = loadGroupConfig;
     document.getElementById('save-group-config').onclick = async () => { const scope = document.getElementById('group-config-scope').value; if (!scope) return; const features = {}; document.querySelectorAll('[data-feature]').forEach(input => features[input.dataset.feature] = input.checked); const recordSelect = document.getElementById('config-message-records'); features.message_records = recordSelect.value === '1'; const result = document.getElementById('group-config-result'); result.textContent = '保存中...'; try { await request('/api/group-config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id:scope, features, server_id:document.getElementById('config-server-id').value.trim(), auto_reply_enabled:document.getElementById('config-auto-reply').value === '1'})}); result.textContent = '已保存'; await loadGroups(); } catch (error) { result.textContent = error.message; } };
     document.getElementById('save-group-admin').onclick = async () => { const scope = document.getElementById('group-config-scope').value; const userId = document.getElementById('group-admin-user').value.trim(); if (!scope || !userId) return; await request('/api/group-admins', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id:scope, user_id:userId, display_name:document.getElementById('group-admin-name').value.trim()})}); document.getElementById('group-admin-user').value = ''; document.getElementById('group-admin-name').value = ''; await loadGroupConfig(); };
     document.getElementById('save-user-reply').onclick = async () => { const scope = document.getElementById('group-config-scope').value; const userId = document.getElementById('user-reply-user').value.trim(); const trigger = document.getElementById('user-reply-trigger').value.trim(); const response = document.getElementById('user-reply-response').value.trim(); if (!scope || !userId || !trigger || !response) return; await request('/api/user-replies', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id:scope, user_id:userId, trigger, response})}); document.getElementById('user-reply-user').value = ''; document.getElementById('user-reply-trigger').value = ''; document.getElementById('user-reply-response').value = ''; await loadGroupConfig(); };
     document.getElementById('save-schedule').onclick = async () => { const scope = document.getElementById('group-config-scope').value; const interval = Number(document.getElementById('schedule-interval').value); const content = document.getElementById('schedule-content').value.trim(); if (!scope || !content || !interval) return; await request('/api/schedules', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id:scope, interval_minutes:interval, content})}); document.getElementById('schedule-content').value = ''; await loadGroupConfig(); };
    document.getElementById('save-reply').onclick = async () => { const scope = document.getElementById('reply-scope').value; const trigger = document.getElementById('reply-trigger').value.trim(); const response = document.getElementById('reply-response').value.trim(); if (!scope || !trigger || !response) return; await request('/api/replies', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id:scope, trigger, response})}); document.getElementById('reply-trigger').value = ''; document.getElementById('reply-response').value = ''; await loadReplies(); await loadGroups(); };
     document.getElementById('restart-service').onclick = async () => { const button = document.getElementById('restart-service'); const result = document.getElementById('restart-result'); if (!window.confirm('确定重启机器人服务吗？')) return; button.disabled = true; result.textContent = '正在重启...'; try { await request('/api/restart', {method:'POST'}); result.textContent = '服务正在重启，页面将自动刷新。'; setTimeout(() => location.reload(), 2500); } catch (error) { result.textContent = '重启请求已发送，请稍后刷新页面。'; setTimeout(() => location.reload(), 3000); } };
    document.getElementById('save-settings').onclick = async () => { const result = document.getElementById('settings-result'); result.textContent = '保存中...'; const payload = {transport: document.getElementById('setting-transport').value, app_id: document.getElementById('setting-app-id').value.trim(), api_base_url: document.getElementById('setting-api-base').value.trim(), app_secret: document.getElementById('setting-app-secret').value, scum_relay_url: document.getElementById('setting-scum-url').value.trim(), scum_relay_key: document.getElementById('setting-scum-key').value, portal_url: document.getElementById('setting-portal-url').value.trim(), dashboard_bind: document.getElementById('setting-dashboard-bind').value.trim(), dashboard_port: Number(document.getElementById('setting-dashboard-port').value), dashboard_token: document.getElementById('setting-dashboard-token').value}; try { const data = await request('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}); result.textContent = '已保存，机器人正在重载。'; setTimeout(() => location.href = '/?token=' + encodeURIComponent(data.access_token || token), 1500); } catch (error) { result.textContent = error.message; } };
    const loadAll = async () => { try { await Promise.all([loadStatus(), loadGroups(), loadFeatures(), loadSettings()]); } catch (error) { document.getElementById('status-text').textContent = error.message; } };
    loadAll(); setInterval(loadStatus, 5000); setInterval(loadGroups, 10000);
  </script>
</body>
</html>"""

PAGE = PAGE.replace(
    '<button data-view="features">功能</button>',
    '<button data-view="features">功能</button><button data-view="authorization">授权与账号</button>'
)
PAGE = PAGE.replace(
    '<div class="status"><span class="dot" id="status-dot"></span><span id="status-text">连接检查中</span></div>',
    '<div style="display:flex;align-items:center;gap:14px"><span id="current-user" class="muted"></span><button id="logout-button">退出登录</button><div class="status"><span class="dot" id="status-dot"></span><span id="status-text">连接检查中</span></div></div>'
)
PAGE = PAGE.replace(
    '<div class="panel"><h2>服务操作</h2><button class="primary" id="restart-service">重启机器人服务</button><p class="muted" id="restart-result" style="margin-top:10px"></p></div>',
    '<div class="panel"><h2>机器人开关</h2><button class="primary" id="power-toggle">读取状态</button><p class="muted" id="power-result" style="margin-top:10px"></p></div><div class="panel"><h2>服务操作</h2><button class="primary" id="restart-service">重启机器人服务</button><p class="muted" id="restart-result" style="margin-top:10px"></p></div>'
)
PAGE = PAGE.replace(
    '    <section class="view" id="settings">',
    r'''    <section class="view" id="authorization">
      <div id="admin-auth-panel">
        <div class="panel"><h2>生成分群注册卡</h2><p class="muted" style="margin-bottom:12px">分群用户使用这张卡注册控制台账号，只能看到指定群组。</p><div class="form"><label>群组<select id="group-card-scope"></select></label><label>可注册次数<input id="group-card-uses" type="number" min="1" value="1"></label><label>有效天数<input id="group-card-days" type="number" min="1" value="30"></label><button class="primary" id="create-group-card">生成</button></div><p class="muted" id="group-card-result" style="margin-top:10px"></p></div>
        <div class="panel"><h2>生成 QQ 用户授权卡</h2><p class="muted" style="margin-bottom:12px">用户在群内使用 `/授权 卡密`，授权后才能使用机器人功能。</p><div class="form"><label>授权范围<select id="bot-card-scope"><option value="">全部群</option></select></label><label>可使用次数<input id="bot-card-uses" type="number" min="1" value="1"></label><label>有效天数<input id="bot-card-days" type="number" min="1" value="30"></label><button class="primary" id="create-bot-card">生成</button></div><p class="muted" id="bot-card-result" style="margin-top:10px"></p></div>
        <div class="panel"><h2>卡密列表</h2><div id="cards-table"></div></div>
        <div class="panel"><h2>QQ 用户授权</h2><div id="authorizations-table"></div></div>
        <div class="panel"><h2>控制台账号</h2><div id="dashboard-users-table"></div></div>
      </div>
      <div id="group-auth-panel" class="panel" hidden><h2>当前账号</h2><p class="muted">这是分群账号，只能管理注册卡绑定的群组。</p></div>
    </section>
    <section class="view" id="settings">'''
)
PAGE = PAGE.replace(
    '     const loadAll = async () => { try { await Promise.all([loadStatus(), loadGroups(), loadFeatures(), loadSettings()]); } catch (error) { document.getElementById(\'status-text\').textContent = error.message; } };\n    loadAll(); setInterval(loadStatus, 5000); setInterval(loadGroups, 10000);',
    r'''     let currentUser = null;
     const loadMe = async () => { currentUser = await request('/api/auth/me'); document.getElementById('current-user').textContent = currentUser.role === 'admin' ? `管理员：${currentUser.username}` : `分群账号：${currentUser.username}`; if (currentUser.role !== 'admin') { document.querySelector('[data-view="authorization"]').hidden = true; document.querySelector('[data-view="settings"]').hidden = true; document.getElementById('admin-auth-panel').hidden = true; document.getElementById('group-auth-panel').hidden = false; document.getElementById('power-toggle').closest('.panel').hidden = true; document.getElementById('restart-service').closest('.panel').hidden = true; } };
     const loadPower = async () => { const data = await request('/api/power'); const button = document.getElementById('power-toggle'); button.textContent = data.enabled ? '机器人运行中，点击关闭' : '机器人已关闭，点击开启'; button.dataset.enabled = data.enabled ? '1' : '0'; button.classList.toggle('primary', data.enabled); };
     const renderAuthData = (data) => { const now = Math.floor(Date.now() / 1000); document.getElementById('cards-table').innerHTML = data.cards.length ? `<table><thead><tr><th>卡密</th><th>用途</th><th>群组</th><th>使用次数</th><th>到期</th><th>操作</th></tr></thead><tbody>${data.cards.map(row => `<tr><td>${esc(row.card_code)}</td><td>${row.kind === 'group' ? '分群注册' : 'QQ 授权'}</td><td>${esc(row.scope_id || '全部群')}</td><td>${row.used_count}/${row.max_uses}</td><td>${row.expires_at > now ? new Date(row.expires_at * 1000).toLocaleString() : '已过期'}</td><td>${row.enabled ? `<button data-revoke-card="${esc(row.card_code)}">停用</button>` : '<span class="tag blocked">已停用</span>'}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无卡密</div>'; document.querySelectorAll('[data-revoke-card]').forEach(button => button.onclick = async () => { await request('/api/auth/revoke-card', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({card_code:button.dataset.revokeCard})}); await loadAuthData(); }); document.getElementById('authorizations-table').innerHTML = data.users.bot_authorizations.length ? `<table><thead><tr><th>用户 OpenID</th><th>范围</th><th>到期</th><th>操作</th></tr></thead><tbody>${data.users.bot_authorizations.map(row => `<tr><td>${esc(row.user_openid)}</td><td>${esc(row.scope_id || '全部群')}</td><td>${row.expires_at ? new Date(row.expires_at * 1000).toLocaleString() : '永久'}</td><td>${row.enabled ? `<button data-revoke-user="${esc(row.user_openid)}">撤销</button>` : '<span class="tag blocked">已撤销</span>'}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无 QQ 用户授权</div>'; document.querySelectorAll('[data-revoke-user]').forEach(button => button.onclick = async () => { await request('/api/auth/revoke-user', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({user_openid:button.dataset.revokeUser})}); await loadAuthData(); }); document.getElementById('dashboard-users-table').innerHTML = data.users.dashboard_users.length ? `<table><thead><tr><th>账号</th><th>类型</th><th>群组</th><th>状态</th></tr></thead><tbody>${data.users.dashboard_users.map(row => `<tr><td>${esc(row.username)}</td><td>${row.role === 'admin' ? '管理员' : '分群账号'}</td><td>${esc(row.scope_id || '全部群')}</td><td>${row.enabled ? '正常' : '停用'}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">暂无账号</div>'; };
     const loadAuthData = async () => { if (!currentUser || currentUser.role !== 'admin') return; const data = {cards: await request('/api/auth/cards'), users: await request('/api/auth/users')}; renderAuthData(data); };
     document.getElementById('power-toggle').onclick = async () => { const button = document.getElementById('power-toggle'); const enabled = button.dataset.enabled !== '1'; await request('/api/power', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled})}); await loadPower(); document.getElementById('power-result').textContent = enabled ? '机器人已开启。' : '机器人已关闭。'; };
     document.getElementById('create-group-card').onclick = async () => { const result = document.getElementById('group-card-result'); try { const data = await request('/api/auth/cards', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({kind:'group', scope_id:document.getElementById('group-card-scope').value, max_uses:Number(document.getElementById('group-card-uses').value), days:Number(document.getElementById('group-card-days').value)})}); result.textContent = `卡密：${data.card_code}`; await loadAuthData(); } catch (error) { result.textContent = error.message; } };
     document.getElementById('create-bot-card').onclick = async () => { const result = document.getElementById('bot-card-result'); try { const data = await request('/api/auth/cards', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({kind:'bot', scope_id:document.getElementById('bot-card-scope').value, max_uses:Number(document.getElementById('bot-card-uses').value), days:Number(document.getElementById('bot-card-days').value)})}); result.textContent = `卡密：${data.card_code}`; await loadAuthData(); } catch (error) { result.textContent = error.message; } };
     document.getElementById('logout-button').onclick = async () => { await fetch('/logout', {method:'POST'}); location.href = '/'; };
     const loadAll = async () => { try { await loadMe(); await Promise.all([loadStatus(), loadGroups(), loadFeatures(), currentUser.role === 'admin' ? loadSettings() : Promise.resolve(), loadPower()]); const fill = id => { const select = document.getElementById(id); select.innerHTML = groups.map(g => `<option value="${esc(g.scope_id)}">${esc(g.numeric_group_id || g.scope_id)}</option>`).join(''); }; fill('group-card-scope'); fill('bot-card-scope'); const botScope = document.getElementById('bot-card-scope'); botScope.insertAdjacentHTML('afterbegin', '<option value="">全部群</option>'); await loadAuthData(); } catch (error) { document.getElementById('status-text').textContent = error.message; } };
     loadAll(); setInterval(loadStatus, 5000); setInterval(loadGroups, 10000); setInterval(loadPower, 10000);'''
)


HOME_PAGE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Joker QQ 机器人</title><style>
:root{font-family:Inter,"Microsoft YaHei",sans-serif;color:#172033;background:#f4f6f8}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:linear-gradient(135deg,#f7f9fb,#eef2f6);padding:32px}.home{width:min(980px,100%);margin:0 auto}.brand{display:flex;align-items:center;gap:12px;color:#172033}.mark{width:42px;height:42px;border-radius:10px;background:#e86d3f;color:#fff;display:grid;place-items:center;font-weight:800}.brand span{color:#687386;font-size:13px}.hero{padding:72px 0 48px;max-width:700px}.hero h1{margin:0 0 16px;font-size:clamp(34px,6vw,58px);line-height:1.08;letter-spacing:0}.hero p{margin:0;color:#687386;font-size:17px;line-height:1.8}.features{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.feature{border:1px solid #dfe5ec;border-radius:10px;background:#fff;padding:22px;min-height:150px}.feature strong{display:block;margin-bottom:10px;font-size:17px}.feature span{color:#687386;font-size:14px;line-height:1.7}.actions{margin-top:28px}.button{display:inline-block;padding:12px 20px;border-radius:7px;background:#e86d3f;color:#fff;text-decoration:none;font-weight:700}.foot{margin-top:42px;color:#8a94a3;font-size:13px}@media(max-width:680px){body{padding:22px}.hero{padding:54px 0 34px}.features{grid-template-columns:1fr}.feature{min-height:auto}}
</style></head><body><main class="home"><div class="brand"><div class="mark">J</div><strong>Joker QQ</strong><span>官方机器人服务</span></div><section class="hero"><h1>让群管理更简单</h1><p>群组管理、SCUM 查询、自动回复和分群配置，统一接入 QQ 官方机器人。</p><div class="actions"><a class="button" href="__USER_PATH__">进入分群用户中心</a></div></section><section class="features"><div class="feature"><strong>群组管理</strong><span>按群独立配置功能和管理员，权限清晰，互不影响。</span></div><div class="feature"><strong>SCUM 查询</strong><span>绑定服务器后查询在线状态、服务器信息和玩家数据。</span></div><div class="feature"><strong>分群配置</strong><span>用户只管理自己的群组，授权和配置集中维护。</span></div></section><p class="foot">Joker QQ 官方机器人控制台</p></main></body></html>"""


AUTH_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Joker QQ Admin 登录</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, "Microsoft YaHei", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #171717; color: #ededed; }
    main { width: min(420px, calc(100% - 32px)); border: 1px solid #363636; background: #202020; border-radius: 8px; padding: 28px; box-shadow: 0 18px 50px #0008; }
    h1, p { margin: 0; }
    h1 { font-size: 22px; margin-bottom: 9px; }
    p { color: #a9a9a9; font-size: 13px; line-height: 1.6; margin-bottom: 20px; }
    label { display: grid; gap: 7px; color: #cfcfcf; font-size: 13px; }
    input { width: 100%; border: 1px solid #444; border-radius: 5px; background: #151515; color: #eee; padding: 11px 12px; font: inherit; }
    button { width: 100%; margin-top: 16px; border: 1px solid #e86d3f; border-radius: 6px; background: #e86d3f; color: #fff; padding: 11px 13px; font: inherit; cursor: pointer; }
    button:hover { background: #f47d4e; }
    .error { color: #ff9b9b; margin-top: 12px; margin-bottom: 0; }
  </style>
</head>
<body>
  <main>
    <h1>Joker QQ Admin</h1>
    <p>请输入控制台访问令牌后进入官方 QQ 机器人控制台。</p>
    <form id="login-form">
      <label>访问令牌<input id="dashboard-token" type="password" autocomplete="current-password" autofocus></label>
      <button type="submit">进入控制台</button>
    </form>
    <p id="login-error" class="error" hidden>访问令牌无效，请重新输入。</p>
  </main>
  <script>
    const form = document.getElementById('login-form');
    const tokenInput = document.getElementById('dashboard-token');
    const hasToken = new URLSearchParams(location.search).has('token');
    if (hasToken) document.getElementById('login-error').hidden = false;
    form.addEventListener('submit', event => {
      event.preventDefault();
      const value = tokenInput.value.trim();
      if (value) location.href = '/?token=' + encodeURIComponent(value);
    });
  </script>
</body>
</html>"""


AUTH_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Joker QQ Admin</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, "Microsoft YaHei", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #171717; color: #ededed; }
    main { width: min(440px, calc(100% - 32px)); border: 1px solid #363636; background: #202020; border-radius: 8px; padding: 28px; box-shadow: 0 18px 50px #0008; }
    h1, p { margin: 0; } h1 { font-size: 22px; margin-bottom: 9px; } p { color: #a9a9a9; font-size: 13px; line-height: 1.6; margin-bottom: 20px; }
    .tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 18px; } .tabs button { margin: 0; border-color: #444; background: #292929; } .tabs button.active { background: #e86d3f; border-color: #e86d3f; }
    form { display: grid; gap: 12px; } label { display: grid; gap: 7px; color: #cfcfcf; font-size: 13px; }
    input { width: 100%; border: 1px solid #444; border-radius: 5px; background: #151515; color: #eee; padding: 11px 12px; font: inherit; }
    button { width: 100%; border: 1px solid #e86d3f; border-radius: 6px; background: #e86d3f; color: #fff; padding: 11px 13px; font: inherit; cursor: pointer; } button:hover { background: #f47d4e; }
    .secondary { background: #292929; border-color: #444; } .error { color: #ff9b9b; margin-top: 12px; margin-bottom: 0; } .hint { margin-top: 16px; font-size: 12px; }
  </style>
</head>
<body>
  <main>
    <h1>Joker QQ Admin</h1>
    <p>官方 QQ 机器人控制台。管理员负责全局设置、用户和卡密；分群用户只管理自己已授权的群。</p>
    <div class="tabs"><button class="active" id="login-tab">__LOGIN_LABEL__</button><button id="register-tab">分群注册</button></div>
    <form id="login-form">
      <label>账号<input id="login-username" autocomplete="username" autofocus></label>
      <label>密码<input id="login-password" type="password" autocomplete="current-password"></label>
      <button type="submit">登录</button>
      <button type="button" class="secondary" id="token-login">使用访问令牌</button>
    </form>
    <form id="register-form" hidden>
      <label>用户注册卡<input id="register-card" placeholder="JOKER-XXXXXXXXXX"></label>
      <label>账号<input id="register-username" autocomplete="username"></label>
      <label>邮箱<input id="register-email" type="email" autocomplete="email" placeholder="可选，管理员开启后为必填"></label>
      <label>密码<input id="register-password" type="password" autocomplete="new-password"></label>
      <button type="submit">注册并登录</button>
    </form>
    <p id="auth-error" class="error" hidden></p>
    <p class="hint">先用用户注册卡创建账号；登录后再用群授权卡绑定要管理的官方群。QQ 用户授权仍可在群内使用 /授权 卡密。</p>
  </main>
  <script>
    const audience = '__AUTH_AUDIENCE__'; const loginEndpoint = '__LOGIN_ENDPOINT__'; const registerEndpoint = '__REGISTER_ENDPOINT__'; const adminPath = '__ADMIN_PATH__'; const loginTab = document.getElementById('login-tab'); const registerTab = document.getElementById('register-tab'); const loginForm = document.getElementById('login-form'); const registerForm = document.getElementById('register-form'); const error = document.getElementById('auth-error');
    if (audience === 'admin') { registerTab.hidden = true; registerForm.hidden = true; }
    const show = form => { loginForm.hidden = form !== 'login'; registerForm.hidden = form !== 'register'; loginTab.classList.toggle('active', form === 'login'); registerTab.classList.toggle('active', form === 'register'); error.hidden = true; };
    loginTab.onclick = () => show('login'); registerTab.onclick = () => show('register');
    const submit = async (url, data) => { const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)}); const result = await response.json().catch(() => ({})); if (!response.ok) throw new Error(result.error || '操作失败'); return result; };
    loginForm.onsubmit = async event => { event.preventDefault(); try { const result = await submit(loginEndpoint, {username:document.getElementById('login-username').value, password:document.getElementById('login-password').value}); location.href = result.redirect || adminPath; } catch (e) { error.textContent = e.message; error.hidden = false; } };
    registerForm.onsubmit = async event => { event.preventDefault(); try { const result = await submit(registerEndpoint, {card_code:document.getElementById('register-card').value, username:document.getElementById('register-username').value, email:document.getElementById('register-email').value, password:document.getElementById('register-password').value}); location.href = result.redirect || '__USER_PATH__'; } catch (e) { error.textContent = e.message; error.hidden = false; } };
    document.getElementById('token-login').onclick = () => { const token = window.prompt('请输入控制台访问令牌'); if (token) location.href = adminPath + '?token=' + encodeURIComponent(token); };
  </script>
</body>
</html>"""


ADMIN_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Joker QQ Admin · 管理后台</title>
  <style>
    :root { color-scheme: light; font-family: Inter, "Microsoft YaHei", sans-serif; --ink:#172033; --muted:#687386; --line:#e5e9f0; --surface:#fff; --soft:#f5f7fb; --accent:#e86d3f; --accent-dark:#c6532c; --ok:#198754; }
    * { box-sizing:border-box } body { margin:0; color:var(--ink); background:#f3f5f8 } button,input,select { font:inherit } button { border:0; cursor:pointer }
    .shell { display:grid; grid-template-columns:238px 1fr; min-height:100vh } .sidebar { background:#172033; color:#e9eef7; padding:25px 16px; display:flex; flex-direction:column; gap:24px }
    .brand { padding:0 12px } .brand strong { display:block; font-size:19px; letter-spacing:.2px } .brand span { color:#93a0b7; font-size:12px; margin-top:6px; display:block }
    .nav { display:grid; gap:5px } .nav button { background:transparent; color:#aeb9ca; text-align:left; padding:11px 12px; border-radius:7px } .nav button:hover,.nav button.active { background:#27344d; color:white }
    .sidebar-foot { margin-top:auto; padding:0 12px; color:#93a0b7; font-size:12px; line-height:1.7 } .sidebar-foot button { color:#fff; background:#33415b; padding:8px 10px; border-radius:6px; margin-top:10px }
    .main { min-width:0 } .topbar { background:var(--surface); border-bottom:1px solid var(--line); min-height:76px; padding:18px 34px; display:flex; justify-content:space-between; align-items:center; gap:20px }
    .topbar h1 { margin:0; font-size:22px } .topbar p { margin:5px 0 0; color:var(--muted); font-size:13px } .top-actions { display:flex; align-items:center; gap:12px; color:var(--muted); font-size:13px }
    .status { display:inline-flex; align-items:center; gap:7px; white-space:nowrap } .status i { width:8px; height:8px; border-radius:50%; background:#19a463; display:block }
    .content { max-width:1400px; padding:30px 34px 60px; margin:0 auto } .view { display:none } .view.active { display:block }
    .metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-bottom:20px } .metric,.panel { background:var(--surface); border:1px solid var(--line); border-radius:10px; box-shadow:0 4px 16px #17203308 }
    .metric { padding:19px 20px } .metric small { color:var(--muted); font-size:12px } .metric strong { display:block; font-size:25px; margin-top:10px }
    .panel { padding:22px; margin-bottom:18px } .panel-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:18px } .panel h2 { margin:0; font-size:16px } .panel-head p { color:var(--muted); font-size:13px; margin:6px 0 0 }
    .grid2 { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px } .grid3 { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px }
    .form { display:grid; gap:13px } .form-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:13px } label { display:grid; gap:7px; color:#4f5b6d; font-size:12px } input,select { width:100%; padding:10px 11px; border:1px solid #d8dee8; border-radius:7px; background:#fff; color:var(--ink); outline:none } input:focus,select:focus { border-color:var(--accent); box-shadow:0 0 0 3px #e86d3f1c }
    .button { display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:10px 14px; border-radius:7px; background:#edf0f5; color:#344054; font-weight:600 } .button:hover { background:#dfe5ee } .button.primary { color:#fff; background:var(--accent) } .button.primary:hover { background:var(--accent-dark) } .button.danger { color:#a83232; background:#fff0f0 } .button.small { padding:7px 10px; font-size:12px }
    .toolbar { display:flex; flex-wrap:wrap; gap:10px; align-items:end } .toolbar > * { flex:1 1 160px } .toolbar .button { flex:0 0 auto } .hint,.muted { color:var(--muted); font-size:13px; line-height:1.6 } .notice { padding:13px 15px; border-left:3px solid var(--accent); background:#fff7f3; color:#6a4a3d; border-radius:5px; font-size:13px; line-height:1.6 }
    table { width:100%; border-collapse:collapse; font-size:13px } th,td { padding:12px 10px; text-align:left; border-bottom:1px solid var(--line); vertical-align:middle } th { color:var(--muted); font-weight:600 } tr:last-child td { border-bottom:0 } .empty { text-align:center; color:var(--muted); padding:28px 0 }
    .pill { display:inline-flex; padding:4px 9px; border-radius:999px; font-size:12px; background:#eaf7ef; color:var(--ok) } .pill.off { background:#fff0f0; color:#af4141 } .check-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:15px } .check { display:flex; align-items:center; gap:8px; color:#465267; font-size:13px; padding:10px; background:var(--soft); border-radius:7px } .check input { width:auto }
    @media(max-width:900px){ .shell{grid-template-columns:1fr}.sidebar{padding:15px;gap:14px}.nav{display:flex;overflow:auto}.nav button{white-space:nowrap}.sidebar-foot{display:none}.topbar{padding:18px}.content{padding:20px 16px}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.grid2,.form-grid{grid-template-columns:1fr}.check-grid{grid-template-columns:repeat(2,minmax(0,1fr))} }
    @media(max-width:520px){.metrics{grid-template-columns:1fr 1fr}.topbar{align-items:flex-start;flex-direction:column}.check-grid{grid-template-columns:1fr}table{display:block;overflow:auto;white-space:nowrap}}
  </style>
</head>
<body><div class="shell">
  <aside class="sidebar"><div class="brand"><strong>Joker QQ Admin</strong><span>官方 QQ 机器人管理后台</span></div><nav class="nav"><button class="active" data-view="overview">总览</button><button data-view="groups">群组配置</button><button data-view="approval">入群审核</button><button data-view="auth">授权与账号</button><button data-view="settings">系统设置</button></nav><div class="sidebar-foot"><div id="sidebar-user">管理员</div><button id="logout">退出登录</button></div></aside>
  <div class="main"><header class="topbar"><div><h1 id="page-title">运行总览</h1><p>集中管理官方机器人、群组权限和用户账号</p></div><div class="top-actions"><span class="status"><i></i><span id="gateway">连接检查中</span></span></div></header>
  <main class="content">
    <section class="view active" id="overview"><div class="metrics"><div class="metric"><small>Gateway</small><strong id="metric-gateway">-</strong></div><div class="metric"><small>接收事件</small><strong id="metric-events">0</strong></div><div class="metric"><small>已回复</small><strong id="metric-replies">0</strong></div><div class="metric"><small>已接入群组</small><strong id="metric-groups">0</strong></div></div><div class="grid2"><div class="panel"><div class="panel-head"><div><h2>机器人状态</h2><p>控制消息处理，不影响后台登录。</p></div><span id="power-pill" class="pill">运行中</span></div><button class="button primary" id="power-button">关闭机器人</button><p class="hint" id="power-result"></p></div><div class="panel"><div class="panel-head"><div><h2>消息接收</h2><p>确认 QQ 开放平台是否下发全量群消息。</p></div></div><p class="notice" id="message-mode">检查中</p><p class="hint" id="last-event"></p></div></div><div class="panel"><div class="panel-head"><div><h2>服务操作</h2><p>修改官方接口或 SMTP 配置后需要重载服务。</p></div><button class="button" id="restart">重载服务</button></div><p class="hint" id="restart-result"></p></div></section>
     <section class="view" id="groups"><div class="panel"><div class="panel-head"><div><h2>群组配置</h2><p>每个群独立设置功能、SCUM 服务器和自动回复。</p></div><button class="button" id="refresh-groups">刷新</button></div><div id="groups-table"></div></div></section>
     <section class="view" id="approval"><div class="grid2"><div class="panel"><div class="panel-head"><div><h2>入群申请</h2><p>官方接口返回申请 ID 和成员 OpenID，审批结果直接提交 QQ 官方接口。</p></div></div><div class="toolbar"><select id="approval-scope"></select><button class="button" id="load-requests">刷新申请</button></div><div id="requests-table" style="margin-top:16px"></div></div><div class="panel"><div class="panel-head"><div><h2>自动审批策略</h2><p>策略由 QQ 官方平台执行，是否开放取决于机器人权限。</p></div></div><div class="form"><label>关联群 OpenID<input id="strategy-group" placeholder="默认使用当前群"></label><label>备注<input id="strategy-remark" maxlength="255"></label><button class="button primary" id="create-strategy">创建策略</button></div><div id="strategies-table" style="margin-top:16px"></div></div></div></section>
    <section class="view" id="auth"><div class="grid2"><div class="panel"><div class="panel-head"><div><h2>分群注册卡</h2><p>发给分群用户，账号只绑定一个群。</p></div></div><div class="form"><label>绑定群组<select id="group-card-scope"></select></label><div class="grid2"><label>使用次数<input id="group-card-uses" type="number" min="1" value="1"></label><label>有效天数<input id="group-card-days" type="number" min="1" value="30"></label></div><button class="button primary" id="create-group-card">生成注册卡</button><p class="hint" id="group-card-result"></p></div></div><div class="panel"><div class="panel-head"><div><h2>QQ 用户授权卡</h2><p>用户在群内使用 `/授权 卡密`。</p></div></div><div class="form"><label>授权范围<select id="bot-card-scope"><option value="">全部群</option></select></label><div class="grid2"><label>使用次数<input id="bot-card-uses" type="number" min="1" value="1"></label><label>有效天数<input id="bot-card-days" type="number" min="1" value="30"></label></div><button class="button primary" id="create-bot-card">生成授权卡</button><p class="hint" id="bot-card-result"></p></div></div></div><div class="panel"><div class="panel-head"><div><h2>卡密</h2><p>可随时停用未使用的卡密。</p></div></div><div id="cards-table"></div></div><div class="grid2"><div class="panel"><div class="panel-head"><div><h2>QQ 授权用户</h2></div></div><div id="authorized-users"></div></div><div class="panel"><div class="panel-head"><div><h2>后台账号</h2></div></div><div id="dashboard-users"></div></div></div></section>
     <section class="view" id="settings"><div class="panel"><div class="panel-head"><div><h2>官方机器人</h2><p>敏感字段只写入服务器环境文件，不在页面回显。</p></div></div><div class="form-grid"><label>AppID<input id="setting-app-id"></label><label>接收方式<select id="setting-transport"><option value="webhook">Webhook</option><option value="websocket">WebSocket</option></select></label><label>官方 API 地址<input id="setting-api-base"></label><label>AppSecret<input id="setting-app-secret" type="password" placeholder="留空保持不变"></label><label>SCUM 中转地址<input id="setting-scum-url"></label><label>SCUM Key<input id="setting-scum-key" type="password" placeholder="留空保持不变"></label></div></div><div class="panel"><div class="panel-head"><div><h2>入口与注册</h2><p>根地址是首页，管理员和分群用户使用不同路径。</p></div></div><div class="form-grid"><label>管理员路径<input id="setting-admin-path" placeholder="/admin"></label><label>用户路径<input id="setting-user-path" placeholder="/user"></label><label>监听地址<input id="setting-dashboard-bind"></label><label>监听端口<input id="setting-dashboard-port" type="number"></label><label>访问令牌<input id="setting-dashboard-token" type="password" placeholder="留空保持不变"></label><label>网页版地址<input id="setting-portal-url"></label><label>注册必须填写邮箱<select id="setting-require-email"><option value="0">否</option><option value="1">是</option></select></label></div></div><div class="panel"><div class="panel-head"><div><h2>邮箱 SMTP</h2><p>用于邮箱登录资料和后续验证码扩展，密码不会回显。</p></div></div><div class="form-grid"><label>SMTP 主机<input id="setting-smtp-host" placeholder="smtp.qq.com"></label><label>SMTP 端口<input id="setting-smtp-port" type="number" value="587"></label><label>SMTP 用户名<input id="setting-smtp-username" type="email"></label><label>SMTP 密码<input id="setting-smtp-password" type="password" placeholder="留空保持不变"></label><label>发件邮箱<input id="setting-smtp-from" type="email"></label><label>加密方式<select id="setting-smtp-tls"><option value="1">TLS / STARTTLS</option><option value="0">不启用 TLS</option></select></label></div><button class="button primary" id="save-settings" style="margin-top:18px">保存并重载</button><p class="hint" id="settings-result"></p></div></section>
  </main></div></div>
  <script>
    const request=async(u,o={})=>{const r=await fetch(u,{...o,headers:{...(o.headers||{})}});if(!r.ok)throw new Error((await r.text())||`HTTP ${r.status}`);return r.json()};const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let groups=[];
    document.querySelectorAll('.nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.nav button').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.view).classList.add('active');document.getElementById('page-title').textContent=b.textContent});
    const loadStatus=async()=>{const d=await request('/api/status');document.getElementById('gateway').textContent=d.gateway_state;document.getElementById('metric-gateway').textContent=d.gateway_state;document.getElementById('metric-events').textContent=d.event_count;document.getElementById('metric-replies').textContent=d.reply_count;document.getElementById('metric-groups').textContent=d.group_count;document.getElementById('last-event').textContent=d.last_event?`最近事件：${d.last_event} ${d.last_event_at||''}`:'暂无事件';const f=Number(d.full_message_event_count||0),a=Number(d.at_message_event_count||0);document.getElementById('message-mode').textContent=f?`已收到全量群消息（${f}）`:a?`当前仅收到 @ 消息（${a}），请在 QQ 开放平台开启全量消息权限`:'尚未收到群消息'};
    const loadPower=async()=>{const d=await request('/api/power'),p=document.getElementById('power-pill'),b=document.getElementById('power-button');p.textContent=d.enabled?'运行中':'已关闭';p.className='pill'+(d.enabled?'':' off');b.textContent=d.enabled?'关闭机器人':'开启机器人';b.dataset.enabled=d.enabled?'1':'0'};
     const loadGroups=async()=>{groups=await request('/api/groups');document.getElementById('metric-groups').textContent=groups.length;const options=groups.map(g=>`<option value="${esc(g.scope_id)}">${esc(g.numeric_group_id||g.scope_id)}</option>`).join('');document.getElementById('group-card-scope').innerHTML=options||'<option value="">暂无群组</option>';document.getElementById('bot-card-scope').innerHTML='<option value="">全部群</option>'+options;document.getElementById('approval-scope').innerHTML=options||'<option value="">暂无群组</option>';document.getElementById('strategy-group').value=groups[0]?.scope_id||'';const box=document.getElementById('groups-table');if(!groups.length){box.innerHTML='<div class="empty">还没有收到群消息，先让机器人在目标群收到一条消息。</div>';return}box.innerHTML=`<table><thead><tr><th>群号</th><th>群 OpenID</th><th>SCUM</th><th>消息</th><th>自动回复</th></tr></thead><tbody>${groups.map(g=>`<tr><td>${esc(g.numeric_group_id||'-')}</td><td>${esc(g.scope_id)}</td><td>${esc(g.server_id||'-')}</td><td>${g.message_count}</td><td><span class="pill ${g.auto_reply_enabled?'':'off'}">${g.auto_reply_enabled?'开启':'关闭'}</span></td></tr>`).join('')}</tbody></table>`};
    const loadAuth=async()=>{const cards=await request('/api/auth/cards'),u=await request('/api/auth/users'),now=Math.floor(Date.now()/1000);document.getElementById('cards-table').innerHTML=cards.length?`<table><thead><tr><th>卡密</th><th>用途</th><th>范围</th><th>使用次数</th><th>状态</th><th></th></tr></thead><tbody>${cards.map(c=>`<tr><td><strong>${esc(c.card_code)}</strong></td><td>${c.kind==='group'?'分群注册':'QQ 授权'}</td><td>${esc(c.scope_id||'全部群')}</td><td>${c.used_count}/${c.max_uses}</td><td>${c.enabled&&c.expires_at>now?'<span class="pill">有效</span>':'<span class="pill off">停用/过期</span>'}</td><td>${c.enabled?`<button class="button danger small" data-card="${esc(c.card_code)}">停用</button>`:''}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">暂无卡密</div>';document.querySelectorAll('[data-card]').forEach(b=>b.onclick=async()=>{await request('/api/auth/revoke-card',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({card_code:b.dataset.card})});await loadAuth()});const a=u.bot_authorizations;document.getElementById('authorized-users').innerHTML=a.length?`<table><thead><tr><th>OpenID</th><th>范围</th><th>状态</th><th></th></tr></thead><tbody>${a.map(x=>`<tr><td>${esc(x.user_openid)}</td><td>${esc(x.scope_id||'全部群')}</td><td>${x.enabled?'<span class="pill">有效</span>':'<span class="pill off">已撤销</span>'}</td><td>${x.enabled?`<button class="button danger small" data-user="${esc(x.user_openid)}">撤销</button>`:''}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">暂无授权用户</div>';document.querySelectorAll('[data-user]').forEach(b=>b.onclick=async()=>{await request('/api/auth/revoke-user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_openid:b.dataset.user})});await loadAuth()});document.getElementById('dashboard-users').innerHTML=u.dashboard_users.length?`<table><thead><tr><th>账号</th><th>邮箱</th><th>类型</th><th>群组</th></tr></thead><tbody>${u.dashboard_users.map(x=>`<tr><td>${esc(x.username)}</td><td>${esc(x.email||'-')}</td><td>${x.role==='admin'?'管理员':'分群用户'}</td><td>${esc(x.scope_id||'全部')}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">暂无账号</div>'};
     const loadSettings=async()=>{const d=await request('/api/settings');for(const [id,v] of Object.entries({'setting-app-id':d.app_id,'setting-api-base':d.api_base_url,'setting-transport':d.transport,'setting-scum-url':d.scum_relay_url,'setting-portal-url':d.portal_url,'setting-admin-path':d.admin_path||d.dashboard_path,'setting-user-path':d.user_path||'/user','setting-dashboard-bind':d.dashboard_bind,'setting-dashboard-port':d.dashboard_port,'setting-smtp-host':d.smtp_host,'setting-smtp-port':d.smtp_port,'setting-smtp-username':d.smtp_username,'setting-smtp-from':d.smtp_from,'setting-require-email':d.registration_require_email?'1':'0','setting-smtp-tls':d.smtp_use_tls?'1':'0'})){const e=document.getElementById(id);if(e)e.value=v??''}};
    document.getElementById('power-button').onclick=async()=>{const enabled=document.getElementById('power-button').dataset.enabled!=='1';await request('/api/power',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})});await loadPower();document.getElementById('power-result').textContent=enabled?'机器人已开启':'机器人已关闭'};
    document.getElementById('create-group-card').onclick=async()=>{const r=document.getElementById('group-card-result');try{const d=await request('/api/auth/cards',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'group',scope_id:document.getElementById('group-card-scope').value,max_uses:+document.getElementById('group-card-uses').value,days:+document.getElementById('group-card-days').value})});r.textContent=`卡密：${d.card_code}`;await loadAuth()}catch(e){r.textContent=e.message}};
    document.getElementById('create-bot-card').onclick=async()=>{const r=document.getElementById('bot-card-result');try{const d=await request('/api/auth/cards',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'bot',scope_id:document.getElementById('bot-card-scope').value,max_uses:+document.getElementById('bot-card-uses').value,days:+document.getElementById('bot-card-days').value})});r.textContent=`卡密：${d.card_code}`;await loadAuth()}catch(e){r.textContent=e.message}};
    document.getElementById('save-settings').onclick=async()=>{const r=document.getElementById('settings-result');const p={app_id:document.getElementById('setting-app-id').value.trim(),api_base_url:document.getElementById('setting-api-base').value.trim(),transport:document.getElementById('setting-transport').value,app_secret:document.getElementById('setting-app-secret').value,scum_relay_url:document.getElementById('setting-scum-url').value.trim(),portal_url:document.getElementById('setting-portal-url').value.trim(),admin_path:document.getElementById('setting-admin-path').value.trim(),user_path:document.getElementById('setting-user-path').value.trim(),dashboard_bind:document.getElementById('setting-dashboard-bind').value.trim(),dashboard_port:+document.getElementById('setting-dashboard-port').value,dashboard_token:document.getElementById('setting-dashboard-token').value,smtp_host:document.getElementById('setting-smtp-host').value.trim(),smtp_port:+document.getElementById('setting-smtp-port').value,smtp_username:document.getElementById('setting-smtp-username').value.trim(),smtp_password:document.getElementById('setting-smtp-password').value,smtp_from:document.getElementById('setting-smtp-from').value.trim(),smtp_use_tls:document.getElementById('setting-smtp-tls').value==='1',registration_require_email:document.getElementById('setting-require-email').value==='1'};try{await request('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});r.textContent='已保存，服务正在重载。'}catch(e){r.textContent=e.message}};
    document.getElementById('restart').onclick=async()=>{const r=document.getElementById('restart-result');try{await request('/api/restart',{method:'POST'});r.textContent='服务正在重载，请稍后刷新页面';setTimeout(()=>location.reload(),2500)}catch(e){r.textContent=e.message}};document.getElementById('refresh-groups').onclick=loadGroups;document.getElementById('logout').onclick=async()=>{await fetch('__LOGOUT_ENDPOINT__',{method:'POST'});location.href='/'};
    (async()=>{try{const me=await request('/api/auth/me');document.getElementById('sidebar-user').textContent=`管理员：${me.display_name||me.username}`;await Promise.all([loadStatus(),loadPower(),loadGroups(),loadAuth(),loadSettings()])}catch(e){document.getElementById('gateway').textContent=e.message}})();setInterval(loadStatus,5000);setInterval(loadPower,10000);
  </script>
</body></html>"""


ADMIN_PAGE = ADMIN_PAGE.replace(
    "    const loadAuth=async()=>",
    r'''    const renderApprovalError=error=>{const message=esc(error.message||error);document.getElementById('requests-table').innerHTML=`<div class="empty">${message}</div>`;document.getElementById('strategies-table').innerHTML=`<div class="empty">${message}</div>`};
    const loadApproval=async()=>{const scope=document.getElementById('approval-scope').value;if(!scope){document.getElementById('requests-table').innerHTML='<div class="empty">暂无群组</div>';document.getElementById('strategies-table').innerHTML='<div class="empty">暂无群组</div>';return}try{const data=await request('/api/join-requests?scope_id='+encodeURIComponent(scope));const rows=Array.isArray(data.list)?data.list:[];document.getElementById('requests-table').innerHTML=rows.length?`<table><thead><tr><th>昵称</th><th>成员 OpenID</th><th>申请 ID</th><th>验证信息</th><th>操作</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(row.username||'未知')}</td><td>${esc(row.member_openid||'')}</td><td>${esc(row.join_request_id||'')}</td><td>${esc(row.verify_info?.verify_message||'无')}</td><td><button class="button small" data-approval="approve" data-member="${esc(row.member_openid||'')}" data-request="${esc(row.join_request_id||'')}">通过</button> <button class="button danger small" data-approval="decline" data-member="${esc(row.member_openid||'')}" data-request="${esc(row.join_request_id||'')}">拒绝</button></td></tr>`).join('')}</tbody></table>`:'<div class="empty">当前没有待处理的入群申请</div>';document.querySelectorAll('[data-approval]').forEach(button=>button.onclick=async()=>{const operation=button.dataset.approval;const reason=operation==='decline'?window.prompt('拒绝理由（可留空）','')||'':'';try{await request('/api/join-requests/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope_id,member_openid:button.dataset.member,join_request_id:button.dataset.request,operation,reject_reason:reason})});await loadApproval()}catch(error){renderApprovalError(error)}});const strategyData=await request('/api/join-approval-strategies');const strategies=Array.isArray(strategyData.list)?strategyData.list:(Array.isArray(strategyData.strategies)?strategyData.strategies:[]);document.getElementById('strategies-table').innerHTML=strategies.length?`<table><thead><tr><th>策略 ID</th><th>群组</th><th>状态</th><th>备注</th><th>操作</th></tr></thead><tbody>${strategies.map(row=>{const enabled=row.is_enable===true||row.is_enable==='on'||row.status==='enabled';const groups=(row.group_openids||row.group_ids||[]);return `<tr><td>${esc(row.strategy_id||row.id||'')}</td><td>${esc(Array.isArray(groups)?groups.join(', '):groups)}</td><td>${enabled?'<span class="pill">开启</span>':'<span class="pill off">关闭</span>'}</td><td>${esc(row.remark||'-')}</td><td><button class="button small" data-strategy-toggle="${esc(row.strategy_id||row.id||'')}" data-enabled="${enabled?'1':'0'}">${enabled?'关闭':'开启'}</button> <button class="button small" data-strategy-execute="${esc(row.strategy_id||row.id||'')}">执行</button> <button class="button danger small" data-strategy-delete="${esc(row.strategy_id||row.id||'')}">删除</button></td></tr>`}).join('')}</tbody></table>`:'<div class="empty">暂无自动审批策略</div>';document.querySelectorAll('[data-strategy-toggle]').forEach(button=>button.onclick=async()=>{try{await request('/api/join-approval-strategies/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({strategy_id:button.dataset.strategyToggle,is_enable:button.dataset.enabled==='1'?'off':'on'})});await loadApproval()}catch(error){renderApprovalError(error)}});document.querySelectorAll('[data-strategy-execute]').forEach(button=>button.onclick=async()=>{try{await request('/api/join-approval-strategies/execute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({strategy_id:button.dataset.strategyExecute})});await loadApproval()}catch(error){renderApprovalError(error)}});document.querySelectorAll('[data-strategy-delete]').forEach(button=>button.onclick=async()=>{if(!window.confirm('确定删除该自动审批策略吗？'))return;try{await request('/api/join-approval-strategies/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({strategy_id:button.dataset.strategyDelete})});await loadApproval()}catch(error){renderApprovalError(error)}})}catch(error){renderApprovalError(error)}};
    document.getElementById('load-requests').onclick=loadApproval;document.getElementById('approval-scope').onchange=loadApproval;document.getElementById('create-strategy').onclick=async()=>{const group=document.getElementById('strategy-group').value.trim()||document.getElementById('approval-scope').value;const result=document.getElementById('strategies-table');if(!group){result.innerHTML='<div class="empty">请选择群组</div>';return}try{await request('/api/join-approval-strategies',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({group_openids:[group],remark:document.getElementById('strategy-remark').value.trim(),is_enable:'on'})});document.getElementById('strategy-remark').value='';await loadApproval()}catch(error){renderApprovalError(error)}};
    const loadAuth=async()=>''',
    1,
)
ADMIN_PAGE = ADMIN_PAGE.replace(
    "await Promise.all([loadStatus(),loadPower(),loadGroups(),loadAuth(),loadSettings()])",
    "await Promise.all([loadStatus(),loadPower(),loadGroups(),loadAuth(),loadSettings()]);await loadApproval()",
    1,
)
ADMIN_PAGE = ADMIN_PAGE.replace(
    '<button data-view="approval">入群审核</button>',
    '<button data-view="approval">入群审核</button><button data-view="official-info">官方群资料</button>',
    1,
)
ADMIN_PAGE = ADMIN_PAGE.replace(
    '     <section class="view" id="approval">',
    '     <section class="view" id="official-info"><div class="panel"><div class="panel-head"><div><h2>官方群资料</h2><p>读取 QQ 官方接口返回的群信息和机器人在群内的状态。</p></div><button class="button" id="load-group-info">读取</button></div><label>选择群组<select id="official-group-scope"></select></label><pre id="official-group-result" class="hint" style="white-space:pre-wrap;margin-top:16px"></pre></div></section>\n     <section class="view" id="approval">',
    1,
)
ADMIN_PAGE = ADMIN_PAGE.replace(
    "    const loadAuth=async()=>",
    r'''    const initOfficialGroupInfo=async()=>{const select=document.getElementById('official-group-scope');const rows=await request('/api/groups');select.innerHTML=rows.map(row=>`<option value="${esc(row.scope_id)}">${esc(row.numeric_group_id||row.scope_id)}</option>`).join('')||'<option value="">暂无群组</option>'};
    const loadOfficialGroupInfo=async()=>{const scope=document.getElementById('official-group-scope').value;const result=document.getElementById('official-group-result');if(!scope){result.textContent='暂无群组';return}result.textContent='读取中...';try{const [info,state]=await Promise.all([request('/api/group-info?scope_id='+encodeURIComponent(scope)),request('/api/group-bot-state?scope_id='+encodeURIComponent(scope))]);result.textContent=[`群名称：${info.group_name||'未知'}`,`群 OpenID：${info.group_openid||scope}`,`群分类：${info.group_class_text||'未设置'}`,`群成员数：${info.group_member_num??'未知'}`,`机器人 OpenID：${state.member_openid||'未知'}`,`群内角色：${state.member_role||'未知'}`,`接收消息：${state.recv_msg_setting||'未知'}`].join('\\n')}catch(error){result.textContent=error.message}};
    document.getElementById('load-group-info').onclick=loadOfficialGroupInfo;
    const loadAuth=async()=>''',
    1,
)
ADMIN_PAGE = ADMIN_PAGE.replace(
    "await Promise.all([loadStatus(),loadPower(),loadGroups(),loadAuth(),loadSettings()]);await loadApproval()",
    "await Promise.all([loadStatus(),loadPower(),loadGroups(),loadAuth(),loadSettings()]);await initOfficialGroupInfo();await loadApproval()",
    1,
)


ADMIN_PAGE = ADMIN_PAGE.replace(
    "    const loadStatus=async()=>",
    r'''    const initialView = new URLSearchParams(location.search).get('view');
    if (initialView) { const initialButton = document.querySelector(`[data-view="${initialView}"]`); if (initialButton) initialButton.click(); }
    const loadStatus=async()=>''',
    1,
)


GROUP_PAGE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Joker QQ Admin · 分群管理</title><style>
:root{color-scheme:light;font-family:Inter,"Microsoft YaHei",sans-serif;--ink:#172033;--muted:#687386;--line:#e5e9f0;--surface:#fff;--soft:#f5f7fb;--accent:#e86d3f}*{box-sizing:border-box}body{margin:0;color:var(--ink);background:#f3f5f8}button,input,select,textarea{font:inherit}.shell{min-height:100vh}.top{background:#172033;color:#fff;padding:22px 28px;display:flex;justify-content:space-between;align-items:center;gap:15px}.top h1{font-size:20px;margin:0}.top p{font-size:12px;color:#aeb9ca;margin:6px 0 0}.top button{background:#33415b;color:#fff;border:0;border-radius:6px;padding:9px 12px;cursor:pointer}.wrap{max-width:1100px;margin:auto;padding:28px 20px}.tabs{display:flex;gap:8px;overflow:auto;margin-bottom:20px}.tabs button{border:0;background:#e5e9f0;color:#455166;border-radius:7px;padding:10px 14px;cursor:pointer}.tabs button.active{background:var(--accent);color:#fff}.view{display:none}.view.active{display:block}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:21px;margin-bottom:18px;box-shadow:0 4px 16px #17203308}.panel h2{font-size:16px;margin:0 0 6px}.muted,.hint{color:var(--muted);font-size:13px;line-height:1.6}.form{display:grid;gap:13px}label{display:grid;gap:7px;font-size:12px;color:#4f5b6d}input,select,textarea{width:100%;padding:10px;border:1px solid #d8dee8;border-radius:7px;background:#fff;color:var(--ink)}textarea{min-height:90px}.button{border:0;border-radius:7px;padding:10px 14px;background:#edf0f5;color:#344054;font-weight:600;cursor:pointer}.button.primary{background:var(--accent);color:#fff}.button.danger{background:#fff0f0;color:#a83232}.head{display:flex;justify-content:space-between;gap:15px;align-items:flex-start;margin-bottom:17px}.check-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.check{display:flex;gap:8px;align-items:center;background:var(--soft);padding:10px;border-radius:7px;font-size:13px}.check input{width:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:11px 8px;border-bottom:1px solid var(--line)}th{color:var(--muted)}.empty{text-align:center;color:var(--muted);padding:25px}@media(max-width:760px){.grid{grid-template-columns:1fr}.check-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:500px){.check-grid{grid-template-columns:1fr}table{display:block;overflow:auto;white-space:nowrap}}
</style></head><body><header class="top"><div><h1>Joker QQ Admin · 分群管理</h1><p id="group-label">正在读取群组</p></div><div><span id="user-label"></span><button id="logout">退出登录</button></div></header><main class="wrap"><nav class="tabs"><button class="active" data-view="config">群组功能</button><button data-view="replies">自动回复</button><button data-view="profile">账号资料</button></nav><section class="view active" id="config"><div class="panel"><div class="head"><div><h2>功能开关</h2><p class="muted">设置只对当前授权群生效。</p></div><button class="button primary" id="save-config">保存设置</button></div><div id="config-box"></div><p class="hint" id="config-result"></p></div><div class="grid"><div class="panel"><div class="head"><div><h2>分管管理员</h2></div></div><div class="form"><label>用户 OpenID<input id="admin-user"></label><label>显示名称<input id="admin-name"></label><button class="button" id="add-admin">添加管理员</button></div><div id="admins" style="margin-top:15px"></div></div><div class="panel"><div class="head"><div><h2>SCUM 服务器</h2></div></div><div class="form"><label>服务器 ID<input id="server-id"></label><button class="button primary" id="save-server">保存服务器绑定</button></div></div></div></section><section class="view" id="replies"><div class="panel"><div class="head"><div><h2>自动回复</h2><p class="muted">关键词匹配后在当前群回复。</p></div></div><div class="form"><label>关键词<input id="reply-trigger"></label><label>回复内容<textarea id="reply-response"></textarea></label><button class="button primary" id="add-reply">保存回复</button></div><div id="reply-list" style="margin-top:15px"></div></div></section><section class="view" id="profile"><div class="panel"><div class="head"><div><h2>账号资料</h2><p class="muted">邮箱可用于账号识别和后续通知。</p></div></div><div class="form"><label>账号<input id="profile-username" disabled></label><label>显示名称<input id="profile-name"></label><label>邮箱<input id="profile-email" type="email"></label><button class="button primary" id="save-profile">保存资料</button></div><p class="hint" id="profile-result"></p></div></section></main><script>
const request=async(u,o={})=>{const r=await fetch(u,{...o,headers:{...(o.headers||{})}});if(!r.ok)throw new Error((await r.text())||`HTTP ${r.status}`);return r.json()};const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let scope='';let config;
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.view).classList.add('active')});
const render=()=>{const list=config.features||[];document.getElementById('config-box').innerHTML=`<div class="form"><label>自动回复<select id="auto-reply"><option value="1" ${config.auto_reply_enabled?'selected':''}>开启</option><option value="0" ${config.auto_reply_enabled?'':'selected'}>关闭</option></select></label><label>SCUM 服务器 ID<input id="server-config" value="${esc(config.server_id||'')}"></label></div><div class="check-grid">${list.map(f=>`<label class="check"><input type="checkbox" data-feature="${esc(f.key)}" ${f.enabled?'checked':''}>${esc(f.label)}</label>`).join('')}</div>`;document.getElementById('admins').innerHTML=config.admins?.length?`<table><thead><tr><th>名称</th><th>OpenID</th><th></th></tr></thead><tbody>${config.admins.map(a=>`<tr><td>${esc(a.display_name)}</td><td>${esc(a.user_id)}</td><td><button class="button danger" data-remove="${esc(a.user_id)}">删除</button></td></tr>`).join('')}</tbody></table>`:'<div class="empty">暂无分管管理员</div>';document.querySelectorAll('[data-remove]').forEach(b=>b.onclick=async()=>{await request('/api/group-admins',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope_id:scope,user_id:b.dataset.remove,action:'remove'})});await loadConfig()})};
const loadConfig=async()=>{config=await request('/api/group-config?scope_id='+encodeURIComponent(scope));render()};const loadReplies=async()=>{const r=await request('/api/replies?scope_id='+encodeURIComponent(scope));document.getElementById('reply-list').innerHTML=r.length?`<table><thead><tr><th>关键词</th><th>回复</th><th></th></tr></thead><tbody>${r.map(x=>`<tr><td>${esc(x.trigger)}</td><td>${esc(x.response)}</td><td><button class="button danger" data-reply="${esc(x.trigger)}">删除</button></td></tr>`).join('')}</tbody></table>`:'<div class="empty">暂无自动回复</div>';document.querySelectorAll('[data-reply]').forEach(b=>b.onclick=async()=>{await request('/api/replies/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope_id:scope,trigger:b.dataset.reply})});await loadReplies()})};
document.getElementById('save-config').onclick=async()=>{const features={};document.querySelectorAll('[data-feature]').forEach(x=>features[x.dataset.feature]=x.checked);await request('/api/group-config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope_id:scope,features,server_id:document.getElementById('server-config').value.trim(),auto_reply_enabled:document.getElementById('auto-reply').value==='1'})});document.getElementById('config-result').textContent='已保存';await loadConfig()};document.getElementById('add-admin').onclick=async()=>{await request('/api/group-admins',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope_id:scope,user_id:document.getElementById('admin-user').value.trim(),display_name:document.getElementById('admin-name').value.trim()})});document.getElementById('admin-user').value='';document.getElementById('admin-name').value='';await loadConfig()};document.getElementById('save-server').onclick=()=>document.getElementById('save-config').click();document.getElementById('add-reply').onclick=async()=>{await request('/api/replies',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope_id:scope,trigger:document.getElementById('reply-trigger').value.trim(),response:document.getElementById('reply-response').value.trim()})});document.getElementById('reply-trigger').value='';document.getElementById('reply-response').value='';await loadReplies()};document.getElementById('save-profile').onclick=async()=>{const r=document.getElementById('profile-result');try{await request('/api/profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('profile-email').value.trim(),display_name:document.getElementById('profile-name').value.trim()})});r.textContent='资料已保存'}catch(e){r.textContent=e.message}};document.getElementById('logout').onclick=async()=>{await fetch('__LOGOUT_ENDPOINT__',{method:'POST'});location.href='/'};
(async()=>{try{const [me,groups]=await Promise.all([request('/api/profile'),request('/api/groups')]);scope=groups[0]?.scope_id||'';document.getElementById('user-label').textContent=me.display_name||me.username;document.getElementById('profile-username').value=me.username;document.getElementById('profile-name').value=me.display_name||'';document.getElementById('profile-email').value=me.email||'';document.getElementById('group-label').textContent=groups[0]?`当前群：${groups[0].numeric_group_id||groups[0].scope_id}`:'尚未绑定群组';if(scope){await Promise.all([loadConfig(),loadReplies()])}else{document.getElementById('config-box').innerHTML='<div class="empty">当前账号没有可管理的群组。</div>'}}catch(e){document.getElementById('group-label').textContent=e.message}})();
</script></body></html>"""


from dashboard_pages import (
    ADMIN_PAGE as ROLE_ADMIN_PAGE,
    AUTH_PAGE as ROLE_AUTH_PAGE,
    HOME_PAGE as ROLE_HOME_PAGE,
)
from group_dashboard_page import GROUP_PAGE as ROLE_GROUP_PAGE


# Keep the HTTP handlers in this module while keeping the role-specific UI in
# a focused module.  This prevents administrator controls from leaking into
# the customer group console.
ADMIN_PAGE = ROLE_ADMIN_PAGE
GROUP_PAGE = ROLE_GROUP_PAGE
AUTH_PAGE = ROLE_AUTH_PAGE
HOME_PAGE = ROLE_HOME_PAGE


class DashboardServer:
    def __init__(
        self,
        config: QQBotConfig,
        store: SQLiteStore,
        status: dict[str, Any],
        api: QQBotAPI,
        on_event: Callable[[str, dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.config = config
        self.store = store
        self.status = status
        self.api = api
        self.on_event = on_event
        self.admin_path = config.admin_path or config.dashboard_path or "/admin"
        if self.admin_path == "/":
            self.admin_path = "/admin"
        self.user_path = config.user_path or "/user"
        if self.user_path == "/" or self.user_path == self.admin_path:
            self.user_path = "/user"
        self.dashboard_path = self.admin_path
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        routes = [
                web.get("/", self._home),
                web.get("/login", self._login_page),
                web.post("/login", self._login),
                web.get("/register", self._register_page),
                web.post("/register", self._register),
                web.post("/logout", self._logout),
                web.post("/", self._webhook),
                web.post("/qqbot", self._webhook),
                web.get("/healthz", self._health),
                web.get("/api/status", self._status),
                web.get("/api/features", self._features),
                web.get("/api/groups", self._groups),
                web.get("/api/group-config", self._group_config),
                web.get("/api/group-info", self._group_info),
                web.get("/api/group-bot-state", self._group_bot_state),
                web.get("/api/group-members", self._group_members),
                web.get("/api/join-requests", self._join_requests),
                web.get("/api/join-approval/state", self._join_approval_state),
                web.get("/api/join-approval-strategies", self._join_approval_strategies),
                web.get("/api/messages", self._messages),
                web.get("/api/message-users", self._message_users),
                web.get("/api/keyword-rules", self._keyword_rules),
                web.get("/api/group-admins", self._group_admins),
                web.get("/api/blacklist", self._blacklist),
                web.get("/api/user-replies", self._user_replies),
                web.get("/api/schedules", self._schedules),
                web.get("/api/tasks", self._tasks),
                web.get("/api/replies", self._replies),
                web.get("/api/settings", self._settings),
                web.get("/api/owner", self._owner),
                web.get("/api/auth/me", self._auth_me),
                web.get("/api/profile", self._profile),
                web.get("/api/auth/cards", self._auth_cards),
                web.get("/api/auth/users", self._auth_users),
                web.get("/api/power", self._power),
                web.post("/api/replies", self._save_reply),
                web.post("/api/replies/delete", self._delete_reply),
                web.post("/api/group-settings", self._save_group_settings),
                web.post("/api/group-config", self._save_group_config),
                web.post("/api/join-requests/approve", self._approve_join_request),
                web.post("/api/join-approval/direct", self._set_direct_join_approval),
                web.post("/api/join-approval-strategies", self._create_join_approval_strategy),
                web.post("/api/join-approval-strategies/update", self._update_join_approval_strategy),
                web.post("/api/join-approval-strategies/delete", self._delete_join_approval_strategy),
                web.post("/api/join-approval-strategies/execute", self._execute_join_approval_strategy),
                web.post("/api/join-approval-strategies/whitelist", self._update_join_approval_whitelist),
                web.post("/api/group-admins", self._save_group_admins),
                web.post("/api/blacklist", self._save_blacklist),
                web.post("/api/keyword-rules", self._save_keyword_rule),
                web.post("/api/keyword-rules/delete", self._delete_keyword_rule),
                web.post("/api/moderation", self._moderation),
                web.post("/api/user-replies", self._save_user_reply),
                web.post("/api/user-replies/delete", self._delete_user_reply),
                web.post("/api/schedules", self._save_schedule),
                web.post("/api/schedules/delete", self._delete_schedule),
                web.post("/api/tasks", self._save_task),
                web.post("/api/tasks/delete", self._delete_task),
                web.post("/api/restart", self._restart_service),
                web.post("/api/settings", self._save_settings),
                web.post("/api/owner", self._save_owner),
                web.post("/api/profile", self._save_profile),
                web.get("/api/license/status", self._license_status),
                web.post("/api/license/redeem", self._redeem_license),
                web.post("/api/profile/password/code", self._send_profile_password_code),
                web.post("/api/profile/password/reset", self._reset_profile_password),
                web.post("/api/auth/cards", self._create_card),
                web.post("/api/auth/cards/delete", self._delete_card),
                web.post("/api/auth/groups/delete", self._delete_group_authorization),
                web.post("/api/auth/users/update", self._update_dashboard_user),
                web.post("/api/user/groups/bind", self._bind_user_group),
                web.post("/api/auth/revoke-card", self._revoke_card),
                web.post("/api/auth/revoke-user", self._revoke_user),
                web.post("/api/power", self._set_power),
        ]
        routes.extend([
            web.get(self.admin_path, self._page),
            web.get(self.admin_path + "/login", self._login_page),
            web.post(self.admin_path + "/login", self._login),
            web.post(self.admin_path + "/logout", self._logout),
            web.get(self.user_path, self._page),
            web.get(self.user_path + "/login", self._login_page),
            web.post(self.user_path + "/login", self._login),
                web.post(self.user_path + "/register/code", self._send_registration_code),
            web.get(self.user_path + "/register", self._register_page),
            web.post(self.user_path + "/register", self._register),
            web.post(self.user_path + "/logout", self._logout),
        ])
        app.add_routes(routes)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.config.dashboard_bind, self.config.dashboard_port)
        await site.start()
        logger.info("dashboard listening on %s:%s", self.config.dashboard_bind, self.config.dashboard_port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    def _current_user(self, request: web.Request) -> dict[str, Any] | None:
        supplied = request.headers.get("X-Dashboard-Token") or request.query.get("token", "")
        if self.config.dashboard_token and supplied and hmac.compare_digest(supplied, self.config.dashboard_token):
            return {"user_id": 0, "username": "token", "role": "admin", "scope_id": ""}
        session = self.store.get_dashboard_session(request.cookies.get("joker_dashboard_session", ""))
        if session:
            return session
        if not self.config.dashboard_token and not self.store.list_dashboard_users():
            return {"user_id": 0, "username": "local", "role": "admin", "scope_id": ""}
        return None

    def _authorized(self, request: web.Request) -> bool:
        return self._current_user(request) is not None

    def _require_auth(self, request: web.Request) -> web.Response | None:
        if self._authorized(request):
            return None
        return web.json_response({"error": "dashboard authentication required"}, status=401)

    def _require_admin(self, request: web.Request) -> web.Response | None:
        user = self._current_user(request)
        if user is None:
            return web.json_response({"error": "dashboard authentication required"}, status=401)
        if user.get("role") != "admin":
            return web.json_response({"error": "administrator access required"}, status=403)
        return None

    def _require_scope(self, request: web.Request, scope_id: str) -> web.Response | None:
        user = self._current_user(request)
        if user is None:
            return web.json_response({"error": "dashboard authentication required"}, status=401)
        if user.get("role") == "admin":
            return None
        if user.get("user_id") and self.store.dashboard_user_manages_scope(user["user_id"], scope_id):
            return None
        if str(user.get("scope_id", "")) == str(scope_id) and str(scope_id):
            return None
        return web.json_response({"error": "没有该群的管理权限"}, status=403)

    @staticmethod
    def _official_feature_error(error: QQBotAPIError, feature_name: str) -> str:
        """Make QQ-platform capability errors clear in the dashboard."""

        detail = str(error)
        if "11253" in detail:
            return (
                f"{feature_name}返回 QQ 官方错误码 11253：当前机器人尚未获该接口权限/白名单。"
                "这不是授权卡或网站代码错误；请在 QQ 机器人运营后台申请对应接口权限。"
            )
        if "40062003" in detail or "403" in detail:
            return f"{feature_name}执行失败：机器人需要具备该官方群的管理员权限。"
        return f"{feature_name}执行失败：{detail[:180]}"

    async def _page(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return self._auth_response(request)
        user = self._current_user(request) or {}
        expected_role = self._role_for_path(request.path)
        if expected_role and user.get("role") != expected_role:
            raise web.HTTPFound(self.admin_path if user.get("role") == "admin" else self.user_path)
        content = ADMIN_PAGE if user.get("role") == "admin" else GROUP_PAGE
        if user.get("role") != "admin":
            content = (
                content
                .replace(
                    "填写官方群 OpenID 即可绑定，不需要第二张卡密。",
                    "先让机器人在目标群记录 QQ 群号，再填写同一个群号完成绑定；不需要第二张卡密。",
                )
                .replace(
                    '<label>官方群 OpenID<input id="bind-scope" placeholder="官方群 group_openid"></label>',
                    '<label>QQ 群号<input id="bind-scope" inputmode="numeric" placeholder="例如 1102579807"></label>',
                )
                .replace(
                    "<h3>如何获取官方群 OpenID</h3><p class=\"muted\">在目标官方群内发送 <code>/获取OpenID</code>。机器人回复的第一行“群 OpenID”就是这里需要填写的值；它是 QQ 官方群标识，不是分群账号，也不是传统数字 QQ 群号。</p>",
                    "<h3>绑定步骤</h3><p class=\"muted\">1. 在目标群发送 <code>/绑定官方群 数字QQ群号</code>；2. 返回网页填写同一个 QQ 群号。需要对成员禁言、拉黑时，在群内发送 <code>/获取OpenID</code> 获取成员 OpenID。</p>",
                )
                .replace(
                    "{scope_id:document.getElementById('bind-scope').value.trim()}",
                    "{group_id:document.getElementById('bind-scope').value.trim()}",
                )
                .replace("keyword-mute-minutes", "keyword-mute-seconds")
                .replace("moderation-minutes", "moderation-seconds")
                .replace("id+'-minutes'", "id+'-seconds'")
                .replace("禁言时长（分钟）", "禁言时长（秒）")
                .replace("min=\"1\" max=\"43200\" value=\"10\"", "min=\"1\" max=\"2592000\" value=\"600\"")
                .replace("duration_minutes", "duration_seconds")
                .replace("duration_seconds||10} 分钟", "duration_seconds||600} 秒")
                .replace("加入黑名单会通过 QQ 官方接口移出成员并拉黑。", "成员仍在群内时会先移出再拉黑；若返回 11253，请先申请 QQ 官方黑名单权限。")
                .replace("命中关键词后移出成员并加入 QQ 官方群黑名单。", "命中关键词后先移出成员，再加入 QQ 官方群黑名单；接口权限不足时会保留明确报错。")
                .replace(
                    '<button id="run-moderation" class="button danger" style="margin-top:12px">执行群管操作</button><div id="moderation-result"',
                    '<div class="row-actions" style="margin-top:12px"><button id="run-moderation" class="button danger">执行群管操作</button><button id="load-members" class="button">读取官方群成员</button></div><div id="moderation-result"',
                )
                .replace(
                    '<button id="refresh-approval" class="button">刷新申请</button>',
                    '<div class="row-actions"><button id="direct-approval" class="button primary">开启直接入群</button><button id="disable-direct-approval" class="button">关闭直接入群</button><button id="refresh-approval" class="button">刷新申请</button></div>',
                )
                .replace(
                    "document.getElementById('refresh-approval').onclick=()=>loadApproval().catch(e=>out('approval-result',e.message,false));",
                    "document.getElementById('refresh-approval').onclick=()=>loadApproval().catch(e=>out('approval-result',e.message,false));document.getElementById('direct-approval').onclick=async()=>{try{await post('/api/join-approval/direct',{scope_id:scope,enabled:true});out('approval-result','已开启 QQ 官方直接入群策略')}catch(e){out('approval-result',e.message,false)}};document.getElementById('disable-direct-approval').onclick=async()=>{try{await post('/api/join-approval/direct',{scope_id:scope,enabled:false});out('approval-result','已关闭 QQ 官方直接入群策略')}catch(e){out('approval-result',e.message,false)}};",
                )
                .replace(
                    "document.getElementById('run-moderation').onclick=async()=>",
                    "document.getElementById('load-members').onclick=async()=>{try{const data=await api('/api/group-members?scope_id='+encodeURIComponent(scope));const rows=Array.isArray(data.members)?data.members:[];document.getElementById('member-openid-list').innerHTML=rows.length?`<table><thead><tr><th>成员</th><th>OpenID</th><th></th></tr></thead><tbody>${rows.map(m=>{const id=m.member_openid||m.user_openid||m.openid||'';const name=m.username||m.nick||id;return `<tr><td>${esc(name)}</td><td>${esc(id)}</td><td><button class=\"button\" data-member-select=\"${esc(id)}\">选择</button></td></tr>`}).join('')}</tbody></table>`:'<div class=\"empty\">未返回成员，可能尚未获得官方群成员接口权限。</div>';document.querySelectorAll('[data-member-select]').forEach(b=>b.onclick=()=>{document.getElementById('moderation-user').value=b.dataset.memberSelect;document.getElementById('blacklist-user').value=b.dataset.memberSelect;out('moderation-result','已选择成员 OpenID')})}catch(e){out('moderation-result',e.message,false)}};document.getElementById('run-moderation').onclick=async()=>",
                )
                .replace(
                    '<div id="moderation-result" class="result"></div>',
                    '<div id="moderation-result" class="result"></div><div id="member-openid-list" style="margin-top:14px"></div>',
                )
            )
        if user.get("role") == "admin":
            enhancement = _ADMIN_UI_ENHANCEMENT + ADMIN_UI_OVERLAY
        else:
            enhancement = _GROUP_UI_ENHANCEMENT + GROUP_UI_OVERLAY + FUNCTION_USAGE_OVERLAY
        content = content.replace("</body>", enhancement + "</body>")
        logout_path = self.admin_path if user.get("role") == "admin" else self.user_path
        content = content.replace("__LOGOUT_ENDPOINT__", logout_path + "/logout")
        return web.Response(text=content, content_type="text/html")

    async def _home(self, request: web.Request) -> web.Response:
        content = (
            HOME_PAGE.replace('使用用户注册卡创建账号', '完成注册后绑定官方群')
            .replace('输入群授权卡绑定官方群', '登录后绑定官方群')
            .replace('卡密创建时不预先绑定群。', '一张授权卡只授权一个官方群；一个账号可管理多个已授权群。')
        )
        return web.Response(
            text=content.replace("__ADMIN_PATH__", self.admin_path).replace("__USER_PATH__", self.user_path),
            content_type="text/html",
        )

    def _role_for_path(self, path: str) -> str:
        if path == self.admin_path or path.startswith(self.admin_path + "/"):
            return "admin"
        if path == self.user_path or path.startswith(self.user_path + "/"):
            return "group"
        return ""

    def _auth_response(self, request: web.Request, audience: str | None = None) -> web.Response:
        audience = audience or self._role_for_path(request.path) or "all"
        content = AUTH_PAGE
        replacements = {
            "__AUTH_AUDIENCE__": audience,
            "__ADMIN_PATH__": self.admin_path,
            "__USER_PATH__": self.user_path,
            "__LOGIN_ENDPOINT__": (self.admin_path if audience == "admin" else self.user_path) + "/login",
            "__REGISTER_ENDPOINT__": self.user_path + "/register",
            "__REGISTER_CODE_ENDPOINT__": self.user_path + "/register/code",
            "__LOGIN_LABEL__": "管理员登录" if audience == "admin" else "用户登录",
        }
        for key, value in replacements.items():
            content = content.replace(key, value)
        if audience != "admin":
            content = content.replace("</body>", AUTH_UI_OVERLAY + "</body>")
        return web.Response(text=content, content_type="text/html")

    async def _login_page(self, request: web.Request) -> web.Response:
        return self._auth_response(request)

    async def _login(self, request: web.Request) -> web.Response:
        payload = await self._json(request)
        user = self.store.authenticate_dashboard_user(
            str(payload.get("username", "")), str(payload.get("password", ""))
        )
        if not user:
            return web.json_response({"error": "账号或密码错误"}, status=401)
        expected_role = self._role_for_path(request.path)
        if expected_role and user["role"] != expected_role:
            return web.json_response({"error": "请使用对应的管理员或分群用户入口登录"}, status=403)
        token = self.store.create_dashboard_session(user["user_id"], self.config.dashboard_session_max_age)
        redirect = (self.admin_path + "?view=auth") if user["role"] == "admin" else self.user_path
        response = web.json_response({"ok": True, "role": user["role"], "redirect": redirect})
        response.set_cookie(
            "joker_dashboard_session", token,
            max_age=self.config.dashboard_session_max_age,
            httponly=True,
            samesite="Lax",
            secure=request.scheme == "https" or request.headers.get("X-Forwarded-Proto", "").lower() == "https",
        )
        return response

    async def _register_page(self, request: web.Request) -> web.Response:
        return self._auth_response(request, "group")

    def _send_registration_email(self, email: str, code: str) -> None:
        if not self.config.smtp_host:
            raise RuntimeError("管理员尚未配置 SMTP 邮箱服务")
        sender = self.config.smtp_from or self.config.smtp_username
        if not sender:
            raise RuntimeError("管理员尚未配置发件邮箱")
        message = EmailMessage()
        message["Subject"] = "Joker QQ 用户注册验证码"
        message["From"] = sender
        message["To"] = email
        message.set_content(
            f"你的 Joker QQ 用户注册验证码是：{code}\n\n"
            "验证码 10 分钟内有效，请勿转发给他人。"
        )
        context = ssl.create_default_context()
        if self.config.smtp_port == 465:
            with smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, timeout=20, context=context) as client:
                if self.config.smtp_username:
                    client.login(self.config.smtp_username, self.config.smtp_password)
                client.send_message(message)
            return
        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=20) as client:
            client.ehlo()
            if self.config.smtp_use_tls:
                client.starttls(context=context)
                client.ehlo()
            if self.config.smtp_username:
                client.login(self.config.smtp_username, self.config.smtp_password)
            client.send_message(message)

    async def _send_registration_code(self, request: web.Request) -> web.Response:
        payload = await self._json(request)
        email = str(payload.get("email", "")).strip().lower()
        try:
            code = self.store.issue_registration_email_code(email)
            await asyncio.to_thread(self._send_registration_email, email, code)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self.store.discard_registration_email_code(email)
            logger.warning("registration email delivery failed: %s", exc)
            return web.json_response({"error": "验证码发送失败，请联系管理员检查邮箱服务"}, status=502)
        return web.json_response({"ok": True, "message": "验证码已发送，10 分钟内有效"})

    async def _register(self, request: web.Request) -> web.Response:
        payload = await self._json(request)
        email = str(payload.get("email", "")).strip().lower()
        if not email:
            return web.json_response({"error": "请填写并验证邮箱"}, status=400)
        user = self.store.register_group_user(
            str(payload.get("username", "")),
            str(payload.get("password", "")),
            str(payload.get("card_code", "")),
            email,
            str(payload.get("verification_code", "")),
        )
        if not user:
            return web.json_response({"error": "注册失败：请检查邮箱验证码和账号信息"}, status=400)
        token = self.store.create_dashboard_session(user["user_id"], self.config.dashboard_session_max_age)
        response = web.json_response({"ok": True, "role": user["role"], "redirect": self.user_path})
        response.set_cookie(
            "joker_dashboard_session", token,
            max_age=self.config.dashboard_session_max_age,
            httponly=True,
            samesite="Lax",
            secure=request.scheme == "https" or request.headers.get("X-Forwarded-Proto", "").lower() == "https",
        )
        return response

    async def _logout(self, request: web.Request) -> web.Response:
        token = request.cookies.get("joker_dashboard_session", "")
        self.store.delete_dashboard_session(token)
        response = web.json_response({"ok": True})
        response.del_cookie("joker_dashboard_session")
        return response

    async def _auth_me(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        user = self._current_user(request) or {}
        payload = {
            "username": user.get("username", ""),
            "email": user.get("email", ""),
            "display_name": user.get("display_name", ""),
            "role": user.get("role", ""),
            "scope_id": user.get("scope_id", ""),
        }
        if user.get("role") == "group" and user.get("user_id"):
            payload["license"] = self.store.dashboard_user_license_status(int(user["user_id"]))
        return web.json_response(payload)

    async def _profile(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        user = self._current_user(request) or {}
        payload = {
            "username": user.get("username", ""),
            "email": user.get("email", ""),
            "display_name": user.get("display_name", ""),
            "role": user.get("role", ""),
            "scope_id": user.get("scope_id", ""),
        }
        if user.get("role") == "group" and user.get("user_id"):
            payload["license"] = self.store.dashboard_user_license_status(int(user["user_id"]))
        return web.json_response(payload)

    async def _save_profile(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        user = self._current_user(request) or {}
        if not user.get("user_id"):
            return web.json_response({"error": "令牌登录不能修改账号资料"}, status=403)
        payload = await self._json(request)
        email = str(payload.get("email", "")).strip().lower()
        display_name = str(payload.get("display_name", "")).strip()
        if email and ("@" not in email or len(email) > 320):
            return web.json_response({"error": "邮箱格式不正确"}, status=400)
        if not self.store.update_dashboard_user_profile(user["user_id"], email, display_name):
            return web.json_response({"error": "邮箱已被其他账号使用"}, status=409)
        return web.json_response({"ok": True})

    async def _license_status(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        return web.json_response(
            {"error": "授权状态按群查看，请在“我的群”或群内使用 /授权状态。"},
            status=400,
        )

    async def _redeem_license(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        return web.json_response(
            {"error": "授权卡只授权官方群，不兑换到账号。请在“绑定群授权”中填写目标 QQ 群号和授权卡密。"},
            status=400,
        )

    async def _send_profile_password_code(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        user = self._current_user(request) or {}
        if user.get("role") != "group" or not user.get("user_id") or not user.get("email"):
            return web.json_response({"error": "请先在账号资料中保存有效邮箱"}, status=400)
        email = str(user["email"]).strip().lower()
        try:
            code = self.store.issue_registration_email_code(email)
            await asyncio.to_thread(self._send_registration_email, email, code)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self.store.discard_registration_email_code(email)
            logger.warning("password reset email delivery failed: %s", exc)
            return web.json_response({"error": "验证码发送失败，请联系管理员检查邮箱服务"}, status=502)
        return web.json_response({"ok": True, "message": "验证码已发送，10 分钟内有效"})

    async def _reset_profile_password(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        user = self._current_user(request) or {}
        if user.get("role") != "group" or not user.get("user_id") or not user.get("email"):
            return web.json_response({"error": "请先在账号资料中保存有效邮箱"}, status=400)
        payload = await self._json(request)
        if not self.store.reset_dashboard_user_password_from_email(
            int(user["user_id"]),
            str(user["email"]),
            str(payload.get("verification_code", "")),
            str(payload.get("password", "")),
        ):
            return web.json_response({"error": "验证码或新密码无效"}, status=400)
        return web.json_response({"ok": True})

    async def _auth_cards(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        return web.json_response(self.store.list_access_cards())

    async def _auth_users(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        users = self.store.list_dashboard_users()
        managers_by_scope: dict[str, list[str]] = {}
        for item in users:
            if item.get("role") == "group":
                item["groups"] = self.store.list_dashboard_user_groups(int(item["user_id"]))
                for group in item["groups"]:
                    scope_id = str(group.get("scope_id", "")).strip()
                    if scope_id:
                        managers_by_scope.setdefault(scope_id, []).append(
                            str(item.get("username") or item.get("display_name") or item["user_id"])
                        )
        scope_data = {str(item["scope_id"]): item for item in self.store.list_scopes()}
        group_authorizations = []
        for authorization in self.store.list_group_authorizations():
            scope_id = str(authorization["scope_id"])
            item = dict(authorization)
            item.update(scope_data.get(scope_id, {}))
            item["managers"] = managers_by_scope.get(scope_id, [])
            status = self.store.group_authorization_status(scope_id)
            item["active"] = bool(status and status.get("enabled"))
            item["status"] = "有效" if item["active"] else ("已过期" if status else "已撤销")
            group_authorizations.append(item)
        return web.json_response({
            "dashboard_users": users,
            "bot_authorizations": self.store.list_bot_authorizations(),
            "group_authorizations": group_authorizations,
        })

    async def _create_card(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        payload = await self._json(request)
        kind = "license"
        scope_id = ""
        try:
            max_uses = int(payload.get("max_uses", 1))
            days = int(payload.get("days", 30))
            raw_expires_at = payload.get("expires_at")
            expires_at = int(raw_expires_at) if raw_expires_at not in (None, "") else None
            code = self.store.create_access_card(kind, scope_id, max_uses, days, expires_at=expires_at)
        except (TypeError, ValueError) as exc:
            return web.json_response({"error": f"卡密参数无效：{exc}"}, status=400)
        return web.json_response({"ok": True, "card_code": code})

    async def _revoke_card(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        payload = await self._json(request)
        code = str(payload.get("card_code", "")).strip()
        if not code:
            return web.json_response({"error": "card_code is required"}, status=400)
        deleted = self.store.delete_access_card(code)
        if not deleted:
            return web.json_response({"error": "授权卡不存在或已删除"}, status=404)
        return web.json_response({"ok": True})

    async def _delete_card(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        payload = await self._json(request)
        code = str(payload.get("card_code", "")).strip()
        if not code:
            return web.json_response({"error": "card_code is required"}, status=400)
        deleted = self.store.delete_access_card(code)
        if not deleted:
            return web.json_response({"error": "授权卡不存在或已删除"}, status=404)
        return web.json_response({"ok": True})

    async def _delete_group_authorization(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        deleted = self.store.delete_group_authorization(scope_id)
        if not deleted:
            return web.json_response({"error": "授权群组不存在或已删除"}, status=404)
        return web.json_response({"ok": True, "message": "已撤销该群授权，原授权卡不会恢复使用次数"})

    async def _update_dashboard_user(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        payload = await self._json(request)
        try:
            user_id = int(payload.get("user_id", 0))
        except (TypeError, ValueError):
            user_id = 0
        if user_id <= 0:
            return web.json_response({"error": "用户无效"}, status=400)
        changed = self.store.update_dashboard_user_by_admin(
            user_id,
            username=payload.get("username") if "username" in payload else None,
            email=payload.get("email") if "email" in payload else None,
            display_name=payload.get("display_name") if "display_name" in payload else None,
            password=str(payload.get("password", "")),
            enabled=bool(payload["enabled"]) if "enabled" in payload else None,
        )
        if not changed:
            return web.json_response({"error": "没有可更新的用户，或不能修改管理员账号"}, status=400)
        return web.json_response({"ok": True})

    async def _bind_user_group(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        user = self._current_user(request) or {}
        if user.get("role") != "group" or not user.get("user_id"):
            return web.json_response({"error": "只有分群用户可以绑定群授权"}, status=403)
        payload = await self._json(request)
        requested_scope = str(
            payload.get("group_id") or payload.get("numeric_group_id") or payload.get("scope_id", "")
        ).strip()
        if not requested_scope:
            return web.json_response({"error": "请填写 QQ 群号"}, status=400)
        scope_id = requested_scope
        numeric_group_id = ""
        if requested_scope.isdigit():
            numeric_group_id = requested_scope
            scope_id = self.store.find_official_group_openid(numeric_group_id) or ""
            if not scope_id:
                return web.json_response(
                    {
                        "error": (
                            "尚未识别到这个 QQ 群号。请先在目标官方群内发送："
                            f"/绑定官方群 {numeric_group_id}，再回到网页绑定。"
                        )
                    },
                    status=400,
                )
        result = self.store.bind_group_authorization(
            int(user["user_id"]), scope_id, str(payload.get("card_code", ""))
        )
        if not result:
            return web.json_response({"error": "授权卡无效、已过期、已用于其他群，或该官方群已绑定其他用户"}, status=400)
        if result.get("error"):
            return web.json_response({"error": result["error"]}, status=400)
        return web.json_response({"ok": True, "numeric_group_id": numeric_group_id, **result})

    async def _revoke_user(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        payload = await self._json(request)
        user_openid = str(payload.get("user_openid", "")).strip()
        if not user_openid:
            return web.json_response({"error": "user_openid is required"}, status=400)
        return web.json_response({"ok": self.store.revoke_bot_authorization(user_openid)})

    async def _power(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        return web.json_response({
            "enabled": self.store.get_setting("__global__", "bot_enabled", "1") == "1"
        })

    async def _set_power(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        payload = await self._json(request)
        enabled = bool(payload.get("enabled"))
        self.store.set_setting("__global__", "bot_enabled", "1" if enabled else "0")
        return web.json_response({"ok": True, "enabled": enabled})

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
        user = self._current_user(request) or {}
        groups = self.store.list_scopes() if user.get("role") == "admin" else self.store.list_dashboard_user_groups(
            int(user.get("user_id") or 0), include_inactive=False
        )
        return web.json_response(groups)

    async def _group_config(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        configurable = [
            feature for feature in FEATURES
            if feature.key not in {"basic_commands", "identity", "group_settings"}
        ]
        return web.json_response(
            {
                "scope_id": scope_id,
                "features": [
                    {
                        "key": feature.key,
                        "label": feature.label,
                        "enabled": self.store.feature_enabled(scope_id, feature.key),
                    }
                    for feature in configurable
                ],
                "server_id": self.store.get_server(scope_id) or "",
                "auto_reply_enabled": self.store.get_setting(scope_id, "auto_reply_enabled", "1") == "1",
                "admins": self.store.list_group_admins(scope_id),
                "schedules": self.store.list_scheduled_messages(scope_id),
                "blacklist": [
                    {"user_id": user_id, "reason": reason}
                    for user_id, reason in self.store.list_blacklist(scope_id)
                ],
            }
        )

    async def _group_info(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        try:
            return web.json_response(await self.api.get_group_info(scope_id))
        except QQBotAPIError as exc:
            return web.json_response({"error": str(exc), "official": True}, status=502)

    async def _group_bot_state(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        try:
            return web.json_response(await self.api.get_group_bot_state(scope_id))
        except QQBotAPIError as exc:
            return web.json_response({"error": str(exc), "official": True}, status=502)

    async def _group_members(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id 必填"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        try:
            if request.query.get("all", "").strip().lower() in {"1", "true", "yes"}:
                return web.json_response(
                    {
                        "members": await self._list_all_group_members(scope_id),
                        "next_cursor": "",
                    }
                )
            payload = await self.api.get_group_members(
                scope_id, cursor=request.query.get("cursor", "").strip()
            )
        except QQBotAPIError as exc:
            return web.json_response(
                {"error": self._official_feature_error(exc, "官方群成员接口"), "official": True},
                status=502,
            )
        members = payload.get("members")
        return web.json_response(
            {
                "members": members if isinstance(members, list) else [],
                "next_cursor": str(payload.get("next_cursor", "") or ""),
            }
        )

    async def _list_all_group_members(self, scope_id: str) -> list[dict[str, Any]]:
        members: list[dict[str, Any]] = []
        cursor = ""
        seen_cursors: set[str] = set()
        seen_members: set[str] = set()
        while True:
            payload = await self.api.get_group_members(scope_id, cursor=cursor)
            rows = payload.get("members")
            if isinstance(rows, list):
                for item in rows:
                    if not isinstance(item, dict):
                        continue
                    member_openid = str(
                        item.get("member_openid") or item.get("user_openid") or item.get("openid") or ""
                    ).strip()
                    if member_openid and member_openid not in seen_members:
                        members.append(item)
                        seen_members.add(member_openid)
            next_cursor = str(payload.get("next_cursor", "") or "").strip()
            if not next_cursor or next_cursor in seen_cursors or len(members) >= 5000:
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        return members

    async def _resolve_member_openid(self, scope_id: str, value: str) -> str:
        """Resolve a numeric QQ value when the official member payload exposes it."""

        candidate = str(value or "").strip()
        if not candidate or not candidate.isdigit():
            return candidate
        for item in await self._list_all_group_members(scope_id):
            member_openid = str(
                item.get("member_openid") or item.get("user_openid") or item.get("openid") or ""
            ).strip()
            known_numbers = {
                str(item.get(key, "")).strip()
                for key in ("qq", "qq_number", "user_id", "member_id", "uin")
                if str(item.get(key, "")).strip()
            }
            if member_openid and candidate in known_numbers:
                return member_openid
        return candidate

    async def _member_display_name(self, scope_id: str, member_openid: str) -> str:
        try:
            data = await self.api.get_group_member(scope_id, member_openid)
        except QQBotAPIError:
            return member_openid
        return str(
            data.get("username") or data.get("nick") or data.get("nickname") or member_openid
        ).strip() or member_openid

    async def _join_requests(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        try:
            return web.json_response(
                await self.api.list_join_requests(
                    scope_id,
                    cursor=request.query.get("cursor", "").strip(),
                    limit=int(request.query.get("limit", "50")),
                )
            )
        except (QQBotAPIError, ValueError) as exc:
            return web.json_response({"error": str(exc), "official": True}, status=502)

    async def _approve_join_request(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        member_openid = str(payload.get("member_openid", "")).strip()
        operation = str(payload.get("operation", "")).strip().lower()
        if not scope_id or not member_openid or operation not in {"approve", "decline"}:
            return web.json_response({"error": "scope_id、member_openid 和 operation 必填"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        try:
            await self.api.approve_join_request(
                scope_id,
                member_openid,
                operation=operation,
                join_request_id=str(payload.get("join_request_id", "")).strip(),
                reject_reason=str(payload.get("reject_reason", "")).strip(),
                add_to_member_blacklist=bool(payload.get("add_to_member_blacklist")),
            )
        except QQBotAPIError as exc:
            return web.json_response({"error": str(exc), "official": True}, status=502)
        return web.json_response({"ok": True})

    async def _set_direct_join_approval(self, request: web.Request) -> web.Response:
        """Enable or disable the official QQ direct-approval strategy for one group."""

        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        enabled = bool(payload.get("enabled"))
        if not scope_id:
            return web.json_response({"error": "scope_id 必填"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        strategy_key = "join_approval_direct_strategy_id"
        strategy_id = self.store.get_setting(scope_id, strategy_key, "")
        try:
            if enabled and not strategy_id:
                numeric_group_id = self.store.get_official_group_binding(scope_id)
                result = await self.api.create_join_approval_strategy(
                    group_openids=[scope_id],
                    group_ids=None,
                    is_enable="on",
                    remark="Joker：直接入群",
                )
                strategy_id = str(result.get("strategy_id", "")).strip()
                if not strategy_id:
                    return web.json_response({"error": "QQ 官方未返回自动审批策略 ID"}, status=502)
                self.store.set_setting(scope_id, strategy_key, strategy_id)
            elif strategy_id:
                if enabled:
                    await self.api.update_join_approval_strategy(
                        strategy_id,
                        is_enable="on",
                        group_operation="add",
                        group_openids=[scope_id],
                    )
                else:
                    await self.api.update_join_approval_strategy(
                        strategy_id,
                        is_enable="off",
                    )
            elif not enabled:
                self.store.set_setting(scope_id, "join_approval_mode", "manual")
                return web.json_response({"ok": True, "enabled": False})
        except QQBotAPIError as exc:
            return web.json_response(
                {"error": self._official_feature_error(exc, "官方直接入群策略"), "official": True},
                status=502,
            )
        self.store.set_setting(scope_id, "join_approval_mode", "direct" if enabled else "manual")
        return web.json_response({"ok": True, "enabled": enabled, "strategy_id": strategy_id})

    async def _join_approval_strategies(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        try:
            return web.json_response(
                await self.api.list_join_approval_strategies(
                    cursor=request.query.get("cursor", "").strip(),
                    limit=int(request.query.get("limit", "50")),
                )
            )
        except (QQBotAPIError, ValueError) as exc:
            return web.json_response({"error": str(exc), "official": True}, status=502)

    async def _join_approval_state(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        strategy_id = self.store.get_setting(scope_id, "join_approval_direct_strategy_id", "")
        numeric_group_id = self.store.get_official_group_binding(scope_id) or ""
        try:
            data = await self.api.list_join_approval_strategies(limit=50)
        except QQBotAPIError as exc:
            return web.json_response(
                {"error": self._official_feature_error(exc, "官方入群审核策略"), "official": True},
                status=502,
            )
        strategies = data.get("list") if isinstance(data, dict) else []
        if not isinstance(strategies, list):
            strategies = data.get("strategies", []) if isinstance(data, dict) else []
        matched: list[dict[str, Any]] = []
        for item in strategies:
            if not isinstance(item, dict):
                continue
            groups = item.get("group_openids") or item.get("group_ids") or []
            groups = groups if isinstance(groups, list) else [groups]
            values = {str(value).strip() for value in groups if str(value).strip()}
            item_id = str(item.get("strategy_id") or item.get("id") or "").strip()
            if item_id == strategy_id or not values or scope_id in values or str(numeric_group_id) in values:
                matched.append(item)
        enabled = self.store.get_setting(scope_id, "join_approval_mode", "manual") == "direct"
        return web.json_response({"enabled": enabled, "strategy_id": strategy_id, "strategies": matched})

    async def _create_join_approval_strategy(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        payload = await self._json(request)
        group_openids = [str(item).strip() for item in payload.get("group_openids", []) if str(item).strip()]
        group_ids = [str(item).strip() for item in payload.get("group_ids", []) if str(item).strip()]
        try:
            result = await self.api.create_join_approval_strategy(
                group_openids=group_openids or None,
                group_ids=group_ids or None,
                is_enable=str(payload.get("is_enable", "on")),
                expire_at=str(payload.get("expire_at", "")).strip(),
                remark=str(payload.get("remark", "")).strip(),
            )
        except QQBotAPIError as exc:
            return web.json_response({"error": str(exc), "official": True}, status=502)
        return web.json_response(result)

    async def _update_join_approval_strategy(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        payload = await self._json(request)
        strategy_id = str(payload.get("strategy_id", "")).strip()
        if not strategy_id:
            return web.json_response({"error": "strategy_id is required"}, status=400)
        group_openids = [str(item).strip() for item in payload.get("group_openids", []) if str(item).strip()]
        group_ids = [str(item).strip() for item in payload.get("group_ids", []) if str(item).strip()]
        try:
            result = await self.api.update_join_approval_strategy(
                strategy_id,
                is_enable=str(payload.get("is_enable", "")).strip(),
                expire_at=str(payload.get("expire_at", "")).strip(),
                group_operation=str(payload.get("group_operation", "")).strip(),
                group_openids=group_openids or None,
                group_ids=group_ids or None,
                remark=str(payload.get("remark", "")).strip(),
            )
        except QQBotAPIError as exc:
            return web.json_response({"error": str(exc), "official": True}, status=502)
        return web.json_response(result)

    async def _delete_join_approval_strategy(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        payload = await self._json(request)
        strategy_id = str(payload.get("strategy_id", "")).strip()
        if not strategy_id:
            return web.json_response({"error": "strategy_id is required"}, status=400)
        try:
            await self.api.delete_join_approval_strategy(strategy_id)
        except QQBotAPIError as exc:
            return web.json_response({"error": str(exc), "official": True}, status=502)
        return web.json_response({"ok": True})

    async def _execute_join_approval_strategy(self, request: web.Request) -> web.Response:
        payload = await self._json(request)
        strategy_id = str(payload.get("strategy_id", "")).strip()
        scope_id = str(payload.get("scope_id", "")).strip()
        denied = self._require_scope(request, scope_id) if scope_id else self._require_admin(request)
        if denied:
            return denied
        if not strategy_id:
            return web.json_response({"error": "strategy_id is required"}, status=400)
        try:
            await self.api.execute_join_approval_strategy(strategy_id)
        except QQBotAPIError as exc:
            return web.json_response({"error": str(exc), "official": True}, status=502)
        return web.json_response({"ok": True})

    async def _update_join_approval_whitelist(self, request: web.Request) -> web.Response:
        payload = await self._json(request)
        strategy_id = str(payload.get("strategy_id", "")).strip()
        scope_id = str(payload.get("scope_id", "")).strip()
        denied = self._require_scope(request, scope_id) if scope_id else self._require_admin(request)
        if denied:
            return denied
        operation = str(payload.get("operation", "")).strip().lower()
        whitelist_users = [str(item).strip() for item in payload.get("whitelist_users", []) if str(item).strip()]
        if not strategy_id or operation not in {"add", "del"} or not whitelist_users:
            return web.json_response({"error": "strategy_id、operation 和 whitelist_users 必填"}, status=400)
        try:
            result = await self.api.update_join_approval_whitelist(
                strategy_id, operation=operation, whitelist_users=whitelist_users
            )
        except QQBotAPIError as exc:
            return web.json_response({"error": str(exc), "official": True}, status=502)
        return web.json_response(result)

    async def _blacklist(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        try:
            payload = await self.api.get_group_blacklist(scope_id)
        except QQBotAPIError as exc:
            return web.json_response(
                {"error": self._official_feature_error(exc, "官方黑名单接口"), "official": True},
                status=502,
            )
        raw = payload.get("member_openids")
        if not isinstance(raw, list):
            raw = payload.get("members")
        if not isinstance(raw, list):
            raw = payload.get("blacklist")
        if not isinstance(raw, list):
            raw = payload.get("users")
        known_reasons = dict(self.store.list_blacklist(scope_id))
        result: list[dict[str, str]] = []
        for item in raw if isinstance(raw, list) else []:
            if isinstance(item, dict):
                user_id = item.get("member_openid") or item.get("openid") or item.get("user_openid")
            else:
                user_id = item
            user_id = str(user_id or "").strip()
            if user_id and not any(row["user_id"] == user_id for row in result):
                result.append({"user_id": user_id, "reason": known_reasons.get(user_id, "")})
        return web.json_response(result)

    async def _save_blacklist(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        user_id = str(payload.get("user_id", "")).strip()
        action = str(payload.get("action", "add")).strip().lower()
        reason = str(payload.get("reason", "")).strip()[:500]
        if not scope_id or not user_id:
            return web.json_response({"error": "scope_id and user_id are required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        user_id = await self._resolve_member_openid(scope_id, user_id)
        try:
            if action == "remove":
                result = await self.api.update_group_blacklist(
                    scope_id,
                    operation="del",
                    member_openids=[user_id],
                )
                failed = result.get("fail_openids") if isinstance(result, dict) else None
                if isinstance(failed, list) and user_id in {str(item).strip() for item in failed}:
                    return web.json_response({"error": "官方接口未移出该用户"}, status=502)
                self.store.remove_blacklist(scope_id, user_id)
            else:
                await self.api.remove_group_members(scope_id, [user_id])
                result = await self.api.update_group_blacklist(
                    scope_id,
                    operation="add",
                    member_openids=[user_id],
                )
                failed = result.get("fail_openids") if isinstance(result, dict) else None
                if isinstance(failed, list) and user_id in {str(item).strip() for item in failed}:
                    return web.json_response({"error": "成员已移出群聊，但 QQ 官方接口未加入黑名单"}, status=502)
                self.store.add_blacklist(scope_id, user_id, reason)
        except QQBotAPIError as exc:
            return web.json_response(
                {"error": self._official_feature_error(exc, "官方黑名单接口"), "official": True},
                status=502,
            )
        return web.json_response({"ok": True})

    async def _save_group_config(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        valid_keys = {
            feature.key for feature in FEATURES
            if feature.key not in {"basic_commands", "identity", "group_settings"}
        }
        features = payload.get("features")
        if isinstance(features, dict):
            for key, enabled in features.items():
                if key in valid_keys:
                    self.store.set_feature_enabled(scope_id, key, bool(enabled))
        server_id = str(payload.get("server_id", "")).strip()
        if server_id:
            self.store.bind_server(scope_id, server_id)
        else:
            self.store.unbind_server(scope_id)
        if "auto_reply_enabled" in payload:
            self.store.set_setting(scope_id, "auto_reply_enabled", "1" if payload["auto_reply_enabled"] else "0")
        return web.json_response({"ok": True})

    async def _messages(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        try:
            limit = int(request.query.get("limit", "100"))
        except ValueError:
            limit = 100
        return web.json_response(self.store.list_message_records(scope_id, limit))

    async def _message_users(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        try:
            limit = int(request.query.get("limit", "200"))
        except ValueError:
            limit = 200
        return web.json_response(self.store.list_message_users(scope_id, limit))

    async def _keyword_rules(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        action = request.query.get("action", "").strip().lower()
        if action not in {"", "mute", "kick", "blacklist"}:
            return web.json_response({"error": "action is invalid"}, status=400)
        return web.json_response(self.store.list_keyword_rules(scope_id, action))

    async def _save_keyword_rule(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        action = str(payload.get("action", "")).strip().lower()
        trigger = str(payload.get("trigger", "")).strip()[:128]
        if not scope_id or action not in {"mute", "kick", "blacklist"} or not trigger:
            return web.json_response({"error": "scope_id、action 和 trigger 必填"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        try:
            duration = int(payload.get("duration_seconds", 600))
        except (TypeError, ValueError):
            duration = 600
        if action == "mute" and not 1 <= duration <= 2_592_000:
            return web.json_response({"error": "禁言时长需为 1 到 2592000 秒"}, status=400)
        self.store.save_keyword_rule(scope_id, action, trigger, duration)
        return web.json_response({"ok": True})

    async def _delete_keyword_rule(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        try:
            rule_id = int(payload.get("rule_id", 0))
        except (TypeError, ValueError):
            rule_id = 0
        if not scope_id or rule_id <= 0:
            return web.json_response({"error": "scope_id 和 rule_id 必填"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        return web.json_response({"ok": self.store.delete_keyword_rule(scope_id, rule_id)})

    async def _moderation(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        action = str(payload.get("action", "")).strip().lower()
        user_id = str(payload.get("user_id", "")).strip()
        if not scope_id or action not in {
            "mute", "unmute", "mute_all", "unmute_all", "kick", "blacklist", "recall_user"
        }:
            return web.json_response({"error": "scope_id 或 action 无效"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        user_id = await self._resolve_member_openid(scope_id, user_id)
        try:
            if action in {"mute_all", "unmute_all"}:
                members = await self._list_all_group_members(scope_id)
                member_ids = [
                    str(
                        item.get("member_openid")
                        or item.get("user_openid")
                        or item.get("openid")
                        or ""
                    ).strip()
                    for item in members
                    if isinstance(item, dict)
                    and str(
                        item.get("member_openid") or item.get("user_openid") or item.get("openid") or ""
                    ).strip()
                    and str(item.get("member_role", "member")).lower()
                    not in {"owner", "admin", "administrator", "bot"}
                    and not bool(item.get("bot") or item.get("is_bot"))
                ]
                if not member_ids:
                    return web.json_response({"error": "未找到可操作的普通群成员"}, status=400)
                operation = "add" if action == "mute_all" else "del"
                mute_expire_at = ""
                if operation == "add":
                    try:
                        seconds = int(payload.get("duration_seconds", 600))
                    except (TypeError, ValueError):
                        seconds = 600
                    if not 1 <= seconds <= 2_592_000:
                        return web.json_response({"error": "禁言时长需为 1 到 2592000 秒"}, status=400)
                    mute_expire_at = (
                        datetime.now(timezone.utc) + timedelta(seconds=seconds)
                    ).isoformat(timespec="seconds").replace("+00:00", "Z")
                for offset in range(0, len(member_ids), 20):
                    await self.api.set_group_members_mute(
                        scope_id,
                        member_ids[offset:offset + 20],
                        operation=operation,
                        mute_expire_at=mute_expire_at,
                    )
                return web.json_response(
                    {
                        "ok": True,
                        "processed": len(member_ids),
                        "message": f"已{'禁言' if operation == 'add' else '解除禁言'} {len(member_ids)} 名普通成员",
                    }
                )
            if not user_id:
                return web.json_response({"error": "请填写成员 QQ号或官方 OpenID"}, status=400)
            if action == "recall_user":
                try:
                    limit = int(payload.get("recall_limit", 20))
                except (TypeError, ValueError):
                    limit = 20
                records = self.store.list_user_message_records(scope_id, user_id, limit)
                if not records:
                    return web.json_response({"error": "没有找到该成员可撤回的已记录消息"}, status=400)
                now = datetime.now(timezone.utc)
                eligible_records: list[dict[str, str]] = []
                expired = 0
                for record in records:
                    try:
                        created_at = datetime.fromisoformat(
                            record["created_at"].replace("Z", "+00:00")
                        )
                    except (KeyError, TypeError, ValueError):
                        eligible_records.append(record)
                        continue
                    if now - created_at <= timedelta(minutes=2):
                        eligible_records.append(record)
                    else:
                        expired += 1
                if not eligible_records:
                    return web.json_response(
                        {"error": "该成员已记录消息均超过 2 分钟，QQ 官方接口无法撤回"},
                        status=400,
                    )
                recalled = 0
                failures: list[str] = []
                for record in eligible_records:
                    try:
                        await self.api.delete_group_message(scope_id, record["message_id"])
                        self.store.mark_message_recalled(scope_id, record["message_id"])
                        recalled += 1
                    except QQBotAPIError as exc:
                        failures.append(str(exc))
                if not recalled and failures:
                    raise QQBotAPIError(failures[0])
                member_name = await self._member_display_name(scope_id, user_id)
                return web.json_response(
                    {
                        "ok": recalled > 0,
                        "recalled": recalled,
                        "failed": len(failures),
                        "message": (
                            f"已请求撤回 {member_name} 的 {recalled} 条消息"
                            + (f"，{expired} 条超时跳过" if expired else "")
                            + (f"，{len(failures)} 条未撤回" if failures else "")
                        ),
                    }
                )
            if action in {"mute", "unmute"}:
                if action == "unmute":
                    await self.api.set_group_member_mute(scope_id, user_id, operation="del")
                else:
                    try:
                        seconds = int(payload.get("duration_seconds", 600))
                    except (TypeError, ValueError):
                        seconds = 600
                    if not 1 <= seconds <= 2_592_000:
                        return web.json_response({"error": "禁言时长需为 1 到 2592000 秒"}, status=400)
                    expire_at = (
                        datetime.now(timezone.utc) + timedelta(seconds=seconds)
                    ).isoformat(timespec="seconds").replace("+00:00", "Z")
                    await self.api.set_group_member_mute(
                        scope_id, user_id, operation="add", mute_expire_at=expire_at
                    )
            elif action == "kick":
                await self.api.remove_group_members(scope_id, [user_id])
            else:
                await self.api.remove_group_members(scope_id, [user_id])
                result = await self.api.update_group_blacklist(
                    scope_id, operation="add", member_openids=[user_id]
                )
                failed = result.get("fail_openids") if isinstance(result, dict) else None
                if isinstance(failed, list) and user_id in {str(item).strip() for item in failed}:
                    return web.json_response({"error": "成员已移出群聊，但 QQ 官方接口未加入黑名单"}, status=502)
                self.store.add_blacklist(scope_id, user_id, "网页群管操作")
        except QQBotAPIError as exc:
            feature = "官方黑名单接口" if action == "blacklist" else "官方群管接口"
            return web.json_response(
                {"error": self._official_feature_error(exc, feature), "official": True}, status=502
            )
        member_name = await self._member_display_name(scope_id, user_id)
        action_labels = {"mute": "已禁言", "unmute": "已解除禁言", "kick": "已踢出群聊", "blacklist": "已移出并加入黑名单"}
        return web.json_response({"ok": True, "message": f"{action_labels.get(action, '操作完成')}：{member_name}"})

    async def _group_admins(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        return web.json_response(self.store.list_group_admins(scope_id))

    async def _save_group_admins(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        user_id = str(payload.get("user_id", "")).strip()
        if not scope_id or not user_id:
            return web.json_response({"error": "scope_id and user_id are required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        user_id = await self._resolve_member_openid(scope_id, user_id)
        if str(payload.get("action", "add")) == "remove":
            return web.json_response({"ok": self.store.remove_group_admin(scope_id, user_id)})
        self.store.add_group_admin(scope_id, user_id, str(payload.get("display_name", "")).strip())
        return web.json_response({"ok": True})

    async def _user_replies(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        user_id = request.query.get("user_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        return web.json_response(self.store.list_user_replies(scope_id, user_id))

    async def _save_user_reply(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        user_id = str(payload.get("user_id", "")).strip()
        trigger = str(payload.get("trigger", "")).strip()
        response = str(payload.get("response", "")).strip()
        match_mode = str(payload.get("match_mode", "exact")).strip().lower()
        if not all((scope_id, user_id, trigger, response)):
            return web.json_response({"error": "scope_id, user_id, trigger and response are required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        user_id = await self._resolve_member_openid(scope_id, user_id)
        self.store.save_user_reply(scope_id, user_id, trigger, response, match_mode)
        return web.json_response({"ok": True})

    async def _delete_user_reply(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        user_id = str(payload.get("user_id", "")).strip()
        trigger = str(payload.get("trigger", "")).strip()
        if not all((scope_id, user_id, trigger)):
            return web.json_response({"error": "scope_id, user_id and trigger are required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        return web.json_response({"ok": self.store.delete_user_reply(scope_id, user_id, trigger)})

    async def _schedules(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if scope_id:
            denied = self._require_scope(request, scope_id)
            if denied:
                return denied
        return web.json_response(self.store.list_scheduled_messages(scope_id))

    async def _tasks(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        return web.json_response(self.store.list_scheduled_tasks(scope_id))

    async def _save_task(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        task_type = str(payload.get("task_type", "")).strip().lower()
        content = str(payload.get("content", "")).strip()
        try:
            run_at = int(payload.get("run_at", 0))
            mute_seconds = int(payload.get("mute_seconds", 0))
        except (TypeError, ValueError):
            return web.json_response({"error": "定时任务时间或禁言时长无效"}, status=400)
        if not scope_id:
            return web.json_response({"error": "请选择官方群"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        try:
            task_id = self.store.create_scheduled_task(
                scope_id, task_type, run_at, content=content, mute_seconds=mute_seconds
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"ok": True, "task_id": task_id})

    async def _delete_task(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        try:
            task_id = int(payload.get("task_id", 0))
        except (TypeError, ValueError):
            task_id = 0
        if not scope_id or task_id <= 0:
            return web.json_response({"error": "任务参数无效"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        return web.json_response({"ok": self.store.delete_scheduled_task(task_id, scope_id)})

    async def _save_schedule(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        content = str(payload.get("content", "")).strip()
        try:
            interval_minutes = int(payload.get("interval_minutes", 0))
        except (TypeError, ValueError):
            interval_minutes = 0
        if not scope_id or not content or not 1 <= interval_minutes <= 525600:
            return web.json_response({"error": "群组、消息和间隔分钟数不能为空"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        schedule_id = self.store.create_scheduled_message(scope_id, content, interval_minutes * 60)
        return web.json_response({"ok": True, "schedule_id": schedule_id})

    async def _delete_schedule(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        try:
            schedule_id = int(payload.get("schedule_id", 0))
        except (TypeError, ValueError):
            schedule_id = 0
        scope_id = str(payload.get("scope_id", "")).strip()
        if schedule_id <= 0:
            return web.json_response({"error": "schedule_id is required"}, status=400)
        if scope_id:
            denied = self._require_scope(request, scope_id)
            if denied:
                return denied
        return web.json_response({"ok": self.store.delete_scheduled_message(schedule_id, scope_id)})

    async def _settings(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        values = read_env_file()
        api_base_url = values.get("QQBOT_API_BASE", self.config.api_base_url)
        if api_base_url == "https://api.sgroup.qq.com":
            api_base_url = self.config.api_base_url
        admin_path = values.get("JOKER_ADMIN_PATH", values.get("JOKER_DASHBOARD_PATH", self.admin_path)) or self.admin_path
        if admin_path == "/":
            admin_path = "/admin"
        user_path = values.get("JOKER_USER_PATH", self.user_path) or self.user_path
        return web.json_response(
            {
                "app_id": values.get("QQBOT_APP_ID", self.config.app_id),
                "api_base_url": api_base_url,
                "transport": values.get("QQBOT_TRANSPORT", self.config.transport),
                "scum_relay_url": values.get("SCUM_RELAY_URL", self.config.scum_relay_url),
                "portal_url": values.get("JOKER_PORTAL_URL", self.config.portal_url),
                "dashboard_bind": values.get("JOKER_DASHBOARD_BIND", self.config.dashboard_bind),
                "dashboard_port": int(values.get("JOKER_DASHBOARD_PORT", str(self.config.dashboard_port))),
                "dashboard_path": admin_path,
                "admin_path": admin_path,
                "user_path": user_path,
                "smtp_host": values.get("JOKER_SMTP_HOST", self.config.smtp_host),
                "smtp_port": int(values.get("JOKER_SMTP_PORT", str(self.config.smtp_port))),
                "smtp_username": values.get("JOKER_SMTP_USERNAME", self.config.smtp_username),
                "smtp_from": values.get("JOKER_SMTP_FROM", self.config.smtp_from),
                "smtp_password_configured": bool(values.get("JOKER_SMTP_PASSWORD", self.config.smtp_password)),
                "smtp_use_tls": values.get("JOKER_SMTP_USE_TLS", "1") not in {"0", "false", "no"},
                "registration_require_email": values.get("JOKER_REGISTRATION_REQUIRE_EMAIL", "0") not in {"0", "false", "no"},
                "env_file": str(env_file_path()),
            }
        )

    async def _owner(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        return web.json_response(
            {"owner_openid": self.store.get_bot_owner_openid(self.config.owner_openid)}
        )

    async def _save_owner(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        payload = await self._json(request)
        owner_openid = str(payload.get("owner_openid", "")).strip()
        if owner_openid and len(owner_openid) > 512:
            return web.json_response({"error": "主人 OpenID 长度无效"}, status=400)
        self.store.set_bot_owner_openid(owner_openid)
        return web.json_response({"ok": True, "owner_openid": owner_openid})

    async def _replies(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        scope_id = request.query.get("scope_id", "").strip()
        if not scope_id:
            return web.json_response({"error": "scope_id is required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        return web.json_response(
            [
                {
                    "trigger": trigger,
                    "response": response,
                    "enabled": enabled,
                    "match_mode": match_mode,
                }
                for trigger, response, enabled, match_mode in self.store.list_replies(scope_id)
            ]
        )

    async def _save_reply(self, request: web.Request) -> web.Response:
        denied = self._require_auth(request)
        if denied:
            return denied
        payload = await self._json(request)
        scope_id = str(payload.get("scope_id", "")).strip()
        trigger = str(payload.get("trigger", "")).strip()
        response = str(payload.get("response", "")).strip()
        match_mode = str(payload.get("match_mode", "exact")).strip().lower()
        if not scope_id or not trigger or not response:
            return web.json_response({"error": "scope_id, trigger and response are required"}, status=400)
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        self.store.save_reply(scope_id, trigger, response, match_mode)
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
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
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
        denied = self._require_scope(request, scope_id)
        if denied:
            return denied
        if server_id:
            self.store.bind_server(scope_id, server_id)
        else:
            self.store.unbind_server(scope_id)
        self.store.set_setting(scope_id, "auto_reply_enabled", "1" if payload.get("auto_reply_enabled") else "0")
        return web.json_response({"ok": True})

    async def _restart_service(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        asyncio.create_task(self._restart_process(env_file_path()))
        return web.json_response({"ok": True, "restarting": True})

    async def _save_settings(self, request: web.Request) -> web.Response:
        denied = self._require_admin(request)
        if denied:
            return denied
        payload = await self._json(request)
        current = read_env_file()
        app_id = str(payload.get("app_id", "")).strip()
        api_base_url = str(payload.get("api_base_url", self.config.api_base_url)).strip().rstrip("/")
        transport = str(payload.get("transport", "webhook")).strip().lower() or "webhook"
        bind = str(payload.get("dashboard_bind", "127.0.0.1")).strip() or "127.0.0.1"
        admin_path = str(payload.get("admin_path", payload.get("dashboard_path", self.admin_path))).strip() or "/admin"
        user_path = str(payload.get("user_path", self.user_path)).strip() or "/user"
        for name, value in (("管理员路径", admin_path), ("用户路径", user_path)):
            if not value.startswith("/") or "?" in value or "#" in value:
                return web.json_response({"error": f"{name}必须以 / 开头，不能包含 ? 或 #"}, status=400)
        if len(admin_path) > 1:
            admin_path = "/" + admin_path.strip("/")
        if len(user_path) > 1:
            user_path = "/" + user_path.strip("/")
        if admin_path == "/" or user_path == "/" or admin_path == user_path:
            return web.json_response({"error": "管理员路径和用户路径必须是不同的非根路径"}, status=400)
        try:
            port = int(payload.get("dashboard_port", 8080))
            smtp_port = int(payload.get("smtp_port", self.config.smtp_port))
        except (TypeError, ValueError):
            return web.json_response({"error": "控制台端口必须是数字"}, status=400)
        if not app_id:
            return web.json_response({"error": "AppID 不能为空"}, status=400)
        if not api_base_url.startswith(("https://", "http://")):
            return web.json_response({"error": "官方 API 地址必须是 http 或 https 地址"}, status=400)
        if transport not in {"websocket", "webhook"}:
            return web.json_response({"error": "接收方式必须是 Webhook 或 WebSocket"}, status=400)
        if not 1 <= port <= 65535:
            return web.json_response({"error": "控制台端口范围为 1-65535"}, status=400)
        if not 1 <= smtp_port <= 65535:
            return web.json_response({"error": "SMTP 端口范围为 1-65535"}, status=400)
        app_secret = str(payload.get("app_secret", ""))
        dashboard_token = str(payload.get("dashboard_token", ""))
        existing_token = current.get("JOKER_DASHBOARD_TOKEN", "")
        if bind not in {"127.0.0.1", "localhost", "::1"} and not (dashboard_token or existing_token):
            return web.json_response({"error": "远程访问必须设置控制台访问令牌"}, status=400)
        updates = {
            "QQBOT_APP_ID": app_id,
            "QQBOT_API_BASE": api_base_url,
            "QQBOT_TRANSPORT": transport,
            "SCUM_RELAY_URL": str(payload.get("scum_relay_url", "")).strip(),
            "JOKER_PORTAL_URL": str(payload.get("portal_url", self.config.portal_url)).strip().rstrip("/"),
            "JOKER_DASHBOARD_BIND": bind,
            "JOKER_DASHBOARD_PORT": str(port),
            "JOKER_DASHBOARD_PATH": admin_path,
            "JOKER_ADMIN_PATH": admin_path,
            "JOKER_USER_PATH": user_path,
            "JOKER_SMTP_HOST": str(payload.get("smtp_host", "")).strip(),
            "JOKER_SMTP_PORT": str(smtp_port),
            "JOKER_SMTP_USERNAME": str(payload.get("smtp_username", "")).strip(),
            "JOKER_SMTP_FROM": str(payload.get("smtp_from", "")).strip(),
            "JOKER_SMTP_USE_TLS": "1" if payload.get("smtp_use_tls") else "0",
            "JOKER_REGISTRATION_REQUIRE_EMAIL": "1" if payload.get("registration_require_email") else "0",
        }
        if app_secret:
            updates["QQBOT_APP_SECRET"] = app_secret
        if dashboard_token:
            updates["JOKER_DASHBOARD_TOKEN"] = dashboard_token
        scum_key = str(payload.get("scum_relay_key", ""))
        if scum_key:
            updates["SCUM_RELAY_KEY"] = scum_key
        smtp_password = str(payload.get("smtp_password", ""))
        if smtp_password:
            updates["JOKER_SMTP_PASSWORD"] = smtp_password
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
        "group_event_count": 0,
        "full_message_event_count": 0,
        "at_message_event_count": 0,
        "last_group_event": "",
        "last_error": "",
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
