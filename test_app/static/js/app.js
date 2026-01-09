/**
 * Stageflow Test App - Frontend Application
 */

class StageflowApp {
    constructor() {
        this.socket = null;
        this.currentPipeline = 'simple';
        this.dagData = null;
        this.nodeStates = {};
        this.isProcessing = false;
        this.outputsContainer = null;
        this.outputEntryKeys = new Set();
        this.currentRunId = null;
        this.pipelineInfo = {};
        this.helpModal = null;
        this.modalBackdrop = null;
        this.modalTitleEl = null;
        this.modalDescriptionEl = null;
        this.modalInstructionsEl = null;

        this.init();
    }

    init() {
        this.outputsContainer = document.getElementById('outputs-container');
        this.pipelineInfo = this.getPipelineInfo();
        this.initSocket();
        this.initEventListeners();
        this.initResizers();
        this.initHelpModal();
        this.loadPipelineDAG();
        this.updateHelpContent();
    }

    // Socket.IO connection
    initSocket() {
        this.socket = io();

        this.socket.on('connect', () => {
            this.log('info', 'Connected to server');
        });

        this.socket.on('disconnect', () => {
            this.log('warning', 'Disconnected from server');
        });

        this.socket.on('pipeline_event', (event) => {
            this.handlePipelineEvent(event);
        });

        this.socket.on('pipeline_result', (result) => {
            this.handlePipelineResult(result);
        });
    }

