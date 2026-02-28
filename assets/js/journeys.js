(function() {
    'use strict';

    const MAX_JOURNEYS = 6;

    function timeToSeconds(value, unit) {
        const v = parseInt(value, 10) || 0;
        switch (unit) {
            case 'hours': return v * 3600;
            case 'minutes': return v * 60;
            case 'days': return v * 86400;
            default: return v;
        }
    }

    function secondsToTimeUnit(totalSeconds) {
        if (!totalSeconds || totalSeconds <= 0) return { value: 0, unit: 'seconds' };
        if (totalSeconds >= 86400 && totalSeconds % 86400 === 0) return { value: totalSeconds / 86400, unit: 'days' };
        if (totalSeconds >= 3600 && totalSeconds % 3600 === 0) return { value: totalSeconds / 3600, unit: 'hours' };
        if (totalSeconds >= 60 && totalSeconds % 60 === 0) return { value: totalSeconds / 60, unit: 'minutes' };
        return { value: totalSeconds, unit: 'seconds' };
    }

    const state = {
        journeys: [],
        currentJourneyId: null,
        steps: [],
        stepAnalytics: {},
        editingStepIndex: null,
        selectedStatus: 'draft',
        loading: false,
        messageBotUsername: null,
        telethonUsername: null,
        journeysLoaded: false,
        lastLoadTime: null,
        listStatusFilter: 'all',
        listSearchQuery: ''
    };

    let config = {
        getAuthHeaders: null,
        showToast: null,
        showLoading: null,
        hideLoading: null,
        escapeHtml: null,
        confirmDialog: null
    };

    function escapeHtmlDefault(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async function loadMessageBotUsername() {
        try {
            const headers = await config.getAuthHeaders();
            const resp = await fetch('/api/connections', { headers, credentials: 'include' });
            if (resp.ok) {
                const data = await resp.json();
                const messageBot = (data.connections || []).find(c => c.bot_role === 'message_bot');
                state.messageBotUsername = messageBot?.bot_username || null;
            }
        } catch (err) {
            console.error('Failed to load message bot:', err);
        }
    }

    async function loadTelethonUsername() {
        try {
            const headers = await config.getAuthHeaders();
            const resp = await fetch('/api/journeys/user-account', { headers, credentials: 'include' });
            if (resp.ok) {
                const data = await resp.json();
                state.telethonUsername = data.username || null;
            }
        } catch (err) {
            console.error('Failed to load Telethon username:', err);
        }
        renderConnectionBanner();
    }

    function renderConnectionBanner() {
        const bar = document.getElementById('journeys-connection-bar');
        if (!bar) return;
        const escapeHtml = config.escapeHtml || escapeHtmlDefault;
        const connected = !!state.telethonUsername;
        const dotClass = connected ? 'connected' : 'disconnected';
        const usernameDisplay = state.telethonUsername ? escapeHtml(state.telethonUsername.startsWith('@') ? state.telethonUsername : '@' + state.telethonUsername) : 'Not configured';
        const tgIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z"/></svg>';
        bar.innerHTML = `
            <div class="connection-banner">
                <span class="conn-icon">${tgIcon}</span>
                <span class="conn-username">${usernameDisplay}</span>
                <span class="conn-label">User Account</span>
                <span class="conn-dot ${dotClass}"></span>
            </div>`;
    }

    function getDeepLinkUrl(startParam) {
        if (!state.messageBotUsername || !startParam) return null;
        const username = state.messageBotUsername.replace(/^@/, '');
        return `https://t.me/${username}?start=${encodeURIComponent(startParam)}`;
    }

    async function loadJourneys(forceRefresh = false) {
        const cacheExpiry = 60 * 1000;
        const now = Date.now();
        if (!forceRefresh && state.journeysLoaded && state.lastLoadTime && (now - state.lastLoadTime < cacheExpiry)) {
            renderListView();
            return;
        }

        try {
            state.loading = true;
            const headers = await config.getAuthHeaders();

            await Promise.all([loadMessageBotUsername(), loadTelethonUsername()]);

            const resp = await fetch('/api/journeys', { headers, credentials: 'include' });
            if (resp.ok) {
                const data = await resp.json();
                state.journeys = data.journeys || [];
                state.journeysLoaded = true;
                state.lastLoadTime = now;
                renderListView();
            } else {
                config.showToast('Failed to load journeys', 'error');
            }
        } catch (err) {
            console.error('Failed to load journeys:', err);
            config.showToast('Failed to load journeys', 'error');
        } finally {
            state.loading = false;
        }
    }

    function invalidateJourneysCache() {
        state.journeysLoaded = false;
        state.lastLoadTime = null;
    }

    function renderJourneys() {}

    function _getTriggerDisplay(journey) {
        const triggers = journey.triggers || [];
        const first = triggers[0];
        if (!first) return '—';
        const tt = first.trigger_type || 'deep_link';
        if (tt === 'direct_message') {
            const kw = first.trigger_config?.keyword;
            return kw ? `DM: ${kw}` : 'DM: any';
        }
        if (tt === 'api_event') {
            return `API: ${first.trigger_config?.event_name || '—'}`;
        }
        const val = first.trigger_config?.start_param || first.trigger_config?.value || '';
        return val ? `Link: ${val}` : 'Deep link';
    }

    function _formatDate(dateStr) {
        if (!dateStr) return '—';
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
    }

    function _getStatusDot(status) {
        const colours = { active: '#22c55e', paused: '#f59e0b', draft: '#64748b', stopped: '#ef4444' };
        const c = colours[status] || '#64748b';
        return `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${c};box-shadow:0 0 0 2px ${c}33;flex-shrink:0;"></span>`;
    }

    function renderListView() {
        const listView = document.getElementById('journey-list-view');
        if (!listView) return;

        const escapeHtml = config.escapeHtml || escapeHtmlDefault;
        const count = state.journeys.length;

        let filtered = state.journeys;
        if (state.listStatusFilter !== 'all') {
            filtered = filtered.filter(j => j.status === state.listStatusFilter);
        }
        if (state.listSearchQuery) {
            const q = state.listSearchQuery.toLowerCase();
            filtered = filtered.filter(j => (j.name || '').toLowerCase().includes(q));
        }

        const statusFilters = ['all', 'active', 'draft', 'stopped'];
        const filterLabels = { all: 'All', active: 'Active', draft: 'Draft', stopped: 'Stopped' };

        let rowsHtml = '';
        if (filtered.length === 0) {
            rowsHtml = `<tr><td colspan="6" style="text-align:center;padding:48px 24px;color:var(--text-secondary);">
                ${state.journeys.length === 0 ? 'No journeys yet. Create your first to start automating user conversations.' : 'No journeys match your filters.'}
            </td></tr>`;
        } else {
            filtered.forEach(j => {
                const statusLabel = { active: 'Active', paused: 'Paused', draft: 'Draft', stopped: 'Stopped' }[j.status] || j.status;
                const triggerDisplay = escapeHtml(_getTriggerDisplay(j));
                const created = _formatDate(j.created_at);
                const steps = j.step_count || 0;

                rowsHtml += `
                <tr class="journey-table-row" data-id="${escapeHtml(j.id)}" onclick="window.JourneysModule.openJourneyEditor('${escapeHtml(j.id)}')" style="cursor:pointer;">
                    <td style="padding:14px 16px;font-weight:500;color:var(--text-primary);">${escapeHtml(j.name || 'Untitled')}</td>
                    <td style="padding:14px 16px;">
                        <span style="display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--text-secondary);">
                            ${_getStatusDot(j.status)} ${statusLabel}
                        </span>
                    </td>
                    <td style="padding:14px 16px;font-size:13px;color:var(--text-secondary);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${triggerDisplay}</td>
                    <td style="padding:14px 16px;font-size:13px;color:var(--text-secondary);">${steps} ${steps === 1 ? 'step' : 'steps'}</td>
                    <td style="padding:14px 16px;font-size:13px;color:var(--text-secondary);">${created}</td>
                    <td style="padding:14px 16px;text-align:right;" onclick="event.stopPropagation()">
                        <button class="journey-menu-btn" onclick="_showJourneyMenuGlobal('${escapeHtml(j.id)}', this)" title="Actions" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;padding:4px 8px;border-radius:6px;font-size:18px;line-height:1;">⋮</button>
                    </td>
                </tr>`;
            });
        }

        listView.innerHTML = `
            <div style="padding:24px 28px 0;">
                <div id="journeys-connection-bar" style="margin-bottom:16px;"></div>
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;gap:16px;flex-wrap:wrap;">
                    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
                        <h1 style="margin:0;font-size:22px;font-weight:700;color:var(--text-primary);">Support Chat</h1>
                        <span class="limit-badge" id="journeys-limit-badge">${count} / ${MAX_JOURNEYS}</span>
                    </div>
                    <button class="btn" id="create-journey-btn" onclick="window.JourneysModule.openJourneyEditor()" ${count >= MAX_JOURNEYS ? 'disabled title="Maximum journeys reached"' : ''} style="gap:6px;display:flex;align-items:center;">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" width="16" height="16"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>
                        New Journey
                    </button>
                </div>
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;flex-wrap:wrap;">
                    <div style="position:relative;flex:1;min-width:200px;max-width:340px;">
                        <svg style="position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--text-secondary);pointer-events:none;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                        <input type="text" id="journey-list-search" placeholder="Search journeys…" value="${escapeHtml(state.listSearchQuery)}" oninput="window.JourneysModule._onJourneySearch(this.value)" style="width:100%;padding:8px 10px 8px 32px;background:var(--input-bg);border:1px solid var(--border-color);border-radius:8px;color:var(--text-primary);font-size:13px;box-sizing:border-box;">
                    </div>
                    <div style="display:flex;gap:4px;">
                        ${statusFilters.map(s => `
                        <button onclick="window.JourneysModule._onJourneyStatusFilter('${s}')"
                            style="padding:6px 14px;border-radius:20px;border:1px solid var(--border-color);font-size:12px;font-weight:500;cursor:pointer;background:${state.listStatusFilter === s ? 'var(--accent-color)' : 'var(--card-bg)'};color:${state.listStatusFilter === s ? '#fff' : 'var(--text-secondary)'};">
                            ${filterLabels[s]}
                        </button>`).join('')}
                    </div>
                </div>
            </div>
            <div style="padding:0 28px 28px;overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;">
                    <thead>
                        <tr style="border-bottom:1px solid var(--border-color);">
                            <th style="padding:10px 16px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-secondary);">Name</th>
                            <th style="padding:10px 16px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-secondary);">Status</th>
                            <th style="padding:10px 16px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-secondary);">Trigger</th>
                            <th style="padding:10px 16px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-secondary);">Steps</th>
                            <th style="padding:10px 16px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-secondary);">Created</th>
                            <th style="padding:10px 16px;"></th>
                        </tr>
                    </thead>
                    <tbody id="journeys-table-body">
                        ${rowsHtml}
                    </tbody>
                </table>
            </div>`;

        renderConnectionBanner();
    }

    function _onJourneySearch(query) {
        state.listSearchQuery = query;
        _refilterTable();
    }

    function _onJourneyStatusFilter(status) {
        state.listStatusFilter = status;
        renderListView();
    }

    function _refilterTable() {
        const body = document.getElementById('journeys-table-body');
        if (!body) { renderListView(); return; }

        const escapeHtml = config.escapeHtml || escapeHtmlDefault;
        const q = state.listSearchQuery.toLowerCase();

        let filtered = state.journeys;
        if (state.listStatusFilter !== 'all') {
            filtered = filtered.filter(j => j.status === state.listStatusFilter);
        }
        if (q) {
            filtered = filtered.filter(j => (j.name || '').toLowerCase().includes(q));
        }

        if (filtered.length === 0) {
            body.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:48px 24px;color:var(--text-secondary);">No journeys match your search.</td></tr>`;
            return;
        }

        body.innerHTML = filtered.map(j => {
            const statusLabel = { active: 'Active', paused: 'Paused', draft: 'Draft', stopped: 'Stopped' }[j.status] || j.status;
            const triggerDisplay = escapeHtml(_getTriggerDisplay(j));
            const created = _formatDate(j.created_at);
            const steps = j.step_count || 0;
            return `
            <tr class="journey-table-row" data-id="${escapeHtml(j.id)}" onclick="window.JourneysModule.openJourneyEditor('${escapeHtml(j.id)}')" style="cursor:pointer;">
                <td style="padding:14px 16px;font-weight:500;color:var(--text-primary);">${escapeHtml(j.name || 'Untitled')}</td>
                <td style="padding:14px 16px;">
                    <span style="display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--text-secondary);">
                        ${_getStatusDot(j.status)} ${statusLabel}
                    </span>
                </td>
                <td style="padding:14px 16px;font-size:13px;color:var(--text-secondary);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${triggerDisplay}</td>
                <td style="padding:14px 16px;font-size:13px;color:var(--text-secondary);">${steps} ${steps === 1 ? 'step' : 'steps'}</td>
                <td style="padding:14px 16px;font-size:13px;color:var(--text-secondary);">${created}</td>
                <td style="padding:14px 16px;text-align:right;" onclick="event.stopPropagation()">
                    <button class="journey-menu-btn" onclick="_showJourneyMenuGlobal('${escapeHtml(j.id)}', this)" title="Actions" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;padding:4px 8px;border-radius:6px;font-size:18px;line-height:1;">⋮</button>
                </td>
            </tr>`;
        }).join('');
    }

    window._showJourneyMenuGlobal = function(journeyId, btnEl) {
        document.querySelectorAll('.journey-ctx-menu').forEach(m => m.remove());

        const journey = state.journeys.find(j => j.id === journeyId);
        if (!journey) return;

        const rect = btnEl.getBoundingClientRect();
        const menu = document.createElement('div');
        menu.className = 'journey-ctx-menu hype-flow-menu';
        menu.style.cssText = `position:fixed;z-index:9999;background:var(--card-bg,#1e2a3a);border:1px solid var(--border-color,rgba(255,255,255,.1));border-radius:10px;padding:6px;min-width:160px;box-shadow:0 8px 32px rgba(0,0,0,.4);`;

        const menuTop = rect.bottom + 4;
        const menuLeft = rect.right - 160;
        menu.style.top = menuTop + 'px';
        menu.style.left = Math.max(8, menuLeft) + 'px';

        const items = [
            { label: 'Edit', icon: '✏️', action: () => window.JourneysModule.openJourneyEditor(journeyId) }
        ];

        if (journey.status === 'draft') {
            items.push({ label: 'Publish', icon: '▶', action: () => window.JourneysModule.publishJourney(journeyId) });
        } else if (journey.status === 'active') {
            items.push({ label: 'Stop', icon: '⏸', action: () => window.JourneysModule.stopJourney(journeyId) });
        }

        if (journey.status !== 'draft' || true) {
            items.push({ label: 'Duplicate', icon: '⧉', action: () => window.JourneysModule.duplicateJourney(journeyId) });
        }

        items.push({ label: 'Delete', icon: '🗑', action: () => window.JourneysModule.deleteJourney(journeyId), danger: true });

        items.forEach(item => {
            const btn = document.createElement('button');
            btn.style.cssText = `display:flex;align-items:center;gap:8px;width:100%;padding:8px 12px;background:none;border:none;border-radius:6px;cursor:pointer;font-size:13px;color:${item.danger ? '#ef4444' : 'var(--text-primary)'};text-align:left;`;
            btn.innerHTML = `<span style="width:16px;text-align:center;">${item.icon}</span> ${item.label}`;
            btn.onmouseover = () => btn.style.background = 'rgba(255,255,255,.06)';
            btn.onmouseout = () => btn.style.background = 'none';
            btn.onclick = () => { menu.remove(); item.action(); };
            menu.appendChild(btn);
        });

        document.body.appendChild(menu);

        setTimeout(() => {
            document.addEventListener('click', function handler(e) {
                if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', handler); }
            });
        }, 0);
    };

    function _buildEditorHTML(journey) {
        const escapeHtml = config.escapeHtml || escapeHtmlDefault;
        const isNew = !journey;
        const status = journey?.status || 'draft';
        const name = journey?.name || '';

        let publishBtnHtml = '';
        if (!isNew) {
            if (status === 'draft') {
                publishBtnHtml = `<button id="journey-publish-btn" onclick="window.JourneysModule.publishJourney('${escapeHtml(journey.id)}')" style="padding:8px 18px;border-radius:8px;border:none;background:#22c55e;color:#fff;font-weight:600;font-size:13px;cursor:pointer;display:flex;align-items:center;gap:6px;">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg> Publish
                </button>`;
            } else if (status === 'active') {
                publishBtnHtml = `<button id="journey-publish-btn" onclick="window.JourneysModule.stopJourney('${escapeHtml(journey.id)}')" style="padding:8px 18px;border-radius:8px;border:none;background:rgba(245,158,11,.15);color:#f59e0b;border:1px solid rgba(245,158,11,.3);font-weight:600;font-size:13px;cursor:pointer;display:flex;align-items:center;gap:6px;">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="14" height="14"><rect x="6" y="6" width="12" height="12" rx="1"/></svg> Stop
                </button>`;
            } else {
                publishBtnHtml = `<span style="padding:8px 14px;font-size:13px;color:var(--text-secondary);border:1px solid var(--border-color);border-radius:8px;">Stopped — Duplicate to restart</span>`;
            }
        }

        const createdDisplay = journey ? _formatDate(journey.created_at) : '—';
        const stepsDisplay = journey ? (journey.step_count || 0) : 0;

        const delaySeconds = journey?.start_delay_seconds || 0;
        const delayParsed = secondsToTimeUnit(delaySeconds);
        const delayValue = delayParsed.value;
        const delayUnit = delayParsed.unit === 'seconds' ? 'seconds' : (delayParsed.unit === 'hours' ? 'hours' : 'minutes');

        const statusLabels = ['draft', 'active', 'stopped'];

        return `
        <div style="flex-shrink:0;display:flex;align-items:center;gap:12px;padding:14px 20px;border-bottom:1px solid var(--border-color);background:var(--section-bg,var(--bg-primary));">
            <button onclick="window.JourneysModule.closeJourneyEditor()" style="display:flex;align-items:center;gap:6px;background:none;border:none;color:var(--text-secondary);cursor:pointer;padding:6px 10px;border-radius:8px;font-size:13px;font-weight:500;white-space:nowrap;" onmouseover="this.style.background='rgba(255,255,255,.06)'" onmouseout="this.style.background='none'">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><polyline points="15 18 9 12 15 6"/></svg>
                Journeys
            </button>
            <div style="width:1px;height:20px;background:var(--border-color);flex-shrink:0;"></div>
            <input type="text" id="journey-name-input" value="${escapeHtml(name)}" placeholder="Journey name…" style="flex:1;background:none;border:none;color:var(--text-primary);font-size:16px;font-weight:600;outline:none;min-width:0;padding:4px 0;">
            <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;">
                ${publishBtnHtml}
            </div>
        </div>
        <div style="flex:1;display:flex;overflow:hidden;">
            <div style="flex:1;overflow-y:auto;padding:24px 28px;">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;">
                    <div style="font-size:15px;font-weight:600;color:var(--text-primary);">Message Steps</div>
                    <button onclick="window.JourneysModule.addStep()" style="display:flex;align-items:center;gap:6px;padding:8px 14px;border-radius:8px;border:1px solid var(--border-color);background:var(--card-bg);color:var(--text-primary);font-size:13px;font-weight:500;cursor:pointer;">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" width="14" height="14"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>
                        Add Step
                    </button>
                </div>
                <div class="steps-list" id="steps-list">
                    <div class="steps-empty" id="steps-empty" style="${isNew ? '' : 'display:none;'}">No steps yet. Add your first message step above.</div>
                </div>
            </div>
            <div style="width:272px;flex-shrink:0;border-left:1px solid var(--border-color);overflow-y:auto;padding:20px 16px;background:var(--section-bg,var(--bg-primary));">
                <div style="margin-bottom:20px;">
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--text-secondary);margin-bottom:10px;">Trigger Type</div>
                    <select class="form-select" id="journey-trigger-type" onchange="window.JourneysModule.onTriggerTypeChange && window.JourneysModule.onTriggerTypeChange()" style="width:100%;font-size:13px;">
                        <option value="deep_link">Deep Link</option>
                        <option value="direct_message">Direct Message</option>
                        <option value="api_event">API Event</option>
                    </select>
                    <div class="form-hint" id="trigger-type-hint" style="margin-top:6px;font-size:12px;">Journeys are triggered when users start the bot via a deep link.</div>
                </div>

                <div style="margin-bottom:20px;">
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--text-secondary);margin-bottom:10px;" id="trigger-value-label">Trigger Value</div>
                    <div id="trigger-value-container">
                        <input type="text" class="form-input" id="journey-trigger-value" placeholder="e.g., welcome_promo" style="width:100%;font-size:13px;box-sizing:border-box;" oninput="window.JourneysModule.updateDeepLinkPreview()">
                    </div>
                    <div class="form-hint" id="trigger-value-hint" style="margin-top:6px;font-size:12px;">The start parameter value</div>
                    <div class="deeplink-preview" id="deeplink-preview" style="display:none;margin-top:10px;">
                        <div class="deeplink-preview-label" style="font-size:11px;color:var(--text-secondary);margin-bottom:4px;">Your Deep Link:</div>
                        <div class="deeplink-preview-url" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                            <code id="deeplink-preview-url" style="font-size:11px;word-break:break-all;color:var(--accent-color);flex:1;"></code>
                            <button class="btn-copy" onclick="window.JourneysModule.copyDeepLinkFromPreview()" title="Copy link" style="flex-shrink:0;">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                            </button>
                            <a id="deeplink-preview-test" href="#" target="_blank" class="btn-test" title="Test link" style="flex-shrink:0;">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                            </a>
                        </div>
                        <div class="deeplink-preview-warning" id="deeplink-preview-warning" style="display:none;font-size:12px;color:#f59e0b;margin-top:4px;">Configure Message Bot in Connections tab first</div>
                    </div>
                </div>

                <div style="margin-bottom:20px;">
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--text-secondary);margin-bottom:10px;">Start Delay <span style="font-weight:400;opacity:.5;">(optional)</span></div>
                    <div style="display:flex;gap:8px;align-items:center;">
                        <input type="number" class="form-input" id="journey-start-delay-value" placeholder="0" min="0" max="10800" value="${delayValue}" style="width:70px;text-align:center;font-size:13px;">
                        <select class="form-input" id="journey-start-delay-unit" style="flex:1;font-size:13px;">
                            <option value="seconds" ${delayUnit === 'seconds' ? 'selected' : ''}>Seconds</option>
                            <option value="minutes" ${delayUnit === 'minutes' ? 'selected' : ''}>Minutes</option>
                            <option value="hours" ${delayUnit === 'hours' ? 'selected' : ''}>Hours</option>
                        </select>
                    </div>
                    <div class="form-hint" style="margin-top:6px;font-size:12px;">Delay before the first message is sent. 0 = instant.</div>
                </div>

                <div style="margin-bottom:20px;">
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--text-secondary);margin-bottom:10px;">Status</div>
                    <div class="status-options" style="display:flex;gap:6px;flex-wrap:wrap;">
                        ${statusLabels.map(s => `
                        <div class="status-option${state.selectedStatus === s ? ' selected' : ''}" onclick="window.JourneysModule.selectStatus('${s}')" data-status="${s}" style="padding:7px 14px;border-radius:8px;border:1px solid var(--border-color);cursor:pointer;font-size:12px;font-weight:500;background:${state.selectedStatus === s ? 'var(--accent-color)' : 'var(--card-bg)'};color:${state.selectedStatus === s ? '#fff' : 'var(--text-secondary)'};">
                            <div class="status-option-label">${s.charAt(0).toUpperCase() + s.slice(1)}</div>
                        </div>`).join('')}
                    </div>
                    <div class="active-warning" id="active-warning" style="display:none;margin-top:10px;padding:10px 12px;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:8px;font-size:12px;color:#f59e0b;display:flex;align-items:flex-start;gap:8px;">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" width="16" height="16" style="flex-shrink:0;margin-top:1px;"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>
                        <span id="active-warning-text">Active journeys will start sending messages to users immediately when they join via the deep link.</span>
                    </div>
                </div>

                <button onclick="window.JourneysModule.saveJourneySettings()" style="width:100%;padding:10px 16px;border-radius:8px;border:none;background:var(--accent-color);color:#fff;font-weight:600;font-size:13px;cursor:pointer;margin-bottom:20px;">Save Settings</button>

                <div style="border-top:1px solid var(--border-color);padding-top:16px;display:flex;flex-direction:column;gap:8px;">
                    <div style="display:flex;justify-content:space-between;font-size:12px;">
                        <span style="color:var(--text-secondary);">Created</span>
                        <span style="color:var(--text-primary);">${createdDisplay}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;font-size:12px;" id="editor-meta-steps">
                        <span style="color:var(--text-secondary);">Steps</span>
                        <span style="color:var(--text-primary);" id="editor-steps-count">${stepsDisplay}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;font-size:12px;">
                        <span style="color:var(--text-secondary);">Status</span>
                        <span style="color:var(--text-primary);" id="editor-status-display">${status.charAt(0).toUpperCase() + status.slice(1)}</span>
                    </div>
                </div>
            </div>
        </div>`;
    }

    async function openJourneyEditor(journeyId = null) {
        state.currentJourneyId = journeyId;
        state.steps = [];
        state.stepAnalytics = {};
        state.selectedStatus = 'draft';

        const listView = document.getElementById('journey-list-view');
        const editorView = document.getElementById('journey-editor-view');
        if (!editorView) return;

        if (listView) listView.style.display = 'none';
        editorView.style.display = 'flex';
        editorView.style.flexDirection = 'column';

        await loadMessageBotUsername();

        const journey = journeyId ? state.journeys.find(j => j.id === journeyId) : null;
        state.selectedStatus = journey?.status || 'draft';

        editorView.innerHTML = _buildEditorHTML(journey);

        selectStatus(state.selectedStatus);
        onTriggerTypeChange();
        renderStepsList();

        if (journeyId) {
            await fetchJourneyDetail(journeyId);
            updateDeepLinkPreview();
        }
    }

    function openJourneyModal(journeyId = null) {
        return openJourneyEditor(journeyId);
    }

    function closeJourneyEditor() {
        const listView = document.getElementById('journey-list-view');
        const editorView = document.getElementById('journey-editor-view');
        if (editorView) { editorView.style.display = 'none'; editorView.innerHTML = ''; }
        if (listView) listView.style.display = '';
        state.currentJourneyId = null;
        state.steps = [];
        state.stepAnalytics = {};
    }

    function closeJourneyModal() {
        closeJourneyEditor();
    }

    async function saveJourneySettings() {
        const nameInput = document.getElementById('journey-name-input');
        const name = nameInput ? nameInput.value.trim() : '';
        const triggerValue = getTriggerValue().trim();
        const status = state.selectedStatus;

        if (!name) {
            config.showToast('Please enter a journey name', 'error');
            return;
        }

        try {
            if (config.showLoading) config.showLoading('Saving journey...');
            const headers = await config.getAuthHeaders(true);

            let journeyId = state.currentJourneyId;

            const delayVal = parseInt(document.getElementById('journey-start-delay-value')?.value || '0', 10) || 0;
            const delayUnit = document.getElementById('journey-start-delay-unit')?.value || 'minutes';
            const startDelaySeconds = delayUnit === 'hours' ? delayVal * 3600 : (delayUnit === 'minutes' ? delayVal * 60 : delayVal);

            if (journeyId) {
                const resp = await fetch(`/api/journeys/${journeyId}`, {
                    method: 'PUT',
                    headers,
                    body: JSON.stringify({ name, status, start_delay_seconds: startDelaySeconds }),
                    credentials: 'include'
                });
                if (!resp.ok) {
                    const data = await resp.json();
                    throw new Error(data.error || 'Failed to update journey');
                }
            } else {
                const botId = state.messageBotUsername || 'default';
                const resp = await fetch('/api/journeys', {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({ name, status, bot_id: botId, start_delay_seconds: startDelaySeconds }),
                    credentials: 'include'
                });
                const data = await resp.json();
                if (!resp.ok) {
                    throw new Error(data.error || 'Failed to create journey');
                }
                journeyId = data.journey.id;
                state.currentJourneyId = journeyId;
            }

            const triggerTypeSelect = document.getElementById('journey-trigger-type');
            const selectedTriggerType = triggerTypeSelect ? triggerTypeSelect.value : 'deep_link';

            if (selectedTriggerType === 'direct_message') {
                await fetch(`/api/journeys/${journeyId}/triggers`, {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({
                        trigger_type: 'direct_message',
                        trigger_config: { keyword: triggerValue },
                        is_active: true
                    }),
                    credentials: 'include'
                });
            } else if (selectedTriggerType === 'api_event' && triggerValue) {
                await fetch(`/api/journeys/${journeyId}/triggers`, {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({
                        trigger_type: 'api_event',
                        trigger_config: { event_name: triggerValue },
                        is_active: true
                    }),
                    credentials: 'include'
                });
            } else if (triggerValue) {
                await fetch(`/api/journeys/${journeyId}/triggers`, {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({
                        trigger_type: 'telegram_deeplink',
                        trigger_config: { start_param: triggerValue },
                        is_active: true
                    }),
                    credentials: 'include'
                });
            }

            if (state.steps.length > 0) {
                await fetch(`/api/journeys/${journeyId}/steps`, {
                    method: 'PUT',
                    headers,
                    body: JSON.stringify({ steps: state.steps }),
                    credentials: 'include'
                });
            }

            if (config.hideLoading) config.hideLoading();
            config.showToast('Journey saved successfully', 'success');

            invalidateJourneysCache();
            await loadJourneys(true);

            const statusDisplay = document.getElementById('editor-status-display');
            if (statusDisplay) statusDisplay.textContent = status.charAt(0).toUpperCase() + status.slice(1);

        } catch (err) {
            if (config.hideLoading) config.hideLoading();
            console.error('Save journey settings error:', err);
            config.showToast(err.message || 'Failed to save journey', 'error');
        }
    }

    async function saveJourney() {
        return saveJourneySettings();
    }

    async function fetchJourneyDetail(journeyId) {
        let headers;
        try {
            headers = await config.getAuthHeaders();
        } catch (err) {
            console.warn('Auth headers issue, continuing with cookies:', err);
            headers = { 'Content-Type': 'application/json' };
        }

        try {
            const resp = await fetch(`/api/journeys/${journeyId}`, { headers, credentials: 'include' });
            if (resp.ok) {
                const data = await resp.json();
                const journey = data.journey;

                const nameInput = document.getElementById('journey-name-input');
                if (nameInput) nameInput.value = journey.name || '';

                const delaySeconds = journey.start_delay_seconds || 0;
                const startDelayValueInput = document.getElementById('journey-start-delay-value');
                const startDelayUnitSelect = document.getElementById('journey-start-delay-unit');
                if (startDelayValueInput && startDelayUnitSelect) {
                    if (delaySeconds > 0 && delaySeconds % 3600 === 0) {
                        startDelayValueInput.value = delaySeconds / 3600;
                        startDelayUnitSelect.value = 'hours';
                    } else if (delaySeconds > 0 && delaySeconds % 60 === 0) {
                        startDelayValueInput.value = delaySeconds / 60;
                        startDelayUnitSelect.value = 'minutes';
                    } else {
                        startDelayValueInput.value = delaySeconds;
                        startDelayUnitSelect.value = 'seconds';
                    }
                }
                selectStatus(journey.status || 'draft');

                const triggers = journey.triggers || [];
                if (triggers.length > 0) {
                    const trigger = triggers[0];
                    const triggerTypeEl = document.getElementById('journey-trigger-type');
                    const triggerValueEl = document.getElementById('journey-trigger-value');
                    const tt = trigger.trigger_type === 'direct_message' ? 'direct_message' : (trigger.trigger_type === 'api_event' ? 'api_event' : 'deep_link');
                    if (triggerTypeEl) triggerTypeEl.value = tt;
                    onTriggerTypeChange();
                    if (tt === 'direct_message') {
                        if (triggerValueEl) triggerValueEl.value = trigger.trigger_config?.keyword || '';
                    } else if (tt === 'api_event') {
                        const eventSel = document.getElementById('journey-trigger-event-select');
                        if (eventSel) eventSel.value = trigger.trigger_config?.event_name || '';
                    } else {
                        if (triggerValueEl) triggerValueEl.value = trigger.trigger_config?.start_param || trigger.trigger_config?.value || '';
                    }
                }

                state.steps = (journey.steps || []).map(s => {
                    const waitForReply = s.wait_for_reply || s.config?.wait_for_reply || false;
                    const rawDelay = s.delay_seconds || s.config?.delay_seconds || 0;
                    const rawTimeoutSeconds = s.timeout_seconds || s.config?.timeout_seconds || 0;
                    const rawTimeoutMinutes = s.config?.timeout_minutes || 0;

                    let delaySecondsVal = rawDelay;
                    let timeoutSeconds = rawTimeoutSeconds || (rawTimeoutMinutes * 60);

                    if (waitForReply && timeoutSeconds === 0 && rawDelay > 0) {
                        timeoutSeconds = rawDelay;
                        delaySecondsVal = 0;
                    }

                    return {
                        id: s.id || null,
                        step_type: s.step_type || 'message',
                        message_template: s.message_template || s.config?.text || '',
                        delay_seconds: delaySecondsVal,
                        wait_for_reply: waitForReply,
                        timeout_action: s.timeout_action || s.config?.timeout_action || 'continue',
                        timeout_seconds: timeoutSeconds
                    };
                });

                try {
                    const analyticsResp = await fetch(`/api/journeys/${journeyId}/analytics`, { headers, credentials: 'include' });
                    if (analyticsResp.ok) {
                        const analyticsData = await analyticsResp.json();
                        state.stepAnalytics = {};
                        (analyticsData.analytics || []).forEach(a => {
                            state.stepAnalytics[a.step_id] = a;
                        });
                    }
                } catch (err) {
                    console.warn('Failed to load step analytics:', err);
                }

                renderStepsList();

                const stepsCount = document.getElementById('editor-steps-count');
                if (stepsCount) stepsCount.textContent = state.steps.length;

            } else {
                console.error('Failed to fetch journey, status:', resp.status);
                config.showToast('Failed to load journey details', 'error');
            }
        } catch (err) {
            console.error('Failed to fetch journey detail:', err);
            config.showToast('Failed to load journey details', 'error');
        }
    }

    function selectStatus(status) {
        state.selectedStatus = status;
        document.querySelectorAll('.status-option').forEach(opt => {
            const isSelected = opt.dataset.status === status;
            opt.classList.toggle('selected', isSelected);
            opt.style.background = isSelected ? 'var(--accent-color)' : 'var(--card-bg)';
            opt.style.color = isSelected ? '#fff' : 'var(--text-secondary)';
        });
        const warning = document.getElementById('active-warning');
        if (warning) {
            warning.style.display = status === 'active' ? 'flex' : 'none';
        }
    }

    async function deleteJourney(journeyId) {
        const confirmFn = config.confirmDialog || window.confirm;
        const confirmed = await confirmFn('Are you sure you want to delete this journey? This action cannot be undone.');
        if (!confirmed) return;

        let headers;
        try {
            headers = await config.getAuthHeaders();
        } catch (err) {
            console.warn('Auth headers issue, continuing with cookies:', err);
            headers = { 'Content-Type': 'application/json' };
        }

        try {
            if (config.showLoading) config.showLoading('Deleting journey...');
            const resp = await fetch(`/api/journeys/${journeyId}`, {
                method: 'DELETE',
                headers,
                credentials: 'include'
            });

            if (config.hideLoading) config.hideLoading();

            if (resp.ok) {
                config.showToast('Journey deleted successfully', 'success');
                invalidateJourneysCache();
                await loadJourneys(true);
            } else {
                let errorMsg = 'Failed to delete journey';
                try {
                    const data = await resp.json();
                    errorMsg = data.error || errorMsg;
                } catch (e) {}
                config.showToast(errorMsg, 'error');
            }
        } catch (err) {
            if (config.hideLoading) config.hideLoading();
            console.error('Delete journey error:', err);
            config.showToast('Failed to delete journey', 'error');
        }
    }

    function formatTimeValue(seconds) {
        if (!seconds || seconds <= 0) return null;
        if (seconds >= 86400 && seconds % 86400 === 0) return `${seconds / 86400}d`;
        if (seconds >= 3600 && seconds % 3600 === 0) return `${seconds / 3600}h`;
        if (seconds >= 60 && seconds % 60 === 0) return `${seconds / 60}m`;
        return `${seconds}s`;
    }

    function getStepTypeLabel(step) {
        const delaySecs = step.delay_seconds || 0;
        const timeoutSecs = step.timeout_seconds || 0;
        if (step.wait_for_reply) {
            const timeoutStr = timeoutSecs > 0 ? formatTimeValue(timeoutSecs) : '∞';
            const delayStr = delaySecs > 0 ? `${formatTimeValue(delaySecs)} delay → ` : '';
            return `${delayStr}Wait for reply (${timeoutStr})`;
        } else if (delaySecs > 0) {
            return `Delay: ${formatTimeValue(delaySecs)}`;
        }
        return 'Send immediately';
    }

    function renderStepsList() {
        const container = document.getElementById('steps-list');
        const emptyState = document.getElementById('steps-empty');

        if (!container) return;

        if (state.steps.length === 0) {
            if (emptyState) emptyState.style.display = 'block';
            const existingItems = container.querySelectorAll('.step-item');
            existingItems.forEach(el => el.remove());
            return;
        }

        if (emptyState) emptyState.style.display = 'none';
        const escapeHtml = config.escapeHtml || escapeHtmlDefault;

        container.innerHTML = state.steps.map((step, index) => {
            const analytics = step.id ? state.stepAnalytics[step.id] : null;
            const analyticsHtml = analytics && (analytics.sends > 0 || analytics.unique_users > 0)
                ? `<div class="step-analytics">
                    <span title="Messages sent">\u{1F4E4} ${analytics.sends}</span>
                    <span title="Unique users">\u{1F464} ${analytics.unique_users}</span>
                </div>`
                : '';
            return `
            <div class="step-item">
                <div class="step-order">${index + 1}</div>
                <div class="step-content">
                    <div class="step-message">${escapeHtml((step.message_template || '').substring(0, 80))}${(step.message_template || '').length > 80 ? '...' : ''}</div>
                    <div class="step-delay">${step.wait_for_reply ? '⏳ ' : ''}${getStepTypeLabel(step)}</div>
                    ${analyticsHtml}
                </div>
                <div class="step-actions">
                    <button class="step-btn" onclick="window.JourneysModule.moveStep(${index}, -1)" ${index === 0 ? 'disabled' : ''} title="Move up">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18,15 12,9 6,15"/></svg>
                    </button>
                    <button class="step-btn" onclick="window.JourneysModule.moveStep(${index}, 1)" ${index === state.steps.length - 1 ? 'disabled' : ''} title="Move down">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6,9 12,15 18,9"/></svg>
                    </button>
                    <button class="step-btn" onclick="window.JourneysModule.editStep(${index})" title="Edit">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    </button>
                    <button class="step-btn danger" onclick="window.JourneysModule.deleteStep(${index})" title="Delete">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3,6 5,6 21,6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>
                </div>
            </div>
        `}).join('');

        const stepsCount = document.getElementById('editor-steps-count');
        if (stepsCount) stepsCount.textContent = state.steps.length;
    }

    function updateStepModalVisibility() {
        const waitCheckbox = document.getElementById('step-wait-for-reply');
        const timeoutGroup = document.getElementById('step-timeout-group');
        if (timeoutGroup) {
            timeoutGroup.style.display = waitCheckbox && waitCheckbox.checked ? 'block' : 'none';
        }
    }

    function addStep() {
        state.editingStepIndex = null;
        const msgInput = document.getElementById('step-message-input');
        const delayInput = document.getElementById('step-delay-input');
        const delayUnit = document.getElementById('step-delay-unit');
        const waitCheckbox = document.getElementById('step-wait-for-reply');
        const timeoutValue = document.getElementById('step-timeout-value');
        const timeoutUnit = document.getElementById('step-timeout-unit');
        const timeoutSelect = document.getElementById('step-timeout-action');
        const modalTitle = document.getElementById('step-modal-title');
        if (msgInput) msgInput.value = '';
        if (delayInput) delayInput.value = '0';
        if (delayUnit) delayUnit.value = 'seconds';
        if (waitCheckbox) waitCheckbox.checked = false;
        if (timeoutValue) timeoutValue.value = '0';
        if (timeoutUnit) timeoutUnit.value = 'minutes';
        if (timeoutSelect) timeoutSelect.value = 'continue';
        if (modalTitle) modalTitle.textContent = 'Add Step';
        updateStepModalVisibility();
        const backdrop = document.getElementById('step-modal-backdrop');
        if (backdrop) backdrop.classList.add('show');
    }

    function editStep(index) {
        state.editingStepIndex = index;
        const step = state.steps[index];
        const msgInput = document.getElementById('step-message-input');
        const delayInput = document.getElementById('step-delay-input');
        const delayUnit = document.getElementById('step-delay-unit');
        const waitCheckbox = document.getElementById('step-wait-for-reply');
        const timeoutValue = document.getElementById('step-timeout-value');
        const timeoutUnit = document.getElementById('step-timeout-unit');
        const timeoutSelect = document.getElementById('step-timeout-action');
        const modalTitle = document.getElementById('step-modal-title');
        if (msgInput) msgInput.value = step.message_template || '';
        const delayParsed = secondsToTimeUnit(step.delay_seconds || 0);
        if (delayInput) delayInput.value = delayParsed.value;
        if (delayUnit) delayUnit.value = delayParsed.unit;
        if (waitCheckbox) waitCheckbox.checked = step.wait_for_reply || false;
        const timeoutParsed = secondsToTimeUnit(step.timeout_seconds || 0);
        if (timeoutValue) timeoutValue.value = timeoutParsed.value;
        if (timeoutUnit) timeoutUnit.value = timeoutParsed.unit;
        if (timeoutSelect) timeoutSelect.value = step.timeout_action || 'continue';
        if (modalTitle) modalTitle.textContent = 'Edit Step';
        updateStepModalVisibility();
        const backdrop = document.getElementById('step-modal-backdrop');
        if (backdrop) backdrop.classList.add('show');
    }

    function closeStepModal() {
        const backdrop = document.getElementById('step-modal-backdrop');
        if (backdrop) backdrop.classList.remove('show');
        state.editingStepIndex = null;
    }

    function saveStep() {
        const msgInput = document.getElementById('step-message-input');
        const delayInput = document.getElementById('step-delay-input');
        const delayUnit = document.getElementById('step-delay-unit');
        const waitCheckbox = document.getElementById('step-wait-for-reply');
        const timeoutValueInput = document.getElementById('step-timeout-value');
        const timeoutUnit = document.getElementById('step-timeout-unit');
        const timeoutSelect = document.getElementById('step-timeout-action');
        const message = msgInput ? msgInput.value.trim() : '';
        const delaySeconds = timeToSeconds(delayInput ? delayInput.value : 0, delayUnit ? delayUnit.value : 'seconds');
        const waitForReply = waitCheckbox ? waitCheckbox.checked : false;
        const timeoutSeconds = timeToSeconds(timeoutValueInput ? timeoutValueInput.value : 0, timeoutUnit ? timeoutUnit.value : 'minutes');
        const timeoutAction = timeoutSelect ? timeoutSelect.value : 'continue';

        if (!message) {
            config.showToast('Please enter a message', 'error');
            return;
        }

        const stepData = {
            message_template: message,
            delay_seconds: delaySeconds,
            wait_for_reply: waitForReply,
            timeout_seconds: timeoutSeconds,
            timeout_action: timeoutAction
        };

        if (state.editingStepIndex !== null) {
            state.steps[state.editingStepIndex] = stepData;
        } else {
            state.steps.push(stepData);
        }

        closeStepModal();
        renderStepsList();

        if (state.currentJourneyId) {
            _saveStepsToServer(state.currentJourneyId);
        }
    }

    async function _saveStepsToServer(journeyId) {
        try {
            const headers = await config.getAuthHeaders(true);
            await fetch(`/api/journeys/${journeyId}/steps`, {
                method: 'PUT',
                headers,
                body: JSON.stringify({ steps: state.steps }),
                credentials: 'include'
            });
            invalidateJourneysCache();
        } catch (err) {
            console.warn('Failed to auto-save steps:', err);
        }
    }

    function deleteStep(index) {
        const confirmFn = config.confirmDialog || window.confirm;
        if (!confirmFn('Delete this step?')) return;
        state.steps.splice(index, 1);
        renderStepsList();
        if (state.currentJourneyId) {
            _saveStepsToServer(state.currentJourneyId);
        }
    }

    function moveStep(index, direction) {
        const newIndex = index + direction;
        if (newIndex < 0 || newIndex >= state.steps.length) return;

        const temp = state.steps[index];
        state.steps[index] = state.steps[newIndex];
        state.steps[newIndex] = temp;
        renderStepsList();
        if (state.currentJourneyId) {
            _saveStepsToServer(state.currentJourneyId);
        }
    }

    async function copyDeepLink(url) {
        try {
            await navigator.clipboard.writeText(url);
            config.showToast('Deep link copied to clipboard!', 'success');
        } catch (err) {
            console.error('Failed to copy:', err);
            const input = document.createElement('input');
            input.value = url;
            document.body.appendChild(input);
            input.select();
            document.execCommand('copy');
            document.body.removeChild(input);
            config.showToast('Deep link copied to clipboard!', 'success');
        }
    }

    function getTriggerValue() {
        const triggerTypeEl = document.getElementById('journey-trigger-type');
        const selectedType = triggerTypeEl ? triggerTypeEl.value : 'deep_link';
        if (selectedType === 'api_event') {
            const sel = document.getElementById('journey-trigger-event-select');
            return sel ? sel.value : '';
        }
        const input = document.getElementById('journey-trigger-value');
        return input ? input.value : '';
    }

    function setTriggerValue(val) {
        const triggerTypeEl = document.getElementById('journey-trigger-type');
        const selectedType = triggerTypeEl ? triggerTypeEl.value : 'deep_link';
        if (selectedType === 'api_event') {
            const sel = document.getElementById('journey-trigger-event-select');
            if (sel) sel.value = val || '';
        } else {
            const input = document.getElementById('journey-trigger-value');
            if (input) input.value = val || '';
        }
    }

    function ensureApiEventSelect() {
        const container = document.getElementById('trigger-value-container');
        if (!container) return;
        if (!document.getElementById('journey-trigger-event-select')) {
            const sel = document.createElement('select');
            sel.className = 'form-select';
            sel.id = 'journey-trigger-event-select';
            sel.style.cssText = 'width:100%;font-size:13px;';
            sel.innerHTML = '<option value="">Select an event...</option>' +
                '<option value="joined_vip">joined_vip — User is granted VIP access</option>' +
                '<option value="stripe_payment_successful">stripe_payment_successful — Stripe payment completed</option>' +
                '<option value="stripe_sub_cancelled">stripe_sub_cancelled — Subscription cancelled</option>' +
                '<option value="email_only_captured">email_only_captured — Lead captured email but didn\'t join Telegram (24h)</option>' +
                '<option value="joined_free_channel">joined_free_channel — User joined FREE channel</option>';
            container.appendChild(sel);
        }
    }

    function onTriggerTypeChange() {
        const triggerTypeEl = document.getElementById('journey-trigger-type');
        const triggerValueEl = document.getElementById('journey-trigger-value');
        const triggerValueLabel = document.getElementById('trigger-value-label');
        const triggerValueHint = document.getElementById('trigger-value-hint');
        const triggerTypeHint = document.getElementById('trigger-type-hint');
        const preview = document.getElementById('deeplink-preview');

        const selectedType = triggerTypeEl ? triggerTypeEl.value : 'deep_link';
        const isDM = selectedType === 'direct_message';
        const isApiEvent = selectedType === 'api_event';

        ensureApiEventSelect();
        const eventSelect = document.getElementById('journey-trigger-event-select');

        if (isApiEvent) {
            if (triggerValueLabel) triggerValueLabel.textContent = 'API Event';
            if (triggerValueEl) triggerValueEl.style.display = 'none';
            if (eventSelect) eventSelect.style.display = '';
            if (triggerValueHint) triggerValueHint.innerHTML = 'This journey will trigger automatically when the selected API event fires.';
            if (triggerTypeHint) triggerTypeHint.textContent = 'Journeys are triggered by API events like payments, signups, and channel joins.';
        } else if (isDM) {
            if (triggerValueEl) { triggerValueEl.style.display = ''; triggerValueEl.placeholder = 'e.g., hello (leave empty for any message)'; }
            if (eventSelect) eventSelect.style.display = 'none';
            if (triggerValueLabel) triggerValueLabel.textContent = 'Keyword (optional)';
            if (triggerValueHint) triggerValueHint.innerHTML = 'If set, the journey triggers when a DM contains this keyword. Leave empty to trigger on any message.';
            if (triggerTypeHint) triggerTypeHint.textContent = 'Journeys are triggered when someone sends a direct message to your Telegram user account.';
        } else {
            if (triggerValueEl) { triggerValueEl.style.display = ''; triggerValueEl.placeholder = 'e.g., welcome_promo'; }
            if (eventSelect) eventSelect.style.display = 'none';
            if (triggerValueLabel) triggerValueLabel.textContent = 'Trigger Value';
            if (triggerValueHint) triggerValueHint.innerHTML = 'The start parameter value (e.g., t.me/bot?start=<strong>welcome_promo</strong>)';
            if (triggerTypeHint) triggerTypeHint.textContent = 'Journeys are triggered when users start the bot via a deep link.';
        }

        const warningText = document.getElementById('active-warning-text');
        if (warningText) {
            if (isApiEvent) {
                warningText.textContent = 'Active journeys will start sending messages immediately when the API event fires.';
            } else if (isDM) {
                warningText.textContent = 'Active journeys will start sending messages immediately when someone DMs your Telegram account with the keyword.';
            } else {
                warningText.textContent = 'Active journeys will start sending messages to users immediately when they join via the deep link.';
            }
        }

        if ((isDM || isApiEvent) && preview) {
            preview.style.display = 'none';
        } else {
            updateDeepLinkPreview();
        }

    }

    function updateDeepLinkPreview() {
        const triggerTypeEl = document.getElementById('journey-trigger-type');
        if (triggerTypeEl && triggerTypeEl.value === 'direct_message') return;

        const triggerInput = document.getElementById('journey-trigger-value');
        const preview = document.getElementById('deeplink-preview');
        const urlCode = document.getElementById('deeplink-preview-url');
        const testLink = document.getElementById('deeplink-preview-test');
        const warning = document.getElementById('deeplink-preview-warning');

        if (!preview || !triggerInput) return;

        const triggerValue = triggerInput.value.trim();

        if (!triggerValue) {
            preview.style.display = 'none';
            return;
        }

        preview.style.display = 'block';

        if (!state.messageBotUsername) {
            if (urlCode) urlCode.textContent = '';
            if (testLink) testLink.style.display = 'none';
            if (warning) warning.style.display = 'block';
            const urlWrapper = preview.querySelector('.deeplink-preview-url');
            if (urlWrapper) urlWrapper.style.display = 'none';
            return;
        }

        const url = getDeepLinkUrl(triggerValue);
        if (urlCode) urlCode.textContent = url;
        if (testLink) {
            testLink.href = url;
            testLink.style.display = 'flex';
        }
        if (warning) warning.style.display = 'none';
        const urlWrapper = preview.querySelector('.deeplink-preview-url');
        if (urlWrapper) urlWrapper.style.display = 'flex';
    }

    function updateDmLinkPreview() {
        const msgInput = document.getElementById('dm-prefill-message');
        const preview = document.getElementById('dm-link-preview');
        const urlCode = document.getElementById('dm-link-preview-url');
        const testLink = document.getElementById('dm-link-preview-test');
        const warning = document.getElementById('dm-link-preview-warning');

        if (!preview || !msgInput) return;

        const message = msgInput.value.trim();

        if (!message) {
            preview.style.display = 'none';
            return;
        }

        preview.style.display = 'block';

        if (!state.telethonUsername) {
            if (urlCode) urlCode.textContent = '';
            if (testLink) testLink.style.display = 'none';
            if (warning) warning.style.display = 'block';
            const urlContainer = preview.querySelector('.deeplink-preview-url');
            if (urlContainer) urlContainer.style.display = 'none';
            return;
        }

        if (warning) warning.style.display = 'none';
        const urlContainer = preview.querySelector('.deeplink-preview-url');
        if (urlContainer) urlContainer.style.display = 'flex';

        const dmUrl = `https://t.me/${state.telethonUsername}?text=${encodeURIComponent(message)}`;
        if (urlCode) urlCode.textContent = dmUrl;
        if (testLink) {
            testLink.href = dmUrl;
            testLink.style.display = 'inline-flex';
        }
    }

    async function copyDmLink() {
        const urlCode = document.getElementById('dm-link-preview-url');
        if (!urlCode) return;
        try {
            await navigator.clipboard.writeText(urlCode.textContent);
            config.showToast('DM link copied to clipboard!', 'success');
        } catch (err) {
            const input = document.createElement('input');
            input.value = urlCode.textContent;
            document.body.appendChild(input);
            input.select();
            document.execCommand('copy');
            document.body.removeChild(input);
            config.showToast('DM link copied!', 'success');
        }
    }

    async function copyDeepLinkFromPreview() {
        const urlCode = document.getElementById('deeplink-preview-url');
        if (urlCode && urlCode.textContent) {
            await copyDeepLink(urlCode.textContent);
        }
    }

    async function publishJourney(journeyId) {
        const confirmFn = config.confirmDialog || window.confirm;
        const confirmed = await confirmFn('Publish this journey? It will start triggering for new users.');
        if (!confirmed) return;

        try {
            if (config.showLoading) config.showLoading('Publishing journey...');
            const headers = await config.getAuthHeaders();
            const resp = await fetch(`/api/journeys/${journeyId}/publish`, {
                method: 'POST',
                headers,
                credentials: 'include'
            });
            const data = await resp.json();
            if (config.hideLoading) config.hideLoading();

            if (resp.ok) {
                config.showToast('Journey published successfully!', 'success');
                invalidateJourneysCache();
                await loadJourneys(true);

                const publishBtn = document.getElementById('journey-publish-btn');
                if (publishBtn) {
                    publishBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="14" height="14"><rect x="6" y="6" width="12" height="12" rx="1"/></svg> Stop`;
                    publishBtn.style.background = 'rgba(245,158,11,.15)';
                    publishBtn.style.color = '#f59e0b';
                    publishBtn.style.border = '1px solid rgba(245,158,11,.3)';
                    publishBtn.onclick = () => window.JourneysModule.stopJourney(journeyId);
                }

                const statusDisplay = document.getElementById('editor-status-display');
                if (statusDisplay) statusDisplay.textContent = 'Active';
                selectStatus('active');

            } else if (resp.status === 409) {
                config.showToast(data.error || 'Trigger keyword conflict', 'error');
            } else {
                config.showToast(data.error || 'Failed to publish journey', 'error');
            }
        } catch (err) {
            if (config.hideLoading) config.hideLoading();
            console.error('Publish journey error:', err);
            config.showToast('Failed to publish journey', 'error');
        }
    }

    async function stopJourney(journeyId) {
        const confirmFn = config.confirmDialog || window.confirm;
        const confirmed = await confirmFn('Stop this journey? New users will no longer trigger it, but users already in the flow will finish.');
        if (!confirmed) return;

        try {
            if (config.showLoading) config.showLoading('Stopping journey...');
            const headers = await config.getAuthHeaders();
            const resp = await fetch(`/api/journeys/${journeyId}/stop`, {
                method: 'POST',
                headers,
                credentials: 'include'
            });
            const data = await resp.json();
            if (config.hideLoading) config.hideLoading();

            if (resp.ok) {
                config.showToast('Journey stopped. In-progress users will complete their flow.', 'success');
                invalidateJourneysCache();
                await loadJourneys(true);

                const publishBtn = document.getElementById('journey-publish-btn');
                if (publishBtn) {
                    publishBtn.outerHTML = `<span style="padding:8px 14px;font-size:13px;color:var(--text-secondary);border:1px solid var(--border-color);border-radius:8px;">Stopped — Duplicate to restart</span>`;
                }

                const statusDisplay = document.getElementById('editor-status-display');
                if (statusDisplay) statusDisplay.textContent = 'Stopped';
                selectStatus('stopped');

            } else {
                config.showToast(data.error || 'Failed to stop journey', 'error');
            }
        } catch (err) {
            if (config.hideLoading) config.hideLoading();
            console.error('Stop journey error:', err);
            config.showToast('Failed to stop journey', 'error');
        }
    }

    async function duplicateJourney(journeyId) {
        try {
            if (config.showLoading) config.showLoading('Duplicating journey...');
            const headers = await config.getAuthHeaders();
            const resp = await fetch(`/api/journeys/${journeyId}/duplicate`, {
                method: 'POST',
                headers,
                credentials: 'include'
            });
            const data = await resp.json();
            if (config.hideLoading) config.hideLoading();

            if (resp.ok) {
                config.showToast('Journey duplicated as draft', 'success');

                const journey = state.journeys.find(j => j.id === journeyId);
                if (journey && journey.status === 'active') {
                    const confirmFn = config.confirmDialog || window.confirm;
                    const shouldStop = await confirmFn('The original journey is still active. Would you like to stop it from accepting new users? Users already in the flow will finish.');
                    if (shouldStop) {
                        await fetch(`/api/journeys/${journeyId}/stop`, {
                            method: 'POST',
                            headers,
                            credentials: 'include'
                        });
                        config.showToast('Original journey stopped', 'success');
                    }
                }

                invalidateJourneysCache();
                await loadJourneys(true);
            } else {
                config.showToast(data.error || 'Failed to duplicate journey', 'error');
            }
        } catch (err) {
            if (config.hideLoading) config.hideLoading();
            console.error('Duplicate journey error:', err);
            config.showToast('Failed to duplicate journey', 'error');
        }
    }

    function initJourneys(options) {
        config.getAuthHeaders = options.getAuthHeaders;
        config.showToast = options.showToast || function(msg) { console.log(msg); };
        config.showLoading = options.showLoading;
        config.hideLoading = options.hideLoading;
        config.escapeHtml = options.escapeHtml;
        config.confirmDialog = options.confirmDialog;

        window.JourneysModule = {
            loadJourneys,
            renderJourneys,
            renderListView,
            openJourneyEditor,
            openJourneyModal,
            closeJourneyEditor,
            closeJourneyModal,
            saveJourneySettings,
            saveJourney,
            deleteJourney,
            publishJourney,
            stopJourney,
            duplicateJourney,
            selectStatus,
            addStep,
            editStep,
            closeStepModal,
            saveStep,
            deleteStep,
            moveStep,
            copyDeepLink,
            copyDeepLinkFromPreview,
            updateDeepLinkPreview,
            onTriggerTypeChange,
            updateDmLinkPreview,
            copyDmLink,
            updateStepModalVisibility,
            _onJourneySearch,
            _onJourneyStatusFilter,
            getDeepLinkUrl: () => state.messageBotUsername
        };

        return window.JourneysModule;
    }

    window.initJourneys = initJourneys;
})();
