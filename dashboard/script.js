document.addEventListener('DOMContentLoaded', () => {
    const rolesList = document.getElementById('roles-list');
    const modelsList = document.getElementById('models-list'); // may be created dynamically in populateSidebar()
    const configTitle = document.getElementById('config-title');
    const configPanel = document.getElementById('config-panel');
    const saveBtn = document.getElementById('save-btn');
    const tabs = document.querySelectorAll('.tab-link');

    // ---- Orchestrations catalog (single source of truth for sidebar + cards) ----
    const ORCHESTRATIONS = [
        { cmd: '/simple',    emoji: '⚡', name: 'Simple',
          desc: 'Single-model pass via the reflex layer. Fast, no council.',
          target: 'simple role' },
        { cmd: '/standard',  emoji: '📋', name: 'Standard',
          desc: 'Single model with active preset. The operational brain.',
          target: 'standard role' },
        { cmd: '/vision',    emoji: '👁', name: 'Vision',
          desc: 'Image-aware single pass (image_base64 supported via API).',
          target: 'vision role' },
        { cmd: '/technical', emoji: '🔧', name: 'Technical Meeting',
          desc: 'Specialist → Creative → Critic → Overseer synthesis.',
          target: 'technical_* roles' },
        { cmd: '/design',    emoji: '🎨', name: 'Design Meeting',
          desc: 'Junior → Creative → Critic → Senior with image prompts.',
          target: 'design_* roles' },
        { cmd: '/boardroom', emoji: '🏛', name: 'Sequential Boardroom',
          desc: 'Full 5-seat council (Strategist · Specialist · Critic · Creative · Logical) + Chairman synthesis.',
          target: 'board_* roles' },
        { cmd: '/oracle',    emoji: '🔮', name: 'Oracle Council',
          desc: 'Online frontier-model parallel deliberation (when connected).',
          target: 'oracle pattern' },
        { cmd: '/nft',       emoji: '💎', name: 'NFT Creation',
          desc: 'Metadata generation + minting simulation.',
          target: 'nft_specialist' },
        { cmd: '/dev',       emoji: '🧪', name: 'Dev Lifecycle',
          desc: 'Creates a proposal in SQLite-backed kanban store (Backlog column). Use #dev in chatbox for proper workflow.',
          target: 'DevRouteManager' },
    ];

    // ── Council / role-group configuration ────────────────────────
    // Single source of truth for which roles belong to which council.
    const COUNCIL_CONFIG = [
        // ── Kanban-triggered councils ─────────────────────────────
        // Ordered by kanban column: proposal→beta_testing runs TECHNICAL_MEETING;
        // beta_testing→alpha_polish runs ALPHA_COUNCIL;
        // alpha_polish→finalized runs FINAL_AUDIT.
        { id:'technical', name:'Beta Testing (Technical)', icon:'🔧',
          desc:'Kanban trigger: draft → expand → critique → CTO synthesis',
          accent:'#4a90d9', section:'councils',
          roles:['drafting_architect','creative_expansionist',
                 'technical_critic','chief_technical_officer'] },
        { id:'alpha', name:'Alpha Polish', icon:'✨',
          desc:'Kanban trigger: UX → performance → critique → dev_alpha_polish',
          accent:'#e67e22', section:'councils',
          roles:['alpha_ux_specialist','alpha_perf_specialist',
                 'alpha_critic','dev_alpha_polish'] },
        { id:'final-audit', name:'Final Audit', icon:'✅',
          desc:'Kanban trigger: final_scribe → dev_final_audit verdict',
          accent:'#27ae60', section:'councils',
          roles:['final_scribe','dev_final_audit'] },

        // ── Manual-pattern councils (not kanban-triggered) ────────
        { id:'boardroom', name:'Boardroom', icon:'🏛',
          desc:'5-seat council → Chairman synthesis (/boardroom)',
          accent:'#c9a227', section:'councils',
          roles:['board_strategist','board_specialist','board_critic',
                 'board_creative','board_logical','board_chairman'] },
        { id:'design', name:'Design Council', icon:'🎨',
          desc:'Junior → Creative → Critic → Senior (/design)',
          accent:'#e74c3c', section:'councils',
          roles:['design_junior','creative_expansionist',
                 'design_critic','design_senior'] },

        // ── Core Services (used by simple/standard/flow patterns) ──
        { id:'fast-ops', name:'Fast Operations', icon:'⚡',
          desc:'Single-model passes (/simple, /standard, /vision)',
          accent:'#6e6e6e', section:'services',
          roles:['simple','standard','vision'] },
        { id:'flow-control', name:'Flow Control', icon:'🎭',
          desc:'Orchestration, guard, scribe & handoff',
          accent:'#6e6e6e', section:'services',
          roles:['moderator','brand_guard','scribe',
                 'handoff','handoff_planner','devlog_scribe',
                 'technical_specialist','dev_beta_council'] }
    ];

    let fullConfig = {};
    let availableModels = []; // New array to store the live model list
    let currentSelection = { type: null, key: null };
    let hasChanges = false;
    let systemLoadInterval = null;
    let chatHistory = []; // Store conversation history for role chat
    let currentChatRole = null; // Currently selected role for chat

    // --- Unified Chatbox Functionality ---
    const chatModeRadios = document.querySelectorAll('input[name="chat-mode"]');
    const chatRoleSelector = document.getElementById('chat-role-selector');
    const chatRoleSelect = document.getElementById('chat-role-select');
    const chatInput = document.getElementById('chat-input');
    const chatSendBtn = document.getElementById('chat-send-btn');
    const chatThread = document.getElementById('chat-thread');

    // Mode switching
    chatModeRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            const mode = e.target.value;
            if (mode === 'role') {
                chatRoleSelector.style.display = 'block';
                chatInput.placeholder = 'Chat with the selected role...';
                populateChatRoles();
            } else {
                chatRoleSelector.style.display = 'none';
                chatInput.placeholder = 'Type your message or orchestration command (e.g., #dev Create a new feature for X...)';
                chatHistory = []; // Clear history when switching to orchestration mode
            }
        });
    });

    // Role selection change
    chatRoleSelect.addEventListener('change', (e) => {
        currentChatRole = e.target.value;
        chatHistory = []; // Clear history when switching roles
        clearChatThread();
    });

    // Populate role dropdown
    function populateChatRoles() {
        if (Object.keys(fullConfig.roles || {}).length === 0) return;
        
        const roles = Object.keys(fullConfig.roles).sort();
        chatRoleSelect.innerHTML = '<option value="">-- Select a role --</option>' +
            roles.map(r => `<option value="${r}">${r}</option>`).join('');
    }

    // Send chat message
    chatSendBtn.addEventListener('click', async () => {
        const message = chatInput.value.trim();
        if (!message) return;

        const mode = document.querySelector('input[name="chat-mode"]:checked').value;
        
        if (mode === 'orchestration') {
            await sendOrchestrationMessage(message);
        } else {
            if (!currentChatRole) {
                appendChatMessage('system', 'Please select a role first.');
                return;
            }
            await sendRoleChatMessage(message);
        }
        
        chatInput.value = '';
    });

    // Handle Enter key (Shift+Enter for newline)
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatSendBtn.click();
        }
    });

    // Send orchestration message
    async function sendOrchestrationMessage(message) {
        appendChatMessage('user', message);
        appendChatMessage('system', '🎼 Processing orchestration...');
        
        try {
            const response = await fetch('/api/process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: message })
            });
            
            const data = await response.json();
            
            // Remove processing message
            const lastMsg = chatThread.lastElementChild;
            if (lastMsg && lastMsg.classList.contains('chat-system')) {
                lastMsg.remove();
            }
            
            if (data.status === 'success') {
                appendChatMessage('assistant', data.response || 'Orchestration completed.');
                if (data.kanban_card_id) {
                    appendChatMessage('system', `✅ Created kanban card: ${data.kanban_card_id}`);
                }
            } else {
                appendChatMessage('error', data.error || 'Orchestration failed.');
            }
        } catch (err) {
            const lastMsg = chatThread.lastElementChild;
            if (lastMsg && lastMsg.classList.contains('chat-system')) {
                lastMsg.remove();
            }
            appendChatMessage('error', `Error: ${err.message}`);
        }
    }

    // Send role chat message
    async function sendRoleChatMessage(message) {
        appendChatMessage('user', message);
        appendChatMessage('system', '💭 Thinking...');
        
        try {
            const response = await fetch('/api/chat/role', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    role: currentChatRole,
                    message: message,
                    history: chatHistory
                })
            });
            
            const data = await response.json();
            
            // Remove thinking message
            const lastMsg = chatThread.lastElementChild;
            if (lastMsg && lastMsg.classList.contains('chat-system')) {
                lastMsg.remove();
            }
            
            if (data.response) {
                appendChatMessage('assistant', data.response);
                chatHistory = data.history || [...chatHistory, 
                    { role: 'user', content: message },
                    { role: 'assistant', content: data.response }
                ];
            } else {
                appendChatMessage('error', data.error || 'No response from role.');
            }
        } catch (err) {
            const lastMsg = chatThread.lastElementChild;
            if (lastMsg && lastMsg.classList.contains('chat-system')) {
                lastMsg.remove();
            }
            appendChatMessage('error', `Error: ${err.message}`);
        }
    }

    // Append message to chat thread
    function appendChatMessage(type, content) {
        // Remove placeholder if present
        const placeholder = chatThread.querySelector('.placeholder');
        if (placeholder) placeholder.remove();
        
        const msgDiv = document.createElement('div');
        msgDiv.className = `chat-message chat-${type}`;
        
        const timestamp = new Date().toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit' 
        });
        
        let icon = '';
        if (type === 'user') icon = '👤';
        else if (type === 'assistant') icon = '🤖';
        else if (type === 'system') icon = 'ℹ️';
        else if (type === 'error') icon = '⚠️';
        
        msgDiv.innerHTML = `
            <div class="chat-message-header">
                <span class="chat-message-icon">${icon}</span>
                <span class="chat-message-time">${timestamp}</span>
            </div>
            <div class="chat-message-content">${escapeHtml(content)}</div>
        `;
        
        chatThread.appendChild(msgDiv);
        chatThread.scrollTop = chatThread.scrollHeight;
    }

    // Clear chat thread
    function clearChatThread() {
        chatThread.innerHTML = '<p class="placeholder">Your conversation will appear here</p>';
    }

    // HTML escape helper
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML.replace(/\n/g, '<br>');
    }

    // --- Data Fetching and Initialization ---

    async function loadConfig() {
        try {
            // Fetch config and live models concurrently for speed
            const [configResponse, modelsResponse] = await Promise.all([
                fetch('/api/config'),
                fetch('/api/models')
            ]);

            if (!configResponse.ok) {
                throw new Error('Failed to load configuration');
            }
            
            fullConfig = await configResponse.json();
            
            if (modelsResponse.ok) {
                const modelsData = await modelsResponse.json();
                availableModels = modelsData.models || [];
            } else {
                console.warn("Could not load live models from LM Studio.");
            }

            populateSidebar();
        } catch (error) {
            console.error('Error loading config:', error);
            configPanel.innerHTML = `<p class="placeholder">Error: Could not load configuration from the backend.</p>`;
        }
    }

    function populateSidebar() {
        rolesList.innerHTML = '';
        // modelsList is built dynamically inside the card below

        const allRoleKeys = Object.keys(fullConfig.roles || {}).sort();
        const assignedRoles = new Set();

        // ── Councils section ────────────────────────────────
        const councilsHdr = document.createElement('h2');
        councilsHdr.textContent = '📋 Councils';
        councilsHdr.className = 'section-divider';
        rolesList.appendChild(councilsHdr);

        COUNCIL_CONFIG.forEach(council => {
            const councilRoles = council.roles.filter(r => allRoleKeys.includes(r));
            councilRoles.forEach(r => assignedRoles.add(r));
            rolesList.appendChild(buildCouncilCard(council, councilRoles));
        });

        // ── Core Services section ───────────────────────────
        const svcHdr = document.createElement('h2');
        svcHdr.textContent = '⚙️ Core Services';
        svcHdr.className = 'section-divider';
        rolesList.appendChild(svcHdr);

        COUNCIL_CONFIG.filter(c => c.section === 'services').forEach(council => {
            const councilRoles = council.roles.filter(r => allRoleKeys.includes(r));
            councilRoles.forEach(r => assignedRoles.add(r));
            rolesList.appendChild(buildCouncilCard(council, councilRoles));
        });

        // ── Unassigned fallback ─────────────────────────────
        const unassigned = allRoleKeys.filter(r => !assignedRoles.has(r));
        if (unassigned.length > 0) {
            const warnHdr = document.createElement('h2');
            warnHdr.textContent = '⚠️ Unassigned';
            warnHdr.className = 'section-divider warning';
            rolesList.appendChild(warnHdr);
            unassigned.forEach(key => {
                const li = document.createElement('li');
                li.innerHTML = `<span>${key}</span>`;
                li.dataset.type = 'role';
                li.dataset.key = key;
                li.style.padding = '8px 12px';
                rolesList.appendChild(li);
            });
        }

        // ── Base Models (collapsible card) ─────────────────────
        const modelsCard = document.createElement('div');
        modelsCard.className = 'council-card';
        modelsCard.style.setProperty('--council-accent', '#8a8a8a');
        const modelsHeader = document.createElement('div');
        modelsHeader.className = 'council-card-header';
        modelsHeader.innerHTML = '<span class="council-icon">📦</span><span class="council-name">Base Models</span><span class="council-chevron">▼</span>';
        const modelsUl = document.getElementById('models-list') || document.createElement('ul');
        modelsUl.className = 'council-role-list';
        if (!document.getElementById('models-list')) {
            modelsUl.id = 'models-list';
        }
        modelsUl.innerHTML = '';
        Object.keys(fullConfig.models || {}).sort().forEach(key => {
            const li = document.createElement('li');
            li.textContent = key;
            li.dataset.type = 'model';
            li.dataset.key = key;
            modelsUl.appendChild(li);
        });
        modelsHeader.addEventListener('click', () => {
            const isCollapsed = modelsCard.classList.toggle('collapsed');
            try { localStorage.setItem('council-collapse-models', isCollapsed ? 'collapsed' : 'open'); } catch(_) {}
        });
        const savedModels = (() => { try { return localStorage.getItem('council-collapse-models'); } catch(_) { return null; } })();
        if (savedModels === 'collapsed') modelsCard.classList.add('collapsed');
        modelsCard.appendChild(modelsHeader);
        modelsCard.appendChild(modelsUl);
        rolesList.appendChild(modelsCard);
    }

    function buildCouncilCard(council, roles) {
        const card = document.createElement('div');
        card.className = 'council-card';
        card.style.setProperty('--council-accent', council.accent);
        card.dataset.councilId = council.id;

        // Header row (click to collapse)
        const header = document.createElement('div');
        header.className = 'council-card-header';
        header.innerHTML = `<span class="council-icon">${council.icon}</span>
                            <span class="council-name">${council.name}</span>
                            <span class="council-count">${roles.length} roles</span>
                            <span class="council-chevron">▼</span>`;

        // Description
        const desc = document.createElement('div');
        desc.className = 'council-card-desc';
        desc.textContent = council.desc;

        // Role list
        const ul = document.createElement('ul');
        ul.className = 'council-role-list';

        if (roles.length === 0) {
            const empty = document.createElement('li');
            empty.className = 'council-empty';
            empty.textContent = '(no roles configured)';
            ul.appendChild(empty);
        } else {
            roles.forEach(key => {
                const li = document.createElement('li');
                const roleSpan = document.createElement('span');
                roleSpan.textContent = key;
                li.appendChild(roleSpan);

                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'delete-role-btn';
                deleteBtn.textContent = '×';
                deleteBtn.title = 'Delete this role';
                deleteBtn.onclick = (e) => {
                    e.stopPropagation();
                    handleDeleteRole(key);
                };
                li.appendChild(deleteBtn);

                li.dataset.type = 'role';
                li.dataset.key = key;
                ul.appendChild(li);
            });
        }

        // Add-role button
        const addBtn = document.createElement('button');
        addBtn.className = 'add-role-category-btn';
        addBtn.textContent = `+ Add ${council.name} Role`;
        addBtn.onclick = () => handleAddRoleToCouncil(council);

        card.appendChild(header);
        card.appendChild(desc);
        card.appendChild(ul);
        card.appendChild(addBtn);

        // Collapse toggle
        header.addEventListener('click', () => {
            const isCollapsed = card.classList.toggle('collapsed');
            try { localStorage.setItem(`council-collapse-${council.id}`, isCollapsed ? 'collapsed' : 'open'); }
            catch(_) {}
        });

        // Restore state (services start collapsed by default)
        const saved = (() => { try { return localStorage.getItem(`council-collapse-${council.id}`); } catch(_) { return null; } })();
        if (saved === 'collapsed' || (saved === null && council.section === 'services')) {
            card.classList.add('collapsed');
        }

        return card;
    }

    // --- UI Rendering ---

    function renderConfigForm(type, key) {
        currentSelection = { type, key };
        const data = (type === 'role') ? fullConfig.roles[key] : fullConfig.models[key];

        configTitle.textContent = `Configuring ${type}: ${key}`;
        configPanel.innerHTML = '';

        // Identity & Behavior Section
        const identitySection = createSection('Identity & Behavior');
        
        if (type === 'role') {
            const isEnabled = data.enabled !== false; // default to true if missing
            identitySection.appendChild(createCheckbox('enabled', isEnabled, 'Enable this role'));
            
            // Use the live availableModels if we have them, otherwise fall back to whatever is in the config
            let modelOptions = availableModels.length > 0 ? availableModels : Object.keys(fullConfig.models || {});
            
            // Ensure the currently selected model is always in the list, even if LM Studio doesn't report it
            // (e.g., if LM Studio is closed but the config has a saved model)
            if (data.model && !modelOptions.includes(data.model)) {
                modelOptions = [data.model, ...modelOptions];
            }
            
            identitySection.appendChild(createSelect('model', data.model, 'Model', modelOptions));
            identitySection.appendChild(createCheckbox('reasoning_enabled', data.reasoning_enabled, 'Enable reasoning mode'));
        }
        
        configPanel.appendChild(identitySection);

        // Prompting Section (only for roles)
        if (type === 'role') {
            const promptingSection = createSection('Prompting');
            promptingSection.appendChild(createTextArea('system_prompt', data.system_prompt, 'System Prompt'));
            configPanel.appendChild(promptingSection);
        }

        // Sampling Section
        const samplingSection = createSection('Sampling Parameters');
        samplingSection.appendChild(createSlider('temperature', data.temperature, 'Temperature', 0, 2, 0.1));
        samplingSection.appendChild(createSlider('top_p', data.top_p, 'Top P', 0, 1, 0.05));
        samplingSection.appendChild(createSlider('top_k', data.top_k, 'Top K', 0, 120, 1));
        samplingSection.appendChild(createSlider('repeat_penalty', data.repeat_penalty, 'Repeat Penalty', 0, 2, 0.1));
        samplingSection.appendChild(createSlider('min_p', data.min_p, 'Min P', 0, 1, 0.05));
        configPanel.appendChild(samplingSection);

        // Resources Section
        const resourcesSection = createSection('Resources & Performance');
        
        // Get hints from loaded models if available
        let contextHint = '';
        let layersHint = 'Use -1 for maximum GPU offload';
        
        if (type === 'role' && data.model) {
            // Check if this model is loaded in LM Studio
            fetch('/api/loaded').then(async response => {
                if (response.ok) {
                    const loadedData = await response.json();
                    const loaded = loadedData.loaded || [];
                    const modelInfo = loaded.find(m => m.model_key === data.model);
                    
                    if (modelInfo) {
                        // Update hints with actual values from LM Studio
                        if (modelInfo.context_length) {
                            const ctxInput = document.getElementById('config-context_window');
                            if (ctxInput && ctxInput.nextElementSibling) {
                                const helpText = ctxInput.parentElement.querySelector('.form-help') || 
                                               document.createElement('small');
                                helpText.className = 'form-help';
                                helpText.textContent = `LM Studio reports: ${modelInfo.context_length}`;
                                helpText.style.color = 'var(--success-color)';
                                if (!ctxInput.parentElement.querySelector('.form-help')) {
                                    ctxInput.parentElement.appendChild(helpText);
                                }
                            }
                        }
                    }
                }
            }).catch(console.error);
        }
        
        resourcesSection.appendChild(createNumberInput('max_tokens', data.max_tokens, 'Max Tokens'));
        resourcesSection.appendChild(createNumberInput('context_window', data.context_window, 'Context Window', contextHint));
        resourcesSection.appendChild(createRangeInput('gpu_offload_ratio', data.gpu_offload_ratio !== undefined ? data.gpu_offload_ratio : "max", 'GPU Offload Ratio', '0 (CPU-only) to 1 (max GPU)', 0, 1, 0.1));
        resourcesSection.appendChild(createSelect('k_cache_quant', data.k_cache_quant, 'K-Cache Quantization', ['f16', 'q8_0', 'q4_0']));
        resourcesSection.appendChild(createSelect('v_cache_quant', data.v_cache_quant, 'V-Cache Quantization', ['f16', 'q8_0', 'q4_0']));
        resourcesSection.appendChild(createSelect('flash_attention', data.flash_attention, 'Flash Attention', ['true', 'false']));
        resourcesSection.appendChild(createNumberInput('n_parallel', data.n_parallel, 'N-Parallel', 'Concurrent request slots (CLI override, not in SDK)'));
        configPanel.appendChild(resourcesSection);

        // Advanced Section (only for roles)
        if (type === 'role') {
            const advancedSection = createSection('Advanced');
            const compassOptions = ["IGNORE", "LOW WEIGHT", "MEDIUM WEIGHT", "HIGH WEIGHT", "MAXIMUM WEIGHT"];
            advancedSection.appendChild(createSelect('compass_weight', data.compass_weight, 'Compass Weight', compassOptions));
            configPanel.appendChild(advancedSection);
        }
        
        // After rendering, update empty seats
        updateHomeEmptySeats();
    }

    // --- Form Element Creators ---
    
    function createSection(title) {
        const section = document.createElement('fieldset');
        section.className = 'config-section';
        const legend = document.createElement('legend');
        legend.textContent = title;
        section.appendChild(legend);
        return section;
    }

    function createFormGroup(labelText, helpText) {
        const group = document.createElement('div');
        group.className = 'form-group';
        const label = document.createElement('label');
        label.textContent = labelText;
        group.appendChild(label);
        
        if (helpText) {
            const help = document.createElement('small');
            help.className = 'form-help';
            help.textContent = helpText;
            group.appendChild(help);
        }
        
        return group;
    }

    function createSelect(key, value, labelText, options) {
        const group = createFormGroup(labelText);
        const select = document.createElement('select');
        select.id = `config-${key}`;
        select.dataset.key = key;
        // Empty placeholder — no phantom defaults. The value must exist in
        // master_config.md, otherwise the field is explicitly unconfigured.
        const emptyOpt = document.createElement('option');
        emptyOpt.value = '';
        emptyOpt.textContent = '—';
        if (!value) emptyOpt.selected = true;
        select.appendChild(emptyOpt);
        options.forEach(option => {
            const opt = document.createElement('option');
            opt.value = option;
            opt.textContent = option;
            // Normalise both sides to strings: JSON bool true/false from API
            // will match string 'true'/'false' in the options array.
            if (String(option) === String(value)) {
                opt.selected = true;
                emptyOpt.selected = false;
            }
            select.appendChild(opt);
        });
        select.addEventListener('change', handleInputChange);
        group.appendChild(select);
        return group;
    }

    function createCheckbox(key, value, labelText) {
        const group = document.createElement('div');
        group.className = 'form-group checkbox-group';
        const label = document.createElement('label');
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `config-${key}`;
        checkbox.dataset.key = key;
        checkbox.checked = value;
        checkbox.addEventListener('change', handleInputChange);
        
        const span = document.createElement('span');
        span.textContent = labelText;

        label.appendChild(checkbox);
        label.appendChild(span);
        group.appendChild(label);
        return group;
    }

    function createTextArea(key, value, labelText) {
        const group = createFormGroup(labelText);
        const textarea = document.createElement('textarea');
        textarea.id = `config-${key}`;
        textarea.dataset.key = key;
        textarea.value = value || '';
        textarea.addEventListener('input', handleInputChange);
        group.appendChild(textarea);
        return group;
    }
    
    // This function is no longer needed for roles, but might be useful elsewhere.
    function createText(key, value, labelText) {
        const group = createFormGroup(labelText);
        const text = document.createElement('input');
        text.type = 'text';
        text.id = `config-${key}`;
        text.dataset.key = key;
        text.value = value || '';
        text.addEventListener('input', handleInputChange);
        group.appendChild(text);
        return group;
    }


    function createSlider(key, value, labelText, min, max, step) {
        const group = createFormGroup(labelText);
        const sliderContainer = document.createElement('div');
        sliderContainer.className = 'slider-group';
        
        const slider = document.createElement('input');
        slider.type = 'range';
        slider.id = `config-${key}`;
        slider.dataset.key = key;
        slider.min = min;
        slider.max = max;
        // Use finer increments for better control
        slider.step = step || (max <= 1 ? 0.01 : max <= 100 ? 0.1 : 1);
        slider.value = value || 0;
        
        const valueDisplay = document.createElement('span');
        valueDisplay.textContent = slider.value;
        
        slider.addEventListener('input', () => {
            valueDisplay.textContent = slider.value;
            handleInputChange({ target: slider });
        });
        
        sliderContainer.appendChild(slider);
        sliderContainer.appendChild(valueDisplay);
        group.appendChild(sliderContainer);
        return group;
    }

    function createRangeInput(key, value, labelText, helpText, min, max, step) {
        const group = createFormGroup(labelText, helpText);
        const wrapper = document.createElement('div');
        wrapper.style.display = 'flex';
        wrapper.style.alignItems = 'center';
        wrapper.style.gap = '8px';

        const input = document.createElement('input');
        input.type = 'range';
        input.min = min;
        input.max = max;
        input.step = step;
        input.id = `config-${key}`;
        input.dataset.key = key;
        
        // Handle "max" and "off" string defaults coming from config
        if (value === 'max') input.value = 1;
        else if (value === 'off') input.value = 0;
        else input.value = value !== undefined ? value : 1;

        const display = document.createElement('span');
        display.style.fontFamily = 'monospace';
        display.style.fontSize = '0.9em';
        
        const updateDisplay = (v) => {
            if (v === '1') return 'max';
            if (v === '0') return 'off';
            return v;
        };
        display.textContent = updateDisplay(input.value);

        input.addEventListener('input', (e) => {
            display.textContent = updateDisplay(e.target.value);
            
            // Format the value for the backend before sending to handleInputChange
            const finalValue = e.target.value === '1' ? 'max' : (e.target.value === '0' ? 'off' : parseFloat(e.target.value));
            
            // We need to trigger handleInputChange but spoof the value
            // Since handleInputChange reads directly from the element, we temporarily attach a property
            e.target._spofedValue = finalValue;
            handleInputChange(e);
        });

        wrapper.appendChild(input);
        wrapper.appendChild(display);
        group.appendChild(wrapper);
        return group;
    }

    function createNumberInput(key, value, labelText, helpText) {
        const group = createFormGroup(labelText, helpText);
        const input = document.createElement('input');
        input.type = 'number';
        input.id = `config-${key}`;
        input.dataset.key = key;
        input.value = value || 0;
        input.addEventListener('input', (e) => {
            if (e.target._spofedValue !== undefined) {
                // Ignore, this is handled by the custom wrapper
            } else {
                handleInputChange(e);
            }
        });
        group.appendChild(input);
        return group;
    }

    // --- Helper function to switch tabs programmatically ---
    window.switchToTab = function(tabName) {
        const tabButton = document.querySelector(`.tab-link[data-tab="${tabName}"]`);
        if (tabButton) {
            tabButton.click();
        }
    };

    // --- Home Tab Functions ---
    async function updateSystemLoad() {
        try {
            // Try the direct endpoint first, fall back to mock data if server has old routes
            const response = await fetch('/api/system/load');
            
            let data;
            if (!response.ok) {
                // If the server has old routes, use mock data for demonstration
                console.warn('System load endpoint not available, using mock data');
                data = {
                    cpu: {
                        percent: Math.random() * 100,
                        cores: 8
                    },
                    memory: {
                        percent: 45 + Math.random() * 30,
                        used_gb: Math.round((8 + Math.random() * 8) * 100) / 100,
                        total_gb: 32
                    },
                    gpu1: {
                        percent: Math.random() * 100,
                        memory_used_gb: Math.round(Math.random() * 24 * 10) / 10,
                        memory_total_gb: 24,
                        available: true,
                        name: "NVIDIA RTX 4090"
                    },
                    gpu2: {
                        percent: Math.random() * 100,
                        memory_used_gb: Math.round(Math.random() * 24 * 10) / 10,
                        memory_total_gb: 24,
                        available: true,
                        name: "NVIDIA RTX 4090"
                    },
                    gpu: {  // Backward compatibility
                        percent: Math.random() * 100,
                        memory_used_gb: Math.round(Math.random() * 24 * 10) / 10,
                        memory_total_gb: 24,
                        available: true
                    }
                };
            } else {
                data = await response.json();
            }
            
            // Update CPU (both Home and Orchestrations)
            const cpuBars = ['cpu-bar', 'orch-cpu-bar'];
            const cpuTexts = ['cpu-text', 'orch-cpu-text'];
            cpuBars.forEach((id, idx) => {
                const bar = document.getElementById(id);
                const text = document.getElementById(cpuTexts[idx]);
                if (bar && text) {
                    bar.style.width = `${data.cpu.percent}%`;
                    text.textContent = `${data.cpu.percent.toFixed(1)}%`;
                }
            });
            
            // Update Memory (both Home and Orchestrations)
            const ramBars = ['ram-bar', 'orch-ram-bar'];
            const ramTexts = ['ram-text', 'orch-ram-text'];
            ramBars.forEach((id, idx) => {
                const bar = document.getElementById(id);
                const text = document.getElementById(ramTexts[idx]);
                if (bar && text) {
                    bar.style.width = `${data.memory.percent}%`;
                    text.textContent = `${data.memory.used_gb}/${data.memory.total_gb} GB`;
                }
            });
            
            // Update GPU 1 (both Home and Orchestrations)
            const gpu1Bars = ['gpu-bar', 'orch-gpu-bar'];
            const gpu1Texts = ['gpu-text', 'orch-gpu-text'];
            gpu1Bars.forEach((id, idx) => {
                const bar = document.getElementById(id);
                const text = document.getElementById(gpu1Texts[idx]);
                if (bar && text) {
                    if (data.gpu1 && data.gpu1.available) {
                        bar.style.width = `${data.gpu1.percent}%`;
                        text.textContent = `${data.gpu1.percent.toFixed(1)}%`;
                    } else if (data.gpu && data.gpu.available) {
                        // Fallback to single GPU data
                        bar.style.width = `${data.gpu.percent}%`;
                        text.textContent = `${data.gpu.percent.toFixed(1)}%`;
                    } else {
                        bar.style.width = '0%';
                        text.textContent = 'N/A';
                    }
                }
            });
            
            // Update VRAM 1
            const vram1Bars = ['vram1-bar', 'orch-vram1-bar'];
            const vram1Texts = ['vram1-text', 'orch-vram1-text'];
            vram1Bars.forEach((id, idx) => {
                const bar = document.getElementById(id);
                const text = document.getElementById(vram1Texts[idx]);
                if (bar && text) {
                    if (data.gpu1 && data.gpu1.available) {
                        const vramPercent = (data.gpu1.memory_used_gb / data.gpu1.memory_total_gb) * 100;
                        bar.style.width = `${vramPercent}%`;
                        text.textContent = `${data.gpu1.memory_used_gb.toFixed(1)}/${data.gpu1.memory_total_gb.toFixed(1)} GB`;
                    } else if (data.gpu && data.gpu.available) {
                        // Fallback to single GPU data
                        const vramPercent = (data.gpu.memory_used_gb / data.gpu.memory_total_gb) * 100;
                        bar.style.width = `${vramPercent}%`;
                        text.textContent = `${data.gpu.memory_used_gb.toFixed(1)}/${data.gpu.memory_total_gb.toFixed(1)} GB`;
                    } else {
                        bar.style.width = '0%';
                        text.textContent = 'N/A';
                    }
                }
            });
            
            // Update GPU 2
            const gpu2Bars = ['gpu2-bar', 'orch-gpu2-bar'];
            const gpu2Texts = ['gpu2-text', 'orch-gpu2-text'];
            gpu2Bars.forEach((id, idx) => {
                const bar = document.getElementById(id);
                const text = document.getElementById(gpu2Texts[idx]);
                if (bar && text) {
                    if (data.gpu2 && data.gpu2.available) {
                        bar.style.width = `${data.gpu2.percent}%`;
                        text.textContent = `${data.gpu2.percent.toFixed(1)}%`;
                    } else {
                        bar.style.width = '0%';
                        text.textContent = 'N/A';
                    }
                }
            });
            
            // Update VRAM 2
            const vram2Bars = ['vram2-bar', 'orch-vram2-bar'];
            const vram2Texts = ['vram2-text', 'orch-vram2-text'];
            vram2Bars.forEach((id, idx) => {
                const bar = document.getElementById(id);
                const text = document.getElementById(vram2Texts[idx]);
                if (bar && text) {
                    if (data.gpu2 && data.gpu2.available) {
                        const vramPercent = (data.gpu2.memory_used_gb / data.gpu2.memory_total_gb) * 100;
                        bar.style.width = `${vramPercent}%`;
                        text.textContent = `${data.gpu2.memory_used_gb.toFixed(1)}/${data.gpu2.memory_total_gb.toFixed(1)} GB`;
                    } else {
                        bar.style.width = '0%';
                        text.textContent = 'N/A';
                    }
                }
            });
        } catch (error) {
            console.error('Error fetching system load:', error);
        }
    }

    async function updateHomeLoadedModels() {
        try {
            const response = await fetch('/api/loaded');
            if (!response.ok) throw new Error('Failed to fetch loaded models');
            
            const data = await response.json();
            const container = document.getElementById('home-loaded-models');
            
            if (!container) return;
            
            if (data.loaded && data.loaded.length > 0) {
                container.innerHTML = data.loaded.map(model => `
                    <div class="model-item">
                        <span class="model-name">${model.identifier || model.model_key}</span>
                        <span class="model-context">${model.context_length ? `${model.context_length} ctx` : ''}</span>
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<p class="placeholder">No models loaded</p>';
            }
        } catch (error) {
            console.error('Error fetching loaded models:', error);
        }
    }

    function updateHomeEmptySeats() {
        const container = document.getElementById('home-empty-seats');
        if (!container) return;
        
        const emptySeats = [];
        
        // Check for roles with issues
        Object.entries(fullConfig.roles || {}).forEach(([key, role]) => {
            const issues = [];
            
            if (role.enabled === false) {
                issues.push('disabled');
            }
            if (!role.model) {
                issues.push('no model');
            }
            if (!role.system_prompt || role.system_prompt.trim() === '') {
                issues.push('no prompt');
            }
            
            if (issues.length > 0) {
                emptySeats.push({ name: key, reason: issues.join(', ') });
            }
        });
        
        if (emptySeats.length > 0) {
            container.innerHTML = emptySeats.map(seat => `
                <div class="empty-seat">
                    <span class="role-name">${seat.name}</span>
                    <span class="reason">${seat.reason}</span>
                </div>
            `).join('');
            
            // Also add badges to sidebar
            document.querySelectorAll('.sidebar li[data-type="role"]').forEach(li => {
                const roleName = li.dataset.key;
                const hasIssue = emptySeats.some(s => s.name === roleName);
                
                // Remove existing badge
                const existingBadge = li.querySelector('.empty-seat-badge');
                if (existingBadge) existingBadge.remove();
                
                // Add badge if needed
                if (hasIssue) {
                    const badge = document.createElement('span');
                    badge.className = 'empty-seat-badge';
                    badge.title = 'Empty seat - needs configuration';
                    li.appendChild(badge);
                }
            });
        } else {
            container.innerHTML = '<p style="color: var(--success-color);">✓ All roles configured</p>';
        }
    }

    async function initializeHome() {
        await updateSystemLoad();
        await updateHomeLoadedModels();
        updateHomeEmptySeats();
        
        // Start polling for system load
        if (systemLoadInterval) clearInterval(systemLoadInterval);
        systemLoadInterval = setInterval(updateSystemLoad, 3000);
    }

    // --- Tab Switching Logic ---

    async function handleTabClick(event) {
        const tab = event.target;
        const tabName = tab.dataset.tab;

        // Update tab buttons
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        // Update content panels
        document.querySelectorAll('.tab-content').forEach(panel => {
            panel.classList.remove('active');
        });
        document.getElementById(tabName).classList.add('active');

        // Show config actions only on config tab
        const configActions = document.querySelector('.config-actions');
        if (configActions) {
            configActions.style.display = (tabName === 'config') ? 'flex' : 'none';
        }
        
        // Clear intervals when leaving home
        if (tabName !== 'home' && systemLoadInterval) {
            clearInterval(systemLoadInterval);
            systemLoadInterval = null;
        }

        // Home tab: initialize dashboard
        if (tabName === 'home') {
            lmstudio.deactivate();
            initializeHome();
            return;
        }
        
        // Orchestrations tab: render cards (no diagram fetch)
        if (tabName === 'orchestrations') {
            lmstudio.deactivate();
            renderOrchestrationCards();
            return;
        }

        // LM Studio tab: refresh loaded + catalog + benches on open
        if (tabName === 'lmstudio') {
            lmstudio.activate();
            return;
        }
        
        // System tab: handle subtabs
        if (tabName === 'system') {
            lmstudio.deactivate();
            initializeSystemTab();
            return;
        }

        // DevLog tab: set default date to today
        if (tabName === 'devlog') {
            const dateInput = document.getElementById('devlog-date');
            if (dateInput && !dateInput.value) {
                dateInput.value = new Date().toISOString().split('T')[0];
            }
        }

        // Any other tab: stop the LM Studio log poller
        lmstudio.deactivate();
    }
    
    async function loadDiagram(diagramType) {
        const panel = document.getElementById(`system-${diagramType}`);
        if (!panel) return;
        
        panel.innerHTML = '<p class="placeholder">Loading System Diagram...</p>';

        try {
            const response = await fetch(`/api/system/${diagramType}`);
            if (!response.ok) {
                throw new Error(`Failed to load '${diagramType}' diagram`);
            }
            const data = await response.json();

            let html = '';
            if (data.description) {
                html += `<div class="system-diagram-desc" style="margin-bottom: 20px; font-size: 14px; line-height: 1.6; color: var(--text-muted);">${data.description}</div>`;
            }
            html += `<pre class="mermaid">${data.diagram}</pre>`;
            
            panel.innerHTML = html;
            await mermaid.run({ nodes: panel.querySelectorAll('.mermaid') });
            panel.setAttribute('data-loaded', 'true');

        } catch (error) {
            console.error(`Error loading diagram for ${diagramType}:`, error);
            panel.innerHTML = `<p class="placeholder">Error: Could not load diagram.</p>`;
        }
    }
    
    function initializeSystemTab() {
        // Load first subtab if not already loaded
        const activeSubtab = document.querySelector('.system-subtab-link.active');
        if (activeSubtab) {
            const subtabName = activeSubtab.dataset.subtab;
            const panel = document.getElementById(`system-${subtabName}`);
            if (panel && !panel.hasAttribute('data-loaded')) {
                loadDiagram(subtabName);
            }
        }
        
        // Add event listeners to system subtabs
        document.querySelectorAll('.system-subtab-link').forEach(link => {
            link.removeEventListener('click', handleSystemSubtabClick); // Remove if exists
            link.addEventListener('click', handleSystemSubtabClick);
        });
    }
    
    function handleSystemSubtabClick(event) {
        const link = event.target;
        const subtabName = link.dataset.subtab;
        
        // Update active states
        document.querySelectorAll('.system-subtab-link').forEach(l => l.classList.remove('active'));
        link.classList.add('active');
        
        document.querySelectorAll('.system-subtab').forEach(panel => {
            panel.classList.remove('active');
        });
        const targetPanel = document.getElementById(`system-${subtabName}`);
        if (targetPanel) {
            targetPanel.classList.add('active');
            
            // ARCH-DA5B0A2D (A4): the 'kanban' subtab is owned by window.Kanban
            // (see the KANBAN WORKFLOW MODULE block below). Do NOT run
            // loadDiagram() for it — that would clobber the Kanban DOM with
            // a mermaid chart fetched from the legacy /api/system/kanban
            // endpoint. The Kanban module renders its own content via
            // /api/kanban/board on first subtab activation.
            if (subtabName === 'kanban') {
                return;
            }

            // Load diagram if not loaded
            if (!targetPanel.hasAttribute('data-loaded')) {
                loadDiagram(subtabName);
            }
        }
    }


    // --- Event Handlers ---

    function handleSidebarClick(event) {
        // Find the nearest LI (handles clicks on spans/buttons inside LIs)
        const li = event.target.closest('li');
        if (!li) return;
        if (!li.dataset.type || !li.dataset.key) return;

        // Remove active class from all items
        document.querySelectorAll('#roles-list li').forEach(el => el.classList.remove('active'));
        // Add active class to clicked item
        li.classList.add('active');
        renderConfigForm(li.dataset.type, li.dataset.key);
    }

    function handleInputChange(event) {
        hasChanges = true;
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Configuration';
        saveBtn.classList.remove('success');

        const target = event.target;
        const key = target.dataset.key;
        
        // Use spoofed value if provided by custom wrapper
        let value = target._spofedValue !== undefined ? target._spofedValue : target.value;

        // Convert numeric types (unless it's a spoofed string like 'max' or 'off')
        if ((target.type === 'number' || target.type === 'range') && typeof value !== 'string') {
            value = Number(value);
        } else if (target.type === 'checkbox') {
            value = target.checked;
        }
        
        const { type, key: configKey } = currentSelection;
        if (type && configKey) {
            const targetObj = type === 'role' ? fullConfig.roles[configKey] : fullConfig.models[configKey];
            if (value === '' || value === null || value === undefined) {
                delete targetObj[key]; // remove key entirely — no phantom empties
            } else {
                targetObj[key] = value;
            }
        }
    }

    async function handleSaveClick() {
        if (!hasChanges) return;

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(fullConfig),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to save configuration');
            }

            await loadConfig();
            hasChanges = false;
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saved Successfully!';
            saveBtn.classList.add('success');
            if (currentSelection.type && currentSelection.key) {
                renderConfigForm(currentSelection.type, currentSelection.key);
            }

        } catch (error) {
            console.error('Error saving config:', error);
            alert(`Error: ${error.message}`);
        }
    }

    /*────────────────────────────────────────────────────────────────
     * Bidirectional sync
     * 1. Dashboard → master_config.md  (save — handled above)
     * 2. External → dashboard  (poll — reload if changed without dirty buffer)
     *───────────────────────────────────────────────────────────────*/
    let _lastKnownConfigHash = '';

    async function computeConfigHash() {
        try {
            const r = await fetch('/api/config');
            if (!r.ok) return null;
            return JSON.stringify(await r.json());
        } catch { return null; }
    }

    async function syncFromDisk() {
        const hash = await computeConfigHash();
        if (hash && hash !== _lastKnownConfigHash) {
            if (hasChanges) {
                // Dashboard has unsaved changes — warn, don't overwrite.
                console.warn('[SYNC] External config change detected, but dashboard has unsaved edits — skipping sync.');
                return;
            }
            console.log('[SYNC] External config change detected — reloading.');
            await loadConfig();
            _lastKnownConfigHash = hash;
            // Re-render current form to stay on selected item
            if (currentSelection.type && currentSelection.key) {
                renderConfigForm(currentSelection.type, currentSelection.key);
            }
        }
    }

    // Initial hash
    (async () => {
        _lastKnownConfigHash = await computeConfigHash() || '';
    })();

    // Poll every 15 seconds for external changes
    setInterval(syncFromDisk, 15000);

    /**
     * Run an orchestration against /process.
     */
    async function runOrchestration(cmd, prompt, { compass = '' } = {}) {
        if (!prompt || !prompt.trim()) {
        }
        const composed = (cmd && cmd !== 'auto')
            ? `${cmd} ${prompt}`
            : prompt;

        const body = { prompt: composed };
        if (compass) body.compass_weight = compass;

        const response = await fetch('/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || result.response || `HTTP ${response.status}`);
        }
        return result;
    }

    // ---- Orchestrations tab ----
    function renderOrchestrationCards() {
        const grid = document.getElementById('orch-grid');
        if (!grid || grid.dataset.rendered === '1') return;

        grid.innerHTML = '';
        ORCHESTRATIONS.forEach(o => {
            const card = document.createElement('div');
            card.className = 'orch-card';
            card.dataset.cmd = o.cmd;
            card.innerHTML = `
                <div class="orch-card-head">
                    <span class="orch-card-emoji">${o.emoji}</span>
                    <span>${o.name}</span>
                </div>
                <span class="orch-card-cmd">${o.cmd}</span>
                <div class="orch-card-desc">${o.desc}</div>
                <div class="orch-card-meta">→ ${o.target}</div>
            `;
            card.addEventListener('click', () => triggerCardOrchestration(card, o.cmd));
            grid.appendChild(card);
        });
        grid.dataset.rendered = '1';
    }

    async function triggerCardOrchestration(card, cmd) {
        const promptEl = document.getElementById('orch-prompt');
        const compassEl = document.getElementById('orch-compass');
        const outMeta = document.querySelector('.orch-meta');
        const outResp = document.querySelector('.orch-response');

        const prompt = (promptEl && promptEl.value || '').trim();
        if (!prompt) {
            promptEl && promptEl.focus();
            outMeta.innerHTML = `<span class="err">Need a prompt first.</span>`;
            return;
        }

        card.classList.add('running');
        outMeta.innerHTML = `<span>Pattern: ${cmd}</span><span>Status: ⏳ running…</span>`;
        outResp.textContent = 'Awaiting response from /process …';

        const t0 = performance.now();
        try {
            const result = await runOrchestration(cmd, prompt, {
                compass: compassEl ? compassEl.value : ''
            });
            const ms = Math.round(performance.now() - t0);
            
            outMeta.innerHTML =
                `<span class="ok">Pattern: ${result.pattern || cmd}</span>` +
                `<span>Task: ${result.task_id || '—'}</span>` +
                `<span>Duration: ${(ms / 1000).toFixed(1)}s</span>` +
                (result.saved_path ? `<span>Saved: ${result.saved_path.split(/[\\/]/).slice(-1)[0]}</span>` : '');
            outResp.textContent = result.response || '(no response body)';
        } catch (error) {
            outMeta.innerHTML = `<span class="err">Pattern: ${cmd}</span><span class="err">Error</span>`;
            outResp.textContent = String(error.message || error);
        } finally {
            card.classList.remove('running');
        }
    }

    // --- Initial Setup ---

    function initializeCollapsibleMenus() {
        // Councils and Models use .council-card collapse (handled in
        // buildCouncilCard and populateSidebar respectively).
        // Keep as no-op for backwards compat with call sites.
    }

    rolesList.addEventListener('click', handleSidebarClick);
    // modelsList is created dynamically inside rolesList; use event delegation
    // on the parent (rolesList) which already has the click handler above.
    saveBtn.addEventListener('click', handleSaveClick);
    tabs.forEach(tab => tab.addEventListener('click', handleTabClick));
    
    // Add Role and Meeting buttons
    const addRoleBtn = document.getElementById('add-role-btn');
    const addMeetingBtn = document.getElementById('add-meeting-btn');
    
    if (addRoleBtn) {
        addRoleBtn.addEventListener('click', handleAddRole);
    }
    
    if (addMeetingBtn) {
        addMeetingBtn.addEventListener('click', handleAddMeetingType);
    }
    
    // Orchestration log controls
    const clearLogBtn = document.getElementById('clear-orch-log');
    const saveLogBtn = document.getElementById('save-orch-log');
    
    if (clearLogBtn) {
        clearLogBtn.addEventListener('click', () => {
            const outMeta = document.querySelector('.orch-meta');
            const outResp = document.querySelector('.orch-response');
            if (outMeta) outMeta.innerHTML = '';
            if (outResp) outResp.innerHTML = '<em>Log cleared.</em>';
        });
    }

    const rerunBtn = document.getElementById('rerun-orch-btn');
    if (rerunBtn) {
        rerunBtn.addEventListener('click', async () => {
            const targetIdEl = document.getElementById('orch-target-id');
            const targetId = targetIdEl ? targetIdEl.value.trim() : '';
            if (!targetId) {
                alert("Please enter a Target Proposal ID to re-run.");
                return;
            }

            const outMeta = document.querySelector('.orch-meta');
            const outResp = document.querySelector('.orch-response');
            
            outMeta.innerHTML = `<span>Re-running: ${targetId}</span><span>Status: ⏳ running…</span>`;
            outResp.textContent = 'Awaiting response from /workflow/transition...';
            rerunBtn.disabled = true;

            try {
                // If it starts with DEV or ARCH or NLST it is a proposal
                // Send it to the transition endpoint to run the council
                const response = await fetch('/api/workflow/transition', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        proposal_id: targetId,
                        target_column: 'proposal',
                        approver: 'dashboard-rerun'
                    })
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.detail || data.error || `HTTP ${response.status}`);
                }
                
                outMeta.innerHTML = `<span class="ok">Re-run successful for ${targetId}</span>`;
                outResp.textContent = JSON.stringify(data, null, 2);
            } catch (err) {
                outMeta.innerHTML = `<span class="err">Re-run failed</span>`;
                outResp.textContent = String(err.message || err);
            } finally {
                rerunBtn.disabled = false;
            }
        });
    }
    
    if (saveLogBtn) {
        saveLogBtn.addEventListener('click', () => {
            const outMeta = document.querySelector('.orch-meta');
            const outResp = document.querySelector('.orch-response');
            
            // Create a log object
            const logData = {
                timestamp: new Date().toISOString(),
                metadata: outMeta ? outMeta.innerText : '',
                response: outResp ? outResp.innerText : ''
            };
            
            // Create downloadable file
            const blob = new Blob([JSON.stringify(logData, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `orchestration-log-${Date.now()}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        });
    }
    
    // Preset management buttons
    const savePresetBtn = document.getElementById('save-preset-btn');
    const loadPresetBtnConfig = document.getElementById('load-preset-btn-config');
    const pushObsidianBtn = document.getElementById('push-obsidian-btn');
    
    if (savePresetBtn) {
        savePresetBtn.addEventListener('click', () => {
            const presetName = prompt('Enter a name for this preset:');
            if (!presetName) return;
            
            // Save current config as preset
            const preset = {
                name: presetName,
                timestamp: new Date().toISOString(),
                config: fullConfig
            };
            
            // Store in localStorage (could be sent to backend instead)
            const presets = JSON.parse(localStorage.getItem('configPresets') || '{}');
            presets[presetName] = preset;
            localStorage.setItem('configPresets', JSON.stringify(presets));
            
            alert(`Preset "${presetName}" saved successfully!`);
        });
    }
    
    if (loadPresetBtnConfig) {
        loadPresetBtnConfig.addEventListener('click', () => {
            const presets = JSON.parse(localStorage.getItem('configPresets') || '{}');
            const presetNames = Object.keys(presets);
            
            if (presetNames.length === 0) {
                alert('No saved presets found.');
                return;
            }
            
            const selectedPreset = prompt(`Available presets:\n${presetNames.join('\n')}\n\nEnter preset name to load:`);
            if (!selectedPreset || !presets[selectedPreset]) return;
            
            // Load the preset
            fullConfig = presets[selectedPreset].config;
            
            // Update UI
            populateSidebar();
            const firstRole = document.querySelector('.sidebar li[data-type="role"]');
            if (firstRole) firstRole.click();
            
            hasChanges = true;
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Configuration (Preset Loaded)';
            
            alert(`Preset "${selectedPreset}" loaded. Remember to save configuration to apply changes.`);
        });
    }
    
    if (pushObsidianBtn) {
        pushObsidianBtn.addEventListener('click', async () => {
            try {
                // This would integrate with Obsidian API
                const vaultPath = prompt('Enter your Obsidian vault path:');
                if (!vaultPath) return;
                
                // TODO: Implement actual Obsidian integration
                alert('Obsidian integration will be implemented with the Obsidian plugin. Config would be pushed to: ' + vaultPath);
                
            } catch (error) {
                console.error('Error pushing to Obsidian:', error);
                alert('Failed to push to Obsidian: ' + error.message);
            }
        });
    }
    
    async function handleAddRole() {
        // Prompt user to pick a council first
        const councilNames = COUNCIL_CONFIG.map(c => c.name).join('\n');
        const choice = prompt(`Which council should this role belong to?\n\n${councilNames}\n\nEnter council name:`, 'Fast Operations');
        if (!choice) return;
        const council = COUNCIL_CONFIG.find(c => c.name.toLowerCase() === choice.trim().toLowerCase());
        if (!council) { alert(`Unknown council "${choice}". Please pick from the list.`); return; }
        handleAddRoleToCouncil(council);
    }

    async function handleAddRoleToCouncil(council) {
        const roleName = prompt(`Enter the name for the new ${council.name} role:`);
        if (!roleName || !roleName.trim()) return;

        if (fullConfig.roles && fullConfig.roles[roleName]) {
            alert(`Role "${roleName}" already exists!`);
            return;
        }

        const newRole = {
            enabled: true,
            model: Object.keys(fullConfig.models || {})[0] || '',
            system_prompt: '',
            temperature: 0.8,
            top_p: 0.95,
            top_k: 40,
            repeat_penalty: 1.1,
            min_p: 0.05,
            max_tokens: 2048,
            context_window: 8192,
            gpu_layers: -1,
            kv_cache: 512,
            reasoning_enabled: false,
            compass_weight: 'MEDIUM WEIGHT'
        };

        if (!fullConfig.roles) fullConfig.roles = {};
        fullConfig.roles[roleName] = newRole;

        // Also add to the council's static role list so it renders there
        if (!council.roles.includes(roleName)) council.roles.push(roleName);

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(fullConfig),
            });
            if (!response.ok) throw new Error('Failed to save new role');
            await loadConfig();
            const newRoleElement = document.querySelector(`li[data-key="${roleName}"][data-type="role"]`);
            if (newRoleElement) newRoleElement.click();
        } catch (error) {
            console.error('Error creating role:', error);
            alert(`Failed to create role: ${error.message}`);
            delete fullConfig.roles[roleName];
            council.roles = council.roles.filter(r => r !== roleName);
        }
    }
    
    async function handleDeleteRole(roleName) {
        if (!confirm(`Are you sure you want to delete the role "${roleName}"?`)) {
            return;
        }
        
        // Remove from config
        delete fullConfig.roles[roleName];
        
        // Save config
        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(fullConfig),
            });
            
            if (!response.ok) {
                throw new Error('Failed to delete role');
            }
            
            // Reload UI
            await loadConfig();
            
            // Clear config panel
            configTitle.textContent = 'Select a Role or Model to Configure';
            configPanel.innerHTML = '<p class="placeholder">Role deleted successfully.</p>';
            
        } catch (error) {
            console.error('Error deleting role:', error);
            alert(`Failed to delete role: ${error.message}`);
            // Restore role if delete failed
            await loadConfig();
        }
    }
    
    async function handleAddMeetingType() {
        const meetingName = prompt('Enter the name for the new meeting type:');
        if (!meetingName || !meetingName.trim()) return;
        
        const meetingPrefix = prompt('Enter the prefix for roles in this meeting type (e.g., "custom_"):');
        if (!meetingPrefix || !meetingPrefix.trim()) return;
        
        const meetingEmoji = prompt('Enter an emoji for this meeting type:', '🎯');
        const meetingCmd = prompt('Enter the command for this meeting type (e.g., "/custom"):', '/' + meetingPrefix.replace('_', ''));
        const meetingDesc = prompt('Enter a description for this meeting type:');
        
        // Create new orchestration pattern
        const newOrchestration = {
            name: meetingName,
            emoji: meetingEmoji || '🎯',
            cmd: meetingCmd || '/' + meetingPrefix.replace('_', ''),
            desc: meetingDesc || 'Custom meeting type',
            target: 'Custom orchestration pattern'
        };
        
        // Add to orchestrations list
        ORCHESTRATIONS.push(newOrchestration);
        
        // Re-render orchestration cards
        const grid = document.getElementById('orch-grid');
        if (grid) {
            grid.dataset.rendered = '0'; // Force re-render
            renderOrchestrationCards();
        }
        
        // Create initial roles for this meeting type
        const createInitialRoles = confirm(`Would you like to create initial roles for "${meetingName}"?`);
        if (createInitialRoles) {
            const numRoles = parseInt(prompt('How many roles to create?', '3'));
            for (let i = 1; i <= numRoles; i++) {
                const roleName = `${meetingPrefix}role_${i}`;
                if (!fullConfig.roles[roleName]) {
                    fullConfig.roles[roleName] = {
                        enabled: true,
                        model: Object.keys(fullConfig.models || {})[0] || '',
                        system_prompt: `You are role ${i} in the ${meetingName} meeting.`,
                        temperature: 0.8,
                        top_p: 0.95,
                        top_k: 40,
                        repeat_penalty: 1.1,
                        min_p: 0.05,
                        max_tokens: 2048,
                        context_window: 8192,
                        gpu_layers: -1,
                        kv_cache: 512,
                        reasoning_enabled: false,
                        compass_weight: 'MEDIUM WEIGHT'
                    };
                }
            }
            
            // Save config with new roles
            try {
                const response = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(fullConfig),
                });
                
                if (!response.ok) {
                    throw new Error('Failed to save new meeting roles');
                }
                
                // Reload UI
                await loadConfig();
                
                alert(`Created "${meetingName}" meeting type with ${numRoles} roles!`);
                
            } catch (error) {
                console.error('Error creating meeting type:', error);
                alert(`Failed to create meeting type: ${error.message}`);
            }
        } else {
            alert(`Meeting type "${meetingName}" created! You can add roles using the "+ Add ${meetingName} Role" button in the sidebar.`);
        }
    }

    // =========================================================================
    // LM Studio control module
    // -------------------------------------------------------------------------
    // Wires the LM Studio tab: Console (loaded models, load form, result panel)
    // and Benchmarks (JSONL history + detail panel). Talks to the API on
    // localhost:5000, never to LM Studio directly.
    // =========================================================================
    const lmstudio = (() => {
        const $ = (id) => document.getElementById(id);
        let benchRowsCache = [];
        let activated = false;

        const fmt = (v) => (v === null || v === undefined ? '—' : String(v));
        
        function showModelDefaults(model) {
            const defaultsContainer = document.getElementById('model-defaults-content');
            if (!defaultsContainer) return;
            
            if (!model) {
                defaultsContainer.innerHTML = '<p class="placeholder">Select a loaded model to view defaults</p>';
                return;
            }
            
            // Get model config if available
            const modelConfig = (fullConfig.models && fullConfig.models[model.model_key]) || {};
            
            // Display model defaults and capabilities
            const defaults = {
                'Model Key': model.model_key || 'N/A',
                'Context Length': model.context_length || modelConfig.context_window || '32768',
                'Temperature': modelConfig.temperature || '0.7',
                'Top P': modelConfig.top_p || '0.95',
                'Top K': modelConfig.top_k || '40',
                'Max Tokens': modelConfig.max_tokens || '2048',
                'Batch Size': modelConfig.batch_size || '512',
                'GPU Layers': modelConfig.gpu_layers || '-1',
                'K-Cache Quant': modelConfig.k_cache_quant || '—',
                'V-Cache Quant': modelConfig.v_cache_quant || '—',
                'Flash Attention': model.flash_attention !== undefined ? model.flash_attention : 'auto'
            };
            
            defaultsContainer.innerHTML = Object.entries(defaults).map(([label, value]) => `
                <div class="model-default-item">
                    <label>${label}</label>
                    <div class="value ${['Context Length', 'GPU Layers', 'Batch Size'].includes(label) ? 'highlight' : ''}">
                        ${value}
                    </div>
                </div>
            `).join('');
        }

        function renderResult(obj, kind /* 'ok' | 'err' */) {
            const el = $('lms-result-panel');
            if (!el) return;
            const pretty = (typeof obj === 'string')
                ? obj
                : JSON.stringify(obj, null, 2);
            el.innerHTML = '';
            const span = document.createElement('span');
            span.className = kind === 'err' ? 'lms-err' : 'lms-ok';
            span.textContent = pretty;
            el.appendChild(span);
        }

        async function refreshLoaded() {
            const tbody = $('lms-loaded-table').querySelector('tbody');
            tbody.innerHTML = '<tr><td colspan="4" class="lms-empty">loading…</td></tr>';
            try {
                const r = await fetch('/api/loaded');
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                const data = await r.json();
                const loaded = data.loaded || [];
                if (loaded.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" class="lms-empty">no models loaded</td></tr>';
                } else {
                    tbody.innerHTML = loaded.map((inst, idx) => {
                        // Try to get defaults from config
                        const modelConfig = (fullConfig.models && fullConfig.models[inst.model_key]) || {};
                        const defaultsInfo = modelConfig ? `
                            <div class="model-defaults" style="font-size: 0.8rem; color: #6e6e6e; margin-top: 4px;">
                                T:${modelConfig.temperature || '-'} 
                                P:${modelConfig.top_p || '-'} 
                                K:${modelConfig.top_k || '-'} 
                                Max:${modelConfig.max_tokens || '-'}
                            </div>
                        ` : '';
                        
                        return `
                            <tr class="model-row" data-index="${idx}">
                                <td>${fmt(inst.identifier)}</td>
                                <td>
                                    ${fmt(inst.model_key)}
                                    ${defaultsInfo}
                                </td>
                                <td>${fmt(inst.context_length)}</td>
                                <td>
                                    <button class="lms-link-btn" data-unload="${encodeURIComponent(inst.identifier || '')}">unload</button>
                                    <button class="lms-link-btn" data-force-reload="${encodeURIComponent(inst.identifier || '')}">force reload</button>
                                </td>
                            </tr>
                        `;
                    }).join('');
                    
                    // Add click handlers for model rows
                    tbody.querySelectorAll('.model-row').forEach(row => {
                        row.addEventListener('click', (e) => {
                            if (e.target.tagName !== 'BUTTON') {
                                const modelIdx = parseInt(row.dataset.index);
                                showModelDefaults(loaded[modelIdx]);
                                // Highlight selected row
                                tbody.querySelectorAll('.model-row').forEach(r => r.classList.remove('selected'));
                                row.classList.add('selected');
                            }
                        });
                    });
                    
                    // Auto-select first model
                    if (loaded.length > 0) {
                        showModelDefaults(loaded[0]);
                        tbody.querySelector('.model-row').classList.add('selected');
                    }
                    
                    tbody.querySelectorAll('button[data-unload]').forEach(btn => {
                        btn.addEventListener('click', async () => {
                            const ident = decodeURIComponent(btn.dataset.unload);
                            if (!ident) return;
                            btn.disabled = true;
                            btn.textContent = 'unloading…';
                            try {
                                const res = await fetch(`/api/load/${encodeURIComponent(ident)}`, { method: 'DELETE' });
                                const out = await res.json();
                                renderResult(out, res.ok ? 'ok' : 'err');
                            } catch (e) {
                                renderResult(String(e), 'err');
                            }
                            refreshLoaded();
                        });
                    });
                    
                    tbody.querySelectorAll('button[data-force-reload]').forEach(btn => {
                        btn.addEventListener('click', async () => {
                            const ident = decodeURIComponent(btn.dataset.forceReload);
                            if (!ident) return;
                            
                            // Find the model info
                            const modelInfo = loaded.find(m => m.identifier === ident);
                            if (!modelInfo) return;
                            
                            btn.disabled = true;
                            btn.textContent = 'reloading…';
                            
                            try {
                                // First unload
                                await fetch(`/api/load/${encodeURIComponent(ident)}`, { method: 'DELETE' });
                                
                                // Then reload with force flag
                                const loadBody = {
                                    model_key: modelInfo.model_key,
                                    identifier: ident,
                                    force_reload: true
                                };
                                
                                const res = await fetch('/api/load', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify(loadBody)
                                });
                                const out = await res.json();
                                renderResult(out, res.ok ? 'ok' : 'err');
                            } catch (e) {
                                renderResult(String(e), 'err');
                            }
                            refreshLoaded();
                        });
                    });
                }
                // Populate datalist for the load form
                const dl = $('lms-catalog');
                if (dl && Array.isArray(data.downloaded)) {
                    dl.innerHTML = data.downloaded.map(k =>
                        `<option value="${k.replace(/"/g, '&quot;')}">`).join('');
                }
            } catch (e) {
                tbody.innerHTML = `<tr><td colspan="4" class="lms-empty">error: ${e.message || e}</td></tr>`;
            }
        }

        async function refreshCatalog() {
            try {
                const r = await fetch('/api/catalog/refresh', { method: 'POST' });
                const out = await r.json();
                renderResult(out, r.ok ? 'ok' : 'err');
                if (r.ok && Array.isArray(out.model_keys)) {
                    const dl = $('lms-catalog');
                    if (dl) {
                        dl.innerHTML = out.model_keys.map(k =>
                            `<option value="${k.replace(/"/g, '&quot;')}">`).join('');
                    }
                }
            } catch (e) {
                renderResult(String(e), 'err');
            }
        }

        function readForm() {
            const f = $('lms-load-form');
            const fd = new FormData(f);
            const cfg = {};
            const setIfPresent = (key, transform = v => v) => {
                const v = fd.get(key);
                if (v !== null && v !== '') cfg[key] = transform(v);
            };
            setIfPresent('context_length', Number);
            // gpu_offload_ratio accepts 'max' | 'off' | float 0.0–1.0.
            // Pass strings through as-is so the backend sees the canonical
            // shape; numeric strings convert to float.
            setIfPresent('gpu_offload_ratio', v => {
                const s = String(v).trim().toLowerCase();
                if (s === 'max' || s === 'off') return s;
                const n = Number(s);
                if (n === 1) return 'max';
                if (n === 0) return 'off';
                return Number.isFinite(n) ? n : s;
            });
            setIfPresent('cache_type_k');
            setIfPresent('cache_type_v');
            setIfPresent('n_parallel', Number);
            const fa = fd.get('flash_attention');
            if (fa === 'true') cfg.flash_attention = true;
            else if (fa === 'false') cfg.flash_attention = false;

            // Sampling defaults: collected into a separate payload key so the
            // backend can persist them per-model (they do NOT affect VRAM,
            // they're applied at chat.completions request time).
            const sampling = {};
            const SAMPLING_KEYS = [
                'temperature', 'top_p', 'top_k', 'min_p',
                'repeat_penalty', 'max_tokens',
            ];
            for (const k of SAMPLING_KEYS) {
                const v = fd.get(k);
                if (v !== null && v !== '') {
                    const n = Number(v);
                    if (Number.isFinite(n)) sampling[k] = n;
                }
            }

            const body = {
                model_key: (fd.get('model_key') || '').trim(),
                force_reload: fd.get('force_reload') === 'on',
            };
            const ident = (fd.get('identifier') || '').trim();
            if (ident) body.identifier = ident;
            const ttl = fd.get('ttl');
            if (ttl !== null && ttl !== '') body.ttl = Number(ttl);
            if (Object.keys(cfg).length > 0) body.config = cfg;
            if (Object.keys(sampling).length > 0) body.sampling = sampling;
            return body;
        }

        async function handleLoadSubmit(e) {
            e.preventDefault();
            const submit = $('lms-load-submit');
            const body = readForm();
            if (!body.model_key) {
                renderResult('model_key is required', 'err');
                return;
            }
            submit.disabled = true;
            submit.textContent = 'loading…';
            renderResult(`POST /api/load\n${JSON.stringify(body, null, 2)}\n\n[…]`, 'ok');
            try {
                const r = await fetch('/api/load', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const out = await r.json();
                renderResult(out, r.ok ? 'ok' : 'err');
            } catch (err) {
                renderResult(String(err), 'err');
            } finally {
                submit.disabled = false;
                submit.textContent = 'load';
                refreshLoaded();
            }
        }

        async function refreshBenchmarks() {
            const tbody = $('lms-bench-table').querySelector('tbody');
            tbody.innerHTML = '<tr><td colspan="6" class="lms-empty">loading…</td></tr>';
            try {
                const r = await fetch('/api/benchmarks');
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                const data = await r.json();
                const runs = data.runs || [];
                benchRowsCache = runs;
                if (runs.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="lms-empty">no runs yet</td></tr>';
                    return;
                }
                tbody.innerHTML = runs.map((r, idx) => {
                    const ctx = r.config && r.config.context_length;
                    const cli = r.client_tps;
                    const srv = r.log && r.log.server_eval_tps;
                    const pp  = r.log && r.log.pipeline_parallelism;
                    return `
                        <tr data-idx="${idx}">
                            <td>${fmt(r.ts)}</td>
                            <td>${fmt(r.model_key)}</td>
                            <td>${fmt(ctx)}</td>
                            <td>${fmt(cli)}</td>
                            <td>${fmt(srv)}</td>
                            <td>${pp === true ? '✓' : pp === false ? '✗' : '—'}</td>
                        </tr>`;
                }).join('');
                tbody.querySelectorAll('tr[data-idx]').forEach(tr => {
                    tr.addEventListener('click', () => {
                        tbody.querySelectorAll('tr.selected').forEach(x => x.classList.remove('selected'));
                        tr.classList.add('selected');
                        const idx = Number(tr.dataset.idx);
                        const row = benchRowsCache[idx];
                        $('lms-bench-detail').textContent = JSON.stringify(row, null, 2);
                    });
                });
            } catch (e) {
                tbody.innerHTML = `<tr><td colspan="6" class="lms-empty">error: ${e.message || e}</td></tr>`;
            }
        }

        function activateSubtab(name) {
            document.querySelectorAll('.lms-subtab-link').forEach(b => {
                b.classList.toggle('active', b.dataset.subtab === name);
            });
            document.querySelectorAll('.lms-subtab').forEach(s => {
                s.classList.toggle('active', s.id === `lms-${name}`);
            });
            if (name === 'console') refreshLoaded();
            if (name === 'benchmarks') refreshBenchmarks();
        }

        // ---------------------------------------------------------------
        // LM Studio runtime log tail (right side of Console).
        // ---------------------------------------------------------------
        let logPollHandle = null;

        // Patterns the bench-runner SOP watches for. Coloured for at-a-glance
        // confirmation that a load did what we asked.
        const LOG_PATTERNS = [
            { re: /pipeline parallelism enabled/i, cls: 'lms-log-hit' },
            { re: /flash_attn\s*=\s*enabled/i,     cls: 'lms-log-hit' },
            { re: /LlamaV4::load (called|config)/i, cls: 'lms-log-hit' },
            { re: /llama_kv_cache:\s*size/i,        cls: 'lms-log-hit' },
            { re: /n_seq_max\s*=/i,                 cls: 'lms-log-hit' },
            { re: /retrying without pipeline parallelism/i, cls: 'lms-log-warn' },
            { re: /cudaMalloc failed/i,             cls: 'lms-log-err' },
            { re: /out of memory|OOM/i,             cls: 'lms-log-err' },
            { re: /\[ERROR\]|ERROR:/,               cls: 'lms-log-err' },
            { re: /\[WARN(?:ING)?\]|WARN:/,         cls: 'lms-log-warn' },
        ];

        function escapeHtml(s) {
            // ARCH-DA5B0A2D (A4): tolerate null/undefined. The kanban API
            // legitimately returns title=null for cards migrated from the
            // legacy vault that lacked a frontmatter title — a TypeError
            // here was killing the entire board render.
            if (s === null || s === undefined) return '';
            return String(s)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
        }

        function colourLine(line) {
            const escaped = escapeHtml(line);
            for (const p of LOG_PATTERNS) {
                if (p.re.test(line)) {
                    return `<span class="${p.cls}">${escaped}</span>`;
                }
            }
            return escaped;
        }

        async function refreshLogs() {
            const panel = $('lms-log-panel');
            if (!panel) return;
            const filter = ($('lms-log-filter')?.value || '').trim();
            const wasAtBottom =
                panel.scrollHeight - panel.scrollTop - panel.clientHeight < 24;
            const qs = new URLSearchParams({ lines: '180' });
            if (filter) qs.set('filter', filter);
            try {
                const r = await fetch(`/api/lmstudio/logs?${qs}`);
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                const data = await r.json();
                if (data.error) {
                    panel.innerHTML = `<em>error: ${escapeHtml(data.error)}</em>`;
                    return;
                }
                const lines = data.lines || [];
                if (lines.length === 0) {
                    panel.innerHTML = '<em>no matching lines.</em>';
                    return;
                }
                panel.innerHTML = lines.map(colourLine).join('\n');
                if (wasAtBottom) panel.scrollTop = panel.scrollHeight;
            } catch (e) {
                panel.innerHTML = `<em>error: ${escapeHtml(String(e))}</em>`;
            }
        }

        function setFollow(on) {
            if (logPollHandle) {
                clearInterval(logPollHandle);
                logPollHandle = null;
            }
            if (on) {
                refreshLogs();
                logPollHandle = setInterval(refreshLogs, 2000);
            }
        }

        function bind() {
            document.querySelectorAll('.lms-subtab-link').forEach(b => {
                b.addEventListener('click', () => activateSubtab(b.dataset.subtab));
            });
            const refreshBtn = $('lms-refresh-btn');
            if (refreshBtn) refreshBtn.addEventListener('click', refreshLoaded);
            const catRefresh = $('lms-catalog-refresh-btn');
            if (catRefresh) catRefresh.addEventListener('click', refreshCatalog);
            const benchRefresh = $('lms-bench-refresh-btn');
            if (benchRefresh) benchRefresh.addEventListener('click', refreshBenchmarks);
            const form = $('lms-load-form');
            if (form) form.addEventListener('submit', handleLoadSubmit);
            const logRefresh = $('lms-log-refresh-btn');
            if (logRefresh) logRefresh.addEventListener('click', refreshLogs);
            const logFollow = $('lms-log-follow');
            if (logFollow) logFollow.addEventListener('change', () => setFollow(logFollow.checked));
            const logFilter = $('lms-log-filter');
            if (logFilter) {
                let debounce = null;
                logFilter.addEventListener('input', () => {
                    clearTimeout(debounce);
                    debounce = setTimeout(refreshLogs, 250);
                });
            }
        }

        return {
            activate() {
                if (!activated) { bind(); activated = true; }
                // Always refresh on open so reloads in LM Studio reflect immediately
                refreshLoaded();
                refreshBenchmarks();
                // Kick off the log poller if "follow" is on (it is by default)
                const follow = $('lms-log-follow');
                setFollow(follow ? follow.checked : true);
            },
            deactivate() {
                setFollow(false);
            },
        };
    })();

    loadConfig().then(() => {
        // Initialize menus after the sidebar has been populated
        initializeCollapsibleMenus();
        // Initialize home tab since it's the default active tab
        initializeHome();
    });

    // ===== KANBAN WORKFLOW MODULE =====
    window.Kanban = (function() {
        const API_BASE = '';
        const CANONICAL_COLUMNS = ['backlog', 'proposal', 'beta testing', 'alpha polish', 'finalized', 'deployed'];
        const VALID_SUBSTATUSES = ['planning', 'execution.coding', 'execution.testing', 'review', 'blocked'];

        // ARCH-DA5B0A2D (A4): local escapeHtml — the global one defined at
        // line ~1723 is inside another closure (LMS logs section) and not
        // reachable from this IIFE. Tolerates null/undefined to handle
        // migrated cards that lack a frontmatter title.
        function escapeHtml(s) {
            if (s === null || s === undefined) return '';
            return String(s)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
        }

        // Error banner helpers
        const errorBanner = document.getElementById('kanban-error-banner');
        const errorMessage = document.getElementById('error-message');
        const closeErrorBtn = document.getElementById('close-error-btn');

        function showError(detail) {
            if (!errorBanner || !errorMessage) return;
            errorMessage.textContent = detail || 'An unknown error occurred';
            errorBanner.classList.remove('is-hidden');
        }

        function hideError() {
            if (!errorBanner) return;
            errorBanner.classList.add('is-hidden');
        }

        // Auto-refresh state (defined once, inside IIFE)
        let refreshInterval = null;

        function startAutoRefresh() {
            if (refreshInterval) return;
            refreshInterval = setInterval(() => {
                if (document.visibilityState === 'visible') {
                    loadBoard();
                }
            }, 30000); // 30 seconds
        }

        function stopAutoRefresh() {
            if (refreshInterval) {
                clearInterval(refreshInterval);
                refreshInterval = null;
            }
        }

        // Wire subtab activation/deactivation for auto-refresh
        document.addEventListener('click', (e) => {
            const link = e.target.closest('.system-subtab-link');
            if (!link) return;
            if (link.dataset.subtab === 'kanban') {
                loadBoard();
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });

        // Card creation
        function createCard(cardData) {
            const card = document.createElement('div');
            card.className = 'kanban-card';
            card.draggable = true;
            card.dataset.proposalId = cardData.proposal_id;

            // Prefix badge
            let prefixClass = 'dev';
            if (cardData.proposal_id.startsWith('ARCH-')) prefixClass = 'arch';
            else if (cardData.proposal_id.startsWith('NLST-')) prefixClass = 'nlst';

            const severityClass = cardData.severity || 'unknown';

            // Substatus dropdown — shown for both beta-testing and alpha-polish.
            // Both columns run the same micro-lifecycle (planning -> coding ->
            // testing -> review); the only difference is scope. The original
            // ARCH-DA5B0A2D proposal locked alpha to a single state, but in
            // practice alpha-polish patches march through the same stages
            // (see DEV-B5D5C0DE.alpha_polish_patches). The renderer + API
            // already accept substatus on any column.
            const SUBSTATUS_COLUMNS = ['beta testing', 'alpha polish'];
            // substatusWidget is a DOM node built later via buildSubstatusWidget.

            // Fall back to the proposal id when the title is missing —
            // happens for cards migrated from the legacy vault that lacked
            // a frontmatter `title` field. An untitled card is unreadable.
            const displayTitle = cardData.title || cardData.proposal_id;
            // Keywords — comma-separated tags displayed as small badges
            const keywordsHtml = cardData.keywords
                ? `<div class="kanban-card-keywords">${cardData.keywords.split(',').map(k => `<span class="kanban-card-keyword-tag">${escapeHtml(k.trim())}</span>`).join('')}</div>`
                : '';
            // Compact ID: keep prefix-shortdate-hash readable; the full id
            // (e.g. ARCH-20260524-011510-5DFB393F) is too long for a card
            // footer but the user needs *some* way to refer to it in chat.
            const shortId = cardData.proposal_id;

            card.innerHTML = `
                <div class="kanban-card-header">
                    <span class="kanban-card-prefix ${prefixClass}">${prefixClass.toUpperCase()}</span>
                    <span class="kanban-card-title">${escapeHtml(displayTitle)}</span>
                </div>
                <div class="kanban-card-meta">
                    <span class="kanban-card-severity ${severityClass}">
                        <span class="kanban-card-severity-dot"></span>
                        <span>${severityClass.toUpperCase()}</span>
                    </span>
                </div>
                ${keywordsHtml}
                <div class="kanban-card-id" title="Click card to copy this id">${escapeHtml(shortId)}</div>
            `;

            // Append substatus widget as real DOM node (preserves listeners)
            if (SUBSTATUS_COLUMNS.includes(cardData.column_name)) {
                card.appendChild(buildSubstatusWidget(cardData));
            }

            // Proposal column: show council verdict badge so user knows
            // whether to drag forward or move back to backlog for rework.
            if (cardData.column_name === 'proposal' && cardData.substatus) {
                card.appendChild(buildVerdictBadge(cardData.substatus));
            }

            // Backlog column: show any non-null substatus (e.g. "rejected"
            // persists after a failed council so rework cards are visible).
            if (cardData.column_name === 'backlog' && cardData.substatus) {
                card.appendChild(buildVerdictBadge(cardData.substatus));
            }

            // Finalized column: show audit verdict badge (approved/rejected)
            // so the final audit outcome is visible on the card.
            if (cardData.column_name === 'finalized' && cardData.substatus) {
                card.appendChild(buildVerdictBadge(cardData.substatus));
            }

            // Always add a "Rerun Council" button to the card header
            const rerunBtn = document.createElement('button');
            rerunBtn.className = 'system-button';
            rerunBtn.style.cssText = 'position:absolute; right:5px; top:5px; font-size:10px; padding:2px 4px; z-index:10; background:var(--bg-darker); border:1px solid var(--border-color); color:var(--text-color); cursor:pointer; border-radius:3px;';
            rerunBtn.textContent = '↻ Rerun';
            rerunBtn.title = 'Re-trigger council queue for this proposal';
            rerunBtn.onclick = (e) => {
                e.stopPropagation(); // prevent opening history
                window.Kanban_rerunCouncil(cardData.proposal_id, cardData.column_name);
            };
            card.appendChild(rerunBtn);

            // Drag events
            card.addEventListener('dragstart', handleDragStart);
            card.addEventListener('dragend', handleDragEnd);

            // Click to show history, EXCEPT clicks on substatus controls
            // and the proposal-id badge (copy to clipboard).
            card.addEventListener('click', (e) => {
                if (e.target.closest('.kanban-card-substatus')) return;
                if (e.target.closest('.kanban-verdict-wrap')) return; // DO NOT OPEN HISTORY IF CLICKING VERDICT
                if (e.target.classList.contains('kanban-card-id')) {
                    navigator.clipboard.writeText(cardData.proposal_id).then(() => {
                        const el = e.target;
                        const orig = el.textContent;
                        el.textContent = 'copied!';
                        setTimeout(() => { el.textContent = orig; }, 900);
                    }).catch(() => { /* ignore - non-https origins refuse */ });
                    return;
                }
                showHistory(cardData.proposal_id);
            });

            return card;
        }

        // ── Substatus state machine ────────────────────────────────────────
        // Each state carries: label, badge colour, the single forward
        // action (next + tooltip), and optional secondary actions.
        const SUBSTATUS_MACHINE = {
            'planning': {
                label: 'Planning',
                color: '#4a7eb5',
                forward: { next: 'execution.coding', btn: '▶ Start Coding', tip: 'Implementation started — begin writing code' },
                secondary: []
            },
            'execution.coding': {
                label: 'Coding',
                color: '#d9a84a',
                forward: { next: 'execution.debugging', btn: '▶ Debug', tip: 'Code written — run tests and fix failures' },
                secondary: []
            },
            'execution.debugging': {
                label: 'Debugging',
                color: '#d96a4a',
                forward: { next: 'execution.testing', btn: '▶ Start Testing', tip: 'Bugs resolved — begin formal QA testing' },
                secondary: []
            },
            'execution.testing': {
                label: 'Testing',
                color: '#9a4ad9',
                forward: { next: 'execution.ready-for-alpha', btn: '✓ Mark Ready', tip: 'All tests pass — ready to move to next column' },
                secondary: []
            },
            'execution.ready-for-alpha': {
                label: 'Ready ✓',
                color: '#4ad98a',
                forward: null,  // no advance btn — drag the card
                secondary: []
            },
            'blocked': {
                label: 'Blocked',
                color: '#d94a4a',
                forward: null,  // resolved via Unblock
                secondary: []
            },
            'review': {
                label: 'Review',
                color: '#c4b84a',
                forward: null,  // resolved via Resume
                secondary: []
            },
        };

        // Returns the DOM node for the substatus section of a card.
        function buildSubstatusWidget(cardData) {
            const wrap = document.createElement('div');
            wrap.className = 'kanban-card-substatus';
            const s = cardData.substatus || 'planning';
            const col = cardData.column_name;

            const state = SUBSTATUS_MACHINE[s] || { label: s, color: '#666', forward: null, secondary: [] };

            // Badge
            const badge = document.createElement('span');
            badge.className = 'substatus-badge';
            badge.textContent = state.label;
            badge.style.setProperty('--substatus-color', state.color);
            
            // Add click-to-view for substatus badges too (Beta/Alpha handoffs)
            badge.title = "Click to view Handoff Document";
            badge.style.cursor = 'pointer';
            const openSubstatusDoc = (e) => {
                const cardEl = e.target.closest('.kanban-card');
                if (cardEl && cardEl.dataset.proposalId) {
                    e.stopPropagation();
                    viewDocument(cardEl.dataset.proposalId, cardEl.dataset.columnId || col);
                }
            };
            badge.addEventListener('click', openSubstatusDoc);
            wrap.title = "Click to view Handoff Document";
            wrap.style.cursor = 'pointer';
            wrap.addEventListener('click', openSubstatusDoc);

            wrap.appendChild(badge);

            // Forward action button
            if (state.forward) {
                const btn = document.createElement('button');
                btn.className = 'substatus-btn substatus-btn-forward system-button';
                btn.textContent = state.forward.btn;
                btn.title = state.forward.tip;
                btn.dataset.proposalId = cardData.proposal_id;
                btn.dataset.column = col;
                btn.dataset.next = state.forward.next;
                btn.addEventListener('click', handleSubstatusAdvance);
                
                // Explicitly add styling to override any generic button reset
                btn.style.background = 'var(--bg-dark)';
                btn.style.border = '1px solid var(--border-color)';
                btn.style.color = 'var(--text-color)';
                btn.style.padding = '4px 8px';
                btn.style.borderRadius = '4px';
                btn.style.cursor = 'pointer';
                btn.style.marginTop = '6px';
                btn.style.width = '100%';
                
                wrap.appendChild(btn);
            } else if (s === 'execution.ready-for-alpha') {
                const hint = document.createElement('span');
                hint.className = 'substatus-hint';
                hint.textContent = '⟶ drag to advance';
                wrap.appendChild(hint);
            }

            // Exception buttons: Block / Review / Unblock / Resume
            const btnRow = document.createElement('div');
            btnRow.className = 'substatus-btn-row';
            btnRow.style.display = 'flex';
            btnRow.style.gap = '6px';
            btnRow.style.marginTop = '6px';

            // Common style helper for secondary buttons
            const styleSecondaryBtn = (b) => {
                b.style.background = 'transparent';
                b.style.border = '1px solid var(--border-color)';
                b.style.color = 'var(--text-muted)';
                b.style.padding = '3px 6px';
                b.style.borderRadius = '4px';
                b.style.cursor = 'pointer';
                b.style.fontSize = '11px';
                b.style.flex = '1';
            };

            if (s === 'blocked') {
                const unblockBtn = document.createElement('button');
                unblockBtn.className = 'substatus-btn substatus-btn-secondary system-button';
                unblockBtn.textContent = '↩ Unblock';
                unblockBtn.title = 'Remove blocked status — resume previous phase';
                unblockBtn.dataset.proposalId = cardData.proposal_id;
                unblockBtn.dataset.column = col;
                unblockBtn.dataset.next = 'execution.coding';  // sensible fallback
                unblockBtn.addEventListener('click', handleSubstatusAdvance);
                styleSecondaryBtn(unblockBtn);
                btnRow.appendChild(unblockBtn);
            } else if (s === 'review') {
                const resumeBtn = document.createElement('button');
                resumeBtn.className = 'substatus-btn substatus-btn-secondary system-button';
                resumeBtn.textContent = '↩ Resume';
                resumeBtn.title = 'Review done — return to active work';
                resumeBtn.dataset.proposalId = cardData.proposal_id;
                resumeBtn.dataset.column = col;
                resumeBtn.dataset.next = 'execution.coding';
                resumeBtn.addEventListener('click', handleSubstatusAdvance);
                styleSecondaryBtn(resumeBtn);
                btnRow.appendChild(resumeBtn);
            } else if (s !== 'execution.ready-for-alpha') {
                // Block + Review always available in active states
                const blockBtn = document.createElement('button');
                blockBtn.className = 'substatus-btn substatus-btn-danger system-button';
                blockBtn.textContent = '⚠ Block';
                blockBtn.title = 'Mark as blocked — waiting on external dependency';
                blockBtn.dataset.proposalId = cardData.proposal_id;
                blockBtn.dataset.column = col;
                blockBtn.dataset.next = 'blocked';
                blockBtn.addEventListener('click', handleSubstatusAdvance);
                styleSecondaryBtn(blockBtn);
                blockBtn.style.color = 'var(--lms-log-err)';

                const reviewBtn = document.createElement('button');
                reviewBtn.className = 'substatus-btn substatus-btn-secondary system-button';
                reviewBtn.textContent = '👁 Review';
                reviewBtn.title = 'Flag for human review before proceeding';
                reviewBtn.dataset.proposalId = cardData.proposal_id;
                reviewBtn.dataset.column = col;
                reviewBtn.dataset.next = 'review';
                reviewBtn.addEventListener('click', handleSubstatusAdvance);
                styleSecondaryBtn(reviewBtn);

                btnRow.appendChild(blockBtn);
                btnRow.appendChild(reviewBtn);
            }

            if (btnRow.children.length) wrap.appendChild(btnRow);
            return wrap;
        }

        function formatSubstatus(s) {
            const state = SUBSTATUS_MACHINE[s];
            return state ? state.label : s;
        }

        // Verdict badge for proposal/backlog column cards.
        // Maps the council verdict substatus → a prominent coloured pill
        // so the user knows at a glance whether to drag forward or rework.
        const VERDICT_CONFIG = {
            'approved':       { label: '✓ APPROVED',       color: '#4ad98a', tip: 'Council approved — drag to Beta Testing' },
            'auto-approved':  { label: '✓ AUTO-APPROVED',  color: '#4ab5d9', tip: 'Low severity — auto-approved, drag to Beta Testing' },
            'rejected':       { label: '✗ REJECTED',       color: '#d94a4a', tip: 'Council rejected — edit proposal and move back to Proposal to retry' },
            'queued_council': { label: '⏸ COUNCIL QUEUE', color: '#888888', tip: 'Waiting in line for the council lock' },
            'pending_council':{ label: '⏳ COUNCIL RUNNING',color: '#d9c44a', tip: 'Council is deliberating — check FastAPI terminal for progress' },
            'council_error':  { label: '⚠ ERROR',          color: '#c41e3a', tip: 'Council failed — check FastAPI terminal, then re-drag to Proposal' },
        };

        function buildVerdictBadge(substatus) {
            const cfg = VERDICT_CONFIG[substatus] || { label: substatus, color: '#666', tip: substatus };
            const wrap = document.createElement('div');
            wrap.className = 'kanban-verdict-wrap';
            const badge = document.createElement('span');
            badge.className = 'verdict-badge';
            badge.textContent = cfg.label;
            badge.title = cfg.tip + " (Click to view full Proposal & Verdict)";
            badge.style.setProperty('--verdict-color', cfg.color);
            badge.style.cursor = 'pointer';
            // Click badge to view the document!
            // Bind to 'wrap' as well, since clicking the padding around the text
            // hits the wrap, not the badge span.
            wrap.style.cursor = 'pointer';
            wrap.title = cfg.tip + " (Click to view full Proposal & Verdict)";
            
            const openDoc = (e) => {
                const cardEl = e.target.closest('.kanban-card');
                if (cardEl && cardEl.dataset.proposalId) {
                    e.stopPropagation();
                    viewDocument(cardEl.dataset.proposalId, 'proposal');
                }
            };
            
            badge.addEventListener('click', openDoc);
            wrap.addEventListener('click', openDoc);
            
            wrap.appendChild(badge);
            return wrap;
        }

        // Global drag state
        let draggedCard = null;
        let sourceColumn = null;

        function handleDragStart(e) {
            draggedCard = this;
            sourceColumn = this.closest('.kanban-column');
            this.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', this.dataset.proposalId);
        }

        function handleDragEnd(e) {
            if (draggedCard) {
                draggedCard.classList.remove('dragging');
            }
            draggedCard = null;
            sourceColumn = null;
            
            // Remove drag-over class from all columns
            document.querySelectorAll('.kanban-column').forEach(col => {
                col.classList.remove('drag-over');
            });
        }

        // Column drop handling
        function setupDropZone(column) {
            column.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                column.classList.add('drag-over');
            });

            column.addEventListener('dragleave', (e) => {
                if (!column.contains(e.relatedTarget)) {
                    column.classList.remove('drag-over');
                }
            });

            column.addEventListener('drop', async (e) => {
                e.preventDefault();
                column.classList.remove('drag-over');
                
                // Capture draggedCard locally before handleDragEnd nulls it
                const card = draggedCard;
                const srcCol = sourceColumn;
                
                if (!card) return;
                
                const proposalId = card.dataset.proposalId;
                const newColumnId = column.dataset.columnId;
                const oldColumnId = srcCol.dataset.columnId;

                // Don't allow same-column drops
                if (oldColumnId === newColumnId) {
                    hideError();
                    return;
                }

                card.classList.add('is-loading');

                try {
                    const response = await fetch(`${API_BASE}/api/workflow/transition`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            proposal_id: proposalId,
                            target_column: newColumnId
                        })
                    });

                    if (response.ok) {
                        hideError();
                        // Reload board on success
                        loadBoard();
                    } else {
                        // Handle errors
                        const errorData = await response.json().catch(() => ({}));
                        const detail = errorData.detail || `HTTP ${response.status}`;
                        
                        if (response.status === 404) {
                            showError(`Proposal ${proposalId} not found. Reloading board...`);
                            setTimeout(loadBoard, 2000);
                        } else {
                            showError(detail);
                            // Snap card back to original position
                            if (document.contains(card)) {
                                card.classList.remove('is-loading');
                            }
                        }
                    }
                } catch (err) {
                    showError(`Network error: ${err.message}`);
                    if (document.contains(card)) {
                        card.classList.remove('is-loading');
                    }
                }
            });
        }

        // Render board columns
        //
        // CRITICAL: cards must be appended as real DOM nodes (returned by
        // createCard) — NOT serialized through .outerHTML. createCard
        // attaches dragstart/dragend/click listeners directly on the
        // element via addEventListener, and those listeners are LOST when
        // the element is round-tripped through an HTML string. The dead
        // drag-and-drop bug we hunted on 2026-05-26 was caused by exactly
        // that. Build columns as DOM nodes, then appendChild each card.
        function renderBoard(cardsByColumn) {
            const board = document.getElementById('kanban-board');
            if (!board) return;

            // Clear with replaceChildren so any previously-attached
            // listeners on stale nodes get garbage-collected cleanly.
            board.replaceChildren();

            CANONICAL_COLUMNS.forEach(columnId => {
                const columnCards = cardsByColumn[columnId] || [];

                const colEl = document.createElement('div');
                colEl.className = 'kanban-column';
                colEl.dataset.columnId = columnId;

                const headerEl = document.createElement('div');
                headerEl.className = 'kanban-column-header';
                const COLUMN_DESCRIPTIONS = {
                    'backlog':    'Ideas & new proposals awaiting review',
                    'proposal':   'Under council review — severity-dispatched',
                    'beta testing': 'Active development — coding, debugging, testing',
                    'alpha polish': 'Hardening — UI/UX, performance, final prep',
                    'finalized':  'Complete — approved for release',
                    'deployed':   'Live in production',
                };

                const h3 = document.createElement('h3');
                h3.textContent = columnId;
                const countEl = document.createElement('span');
                countEl.className = 'kanban-column-count';
                countEl.textContent = String(columnCards.length);
                const descEl = document.createElement('p');
                descEl.className = 'kanban-column-desc';
                descEl.textContent = COLUMN_DESCRIPTIONS[columnId] || '';
                headerEl.appendChild(h3);
                headerEl.appendChild(countEl);
                headerEl.appendChild(descEl);

                const bodyEl = document.createElement('div');
                bodyEl.className = 'kanban-column-body';
                columnCards.forEach(card => bodyEl.appendChild(createCard(card)));

                colEl.appendChild(headerEl);
                colEl.appendChild(bodyEl);
                board.appendChild(colEl);

                setupDropZone(colEl);
            });

            // Substatus buttons are attached directly to DOM nodes inside
            // buildSubstatusWidget — no post-render wiring needed.
        }

        // Load board data from API.
        //
        // We only paint the "Loading..." placeholder on first paint (when the
        // board is empty). On auto-refresh ticks the previous render stays
        // visible until the new HTML replaces it in renderBoard(), eliminating
        // the every-30s flicker reported during smoke-test.
        async function loadBoard() {
            hideError();
            const board = document.getElementById('kanban-board');
            const isFirstPaint = board && !board.querySelector('.kanban-column');
            if (isFirstPaint) {
                board.innerHTML = '<p class="placeholder kanban-placeholder">Loading Kanban board...</p>';
            }

            try {
                const response = await fetch(`${API_BASE}/api/kanban/board`);
                
                if (!response.ok) {
                    throw new Error(`API error: ${response.status}`);
                }

                const data = await response.json();
                // data has {columns: [{name, cards}, ...], generated_at} format
                const cardsByColumn = Object.fromEntries((data.columns || []).map(c => [c.name, c.cards || []]));
                renderBoard(cardsByColumn);
            } catch (err) {
                showError(`Failed to load Kanban board: ${err.message}`);
                // Only swap the board to an error placeholder if it's empty.
                // If we already had cards, keep them visible behind the banner.
                if (board && !board.querySelector('.kanban-column')) {
                    board.innerHTML = '<p class="placeholder kanban-placeholder">Error loading board. Check console for details.</p>';
                }
            }
        }

        // Substatus change handler
        async function handleSubstatusChange(e) {
            // Legacy handler — kept as no-op since the dropdown is removed.
            // All substatus changes now flow through handleSubstatusAdvance.
        }

        async function handleSubstatusAdvance(e) {
            e.stopPropagation(); // don't open history drawer
            const btn = e.currentTarget;
            const proposalId = btn.dataset.proposalId;
            const nextSubstatus = btn.dataset.next;
            const currentColumn = btn.dataset.column || 'beta testing';

            btn.disabled = true;
            btn.style.opacity = '0.5';
            try {
                const response = await fetch(`${API_BASE}/api/workflow/transition`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        proposal_id: proposalId,
                        target_column: currentColumn,
                        target_substatus: nextSubstatus,
                        gate_passed: 1
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    showError(errorData.detail || 'Failed to advance substatus');
                    btn.disabled = false;
                    btn.style.opacity = '';
                } else {
                    hideError();
                    loadBoard();
                }
            } catch (err) {
                showError(`Network error: ${err.message}`);
                btn.disabled = false;
                btn.style.opacity = '';
            }
        }

        // History drawer
        const historyOverlay = document.createElement('div');
        historyOverlay.id = 'kanban-history-overlay';
        historyOverlay.innerHTML = `
            <div id="kanban-history-panel">
                <div id="kanban-history-header">
                    <h3>Transition History</h3>
                    <button id="kanban-history-close">&times;</button>
                </div>
                <div id="kanban-history-body"></div>
            </div>
        `;
        document.body.appendChild(historyOverlay);

        function showHistory(proposalId) {
            const body = document.getElementById('kanban-history-body');
            if (!body) return;

            body.innerHTML = '<p class="placeholder">Loading history...</p>';
            
            fetch(`${API_BASE}/api/workflow/state/${encodeURIComponent(proposalId)}?history_limit=10`)
                .then(r => r.ok ? r.json() : Promise.reject(r))
                .then(data => {
                    if (!body) return;
                    
                    const transitions = data.history || [];
                    let html = '';
                    
                    // Add tabs for Document viewing directly inside the history modal
                    html += `
                        <div style="margin-bottom: 15px; display: flex; gap: 10px; border-bottom: 1px solid var(--border-color); padding-bottom: 10px;">
                            <button class="system-button" onclick="window.Kanban_loadArtifactInline(this, '${proposalId}', 'proposal')" 
                                    style="background: none; border: 1px solid var(--border-color); color: var(--text-color); padding: 6px 12px; border-radius: 4px; cursor: pointer; transition: all 0.2s;">
                                Proposal & Verdict
                            </button>
                            <button class="system-button" onclick="window.Kanban_loadArtifactInline(this, '${proposalId}', 'beta_handoff')" 
                                    style="background: none; border: 1px solid var(--border-color); color: var(--text-color); padding: 6px 12px; border-radius: 4px; cursor: pointer; transition: all 0.2s;">
                                Beta Handoff
                            </button>
                            <button class="system-button" onclick="window.Kanban_loadArtifactInline(this, '${proposalId}', 'alpha_handoff')" 
                                    style="background: none; border: 1px solid var(--border-color); color: var(--text-color); padding: 6px 12px; border-radius: 4px; cursor: pointer; transition: all 0.2s;">
                                Alpha Handoff
                            </button>
                            <button class="system-button" onclick="window.Kanban_loadArtifactInline(this, '${proposalId}', 'final_audit')" 
                                    style="background: none; border: 1px solid var(--border-color); color: var(--text-color); padding: 6px 12px; border-radius: 4px; cursor: pointer; transition: all 0.2s;">
                                Final Audit
                            </button>
                        </div>
                        <div id="kanban-inline-doc" style="display: none; background: var(--bg-darker); padding: 15px; border-radius: 4px; border: 1px solid var(--border-color); margin-bottom: 20px; max-height: 400px; overflow-y: auto; font-family: monospace; white-space: pre-wrap; font-size: 13px;"></div>
                    `;

                    if (transitions.length === 0) {
                        html += '<p class="placeholder">No transition history found.</p>';
                    } else {
                        html += transitions.map((t, i) => {
                            const approver = t.approver || 'system';
                            const reason = t.reason ? ` (${escapeHtml(t.reason)})` : '';
                            const gatePassed = t.gate_passed !== undefined ? ` [gate:${t.gate_passed}]` : '';
                            return `
                                <div class="kanban-transition-item">
                                    <span class="label">${escapeHtml(t.from_column || 'N/A')}</span>
                                    <span class="arrow">→</span>
                                    <span class="value">${escapeHtml(t.to_column)}</span>
                                    <span class="timestamp">${escapeHtml(new Date(t.ts || 0).toLocaleString())}</span>
                                    <span class="note">${approver}${reason}${gatePassed}</span>
                                </div>
                            `;
                        }).join('');
                    }
                    body.innerHTML = html;
                })
                .catch(err => {
                    if (!body) return;
                    body.innerHTML = `<p style="color:red">Failed to load history: ${err.message}</p>`;
                });
            
            historyOverlay.classList.add('active');
        }

        function hideHistory() {
            historyOverlay.classList.remove('active');
        }

        // Close history drawer when clicking outside the panel
        historyOverlay.addEventListener('click', (e) => {
            if (e.target === historyOverlay) {
                hideHistory();
            }
        });

        // Close via Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && historyOverlay.classList.contains('active')) {
                hideHistory();
            }
        });

        // We use window.Kanban_loadArtifactInline instead of exposing it on Kanban,
        // because inline onclick attributes execute in global scope.
        window.Kanban_loadArtifactInline = async function(btnNode, proposalId, type) {
            const docContainer = document.getElementById('kanban-inline-doc');
            if (!docContainer) return;
            
            // Highlight active button
            const buttons = btnNode.parentElement.querySelectorAll('button');
            buttons.forEach(b => {
                b.style.background = 'none';
                b.style.borderColor = 'var(--border-color)';
            });
            btnNode.style.background = 'color-mix(in srgb, var(--accent-color) 20%, transparent)';
            btnNode.style.borderColor = 'var(--accent-color)';

            docContainer.style.display = 'block';
            docContainer.innerHTML = '<em>Loading ' + type + '...</em>';
            
            try {
                const response = await fetch(`${API_BASE}/api/workflow/artifact/${proposalId}?type=${type}`);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                const data = await response.json();
                docContainer.textContent = data.content || "Document is empty.";
            } catch (err) {
                docContainer.innerHTML = `<span style="color:var(--lms-log-err)">Not found or not generated yet: ${err.message}</span>`;
            }
        };

        window.Kanban_rerunCouncil = async function(proposalId, currentColumn) {
            if (!confirm(`Are you sure you want to manually re-trigger the ${currentColumn} council for ${proposalId}?`)) return;
            
            try {
                const response = await fetch(`${API_BASE}/api/workflow/transition`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        proposal_id: proposalId,
                        target_column: currentColumn,
                        approver: 'dashboard-rerun'
                    })
                });
                
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || data.error || `HTTP ${response.status}`);
                }
                
                alert(`✅ Council re-triggered successfully for ${proposalId}. Check API logs.`);
                loadBoard(); // refresh the board to show it's queued
            } catch (err) {
                alert(`❌ Failed to re-trigger council: ${err.message}`);
            }
        };

        // Re-inject the global wrapper into the html string 
        // to use the new global window function.
        window.Kanban = {
            loadBoard,
            showError,
            hideError,
            init: function() {
                // Initial load: render once so the board is populated when the
                // user first opens the Kanban subtab. Auto-refresh stays OFF
                // until the user actually navigates to the Kanban subtab
                // (wired via the document click handler above). This avoids a
                // background timer firing while the user is on Models / Bench /
                // any other tab on first load.
                loadBoard();
            },
            startAutoRefresh,
            stopAutoRefresh
        };
    })();

    // Initialize Kanban module - MUST be inside DOMContentLoaded since IIFE is inside it
    if (window.Kanban && typeof window.Kanban.init === 'function') {
        window.Kanban.init();
    } else {
        console.warn('Kanban module not yet loaded, retrying...');
        setTimeout(() => {
            if (window.Kanban && typeof window.Kanban.init === 'function') {
                window.Kanban.init();
            }
        }, 500);
    }

    // --- DevLog Tab Functionality ---
    const devlogGenerateBtn = document.getElementById('devlog-generate-btn');
    if (devlogGenerateBtn) {
        devlogGenerateBtn.addEventListener('click', async () => {
            const dateInput = document.getElementById('devlog-date');
            const output = document.getElementById('devlog-output');
            const date = dateInput ? dateInput.value : new Date().toISOString().split('T')[0];
            
            output.innerHTML = '<em>Generating draft...</em>';
            devlogGenerateBtn.disabled = true;
            
            try {
                const response = await fetch(`/api/devlog/draft?date_str=${date}`, { method: 'POST' });
                const data = await response.json();
                if (data.status === 'success') {
                    output.textContent = typeof data.draft === 'string' ? data.draft : JSON.stringify(data.draft, null, 2);
                } else {
                    output.innerHTML = `<span style="color:var(--lms-log-err)">Error: ${data.detail || 'Unknown error'}</span>`;
                }
            } catch (err) {
                output.innerHTML = `<span style="color:var(--lms-log-err)">Network error: ${err.message}</span>`;
            } finally {
                devlogGenerateBtn.disabled = false;
            }
        });
    }
});  // End of DOMContentLoaded
