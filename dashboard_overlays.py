from __future__ import annotations


AUTH_UI_OVERLAY = r"""
<script>
(() => {
  const card = document.getElementById('register-card');
  if (!card) return;
  const label = card.closest('label');
  if (label) label.hidden = true;
  const hint = document.querySelector('#register-form .hint');
  if (hint) hint.textContent = '先完成邮箱验证和账号注册；登录后在“绑定群授权”中为每个官方群分别填写一张授权卡。';
})();
</script>
"""


ADMIN_UI_OVERLAY = r"""
<style id="joker-admin-refinement">
  :root { --bg:#0f141c; --panel:#171f2b; --panel-soft:#1b2533; --line:#2b3748; --text:#f2f5f8; --muted:#98a6b8; --accent:#e87d4d; --accent-strong:#f09363; --danger:#d65c67; }
  body { background:#0f141c; color:var(--text); }
  .shell { grid-template-columns:276px minmax(0,1fr); }
  .side { position:sticky; top:0; height:100vh; overflow-y:auto; background:#111822; border-right:1px solid #273241; padding:28px 16px 20px; gap:18px; }
  .brand { padding:2px 12px 10px; }
  .brand strong { display:flex; align-items:center; gap:9px; font-size:21px; letter-spacing:.1px; }
  .brand strong::before { content:""; width:9px; height:9px; border-radius:50%; background:var(--accent); box-shadow:0 0 0 5px #e87d4d20; }
  .brand span { color:#8090a4; margin-top:8px; }
  .nav-section { border:0; padding-top:4px; }
  .nav-title { color:#718096; padding:11px 12px 6px; font-size:11px; letter-spacing:.08em; }
  .nav button { color:#aeb9c7; padding:10px 12px; margin:2px 0; border:1px solid transparent; border-radius:9px; transition:background .16s,border-color .16s,color .16s; }
  .nav button:hover { background:#192433; color:#f8fafc; }
  .nav button.active { background:#202c3d; border-color:#35475e; color:#fff; box-shadow:none; }
  .side-foot { border-top:1px solid #273241; padding:16px 12px 0; }
  .main { background:#111720; }
  .top { min-height:94px; padding:24px 38px; background:#111822; border-bottom:1px solid #273241; }
  .top h1 { font-size:24px; letter-spacing:-.2px; }
  .top p { color:#8796aa; }
  .status { display:inline-flex; align-items:center; gap:7px; color:#a8e0c2; border:1px solid #2b5a47; background:#153527; border-radius:999px; padding:7px 11px; font-size:12px; }
  .status::before { content:""; width:6px; height:6px; border-radius:50%; background:#5bd18f; }
  .content { max-width:1480px; padding:32px 38px 64px; }
  .grid { gap:16px; }
  .card,.panel { background:var(--panel); border:1px solid var(--line); border-radius:12px; box-shadow:none; }
  .card { padding:20px; min-height:112px; display:flex; flex-direction:column; justify-content:space-between; }
  .card strong { color:#fff; font-size:31px; font-weight:650; letter-spacing:-.6px; }
  .panel { padding:22px; margin-bottom:16px; }
  .panel h2,.panel h3 { letter-spacing:-.15px; }
  .panel-head { gap:16px; }
  .muted { color:var(--muted); line-height:1.75; }
  .form { gap:14px; align-items:end; }
  label { color:#cbd5e1; font-size:12px; }
  input,select,textarea { background:#111822; border-color:#344255; color:#f8fafc; border-radius:8px; padding:11px 12px; }
  input:focus,select:focus,textarea:focus { outline:0; border-color:#e87d4d; box-shadow:0 0 0 3px #e87d4d1c; }
  textarea { min-height:110px; }
  .button { background:#202c3b; border-color:#3a485b; color:#edf2f7; border-radius:8px; padding:10px 14px; transition:transform .15s,background .15s,border-color .15s; }
  .button:hover { filter:none; transform:translateY(-1px); background:#29384a; border-color:#4d5f75; }
  .button.primary { background:var(--accent); border-color:var(--accent); color:#24140d; }
  .button.primary:hover { background:var(--accent-strong); border-color:var(--accent-strong); }
  .button.warn,.button.danger { background:#3a222a; border-color:#6b3c47; color:#ffdce1; }
  table { border-collapse:separate; border-spacing:0; width:100%; overflow:hidden; border:1px solid #2d3a4b; border-radius:10px; }
  th { background:#1b2634; color:#b7c3d2; font-size:12px; font-weight:600; }
  td,th { border-bottom:1px solid #293749; padding:13px 14px; }
  tr:last-child td { border-bottom:0; }
  code { color:#fdba8c; background:#2d2220; border:1px solid #5a3c34; border-radius:5px; padding:2px 5px; }
  #joker-card-usage { border-left:3px solid var(--accent); }
  #joker-owner-panel { background:#182231; }
  @media (max-width:900px) { .shell { display:block; } .side { position:relative; height:auto; overflow:visible; padding:16px; } .nav-section { margin:0; } .nav { display:flex; gap:6px; overflow-x:auto; padding-bottom:4px; } .nav button { flex:0 0 auto; white-space:nowrap; } .side-foot { display:none; } .top { padding:20px; } .content { padding:20px 16px 42px; } .grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .form { grid-template-columns:1fr; } }
  @media (max-width:560px) { .top { align-items:flex-start; flex-direction:column; } .grid { grid-template-columns:1fr; } .panel { padding:16px; } }
</style>
<script>
(() => {
  const post = async (url, payload) => {
    const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || '操作失败');
    return data;
  };
  const reload = () => setTimeout(() => location.reload(), 80);
  const setupOwner = async () => {
    const service = document.getElementById('service');
    if (!service || document.getElementById('joker-owner-panel')) return;
    const panel = document.createElement('section');
    panel.className = 'panel'; panel.id = 'joker-owner-panel';
    panel.innerHTML = '<div class="panel-head"><div><h2>机器人主人</h2><p class="muted">主人不受群功能开关和机器人授权限制，可在私聊或群内使用 /查看授权、/生成授权卡 [天数] [次数]、/删除授权卡 卡密。</p></div></div><div class="form"><label>主人用户 OpenID<input id="joker-owner-openid" placeholder="先私聊机器人发送 /获取OpenID 获取"></label><button class="button primary" id="joker-owner-save">保存主人</button></div><p class="muted" id="joker-owner-result"></p>';
    service.append(panel);
    try { const data = await fetch('/api/owner').then((response) => response.json()); document.getElementById('joker-owner-openid').value=data.owner_openid||''; } catch (error) {}
    document.getElementById('joker-owner-save').onclick = async () => {
      const result = document.getElementById('joker-owner-result');
      try { await post('/api/owner',{owner_openid:document.getElementById('joker-owner-openid').value.trim()}); result.textContent='主人设置已保存，立即生效。'; } catch (error) { result.textContent=error.message; }
    };
  };
  const refreshAuthorizedGroups = async () => {
    const target = document.getElementById('joker-authorized-groups-list');
    if (!target) return;
    try {
      const response = await fetch('/api/auth/users');
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '授权群组读取失败');
      const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
      const groups = Array.isArray(data.group_authorizations) ? data.group_authorizations : [];
      target.innerHTML = groups.length ? `<table><thead><tr><th>QQ群号</th><th>官方群标识</th><th>到期时间</th><th>配置</th><th>管理账号</th><th>状态</th><th></th></tr></thead><tbody>${groups.map((group) => {
        const expires = Number(group.expires_at || 0) ? new Date(Number(group.expires_at) * 1000).toLocaleString() : '永久';
        const config = `服务器 ${group.server_id || '-'} · 自动回复 ${group.auto_reply_enabled ? '开' : '关'} · 记录 ${group.message_recording_enabled ? '开' : '关'} · 回复 ${group.reply_count || 0} 条 · 消息 ${group.message_count || 0} 条 · 分管 ${group.admin_count || 0} 人`;
        const managers = Array.isArray(group.managers) && group.managers.length ? group.managers.join('、') : '未绑定账号';
        return `<tr><td>${escape(group.numeric_group_id || '-')}</td><td><code>${escape(group.scope_id)}</code></td><td>${escape(expires)}</td><td>${escape(config)}</td><td>${escape(managers)}</td><td>${escape(group.status || '未知')}</td><td><button class="button danger" data-revoke-group="${escape(group.scope_id)}">删除授权</button></td></tr>`;
      }).join('')}</tbody></table>` : '<div class="empty">暂无已授权群组</div>';
      target.querySelectorAll('[data-revoke-group]').forEach((button) => button.onclick = async () => {
        if (!confirm(`确认删除群 ${button.closest('tr')?.querySelector('td')?.textContent?.trim() || button.dataset.revokeGroup} 的授权吗？`)) return;
        try {
          await post('/api/auth/groups/delete', {scope_id:button.dataset.revokeGroup});
          await refreshAuthorizedGroups();
          const result = document.getElementById('card-result');
          if (result) result.textContent = '群授权已删除。';
        } catch (error) { alert(error.message); }
      });
    } catch (error) { target.innerHTML = `<div class="empty">${String(error.message || '授权群组读取失败')}</div>`; }
  };
  const setupAuthorizedGroups = () => {
    const auth = document.getElementById('auth');
    if (!auth || document.getElementById('joker-authorized-groups')) return;
    const panel = document.createElement('section');
    panel.className = 'panel'; panel.id = 'joker-authorized-groups';
    panel.innerHTML = '<div class="panel-head"><div><h2>已授权群组</h2><p class="muted">每张卡只授权一个群。这里显示群号、到期时间和当前配置；删除后该群立即停止执行功能，原卡不会恢复使用次数。</p></div><button class="button" id="joker-authorized-groups-refresh">刷新</button></div><div id="joker-authorized-groups-list"><div class="empty">正在读取...</div></div>';
    auth.append(panel);
    document.getElementById('joker-authorized-groups-refresh').onclick = refreshAuthorizedGroups;
    refreshAuthorizedGroups();
  };
  const addCardUsage = () => {
    const cards = document.getElementById('cards');
    if (!cards || document.getElementById('joker-card-usage')) return;
    const panel = document.createElement('section');
    panel.className = 'panel'; panel.id = 'joker-card-usage';
    panel.innerHTML = '<div class="panel-head"><div><h2>官方群授权卡使用</h2><p class="muted">授权以官方群为单位，不绑定个人 QQ 号。每张卡只能授权一个群，到期后该群停止执行机器人功能。可在目标群发送 <code>/授权 卡密</code>，或在用户中心填写卡密和群号完成绑定。</p></div></div>';
    cards.prepend(panel);
  };
  const setupCardExpiry = () => {
    const days = document.getElementById('card-days');
    const button = document.getElementById('create-card');
    if (!days || !button) return;
    if (!document.getElementById('joker-card-expires')) {
      const label = document.createElement('label');
      label.id = 'joker-card-expires-label'; label.innerHTML = '自定义到期时间（可选）<input id="joker-card-expires" type="datetime-local">';
      days.closest('label')?.insertAdjacentElement('afterend', label);
    }
    if (button.dataset.jokerCardBound) return;
    button.dataset.jokerCardBound = '1';
    button.onclick = async () => {
      const result = document.getElementById('card-result');
      const value = document.getElementById('joker-card-expires')?.value || '';
      const payload = { max_uses:1, days:Number(days.value || 30) };
      if (value) {
        const timestamp = Math.floor(new Date(value).getTime() / 1000);
        if (!Number.isFinite(timestamp) || timestamp <= Math.floor(Date.now() / 1000)) { result.textContent='到期时间必须晚于当前时间。'; return; }
        payload.expires_at = timestamp;
      }
      try { const data = await post('/api/auth/cards', payload); result.textContent=`新卡密：${data.card_code}`; reload(); } catch (error) { result.textContent=error.message; }
    };
  };
  const upgradeCards = () => {
    document.querySelectorAll('#cards-table tbody tr').forEach((row) => {
      const code = row.querySelector('td')?.textContent?.trim();
      const cell = row.lastElementChild;
      if (!code || !cell) return;
      let button = cell.querySelector('[data-delete-card]');
      if (!button) { button = document.createElement('button'); button.className = 'button danger'; button.textContent = '删除'; button.dataset.deleteCard = code; cell.replaceChildren(button); }
      if (button.dataset.jokerDeleteBound) return;
      button.dataset.jokerDeleteBound = '1';
      button.onclick = async () => {
        if (!confirm(`确认删除授权卡 ${code} 吗？删除后不能恢复。`)) return;
        try { await post('/api/auth/cards/delete', {card_code:code}); row.remove(); const result=document.getElementById('card-result'); if(result) result.textContent='授权卡已删除。'; await refreshAuthorizedGroups(); } catch (error) { const result=document.getElementById('card-result'); if(result) result.textContent=error.message; else alert(error.message); }
      };
      cell.replaceChildren(button);
    });
  };
  const upgradeUsers = () => {
    document.querySelectorAll('#users-table tbody tr').forEach((row) => {
      const source = row.querySelector('[data-password], [data-user-toggle]');
      const userId = source?.dataset.password || source?.dataset.userToggle;
      const cell = row.lastElementChild;
      if (!userId || !cell || cell.querySelector('[data-edit-user]')) return;
      const button = document.createElement('button');
      button.className = 'button'; button.textContent = '编辑'; button.dataset.editUser = userId;
      button.onclick = async () => {
        const username = prompt('登录账号（留空保持不变）');
        if (username === null) return;
        const name = prompt('显示名称（留空保持不变）');
        if (name === null) return;
        const email = prompt('邮箱（留空保持不变）');
        if (email === null) return;
        const password = prompt('新密码（留空保持不变）');
        if (password === null) return;
        try {
          const payload = {user_id:Number(userId)};
          if (username.trim()) payload.username = username.trim();
          if (name.trim()) payload.display_name = name.trim();
          if (email.trim()) payload.email = email.trim();
          if (password.trim()) payload.password = password.trim();
          await post('/api/auth/users/update', payload); reload();
        } catch (error) { alert(error.message); }
      };
      cell.prepend(button, document.createTextNode(' '));
    });
  };
  const upgrade = () => {
    document.getElementById('card-kind')?.closest('label')?.setAttribute('hidden','hidden');
    document.getElementById('card-uses')?.closest('label')?.setAttribute('hidden','hidden');
    upgradeCards(); upgradeUsers(); setupOwner(); addCardUsage(); setupCardExpiry(); setupAuthorizedGroups();
  };
  const observer = new MutationObserver(upgrade);
  observer.observe(document.body, {childList:true, subtree:true});
  upgrade(); setTimeout(upgrade, 500); setTimeout(upgrade, 1500);
})();
</script>
"""


