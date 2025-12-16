(function() {
    'use strict';

    const MAX_JOURNEYS = 6;
    
    const state = {
        journeys: [],
        currentJourneyId: null,
        steps: [],
        editingStepIndex: null,
        selectedStatus: 'draft',
        loading: false,
        messageBotUsername: null
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
                const messageBot = (data.connections || []).find(c => c.bot_role === 'message');
                state.messageBotUsername = messageBot?.bot_username || null;
            }
        } catch (err) {
            console.error('Failed to load message bot:', err);
        }
    }

    function getDeepLinkUrl(startParam) {
        if (!state.messageBotUsername || !startParam) return null;
        return `https://t.me/${state.messageBotUsername}?start=${encodeURIComponent(startParam)}`;
    }

    async function loadJourneys() {
        try {
            state.loading = true;
            const headers = await config.getAuthHeaders();
            
            await loadMessageBotUsername();
            
            const resp = await fetch('/api/journeys', { headers, credentials: 'include' });
            if (resp.ok) {
                const data = await resp.json();
                state.journeys = data.journeys || [];
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
            const triggerValue = firstTrigger?.trigger_config?.start_param || firstTrigger?.trigger_config?.value || '';
            const deepLinkUrl = getDeepLinkUrl(triggerValue);
            
            let deepLinkHtml = '';
            if (triggerValue && (triggerType === 'telegram_deeplink' || triggerType === 'deep_link')) {
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
                            <span>Trigger: <strong>${escapeHtml(triggerValue || '-')}</strong></span>
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
        state.selectedStatus = 'draft';
        
        const nameInput = document.getElementById('journey-name-input');
        const triggerValue = document.getElementById('journey-trigger-value');
        const triggerType = document.getElementById('journey-trigger-type');
        const modalTitle = document.getElementById('journey-modal-title');
        
        if (nameInput) nameInput.value = '';
        if (triggerValue) triggerValue.value = '';
        if (triggerType) triggerType.value = 'deep_link';
        if (modalTitle) modalTitle.textContent = journeyId ? 'Edit Journey' : 'Create Journey';
        
        selectStatus('draft');
        renderStepsList();
        
        if (journeyId) {
            await fetchJourneyDetail(journeyId);
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
        try {
            const headers = await config.getAuthHeaders();
            const resp = await fetch(`/api/journeys/${journeyId}`, { headers, credentials: 'include' });
            if (resp.ok) {
                const data = await resp.json();
                const journey = data.journey;
                
                const nameInput = document.getElementById('journey-name-input');
                if (nameInput) nameInput.value = journey.name || '';
                selectStatus(journey.status || 'draft');
                
                const triggers = journey.triggers || [];
                if (triggers.length > 0) {
                    const trigger = triggers[0];
                    const triggerType = document.getElementById('journey-trigger-type');
                    const triggerValue = document.getElementById('journey-trigger-value');
                    if (triggerType) triggerType.value = 'deep_link';
                    if (triggerValue) triggerValue.value = trigger.trigger_config?.start_param || trigger.trigger_config?.value || '';
                }
                
                state.steps = (journey.steps || []).map(s => ({
                    message_template: s.message_template,
                    delay_seconds: s.delay_seconds
                }));
                renderStepsList();
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
            
            if (journeyId) {
                const resp = await fetch(`/api/journeys/${journeyId}`, {
                    method: 'PUT',
                    headers,
                    body: JSON.stringify({ name, status }),
                    credentials: 'include'
                });
                if (!resp.ok) {
                    const data = await resp.json();
                    throw new Error(data.error || 'Failed to update journey');
                }
            } else {
                const resp = await fetch('/api/journeys', {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({ name, status }),
                    credentials: 'include'
                });
                const data = await resp.json();
                if (!resp.ok) {
                    throw new Error(data.error || 'Failed to create journey');
                }
                journeyId = data.journey.id;
            }
            
            if (triggerValue) {
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
            await loadJourneys();
            
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
        
        try {
            if (config.showLoading) config.showLoading('Deleting journey...');
            const headers = await config.getAuthHeaders();
            const resp = await fetch(`/api/journeys/${journeyId}`, {
                method: 'DELETE',
                headers,
                credentials: 'include'
            });
            
            if (config.hideLoading) config.hideLoading();
            
            if (resp.ok) {
                config.showToast('Journey deleted successfully', 'success');
                await loadJourneys();
            } else {
                const data = await resp.json();
                config.showToast(data.error || 'Failed to delete journey', 'error');
            }
        } catch (err) {
            if (config.hideLoading) config.hideLoading();
            console.error('Delete journey error:', err);
            config.showToast('Failed to delete journey', 'error');
        }
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
        
        container.innerHTML = state.steps.map((step, index) => `
            <div class="step-item">
                <div class="step-order">${index + 1}</div>
                <div class="step-content">
                    <div class="step-message">${escapeHtml(step.message_template.substring(0, 80))}${step.message_template.length > 80 ? '...' : ''}</div>
                    <div class="step-delay">Delay: ${step.delay_seconds}s</div>
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
        `).join('');
    }

    function addStep() {
        state.editingStepIndex = null;
        const msgInput = document.getElementById('step-message-input');
        const delayInput = document.getElementById('step-delay-input');
        const modalTitle = document.getElementById('step-modal-title');
        if (msgInput) msgInput.value = '';
        if (delayInput) delayInput.value = '0';
        if (modalTitle) modalTitle.textContent = 'Add Step';
        const backdrop = document.getElementById('step-modal-backdrop');
        if (backdrop) backdrop.classList.add('show');
    }

    function editStep(index) {
        state.editingStepIndex = index;
        const step = state.steps[index];
        const msgInput = document.getElementById('step-message-input');
        const delayInput = document.getElementById('step-delay-input');
        const modalTitle = document.getElementById('step-modal-title');
        if (msgInput) msgInput.value = step.message_template;
        if (delayInput) delayInput.value = step.delay_seconds;
        if (modalTitle) modalTitle.textContent = 'Edit Step';
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
        const message = msgInput ? msgInput.value.trim() : '';
        const delay = delayInput ? (parseInt(delayInput.value, 10) || 0) : 0;
        
        if (!message) {
            config.showToast('Please enter a message', 'error');
            return;
        }
        
        const stepData = {
            message_template: message,
            delay_seconds: delay
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
            getDeepLinkUrl: () => state.messageBotUsername
        };
        
        return window.JourneysModule;
    }

    window.initJourneys = initJourneys;
})();
