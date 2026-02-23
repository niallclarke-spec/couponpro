window.HypeBotModule = (function() {
    let prompts = [];
    let flows = [];

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    const TG_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z"/></svg>';

    const ALL_DAYS = ['mon','tue','wed','thu','fri','sat','sun'];
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
        } catch (e) {
            console.error('Error loading connection status:', e);
        }
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
        container.innerHTML = flows.map(f => `
            <div class="hype-flow-card status-${f.status}">
                <div class="hype-card-left">
                    <div class="hype-card-header">
                        <span class="hype-card-title">${escapeHtml(f.name)}</span>
                        <span class="hype-flow-status ${f.status}">${f.status}</span>
                    </div>
                    <div class="hype-flow-prompt-name">Prompt: ${f.prompt_name ? escapeHtml(f.prompt_name) : 'None'}</div>
                </div>
                <div class="hype-card-right">
                    <div class="hype-flow-config">
                        <span class="hype-config-item">${f.message_count} msgs · ${f.interval_minutes}-${f.interval_max_minutes || f.interval_minutes}min</span>
                        <span class="hype-config-item">Flow delay: ${f.delay_after_cta_minutes}min</span>
                        <span class="hype-config-item">${parseDaysString(f.active_days || '').map(d => d.charAt(0).toUpperCase() + d.slice(1)).join(', ')}</span>
                        ${f.cta_enabled ? '<span class="hype-config-item" style="color:#34c759;">CTA ✓</span>' : ''}
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
            </div>
        `).join('');
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
                            <div style="font-size:11px;margin-top:4px;color:var(--text-muted);">Creating a coherent message sequence</div>
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

        const modalHtml = `
            <div class="modal-overlay" id="hype-preview-modal" onclick="if(event.target===this)this.remove()">
                <div class="modal-content" style="max-width:540px;">
                    <div class="modal-header"><h3>Flow Preview: ${escapeHtml(flow.name)}</h3><button class="modal-close" onclick="document.getElementById('hype-preview-modal').remove()">&times;</button></div>
                    <div class="modal-body" style="padding:16px;">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
                            <label style="font-size:12px;font-weight:500;color:var(--text-secondary);white-space:nowrap;">Messages:</label>
                            <input type="number" id="preview-msg-count" min="1" max="10" value="${flow.message_count}" style="width:52px;padding:4px 8px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:6px;color:var(--text-primary);font-size:13px;text-align:center;" readonly>
                        </div>
                        <div id="preview-loading" style="text-align:center;color:var(--text-muted);padding:30px 0;">
                            <div style="font-size:13px;">Generating flow preview...</div>
                            <div style="font-size:11px;margin-top:4px;color:var(--text-muted);">Creating a coherent ${flow.message_count}-message sequence</div>
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
        await doGeneratePreview(customPrompt, flow.message_count, flow.interval_minutes, flow.delay_after_cta_minutes);
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
                <div style="margin-bottom:10px;">
                    ${timelineHtml}
                </div>
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
        await doGeneratePreview(prompt.custom_prompt, flow.message_count, flow.interval_minutes, flow.delay_after_cta_minutes);
    }

    function openFlowModal(editId) {
        const flow = editId ? flows.find(f => f.id === editId) : null;
        const title = flow ? 'Edit Flow' : 'New Flow';
        const opts = prompts.map(p => `<option value="${p.id}" ${flow && flow.prompt_id === p.id ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('');
        const modalHtml = `
            <div class="modal-overlay" id="hype-flow-modal" onclick="if(event.target===this)this.remove()">
                <div class="modal-content" style="max-width:520px;max-height:90vh;display:flex;flex-direction:column;">
                    <div class="modal-header"><h3>${title}</h3><button class="modal-close" onclick="document.getElementById('hype-flow-modal').remove()">&times;</button></div>
                    <div class="modal-body" style="overflow-y:auto;flex:1;">
                        <div style="margin-bottom:16px;">
                            <label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Name</label>
                            <input type="text" id="hype-flow-name" value="${flow ? escapeHtml(flow.name) : ''}" placeholder="e.g. Post-CTA Hype" style="width:100%;padding:10px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;box-sizing:border-box;">
                        </div>
                        <div style="margin-bottom:16px;">
                            <label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Prompt</label>
                            <select id="hype-flow-prompt" style="width:100%;padding:10px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;box-sizing:border-box;">
                                <option value="">Select a prompt...</option>${opts}
                            </select>
                        </div>
                        <div style="background:var(--bg-tertiary,rgba(255,255,255,0.04));border:1px solid var(--border-primary);border-radius:10px;padding:10px 14px;margin-bottom:14px;">
                            <label style="display:block;font-size:11px;font-weight:600;color:var(--text-tertiary,#888);margin-bottom:2px;text-transform:uppercase;letter-spacing:0.5px;">Flow Delay</label>
                            <span style="display:block;font-size:11px;color:var(--text-tertiary,#666);margin-bottom:8px;">Time between TP hit and first hype message</span>
                            <div style="display:flex;align-items:center;gap:6px;">
                                <input type="number" id="hype-flow-delay" min="0" value="${flow ? flow.delay_after_cta_minutes : 10}" style="width:56px;padding:6px 4px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:6px;color:var(--text-primary);font-size:14px;text-align:center;box-sizing:border-box;">
                                <span style="color:var(--text-tertiary,#888);font-size:12px;">min</span>
                            </div>
                        </div>
                        <div style="display:flex;gap:10px;align-items:flex-start;margin-bottom:14px;">
                            <div style="flex:0 0 auto;background:var(--bg-tertiary,rgba(255,255,255,0.04));border:1px solid var(--border-primary);border-radius:10px;padding:10px 14px;text-align:center;">
                                <label style="display:block;font-size:11px;font-weight:600;color:var(--text-tertiary,#888);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">Messages</label>
                                <input type="number" id="hype-flow-count" min="1" max="10" value="${flow ? flow.message_count : 3}" style="width:56px;padding:6px 4px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:6px;color:var(--text-primary);font-size:14px;text-align:center;box-sizing:border-box;">
                            </div>
                            <div style="flex:1;background:var(--bg-tertiary,rgba(255,255,255,0.04));border:1px solid var(--border-primary);border-radius:10px;padding:10px 14px;">
                                <label style="display:block;font-size:11px;font-weight:600;color:var(--text-tertiary,#888);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">Interval between messages</label>
                                <div style="display:flex;align-items:center;gap:6px;">
                                    <input type="number" id="hype-flow-interval" min="1" value="${flow ? flow.interval_minutes : 5}" style="width:56px;padding:6px 4px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:6px;color:var(--text-primary);font-size:14px;text-align:center;box-sizing:border-box;">
                                    <span style="color:var(--text-tertiary,#888);font-size:13px;">–</span>
                                    <input type="number" id="hype-flow-interval-max" min="1" value="${flow ? (flow.interval_max_minutes || flow.interval_minutes) : 30}" style="width:56px;padding:6px 4px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:6px;color:var(--text-primary);font-size:14px;text-align:center;box-sizing:border-box;">
                                    <span style="color:var(--text-tertiary,#888);font-size:12px;">min</span>
                                </div>
                            </div>
                        </div>
                        <div style="margin-bottom:4px;">
                            <label style="display:block;font-size:11px;font-weight:600;color:var(--text-tertiary,#888);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">Active Days</label>
                            <div id="hype-day-toggles" style="display:flex;gap:6px;flex-wrap:wrap;"></div>
                            <div id="hype-day-conflicts" style="font-size:11px;color:#ff6b6b;margin-top:6px;display:none;"></div>
                        </div>
                        <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border-primary);">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
                                <label style="font-size:13px;font-weight:600;color:var(--text-primary);">CTA Message</label>
                                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                                    <input type="checkbox" id="hype-flow-cta-enabled" ${flow && flow.cta_enabled ? 'checked' : ''} onchange="document.getElementById('hype-cta-fields').style.display=this.checked?'block':'none'" style="accent-color:#34c759;">
                                    <span style="font-size:12px;color:var(--text-secondary);">Enabled</span>
                                </label>
                            </div>
                            <div id="hype-cta-fields" style="display:${flow && flow.cta_enabled ? 'block' : 'none'};">
                                <div style="margin-bottom:12px;">
                                    <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:4px;">Delay after last message (min)</label>
                                    <input type="number" id="hype-flow-cta-delay" min="0" value="${flow && flow.cta_delay_minutes != null ? flow.cta_delay_minutes : 30}" style="width:100px;padding:8px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:13px;box-sizing:border-box;">
                                </div>
                                <div style="margin-bottom:12px;">
                                    <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:4px;">Intro Text</label>
                                    <textarea id="hype-flow-cta-intro" rows="2" placeholder="e.g. If you're looking to approach the market with a clear process..." style="width:100%;padding:8px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:13px;resize:vertical;font-family:inherit;box-sizing:border-box;">${flow && flow.cta_intro_text ? escapeHtml(flow.cta_intro_text) : ''}</textarea>
                                </div>
                                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
                                    <div>
                                        <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:4px;">VIP Link Label</label>
                                        <input type="text" id="hype-flow-cta-vip-label" value="${flow && flow.cta_vip_label ? escapeHtml(flow.cta_vip_label) : ''}" placeholder="Join EntryLab VIP" style="width:100%;padding:8px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:13px;box-sizing:border-box;">
                                    </div>
                                    <div>
                                        <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:4px;">VIP Link URL</label>
                                        <input type="text" id="hype-flow-cta-vip-url" value="${flow && flow.cta_vip_url ? escapeHtml(flow.cta_vip_url) : ''}" placeholder="https://..." style="width:100%;padding:8px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:13px;box-sizing:border-box;">
                                    </div>
                                </div>
                                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                                    <div>
                                        <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:4px;">Support Link Label</label>
                                        <input type="text" id="hype-flow-cta-support-label" value="${flow && flow.cta_support_label ? escapeHtml(flow.cta_support_label) : ''}" placeholder="Chat With Us" style="width:100%;padding:8px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:13px;box-sizing:border-box;">
                                    </div>
                                    <div>
                                        <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:4px;">Support Link URL</label>
                                        <input type="text" id="hype-flow-cta-support-url" value="${flow && flow.cta_support_url ? escapeHtml(flow.cta_support_url) : ''}" placeholder="https://..." style="width:100%;padding:8px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:13px;box-sizing:border-box;">
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer" style="display:flex;gap:8px;justify-content:flex-end;padding:16px 24px;border-top:1px solid var(--border-primary);">
                        <button class="btn btn-secondary" onclick="document.getElementById('hype-flow-modal').remove()">Cancel</button>
                        <button class="btn" onclick="window.HypeBotModule.saveFlow('${editId || ''}')">Save</button>
                    </div>
                </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        document.getElementById('hype-flow-modal').classList.add('active');
        document.getElementById('hype-flow-name').focus();

        const allDays = ['mon','tue','wed','thu','fri','sat','sun'];
        const dayLabels = {mon:'Mon',tue:'Tue',wed:'Wed',thu:'Thu',fri:'Fri',sat:'Sat',sun:'Sun'};
        const currentDays = flow ? parseDaysString(flow.active_days || '') : ['mon','tue','wed','thu','fri'];
        const takenMap = {};
        const currentFlowId = flow ? flow.id : null;
        flows.forEach(f => {
            if (f.id === currentFlowId || f.status !== 'active') return;
            parseDaysString(f.active_days || '').forEach(d => { takenMap[d] = f.name; });
        });
        const toggleContainer = document.getElementById('hype-day-toggles');
        const conflictLabel = document.getElementById('hype-day-conflicts');
        allDays.forEach(d => {
            const isSelected = currentDays.includes(d);
            const takenBy = takenMap[d];
            const isTaken = takenBy && !isSelected;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.dataset.day = d;
            btn.textContent = dayLabels[d];
            btn.style.cssText = 'padding:8px 14px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;border:1px solid var(--border-primary);transition:all 0.15s;';
            if (isTaken) {
                btn.style.background = 'var(--bg-primary)';
                btn.style.color = '#555';
                btn.style.cursor = 'not-allowed';
                btn.style.opacity = '0.5';
                btn.style.textDecoration = 'line-through';
                btn.disabled = true;
            } else if (isSelected) {
                btn.style.background = '#34c759';
                btn.style.color = '#fff';
                btn.style.borderColor = '#34c759';
                btn.dataset.active = 'true';
            } else {
                btn.style.background = 'var(--bg-primary)';
                btn.style.color = 'var(--text-secondary)';
                btn.dataset.active = 'false';
            }
            if (!isTaken) {
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
            }
            toggleContainer.appendChild(btn);
        });
        const takenDays = Object.entries(takenMap).filter(([d]) => !currentDays.includes(d));
        if (takenDays.length > 0) {
            const grouped = {};
            takenDays.forEach(([d, name]) => { if (!grouped[name]) grouped[name] = []; grouped[name].push(dayLabels[d]); });
            conflictLabel.textContent = Object.entries(grouped).map(([name, days]) => `${days.join(', ')} used by "${name}"`).join(' · ');
            conflictLabel.style.display = 'block';
        }
    }

    async function saveFlow(editId) {
        const name = document.getElementById('hype-flow-name').value.trim();
        const promptId = document.getElementById('hype-flow-prompt').value;
        const mc = parseInt(document.getElementById('hype-flow-count').value) || 3;
        const iv = parseInt(document.getElementById('hype-flow-interval').value) || 5;
        const ivMax = parseInt(document.getElementById('hype-flow-interval-max')?.value) || iv;
        const dl = parseInt(document.getElementById('hype-flow-delay').value) || 10;
        const selectedDays = Array.from(document.querySelectorAll('#hype-day-toggles button[data-active="true"]')).map(b => b.dataset.day);
        if (selectedDays.length === 0) { alert('Please select at least one active day'); return; }
        const days = selectedDays.join(',');
        const ctaEnabled = document.getElementById('hype-flow-cta-enabled')?.checked || false;
        const ctaDelay = parseInt(document.getElementById('hype-flow-cta-delay')?.value) || 30;
        const ctaIntro = document.getElementById('hype-flow-cta-intro')?.value?.trim() || '';
        const ctaVipLabel = document.getElementById('hype-flow-cta-vip-label')?.value?.trim() || '';
        const ctaVipUrl = document.getElementById('hype-flow-cta-vip-url')?.value?.trim() || '';
        const ctaSupportLabel = document.getElementById('hype-flow-cta-support-label')?.value?.trim() || '';
        const ctaSupportUrl = document.getElementById('hype-flow-cta-support-url')?.value?.trim() || '';
        if (!name) { alert('Please enter a flow name'); return; }
        try {
            const headers = await getAuthHeaders();
            headers['Content-Type'] = 'application/json';
            const url = editId ? `/api/hypechat/flows/${editId}` : '/api/hypechat/flows';
            const resp = await fetch(url, { method: editId ? 'PUT' : 'POST', headers, body: JSON.stringify({ name, prompt_id: promptId || null, message_count: mc, interval_minutes: iv, interval_max_minutes: ivMax, delay_after_cta_minutes: dl, active_days: days, cta_enabled: ctaEnabled, cta_delay_minutes: ctaDelay, cta_intro_text: ctaIntro, cta_vip_label: ctaVipLabel, cta_vip_url: ctaVipUrl, cta_support_label: ctaSupportLabel, cta_support_url: ctaSupportUrl }) });
            if (resp.ok) { document.getElementById('hype-flow-modal')?.remove(); await loadFlows(); }
            else { const err = await resp.json(); alert(err.error || 'Failed to save'); }
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
        const confirmed = await showModalConfirm('Trigger Flow',
            `Manually trigger "${escapeHtml(flow.name)}"? This will schedule ${flow.message_count} messages${flow.cta_enabled ? ' + CTA' : ''}.`,
            { confirmText: 'Trigger' });
        if (confirmed) {
            await doTriggerFlow(id);
        }
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
        loadHypeBot, loadPrompts, loadFlows, openPromptModal, savePrompt, editPrompt, deletePrompt,
        previewPrompt, previewFlow, regeneratePreview, regenerateFlowPreview,
        openFlowModal, saveFlow, editFlow, deleteFlow,
        setFlowStatus, triggerFlow, viewAnalytics
    };
})();