GROUP_UI_OVERLAY = r"""
<style id="joker-group-console-overlay-style">
  :root { --bg:#10151d; --side:#121923; --panel:#192330; --panel2:#202c3b; --line:#304052; --text:#f3f6f9; --muted:#9aa9bb; --accent:#58b5df; --accent2:#ed8a5d; --danger:#d96370; --good:#72d5a5; }
  body { background:#10151d; }
  .shell { grid-template-columns:272px minmax(0,1fr); }
  .side { position:sticky; top:0; height:100vh; overflow-y:auto; background:#121923; border-right:1px solid #2d3a4a; padding:28px 16px 20px; gap:16px; }
  .brand { padding:2px 12px 10px; }
  .brand strong { display:flex; align-items:center; gap:9px; font-size:20px; }
  .brand strong::before { content:""; width:9px; height:9px; border-radius:50%; background:#58b5df; box-shadow:0 0 0 5px #58b5df1c; }
  .brand span { margin-top:8px; color:#8391a4; }
  .nav-group { border-top:0; padding-top:3px; }
  .nav-label { padding:12px 11px 6px; color:#748296; letter-spacing:.08em; }
  .nav button { border:1px solid transparent; border-radius:9px; color:#afbbc9; padding:10px 11px; transition:background .16s,border-color .16s,color .16s; }
  .nav button:hover { background:#1b2735; color:#fff; }
  .nav button.active { background:#223246; border-color:#35516c; box-shadow:none; color:#fff; }
  .side-foot { border-top:1px solid #2d3a4a; padding:16px 11px 0; }
  .main { background:#111821; }
  .top { min-height:96px; background:#121923; border-bottom:1px solid #2d3a4a; padding:24px 38px; }
  .top h1 { font-size:24px; letter-spacing:-.2px; }
  .top p { color:#8e9caf; }
  .scope select { background:#182331; border-color:#3a4c60; border-radius:9px; padding:11px 12px; }
  .content { max-width:1480px; padding:32px 38px 64px; }
  .card,.panel { background:#192330; border:1px solid #304052; border-radius:12px; box-shadow:none; }
  .card { padding:20px; }
  .panel { padding:22px; margin-bottom:16px; }
  .panel h2,.panel h3 { letter-spacing:-.15px; }
  .muted { color:#9aa9bb; line-height:1.75; }
  .form { gap:14px; }
  input,textarea,select { background:#111923; border-color:#3a4d61; border-radius:8px; padding:11px 12px; }
  input:focus,textarea:focus,select:focus { outline:0; border-color:#58b5df; box-shadow:0 0 0 3px #58b5df1c; }
  .button { background:#213043; border-color:#40556d; border-radius:8px; padding:10px 14px; transition:transform .15s,background .15s; }
  .button:hover { filter:none; transform:translateY(-1px); background:#2a3d53; }
  .button.primary { background:#58b5df; border-color:#58b5df; color:#09202d; }
  .button.danger { background:#402630; border-color:#6d3d4a; }
  .joker-note { background:#172536; border-color:#345776; color:#bdd0e1; border-radius:9px; }
  .joker-usage-guide { border-left:3px solid #58b5df; background:#18293a; }
  .joker-toolbar { margin-bottom:14px; }
  table { border-collapse:separate; border-spacing:0; width:100%; overflow:hidden; border:1px solid #304052; border-radius:10px; }
  th { background:#202d3c; color:#bcc8d5; font-size:12px; font-weight:600; }
  td,th { border-bottom:1px solid #2e4053; padding:13px 14px; }
  tr:last-child td { border-bottom:0; }
  .result,.joker-result { font-size:13px; }
  .joker-form-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
  .joker-actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
  .joker-result { min-height:20px; margin-top:10px; color:#9ed9ca; }
  .joker-result.error { color:#ff9b9b; }
  .joker-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:12px; }
  .joker-note { padding:10px 12px; border:1px solid #345574; border-radius:8px; color:#a9bfd8; font-size:12px; line-height:1.7; margin:12px 0; }
  .joker-panel-stack { display:grid; gap:14px; }
  .joker-muted { color:#9ab0ca; font-size:12px; }
  @media (max-width:900px) { .shell { display:block; } .side { position:relative; height:auto; overflow:visible; padding:16px; } .nav-group { margin:0; } .nav { display:flex; gap:6px; overflow-x:auto; padding-bottom:4px; } .nav button { flex:0 0 auto; white-space:nowrap; } .side-foot { display:none; } .top { padding:20px; align-items:flex-start; flex-direction:column; } .scope { min-width:100%; } .content { padding:20px 16px 42px; } .joker-form-grid { grid-template-columns:1fr; } .joker-toolbar { align-items:stretch; flex-direction:column; } .form { grid-template-columns:1fr!important; } }
  @media (max-width:560px) { .panel { padding:16px; } }
</style>
<script>
(() => {
  if (document.getElementById('joker-group-console-overlay-ready')) return;
  const marker = document.createElement('meta'); marker.id = 'joker-group-console-overlay-ready'; document.head.append(marker);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const get = async (url) => { const response = await fetch(url, {headers:{Accept:'application/json'}}); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '读取失败'); return data; };
  const post = async (url, payload) => { const response = await fetch(url, {method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify(payload)}); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '保存失败'); return data; };
  const scope = () => document.getElementById('scope-switch')?.value || '';
  let members = []; let memberScope = '';
  const memberId = (row) => String(row?.member_openid || row?.user_openid || row?.openid || '').trim();
  const memberName = (row, fallback='群成员') => String(row?.username || row?.nick || row?.nickname || fallback).trim() || fallback;
  const memberRole = (row) => ({owner:'群主',admin:'管理员',member:'成员'})[String(row?.member_role || 'member').toLowerCase()] || '成员';
  const nameFor = (userId, fallback='已离群成员') => memberName(members.find((row) => memberId(row) === String(userId)) || {}, fallback);
  const roleFor = (userId) => memberRole(members.find((row) => memberId(row) === String(userId)) || {});
  const options = (selected='') => ['<option value="">请选择群成员</option>', ...members.map((row) => { const id = memberId(row); if (!id) return ''; const label = `${memberName(row)} · ${memberRole(row)}${row.bot ? ' · 机器人' : ''}`; return `<option value="${esc(id)}" ${id===selected?'selected':''}>${esc(label)}</option>`; })].join('');
  const fillMemberOptions = () => document.querySelectorAll('[data-joker-member-select]').forEach((element) => { const previous = element.value; element.innerHTML = options(previous); if (previous) element.value = previous; });
  const memberValue = (selectId, inputId) => String(document.getElementById(inputId)?.value || document.getElementById(selectId)?.value || '').trim();
  const loadMembers = async (force=false) => { const current = scope(); if (!current) { members=[]; memberScope=''; fillMemberOptions(); return []; } if (!force && memberScope === current && members.length) return members; const data = await get(`/api/group-members?scope_id=${encodeURIComponent(current)}&all=1`); members = Array.isArray(data.members) ? data.members.filter((row) => memberId(row)) : []; memberScope=current; fillMemberOptions(); return members; };
  const result = (id, text='', error=false) => { const target=document.getElementById(id); if (!target) return; target.textContent=text; target.classList.toggle('error',error); };
  const show = (id, title, subtitle) => { document.querySelectorAll('.view').forEach((view) => view.classList.toggle('active',view.id===id)); document.querySelectorAll('[data-view]').forEach((button) => button.classList.toggle('active',button.dataset.view===id)); const heading=document.getElementById('title'); const detail=document.getElementById('subtitle'); if (heading) heading.textContent=title; if (detail) detail.textContent=subtitle; if (id==='messages') refreshMessages(); if (id==='replies') refreshReplies(); if (id==='user-replies') refreshUserReplies(); if (id==='group-admins') refreshAdmins(); if (id==='schedules') refreshTasks(); if (id==='approval') refreshApproval(); };
  const addNav = (id, label, title, subtitle) => { if (document.querySelector(`[data-view="${id}"]`)) return; const navs=[...document.querySelectorAll('nav.nav')]; const nav=navs[1] || navs.at(-1); if (!nav) return; const button=document.createElement('button'); button.dataset.view=id; button.textContent=label; button.addEventListener('click',()=>show(id,title,subtitle)); nav.append(button); };
  const addView = (id, label, title, subtitle, html) => { let view=document.getElementById(id); if (!view) { view=document.createElement('section'); view.className='view'; view.id=id; document.querySelector('.content')?.append(view); } view.dataset.memberUi='1'; view.innerHTML=html; addNav(id,label,title,subtitle); };
  const addViews = () => {
    const groupsNote=document.querySelector('#group-workspace .muted'); if (groupsNote) groupsNote.textContent='选择已绑定官方群并设置可用功能。';
    const bindNote=document.querySelector('#bind .panel-head .muted'); if (bindNote) bindNote.textContent='完成机器人授权后，填写机器人已记录的 QQ 群号即可绑定当前群。';
    const replies=document.getElementById('replies'); if (replies) { replies.dataset.memberUi='1'; replies.innerHTML=`<div class="joker-panel-stack"><div class="panel"><div class="panel-head"><div><h2>自动回复</h2><p class="muted">精准回复只在消息完全一致时触发；模糊回复在消息包含关键词时触发。</p></div></div><div class="joker-form-grid"><label>匹配方式<select id="reply-match-mode"><option value="exact">精准回复</option><option value="fuzzy">模糊回复</option></select></label><label>关键词<input id="reply-trigger" maxlength="128"></label><label>回复内容<textarea id="reply-response" maxlength="2000"></textarea></label></div><div class="joker-actions"><button class="button primary" id="reply-save">保存回复</button><button class="button" id="reply-clear">取消编辑</button></div><div class="joker-result" id="reply-result"></div></div><div class="panel"><div class="joker-toolbar"><h3>已设置回复</h3><button class="button" id="reply-refresh">刷新</button></div><div id="reply-list"></div></div></div>`; }
    const messages=document.getElementById('messages'); if (messages) { messages.dataset.memberUi='1'; messages.innerHTML=`<div class="joker-panel-stack"><div class="panel"><div class="panel-head"><div><h2>按成员撤回消息</h2><p class="muted">只处理机器人收到且不超过 2 分钟的普通成员消息；消息正文不会保存或显示。</p></div><button class="button" id="message-refresh">刷新</button></div><div class="joker-form-grid"><label>成员 QQ号或官方 OpenID<input id="message-member-direct" placeholder="直接输入，或从列表选择"></label><label>选择成员<select id="message-member" data-joker-member-select></select></label><label>最多处理条数<input id="message-limit" type="number" min="1" max="100" value="20"></label></div><div class="joker-note">官方接口只接受 OpenID；如果成员列表没有返回 QQ 号映射，请填写官方 OpenID 或使用群消息中的成员引用。</div><div class="joker-actions"><button class="button danger" id="message-recall">撤回该成员消息</button></div><div class="joker-result" id="message-result"></div></div><div class="panel"><h3>群消息记录</h3><p class="joker-muted">仅保留时间、发送成员、当前身份和撤回备注。</p><div id="message-list"></div></div></div>`; }
    addView('moderation','手动群管','手动群管','可直接输入成员 QQ 号或 OpenID，也可以从成员列表选择。',`<div class="panel"><div class="panel-head"><div><h2>手动群管</h2><p class="muted">群主、管理员和机器人会被 QQ 官方接口跳过。</p></div><button class="button" id="moderation-members">读取成员</button></div><div class="joker-form-grid"><label>成员 QQ号或官方 OpenID<input id="moderation-member-direct" placeholder="直接输入，或从列表选择"></label><label>选择成员<select id="moderation-member" data-joker-member-select></select></label><label>操作<select id="moderation-action"><option value="mute">禁言</option><option value="unmute">解除禁言</option><option value="kick">踢出群聊</option><option value="blacklist">踢出并拉黑</option></select></label><label>禁言时长（秒）<input id="moderation-seconds" type="number" min="1" max="2592000" value="600"></label></div><div class="joker-note">官方接口只接受 OpenID；如果成员列表没有返回 QQ 号映射，请填写官方 OpenID 或使用群消息中的成员引用。</div><div class="joker-actions"><button class="button danger" id="moderation-run">执行</button><button class="button" id="moderation-mute-all">全体禁言</button><button class="button" id="moderation-unmute-all">全体解禁</button></div><div class="joker-result" id="moderation-result"></div></div>`);
    addView('user-replies','用户专属回复','用户专属回复','可直接输入成员 QQ 号或 OpenID，也可以从成员列表选择。',`<div class="joker-panel-stack"><div class="panel"><h2>新增或编辑专属回复</h2><div class="joker-form-grid"><label>成员 QQ号或官方 OpenID<input id="user-reply-member-direct" placeholder="直接输入，或从列表选择"></label><label>选择成员<select id="user-reply-member" data-joker-member-select></select></label><label>匹配方式<select id="user-reply-mode"><option value="exact">精准回复</option><option value="fuzzy">模糊回复</option></select></label><label>关键词<input id="user-reply-trigger" maxlength="128"></label><label>回复内容<textarea id="user-reply-response" maxlength="2000"></textarea></label></div><div class="joker-actions"><button class="button primary" id="user-reply-save">保存</button></div><div class="joker-result" id="user-reply-result"></div></div><div class="panel"><div class="joker-toolbar"><h3>已设置专属回复</h3><button class="button" id="user-reply-refresh">刷新</button></div><div id="user-reply-list"></div></div></div>`);
    addView('group-admins','分群管理员','分群管理员','可直接输入成员 QQ 号或 OpenID，也可以从成员列表选择。',`<div class="joker-panel-stack"><div class="panel"><h2>设置分群管理员</h2><div class="joker-form-grid"><label>成员 QQ号或官方 OpenID<input id="group-admin-member-direct" placeholder="直接输入，或从列表选择"></label><label>选择成员<select id="group-admin-member" data-joker-member-select></select></label><label>备注（可选）<input id="group-admin-note" maxlength="80"></label></div><div class="joker-actions"><button class="button primary" id="group-admin-save">保存管理员</button></div><div class="joker-result" id="group-admin-result"></div></div><div class="panel"><div class="joker-toolbar"><h3>当前分群管理员</h3><button class="button" id="group-admin-refresh">刷新</button></div><div id="group-admin-list"></div></div></div>`);
    addView('schedules','定时任务','定时任务','按指定时间执行一次播报、禁言、解禁或点歌搜索链接。',`<div class="joker-panel-stack"><div class="panel"><h2>创建定时任务</h2><div class="joker-note">这是一次性任务，不是循环任务。选择时间后只执行一次；点歌会发送稳定的音乐搜索链接。</div><div class="joker-form-grid"><label>任务类型<select id="task-type"><option value="broadcast">定时播报</option><option value="mute_all">定时全体禁言</option><option value="unmute_all">定时全体解禁</option><option value="song">定时点歌</option></select></label><label>执行时间<input id="task-run-at" type="datetime-local"></label><label id="task-content-label">播报内容<input id="task-content" maxlength="2000"></label><label id="task-mute-label">禁言时长（秒）<input id="task-mute-seconds" type="number" min="1" max="2592000" value="600"></label></div><div class="joker-actions"><button class="button primary" id="task-save">创建任务</button></div><div class="joker-result" id="task-result"></div></div><div class="panel"><div class="joker-toolbar"><h3>已创建任务</h3><button class="button" id="task-refresh">刷新</button></div><div id="task-list"></div></div></div>`);
    addView('approval','入群审核','入群审核','读取 QQ 官方审核策略和待处理入群申请。',`<div class="joker-panel-stack"><div class="panel"><h2>官方入群审核</h2><div class="joker-note">官方自动审批只处理白名单 QQ 号，不是开启后所有人自动进群。数学题、随机验证码、自定义 ID 验证没有对应官方接口，因此不显示。</div><div class="joker-note" id="approval-state">正在读取官方策略状态...</div><div class="joker-form-grid"><label>白名单 QQ号（多个用空格或逗号分隔）<input id="approval-whitelist-users" placeholder="例如：123456789"></label></div><div class="joker-actions"><button class="button primary" id="approval-direct-on">开启自动审批策略</button><button class="button" id="approval-direct-off">关闭自动审批</button><button class="button" id="approval-whitelist-add">加入白名单</button><button class="button" id="approval-whitelist-del">移出白名单</button><button class="button" id="approval-execute">处理现有申请</button><button class="button" id="approval-refresh">刷新策略和申请</button></div><div class="joker-result" id="approval-result"></div></div><div class="panel"><h3>入群申请</h3><div id="approval-list"></div></div></div>`);
    const profile=document.getElementById('profile'); if (profile && !document.getElementById('license-panel')) profile.insertAdjacentHTML('beforeend',`<div class="panel" id="license-panel"><h2>机器人授权</h2><p class="muted" id="license-state">读取中</p><div class="joker-form-grid"><label>授权卡密<input id="license-card" placeholder="JOKER-XXXXXXXXXX"></label></div><div class="joker-actions"><button class="button primary" id="license-redeem">兑换授权卡</button></div><div class="joker-result" id="license-result"></div></div><div class="panel"><h2>邮箱验证修改密码</h2><p class="muted">验证码发送至当前账号邮箱。</p><div class="joker-form-grid"><label>邮箱验证码<input id="password-reset-code" inputmode="numeric" maxlength="6"></label><label>新密码<input id="password-reset-value" type="password" minlength="6"></label></div><div class="joker-actions"><button class="button" id="password-reset-send">发送验证码</button><button class="button primary" id="password-reset-save">修改密码</button></div><div class="joker-result" id="password-reset-result"></div></div>`);
  };
  const refreshReplies = async () => { const target=document.getElementById('reply-list'); if (!target || !scope()) return; try { const rows=await get(`/api/replies?scope_id=${encodeURIComponent(scope())}`); target.innerHTML=rows.length?`<table><thead><tr><th>匹配</th><th>关键词</th><th>回复</th><th></th></tr></thead><tbody>${rows.map((row)=>{const trigger=Array.isArray(row)?row[0]:row.trigger;const response=Array.isArray(row)?row[1]:row.response;const mode=Array.isArray(row)?row[3]:row.match_mode;return `<tr><td>${mode==='fuzzy'?'模糊':'精准'}</td><td>${esc(trigger)}</td><td>${esc(response)}</td><td><button class="button" data-reply-edit="${esc(trigger)}" data-mode="${esc(mode||'exact')}">编辑</button> <button class="button danger" data-reply-delete="${esc(trigger)}">删除</button></td></tr>`;}).join('')}</tbody></table>`:'<div class="empty">暂无自动回复</div>'; target.querySelectorAll('[data-reply-edit]').forEach((button)=>button.onclick=()=>{document.getElementById('reply-trigger').value=button.dataset.replyEdit;document.getElementById('reply-match-mode').value=button.dataset.mode||'exact';const row=button.closest('tr');document.getElementById('reply-response').value=row?.children[2]?.textContent||'';}); target.querySelectorAll('[data-reply-delete]').forEach((button)=>button.onclick=async()=>{await post('/api/replies/delete',{scope_id:scope(),trigger:button.dataset.replyDelete});refreshReplies();}); } catch(error) { target.innerHTML=`<div class="empty">${esc(error.message)}</div>`; } };
  const refreshMessages = async () => { const target=document.getElementById('message-list'); if (!target || !scope()) return; try { await loadMembers(); const rows=await get(`/api/messages?scope_id=${encodeURIComponent(scope())}&limit=100`); target.innerHTML=rows.length?`<table><thead><tr><th>发送时间</th><th>发送人</th><th>身份</th><th>备注</th></tr></thead><tbody>${rows.map((row)=>`<tr><td>${esc(row.created_at||'')}</td><td>${esc(nameFor(row.user_id,'已记录成员'))}</td><td>${esc(roleFor(row.user_id))}</td><td>${row.recalled?'已撤回':'已记录'}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">暂无已记录消息</div>'; } catch(error) { target.innerHTML=`<div class="empty">${esc(error.message)}</div>`; } };
  const refreshUserReplies = async () => { const target=document.getElementById('user-reply-list'); if (!target || !scope()) return; try { await loadMembers(); const rows=await get(`/api/user-replies?scope_id=${encodeURIComponent(scope())}`); target.innerHTML=rows.length?`<table><thead><tr><th>成员</th><th>匹配</th><th>关键词</th><th>回复</th><th></th></tr></thead><tbody>${rows.map((row)=>`<tr><td>${esc(nameFor(row.user_id))}</td><td>${row.match_mode==='fuzzy'?'模糊':'精准'}</td><td>${esc(row.trigger)}</td><td>${esc(row.response)}</td><td><button class="button danger" data-user-reply-delete="${esc(row.user_id)}" data-trigger="${esc(row.trigger)}">删除</button></td></tr>`).join('')}</tbody></table>`:'<div class="empty">暂无专属回复</div>'; target.querySelectorAll('[data-user-reply-delete]').forEach((button)=>button.onclick=async()=>{await post('/api/user-replies/delete',{scope_id:scope(),user_id:button.dataset.userReplyDelete,trigger:button.dataset.trigger});refreshUserReplies();}); } catch(error) { target.innerHTML=`<div class="empty">${esc(error.message)}</div>`; } };
  const refreshAdmins = async () => { const target=document.getElementById('group-admin-list'); if (!target || !scope()) return; try { await loadMembers(); const rows=await get(`/api/group-admins?scope_id=${encodeURIComponent(scope())}`); target.innerHTML=rows.length?`<table><thead><tr><th>成员</th><th>备注</th><th></th></tr></thead><tbody>${rows.map((row)=>`<tr><td>${esc(nameFor(row.user_id,row.display_name||'已离群成员'))}</td><td>${esc(row.display_name||'-')}</td><td><button class="button danger" data-admin-delete="${esc(row.user_id)}">删除</button></td></tr>`).join('')}</tbody></table>`:'<div class="empty">暂无分群管理员</div>'; target.querySelectorAll('[data-admin-delete]').forEach((button)=>button.onclick=async()=>{await post('/api/group-admins',{scope_id:scope(),user_id:button.dataset.adminDelete,action:'remove'});refreshAdmins();}); } catch(error) { target.innerHTML=`<div class="empty">${esc(error.message)}</div>`; } };
  const refreshTasks = async () => { const target=document.getElementById('task-list'); if (!target || !scope()) return; try { const labels={broadcast:'定时播报',mute_all:'定时全体禁言',unmute_all:'定时全体解禁',song:'定时点歌'}; const rows=await get(`/api/tasks?scope_id=${encodeURIComponent(scope())}`); target.innerHTML=rows.length?`<table><thead><tr><th>类型</th><th>执行时间</th><th>内容/时长</th><th>状态</th><th></th></tr></thead><tbody>${rows.map((row)=>`<tr><td>${esc(labels[row.task_type]||row.task_type)}</td><td>${new Date(row.run_at*1000).toLocaleString()}</td><td>${esc(row.content||`${row.mute_seconds} 秒`)}</td><td>${row.completed_at?'已完成':row.last_error?'执行失败':'待执行'}</td><td>${row.completed_at||row.last_error?'':`<button class="button danger" data-task-delete="${row.task_id}">删除</button>`}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">暂无定时任务</div>'; target.querySelectorAll('[data-task-delete]').forEach((button)=>button.onclick=async()=>{await post('/api/tasks/delete',{scope_id:scope(),task_id:Number(button.dataset.taskDelete)});refreshTasks();}); } catch(error) { target.innerHTML=`<div class="empty">${esc(error.message)}</div>`; } };
   const refreshApproval = async () => { const target=document.getElementById('approval-list'); const stateTarget=document.getElementById('approval-state'); if (!target || !scope()) return; try { try { const state=await get(`/api/join-approval/state?scope_id=${encodeURIComponent(scope())}`); if (stateTarget) { const strategy=Array.isArray(state.strategies)&&state.strategies.length?`，官方策略 ${state.strategies.length} 条`:'，暂无匹配官方策略'; stateTarget.textContent=`自动审批：${state.enabled?'开启':'关闭'}${state.strategy_id?`，策略 ID：${state.strategy_id}`:''}${strategy}`; } } catch (error) { if (stateTarget) stateTarget.textContent=`官方策略状态暂时无法读取：${error.message}`; } const data=await get(`/api/join-requests?scope_id=${encodeURIComponent(scope())}`); const rows=Array.isArray(data.list)?data.list:(Array.isArray(data.requests)?data.requests:[]); target.innerHTML=rows.length?`<table><thead><tr><th>申请成员</th><th>验证信息</th><th>操作</th></tr></thead><tbody>${rows.map((row)=>{const member=row.member_openid||row.user_openid||row.openid||'';const request=row.join_request_id||row.request_id||row.id||'';return `<tr><td>${esc(row.username||'申请成员')}</td><td>${esc(row.verify_info?.verify_message||row.verify_info||row.message||'-')}</td><td><button class="button primary" data-approve="${esc(member)}" data-request="${esc(request)}">同意</button> <button class="button danger" data-decline="${esc(member)}" data-request="${esc(request)}">拒绝</button></td></tr>`;}).join('')}</tbody></table>`:'<div class="empty">暂无待处理入群申请</div>'; target.querySelectorAll('[data-approve]').forEach((button)=>button.onclick=async()=>{await post('/api/join-requests/approve',{scope_id:scope(),member_openid:button.dataset.approve,join_request_id:button.dataset.request,operation:'approve'});refreshApproval();}); target.querySelectorAll('[data-decline]').forEach((button)=>button.onclick=async()=>{await post('/api/join-requests/approve',{scope_id:scope(),member_openid:button.dataset.decline,join_request_id:button.dataset.request,operation:'decline',reject_reason:prompt('拒绝理由（可留空）')||''});refreshApproval();}); } catch(error) { if (stateTarget) stateTarget.textContent=error.message; target.innerHTML=`<div class="empty">${esc(error.message)}</div>`; } };
   const updateApprovalWhitelist = async (operation) => { const values=String(document.getElementById('approval-whitelist-users')?.value||'').split(/[\s,，]+/).map((value)=>value.trim()).filter(Boolean); if (!values.length) { result('approval-result','请填写 QQ号',true); return; } try { const state=await get(`/api/join-approval/state?scope_id=${encodeURIComponent(scope())}`); if (!state.strategy_id) { result('approval-result','请先开启自动审批策略',true); return; } await post('/api/join-approval-strategies/whitelist',{scope_id:scope(),strategy_id:state.strategy_id,operation,whitelist_users:values}); result('approval-result',operation==='add'?'白名单已添加':'白名单已移除'); } catch(error) { result('approval-result',error.message,true); } };
  const refreshLicense = async () => { const target=document.getElementById('license-state'); if (!target) return; try { const data=await get('/api/license/status'); target.textContent=data.active ? `已授权${data.expires_at?`，到期：${new Date(data.expires_at*1000).toLocaleString()}`:''}` : '当前账号尚未授权。兑换授权卡后才能绑定官方群。'; } catch(error) { target.textContent=error.message; } };
  const bind = () => {
    document.getElementById('reply-save')?.addEventListener('click',async()=>{try{await post('/api/replies',{scope_id:scope(),trigger:document.getElementById('reply-trigger').value.trim(),response:document.getElementById('reply-response').value.trim(),match_mode:document.getElementById('reply-match-mode').value});result('reply-result','已保存');refreshReplies();}catch(error){result('reply-result',error.message,true);}});
    document.getElementById('reply-clear')?.addEventListener('click',()=>{document.getElementById('reply-trigger').value='';document.getElementById('reply-response').value='';document.getElementById('reply-match-mode').value='exact';}); document.getElementById('reply-refresh')?.addEventListener('click',refreshReplies);
    document.getElementById('message-refresh')?.addEventListener('click',refreshMessages); document.getElementById('message-recall')?.addEventListener('click',async()=>{const userId=memberValue('message-member','message-member-direct');if(!userId)return result('message-result','请填写成员 QQ号或官方 OpenID',true);try{const data=await post('/api/moderation',{scope_id:scope(),user_id:userId,action:'recall_user',recall_limit:Number(document.getElementById('message-limit').value||20)});result('message-result',data.message||'已提交');refreshMessages();}catch(error){result('message-result',error.message,true);}});
    document.getElementById('moderation-members')?.addEventListener('click',async()=>{try{await loadMembers(true);result('moderation-result',`已读取 ${members.length} 名成员`);}catch(error){result('moderation-result',error.message,true);}}); document.getElementById('moderation-run')?.addEventListener('click',async()=>{const userId=memberValue('moderation-member','moderation-member-direct');if(!userId)return result('moderation-result','请填写成员 QQ号或官方 OpenID',true);try{const data=await post('/api/moderation',{scope_id:scope(),user_id:userId,action:document.getElementById('moderation-action').value,duration_seconds:Number(document.getElementById('moderation-seconds').value||600)});result('moderation-result',data.message||'已执行');await loadMembers(true);}catch(error){result('moderation-result',error.message,true);}}); document.getElementById('moderation-mute-all')?.addEventListener('click',async()=>{if(!confirm('确认禁言所有普通成员吗？'))return;try{const data=await post('/api/moderation',{scope_id:scope(),action:'mute_all',duration_seconds:Number(document.getElementById('moderation-seconds').value||600)});result('moderation-result',data.message||'已执行');}catch(error){result('moderation-result',error.message,true);}}); document.getElementById('moderation-unmute-all')?.addEventListener('click',async()=>{if(!confirm('确认解除所有普通成员禁言吗？'))return;try{const data=await post('/api/moderation',{scope_id:scope(),action:'unmute_all'});result('moderation-result',data.message||'已执行');}catch(error){result('moderation-result',error.message,true);}});
    document.getElementById('user-reply-save')?.addEventListener('click',async()=>{const userId=memberValue('user-reply-member','user-reply-member-direct');if(!userId)return result('user-reply-result','请填写成员 QQ号或官方 OpenID',true);try{await post('/api/user-replies',{scope_id:scope(),user_id:userId,trigger:document.getElementById('user-reply-trigger').value.trim(),response:document.getElementById('user-reply-response').value.trim(),match_mode:document.getElementById('user-reply-mode').value});result('user-reply-result','已保存');refreshUserReplies();}catch(error){result('user-reply-result',error.message,true);}}); document.getElementById('user-reply-refresh')?.addEventListener('click',refreshUserReplies);
    document.getElementById('group-admin-save')?.addEventListener('click',async()=>{const userId=memberValue('group-admin-member','group-admin-member-direct');if(!userId)return result('group-admin-result','请填写成员 QQ号或官方 OpenID',true);try{await post('/api/group-admins',{scope_id:scope(),user_id:userId,display_name:document.getElementById('group-admin-note').value.trim()});result('group-admin-result','已保存');refreshAdmins();}catch(error){result('group-admin-result',error.message,true);}}); document.getElementById('group-admin-refresh')?.addEventListener('click',refreshAdmins);
    const taskType=document.getElementById('task-type'); const syncTaskFields=()=>{const type=taskType.value;document.getElementById('task-content-label').hidden=!['broadcast','song'].includes(type);document.getElementById('task-mute-label').hidden=type!=='mute_all';}; taskType?.addEventListener('change',syncTaskFields); syncTaskFields(); document.getElementById('task-save')?.addEventListener('click',async()=>{const raw=document.getElementById('task-run-at').value;const runAt=Math.floor(new Date(raw).getTime()/1000);try{await post('/api/tasks',{scope_id:scope(),task_type:taskType.value,run_at:runAt,content:document.getElementById('task-content').value.trim(),mute_seconds:Number(document.getElementById('task-mute-seconds').value||0)});result('task-result','任务已创建');refreshTasks();}catch(error){result('task-result',error.message,true);}}); document.getElementById('task-refresh')?.addEventListener('click',refreshTasks);
     document.getElementById('approval-direct-on')?.addEventListener('click',async()=>{try{await post('/api/join-approval/direct',{scope_id:scope(),enabled:true});result('approval-result','已开启自动审批策略，请加入白名单 QQ号');refreshApproval();}catch(error){result('approval-result',error.message,true);}}); document.getElementById('approval-direct-off')?.addEventListener('click',async()=>{try{await post('/api/join-approval/direct',{scope_id:scope(),enabled:false});result('approval-result','已关闭官方自动审批策略');refreshApproval();}catch(error){result('approval-result',error.message,true);}}); document.getElementById('approval-whitelist-add')?.addEventListener('click',()=>updateApprovalWhitelist('add')); document.getElementById('approval-whitelist-del')?.addEventListener('click',()=>updateApprovalWhitelist('del')); document.getElementById('approval-execute')?.addEventListener('click',async()=>{try{const state=await get(`/api/join-approval/state?scope_id=${encodeURIComponent(scope())}`);if(!state.strategy_id)return result('approval-result','请先开启自动审批策略',true);await post('/api/join-approval-strategies/execute',{scope_id:scope(),strategy_id:state.strategy_id});result('approval-result','已提交处理现有申请，官方异步执行');}catch(error){result('approval-result',error.message,true);}}); document.getElementById('approval-refresh')?.addEventListener('click',refreshApproval);
    document.getElementById('license-redeem')?.addEventListener('click',async()=>{try{await post('/api/license/redeem',{card_code:document.getElementById('license-card').value.trim()});result('license-result','授权已生效，现在可以绑定官方群。');document.getElementById('license-card').value='';refreshLicense();}catch(error){result('license-result',error.message,true);}}); document.getElementById('password-reset-send')?.addEventListener('click',async()=>{try{const data=await post('/api/profile/password/code',{});result('password-reset-result',data.message||'验证码已发送');}catch(error){result('password-reset-result',error.message,true);}}); document.getElementById('password-reset-save')?.addEventListener('click',async()=>{try{await post('/api/profile/password/reset',{verification_code:document.getElementById('password-reset-code').value.trim(),password:document.getElementById('password-reset-value').value});result('password-reset-result','密码已修改');document.getElementById('password-reset-code').value='';document.getElementById('password-reset-value').value='';}catch(error){result('password-reset-result',error.message,true);}});
  };
  const hydrate = async () => { try { await loadMembers(); await Promise.all([refreshReplies(),refreshMessages(),refreshUserReplies(),refreshAdmins(),refreshTasks(),refreshApproval(),refreshLicense()]); } catch (error) {} };
  const init = () => { addViews(); fillMemberOptions(); bind(); if (!document.body.dataset.overlayNavBound) { document.body.dataset.overlayNavBound='1'; document.addEventListener('click',(event)=>{const button=event.target.closest('[data-view]'); const id=button?.dataset.view; if (id==='messages') { event.preventDefault(); event.stopImmediatePropagation(); show('messages','群消息记录','仅保留发送时间、发送成员、身份和撤回备注。'); } if (id==='replies') { event.preventDefault(); event.stopImmediatePropagation(); show('replies','自动回复','配置精准回复和模糊回复。'); }},true); } const when=new Date(Date.now()+3600000); const taskTime=document.getElementById('task-run-at'); if (taskTime && !taskTime.value) taskTime.value=new Date(when.getTime()-when.getTimezoneOffset()*60000).toISOString().slice(0,16); const select=document.getElementById('scope-switch'); if (select && !select.dataset.overlayBound) { select.dataset.overlayBound='1'; select.addEventListener('change',()=>{memberScope='';members=[];setTimeout(hydrate,120);}); } hydrate(); };
  init(); setTimeout(init, 700); setTimeout(init, 1800);
})();
</script>
"""