    // Event listeners
    initEventListeners() {
        // Pipeline selector
        document.getElementById('pipeline-select').addEventListener('change', (e) => {
            this.currentPipeline = e.target.value;
            this.loadPipelineDAG();
            this.updateHelpContent();
            this.log('info', `Switched to pipeline: ${e.target.value}`);
        });

        // Send button
        document.getElementById('send-btn').addEventListener('click', () => {
            this.sendMessage();
        });

        // Enter key in textarea
        document.getElementById('chat-input').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Escape key to close help modal
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.helpModal && !this.helpModal.classList.contains('hidden')) {
                this.closeHelpModal();
            }
        });

        // Clear buttons
        document.getElementById('clear-logs').addEventListener('click', () => {
            this.clearLogs();
        });

        document.getElementById('clear-chat').addEventListener('click', () => {
            this.clearChat();
        });

        const clearOutputsBtn = document.getElementById('clear-outputs');
        if (clearOutputsBtn) {
            clearOutputsBtn.addEventListener('click', () => {
                this.clearOutputs(true);
            });
        }

        const clearAllBtn = document.getElementById('clear-all');
        if (clearAllBtn) {
            clearAllBtn.addEventListener('click', () => {
                this.clearAllPanels();
            });
        }
    }

    // Resizable panels
    initResizers() {
        // Vertical resizer (between left and right panels)
        this.initVerticalResizer();
        // Horizontal resizers between stacked panels
        this.initHorizontalResizer(
            'resizer-toggle-dag',
            document.getElementById('toggle-panel'),
            document.getElementById('dag-panel')
        );
        this.initHorizontalResizer(
            'resizer-dag-outputs',
            document.getElementById('dag-panel'),
            document.getElementById('outputs-panel')
        );
        this.initHorizontalResizer(
            'resizer-outputs-obs',
            document.getElementById('outputs-panel'),
            document.getElementById('observability-panel')
        );
    }

    initHelpModal() {
        this.helpModal = document.getElementById('pipeline-modal');
        this.modalBackdrop = document.getElementById('modal-backdrop');
        this.modalTitleEl = document.getElementById('modal-title');
        this.modalDescriptionEl = document.getElementById('modal-description');
        this.modalInstructionsEl = document.getElementById('modal-instructions-text');

        const helpBtn = document.getElementById('help-btn');
        const closeBtn = document.getElementById('modal-close');

        if (helpBtn) {
            helpBtn.addEventListener('click', () => this.openHelpModal());
        }
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.closeHelpModal());
        }
        if (this.modalBackdrop) {
            this.modalBackdrop.addEventListener('click', () => this.closeHelpModal());
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.helpModal && !this.helpModal.classList.contains('hidden')) {
                this.closeHelpModal();
            }
        });
    }

    getPipelineInfo() {
        const el = document.getElementById('pipeline-data');
        if (!el) {
            return {};
        }

        try {
            const text = (el.textContent || el.innerText || '{}').trim();
            return text ? JSON.parse(text) : {};
        } catch (error) {
            console.warn('Failed to parse pipeline metadata', error);
            return {};
        }
    }

    

    initVerticalResizer() {
        const resizer = document.getElementById('resizer-main');
        const leftPanel = document.querySelector('.left-panel');
        const chatPanel = document.getElementById('chat-panel');

        let isResizing = false;
        let startX = 0;
        let startLeftWidth = 0;
        let startChatWidth = 0;

        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            startX = e.clientX;
            startLeftWidth = leftPanel.offsetWidth;
            startChatWidth = chatPanel.offsetWidth;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;

            const dx = e.clientX - startX;
            const newLeftWidth = startLeftWidth + dx;
            const newChatWidth = startChatWidth - dx;

            if (newLeftWidth > 300 && newChatWidth > 280) {
                leftPanel.style.flex = 'none';
                leftPanel.style.width = `${newLeftWidth}px`;
                chatPanel.style.width = `${newChatWidth}px`;
            }
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
        });
    }

    initHorizontalResizer(resizerId, topPanel, bottomPanel) {
        const resizer = document.getElementById(resizerId);
        if (!resizer || !topPanel || !bottomPanel) {
            return;
        }

        let isResizing = false;
        let startY = 0;
        let startTopHeight = 0;
        let startBottomHeight = 0;

        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            startY = e.clientY;
            startTopHeight = topPanel.offsetHeight;
            startBottomHeight = bottomPanel.offsetHeight;
            document.body.style.cursor = 'row-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;

            const dy = e.clientY - startY;
            const newTopHeight = startTopHeight + dy;
            const newBottomHeight = startBottomHeight - dy;

            if (newTopHeight > 100 && newBottomHeight > 100) {
                topPanel.style.flex = 'none';
                topPanel.style.height = `${newTopHeight}px`;
                bottomPanel.style.flex = 'none';
                bottomPanel.style.height = `${newBottomHeight}px`;
            }
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
        });
    }

    // Load pipeline DAG
    async loadPipelineDAG() {
        try {
            const response = await fetch(`/api/pipelines/${this.currentPipeline}/dag`);
            this.dagData = await response.json();
            this.nodeStates = {};
            this.renderDAG();
        } catch (error) {
            this.log('error', `Failed to load DAG: ${error.message}`);
        }
    }

    // Render DAG visualization
    renderDAG() {
        const svg = document.getElementById('dag-svg');
        const container = document.getElementById('dag-container');

        if (!this.dagData || !this.dagData.nodes.length) {
            svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle" fill="#8b949e">No stages in pipeline</text>';
            return;
        }

        const nodes = this.dagData.nodes;
        const edges = this.dagData.edges;

        // Calculate layout using topological sort
        const layout = this.calculateLayout(nodes, edges);

        // Get container dimensions
        const width = container.offsetWidth || 500;
        const height = container.offsetHeight || 300;

        // Calculate node positions
        const nodeWidth = 100;
        const nodeHeight = 36;
        const levelGap = 140;
        const nodeGap = 60;

        // Center the DAG
        const maxLevel = Math.max(...Object.values(layout.levels));
        const dagWidth = (maxLevel + 1) * levelGap;
        const offsetX = (width - dagWidth) / 2 + nodeWidth / 2;

        // Calculate vertical positions for each level
        const levelNodes = {};
        nodes.forEach(node => {
            const level = layout.levels[node.id];
            if (!levelNodes[level]) levelNodes[level] = [];
            levelNodes[level].push(node);
        });

        const nodePositions = {};
        Object.entries(levelNodes).forEach(([level, levelNodeList]) => {
            const levelHeight = levelNodeList.length * nodeGap;
            const startY = (height - levelHeight) / 2 + nodeGap / 2;

            levelNodeList.forEach((node, index) => {
                nodePositions[node.id] = {
                    x: offsetX + parseInt(level) * levelGap,
                    y: startY + index * nodeGap,
                };
            });
        });

        // Build SVG
        let svgContent = `
            <defs>
                <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                    <polygon points="0 0, 10 3.5, 0 7" fill="#30363d"/>
                </marker>
            </defs>
        `;

        // Draw edges
        edges.forEach(edge => {
            const source = nodePositions[edge.source];
            const target = nodePositions[edge.target];
            if (source && target) {
                const edgeClass = this.getEdgeClass(edge.source, edge.target);
                svgContent += `
                    <path class="dag-edge ${edgeClass}" 
                          d="M ${source.x + nodeWidth/2} ${source.y} 
                             C ${source.x + nodeWidth/2 + 50} ${source.y},
                               ${target.x - nodeWidth/2 - 50} ${target.y},
                               ${target.x - nodeWidth/2} ${target.y}"
                          data-source="${edge.source}" data-target="${edge.target}"/>
                `;
            }
        });

        // Draw nodes
        nodes.forEach(node => {
            const pos = nodePositions[node.id];
            const state = this.nodeStates[node.id] || 'idle';
            const kindClass = node.kind || 'transform';

            svgContent += `
                <g class="dag-node ${kindClass} ${state}" data-node="${node.id}" transform="translate(${pos.x - nodeWidth/2}, ${pos.y - nodeHeight/2})">
                    <rect width="${nodeWidth}" height="${nodeHeight}"/>
                    <text x="${nodeWidth/2}" y="${nodeHeight/2}">${node.label}</text>
                </g>
            `;
        });

        svg.innerHTML = svgContent;
    }

    calculateLayout(nodes, edges) {
        // Build adjacency list
        const adj = {};
        const inDegree = {};
        nodes.forEach(n => {
            adj[n.id] = [];
            inDegree[n.id] = 0;
        });
        edges.forEach(e => {
            adj[e.source].push(e.target);
            inDegree[e.target]++;
        });

        // Topological sort to assign levels
        const levels = {};
        const queue = [];
        nodes.forEach(n => {
            if (inDegree[n.id] === 0) {
                queue.push(n.id);
                levels[n.id] = 0;
            }
        });

        while (queue.length > 0) {
            const node = queue.shift();
            adj[node].forEach(child => {
                levels[child] = Math.max(levels[child] || 0, levels[node] + 1);
                inDegree[child]--;
                if (inDegree[child] === 0) {
                    queue.push(child);
                }
            });
        }

        return { levels };
    }

    getEdgeClass(source, target) {
        const sourceState = this.nodeStates[source];
        const targetState = this.nodeStates[target];
        if (sourceState === 'completed' && targetState === 'active') {
            return 'active';
        }
        return '';
    }

    updateNodeState(nodeName, state) {
        this.nodeStates[nodeName] = state;
        this.renderDAG();
    }

    resetNodeStates() {
        this.nodeStates = {};
        this.renderDAG();
    }

    // Send message
    async sendMessage() {
        const input = document.getElementById('chat-input');
        const message = input.value.trim();

        if (!message || this.isProcessing) return;

        this.isProcessing = true;
        this.setProcessingState(true);

        // Add user message to chat
        this.addMessage('user', message);
        input.value = '';

        // Reset node states
        this.resetNodeStates();
        this.clearOutputs(true);

        try {
            // Use WebSocket for real-time updates
            this.socket.emit('run_pipeline', {
                pipeline_id: this.currentPipeline,
                message: message,
            });
        } catch (error) {
            this.log('error', `Failed to send message: ${error.message}`);
            this.setProcessingState(false);
        }
    }

    setProcessingState(processing) {
        const btn = document.getElementById('send-btn');
        const btnText = btn.querySelector('.btn-text');
        const btnLoading = btn.querySelector('.btn-loading');

        btn.disabled = processing;
        btnText.style.display = processing ? 'none' : 'inline';
        btnLoading.style.display = processing ? 'inline' : 'none';

        if (processing) {
            document.getElementById('dag-status').textContent = 'Running...';
        } else {
            document.getElementById('dag-status').textContent = '';
        }
    }

    // Handle pipeline events
    handlePipelineEvent(event) {
        const { type, data, timestamp, run_id } = event;

        if (type === 'pipeline.started') {
            this.currentRunId = run_id || Date.now().toString();
            this.clearOutputs(true);
        }

        // Log the event
        const eventType = type.split('.').pop();
        let logLevel = 'info';

        if (type.includes('.started')) {
            logLevel = 'info';
        } else if (type.includes('.completed')) {
            logLevel = 'success';
        } else if (type.includes('.failed')) {
            logLevel = 'error';
        } else if (type.includes('.cancelled')) {
            logLevel = 'warning';
        }

        this.log(logLevel, `${type}`, data);

        const stagePayload = data && data.data ? data.data : data;
        const actionResults = stagePayload && stagePayload.action_results ? stagePayload.action_results : (data && data.action_results ? data.action_results : null);

        // Update toggle panel from agent actions
        if (type.includes('stage.agent.completed') && actionResults) {
            actionResults.forEach(result => {
                if (result.action === 'TOGGLE_PANEL' && result.success && result.data) {
                    this.updateTogglePanel(result.data.panel_state);
                }
            });
        }

        // Capture stage outputs
        if (type.includes('stage.') && data && data.stage) {
            const stageName = data.stage;
            const status = data.status || (type.includes('.failed') ? 'fail' : 'ok');
            const payload = data.data ?? data;
            if (type.includes('.completed') || type.includes('.failed')) {
                this.addOutputEntry(stageName, status, payload, run_id);
            }
        }

        // Update DAG visualization
        if (type.includes('stage.')) {
            const parts = type.split('.');
            if (parts.length >= 3) {
                const stageName = parts[1];
                const stageEvent = parts[2];

                if (stageEvent === 'started') {
                    this.updateNodeState(stageName, 'active');
                } else if (stageEvent === 'completed') {
                    this.updateNodeState(stageName, 'completed');
                } else if (stageEvent === 'failed') {
                    this.updateNodeState(stageName, 'failed');
                }
            }
        }
    }

    // Update toggle panel state
    updateTogglePanel(state) {
        const toggleSwitch = document.getElementById('toggle-switch');
        const toggleStatus = document.getElementById('toggle-status');
        const toggleMessage = document.getElementById('toggle-message');

        if (state) {
            toggleSwitch.classList.add('on');
            toggleStatus.textContent = 'ON';
            toggleMessage.textContent = 'Panel is ON';
        } else {
            toggleSwitch.classList.remove('on');
            toggleStatus.textContent = 'OFF';
            toggleMessage.textContent = 'Panel is OFF';
        }

        this.log('success', `Toggle panel set to ${state ? 'ON' : 'OFF'}`);
    }

    // Handle pipeline result
    handlePipelineResult(result) {
        this.isProcessing = false;
        this.setProcessingState(false);

        if (result.response) {
            this.addMessage('assistant', result.response);
        } else if (result.errors && result.errors.length > 0) {
            this.addMessage('system', `Error: ${result.errors.join(', ')}`);
        } else {
            // Try to extract any useful output
            const results = result.results || {};
            let output = null;
            for (const stageName of ['output_guard', 'llm', 'summarize', 'echo']) {
                if (results[stageName] && results[stageName].data) {
                    output = results[stageName].data.response || 
                             results[stageName].data.text || 
                             results[stageName].data.echo ||
                             results[stageName].data.message;
                    if (output) break;
                }
            }
            if (output) {
                this.addMessage('assistant', output);
            } else {
                this.addMessage('system', 'Pipeline completed (no response generated)');
            }
        }

        this.log('success', 'Pipeline execution completed', result);

        const stageResults = result.results || {};
        Object.entries(stageResults).forEach(([stageName, stageResult]) => {
            this.addOutputEntry(
                stageName,
                stageResult.status || 'ok',
                stageResult.data || {},
                result.run_id,
                true
            );
        });
    }

    // Add message to chat
    addMessage(role, content) {
        const container = document.getElementById('messages-container');
        const msg = document.createElement('div');
        msg.className = `message ${role}`;
        msg.textContent = content;
        container.appendChild(msg);
        container.scrollTop = container.scrollHeight;
    }

    // Log to observability panel
    log(level, message, data = null) {
        const container = document.getElementById('logs-container');
        const entry = document.createElement('div');
        entry.className = `log-entry ${level}`;

        const time = new Date().toLocaleTimeString();
        let dataStr = '';
        if (data) {
            try {
                dataStr = JSON.stringify(data);
                if (dataStr.length > 100) {
                    dataStr = dataStr.substring(0, 100) + '...';
                }
            } catch (e) {
                dataStr = String(data);
            }
        }

        entry.innerHTML = `
            <span class="log-time">${time}</span>
            <span class="log-type">${level.toUpperCase()}</span>
            <span class="log-message">${message}${dataStr ? ' ' + dataStr : ''}</span>
        `;

        container.appendChild(entry);
        container.scrollTop = container.scrollHeight;
    }

    openHelpModal() {
        this.updateHelpContent();
        if (this.helpModal) {
            this.helpModal.classList.remove('hidden');
        }
    }

    closeHelpModal() {
        if (this.helpModal) {
            this.helpModal.classList.add('hidden');
        }
    }

    updateHelpContent() {
        if (!this.modalTitleEl || !this.modalDescriptionEl || !this.modalInstructionsEl) {
            return;
        }
        const meta = this.pipelineInfo[this.currentPipeline] || {};
        const name = meta.name || this.currentPipeline;
        const description = meta.description || 'No description available.';
        const instructions = meta.instructions || 'Interact with this pipeline to see it in action.';

        this.modalTitleEl.textContent = `${name} Pipeline`;
        this.modalDescriptionEl.textContent = description;
        this.modalInstructionsEl.textContent = instructions;
    }

    clearAllPanels() {
        this.clearChat();
        this.clearLogs();
        this.clearOutputs(true);
        this.updateTogglePanel(false);
        this.resetNodeStates();
    }

    clearChat() {
        const container = document.getElementById('messages-container');
        if (container) {
            container.innerHTML = '';
        }
        fetch('/api/clear-history', { method: 'POST' });
    }

    clearLogs() {
        const container = document.getElementById('logs-container');
        if (container) {
            container.innerHTML = '';
        }
    }

    clearOutputs(showPlaceholder = true) {
        this.outputEntryKeys.clear();
        if (!this.outputsContainer) return;
        this.outputsContainer.innerHTML = '';
        if (showPlaceholder) {
            const empty = document.createElement('div');
            empty.className = 'outputs-empty';
            empty.textContent = 'Run a pipeline to see outputs';
            this.outputsContainer.appendChild(empty);
        }
    }

    addOutputEntry(stage, status = 'ok', payload = {}, runId = null, force = false) {
        if (!this.outputsContainer) return;
        const keyPayload = JSON.stringify(payload || {});
        const signature = `${runId || this.currentRunId || 'local'}-${stage}-${status}-${keyPayload}`;
        if (!force && this.outputEntryKeys.has(signature)) {
            return;
        }
        this.outputEntryKeys.add(signature);

        const placeholder = this.outputsContainer.querySelector('.outputs-empty');
        if (placeholder) {
            this.outputsContainer.removeChild(placeholder);
        }

        const entry = document.createElement('div');
        entry.className = 'output-entry';

        const header = document.createElement('div');
        header.className = 'output-entry-header';

        const stageSpan = document.createElement('span');
        stageSpan.className = 'output-entry-stage';
        stageSpan.textContent = stage;

        const statusSpan = document.createElement('span');
        statusSpan.className = `output-entry-status ${status}`;
        statusSpan.textContent = status.toUpperCase();

        header.appendChild(stageSpan);
        header.appendChild(statusSpan);
        entry.appendChild(header);

        const body = document.createElement('pre');
        body.className = 'output-entry-body';
        const hasData = payload && Object.keys(payload).length > 0;
        body.textContent = hasData ? JSON.stringify(payload, null, 2) : 'No output data';

        entry.appendChild(body);
        this.outputsContainer.appendChild(entry);
        this.outputsContainer.scrollTop = this.outputsContainer.scrollHeight;
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new StageflowApp();
});
