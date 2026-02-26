window.HypeBotModule = (function() {
    let prompts = [];
    let flows = [];
    let flowSteps = {};

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

    async function loadHypeBot() {
        await Promise.all([loadPrompts(), loadFlows(), loadConnectionStatus()]);
    }

    async function loadPrompts() {
        try {
            const headers = await getAuthHeaders();
            const resp = await fetch('/api/hypechat/prompts', { headers });
            const data = await resp.json();
            prompts = data.prompts || [];
            renderPrompts();
        } catch (e) { console.error('Error loading prompts:', e); }
    }

    function renderPrompts() {
        const container = document.getElementById('hype-prompts-list');
        if (!container) return;
        if (!prompts.length) {
            container.innerHTML = '<div class="hype-empty-state">No prompts yet. Create one to get started.</div>';
            return;
        }
        container.innerHTML = prompts.map(p => `
            <div class="hype-prompt-card">
                <div class="hype-card-left">
                    <div class="hype-card-title"><svg class="card-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>${escapeHtml(p.name)}</div>
                    <div class="hype-card-prompt">${escapeHtml(p.custom_prompt)}</div>
                </div>
                <div class="hype-card-right">
                    <span class="hype-card-meta">${new Date(p.created_at).toLocaleDateString()}</span>
                    <div class="hype-card-actions">
                        <button onclick="window.HypeBotModule.previewPrompt('${p.id}')">Preview</button>
                        <button onclick="window.HypeBotModule.editPrompt('${p.id}')">Edit</button>
                        <button class="btn-danger" onclick="window.HypeBotModule.deletePrompt('${p.id}')">Del</button>
                    </div>
                </div>
            </div>
        `).join('');
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
            renderFlows();
        } catch (e) { console.error('Error loading flows:', e); }
    }

    function renderFlows() {
        const container = document.getElementById('hype-flows-list');
        if (!container) return;
        if (!flows.length) {
            container.innerHTML = '<div class="hype-empty-state">No flows yet. Create one to schedule hype messages.</div>';
            return;
        }
        container.innerHTML = flows.map(f => {
            const steps = flowSteps[f.id] || [];
            const hasSteps = steps.length > 0;
            const stepCountBadge = hasSteps
                ? `<span style="font-size:11px;font-weight:600;color:var(--text-muted);background:var(--bg-tertiary,rgba(255,255,255,0.06));border:1px solid var(--border-primary);border-radius:10px;padding:1px 7px;">${steps.length} step${steps.length !== 1 ? 's' : ''}</span>`
                : `<span style="font-size:11px;color:var(--text-muted);font-style:italic;">legacy</span>`;
            const typeStrip = hasSteps
                ? `<span style="font-size:12px;color:var(--text-muted);letter-spacing:2px;">${steps.map(s => STEP_TYPE_ICON[s.step_type] || '?').join(' · ')}</span>`
                : '';
            const parentFlow = f.trigger_after_flow_id ? flows.find(p => p.id === f.trigger_after_flow_id) : null;
            const triggerLabel = f.trigger_after_flow_id
                ? `↳ ${f.trigger_delay_minutes || 0}min after ${parentFlow ? escapeHtml(parentFlow.name) : 'deleted flow'}`
                : (f.trigger_delay_minutes > 0 ? `Fires ${f.trigger_delay_minutes}min after Cross Promo` : 'Fires from Cross Promo');
            return `
            <div class="hype-flow-card status-${f.status}">
                <div class="hype-card-left">
                    <div class="hype-card-header">
                        <span class="hype-card-title">${escapeHtml(f.name)}</span>
                        <span class="hype-flow-status ${f.status}">${f.status}</span>
                        ${stepCountBadge}
                    </div>
                    <div style="display:flex;align-items:center;gap:10px;margin-top:4px;">
                        <div class="hype-flow-prompt-name">Prompt: ${f.prompt_name ? escapeHtml(f.prompt_name) : 'None'}</div>
                        ${typeStrip ? `<div>${typeStrip}</div>` : ''}
                    </div>
                    <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${escapeHtml(triggerLabel)}</div>
                </div>
                <div class="hype-card-right">
                    <div class="hype-flow-config">
                        <span class="hype-config-item">${parseDaysString(f.active_days || '').map(d => d.charAt(0).toUpperCase() + d.slice(1)).join(', ')}</span>
                    </div>
                    <div class="hype-card-actions">
                        ${f.status === 'paused'
                            ? `<button onclick="window.HypeBotModule.setFlowStatus('${f.id}', 'active')" style="color:#34c759;border-color:#34c759;">Activate</button>`
                            : `<button onclick="window.HypeBotModule.setFlowStatus('${f.id}', 'paused')" style="color:#ff9f0a;border-color:#ff9f0a;">Pause</button>`}
                        <button onclick="window.HypeBotModule.previewFlow('${f.id}')">Preview</button>
                        <button onclick="window.HypeBotModule.triggerFlow('${f.id}')">Trigger</button>
                        <button onclick="window.HypeBotModule.editFlow('${f.id}')">Edit</button>
                        <button onclick="window.HypeBotModule.viewAnalytics('${f.id}')">Stats</button>
                        <button class="btn-danger" onclick="window.HypeBotModule.deleteFlow('${f.id}')">Del</button>
                    </div>
                </div>
            </div>`;
        }).join('');
    }

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
            if (resp.ok) { document.getElementById('hype-prompt-modal')?.remove(); await loadPrompts(); }
            else { const err = await resp.json(); alert(err.error || 'Failed to save'); }
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
            alert('This flow has no prompt assigned. Please assign a prompt first.');
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
    // FLOW MODAL (settings + step builder)
    // ─────────────────────────────────────────────────────────────

    function _buildDayToggles(container, conflictLabel, currentDays, isChildFlow) {
        ALL_DAYS.forEach(d => {
            const isSelected = currentDays.includes(d);
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.dataset.day = d;
            btn.textContent = DAY_LABELS[d];
            btn.style.cssText = 'padding:8px 14px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;border:1px solid var(--border-primary);transition:all 0.15s;';
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
        const title = flow ? 'Edit Flow' : 'New Flow';
        const opts = prompts.map(p => `<option value="${p.id}" ${flow && flow.prompt_id === p.id ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('');
        const isChildFlow = !!(flow && flow.trigger_after_flow_id);

        const modalHtml = `
            <div class="modal-overlay" id="hype-flow-modal" onclick="if(event.target===this)this.remove()">
                <div class="modal-content" style="max-width:560px;max-height:92vh;display:flex;flex-direction:column;">
                    <div class="modal-header">
                        <h3>${title}</h3>
                        <button class="modal-close" onclick="document.getElementById('hype-flow-modal').remove()">&times;</button>
                    </div>
                    <div class="modal-body" style="overflow-y:auto;flex:1;padding:16px 24px;">

                        <!-- Settings section -->
                        <div style="background:var(--bg-tertiary,rgba(255,255,255,0.04));border:1px solid var(--border-primary);border-radius:10px;padding:10px 14px;margin-bottom:14px;">
                            <label style="display:block;font-size:11px;font-weight:600;color:var(--text-tertiary,#888);margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px;">Trigger</label>
                            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                                <span style="font-size:13px;color:var(--text-secondary);">Fire</span>
                                <input type="number" id="hype-flow-trigger-delay" min="0" value="${flow ? (flow.trigger_delay_minutes || 0) : 0}" style="width:56px;padding:6px 4px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:6px;color:var(--text-primary);font-size:14px;text-align:center;box-sizing:border-box;">
                                <span style="font-size:13px;color:var(--text-secondary);">min after</span>
                                <select id="hype-flow-trigger-after" style="flex:1;min-width:140px;padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:6px;color:var(--text-primary);font-size:13px;box-sizing:border-box;">
                                    <option value="">Cross Promo</option>
                                    ${flows.filter(f => f.id !== editId && f.status === 'active').map(f => `<option value="${f.id}" ${flow && flow.trigger_after_flow_id === f.id ? 'selected' : ''}>${escapeHtml(f.name)}</option>`).join('')}
                                </select>
                            </div>
                        </div>

                        <div style="margin-bottom:14px;">
                            <label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Name</label>
                            <input type="text" id="hype-flow-name" value="${flow ? escapeHtml(flow.name) : ''}" placeholder="e.g. Post-CTA Hype" style="width:100%;padding:10px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;box-sizing:border-box;">
                        </div>

                        <div style="margin-bottom:14px;">
                            <label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Prompt <span style="font-size:11px;color:var(--text-muted);">(used by AI Hype steps)</span></label>
                            <select id="hype-flow-prompt" style="width:100%;padding:10px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;box-sizing:border-box;">
                                <option value="">Select a prompt...</option>${opts}
                            </select>
                        </div>

                        <div style="margin-bottom:0;">
                            <label style="display:block;font-size:11px;font-weight:600;color:var(--text-tertiary,#888);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">Active Days</label>
                            <div id="hype-day-toggles" data-flow-id="${editId || ''}" style="display:flex;gap:6px;flex-wrap:wrap;"></div>
                        </div>

                        ${editId ? `
                        <!-- Step builder section -->
                        <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border-primary);">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
                                <span style="font-size:14px;font-weight:600;color:var(--text-primary);">Steps</span>
                                <span id="hype-step-count-badge" style="font-size:11px;font-weight:600;color:var(--text-muted);background:var(--bg-tertiary,rgba(255,255,255,0.06));border:1px solid var(--border-primary);border-radius:10px;padding:1px 7px;">0 steps</span>
                            </div>
                            <div id="hype-steps-list" style="min-height:32px;"></div>
                        </div>` : ''}

                    </div>
                    <div class="modal-footer" style="display:flex;gap:8px;justify-content:flex-end;padding:16px 24px;border-top:1px solid var(--border-primary);">
                        <button class="btn btn-secondary" onclick="document.getElementById('hype-flow-modal').remove()">Cancel</button>
                        <button class="btn" onclick="window.HypeBotModule.saveFlow('${editId || ''}')">Save Flow Settings</button>
                    </div>
                </div>
            </div>`;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
        document.getElementById('hype-flow-modal').classList.add('active');
        document.getElementById('hype-flow-name').focus();

        const currentDays = flow ? parseDaysString(flow.active_days || '') : ['mon','tue','wed','thu','fri'];
        const toggleContainer = document.getElementById('hype-day-toggles');
        _buildDayToggles(toggleContainer, null, currentDays, isChildFlow);

        if (editId) {
            renderStepsSection(editId);
        }
    }

    async function saveFlow(editId) {
        const name = document.getElementById('hype-flow-name').value.trim();
        const promptId = document.getElementById('hype-flow-prompt').value;
        const triggerAfterFlowId = document.getElementById('hype-flow-trigger-after')?.value || null;
        const triggerDelayMinutes = parseInt(document.getElementById('hype-flow-trigger-delay')?.value) || 0;
        const selectedDays = Array.from(document.querySelectorAll('#hype-day-toggles button[data-active="true"]')).map(b => b.dataset.day);
        if (!name) { alert('Please enter a flow name'); return; }
        if (selectedDays.length === 0) { alert('Please select at least one active day'); return; }
        const days = selectedDays.join(',');
        try {
            const headers = await getAuthHeaders();
            headers['Content-Type'] = 'application/json';
            const url = editId ? `/api/hypechat/flows/${editId}` : '/api/hypechat/flows';
            const payload = {
                name,
                prompt_id: promptId || null,
                active_days: days,
                trigger_after_flow_id: triggerAfterFlowId || null,
                trigger_delay_minutes: triggerDelayMinutes,
            };
            if (!editId) {
                payload.message_count = 3;
                payload.interval_minutes = 90;
                payload.interval_max_minutes = 90;
                payload.delay_after_cta_minutes = 10;
            }
            const resp = await fetch(url, { method: editId ? 'PUT' : 'POST', headers, body: JSON.stringify(payload) });
            if (resp.ok) {
                const data = await resp.json();
                document.getElementById('hype-flow-modal')?.remove();
                await loadFlows();
                if (!editId && data.id) {
                    openFlowModal(data.id);
                }
            } else {
                const err = await resp.json();
                alert(err.error || 'Failed to save');
            }
        } catch (e) { console.error('Error saving flow:', e); }
    }

    function editFlow(id) { openFlowModal(id); }

    async function deleteFlow(id) {
        if (typeof showModalConfirm === 'function') {
            showModalConfirm('Delete Flow', 'Delete this flow? All message history will be lost.', 'Delete', async () => { await doDeleteFlow(id); }, true);
        } else { if (confirm('Delete this flow?')) await doDeleteFlow(id); }
    }
    async function doDeleteFlow(id) {
        try { const h = await getAuthHeaders(); await fetch(`/api/hypechat/flows/${id}`, { method:'DELETE', headers:h }); await loadFlows(); } catch(e) { console.error(e); }
    }

    async function setFlowStatus(id, status) {
        try {
            const h = await getAuthHeaders(); h['Content-Type'] = 'application/json';
            await fetch(`/api/hypechat/flows/${id}/status`, { method:'POST', headers:h, body: JSON.stringify({ status }) });
            await loadFlows();
        } catch (e) { console.error(e); }
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
    // STEP BUILDER
    // ─────────────────────────────────────────────────────────────

    function _pipelineConnector() {
        return '<div style="width:2px;height:18px;background:var(--border-primary);margin:0 auto;"></div>';
    }

    function _pipelineInsertBtn(flowId, afterStepId) {
        const safeAfter = afterStepId ? `'${afterStepId}'` : 'null';
        return `<div style="display:flex;justify-content:center;position:relative;">
            <button type="button"
                onclick="window.HypeBotModule.openStepModal('${flowId}', null, ${safeAfter})"
                style="width:26px;height:26px;border-radius:50%;border:1px solid var(--border-primary);background:var(--bg-primary);color:var(--text-muted);font-size:15px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.15s;z-index:1;"
                onmouseover="this.style.borderColor='var(--accent,#007aff)';this.style.color='var(--accent,#007aff)';this.style.background='rgba(0,122,255,0.08)'"
                onmouseout="this.style.borderColor='var(--border-primary)';this.style.color='var(--text-muted)';this.style.background='var(--bg-primary)'">+</button>
        </div>`;
    }

    async function renderStepsSection(flowId) {
        const listEl = document.getElementById('hype-steps-list');
        if (!listEl) return;
        listEl.innerHTML = '<div style="font-size:12px;color:var(--text-muted);padding:8px 0;text-align:center;">Loading…</div>';
        try {
            const headers = await getAuthHeaders();
            const resp = await fetch(`/api/hypechat/flows/${flowId}/steps`, { headers });
            const data = await resp.json();
            const steps = data.steps || [];
            flowSteps[flowId] = steps;
            _renderPipeline(flowId, steps);
        } catch (e) {
            console.error('Error loading steps:', e);
            listEl.innerHTML = '<div style="font-size:12px;color:#ff453a;text-align:center;">Failed to load steps</div>';
        }
    }

    function _renderPipeline(flowId, steps) {
        const listEl = document.getElementById('hype-steps-list');
        const badgeEl = document.getElementById('hype-step-count-badge');
        if (!listEl) return;
        if (badgeEl) badgeEl.textContent = `${steps.length} step${steps.length !== 1 ? 's' : ''}`;

        const startNode = `<div style="display:flex;justify-content:center;">
            <div style="display:inline-flex;align-items:center;gap:6px;padding:5px 14px;border:1px solid var(--border-primary);border-radius:20px;font-size:11px;font-weight:600;color:var(--text-muted);letter-spacing:0.5px;text-transform:uppercase;">
                ▶ Start
            </div>
        </div>`;

        let parts = [startNode];

        if (!steps.length) {
            parts.push(_pipelineConnector());
            parts.push(_pipelineInsertBtn(flowId, null));
            parts.push(`<div style="text-align:center;font-size:12px;color:var(--text-muted);font-style:italic;margin-top:8px;">Add your first step</div>`);
        } else {
            parts.push(_pipelineConnector());
            parts.push(_pipelineInsertBtn(flowId, null));

            steps.forEach((step, idx) => {
                const delayLabel = step.delay_minutes > 0 ? `+${step.delay_minutes} min` : '+0 min';
                const summary = stepSummary(step);
                const truncated = summary.length > 55 ? summary.slice(0, 54) + '…' : summary;

                parts.push(`
                    ${_pipelineConnector()}
                    <div style="display:flex;align-items:center;gap:10px;background:var(--bg-secondary,rgba(255,255,255,0.03));border:1px solid var(--border-primary);border-radius:10px;padding:10px 12px;">
                        <div style="flex-shrink:0;width:22px;height:22px;border-radius:50%;background:var(--bg-tertiary,rgba(255,255,255,0.08));border:1px solid var(--border-primary);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--text-muted);">${idx + 1}</div>
                        <div style="flex:1;min-width:0;">
                            <div style="font-size:13px;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(truncated)}</div>
                        </div>
                        <div style="flex-shrink:0;padding:2px 8px;background:var(--bg-tertiary,rgba(255,255,255,0.06));border:1px solid var(--border-primary);border-radius:10px;font-size:11px;color:var(--text-muted);white-space:nowrap;">${delayLabel}</div>
                        <button onclick="window.HypeBotModule.openStepModal('${flowId}','${step.id}',null)"
                            style="flex-shrink:0;padding:4px 8px;font-size:13px;background:none;border:1px solid var(--border-primary);border-radius:5px;color:var(--text-secondary);cursor:pointer;line-height:1;" title="Edit">✏</button>
                        <button onclick="window.HypeBotModule.deleteStep('${flowId}','${step.id}')"
                            style="flex-shrink:0;padding:4px 7px;font-size:13px;background:none;border:1px solid rgba(255,69,58,0.4);border-radius:5px;color:#ff453a;cursor:pointer;line-height:1;" title="Remove">✕</button>
                    </div>`);

                parts.push(_pipelineConnector());
                parts.push(_pipelineInsertBtn(flowId, step.id));
            });
        }

        listEl.innerHTML = `<div style="display:flex;flex-direction:column;padding:4px 0 8px;">${parts.join('')}</div>`;
    }

    function openStepModal(flowId, editStepId, afterStepId) {
        const existingSteps = flowSteps[flowId] || [];
        const editStep = editStepId ? existingSteps.find(s => s.id === editStepId) : null;
        const isEdit = !!editStep;
        const title = isEdit ? 'Edit Step' : 'Add Step';

        const modalHtml = `
            <div class="modal-overlay" id="hype-step-modal" onclick="if(event.target===this)this.remove()" style="z-index:1100;">
                <div class="modal-content" style="max-width:480px;max-height:88vh;display:flex;flex-direction:column;z-index:1101;">
                    <div class="modal-header">
                        <h3>${title}</h3>
                        <button class="modal-close" onclick="document.getElementById('hype-step-modal').remove()">&times;</button>
                    </div>
                    <div class="modal-body" id="hype-step-modal-body" style="overflow-y:auto;flex:1;padding:16px 24px;">
                        ${!isEdit ? `
                        <div style="margin-bottom:16px;">
                            <label style="display:block;font-size:11px;font-weight:600;color:var(--text-tertiary,#888);margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px;">Step Type</label>
                            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;" id="hype-step-type-picker">
                                ${[['reforward','↩','Re-forward'],['cta','🔗','CTA'],['message','💬','Plain Text'],['ai_hype','✨','AI Hype']].map(([t,icon,label]) => `
                                <button type="button" data-type="${t}"
                                    onclick="window.HypeBotModule._selectStepType('${t}')"
                                    style="padding:12px 8px;border:1px solid var(--border-primary);border-radius:8px;background:var(--bg-primary);color:var(--text-secondary);font-size:13px;cursor:pointer;text-align:center;transition:all 0.15s;">
                                    <div style="font-size:20px;margin-bottom:4px;">${icon}</div>
                                    <div style="font-weight:500;">${label}</div>
                                </button>`).join('')}
                            </div>
                        </div>` : `<input type="hidden" id="hype-step-type-value" value="${editStep.step_type}">`}
                        <div id="hype-step-type-fields" style="${!isEdit ? 'display:none;' : ''}">
                            ${isEdit ? _buildStepTypeFields(editStep.step_type, editStep) : ''}
                        </div>
                    </div>
                    <div class="modal-footer" style="display:flex;gap:8px;justify-content:flex-end;padding:16px 24px;border-top:1px solid var(--border-primary);">
                        <button class="btn btn-secondary" onclick="document.getElementById('hype-step-modal').remove()">Cancel</button>
                        <button class="btn" id="hype-step-save-btn" onclick="window.HypeBotModule.saveStep('${flowId}','${editStepId || ''}','${afterStepId || ''}')" ${!isEdit ? 'style="display:none;"' : ''}>Save Step</button>
                    </div>
                </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        document.getElementById('hype-step-modal').classList.add('active');
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
                    <div style="font-size:12px;color:var(--text-muted);line-height:1.5;">AI message generated automatically using this flow's prompt and live pip performance data. All AI Hype steps in a flow are pre-generated together for arc coherence.</div>
                </div>`;
        }

        return common;
    }

    function _selectStepType(type) {
        const picker = document.getElementById('hype-step-type-picker');
        if (picker) {
            picker.querySelectorAll('button').forEach(b => {
                const isSelected = b.dataset.type === type;
                b.style.background = isSelected ? 'var(--accent,#007aff)' : 'var(--bg-primary)';
                b.style.color = isSelected ? '#fff' : 'var(--text-secondary)';
                b.style.borderColor = isSelected ? 'var(--accent,#007aff)' : 'var(--border-primary)';
            });
        }
        const fieldsEl = document.getElementById('hype-step-type-fields');
        if (fieldsEl) {
            fieldsEl.style.display = 'block';
            fieldsEl.innerHTML = _buildStepTypeFields(type, null);
        }
        const saveBtn = document.getElementById('hype-step-save-btn');
        if (saveBtn) saveBtn.style.display = '';
        let hiddenInput = document.getElementById('hype-step-type-value');
        if (!hiddenInput) {
            hiddenInput = document.createElement('input');
            hiddenInput.type = 'hidden';
            hiddenInput.id = 'hype-step-type-value';
            document.getElementById('hype-step-modal-body').appendChild(hiddenInput);
        }
        hiddenInput.value = type;
    }

    function _collectStepData() {
        const stepType = document.getElementById('hype-step-type-value')?.value;
        if (!stepType) return null;
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

    async function saveStep(flowId, editStepId, afterStepId) {
        const data = _collectStepData();
        if (!data) return;
        try {
            const headers = await getAuthHeaders();
            headers['Content-Type'] = 'application/json';
            let url, method;
            let body;
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
                document.getElementById('hype-step-modal')?.remove();
                await renderStepsSection(flowId);
                await loadFlows();
            } else {
                const err = await resp.json();
                alert(err.error || 'Failed to save step');
            }
        } catch (e) { console.error('Error saving step:', e); }
    }

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
            await renderStepsSection(flowId);
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
            await renderStepsSection(flowId);
            await loadFlows();
        } catch (e) { console.error(e); }
    }

    async function viewAnalytics(flowId) {
        try {
            const h = await getAuthHeaders();
            const resp = await fetch(`/api/hypechat/flows/${flowId}/analytics`, { headers:h });
            const data = await resp.json();
            const msgs = data.messages || [];
            const msgsHtml = msgs.length ? msgs.map(m => `
                <div class="hype-message-card">
                    <div class="hype-message-text">${escapeHtml(m.content_sent)}</div>
                    <div class="hype-message-meta"><span>Step ${m.step_number}</span><span>${new Date(m.sent_at).toLocaleString()}</span></div>
                </div>`).join('') : '<div class="hype-empty-state">No messages sent yet</div>';
            const modalHtml = `
                <div class="modal-overlay" id="hype-analytics-modal" onclick="if(event.target===this)this.remove()">
                    <div class="modal-content" style="max-width:560px;">
                        <div class="modal-header"><h3>Analytics: ${escapeHtml(data.flow?.name || '')}</h3><button class="modal-close" onclick="document.getElementById('hype-analytics-modal').remove()">&times;</button></div>
                        <div class="modal-body">
                            <div style="display:flex;gap:16px;margin-bottom:20px;">
                                <div style="flex:1;background:var(--bg-primary);border-radius:10px;padding:14px;text-align:center;">
                                    <div style="font-size:24px;font-weight:700;color:var(--text-primary);">${data.total_messages}</div>
                                    <div style="font-size:12px;color:var(--text-muted);">Total Messages</div>
                                </div>
                                <div style="flex:1;background:var(--bg-primary);border-radius:10px;padding:14px;text-align:center;">
                                    <div style="font-size:24px;font-weight:700;color:var(--text-primary);">${data.today_message_count}</div>
                                    <div style="font-size:12px;color:var(--text-muted);">Today</div>
                                </div>
                            </div>
                            <h4 style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:12px;">Recent Messages</h4>
                            <div style="max-height:300px;overflow-y:auto;">${msgsHtml}</div>
                        </div>
                        <div class="modal-footer" style="padding:16px 24px;border-top:1px solid var(--border-primary);text-align:right;">
                            <button class="btn btn-secondary" onclick="document.getElementById('hype-analytics-modal').remove()">Close</button>
                        </div>
                    </div>
                </div>`;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            document.getElementById('hype-analytics-modal').classList.add('active');
        } catch (e) { console.error(e); }
    }

    return {
        loadHypeBot, loadPrompts, loadFlows,
        openPromptModal, savePrompt, editPrompt, deletePrompt,
        previewPrompt, previewFlow, regeneratePreview, regenerateFlowPreview,
        openFlowModal, saveFlow, editFlow, deleteFlow,
        setFlowStatus, triggerFlow, viewAnalytics,
        openStepModal, saveStep, deleteStep, moveStep,
        _selectStepType,
        renderStepsSection,
    };
})();
