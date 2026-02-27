window.HypeBotModule = (function() {
    let prompts = [];
    let flows = [];
    let flowSteps = {};
    let _editorFlowId = null;
    let _listSearchQuery = '';
    let _listStatusFilter = 'all';

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    const TG_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z"/></svg>';

    const ALL_DAYS = ['mon','tue','wed','thu','fri','sat','sun'];
    const DAY_LABELS = {mon:'Mon',tue:'Tue',wed:'Wed',thu:'Thu',fri:'Fri',sat:'Sat',sun:'Sun'};

    const STEP_TYPE_ICON = { reforward: '↩', cta: '🔗', message: '💬', ai_hype: '✨' };
    const STEP_TYPE_LABEL = { reforward: 'Re-forward', cta: 'CTA', message: 'Plain Text', ai_hype: 'AI Hype' };
    const REFORWARD_PRESET_LABEL = {
        best_tp: 'Best TP (TP3→TP2→TP1)',
        daily_recap: 'Daily Recap',
        weekly_recap: 'Weekly Recap',
        signal: 'Signal Entry'
    };

    function parseDaysString(str) {
        if (!str || str.trim().toLowerCase() === 'daily') return [...ALL_DAYS];
        const raw = str.trim().toLowerCase();
        if (raw.includes('-') && !raw.includes(',')) {
            const parts = raw.split('-');
            if (parts.length === 2) {
                const si = ALL_DAYS.indexOf(parts[0]), ei = ALL_DAYS.indexOf(parts[1]);
                if (si >= 0 && ei >= 0) {
                    const result = [];
                    for (let i = si; i !== (ei + 1) % 7; i = (i + 1) % 7) result.push(ALL_DAYS[i]);
                    result.push(ALL_DAYS[ei]);
                    return result;
                }
            }
        }
        return raw.split(',').map(d => d.trim()).filter(d => ALL_DAYS.includes(d));
    }

    function stepSummary(step) {
        const icon = STEP_TYPE_ICON[step.step_type] || '?';
        switch (step.step_type) {
            case 'reforward':
                return `${icon} Re-forward: ${REFORWARD_PRESET_LABEL[step.reforward_preset] || step.reforward_preset}`;
            case 'cta':
                return `${icon} CTA message`;
            case 'message': {
                const txt = (step.message_text || '').trim();
                return `${icon} ${txt.length > 60 ? txt.slice(0, 60) + '…' : (txt || '(empty)')}`;
            }
            case 'ai_hype':
                return `${icon} AI Hype message`;
            default:
                return icon;
        }
    }

    function _fmtDate(isoStr) {
        if (!isoStr) return '—';
        return new Date(isoStr).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
    }

    function _fmtDateShort(isoStr) {
        if (!isoStr) return '—';
        return new Date(isoStr).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
    }

    // ─────────────────────────────────────────────────────────────
    // CONNECTION STATUS
    // ─────────────────────────────────────────────────────────────

    async function loadConnectionStatus() {
        const bar = document.getElementById('hype-connection-bar');
        if (!bar) return;
        try {
            const headers = await getAuthHeaders();
            const connResp = await fetch('/api/connections', { headers });
            let botUsername = null;
            let freeChannelId = null;
            if (connResp.ok) {
                const connData = await connResp.json();
                const signalBot = (connData.connections || []).find(c => c.bot_role === 'signal_bot');
                botUsername = signalBot?.bot_username || null;
                freeChannelId = signalBot?.free_channel_id || null;
            }
            const connected = !!(botUsername && freeChannelId);
            const dotClass = connected ? 'connected' : 'disconnected';
            const usernameDisplay = botUsername ? escapeHtml(botUsername.startsWith('@') ? botUsername : '@' + botUsername) : 'Not configured';
            const channelDisplay = freeChannelId ? escapeHtml(String(freeChannelId)) : 'Not set';
            bar.innerHTML = `
                <div class="connection-banner">
                    <span class="conn-icon">${TG_ICON}</span>
                    <span class="conn-username">${usernameDisplay}</span>
                    <span class="conn-separator">→</span>
                    <span class="conn-label">FREE: ${channelDisplay}</span>
                    <span class="conn-dot ${dotClass}"></span>
                </div>`;
        } catch (e) { console.error('Error loading connection status:', e); }
    }

    // ─────────────────────────────────────────────────────────────
    // DATA LOADING
    // ─────────────────────────────────────────────────────────────

    async function loadHypeBot() {
        renderListView();
        await Promise.all([loadPrompts(), loadFlows()]);
        await loadConnectionStatus();
    }

    async function loadPrompts() {
        try {
            const headers = await getAuthHeaders();
            const resp = await fetch('/api/hypechat/prompts', { headers });
            const data = await resp.json();
            prompts = data.prompts || [];
        } catch (e) { console.error('Error loading prompts:', e); }
    }

    async function loadFlows() {
        try {
            const headers = await getAuthHeaders();
            const resp = await fetch('/api/hypechat/flows', { headers });
            const data = await resp.json();
            flows = data.flows || [];
            const stepResults = await Promise.all(
                flows.map(f =>
                    fetch(`/api/hypechat/flows/${f.id}/steps`, { headers })
                        .then(r => r.ok ? r.json() : { steps: [] })
                        .then(d => ({ id: f.id, steps: d.steps || [] }))
                        .catch(() => ({ id: f.id, steps: [] }))
                )
            );
            flowSteps = {};
            stepResults.forEach(r => { flowSteps[r.id] = r.steps; });
            renderListView();
        } catch (e) { console.error('Error loading flows:', e); }
    }

    // ─────────────────────────────────────────────────────────────
    // LIST VIEW — table layout
    // ─────────────────────────────────────────────────────────────

    function renderListView() {
        const container = document.getElementById('hype-list-view');
        if (!container) return;

        const filtered = flows.filter(f => {
            if (_listSearchQuery && !f.name.toLowerCase().includes(_listSearchQuery.toLowerCase())) return false;
            if (_listStatusFilter !== 'all' && f.status !== _listStatusFilter) return false;
            return true;
        });

        const tableRows = filtered.map(f => {
            const steps = flowSteps[f.id] || [];
            const parentFlow = f.trigger_after_flow_id ? flows.find(p => p.id === f.trigger_after_flow_id) : null;
            const triggerLabel = f.trigger_after_flow_id
                ? `${f.trigger_delay_minutes || 0}min after ${parentFlow ? parentFlow.name : 'deleted flow'}`
                : (f.trigger_delay_minutes > 0 ? `${f.trigger_delay_minutes}min after Cross Promo` : 'Cross Promo');
            const created = _fmtDateShort(f.created_at);
            const isActive = f.status === 'active';
            const statusColor = isActive ? '#34c759' : '#ff9f0a';
            const statusLabel = isActive ? 'Active' : 'Paused';

            return `<tr data-flow-id="${f.id}" class="hype-flow-row"
                onclick="window.HypeBotModule.editFlow('${f.id}')"
                style="cursor:pointer;border-bottom:1px solid var(--border-primary);transition:background 0.12s;"
                onmouseenter="this.style.background='var(--bg-secondary,rgba(255,255,255,0.03))'"
                onmouseleave="this.style.background='transparent'">
                <td style="padding:14px 16px;font-size:14px;font-weight:500;color:var(--text-primary);">${escapeHtml(f.name)}</td>
                <td style="padding:14px 16px;white-space:nowrap;">
                    <span style="display:inline-flex;align-items:center;gap:7px;font-size:13px;">
                        <span style="width:8px;height:8px;border-radius:50%;background:${statusColor};flex-shrink:0;box-shadow:0 0 6px ${statusColor}55;"></span>
                        <span style="color:${statusColor};font-weight:600;">${statusLabel}</span>
                    </span>
                </td>
                <td style="padding:14px 16px;font-size:13px;color:var(--text-secondary);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(triggerLabel)}</td>
                <td style="padding:14px 16px;font-size:13px;color:var(--text-muted);white-space:nowrap;">${created}</td>
                <td style="padding:14px 16px;text-align:center;font-size:13px;color:var(--text-secondary);">
                    <span style="display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:20px;background:var(--bg-tertiary,rgba(255,255,255,0.06));border:1px solid var(--border-primary);border-radius:10px;padding:0 7px;font-size:11px;font-weight:700;">${steps.length}</span>
                </td>
                <td style="padding:14px 16px;text-align:right;" onclick="event.stopPropagation()">
                    <button
                        onclick="window.HypeBotModule._showFlowMenu('${f.id}', this)"
                        style="background:none;border:1px solid var(--border-primary);border-radius:6px;padding:4px 10px;color:var(--text-secondary);cursor:pointer;font-size:17px;line-height:1;transition:all 0.12s;"
                        onmouseenter="this.style.borderColor='var(--accent,#007aff)';this.style.color='var(--accent,#007aff)'"
                        onmouseleave="this.style.borderColor='var(--border-primary)';this.style.color='var(--text-secondary)'">⋮</button>
                </td>
            </tr>`;
        }).join('');

        const emptyHtml = filtered.length === 0 ? `
            <tr><td colspan="6" style="padding:60px 24px;text-align:center;color:var(--text-muted);font-size:14px;font-style:italic;">
                ${flows.length === 0 ? 'No flows yet. Click <strong style="font-style:normal;color:var(--text-secondary);">+ New Flow</strong> to get started.' : 'No flows match your filter.'}
            </td></tr>` : '';

        const filterBtn = (val, label) => {
            const isActive = _listStatusFilter === val;
            return `<button onclick="window.HypeBotModule._onListStatusFilter('${val}')"
                style="padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;transition:all 0.15s;
                border:1px solid ${isActive ? 'var(--accent,#007aff)' : 'var(--border-primary)'};
                background:${isActive ? 'rgba(0,122,255,0.12)' : 'none'};
                color:${isActive ? 'var(--accent,#007aff)' : 'var(--text-secondary)'};">${label}</button>`;
        };

        container.innerHTML = `
            <div style="padding:24px 24px 0;display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;">
                <div>
                    <h2 style="margin:0 0 2px 0;font-size:22px;font-weight:700;color:var(--text-primary);">Hype Flows</h2>
                    <span style="font-size:13px;color:var(--text-muted);">${flows.length} flow${flows.length !== 1 ? 's' : ''}</span>
                </div>
                <button onclick="window.HypeBotModule.openFlowModal()"
                    style="display:inline-flex;align-items:center;gap:6px;padding:9px 18px;background:var(--accent,#007aff);color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap;flex-shrink:0;">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>
                    New Flow
                </button>
            </div>
            <div id="hype-connection-bar" style="padding:10px 24px 0;"></div>
            <div style="padding:12px 24px 16px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                <input type="text" id="hype-list-search" value="${escapeHtml(_listSearchQuery)}" placeholder="Search flows…"
                    oninput="window.HypeBotModule._onListSearch(this.value)"
                    style="flex:1;min-width:160px;max-width:260px;padding:8px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:13px;outline:none;transition:border-color 0.15s;"
                    onfocus="this.style.borderColor='var(--accent,#007aff)'"
                    onblur="this.style.borderColor='var(--border-primary)'">
                <div style="display:flex;gap:4px;">
                    ${filterBtn('all', 'All')}
                    ${filterBtn('active', 'Active')}
                    ${filterBtn('paused', 'Paused')}
                </div>
            </div>
            <div style="overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;min-width:580px;">
                    <thead>
                        <tr style="border-bottom:1px solid var(--border-primary);">
                            <th style="padding:10px 16px;text-align:left;font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Name</th>
                            <th style="padding:10px 16px;text-align:left;font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Status</th>
                            <th style="padding:10px 16px;text-align:left;font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Trigger</th>
                            <th style="padding:10px 16px;text-align:left;font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Created</th>
                            <th style="padding:10px 16px;text-align:center;font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Steps</th>
                            <th style="padding:10px 16px;width:48px;"></th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tableRows}${emptyHtml}
                    </tbody>
                </table>
            </div>`;
    }

    function _onListSearch(value) {
        _listSearchQuery = value;
        const filtered = flows.filter(f => {
            if (value && !f.name.toLowerCase().includes(value.toLowerCase())) return false;
            if (_listStatusFilter !== 'all' && f.status !== _listStatusFilter) return false;
            return true;
        });
        const tbody = document.querySelector('#hype-list-view table tbody');
        if (!tbody) { renderListView(); return; }
        document.querySelectorAll('.hype-flow-row').forEach(row => {
            const fid = row.dataset.flowId;
            const f = flows.find(fl => fl.id === fid);
            if (!f) { row.style.display = 'none'; return; }
            const matchSearch = !value || f.name.toLowerCase().includes(value.toLowerCase());
            const matchStatus = _listStatusFilter === 'all' || f.status === _listStatusFilter;
            row.style.display = (matchSearch && matchStatus) ? '' : 'none';
        });
        _updateEmptyRow(filtered.length);
    }

    function _onListStatusFilter(status) {
        _listStatusFilter = status;
        renderListView();
    }

    function _updateEmptyRow(visibleCount) {
        const tbody = document.querySelector('#hype-list-view table tbody');
        if (!tbody) return;
        let emptyRow = tbody.querySelector('.hype-empty-row');
        if (visibleCount === 0) {
            if (!emptyRow) {
                emptyRow = document.createElement('tr');
                emptyRow.className = 'hype-empty-row';
                emptyRow.innerHTML = `<td colspan="6" style="padding:60px 24px;text-align:center;color:var(--text-muted);font-size:14px;font-style:italic;">No flows match your filter.</td>`;
                tbody.appendChild(emptyRow);
            }
        } else {
            if (emptyRow) emptyRow.remove();
        }
    }

    function _showFlowMenu(flowId, btnEl) {
        document.querySelectorAll('.hype-flow-menu').forEach(m => m.remove());

        const menu = document.createElement('div');
        menu.className = 'hype-flow-menu';
        menu.style.cssText = 'position:fixed;background:var(--bg-secondary,#1a1f2e);border:1px solid var(--border-primary);border-radius:9px;padding:4px;z-index:9999;min-width:140px;box-shadow:0 8px 24px rgba(0,0,0,0.5);';

        const items = [
            { label: '✏ Edit', fn: () => window.HypeBotModule.editFlow(flowId) },
            { label: '⚡ Trigger', fn: () => window.HypeBotModule.triggerFlow(flowId) },
            { label: '🗑 Delete', fn: () => window.HypeBotModule.deleteFlow(flowId), danger: true },
        ];

        items.forEach((item, i) => {
            if (i > 0 && item.danger) {
                const sep = document.createElement('div');
                sep.style.cssText = 'height:1px;background:var(--border-primary);margin:4px 0;';
                menu.appendChild(sep);
            }
            const btn = document.createElement('button');
            btn.textContent = item.label;
            btn.style.cssText = `display:block;width:100%;padding:8px 12px;text-align:left;background:none;border:none;border-radius:6px;font-size:13px;cursor:pointer;color:${item.danger ? '#ff453a' : 'var(--text-primary)'};transition:background 0.1s;`;
            btn.onmouseenter = () => { btn.style.background = item.danger ? 'rgba(255,69,58,0.1)' : 'var(--bg-tertiary,rgba(255,255,255,0.06))'; };
            btn.onmouseleave = () => { btn.style.background = 'none'; };
            btn.onclick = () => { menu.remove(); item.fn(); };
            menu.appendChild(btn);
        });

        document.body.appendChild(menu);
        const rect = btnEl.getBoundingClientRect();
        const menuH = items.length * 36 + 16;
        const spaceBelow = window.innerHeight - rect.bottom;
        if (spaceBelow < menuH && rect.top > menuH) {
            menu.style.top = (rect.top - menuH - 4) + 'px';
        } else {
            menu.style.top = (rect.bottom + 4) + 'px';
        }
        menu.style.right = (window.innerWidth - rect.right) + 'px';

        const closeHandler = (e) => {
            if (!menu.contains(e.target) && e.target !== btnEl) {
                menu.remove();
                document.removeEventListener('click', closeHandler, { capture: true });
            }
        };
        setTimeout(() => document.addEventListener('click', closeHandler, { capture: true }), 0);
    }

    // ─────────────────────────────────────────────────────────────
    // PROMPT MODAL
    // ─────────────────────────────────────────────────────────────

    function openPromptModal(editId) {
        const prompt = editId ? prompts.find(p => p.id === editId) : null;
        const title = prompt ? 'Edit Prompt' : 'New Prompt';
        const modalHtml = `
            <div class="modal-overlay" id="hype-prompt-modal" onclick="if(event.target===this)this.remove()">
                <div class="modal-content" style="max-width:520px;">
                    <div class="modal-header"><h3>${title}</h3><button class="modal-close" onclick="document.getElementById('hype-prompt-modal').remove()">&times;</button></div>
                    <div class="modal-body">
                        <div style="margin-bottom:16px;">
                            <label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Name</label>
                            <input type="text" id="hype-prompt-name" value="${prompt ? escapeHtml(prompt.name) : ''}" placeholder="e.g. Daily Motivation" style="width:100%;padding:10px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;box-sizing:border-box;">
                        </div>
                        <div>
                            <label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Custom Prompt</label>
                            <textarea id="hype-prompt-text" rows="6" placeholder="e.g. Write a motivational message about today's gold trading wins..." style="width:100%;padding:10px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;resize:vertical;font-family:inherit;box-sizing:border-box;">${prompt ? escapeHtml(prompt.custom_prompt) : ''}</textarea>
                            <div style="font-size:11px;color:var(--text-muted);margin-top:4px;">Combined with the EntryLab system prompt and live pip data to generate messages.</div>
                        </div>
                    </div>
                    <div class="modal-footer" style="display:flex;gap:8px;justify-content:flex-end;padding:16px 24px;border-top:1px solid var(--border-primary);">
                        <button class="btn btn-secondary" onclick="document.getElementById('hype-prompt-modal').remove()">Cancel</button>
                        <button class="btn" onclick="window.HypeBotModule.savePrompt('${editId || ''}')">Save</button>
                    </div>
                </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        document.getElementById('hype-prompt-modal').classList.add('active');
        document.getElementById('hype-prompt-name').focus();
    }

    async function savePrompt(editId) {
        const name = document.getElementById('hype-prompt-name').value.trim();
        const customPrompt = document.getElementById('hype-prompt-text').value.trim();
        if (!name || !customPrompt) { alert('Please fill in both fields'); return; }
        try {
            const headers = await getAuthHeaders();
            headers['Content-Type'] = 'application/json';
            const url = editId ? `/api/hypechat/prompts/${editId}` : '/api/hypechat/prompts';
            const resp = await fetch(url, { method: editId ? 'PUT' : 'POST', headers, body: JSON.stringify({ name, custom_prompt: customPrompt }) });
            if (resp.ok) {
                document.getElementById('hype-prompt-modal')?.remove();
                await loadPrompts();
                const sel = document.getElementById('hype-flow-prompt');
                if (sel) {
                    const opts = prompts.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
                    const current = sel.value;
                    sel.innerHTML = `<option value="">None</option>${opts}`;
                    sel.value = current || '';
                }
            } else { const err = await resp.json(); alert(err.error || 'Failed to save'); }
        } catch (e) { console.error('Error saving prompt:', e); }
    }

    function editPrompt(id) { openPromptModal(id); }

    async function deletePrompt(id) {
        if (typeof showModalConfirm === 'function') {
            showModalConfirm('Delete Prompt', 'Are you sure? Flows using this prompt will lose their reference.', 'Delete', async () => { await doDeletePrompt(id); }, true);
        } else { if (confirm('Delete this prompt?')) await doDeletePrompt(id); }
    }
    async function doDeletePrompt(id) {
        try { const h = await getAuthHeaders(); await fetch(`/api/hypechat/prompts/${id}`, { method:'DELETE', headers:h }); await loadPrompts(); } catch(e) { console.error(e); }
    }

    // ─────────────────────────────────────────────────────────────
    // PREVIEW
    // ─────────────────────────────────────────────────────────────

    function _getArcLabel(step, total) {
        if (total === 1) return 'Single';
        if (step === 1) return 'Opening';
        if (step === total) return 'Finale';
        return 'Build-up';
    }

    function _getArcColor(step, total) {
        if (total === 1) return 'var(--accent, #007aff)';
        if (step === 1) return '#34c759';
        if (step === total) return '#ff9f0a';
        return 'var(--accent, #007aff)';
    }

    function _renderTimelineMessages(messages, messageCount, intervalMinutes, delayAfterCta) {
        if (!messages || !messages.length) {
            return '<div class="hype-empty-state">Failed to generate messages</div>';
        }
        const interval = intervalMinutes || 90;
        const delay = delayAfterCta || 10;
        const items = messages.map((msg, i) => {
            const step = i + 1;
            const offsetMin = delay + (i * interval);
            const arcLabel = _getArcLabel(step, messageCount);
            const arcColor = _getArcColor(step, messageCount);
            const isLast = step === messageCount;
            return `
                <div style="display:flex;gap:10px;position:relative;">
                    <div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;width:24px;">
                        <div style="width:22px;height:22px;border-radius:50%;background:${arcColor};display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;">${step}</div>
                        ${!isLast ? '<div style="flex:1;width:1px;background:var(--border-primary);margin:3px 0;"></div>' : ''}
                    </div>
                    <div style="flex:1;padding-bottom:${isLast ? '0' : '10px'};">
                        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
                            <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;">+${offsetMin} min</span>
                            <span style="font-size:9px;font-weight:600;color:${arcColor};background:${arcColor}18;padding:1px 6px;border-radius:8px;text-transform:uppercase;">${escapeHtml(arcLabel)}</span>
                        </div>
                        <div style="background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;padding:8px 10px;">
                            <div style="font-size:12px;color:var(--text-primary);line-height:1.45;">${msg ? escapeHtml(msg) : '<span style="color:var(--text-muted);font-style:italic;">Failed to generate</span>'}</div>
                        </div>
                    </div>
                </div>`;
        }).join('');
        return `<div style="max-height:50vh;overflow-y:auto;padding-right:4px;">${items}</div>`;
    }

    async function previewPrompt(id) {
        const prompt = prompts.find(p => p.id === id);
        if (!prompt) return;
        const defaultCount = (flows.length > 0 && flows[0].message_count) ? flows[0].message_count : 3;
        const defaultInterval = (flows.length > 0 && flows[0].interval_minutes) ? flows[0].interval_minutes : 90;
        const defaultDelay = (flows.length > 0 && flows[0].delay_after_cta_minutes) ? flows[0].delay_after_cta_minutes : 10;
        const modalHtml = `
            <div class="modal-overlay" id="hype-preview-modal" onclick="if(event.target===this)this.remove()">
                <div class="modal-content" style="max-width:540px;">
                    <div class="modal-header"><h3>Flow Preview: ${escapeHtml(prompt.name)}</h3><button class="modal-close" onclick="document.getElementById('hype-preview-modal').remove()">&times;</button></div>
                    <div class="modal-body" style="padding:16px;">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
                            <label style="font-size:12px;font-weight:500;color:var(--text-secondary);white-space:nowrap;">Messages:</label>
                            <input type="number" id="preview-msg-count" min="1" max="10" value="${defaultCount}" style="width:52px;padding:4px 8px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:6px;color:var(--text-primary);font-size:13px;text-align:center;">
                        </div>
                        <div id="preview-loading" style="text-align:center;color:var(--text-muted);padding:30px 0;">
                            <div style="font-size:13px;">Generating flow preview...</div>
                        </div>
                        <div id="preview-result" style="display:none;"></div>
                    </div>
                    <div class="modal-footer" style="display:flex;gap:8px;justify-content:flex-end;padding:16px 24px;border-top:1px solid var(--border-primary);">
                        <button class="btn btn-secondary" onclick="document.getElementById('hype-preview-modal').remove()">Close</button>
                        <button class="btn" onclick="window.HypeBotModule.regeneratePreview('${id}')">Regenerate</button>
                    </div>
                </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        document.getElementById('hype-preview-modal').classList.add('active');
        await doGeneratePreview(prompt.custom_prompt, defaultCount, defaultInterval, defaultDelay);
    }

    async function previewFlow(id) {
        const flow = flows.find(f => f.id === id);
        if (!flow) return;
        const prompt = flow.prompt_id ? prompts.find(p => p.id === flow.prompt_id) : null;
        const customPrompt = prompt ? prompt.custom_prompt : '';
        if (!customPrompt) {
            alert('This flow has no prompt assigned. Please assign a prompt in the sidebar first.');
            return;
        }
        const steps = flowSteps[id] || [];
        const aiStepCount = steps.filter(s => s.step_type === 'ai_hype').length;
        const msgCount = aiStepCount > 0 ? aiStepCount : (flow.message_count || 3);
        const modalHtml = `
            <div class="modal-overlay" id="hype-preview-modal" onclick="if(event.target===this)this.remove()">
                <div class="modal-content" style="max-width:540px;">
                    <div class="modal-header"><h3>Flow Preview: ${escapeHtml(flow.name)}</h3><button class="modal-close" onclick="document.getElementById('hype-preview-modal').remove()">&times;</button></div>
                    <div class="modal-body" style="padding:16px;">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
                            <label style="font-size:12px;font-weight:500;color:var(--text-secondary);white-space:nowrap;">AI Messages:</label>
                            <input type="number" id="preview-msg-count" min="1" max="10" value="${msgCount}" style="width:52px;padding:4px 8px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:6px;color:var(--text-primary);font-size:13px;text-align:center;" readonly>
                        </div>
                        <div id="preview-loading" style="text-align:center;color:var(--text-muted);padding:30px 0;">
                            <div style="font-size:13px;">Generating flow preview...</div>
                            <div style="font-size:11px;margin-top:4px;color:var(--text-muted);">Creating a coherent ${msgCount}-message sequence</div>
                        </div>
                        <div id="preview-result" style="display:none;"></div>
                    </div>
                    <div class="modal-footer" style="display:flex;gap:8px;justify-content:flex-end;padding:16px 24px;border-top:1px solid var(--border-primary);">
                        <button class="btn btn-secondary" onclick="document.getElementById('hype-preview-modal').remove()">Close</button>
                        <button class="btn" onclick="window.HypeBotModule.regenerateFlowPreview('${id}')">Regenerate</button>
                    </div>
                </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        document.getElementById('hype-preview-modal').classList.add('active');
        await doGeneratePreview(customPrompt, msgCount, flow.interval_minutes, flow.delay_after_cta_minutes);
    }

    async function doGeneratePreview(customPrompt, messageCount, intervalMinutes, delayAfterCta) {
        const count = messageCount || 3;
        const interval = intervalMinutes || 90;
        const delay = delayAfterCta || 10;
        try {
            const headers = await getAuthHeaders();
            headers['Content-Type'] = 'application/json';
            const resp = await fetch('/api/hypechat/preview', { method:'POST', headers, body: JSON.stringify({ custom_prompt: customPrompt, message_count: count }) });
            const data = await resp.json();
            document.getElementById('preview-loading').style.display = 'none';
            const r = document.getElementById('preview-result');
            r.style.display = 'block';
            const messages = data.messages || [];
            let timelineHtml;
            if (data.error && (!messages.length || messages.every(m => !m))) {
                timelineHtml = `
                    <div style="text-align:center;padding:24px 16px;">
                        <div style="font-size:13px;font-weight:600;color:#ff453a;margin-bottom:8px;">Failed to generate messages</div>
                        <div style="font-size:12px;color:var(--text-secondary);line-height:1.5;background:rgba(255,69,58,0.08);border:1px solid rgba(255,69,58,0.2);border-radius:8px;padding:10px 14px;text-align:left;word-break:break-word;">${escapeHtml(data.error)}</div>
                    </div>`;
            } else {
                timelineHtml = _renderTimelineMessages(messages, count, interval, delay);
            }
            r.innerHTML = `
                <div style="margin-bottom:10px;">${timelineHtml}</div>
                <div style="background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;padding:8px 10px;">
                    <div style="font-size:10px;text-transform:uppercase;color:var(--text-muted);margin-bottom:4px;font-weight:600;">Context Injected</div>
                    <div style="font-size:11px;color:var(--text-secondary);line-height:1.4;white-space:pre-wrap;">${escapeHtml(data.context || '')}</div>
                </div>`;
        } catch (e) { console.error('Preview error:', e); }
    }

    async function regeneratePreview(id) {
        const prompt = prompts.find(p => p.id === id);
        if (!prompt) return;
        const countEl = document.getElementById('preview-msg-count');
        const messageCount = countEl ? parseInt(countEl.value) || 3 : 3;
        const defaultInterval = (flows.length > 0 && flows[0].interval_minutes) ? flows[0].interval_minutes : 90;
        const defaultDelay = (flows.length > 0 && flows[0].delay_after_cta_minutes) ? flows[0].delay_after_cta_minutes : 10;
        document.getElementById('preview-loading').style.display = 'block';
        document.getElementById('preview-result').style.display = 'none';
        await doGeneratePreview(prompt.custom_prompt, messageCount, defaultInterval, defaultDelay);
    }

    async function regenerateFlowPreview(id) {
        const flow = flows.find(f => f.id === id);
        if (!flow) return;
        const prompt = flow.prompt_id ? prompts.find(p => p.id === flow.prompt_id) : null;
        if (!prompt) return;
        document.getElementById('preview-loading').style.display = 'block';
        document.getElementById('preview-result').style.display = 'none';
        const steps = flowSteps[id] || [];
        const aiStepCount = steps.filter(s => s.step_type === 'ai_hype').length;
        const msgCount = aiStepCount > 0 ? aiStepCount : (flow.message_count || 3);
        await doGeneratePreview(prompt.custom_prompt, msgCount, flow.interval_minutes, flow.delay_after_cta_minutes);
    }

    // ─────────────────────────────────────────────────────────────
    // VIEW SWITCHING
    // ─────────────────────────────────────────────────────────────

    function _showListView() {
        _editorFlowId = null;
        document.querySelectorAll('.hype-flow-menu').forEach(m => m.remove());
        const listView = document.getElementById('hype-list-view');
        const editorView = document.getElementById('hype-editor-view');
        if (listView) listView.style.display = '';
        if (editorView) { editorView.style.display = 'none'; editorView.innerHTML = ''; }
        loadFlows().then(() => loadConnectionStatus());
    }

    function _showEditorView() {
        const listView = document.getElementById('hype-list-view');
        const editorView = document.getElementById('hype-editor-view');
        if (listView) listView.style.display = 'none';
        if (editorView) editorView.style.display = 'flex';
    }

    // ─────────────────────────────────────────────────────────────
    // FLOW EDITOR — tabbed layout with right sidebar
    // ─────────────────────────────────────────────────────────────

    function _buildDayToggles(container, currentDays) {
        ALL_DAYS.forEach(d => {
            const isSelected = currentDays.includes(d);
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.dataset.day = d;
            btn.textContent = DAY_LABELS[d];
            btn.style.cssText = 'padding:5px 9px;border-radius:6px;font-size:12px;font-weight:500;cursor:pointer;border:1px solid var(--border-primary);transition:all 0.15s;';
            if (isSelected) {
                btn.style.background = '#34c759';
                btn.style.color = '#fff';
                btn.style.borderColor = '#34c759';
                btn.dataset.active = 'true';
            } else {
                btn.style.background = 'var(--bg-primary)';
                btn.style.color = 'var(--text-secondary)';
                btn.dataset.active = 'false';
            }
            btn.addEventListener('click', () => {
                const isActive = btn.dataset.active === 'true';
                btn.dataset.active = isActive ? 'false' : 'true';
                if (btn.dataset.active === 'true') {
                    btn.style.background = '#34c759';
                    btn.style.color = '#fff';
                    btn.style.borderColor = '#34c759';
                } else {
                    btn.style.background = 'var(--bg-primary)';
                    btn.style.color = 'var(--text-secondary)';
                    btn.style.borderColor = 'var(--border-primary)';
                }
            });
            container.appendChild(btn);
        });
    }

    function openFlowModal(editId) {
        const flow = editId ? flows.find(f => f.id === editId) : null;
        _editorFlowId = editId || null;

        const otherFlows = flows.filter(f => f.id !== editId);
        const triggerOpts = otherFlows.map(f =>
            `<option value="${f.id}" ${flow && flow.trigger_after_flow_id === f.id ? 'selected' : ''}>${escapeHtml(f.name)}</option>`
        ).join('');
        const sIn = 'width:100%;padding:7px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:7px;color:var(--text-primary);font-size:13px;box-sizing:border-box;';
        const sLbl = 'font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;display:block;';
        const sSec = 'margin-bottom:22px;';

        const flowStatus = flow?.status || null;
        const stepCount = editId ? (flowSteps[editId]?.length || 0) : 0;
        const created = _fmtDate(flow?.created_at);

        const statusColor = flowStatus === 'active' ? '#34c759' : (flowStatus === 'paused' ? '#ff9f0a' : 'var(--text-muted)');
        const statusLabel = flowStatus ? (flowStatus.charAt(0).toUpperCase() + flowStatus.slice(1)) : '—';

        let activateBtnHtml = '';
        if (flowStatus) {
            const isActive = flowStatus === 'active';
            activateBtnHtml = `<button id="hype-editor-activate-btn"
                onclick="window.HypeBotModule._toggleEditorFlowStatus()"
                style="padding:7px 14px;border-radius:7px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;
                border:1px solid ${isActive ? 'rgba(255,159,10,0.5)' : 'rgba(52,199,89,0.5)'};
                background:${isActive ? 'rgba(255,159,10,0.12)' : 'rgba(52,199,89,0.12)'};
                color:${isActive ? '#ff9f0a' : '#34c759'};">
                ${isActive ? '⏸ Pause' : '▶ Activate'}
            </button>`;
        }

        const triggerBtnHtml = editId ? `
            <button onclick="window.HypeBotModule.triggerFlow('${editId}')"
                style="padding:7px 14px;border-radius:7px;font-size:13px;font-weight:500;cursor:pointer;white-space:nowrap;border:1px solid var(--border-primary);background:none;color:var(--text-secondary);">
                ⚡ Trigger
            </button>` : '';

        const previewBtnHtml = editId ? `
            <button onclick="window.HypeBotModule.previewFlow('${editId}')"
                style="padding:7px 14px;border-radius:7px;font-size:13px;font-weight:500;cursor:pointer;white-space:nowrap;border:1px solid var(--border-primary);background:none;color:var(--text-secondary);">
                Preview
            </button>` : '';

        const editorView = document.getElementById('hype-editor-view');
        if (!editorView) return;

        editorView.innerHTML = `
            <div style="flex-shrink:0;display:flex;align-items:center;gap:10px;padding:11px 20px;border-bottom:1px solid var(--border-primary);background:var(--bg-secondary,rgba(0,0,0,0.12));flex-wrap:wrap;min-height:52px;">
                <button onclick="window.HypeBotModule._showListView()"
                    style="display:inline-flex;align-items:center;gap:5px;padding:6px 12px;border:1px solid var(--border-primary);border-radius:7px;background:none;color:var(--text-secondary);font-size:13px;cursor:pointer;white-space:nowrap;flex-shrink:0;transition:all 0.12s;"
                    onmouseenter="this.style.borderColor='var(--accent,#007aff)';this.style.color='var(--accent,#007aff)'"
                    onmouseleave="this.style.borderColor='var(--border-primary)';this.style.color='var(--text-secondary)'">
                    ← Flows
                </button>
                <input type="text" id="hype-flow-name" value="${flow ? escapeHtml(flow.name) : ''}"
                    placeholder="Flow name…"
                    style="flex:1;min-width:140px;padding:7px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:7px;color:var(--text-primary);font-size:15px;font-weight:600;box-sizing:border-box;outline:none;transition:border-color 0.15s;"
                    onfocus="this.style.borderColor='var(--accent,#007aff)'"
                    onblur="this.style.borderColor='var(--border-primary)'">
                <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;flex-wrap:wrap;">
                    ${previewBtnHtml}
                    ${activateBtnHtml}
                    ${triggerBtnHtml}
                </div>
            </div>
            <div style="flex-shrink:0;display:flex;align-items:center;border-bottom:1px solid var(--border-primary);padding:0 20px;background:var(--bg-secondary,rgba(0,0,0,0.08));">
                <button id="hype-tab-builder" onclick="window.HypeBotModule._switchEditorTab('builder')"
                    style="padding:11px 16px;font-size:13px;font-weight:600;cursor:pointer;background:none;border:none;border-bottom:2px solid var(--accent,#007aff);color:var(--text-primary);margin-bottom:-1px;transition:all 0.15s;">
                    Flow Builder
                </button>
                <button id="hype-tab-analytics" onclick="window.HypeBotModule._switchEditorTab('analytics')"
                    style="padding:11px 16px;font-size:13px;font-weight:500;cursor:pointer;background:none;border:none;border-bottom:2px solid transparent;color:var(--text-muted);margin-bottom:-1px;transition:all 0.15s;">
                    Analytics
                </button>
            </div>
            <div style="flex:1;display:flex;overflow:hidden;min-height:0;">
                <div id="hype-editor-main" style="flex:1;overflow-y:auto;padding:28px 24px;">
                    <div id="hype-editor-pipeline-wrap">
                        <div id="hype-editor-pipeline" style="max-width:560px;margin:0 auto;">
                            ${editId
                                ? '<div style="text-align:center;color:var(--text-muted);font-size:13px;padding:20px;">Loading steps…</div>'
                                : '<div style="text-align:center;color:var(--text-muted);font-size:14px;padding:48px 20px;line-height:1.6;font-style:italic;">Save your flow settings to start adding steps.</div>'}
                        </div>
                    </div>
                    <div id="hype-analytics-inline" style="display:none;max-width:680px;margin:0 auto;"></div>
                </div>
                <div style="width:272px;flex-shrink:0;border-left:1px solid var(--border-primary);overflow-y:auto;padding:20px 16px;background:var(--bg-secondary,rgba(0,0,0,0.08));">
                    <div style="${sSec}">
                        <label style="${sLbl}">Trigger</label>
                        <div style="display:flex;align-items:center;gap:6px;margin-bottom:7px;">
                            <input type="number" id="hype-flow-trigger-delay" min="0" value="${flow ? (flow.trigger_delay_minutes || 0) : 0}"
                                style="width:58px;padding:7px 8px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:7px;color:var(--text-primary);font-size:13px;text-align:center;box-sizing:border-box;">
                            <span style="font-size:12px;color:var(--text-muted);white-space:nowrap;">min after</span>
                        </div>
                        <select id="hype-flow-trigger-after" style="${sIn}">
                            <option value="">Cross Promo</option>
                            ${triggerOpts}
                        </select>
                    </div>
                    <div style="${sSec}">
                        <label style="${sLbl}">Active Days</label>
                        <div id="hype-day-toggles" style="display:flex;gap:4px;flex-wrap:wrap;"></div>
                    </div>
                    <button onclick="window.HypeBotModule.saveFlowSettings()"
                        id="hype-sidebar-save-btn"
                        style="width:100%;padding:9px 16px;background:var(--accent,#007aff);color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;margin-bottom:20px;transition:opacity 0.15s;">
                        Save Settings
                    </button>
                    <div style="border-top:1px solid var(--border-primary);margin-bottom:16px;"></div>
                    <div style="display:flex;flex-direction:column;gap:11px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:12px;color:var(--text-muted);">Created</span>
                            <span style="font-size:12px;color:var(--text-secondary);">${created}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:12px;color:var(--text-muted);">Status</span>
                            <span id="hype-sidebar-status" style="font-size:12px;font-weight:600;color:${statusColor};">${statusLabel}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:12px;color:var(--text-muted);">Steps</span>
                            <span id="hype-sidebar-steps" style="font-size:12px;color:var(--text-secondary);">${stepCount}</span>
                        </div>
                    </div>
                </div>
            </div>`;

        _showEditorView();

        const currentDays = flow ? parseDaysString(flow.active_days || '') : ['mon','tue','wed','thu','fri'];
        const toggleContainer = document.getElementById('hype-day-toggles');
        _buildDayToggles(toggleContainer, currentDays);

        if (editId) {
            _refreshEditorPipeline(editId);
        }
    }

    function _switchEditorTab(tab) {
        const builderTab = document.getElementById('hype-tab-builder');
        const analyticsTab = document.getElementById('hype-tab-analytics');
        const pipelineWrap = document.getElementById('hype-editor-pipeline-wrap');
        const analyticsDiv = document.getElementById('hype-analytics-inline');

        if (tab === 'builder') {
            if (builderTab) { builderTab.style.borderBottomColor = 'var(--accent,#007aff)'; builderTab.style.color = 'var(--text-primary)'; builderTab.style.fontWeight = '600'; }
            if (analyticsTab) { analyticsTab.style.borderBottomColor = 'transparent'; analyticsTab.style.color = 'var(--text-muted)'; analyticsTab.style.fontWeight = '500'; }
            if (pipelineWrap) pipelineWrap.style.display = '';
            if (analyticsDiv) analyticsDiv.style.display = 'none';
        } else {
            if (analyticsTab) { analyticsTab.style.borderBottomColor = 'var(--accent,#007aff)'; analyticsTab.style.color = 'var(--text-primary)'; analyticsTab.style.fontWeight = '600'; }
            if (builderTab) { builderTab.style.borderBottomColor = 'transparent'; builderTab.style.color = 'var(--text-muted)'; builderTab.style.fontWeight = '500'; }
            if (pipelineWrap) pipelineWrap.style.display = 'none';
            if (analyticsDiv) {
                analyticsDiv.style.display = '';
                if (!analyticsDiv.dataset.loaded && _editorFlowId) {
                    analyticsDiv.dataset.loaded = '1';
                    _renderAnalyticsInline(_editorFlowId);
                }
            }
        }
    }

    async function _toggleEditorFlowStatus() {
        const flow = flows.find(f => f.id === _editorFlowId);
        if (!flow) return;
        const newStatus = flow.status === 'active' ? 'paused' : 'active';
        await setFlowStatus(_editorFlowId, newStatus);
        const activateBtn = document.getElementById('hype-editor-activate-btn');
        if (activateBtn) _updateActivateBtn(activateBtn, newStatus);
        const statusEl = document.getElementById('hype-sidebar-status');
        if (statusEl) {
            statusEl.textContent = newStatus.charAt(0).toUpperCase() + newStatus.slice(1);
            statusEl.style.color = newStatus === 'active' ? '#34c759' : '#ff9f0a';
        }
    }

    function _updateActivateBtn(btn, status) {
        const isActive = status === 'active';
        btn.textContent = isActive ? '⏸ Pause' : '▶ Activate';
        btn.style.background = isActive ? 'rgba(255,159,10,0.12)' : 'rgba(52,199,89,0.12)';
        btn.style.color = isActive ? '#ff9f0a' : '#34c759';
        btn.style.borderColor = isActive ? 'rgba(255,159,10,0.5)' : 'rgba(52,199,89,0.5)';
    }

    async function _renderAnalyticsInline(flowId) {
        const container = document.getElementById('hype-analytics-inline');
        if (!container) return;
        container.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:60px 24px;font-size:13px;">Loading analytics…</div>';
        try {
            const h = await getAuthHeaders();
            const resp = await fetch(`/api/hypechat/flows/${flowId}/analytics`, { headers: h });
            const data = await resp.json();
            const msgs = data.messages || [];
            const msgsHtml = msgs.length ? msgs.map(m => `
                <div style="background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:10px;padding:14px 16px;margin-bottom:10px;">
                    <div style="font-size:13px;color:var(--text-primary);line-height:1.55;margin-bottom:8px;">${escapeHtml(m.content_sent || '')}</div>
                    <div style="display:flex;gap:12px;font-size:11px;color:var(--text-muted);">
                        <span>Step ${m.step_number}</span>
                        <span>${new Date(m.sent_at).toLocaleString()}</span>
                    </div>
                </div>`).join('')
                : '<div style="text-align:center;color:var(--text-muted);font-size:13px;padding:40px 20px;font-style:italic;">No messages sent yet</div>';

            container.innerHTML = `
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:28px;">
                    <div style="background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:12px;padding:22px;text-align:center;">
                        <div style="font-size:34px;font-weight:700;color:var(--text-primary);">${data.total_messages || 0}</div>
                        <div style="font-size:12px;color:var(--text-muted);margin-top:5px;">Total Messages</div>
                    </div>
                    <div style="background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:12px;padding:22px;text-align:center;">
                        <div style="font-size:34px;font-weight:700;color:var(--text-primary);">${data.today_message_count || 0}</div>
                        <div style="font-size:12px;color:var(--text-muted);margin-top:5px;">Today</div>
                    </div>
                </div>
                <h4 style="font-size:14px;font-weight:600;color:var(--text-primary);margin:0 0 14px 0;">Recent Messages</h4>
                ${msgsHtml}`;
        } catch (e) {
            const c = document.getElementById('hype-analytics-inline');
            if (c) c.innerHTML = '<div style="text-align:center;color:#ff453a;padding:60px 24px;font-size:13px;">Failed to load analytics</div>';
        }
    }

    async function saveFlowSettings() {
        const editId = _editorFlowId;
        const name = (document.getElementById('hype-flow-name')?.value || '').trim();
        const triggerAfterFlowId = document.getElementById('hype-flow-trigger-after')?.value || null;
        const triggerDelayMinutes = parseInt(document.getElementById('hype-flow-trigger-delay')?.value) || 0;
        const selectedDays = Array.from(document.querySelectorAll('#hype-day-toggles button[data-active="true"]')).map(b => b.dataset.day);

        if (!name) { alert('Please enter a flow name'); return; }
        if (selectedDays.length === 0) { alert('Please select at least one active day'); return; }

        const payload = {
            name,
            active_days: selectedDays.join(','),
            trigger_after_flow_id: triggerAfterFlowId || null,
            trigger_delay_minutes: triggerDelayMinutes,
        };
        if (!editId) {
            payload.message_count = 3;
            payload.interval_minutes = 90;
            payload.interval_max_minutes = 90;
            payload.delay_after_cta_minutes = 10;
        }

        const saveBtn = document.getElementById('hype-sidebar-save-btn');
        if (saveBtn) { saveBtn.textContent = 'Saving…'; saveBtn.disabled = true; }

        try {
            const headers = await getAuthHeaders();
            headers['Content-Type'] = 'application/json';
            const url = editId ? `/api/hypechat/flows/${editId}` : '/api/hypechat/flows';
            const resp = await fetch(url, { method: editId ? 'PUT' : 'POST', headers, body: JSON.stringify(payload) });

            if (resp.ok) {
                const data = await resp.json();
                if (!editId && data.id) {
                    _editorFlowId = data.id;
                    await loadFlows();
                    openFlowModal(data.id);
                } else {
                    await loadFlows();
                    if (saveBtn) {
                        saveBtn.textContent = 'Saved ✓';
                        saveBtn.disabled = false;
                        setTimeout(() => { if (saveBtn) saveBtn.textContent = 'Save Settings'; }, 1800);
                    }
                    const stepsEl = document.getElementById('hype-sidebar-steps');
                    if (stepsEl && _editorFlowId) stepsEl.textContent = (flowSteps[_editorFlowId]?.length || 0);
                }
            } else {
                const err = await resp.json();
                alert(err.error || 'Failed to save');
                if (saveBtn) { saveBtn.textContent = 'Save Settings'; saveBtn.disabled = false; }
            }
        } catch (e) {
            console.error('Error saving flow:', e);
            if (saveBtn) { saveBtn.textContent = 'Save Settings'; saveBtn.disabled = false; }
        }
    }

    function saveFlow(editId) { return saveFlowSettings(); }

    function editFlow(id) { openFlowModal(id); }

    async function deleteFlow(id) {
        if (typeof showModalConfirm === 'function') {
            showModalConfirm('Delete Flow', 'Delete this flow? All message history will be lost.', 'Delete', async () => { await doDeleteFlow(id); }, true);
        } else { if (confirm('Delete this flow?')) await doDeleteFlow(id); }
    }
    async function doDeleteFlow(id) {
        try {
            const h = await getAuthHeaders();
            await fetch(`/api/hypechat/flows/${id}`, { method:'DELETE', headers:h });
            if (_editorFlowId === id) _showListView();
            else await loadFlows();
        } catch(e) { console.error(e); }
    }

    async function setFlowStatus(id, status) {
        try {
            const h = await getAuthHeaders(); h['Content-Type'] = 'application/json';
            await fetch(`/api/hypechat/flows/${id}/status`, { method:'POST', headers:h, body: JSON.stringify({ status }) });
            const flowObj = flows.find(f => f.id === id);
            if (flowObj) flowObj.status = status;
        } catch (e) { console.error(e); }
    }

    function viewAnalytics(flowId) {
        openFlowModal(flowId);
        _switchEditorTab('analytics');
    }

    async function triggerFlow(id) {
        const flow = flows.find(f => f.id === id);
        if (!flow) return;
        const steps = flowSteps[id] || [];
        const stepDesc = steps.length > 0
            ? `${steps.length} steps`
            : `${flow.message_count} messages${flow.cta_enabled ? ' + CTA' : ''}`;
        const confirmed = await showModalConfirm('Trigger Flow',
            `Manually trigger "${escapeHtml(flow.name)}"? This will schedule ${stepDesc}.`,
            { confirmText: 'Trigger' });
        if (confirmed) await doTriggerFlow(id);
    }
    async function doTriggerFlow(id) {
        try {
            const h = await getAuthHeaders(); h['Content-Type'] = 'application/json';
            const resp = await fetch(`/api/hypechat/flows/${id}/trigger`, { method:'POST', headers:h });
            const data = await resp.json();
            if (data.success) showModalAlert('Success', `Scheduled ${data.messages_scheduled} messages`);
            else showModalAlert('Error', data.error || 'Failed to trigger');
        } catch (e) {
            console.error(e);
            showModalAlert('Error', 'Failed to trigger flow');
        }
    }

    // ─────────────────────────────────────────────────────────────
    // INLINE PIPELINE BUILDER
    // ─────────────────────────────────────────────────────────────

    async function _refreshEditorPipeline(flowId) {
        const pipelineEl = document.getElementById('hype-editor-pipeline');
        if (!pipelineEl) return;
        pipelineEl.innerHTML = '<div style="text-align:center;color:var(--text-muted);font-size:13px;padding:20px;">Loading…</div>';
        try {
            const headers = await getAuthHeaders();
            const resp = await fetch(`/api/hypechat/flows/${flowId}/steps`, { headers });
            const data = await resp.json();
            const steps = data.steps || [];
            flowSteps[flowId] = steps;
            _renderPipelineNodes(flowId, steps);
            const stepsEl = document.getElementById('hype-sidebar-steps');
            if (stepsEl) stepsEl.textContent = steps.length;
        } catch (e) {
            const pEl = document.getElementById('hype-editor-pipeline');
            if (pEl) pEl.innerHTML = '<div style="font-size:12px;color:#ff453a;text-align:center;padding:20px;">Failed to load steps</div>';
        }
    }

    function _connector() {
        return '<div style="width:2px;height:22px;background:var(--border-primary);margin:0 auto;"></div>';
    }

    function _addZoneHtml(flowId, afterStepId) {
        const zoneId = 'hype-add-' + (afterStepId || 'start');
        return `<div id="${zoneId}" style="display:flex;justify-content:center;position:relative;">
            <button type="button"
                onclick="window.HypeBotModule.insertStepInline('${flowId}', ${afterStepId ? `'${afterStepId}'` : 'null'})"
                style="width:28px;height:28px;border-radius:50%;border:1.5px solid var(--border-primary);background:var(--bg-secondary,rgba(255,255,255,0.04));color:var(--text-muted);font-size:16px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.15s;"
                onmouseover="this.style.borderColor='var(--accent,#007aff)';this.style.color='var(--accent,#007aff)';this.style.background='rgba(0,122,255,0.1)'"
                onmouseout="this.style.borderColor='var(--border-primary)';this.style.color='var(--text-muted)';this.style.background='var(--bg-secondary,rgba(255,255,255,0.04))'">+</button>
        </div>`;
    }

    function _stepCardHtml(flowId, step, idx) {
        const cardId = 'hype-step-card-' + step.id;
        const delayLabel = `+${step.delay_minutes || 0} min`;
        const summary = stepSummary(step);
        const truncated = summary.length > 65 ? summary.slice(0, 64) + '…' : summary;
        return `<div id="${cardId}">
            <div style="display:flex;align-items:center;gap:10px;background:var(--bg-secondary,rgba(255,255,255,0.03));border:1px solid var(--border-primary);border-radius:10px;padding:12px 14px;">
                <div style="flex-shrink:0;width:24px;height:24px;border-radius:50%;background:var(--bg-tertiary,rgba(255,255,255,0.08));border:1px solid var(--border-primary);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--text-muted);">${idx + 1}</div>
                <div style="flex:1;min-width:0;">
                    <div style="font-size:13px;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(truncated)}</div>
                </div>
                <div style="flex-shrink:0;padding:2px 8px;background:var(--bg-tertiary,rgba(255,255,255,0.06));border:1px solid var(--border-primary);border-radius:10px;font-size:11px;color:var(--text-muted);white-space:nowrap;">${delayLabel}</div>
                <button onclick="window.HypeBotModule.editStepInline('${flowId}','${step.id}')"
                    style="flex-shrink:0;padding:5px 9px;font-size:13px;background:none;border:1px solid var(--border-primary);border-radius:6px;color:var(--text-secondary);cursor:pointer;line-height:1;" title="Edit step">✏</button>
                <button onclick="window.HypeBotModule.deleteStep('${flowId}','${step.id}')"
                    style="flex-shrink:0;padding:5px 8px;font-size:13px;background:none;border:1px solid rgba(255,69,58,0.4);border-radius:6px;color:#ff453a;cursor:pointer;line-height:1;" title="Remove">✕</button>
            </div>
        </div>`;
    }

    function _renderPipelineNodes(flowId, steps) {
        const pipelineEl = document.getElementById('hype-editor-pipeline');
        if (!pipelineEl) return;

        const startNode = `<div style="display:flex;justify-content:center;">
            <div style="display:inline-flex;align-items:center;gap:6px;padding:6px 18px;border:1px solid var(--border-primary);border-radius:20px;font-size:11px;font-weight:600;color:var(--text-muted);letter-spacing:0.5px;text-transform:uppercase;">
                ▶ Start
            </div>
        </div>`;

        let parts = [startNode, _connector(), _addZoneHtml(flowId, null)];

        steps.forEach((step, idx) => {
            parts.push(_connector());
            parts.push(_stepCardHtml(flowId, step, idx));
            parts.push(_connector());
            parts.push(_addZoneHtml(flowId, step.id));
        });

        if (!steps.length) {
            parts.push(`<div style="text-align:center;font-size:12px;color:var(--text-muted);font-style:italic;margin-top:10px;padding-bottom:8px;">Click + to add your first step</div>`);
        }

        pipelineEl.innerHTML = `<div style="display:flex;flex-direction:column;gap:0;">${parts.join('')}</div>`;
    }

    function _inlineFormHtml(flowId, editStep, afterStepId) {
        const isEdit = !!editStep;
        const cancelFn = `window.HypeBotModule.cancelInlineStep('${flowId}')`;
        const saveFn = `window.HypeBotModule.saveInlineStep('${flowId}')`;

        const typePicker = !isEdit ? `
            <div style="margin-bottom:16px;">
                <div style="font-size:12px;font-weight:600;color:var(--text-tertiary,#888);text-transform:uppercase;letter-spacing:0.4px;margin-bottom:10px;">Step Type</div>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;" id="hype-inline-type-picker">
                    ${[['reforward','↩','Re-forward'],['cta','🔗','CTA'],['message','💬','Plain Text'],['ai_hype','✨','AI Hype']].map(([t,icon,label]) => `
                    <button type="button" data-type="${t}"
                        onclick="window.HypeBotModule._selectInlineStepType('${t}')"
                        style="padding:12px 6px;border:1px solid var(--border-primary);border-radius:9px;background:var(--bg-primary);color:var(--text-secondary);font-size:12px;cursor:pointer;text-align:center;transition:all 0.15s;">
                        <div style="font-size:20px;margin-bottom:4px;">${icon}</div>
                        <div style="font-weight:500;">${label}</div>
                    </button>`).join('')}
                </div>
            </div>` : `
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
                <span style="font-size:18px;">${STEP_TYPE_ICON[editStep.step_type]}</span>
                <span style="font-size:14px;font-weight:600;color:var(--text-primary);">${STEP_TYPE_LABEL[editStep.step_type]}</span>
            </div>
            <input type="hidden" id="hype-inline-type-value" value="${editStep.step_type}">`;

        const fieldsHtml = isEdit ? _buildStepTypeFields(editStep.step_type, editStep) : '';
        const saveDisplay = isEdit ? '' : 'display:none;';

        return `
            <div style="border:1.5px solid var(--accent,#007aff);border-radius:12px;background:var(--bg-secondary,rgba(0,0,0,0.2));overflow:hidden;">
                <div style="padding:16px 18px 4px;">
                    ${typePicker}
                    <div id="hype-inline-type-fields" style="${!isEdit ? 'display:none;' : ''}">
                        ${fieldsHtml}
                    </div>
                    ${afterStepId ? `<input type="hidden" id="hype-inline-after-step" value="${afterStepId}">` : ''}
                </div>
                <div style="display:flex;gap:8px;justify-content:flex-end;padding:12px 18px;border-top:1px solid var(--border-primary);">
                    <button type="button" class="btn btn-secondary" onclick="${cancelFn}">Cancel</button>
                    <button type="button" class="btn" id="hype-inline-save-btn" style="${saveDisplay}" onclick="${saveFn}">Save Step</button>
                </div>
            </div>`;
    }

    function insertStepInline(flowId, afterStepId) {
        const zoneId = 'hype-add-' + (afterStepId || 'start');
        const zoneEl = document.getElementById(zoneId);
        if (!zoneEl) return;
        _collapseOtherInlineForms(flowId, zoneId);
        zoneEl.innerHTML = _inlineFormHtml(flowId, null, afterStepId);
    }

    function editStepInline(flowId, stepId) {
        const cardId = 'hype-step-card-' + stepId;
        const cardEl = document.getElementById(cardId);
        if (!cardEl) return;
        const existingSteps = flowSteps[flowId] || [];
        const editStep = existingSteps.find(s => s.id === stepId);
        if (!editStep) return;
        _collapseOtherInlineForms(flowId, cardId);
        cardEl.innerHTML = _inlineFormHtml(flowId, editStep, null) +
            `<input type="hidden" id="hype-inline-edit-step-id" value="${stepId}">`;
    }

    function _collapseOtherInlineForms(flowId, exceptId) {
        const pipeline = document.getElementById('hype-editor-pipeline');
        if (!pipeline) return;
        const existingForm = pipeline.querySelector('#hype-inline-type-picker, #hype-inline-type-value');
        if (existingForm) {
            const steps = flowSteps[flowId] || [];
            _renderPipelineNodes(flowId, steps);
        }
    }

    function cancelInlineStep(flowId) {
        const steps = flowSteps[flowId] || [];
        _renderPipelineNodes(flowId, steps);
    }

    async function saveInlineStep(flowId) {
        const data = _collectInlineStepData();
        if (!data) return;

        const editStepId = document.getElementById('hype-inline-edit-step-id')?.value || null;
        const afterStepId = document.getElementById('hype-inline-after-step')?.value || null;

        try {
            const headers = await getAuthHeaders();
            headers['Content-Type'] = 'application/json';
            let url, method, body;
            if (editStepId) {
                url = `/api/hypechat/flows/${flowId}/steps/${editStepId}`;
                method = 'PUT';
                body = data;
            } else if (afterStepId) {
                url = `/api/hypechat/flows/${flowId}/steps/insert`;
                method = 'POST';
                body = { ...data, after_step_id: afterStepId };
            } else {
                url = `/api/hypechat/flows/${flowId}/steps`;
                method = 'POST';
                body = data;
            }
            const resp = await fetch(url, { method, headers, body: JSON.stringify(body) });
            if (resp.ok) {
                await _refreshEditorPipeline(flowId);
                await loadFlows();
            } else {
                const err = await resp.json();
                alert(err.error || 'Failed to save step');
            }
        } catch (e) { console.error('Error saving step:', e); }
    }

    function _selectInlineStepType(type) {
        const picker = document.getElementById('hype-inline-type-picker');
        if (picker) {
            picker.querySelectorAll('button').forEach(b => {
                const isSelected = b.dataset.type === type;
                b.style.background = isSelected ? 'var(--accent,#007aff)' : 'var(--bg-primary)';
                b.style.color = isSelected ? '#fff' : 'var(--text-secondary)';
                b.style.borderColor = isSelected ? 'var(--accent,#007aff)' : 'var(--border-primary)';
            });
        }
        const fieldsEl = document.getElementById('hype-inline-type-fields');
        if (fieldsEl) {
            fieldsEl.style.display = 'block';
            fieldsEl.innerHTML = _buildStepTypeFields(type, null);
        }
        const saveBtn = document.getElementById('hype-inline-save-btn');
        if (saveBtn) saveBtn.style.display = '';
        let hiddenInput = document.getElementById('hype-inline-type-value');
        if (!hiddenInput) {
            hiddenInput = document.createElement('input');
            hiddenInput.type = 'hidden';
            hiddenInput.id = 'hype-inline-type-value';
            const pipeline = document.getElementById('hype-editor-pipeline');
            if (pipeline) pipeline.appendChild(hiddenInput);
        }
        hiddenInput.value = type;
    }

    function _buildStepTypeFields(stepType, step) {
        const defaultDelay = step ? Math.max(1, step.delay_minutes) : 1;
        const common = `
            <div style="margin-bottom:14px;">
                <label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Delay before this step</label>
                <div style="display:flex;align-items:center;gap:6px;">
                    <input type="number" id="hype-step-delay" min="1" value="${defaultDelay}" style="width:72px;padding:8px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;text-align:center;box-sizing:border-box;">
                    <span style="font-size:13px;color:var(--text-muted);">minutes (relative to previous step)</span>
                </div>
                <div id="hype-step-delay-error" style="font-size:11px;color:#ff453a;margin-top:4px;display:none;">Minimum delay is 1 minute</div>
            </div>`;

        if (stepType === 'reforward') {
            const preset = step?.reforward_preset || 'best_tp';
            return common + `
                <div style="margin-bottom:14px;">
                    <label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Message to Re-forward</label>
                    <select id="hype-step-reforward-preset" style="width:100%;padding:10px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;box-sizing:border-box;">
                        <option value="best_tp" ${preset === 'best_tp' ? 'selected' : ''}>Best TP hit (smart: TP3 → TP2 → TP1)</option>
                        <option value="daily_recap" ${preset === 'daily_recap' ? 'selected' : ''}>Daily Recap</option>
                        <option value="weekly_recap" ${preset === 'weekly_recap' ? 'selected' : ''}>Weekly Recap</option>
                        <option value="signal" ${preset === 'signal' ? 'selected' : ''}>Signal Entry</option>
                    </select>
                </div>`;
        }

        if (stepType === 'cta') {
            return common + `
                <div style="margin-bottom:12px;">
                    <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:4px;">Intro Text</label>
                    <textarea id="hype-step-cta-intro" rows="2" placeholder="e.g. Ready to trade alongside professionals?" style="width:100%;padding:8px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:13px;resize:vertical;font-family:inherit;box-sizing:border-box;">${step ? escapeHtml(step.cta_intro_text || '') : ''}</textarea>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
                    <div>
                        <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:4px;">VIP Link Label</label>
                        <input type="text" id="hype-step-cta-vip-label" value="${step ? escapeHtml(step.cta_vip_label || '') : ''}" placeholder="Join VIP" style="width:100%;padding:8px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:13px;box-sizing:border-box;">
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:4px;">VIP Link URL</label>
                        <input type="text" id="hype-step-cta-vip-url" value="${step ? escapeHtml(step.cta_vip_url || '') : ''}" placeholder="https://..." style="width:100%;padding:8px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:13px;box-sizing:border-box;">
                    </div>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                    <div>
                        <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:4px;">Support Link Label</label>
                        <input type="text" id="hype-step-cta-support-label" value="${step ? escapeHtml(step.cta_support_label || '') : ''}" placeholder="Chat With Us" style="width:100%;padding:8px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:13px;box-sizing:border-box;">
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:4px;">Support Link URL</label>
                        <input type="text" id="hype-step-cta-support-url" value="${step ? escapeHtml(step.cta_support_url || '') : ''}" placeholder="https://..." style="width:100%;padding:8px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:13px;box-sizing:border-box;">
                    </div>
                </div>`;
        }

        if (stepType === 'message') {
            return common + `
                <div style="margin-bottom:14px;">
                    <label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Message Text</label>
                    <textarea id="hype-step-message-text" rows="5" placeholder="Enter your message here..." style="width:100%;padding:10px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;resize:vertical;font-family:inherit;box-sizing:border-box;">${step ? escapeHtml(step.message_text || '') : ''}</textarea>
                </div>`;
        }

        if (stepType === 'ai_hype') {
            return common + `
                <div style="background:var(--bg-tertiary,rgba(255,255,255,0.04));border:1px solid var(--border-primary);border-radius:8px;padding:12px 14px;">
                    <div style="font-size:13px;font-weight:500;color:var(--text-primary);margin-bottom:4px;">✨ AI Hype Message</div>
                    <div style="font-size:12px;color:var(--text-muted);line-height:1.5;">AI message generated automatically using this flow's prompt (set in the sidebar) and live pip performance data. All AI Hype steps in a flow are pre-generated together for arc coherence.</div>
                </div>`;
        }

        return common;
    }

    function _collectInlineStepData() {
        const stepType = document.getElementById('hype-inline-type-value')?.value;
        if (!stepType) { alert('Please select a step type'); return null; }
        const delay = parseInt(document.getElementById('hype-step-delay')?.value || '1') || 1;
        const delayErr = document.getElementById('hype-step-delay-error');
        if (delay < 1) {
            if (delayErr) delayErr.style.display = 'block';
            return null;
        }
        if (delayErr) delayErr.style.display = 'none';
        const data = { step_type: stepType, delay_minutes: delay };
        if (stepType === 'reforward') {
            data.reforward_preset = document.getElementById('hype-step-reforward-preset')?.value || 'best_tp';
        } else if (stepType === 'cta') {
            data.cta_intro_text = document.getElementById('hype-step-cta-intro')?.value?.trim() || '';
            data.cta_vip_label = document.getElementById('hype-step-cta-vip-label')?.value?.trim() || '';
            data.cta_vip_url = document.getElementById('hype-step-cta-vip-url')?.value?.trim() || '';
            data.cta_support_label = document.getElementById('hype-step-cta-support-label')?.value?.trim() || '';
            data.cta_support_url = document.getElementById('hype-step-cta-support-url')?.value?.trim() || '';
        } else if (stepType === 'message') {
            data.message_text = document.getElementById('hype-step-message-text')?.value?.trim() || '';
            if (!data.message_text) { alert('Please enter a message'); return null; }
        }
        return data;
    }

    // ─────────────────────────────────────────────────────────────
    // STEP CRUD
    // ─────────────────────────────────────────────────────────────

    async function deleteStep(flowId, stepId) {
        if (typeof showModalConfirm === 'function') {
            showModalConfirm('Delete Step', 'Remove this step from the flow?', 'Delete', async () => {
                await doDeleteStep(flowId, stepId);
            }, true);
        } else {
            if (confirm('Delete this step?')) await doDeleteStep(flowId, stepId);
        }
    }
    async function doDeleteStep(flowId, stepId) {
        try {
            const h = await getAuthHeaders();
            await fetch(`/api/hypechat/flows/${flowId}/steps/${stepId}`, { method:'DELETE', headers:h });
            await _refreshEditorPipeline(flowId);
            await loadFlows();
        } catch (e) { console.error(e); }
    }

    async function moveStep(flowId, stepId, direction) {
        const steps = flowSteps[flowId] || [];
        const idx = steps.findIndex(s => s.id === stepId);
        if (idx < 0) return;
        const newIdx = idx + direction;
        if (newIdx < 0 || newIdx >= steps.length) return;
        const newOrder = [...steps];
        [newOrder[idx], newOrder[newIdx]] = [newOrder[newIdx], newOrder[idx]];
        const orderedIds = newOrder.map(s => s.id);
        try {
            const h = await getAuthHeaders();
            h['Content-Type'] = 'application/json';
            await fetch(`/api/hypechat/flows/${flowId}/steps/reorder`, {
                method: 'POST', headers: h,
                body: JSON.stringify({ ordered_ids: orderedIds })
            });
            await _refreshEditorPipeline(flowId);
            await loadFlows();
        } catch (e) { console.error(e); }
    }

    // ─────────────────────────────────────────────────────────────
    // BACKWARD COMPAT SHIMS
    // ─────────────────────────────────────────────────────────────

    function renderPrompts() {}
    function renderFlows() { renderListView(); }
    function renderStepsSection(flowId) { return _refreshEditorPipeline(flowId); }
    function openStepModal(flowId, editStepId, afterStepId) {
        if (editStepId) editStepInline(flowId, editStepId);
        else insertStepInline(flowId, afterStepId);
    }
    function saveStep() { if (_editorFlowId) saveInlineStep(_editorFlowId); }
    function _cancelStepEdit() { if (_editorFlowId) cancelInlineStep(_editorFlowId); }
    function _selectStepType(type) { _selectInlineStepType(type); }

    return {
        loadHypeBot, loadPrompts, loadFlows,
        openPromptModal, savePrompt, editPrompt, deletePrompt,
        previewPrompt, previewFlow, regeneratePreview, regenerateFlowPreview,
        openFlowModal, saveFlow, saveFlowSettings, editFlow, deleteFlow,
        setFlowStatus, triggerFlow, viewAnalytics,
        openStepModal, saveStep, deleteStep, moveStep,
        insertStepInline, editStepInline, cancelInlineStep, saveInlineStep,
        _selectStepType, _selectInlineStepType, _cancelStepEdit,
        _showListView, _showEditorView,
        _switchEditorTab, _toggleEditorFlowStatus,
        _onListSearch, _onListStatusFilter,
        _showFlowMenu,
        renderStepsSection, renderPrompts, renderFlows,
    };
})();