FUNCTION_USAGE_OVERLAY = r"""
<script>
(() => {
  const usage = {
    groups: '每个官方群单独授权、单独保存配置。授权到期后，该群的功能会停止执行。',
    bind: '先在目标群发送 /绑定官方群 数字QQ群号；再填写同一 QQ 群号和一张未使用授权卡。授权卡只授权该群，不会授权账号。多个群需要逐个重复此步骤并各用一张卡。',
    settings: '填写服务器 ID 后保存；群内使用 绑定id、解绑、查询在线，使用 查询 关键词 搜索服务器。',
    replies: '填写触发词和回复内容，选择精准或模糊匹配后保存；成员发送对应文字即可。',
    'keyword-mute': '填写关键词和禁言秒数后保存；成员命中关键词时按当前规则执行。',
    'keyword-kick': '填写关键词后保存；成员命中关键词时按当前规则执行。',
    'keyword-blacklist': '填写关键词后保存；成员命中关键词时按当前规则执行。',
    blacklist: '从成员列表选择成员后保存；需要解除时，在黑名单列表选择删除。',
    moderation: '选择成员、操作和时长后执行；全体操作直接选择“全体禁言”或“全体解禁”。',
    'user-replies': '选择成员，填写触发词和回复内容，选择匹配方式后保存。',
    'group-admins': '从成员列表选择成员后保存；需要取消时，在已设置列表删除。',
    schedules: '选择执行时间和任务类型；填写消息内容或禁言秒数后创建任务。',
    approval: '使用“开启直接入群”或“关闭直接入群”；有入群申请时，在申请列表处理。',
    messages: '选择成员后执行撤回；刷新列表查看发送时间、成员和撤回状态。',
    profile: '保存账号资料；需要修改密码时先发送邮箱验证码。授权卡只在“绑定群授权”中使用。',
  };
  const addGuide = (viewId) => {
    const view = document.getElementById(viewId);
    const text = usage[viewId];
    if (!view || !text || view.querySelector('.joker-usage-guide')) return;
    const panel = document.createElement('section');
    panel.className = 'panel joker-usage-guide';
    panel.innerHTML = `<div class="panel-head"><div><h2>使用方式</h2><p class="muted">${text}</p></div></div>`;
    view.prepend(panel);
  };
  const install = () => Object.keys(usage).forEach(addGuide);
  install();
  new MutationObserver(install).observe(document.body, {childList:true, subtree:true});
  setTimeout(install, 700); setTimeout(install, 1800);
})();
</script>
<script>
(() => {
  const installBinding = () => {
    const view = document.getElementById('bind');
    const form = view?.querySelector('.form');
    const scope = document.getElementById('bind-scope');
    const button = document.getElementById('bind-group');
    const result = document.getElementById('bind-result');
    if (!view || !form || !scope || !button || !result) return;
    const summary = view.querySelector('.panel .panel-head p');
    if (summary) summary.textContent = '填写授权卡密和目标 QQ 群号后完成绑定。授权卡只授权当前群；一个账号可以绑定并管理多个已授权群。';
    scope.closest('label').firstChild.textContent = '目标 QQ 群号';
    scope.placeholder = '例如 1102579807';
    if (!document.getElementById('bind-card')) {
      const label = document.createElement('label');
      label.innerHTML = '授权卡密<input id="bind-card" autocomplete="off" placeholder="JOKER-XXXXXXXXXX">';
      form.prepend(label); form.classList.remove('two');
    }
    const guide = view.querySelector('.split > .panel:nth-child(2)');
    if (guide) guide.innerHTML = '<h3>绑定步骤</h3><p class="muted">1. 把机器人拉入目标群。2. 在目标群发送 <code>/绑定官方群 QQ群号</code>。3. 在本页填写同一群号和一张未使用授权卡后点击绑定。成功后，该卡只授权这个群，并显示到期时间。每增加一个群，重复以上步骤并使用另一张卡。</p>';
    if (button.dataset.jokerBindBound) return;
    button.dataset.jokerBindBound = '1';
    button.onclick = async () => {
      const cardCode = document.getElementById('bind-card')?.value.trim();
      const groupId = scope.value.trim();
      if (!cardCode || !groupId) { result.textContent = '请填写授权卡密和目标 QQ 群号。'; result.classList.add('error'); return; }
      try {
        const response = await fetch('/api/user/groups/bind', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope_id:groupId, card_code:cardCode})});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || '绑定失败');
        result.textContent = data.message || '官方群已绑定，可开始配置功能。'; result.classList.remove('error');
        document.getElementById('bind-card').value = '';
        setTimeout(() => location.reload(), 650);
      } catch (error) { result.textContent = error.message; result.classList.add('error'); }
    };
  };
  installBinding(); setTimeout(installBinding, 400); setTimeout(installBinding, 1200);
})();
</script>
<script>
(() => {
  const formatTime = (value) => value ? new Date(Number(value) * 1000).toLocaleString() : '永久';
  const installGroupAuthorizationStatus = async () => {
    const legacyLicensePanel = document.getElementById('license-panel');
    if (legacyLicensePanel) legacyLicensePanel.hidden = true;
    const groupsView = document.getElementById('groups');
    if (!groupsView || groupsView.querySelector('#joker-group-authorization-status')) return;
    try {
      const response = await fetch('/api/groups');
      const groups = await response.json();
      if (!response.ok || !Array.isArray(groups)) return;
      const panel = document.createElement('section');
      panel.className = 'panel';
      panel.id = 'joker-group-authorization-status';
      const rows = groups.map((group) => {
        const name = group.numeric_group_id || group.scope_id;
        const state = group.authorization_active ? '已授权' : '待授权';
        const expiry = group.authorization_active ? `到期：${formatTime(group.authorization_expires_at)}` : '请到“绑定群授权”使用一张未使用卡';
        return `<div class="joker-auth-row"><strong>${name}</strong><span>${state}</span><small>${expiry}</small></div>`;
      }).join('') || '<p class="muted">暂无已绑定官方群。</p>';
      panel.innerHTML = `<div class="panel-head"><div><h2>群授权状态</h2><p class="muted">授权卡只授权官方群，不授权登录账号。一个账号可管理多个群，但每个群都需要单独使用一张授权卡。</p></div></div><div class="joker-auth-list">${rows}</div>`;
      groupsView.prepend(panel);
    } catch (_) {}
  };
  installGroupAuthorizationStatus();
  setTimeout(installGroupAuthorizationStatus, 800);
})();
</script>
"""
