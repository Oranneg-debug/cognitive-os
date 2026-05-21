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
            "Dev Lifecycle": allRoles.filter(k => k.startsWith('dev_')),
            "Boardroom": allRoles.filter(k => k.startsWith('board_')),
            "Technical Meeting": allRoles.filter(k => k.startsWith('technical_')),
            "Design Meeting": allRoles.filter(k => k.startsWith('design_')),
            "System & Base": allRoles.filter(k => k === 'simple' || k === 'standard' || k === 'vision' || k === 'nft_specialist'),
            "Core Flow Control": allRoles.filter(k => k === 'moderator' || k === 'brand_guard' || k === 'scribe'),
        };

        // Clear and build the roles list with groups
        rolesList.innerHTML = '';
        for (const groupName in roleGroups) {
            const roles = roleGroups[groupName];
            if (roles.length > 0) {
                const h2 = document.createElement('h2');
                h2.textContent = groupName;
                rolesList.appendChild(h2);

                const ul = document.createElement('ul');
                roles.forEach(key => {
                    const li = document.createElement('li');
                    li.textContent = key;
                    li.dataset.type = 'role';
                    li.dataset.key = key;
                    ul.appendChild(li);
                });
                rolesList.appendChild(ul);
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

        if (type === 'role') {
            const isEnabled = data.enabled !== false; // default to true if missing
            configPanel.appendChild(createCheckbox('enabled', isEnabled, 'Enable this role'));
            
            // Use the live availableModels if we have them, otherwise fall back to whatever is in the config
            let modelOptions = availableModels.length > 0 ? availableModels : Object.keys(fullConfig.models || {});
            
            // Ensure the currently selected model is always in the list, even if LM Studio doesn't report it
            // (e.g., if LM Studio is closed but the config has a saved model)
            if (data.model && !modelOptions.includes(data.model)) {
                modelOptions = [data.model, ...modelOptions];
            }
            
            configPanel.appendChild(createSelect('model', data.model, 'Model', modelOptions));
            configPanel.appendChild(createTextArea('system_prompt', data.system_prompt, 'System Prompt'));
        }

        configPanel.appendChild(createSlider('temperature', data.temperature, 'Temperature', 0, 2, 0.1));
        configPanel.appendChild(createSlider('top_p', data.top_p, 'Top P', 0, 1, 0.05));
        configPanel.appendChild(createSlider('top_k', data.top_k, 'Top K', 0, 120, 1));
        configPanel.appendChild(createSlider('repeat_penalty', data.repeat_penalty, 'Repeat Penalty', 0, 2, 0.1));
        configPanel.appendChild(createSlider('min_p', data.min_p, 'Min P', 0, 1, 0.05));
        configPanel.appendChild(createNumberInput('max_tokens', data.max_tokens, 'Max Tokens'));
        configPanel.appendChild(createNumberInput('context_window', data.context_window, 'Context Window'));
        configPanel.appendChild(createNumberInput('gpu_layers', data.gpu_layers, 'GPU Layers (-1 for max)'));

        if (type === 'role') {
            const compassOptions = ["IGNORE", "LOW WEIGHT", "MEDIUM WEIGHT", "HIGH WEIGHT", "MAXIMUM WEIGHT"];
            configPanel.appendChild(createSelect('compass_weight', data.compass_weight, 'Compass Weight', compassOptions));
        }
    }

    // --- Form Element Creators ---

    function createFormGroup(labelText) {
        const group = document.createElement('div');
        group.className = 'form-group';
        const label = document.createElement('label');
        label.textContent = labelText;
        group.appendChild(label);
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
        slider.step = step;
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

    function createNumberInput(key, value, labelText) {
        const group = createFormGroup(labelText);
        const input = document.createElement('input');
        input.type = 'number';
        input.id = `config-${key}`;
        input.dataset.key = key;
        input.value = value || 0;
        input.addEventListener('input', handleInputChange);
        group.appendChild(input);
        return group;
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

        // Hide save button if not on config tab
        saveBtn.style.display = (tabName === 'config') ? 'block' : 'none';

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

        // Any other tab: stop the LM Studio log poller
        lmstudio.deactivate();

        // Load content for diagram tabs if they haven't been loaded yet
        if (tabName !== 'config' && !document.getElementById(tabName).hasAttribute('data-loaded')) {
            loadDiagram(tabName);
        }
    }
    
    async function loadDiagram(tabName) {
        const panel = document.getElementById(tabName);
        panel.innerHTML = '<p class="placeholder">Loading System Diagram...</p>';

        try {
            const response = await fetch(`/api/system/${tabName}`);
            if (!response.ok) {
                throw new Error(`Failed to load '${tabName}' diagram`);
            }
            const data = await response.json();

            panel.innerHTML = `<pre class="mermaid">${data.diagram}</pre>`;
            await mermaid.run({ nodes: panel.querySelectorAll('.mermaid') });
            panel.setAttribute('data-loaded', 'true');

        } catch (error) {
            console.error(`Error loading diagram for ${tabName}:`, error);
            panel.innerHTML = `<p class="placeholder">Error: Could not load diagram.</p>`;
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
                    tbody.innerHTML = loaded.map(inst => `
                        <tr>
                            <td>${fmt(inst.identifier)}</td>
                            <td>${fmt(inst.model_key)}</td>
                            <td>${fmt(inst.context_length)}</td>
                            <td>
                                <button class="lms-link-btn" data-unload="${encodeURIComponent(inst.identifier || '')}">unload</button>
                            </td>
                        </tr>
                    `).join('');
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
            return s
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
    });
});
