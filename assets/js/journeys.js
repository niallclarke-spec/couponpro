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
        lastLoadTime: null
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
    }

    function getDeepLinkUrl(startParam) {
        if (!state.messageBotUsername || !startParam) return null;
        const username = state.messageBotUsername.replace(/^@/, '');
        return `https://t.me/${username}?start=${encodeURIComponent(startParam)}`;
    }

    async function loadJourneys(forceRefresh = false) {
        // Use cached data if already loaded and not forcing refresh
        // Cache expires after 60 seconds
        const cacheExpiry = 60 * 1000;
        const now = Date.now();
        if (!forceRefresh && state.journeysLoaded && state.lastLoadTime && (now - state.lastLoadTime < cacheExpiry)) {
            renderJourneys();
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
                renderJourneys();
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

    function renderJourneys() {
        const container = document.getElementById('journeys-grid');
        const emptyState = document.getElementById('journeys-empty-state');
        const createBtn = document.getElementById('create-journey-btn');
        const limitBadge = document.getElementById('journeys-limit-badge');
        
        if (!container || !emptyState) return;
        
        const count = state.journeys.length;
        if (limitBadge) limitBadge.textContent = `${count} / ${MAX_JOURNEYS}`;
        
        if (createBtn) {
            if (count >= MAX_JOURNEYS) {
                createBtn.disabled = true;
                createBtn.title = 'Maximum journeys reached';
            } else {
                createBtn.disabled = false;
                createBtn.title = '';
            }
        }

        if (count === 0) {
            emptyState.style.display = 'block';
            container.style.display = 'none';
            return;
        }

        emptyState.style.display = 'none';
        container.style.display = 'grid';

        const escapeHtml = config.escapeHtml || escapeHtmlDefault;
        
        container.innerHTML = state.journeys.map(journey => {
            const triggers = journey.triggers || [];
            const firstTrigger = triggers[0];
            const triggerType = firstTrigger?.trigger_type || 'deep_link';
            const triggerValue = triggerType === 'direct_message' 
                ? (firstTrigger?.trigger_config?.keyword || '') 
                : (firstTrigger?.trigger_config?.start_param || firstTrigger?.trigger_config?.value || '');
            const deepLinkUrl = getDeepLinkUrl(triggerValue);
            
            let deepLinkHtml = '';
            if (triggerType === 'direct_message') {
                const kwDisplay = triggerValue ? escapeHtml(triggerValue) : '<em>any message</em>';
                deepLinkHtml = `
                    <div class="journey-deeplink" style="font-size:12px;color:var(--text-secondary);">
                        DM Trigger keyword: <strong>${kwDisplay}</strong>
                    </div>`;
            } else if (triggerValue && (triggerType === 'telegram_deeplink' || triggerType === 'deep_link')) {
                if (deepLinkUrl) {
                    deepLinkHtml = `
                        <div class="journey-deeplink">
                            <code class="deeplink-url">${escapeHtml(deepLinkUrl)}</code>
                            <button class="btn-copy" onclick="window.JourneysModule.copyDeepLink('${escapeHtml(deepLinkUrl)}')" title="Copy link">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                                </svg>
                            </button>
                            <a href="${escapeHtml(deepLinkUrl)}" target="_blank" class="btn-test" title="Test link">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                                    <polyline points="15 3 21 3 21 9"/>
                                    <line x1="10" y1="14" x2="21" y2="3"/>
                                </svg>
                            </a>
                        </div>`;
                } else {
                    deepLinkHtml = `
                        <div class="journey-deeplink-warning">
                            Configure Message Bot in Connections to get deep link URL
                        </div>`;
                }
            }
            
            return `
                <div class="journey-card">
                    <div class="journey-card-header">
                        <div class="journey-name">${escapeHtml(journey.name)}</div>
                        <span class="journey-status ${journey.status}">${journey.status}</span>
                    </div>
                    <div class="journey-meta">
                        <div class="journey-meta-item">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                                <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                            </svg>
                            <span>${triggerType === 'direct_message' ? 'DM' : 'Trigger'}: <strong>${escapeHtml(triggerValue || (triggerType === 'direct_message' ? 'any' : '-'))}</strong></span>
                        </div>
                        <div class="journey-meta-item">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                <polyline points="14,2 14,8 20,8"/>
                                <line x1="16" y1="13" x2="8" y2="13"/>
                                <line x1="16" y1="17" x2="8" y2="17"/>
                            </svg>
                            <span>${journey.step_count || 0} step${journey.step_count !== 1 ? 's' : ''}</span>
                        </div>
                    </div>
                    ${deepLinkHtml}
                    <div class="journey-actions">
                        <button class="btn-icon" onclick="window.JourneysModule.openJourneyModal('${journey.id}')" title="Edit">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                            </svg>
                        </button>
                        <button class="btn-icon danger" onclick="window.JourneysModule.deleteJourney('${journey.id}')" title="Delete">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3,6 5,6 21,6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                            </svg>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }

    async function openJourneyModal(journeyId = null) {
        state.currentJourneyId = journeyId;
        state.steps = [];
        state.stepAnalytics = {};
        state.selectedStatus = 'draft';
        
        await loadMessageBotUsername();
        
        const nameInput = document.getElementById('journey-name-input');
        const triggerValue = document.getElementById('journey-trigger-value');
        const triggerType = document.getElementById('journey-trigger-type');
        const modalTitle = document.getElementById('journey-modal-title');
        const preview = document.getElementById('deeplink-preview');
        
        if (nameInput) nameInput.value = '';
        if (triggerValue) triggerValue.value = '';
        if (triggerType) triggerType.value = 'deep_link';
        const dmPrefill = document.getElementById('dm-prefill-message');
        if (dmPrefill) dmPrefill.value = '';
        const welcomeMsg = document.getElementById('journey-welcome-message');
        if (welcomeMsg) welcomeMsg.value = '';
        if (modalTitle) modalTitle.textContent = journeyId ? 'Edit Journey' : 'Create Journey';
        if (preview) preview.style.display = 'none';
        onTriggerTypeChange();
        
        selectStatus('draft');
        renderStepsList();
        
        if (journeyId) {
            await fetchJourneyDetail(journeyId);
            updateDeepLinkPreview();
        }
        
        const backdrop = document.getElementById('journey-modal-backdrop');
        if (backdrop) backdrop.classList.add('show');
    }

    function closeJourneyModal() {
        const backdrop = document.getElementById('journey-modal-backdrop');
        if (backdrop) backdrop.classList.remove('show');
        state.currentJourneyId = null;
        state.steps = [];
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
                const welcomeMsgInput = document.getElementById('journey-welcome-message');
                if (welcomeMsgInput) welcomeMsgInput.value = journey.welcome_message || '';
                selectStatus(journey.status || 'draft');
                
                const triggers = journey.triggers || [];
                if (triggers.length > 0) {
                    const trigger = triggers[0];
                    const triggerTypeEl = document.getElementById('journey-trigger-type');
                    const triggerValueEl = document.getElementById('journey-trigger-value');
                    const tt = trigger.trigger_type === 'direct_message' ? 'direct_message' : 'deep_link';
                    if (triggerTypeEl) triggerTypeEl.value = tt;
                    if (tt === 'direct_message') {
                        if (triggerValueEl) triggerValueEl.value = trigger.trigger_config?.keyword || '';
                        const dmPrefill = document.getElementById('dm-prefill-message');
                        if (dmPrefill) dmPrefill.value = trigger.trigger_config?.prefill_message || '';
                    } else {
                        if (triggerValueEl) triggerValueEl.value = trigger.trigger_config?.start_param || trigger.trigger_config?.value || '';
                    }
                    onTriggerTypeChange();
                }
                
                state.steps = (journey.steps || []).map(s => {
                    const waitForReply = s.wait_for_reply || s.config?.wait_for_reply || false;
                    const rawDelay = s.delay_seconds || s.config?.delay_seconds || 0;
                    const rawTimeoutSeconds = s.timeout_seconds || s.config?.timeout_seconds || 0;
                    const rawTimeoutMinutes = s.config?.timeout_minutes || 0;
                    
                    let delaySeconds = rawDelay;
                    let timeoutSeconds = rawTimeoutSeconds || (rawTimeoutMinutes * 60);
                    
                    if (waitForReply && timeoutSeconds === 0 && rawDelay > 0) {
                        timeoutSeconds = rawDelay;
                        delaySeconds = 0;
                    }
                    
                    return {
                        id: s.id || null,
                        step_type: s.step_type || 'message',
                        message_template: s.message_template || s.config?.text || '',
                        delay_seconds: delaySeconds,
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
            opt.classList.toggle('selected', opt.dataset.status === status);
        });
        const warning = document.getElementById('active-warning');
        if (warning) warning.classList.toggle('show', status === 'active');
    }

    async function saveJourney() {
        const nameInput = document.getElementById('journey-name-input');
        const triggerValueInput = document.getElementById('journey-trigger-value');
        const name = nameInput ? nameInput.value.trim() : '';
        const triggerValue = triggerValueInput ? triggerValueInput.value.trim() : '';
        const status = state.selectedStatus;
        
        if (!name) {
            config.showToast('Please enter a journey name', 'error');
            return;
        }
        
        try {
            if (config.showLoading) config.showLoading('Saving journey...');
            const headers = await config.getAuthHeaders(true);
            
            let journeyId = state.currentJourneyId;
            
            const welcomeMessage = (document.getElementById('journey-welcome-message') || {}).value?.trim() || '';
            
            if (journeyId) {
                const resp = await fetch(`/api/journeys/${journeyId}`, {
                    method: 'PUT',
                    headers,
                    body: JSON.stringify({ name, status, welcome_message: welcomeMessage }),
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
                    body: JSON.stringify({ name, status, bot_id: botId, welcome_message: welcomeMessage }),
                    credentials: 'include'
                });
                const data = await resp.json();
                if (!resp.ok) {
                    throw new Error(data.error || 'Failed to create journey');
                }
                journeyId = data.journey.id;
            }
            
            const triggerTypeSelect = document.getElementById('journey-trigger-type');
            const selectedTriggerType = triggerTypeSelect ? triggerTypeSelect.value : 'deep_link';
            
            if (selectedTriggerType === 'direct_message') {
                await fetch(`/api/journeys/${journeyId}/triggers`, {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({
                        trigger_type: 'direct_message',
                        trigger_config: { keyword: triggerValue, prefill_message: (document.getElementById('dm-prefill-message') || {}).value?.trim() || '' },
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
            config.showToast(state.currentJourneyId ? 'Journey updated successfully' : 'Journey created successfully', 'success');
            closeJourneyModal();
            invalidateJourneysCache();
            await loadJourneys(true);
            
        } catch (err) {
            if (config.hideLoading) config.hideLoading();
            console.error('Save journey error:', err);
            config.showToast(err.message || 'Failed to save journey', 'error');
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
            container.innerHTML = '';
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
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="18,15 12,9 6,15"/>
                        </svg>
                    </button>
                    <button class="step-btn" onclick="window.JourneysModule.moveStep(${index}, 1)" ${index === state.steps.length - 1 ? 'disabled' : ''} title="Move down">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6,9 12,15 18,9"/>
                        </svg>
                    </button>
                    <button class="step-btn" onclick="window.JourneysModule.editStep(${index})" title="Edit">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                        </svg>
                    </button>
                    <button class="step-btn danger" onclick="window.JourneysModule.deleteStep(${index})" title="Delete">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3,6 5,6 21,6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                </div>
            </div>
        `}).join('');
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
    }

    function deleteStep(index) {
        const confirmFn = config.confirmDialog || window.confirm;
        if (!confirmFn('Delete this step?')) return;
        state.steps.splice(index, 1);
        renderStepsList();
    }

    function moveStep(index, direction) {
        const newIndex = index + direction;
        if (newIndex < 0 || newIndex >= state.steps.length) return;
        
        const temp = state.steps[index];
        state.steps[index] = state.steps[newIndex];
        state.steps[newIndex] = temp;
        renderStepsList();
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

    function onTriggerTypeChange() {
        const triggerTypeEl = document.getElementById('journey-trigger-type');
        const triggerValueEl = document.getElementById('journey-trigger-value');
        const triggerValueLabel = document.getElementById('trigger-value-label');
        const triggerValueHint = document.getElementById('trigger-value-hint');
        const triggerTypeHint = document.getElementById('trigger-type-hint');
        const preview = document.getElementById('deeplink-preview');
        
        const isDM = triggerTypeEl && triggerTypeEl.value === 'direct_message';
        
        if (triggerValueLabel) triggerValueLabel.textContent = isDM ? 'Keyword (optional)' : 'Trigger Value';
        if (triggerValueEl) triggerValueEl.placeholder = isDM ? 'e.g., hello (leave empty for any message)' : 'e.g., welcome_promo';
        if (triggerValueHint) triggerValueHint.innerHTML = isDM 
            ? 'If set, the journey triggers when a DM contains this keyword. Leave empty to trigger on any message.'
            : 'The start parameter value (e.g., t.me/bot?start=<strong>welcome_promo</strong>)';
        if (triggerTypeHint) triggerTypeHint.textContent = isDM
            ? 'Journeys are triggered when someone sends a direct message to your Telegram user account.'
            : 'Journeys are triggered when users start the bot via a deep link.';
        
        const warningText = document.getElementById('active-warning-text');
        if (warningText) warningText.textContent = isDM
            ? 'Active journeys will start sending messages immediately when someone DMs your Telegram account with the keyword.'
            : 'Active journeys will start sending messages to users immediately when they join via the deep link.';
        
        if (isDM && preview) {
            preview.style.display = 'none';
        } else {
            updateDeepLinkPreview();
        }

        const dmMessageGroup = document.getElementById('dm-message-group');
        if (dmMessageGroup) {
            dmMessageGroup.style.display = isDM ? 'block' : 'none';
        }
        if (isDM) {
            updateDmLinkPreview();
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
            document.querySelector('.deeplink-preview-url').style.display = 'none';
            return;
        }
        
        const url = getDeepLinkUrl(triggerValue);
        if (urlCode) urlCode.textContent = url;
        if (testLink) {
            testLink.href = url;
            testLink.style.display = 'flex';
        }
        if (warning) warning.style.display = 'none';
        document.querySelector('.deeplink-preview-url').style.display = 'flex';
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
            openJourneyModal,
            closeJourneyModal,
            saveJourney,
            deleteJourney,
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
            getDeepLinkUrl: () => state.messageBotUsername
        };
        
        return window.JourneysModule;
    }

    window.initJourneys = initJourneys;
})();
