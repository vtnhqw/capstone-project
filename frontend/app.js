// State Management
let currentTab = 'dashboard';
let api_key = sessionStorage.getItem('gemini_api_key') || '';
let vaultPassword = '';
let activeModuleId = null;
let currentFlashcards = [];
let currentFlashcardIndex = 0;
let isFlipped = false;
let secureNotes = [];
let activeNoteTitle = '';
let mcpTools = [];

// Initialize Page
document.addEventListener('DOMContentLoaded', () => {
    updateApiStatusUI();
    loadDashboardData();
    loadMcpTools();
});

// Tab Router
function switchTab(tabId) {
    // Hide active tabs
    document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    
    // Show select tab
    document.getElementById(`tab-${tabId}`).classList.add('active');
    document.getElementById(`nav-${tabId}`).classList.add('active');
    
    currentTab = tabId;
    
    // Lazy loads based on tab context
    if (tabId === 'dashboard') {
        loadDashboardData();
    } else if (tabId === 'syllabus') {
        loadRoadmapTimeline();
    } else if (tabId === 'recall') {
        populateModuleDropdown();
    } else if (tabId === 'vault') {
        checkVaultState();
    }
}

// Gemini Key Manager
function openKeyModal() {
    document.getElementById('key-modal').classList.add('open');
    document.getElementById('gemini-key-input').value = api_key;
}

function closeKeyModal() {
    document.getElementById('key-modal').classList.remove('open');
}

function saveApiKey() {
    api_key = document.getElementById('gemini-key-input').value.trim();
    if (api_key) {
        sessionStorage.setItem('gemini_api_key', api_key);
    } else {
        sessionStorage.removeItem('gemini_api_key');
    }
    updateApiStatusUI();
    closeKeyModal();
    // Reload active context
    loadDashboardData();
}

function clearApiKey() {
    api_key = '';
    sessionStorage.removeItem('gemini_api_key');
    updateApiStatusUI();
    closeKeyModal();
    loadDashboardData();
}

function updateApiStatusUI() {
    const dot = document.getElementById('status-mode-dot');
    const txt = document.getElementById('status-mode-text');
    
    if (api_key) {
        dot.className = 'status-indicator online';
        txt.textContent = 'Live Gemini Active';
    } else {
        dot.className = 'status-indicator';
        txt.textContent = 'Local Simulation';
    }
}

// API Helper
async function apiCall(endpoint, method = 'GET', body = null) {
    const headers = { 'Content-Type': 'application/json' };
    const options = { method, headers };
    
    if (body) {
        // Automatically inject API key to requests
        if (api_key) body.api_key = api_key;
        options.body = JSON.stringify(body);
    } else if (api_key && method === 'POST') {
        options.body = JSON.stringify({ api_key });
    }
    
    try {
        const response = await fetch(endpoint, options);
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'API Call failed');
        }
        return await response.json();
    } catch (e) {
        console.error(`API Error on ${endpoint}:`, e);
        throw e;
    }
}

// --- TAB 1: DASHBOARD LOGIC ---
async function loadDashboardData() {
    try {
        // Load Metrics
        const progress = await apiCall('/api/progress');
        document.getElementById('stat-completed-modules').textContent = progress.completed_modules;
        document.getElementById('stat-total-hours').innerHTML = `${progress.total_hours} <small>hrs</small>`;
        document.getElementById('stat-average-score').textContent = `${progress.average_score}%`;
        
        // Load focus areas
        const weakContainer = document.getElementById('dash-weak-list');
        weakContainer.innerHTML = '';
        progress.weak_areas.forEach(area => {
            const item = document.createElement('div');
            item.className = 'weak-item';
            item.textContent = area;
            weakContainer.appendChild(item);
        });
        
        // Load Modules Summary
        const roadmap = await apiCall('/api/roadmap');
        document.getElementById('stat-total-modules').textContent = roadmap.modules.length;
        
        const summaryContainer = document.getElementById('dash-roadmap-list');
        summaryContainer.innerHTML = '';
        
        if (roadmap.modules.length === 0) {
            summaryContainer.innerHTML = '<div class="empty-state">No syllabus modules defined. Build a plan in "Syllabus Coach"!</div>';
            return;
        }
        
        roadmap.modules.forEach(m => {
            const card = document.createElement('div');
            card.className = `roadmap-summary-card ${m.status}`;
            
            const statusLabel = m.status.replace('_', ' ');
            card.innerHTML = `
                <div class="summary-card-header">
                    <h4>${m.title}</h4>
                    <span class="status-badge ${m.status}">${statusLabel}</span>
                </div>
                <p class="summary-card-desc">${m.description}</p>
            `;
            summaryContainer.appendChild(card);
        });
    } catch (e) {
        console.error('Failed to load dashboard data:', e);
    }
}

