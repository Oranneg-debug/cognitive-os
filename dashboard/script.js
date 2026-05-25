document.addEventListener('DOMContentLoaded', () => {
    const rolesList = document.getElementById('roles-list');
    const modelsList = document.getElementById('models-list');
    const configTitle = document.getElementById('config-title');
    const configPanel = document.getElementById('config-panel');
    const saveBtn = document.getElementById('save-btn');
    const testPromptInput = document.getElementById('test-prompt-input');
    const testBtn = document.getElementById('test-btn');
    const orchestrationSelect = document.getElementById('orchestration-select');
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
          desc: 'Creates a proposal and pushes a card to Backlog. The Kanban watcher takes it from there.',
          target: 'DevRouteManager' },
    ];

    let fullConfig = {};
    let availableModels = []; // New array to store the live model list
    let currentSelection = { type: null, key: null };
    let hasChanges = false;
    let systemLoadInterval = null;
    let recentOrchestrations = []; // Store recent runs

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
        modelsList.innerHTML = '';

        const allRoles = Object.keys(fullConfig.roles || {}).sort();
        
        const roleGroups = {
            "Dev Team": allRoles.filter(k => k.startsWith('dev_')),
            "Boardroom": allRoles.filter(k => k.startsWith('board_')),
            "Technical Meeting": allRoles.filter(k => k.startsWith('technical_')),
            "Design Meeting": allRoles.filter(k => k.startsWith('design_')),
            "Oracle Council": allRoles.filter(k => k.startsWith('oracle_')),
            "System & Base": allRoles.filter(k => k === 'simple' || k === 'standard' || k === 'vision' || k === 'nft_specialist'),
            "Core Flow Control": allRoles.filter(k => k === 'moderator' || k === 'brand_guard' || k === 'scribe'),
            "Other": allRoles.filter(k => !k.startsWith('dev_') && !k.startsWith('board_') && 
                                          !k.startsWith('technical_') && !k.startsWith('design_') && 
                                          !k.startsWith('oracle_') && 
                                          !['simple', 'standard', 'vision', 'nft_specialist', 'moderator', 'brand_guard', 'scribe'].includes(k))
        };

        // Clear and build the roles list with groups
        rolesList.innerHTML = '';
        for (const groupName in roleGroups) {
            const roles = roleGroups[groupName];
            if (roles.length > 0 || groupName !== 'Other') { // Always show non-Other groups
                const h2 = document.createElement('h2');
                h2.textContent = groupName;
                h2.dataset.group = groupName;
                rolesList.appendChild(h2);

                const ul = document.createElement('ul');
                ul.dataset.group = groupName;
                roles.forEach(key => {
                    const li = document.createElement('li');
                    const roleSpan = document.createElement('span');
                    roleSpan.textContent = key;
                    li.appendChild(roleSpan);
                    
                    // Add delete button
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
                rolesList.appendChild(ul);
                
                // Add "Add Role" button for this category
                const addBtn = document.createElement('button');
                addBtn.className = 'add-role-category-btn';
                addBtn.textContent = `+ Add ${groupName} Role`;
                addBtn.dataset.group = groupName;
                addBtn.onclick = () => handleAddRoleToCategory(groupName);
                rolesList.appendChild(addBtn);
            }
        }

        Object.keys(fullConfig.models || {}).sort().forEach(key => {
            const li = document.createElement('li');
            li.textContent = key;
            li.dataset.type = 'model';
            li.dataset.key = key;
            modelsList.appendChild(li);
        });
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
        resourcesSection.appendChild(createNumberInput('gpu_layers', data.gpu_layers, 'GPU Layers', layersHint));
        resourcesSection.appendChild(createNumberInput('n_parallel', data.n_parallel, 'Data Parallelism (n_parallel)', 'Concurrent request handling (1-16). Note: Tensor parallelism requires LM Studio SDK configuration'));
        resourcesSection.appendChild(createNumberInput('batch_size', data.batch_size || 512, 'Batch Size', 'Number of tokens to process per batch'));
        resourcesSection.appendChild(createSelect('k_cache_quant', data.k_cache_quant || 'q8_0', 'K-Cache Quantization', ['f16', 'q8_0', 'q4_0']));
        resourcesSection.appendChild(createSelect('v_cache_quant', data.v_cache_quant || 'q8_0', 'V-Cache Quantization', ['f16', 'q8_0', 'q4_0']));
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
        options.forEach(option => {
            const opt = document.createElement('option');
            opt.value = option;
            opt.textContent = option;
            if (option === value) {
                opt.selected = true;
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

    function createNumberInput(key, value, labelText, helpText) {
        const group = createFormGroup(labelText, helpText);
        const input = document.createElement('input');
        input.type = 'number';
        input.id = `config-${key}`;
        input.dataset.key = key;
        input.value = value || 0;
        input.addEventListener('input', handleInputChange);
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

    function updateRecentActivity() {
        const container = document.getElementById('home-recent');
        if (!container) return;
        
        if (recentOrchestrations.length > 0) {
            container.innerHTML = recentOrchestrations.slice(0, 5).map(item => `
                <div class="recent-item">
                    <span class="pattern">${item.pattern}</span>
                    <span class="time">${new Date(item.timestamp).toLocaleTimeString()}</span>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<p class="placeholder">No recent activity</p>';
        }
    }

    async function initializeHome() {
        await updateSystemLoad();
        await updateHomeLoadedModels();
        updateHomeEmptySeats();
        updateRecentActivity();
        
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

            panel.innerHTML = `<pre class="mermaid">${data.diagram}</pre>`;
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
        if (event.target.tagName === 'LI') {
            // Remove active class from all items
            document.querySelectorAll('.sidebar li').forEach(li => li.classList.remove('active'));
            // Add active class to clicked item
            event.target.classList.add('active');
            
            const { type, key } = event.target.dataset;
            renderConfigForm(type, key);
        }
    }

    function handleInputChange(event) {
        hasChanges = true;
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Configuration';
        saveBtn.classList.remove('success');

        const { key } = event.target.dataset;
        let value = event.target.value;

        // Convert numeric types
        if (event.target.type === 'number' || event.target.type === 'range') {
            value = Number(value);
        } else if (event.target.type === 'checkbox') {
            value = event.target.checked;
        }
        
        const { type, key: configKey } = currentSelection;
        if (type && configKey) {
            if (type === 'role') {
                fullConfig.roles[configKey][key] = value;
            } else {
                fullConfig.models[configKey][key] = value;
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

            hasChanges = false;
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saved Successfully!';
            saveBtn.classList.add('success');
            
            // Optionally, reload config to ensure sync, though not strictly necessary
            // await loadConfig();

        } catch (error) {
            console.error('Error saving config:', error);
            alert(`Error: ${error.message}`);
        }
    }

    /**
     * Run an orchestration against /process. `cmd` is "/simple", "/boardroom", …
     * or "auto" to let the Sentry Router decide.
     */
    async function runOrchestration(cmd, prompt, { compass = '' } = {}) {
        if (!prompt || !prompt.trim()) {
            throw new Error('Prompt is empty.');
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

    async function handleTestClick() {
        const prompt = testPromptInput.value;
        if (!prompt) {
            alert('Please enter a test prompt.');
            return;
        }
        const cmd = orchestrationSelect ? orchestrationSelect.value : '/simple';
        testBtn.disabled = true;
        testBtn.textContent = 'Running…';
        try {
            const result = await runOrchestration(cmd, prompt);
            alert(
                `Pattern: ${result.pattern || cmd}\n` +
                `Task: ${result.task_id || '—'}\n\n` +
                `${(result.response || '').slice(0, 1200)}` +
                ((result.response || '').length > 1200 ? '\n\n…(truncated, see terminal)' : '')
            );
        } catch (error) {
            console.error('Error running orchestration:', error);
            alert(`Error: ${error.message}`);
        } finally {
            testBtn.disabled = false;
            testBtn.textContent = 'Run Orchestration';
        }
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
            
            // Record this run for recent activity
            recentOrchestrations.unshift({
                pattern: result.pattern || cmd,
                timestamp: Date.now(),
                duration: ms,
                task_id: result.task_id
            });
            // Keep only last 10
            recentOrchestrations = recentOrchestrations.slice(0, 10);
            
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
        const sidebarHeaders = document.querySelectorAll('.sidebar h2');
        sidebarHeaders.forEach(header => {
            const list = header.nextElementSibling;
            if (list) {
                // Start with menus collapsed
                list.style.display = 'none';
                header.classList.add('collapsed');
            }

            header.addEventListener('click', () => {
                if (list) {
                    const isCollapsed = list.style.display === 'none';
                    list.style.display = isCollapsed ? 'block' : 'none';
                    header.classList.toggle('collapsed', !isCollapsed);
                }
            });
        });
    }

    rolesList.addEventListener('click', handleSidebarClick);
    modelsList.addEventListener('click', handleSidebarClick);
    saveBtn.addEventListener('click', handleSaveClick);
    testBtn.addEventListener('click', handleTestClick);
    tabs.forEach(tab => tab.addEventListener('click', handleTabClick));
    
    // Load Obsidian Preset button
    const loadPresetBtn = document.getElementById('load-preset-btn');
    if (loadPresetBtn) {
        loadPresetBtn.addEventListener('click', handleLoadObsidianPreset);
    }
    
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
    
    if (saveLogBtn) {
        saveLogBtn.addEventListener('click', () => {
            const outMeta = document.querySelector('.orch-meta');
            const outResp = document.querySelector('.orch-response');
            
            // Create a log object
            const logData = {
                timestamp: new Date().toISOString(),
                metadata: outMeta ? outMeta.innerText : '',
                response: outResp ? outResp.innerText : '',
                orchestrations: recentOrchestrations
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
    
    async function handleLoadObsidianPreset() {
        // This would integrate with Obsidian's API or a file picker
        // For now, we'll show a simple prompt
        const presetPath = prompt('Enter the path to your Obsidian chat preset file:');
        if (!presetPath) return;
        
        try {
            // In a real implementation, this would read the file and parse it
            // For now, we'll just show a success message
            alert('Obsidian preset loading functionality will be implemented with the Obsidian plugin integration.');
            
            // TODO: Implement actual preset loading logic
            // This would involve:
            // 1. Reading the preset file from Obsidian vault
            // 2. Parsing the preset format
            // 3. Applying settings to roles/models
            // 4. Saving the updated config
        } catch (error) {
            console.error('Error loading Obsidian preset:', error);
            alert('Failed to load preset: ' + error.message);
        }
    }
    
    async function handleAddRole() {
        handleAddRoleToCategory('Other');
    }
    
    async function handleAddRoleToCategory(groupName) {
        // Determine prefix based on group
        const prefixes = {
            'Dev Team': 'dev_',
            'Boardroom': 'board_',
            'Technical Meeting': 'technical_',
            'Design Meeting': 'design_',
            'Oracle Council': 'oracle_',
            'System & Base': '',
            'Core Flow Control': '',
            'Other': ''
        };
        
        const prefix = prefixes[groupName] || '';
        const roleName = prompt(`Enter the name for the new ${groupName} role:`, prefix);
        if (!roleName || !roleName.trim()) return;
        
        // Check if role already exists
        if (fullConfig.roles && fullConfig.roles[roleName]) {
            alert(`Role "${roleName}" already exists!`);
            return;
        }
        
        // Create new role with default values
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
            n_parallel: 1,
            kv_cache: 512,
            reasoning_enabled: false,
            compass_weight: 'MEDIUM WEIGHT'
        };
        
        // Add to config
        if (!fullConfig.roles) fullConfig.roles = {};
        fullConfig.roles[roleName] = newRole;
        
        // Save config
        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(fullConfig),
            });
            
            if (!response.ok) {
                throw new Error('Failed to save new role');
            }
            
            // Reload UI
            await loadConfig();
            
            // Select the new role
            const newRoleElement = document.querySelector(`li[data-key="${roleName}"][data-type="role"]`);
            if (newRoleElement) {
                newRoleElement.click();
            }
            
        } catch (error) {
            console.error('Error creating role:', error);
            alert(`Failed to create role: ${error.message}`);
            // Remove from local config if save failed
            delete fullConfig.roles[roleName];
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
                        n_parallel: 1,
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
                'N-Parallel': model.n_parallel || modelConfig.n_parallel || '1',
                'GPU Layers': modelConfig.gpu_layers || '-1',
                'K-Cache Quant': modelConfig.k_cache_quant || 'q8_0',
                'V-Cache Quant': modelConfig.v_cache_quant || 'q8_0',
                'Flash Attention': model.flash_attention !== undefined ? model.flash_attention : 'auto'
            };
            
            defaultsContainer.innerHTML = Object.entries(defaults).map(([label, value]) => `
                <div class="model-default-item">
                    <label>${label}</label>
                    <div class="value ${['Context Length', 'GPU Layers', 'N-Parallel', 'Batch Size'].includes(label) ? 'highlight' : ''}">
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
            setIfPresent('n_parallel', Number);
            // gpu_offload_ratio accepts 'max' | 'off' | float 0.0–1.0.
            // Pass strings through as-is so the backend sees the canonical
            // shape; numeric strings convert to float.
            setIfPresent('gpu_offload_ratio', v => {
                const s = String(v).trim().toLowerCase();
                if (s === 'max' || s === 'off') return s;
                const n = Number(s);
                return Number.isFinite(n) ? n : s;
            });
            setIfPresent('cache_type_k');
            setIfPresent('cache_type_v');
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

            // Substatus dropdown (only for beta testing cards)
            let substatusHtml = '';
            if (cardData.column_name === 'beta testing') {
                const currentSubstatus = cardData.substatus || 'planning';
                substatusHtml = `
                    <div class="kanban-card-substatus">
                        <label>Substatus</label>
                        <select class="beta-substatus" data-proposal-id="${cardData.proposal_id}" data-prev-value="${currentSubstatus}">
                            ${VALID_SUBSTATUSES.map(s => `<option value="${s}" ${currentSubstatus === s ? 'selected' : ''}>${formatSubstatus(s)}</option>`).join('')}
                        </select>
                    </div>
                `;
            }

            // Fall back to the proposal id when the title is missing —
            // happens for cards migrated from the legacy vault that lacked
            // a frontmatter `title` field. An untitled card is unreadable.
            const displayTitle = cardData.title || cardData.proposal_id;

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
                ${substatusHtml}
            `;

            // Drag events
            card.addEventListener('dragstart', handleDragStart);
            card.addEventListener('dragend', handleDragEnd);

            // Click to show history
            card.addEventListener('click', (e) => {
                if (!e.target.classList.contains('beta-substatus')) {
                    showHistory(cardData.proposal_id);
                }
            });

            return card;
        }

        function formatSubstatus(s) {
            const map = {
                'planning': 'Planning',
                'execution.coding': 'Coding',
                'execution.testing': 'Testing',
                'review': 'Review',
                'blocked': 'Blocked'
            };
            return map[s] || s;
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
            this.classList.remove('dragging');
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
                
                if (!draggedCard) return;
                
                const proposalId = draggedCard.dataset.proposalId;
                const newColumnId = column.dataset.columnId;
                const oldColumnId = sourceColumn.dataset.columnId;

                // Don't allow same-column drops
                if (oldColumnId === newColumnId) {
                    hideError();
                    return;
                }

                draggedCard.classList.add('is-loading');

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
                            draggedCard.classList.remove('is-loading');
                        }
                    }
                } catch (err) {
                    showError(`Network error: ${err.message}`);
                    draggedCard.classList.remove('is-loading');
                }
            });
        }

        // Render board columns
        function renderBoard(cardsByColumn) {
            const board = document.getElementById('kanban-board');
            if (!board) return;

            let html = '';
            CANONICAL_COLUMNS.forEach(columnId => {
                const columnCards = cardsByColumn[columnId] || [];
                html += `
                    <div class="kanban-column" data-column-id="${columnId}">
                        <div class="kanban-column-header">
                            <h3>${escapeHtml(columnId)}</h3>
                            <span class="kanban-column-count">${columnCards.length}</span>
                        </div>
                        <div class="kanban-column-body">
                            ${columnCards.map(card => createCard(card).outerHTML).join('')}
                        </div>
                    </div>
                `;
            });

            board.innerHTML = html;

            // Attach drop zones
            document.querySelectorAll('.kanban-column').forEach(column => {
                setupDropZone(column);
            });

            // Attach substatus change handlers
            document.querySelectorAll('.beta-substatus').forEach(select => {
                select.addEventListener('change', handleSubstatusChange);
            });
        }

        // Load board data from API
        async function loadBoard() {
            hideError();
            const board = document.getElementById('kanban-board');
            if (board) board.innerHTML = '<p class="placeholder kanban-placeholder">Loading Kanban board...</p>';

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
                const board = document.getElementById('kanban-board');
                if (board) board.innerHTML = '<p class="placeholder kanban-placeholder">Error loading board. Check console for details.</p>';
            }
        }

        // Substatus change handler
        async function handleSubstatusChange(e) {
            const select = e.target;
            const proposalId = select.dataset.proposalId;
            const newSubstatus = select.value;

            try {
                const response = await fetch(`${API_BASE}/api/workflow/transition`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        proposal_id: proposalId,
                        target_column: 'beta testing',
                        target_substatus: newSubstatus,
                        gate_passed: 1
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    showError(errorData.detail || `Failed to update substatus`);
                    select.value = select.dataset.prevValue;
                } else {
                    hideError();
                }
            } catch (err) {
                showError(`Network error: ${err.message}`);
                select.value = select.dataset.prevValue;
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
                    if (transitions.length === 0) {
                        body.innerHTML = '<p class="placeholder">No transition history found.</p>';
                    } else {
                            body.innerHTML = transitions.map((t, i) => {
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
                })
                .catch(err => {
                    if (!body) return;
                    body.innerHTML = `<p class="placeholder">Failed to load history: ${err.message || 'Unknown error'}</p>`;
                });
            
            historyOverlay.classList.add('active');
        }

        function hideHistory() {
            historyOverlay.classList.remove('active');
        }

        // Close history drawer when clicking close button
        document.getElementById('kanban-history-close').addEventListener('click', hideHistory);

        // Close on Esc key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && historyOverlay.classList.contains('active')) {
                hideHistory();
            }
        });

        // Close on overlay click
        historyOverlay.addEventListener('click', (e) => {
            if (e.target === historyOverlay) {
                hideHistory();
            }
        });

        // Close error banner button
        if (closeErrorBtn) {
            closeErrorBtn.addEventListener('click', hideError);
        }

        // Expose public API
        return {
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
    Kanban.init();
});  // End of DOMContentLoaded
