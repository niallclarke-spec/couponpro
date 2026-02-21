window.HypeBotModule = (function() {
    let prompts = [];
    let flows = [];

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async function loadHypeBot() {
        await Promise.all([loadPrompts(), loadFlows()]);
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
                <div class="hype-card-header">
                    <span class="hype-card-title">${escapeHtml(p.name)}</span>
                    <span class="hype-card-meta">${new Date(p.created_at).toLocaleDateString()}</span>
                </div>
                <div class="hype-card-prompt">${escapeHtml(p.custom_prompt)}</div>
                <div class="hype-card-actions">
                    <button onclick="window.HypeBotModule.previewPrompt('${p.id}')">Preview</button>
                    <button onclick="window.HypeBotModule.editPrompt('${p.id}')">Edit</button>
                    <button class="btn-danger" onclick="window.HypeBotModule.deletePrompt('${p.id}')">Delete</button>
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
            <div class="hype-flow-card">
                <div class="hype-card-header">
                    <div>
                        <span class="hype-card-title">${escapeHtml(f.name)}</span>
                        <span class="hype-flow-status ${f.status}">${f.status}</span>
                    </div>
                    <span class="hype-card-meta">Prompt: ${f.prompt_name ? escapeHtml(f.prompt_name) : 'None'}</span>
                </div>
                <div class="hype-flow-config">
                    <div class="hype-config-item">Messages<br><span class="hype-config-value">${f.message_count}</span></div>
                    <div class="hype-config-item">Interval<br><span class="hype-config-value">${f.interval_minutes} min</span></div>
                    <div class="hype-config-item">Delay after CTA<br><span class="hype-config-value">${f.delay_after_cta_minutes} min</span></div>
                    <div class="hype-config-item">Active Days<br><span class="hype-config-value">${f.active_days}</span></div>
                </div>
                <div class="hype-card-actions">
                    ${f.status === 'paused'
                        ? `<button onclick="window.HypeBotModule.setFlowStatus('${f.id}', 'active')" style="color:#34c759;border-color:#34c759;">Activate</button>`
                        : `<button onclick="window.HypeBotModule.setFlowStatus('${f.id}', 'paused')" style="color:#ff9f0a;border-color:#ff9f0a;">Pause</button>`}
                    <button onclick="window.HypeBotModule.previewFlow('${f.id}')">Preview</button>
                    <button onclick="window.HypeBotModule.triggerFlow('${f.id}')">Trigger Now</button>
                    <button onclick="window.HypeBotModule.editFlow('${f.id}')">Edit</button>
                    <button onclick="window.HypeBotModule.viewAnalytics('${f.id}')">Analytics</button>
                    <button class="btn-danger" onclick="window.HypeBotModule.deleteFlow('${f.id}')">Delete</button>
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

        return messages.map((msg, i) => {
            const step = i + 1;
            const offsetMin = delay + (i * interval);
            const arcLabel = _getArcLabel(step, messageCount);
            const arcColor = _getArcColor(step, messageCount);
            const isLast = step === messageCount;

            return `
                <div style="display:flex;gap:16px;position:relative;">
                    <div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;width:36px;">
                        <div style="width:28px;height:28px;border-radius:50%;background:${arcColor};display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#fff;">${step}</div>
                        ${!isLast ? '<div style="flex:1;width:2px;background:var(--border-primary);margin:4px 0;"></div>' : ''}
                    </div>
                    <div style="flex:1;padding-bottom:${isLast ? '0' : '16px'};">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                            <span style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;">+${offsetMin} min</span>
                            <span style="font-size:10px;font-weight:600;color:${arcColor};background:${arcColor}18;padding:2px 8px;border-radius:10px;text-transform:uppercase;">${escapeHtml(arcLabel)}</span>
                        </div>
                        <div style="background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:10px;padding:14px 16px;">
                            <div style="font-size:14px;color:var(--text-primary);line-height:1.6;">${msg ? escapeHtml(msg) : '<span style="color:var(--text-muted);font-style:italic;">Failed to generate</span>'}</div>
                        </div>
                    </div>
                </div>`;
        }).join('');
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
                    <div class="modal-body" style="padding:24px;">
                        <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
                            <label style="font-size:13px;font-weight:500;color:var(--text-secondary);white-space:nowrap;">Messages:</label>
                            <input type="number" id="preview-msg-count" min="1" max="10" value="${defaultCount}" style="width:60px;padding:6px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;text-align:center;">
                        </div>
                        <div id="preview-loading" style="text-align:center;color:var(--text-muted);padding:40px 0;">
                            <div style="font-size:14px;">Generating flow preview...</div>
                            <div style="font-size:12px;margin-top:6px;color:var(--text-muted);">Creating a coherent message sequence</div>
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
                    <div class="modal-body" style="padding:24px;">
                        <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
                            <label style="font-size:13px;font-weight:500;color:var(--text-secondary);white-space:nowrap;">Messages:</label>
                            <input type="number" id="preview-msg-count" min="1" max="10" value="${flow.message_count}" style="width:60px;padding:6px 10px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;text-align:center;" readonly>
                        </div>
                        <div id="preview-loading" style="text-align:center;color:var(--text-muted);padding:40px 0;">
                            <div style="font-size:14px;">Generating flow preview...</div>
                            <div style="font-size:12px;margin-top:6px;color:var(--text-muted);">Creating a coherent ${flow.message_count}-message sequence</div>
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
            const timelineHtml = _renderTimelineMessages(messages, count, interval, delay);

            r.innerHTML = `
                <div style="margin-bottom:16px;">
                    ${timelineHtml}
                </div>
                <div style="background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:10px;padding:14px 16px;">
                    <div style="font-size:11px;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px;font-weight:600;">Context Injected</div>
                    <div style="font-size:13px;color:var(--text-secondary);line-height:1.5;white-space:pre-wrap;">${escapeHtml(data.context || '')}</div>
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
                <div class="modal-content" style="max-width:520px;">
                    <div class="modal-header"><h3>${title}</h3><button class="modal-close" onclick="document.getElementById('hype-flow-modal').remove()">&times;</button></div>
                    <div class="modal-body">
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
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                            <div><label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Messages</label><input type="number" id="hype-flow-count" min="1" max="10" value="${flow ? flow.message_count : 3}" style="width:100%;padding:10px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;box-sizing:border-box;"></div>
                            <div><label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Interval (min)</label><input type="number" id="hype-flow-interval" min="5" value="${flow ? flow.interval_minutes : 90}" style="width:100%;padding:10px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;box-sizing:border-box;"></div>
                            <div><label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Delay after CTA (min)</label><input type="number" id="hype-flow-delay" min="0" value="${flow ? flow.delay_after_cta_minutes : 10}" style="width:100%;padding:10px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;box-sizing:border-box;"></div>
                            <div><label style="display:block;font-size:13px;font-weight:500;color:var(--text-secondary);margin-bottom:6px;">Active Days</label><input type="text" id="hype-flow-days" value="${flow ? flow.active_days : 'mon-fri'}" placeholder="mon-fri" style="width:100%;padding:10px 12px;background:var(--bg-primary);border:1px solid var(--border-primary);border-radius:8px;color:var(--text-primary);font-size:14px;box-sizing:border-box;"></div>
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
    }

    async function saveFlow(editId) {
        const name = document.getElementById('hype-flow-name').value.trim();
        const promptId = document.getElementById('hype-flow-prompt').value;
        const mc = parseInt(document.getElementById('hype-flow-count').value) || 3;
        const iv = parseInt(document.getElementById('hype-flow-interval').value) || 90;
        const dl = parseInt(document.getElementById('hype-flow-delay').value) || 10;
        const days = document.getElementById('hype-flow-days').value.trim() || 'mon-fri';
        if (!name) { alert('Please enter a flow name'); return; }
        try {
            const headers = await getAuthHeaders();
            headers['Content-Type'] = 'application/json';
            const url = editId ? `/api/hypechat/flows/${editId}` : '/api/hypechat/flows';
            const resp = await fetch(url, { method: editId ? 'PUT' : 'POST', headers, body: JSON.stringify({ name, prompt_id: promptId || null, message_count: mc, interval_minutes: iv, delay_after_cta_minutes: dl, active_days: days }) });
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
        if (typeof showModalConfirm === 'function') {
            showModalConfirm('Trigger Flow', `Manually trigger "${escapeHtml(flow.name)}"? This will schedule ${flow.message_count} messages.`, 'Trigger', async () => { await doTriggerFlow(id); });
        } else { await doTriggerFlow(id); }
    }
    async function doTriggerFlow(id) {
        try {
            const h = await getAuthHeaders(); h['Content-Type'] = 'application/json';
            const resp = await fetch(`/api/hypechat/flows/${id}/trigger`, { method:'POST', headers:h });
            const data = await resp.json();
            if (data.success) alert(`Scheduled ${data.messages_scheduled} messages`);
            else alert(data.error || 'Failed to trigger');
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
        loadHypeBot, loadPrompts, loadFlows, openPromptModal, savePrompt, editPrompt, deletePrompt,
        previewPrompt, previewFlow, regeneratePreview, regenerateFlowPreview,
        openFlowModal, saveFlow, editFlow, deleteFlow,
        setFlowStatus, triggerFlow, viewAnalytics
    };
})();