// Dashboard Quick Chat
async function sendChatMessage() {
    const input = document.getElementById('dash-chat-input');
    const msg = input.value.trim();
    if (!msg) return;
    
    appendMessage('user', msg);
    input.value = '';
    
    try {
        const res = await apiCall('/api/chat', 'POST', { message: msg });
        appendMessage('agent', res.reply);
    } catch (e) {
        appendMessage('system', 'Error: Failed to fetch tutor response.');
    }
}

function handleChatKey(e) {
    if (e.key === 'Enter') sendChatMessage();
}

function appendMessage(sender, text) {
    const container = document.getElementById('dash-chat-messages');
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}`;
    msgDiv.textContent = text;
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
}

// --- TAB 2: SYLLABUS LOGIC ---
async function loadRoadmapTimeline() {
    const timeline = document.getElementById('syllabus-roadmap-timeline');
    timeline.innerHTML = '<div class="loading-spinner">Loading timeline...</div>';
    
    try {
        const roadmap = await apiCall('/api/roadmap');
        timeline.innerHTML = '';
        
        if (roadmap.modules.length === 0) {
            timeline.innerHTML = '<div class="empty-state">No syllabus uploaded yet. Fill the left panel and click "Build Roadmap".</div>';
            return;
        }
        
        roadmap.modules.forEach(m => {
            const card = document.createElement('div');
            card.className = `roadmap-card ${m.status}`;
            
            const statusText = m.status.replace('_', ' ');
            const topicsHtml = m.topics.map(t => `<span class="topic-tag">${t}</span>`).join('');
            
            let actionBtnHtml = '';
            if (m.status !== 'completed') {
                actionBtnHtml = `<button class="complete-module-btn" onclick="completeRoadmapUnit(${m.id})">Mark Complete</button>`;
            }
            
            card.innerHTML = `
                <div class="card-header-row">
                    <div>
                        <h4>${m.title}</h4>
                        <div class="card-metadata">
                            <span>⏱️ ${m.hours} Hours</span>
                            <span>Status: ${statusText}</span>
                        </div>
                    </div>
                    ${actionBtnHtml}
                </div>
                <p class="summary-card-desc">${m.description}</p>
                <div class="card-topics-list">
                    ${topicsHtml}
                </div>
            `;
            timeline.appendChild(card);
        });
    } catch (e) {
        timeline.innerHTML = '<div class="empty-state">Failed to load roadmap timeline.</div>';
    }
}

async function generateSyllabusPlan() {
    const txtArea = document.getElementById('syllabus-text');
    const syllabusText = txtArea.value.trim();
    if (!syllabusText) return;
    
    const btn = document.querySelector('.run-btn');
    btn.classList.add('loading');
    
    try {
        const res = await apiCall('/api/roadmap', 'POST', { syllabus_text: syllabusText });
        
        // Show/hide PII banner
        const piiBanner = document.getElementById('pii-alert-banner');
        if (res.pii_sanitized) {
            piiBanner.style.display = 'block';
        } else {
            piiBanner.style.display = 'none';
        }
        
        await loadRoadmapTimeline();
    } catch (e) {
        alert('Failed to generate roadmap. Verify configuration.');
    } finally {
        btn.classList.remove('loading');
    }
}

async function completeRoadmapUnit(moduleId) {
    try {
        await apiCall(`/api/roadmap/complete/${moduleId}`, 'POST');
        loadRoadmapTimeline();
    } catch (e) {
        console.error('Failed to complete roadmap unit', e);
    }
}

// --- TAB 3: ACTIVE RECALL LOGIC ---
async function populateModuleDropdown() {
    const select = document.getElementById('quiz-module-select');
    select.innerHTML = '<option value="">-- Choose Module --</option>';
    
    try {
        const roadmap = await apiCall('/api/roadmap');
        roadmap.modules.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.title;
            select.appendChild(opt);
        });
        
        // Default to first module if any
        if (roadmap.modules.length > 0 && !activeModuleId) {
            select.value = roadmap.modules[0].id;
            loadQuizForModule();
        } else if (activeModuleId) {
            select.value = activeModuleId;
        }
    } catch (e) {
        console.error('Failed to populate modules select:', e);
    }
}

async function loadQuizForModule() {
    const select = document.getElementById('quiz-module-select');
    const modId = parseInt(select.value);
    if (!modId) return;
    
    activeModuleId = modId;
    
    // Reset flashcard state
    isFlipped = false;
    document.getElementById('flashcard-element').classList.remove('flipped');
    document.getElementById('evaluate-btn').disabled = true;
    document.getElementById('student-answer').value = '';
    document.getElementById('coach-results-state').style.display = 'none';
    document.getElementById('coach-empty-state').style.display = 'block';
    
    document.getElementById('card-question-text').textContent = 'Loading quiz cards...';
    document.getElementById('card-answer-text').textContent = '';
    
    try {
        const res = await apiCall(`/api/quizzes/module/${modId}`);
        currentFlashcards = res.flashcards || [];
        currentFlashcardIndex = 0;
        
        if (currentFlashcards.length === 0) {
            document.getElementById('card-question-text').textContent = 'No flashcards generated for this module.';
            return;
        }
        
        displayActiveFlashcard();
    } catch (e) {
        document.getElementById('card-question-text').textContent = 'Error loading flashcards.';
    }
}

function displayActiveFlashcard() {
    const card = currentFlashcards[currentFlashcardIndex];
    document.getElementById('card-question-text').textContent = card.question;
    document.getElementById('card-answer-text').textContent = card.answer;
    
    document.getElementById('evaluate-btn').disabled = false;
    
    // Reset flip
    isFlipped = false;
    document.getElementById('flashcard-element').classList.remove('flipped');
}

function flipCard() {
    isFlipped = !isFlipped;
    const el = document.getElementById('flashcard-element');
    if (isFlipped) {
        el.classList.add('flipped');
    } else {
        el.classList.remove('flipped');
    }
}

async function submitRecallAnswer() {
    const ansArea = document.getElementById('student-answer');
    const studentAnswer = ansArea.value.trim();
    if (!studentAnswer) return;
    
    const card = currentFlashcards[currentFlashcardIndex];
    const btn = document.getElementById('evaluate-btn');
    btn.classList.add('loading');
    
    try {
        const res = await apiCall('/api/quizzes/evaluate', 'POST', {
            quiz_id: card.id,
            user_answer: studentAnswer
        });
        
        // Render Evaluation Results
        document.getElementById('coach-empty-state').style.display = 'none';
        const resultPanel = document.getElementById('coach-results-state');
        resultPanel.style.display = 'flex';
        
        const scoreVal = res.score_out_of_5;
        const percent = scoreVal * 20;
        
        document.getElementById('coach-score-progress').style.setProperty('--percent', percent);
        document.getElementById('coach-score-value').textContent = `${scoreVal}/5`;
        document.getElementById('coach-explanation-text').textContent = res.explanation;
        document.getElementById('coach-spaced-rep-text').textContent = res.spaced_repetition;
        
        // Auto flip card to back to reveal exact correct answer comparison
        if (!isFlipped) flipCard();
        
    } catch (e) {
        alert('Failed to evaluate answer.');
    } finally {
        btn.classList.remove('loading');
    }
}

// --- TAB 4: VAULT (SECURITY) LOGIC ---
function checkVaultState() {
    const ind = document.getElementById('vault-status-indicator');
    if (vaultPassword) {
        // unlocked
        document.getElementById('vault-auth-view').style.display = 'none';
        document.getElementById('vault-notebook-view').style.display = 'grid';
        
        ind.className = 'lock-indicator unlocked';
        document.getElementById('vault-status-text').textContent = 'Vault Unlocked';
        
        loadNotesList();
    } else {
        // locked
        document.getElementById('vault-auth-view').style.display = 'block';
        document.getElementById('vault-notebook-view').style.display = 'none';
        
        ind.className = 'lock-indicator locked';
        document.getElementById('vault-status-text').textContent = 'Vault Locked';
    }
}

async function unlockVault() {
    const pwdInput = document.getElementById('vault-password-input');
    const pwd = pwdInput.value;
    if (!pwd) return;
    
    const errEl = document.getElementById('vault-auth-error');
    errEl.textContent = '';
    
    try {
        const res = await apiCall('/api/vault/verify', 'POST', { password: pwd });
        if (res.status === 'success') {
            vaultPassword = pwd;
            pwdInput.value = '';
            checkVaultState();
        }
    } catch (e) {
        errEl.textContent = 'Decryption failed. Incorrect password.';
    }
}

function lockVault() {
    vaultPassword = '';
    secureNotes = [];
    activeNoteTitle = '';
    
    document.getElementById('note-edit-title').value = '';
    document.getElementById('note-edit-content').value = '';
    
    checkVaultState();
}

async function loadNotesList() {
    const listContainer = document.getElementById('vault-notes-list');
    listContainer.innerHTML = '<div class="loading-spinner">Decrypting journals...</div>';
    
    try {
        const res = await apiCall('/api/vault/notes/load', 'POST', { password: vaultPassword });
        secureNotes = res.notes || [];
        listContainer.innerHTML = '';
        
        if (secureNotes.length === 0) {
            listContainer.innerHTML = '<div class="empty-state">No secure notes saved. Click "+" to create one.</div>';
            return;
        }
        
        secureNotes.forEach(note => {
            const item = document.createElement('div');
            item.className = `note-item ${activeNoteTitle === note.title ? 'active' : ''}`;
            item.onclick = () => selectNote(note);
            
            item.innerHTML = `
                <span>${note.title}</span>
                <button class="note-delete-btn" onclick="event.stopPropagation(); deleteNote('${note.title}')">&times;</button>
            `;
            listContainer.appendChild(item);
        });
    } catch (e) {
        listContainer.innerHTML = '<div class="empty-state">Error loading decrypted notes.</div>';
    }
}

function selectNote(note) {
    activeNoteTitle = note.title;
    document.getElementById('note-edit-title').value = note.title;
    document.getElementById('note-edit-content').value = note.content;
    
    // Highlight list selection
    document.querySelectorAll('.note-item').forEach(el => {
        el.classList.remove('active');
        if (el.querySelector('span').textContent === note.title) {
            el.classList.add('active');
        }
    });
}

function startNewNote() {
    activeNoteTitle = '';
    document.getElementById('note-edit-title').value = '';
    document.getElementById('note-edit-content').value = '';
    
    document.querySelectorAll('.note-item').forEach(el => el.classList.remove('active'));
}

async function saveActiveNote() {
    const title = document.getElementById('note-edit-title').value.trim();
    const content = document.getElementById('note-edit-content').value.trim();
    if (!title || !content || !vaultPassword) return;
    
    try {
        await apiCall('/api/vault/notes', 'POST', {
            title,
            content,
            password: vaultPassword
        });
        activeNoteTitle = title;
        loadNotesList();
    } catch (e) {
        alert('Failed to save encrypted note.');
    }
}

async function deleteNote(title) {
    if (!confirm(`Are you sure you want to delete '${title}'?`)) return;
    try {
        await fetch('/api/vault/notes/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, password: vaultPassword })
        });
        if (activeNoteTitle === title) {
            startNewNote();
        }
        loadNotesList();
    } catch (e) {
        alert('Failed to delete note.');
    }
}

// --- TAB 5: MCP TOOLS LOGIC ---
async function loadMcpTools() {
    const container = document.getElementById('mcp-schema-container');
    const select = document.getElementById('mcp-tool-select');
    
    try {
        mcpTools = await apiCall('/api/tools');
        container.innerHTML = '';
        select.innerHTML = '';
        
        mcpTools.forEach(tool => {
            // Schema card
            const card = document.createElement('div');
            card.className = 'mcp-tool-schema-card';
            card.innerHTML = `
                <h4>${tool.name}</h4>
                <p>${tool.description}</p>
                <div class="mcp-schema-code">Input Schema: ${JSON.stringify(tool.input_schema, null, 2)}</div>
            `;
            container.appendChild(card);
            
            // Select option
            const opt = document.createElement('option');
            opt.value = tool.name;
            opt.textContent = tool.name;
            select.appendChild(opt);
        });
        
        updateMcpArgsPlaceholder();
    } catch (e) {
        container.innerHTML = '<div class="empty-state">Failed to load MCP schemas.</div>';
    }
}

function updateMcpArgsPlaceholder() {
    const select = document.getElementById('mcp-tool-select');
    const toolName = select.value;
    const tool = mcpTools.find(t => t.name === toolName);
    
    if (tool && tool.input_schema) {
        const dummyArgs = {};
        const props = tool.input_schema.properties || {};
        
        for (let key in props) {
            if (props[key].type === 'string') {
                dummyArgs[key] = 'calculus' + (key === 'password' ? '123' : '');
            } else if (props[key].type === 'integer' || props[key].type === 'number') {
                dummyArgs[key] = 3;
            } else {
                dummyArgs[key] = '';
            }
        }
        
        document.getElementById('mcp-arguments').value = JSON.stringify(dummyArgs, null, 4);
    }
}

async function invokeMcpTool() {
    const select = document.getElementById('mcp-tool-select');
    const name = select.value;
    const argsStr = document.getElementById('mcp-arguments').value;
    
    const display = document.getElementById('mcp-output-display');
    display.textContent = 'Invoking MCP server tool over stdio/IPC...';
    
    try {
        const arguments = JSON.parse(argsStr);
        const res = await fetch('/api/tools/call', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tool_name: name, arguments })
        });
        const out = await res.json();
        display.textContent = JSON.stringify(out, null, 4);
    } catch (e) {
        display.textContent = `Execution Error: ${e.message}`;
    }
}
