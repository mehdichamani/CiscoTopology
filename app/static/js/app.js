/* ==========================================================================
   CiscoToolsV2 - Frontend Application Logic & Topology Engine
   ========================================================================== */

let visNetwork = null;
let eventSource = null;

let currentLang = 'fa';
let currentTheme = 'dark';

document.addEventListener('DOMContentLoaded', () => {
    initThemeAndLanguage();
    initTopology();
    loadSwitches();
    loadTaskSchedules();
});

// --- i18n & Theme Engine ---
function t(key) {
    if (typeof TRANSLATIONS !== 'undefined' && TRANSLATIONS[currentLang] && TRANSLATIONS[currentLang][key]) {
        return TRANSLATIONS[currentLang][key];
    }
    return key;
}

function initThemeAndLanguage() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        currentTheme = savedTheme;
    } else {
        currentTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    applyTheme(currentTheme);

    const savedLang = localStorage.getItem('lang');
    if (savedLang) {
        currentLang = savedLang;
    } else {
        const browserLang = (navigator.language || '').toLowerCase();
        currentLang = browserLang.startsWith('fa') ? 'fa' : 'en';
    }
    applyLanguage(currentLang);
}

function applyTheme(theme) {
    currentTheme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    document.body.setAttribute('data-theme', theme);
    const themeBtn = document.getElementById('theme-toggle-btn');
    if (themeBtn) {
        themeBtn.textContent = theme === 'light' ? '☀️' : '🌙';
    }

    if (visNetwork) {
        updateTopologyTheme();
    }
}

function toggleTheme() {
    const nextTheme = currentTheme === 'light' ? 'dark' : 'light';
    localStorage.setItem('theme', nextTheme);
    applyTheme(nextTheme);
}

function applyLanguage(lang) {
    currentLang = lang;
    document.documentElement.setAttribute('lang', lang);
    document.documentElement.setAttribute('dir', lang === 'fa' ? 'rtl' : 'ltr');
    const langBtn = document.getElementById('lang-toggle-btn');
    if (langBtn) {
        langBtn.textContent = lang === 'fa' ? '🌐 EN' : '🌐 FA';
    }
    updateUITranslations();
}

function toggleLanguage() {
    const nextLang = currentLang === 'fa' ? 'en' : 'fa';
    localStorage.setItem('lang', nextLang);
    applyLanguage(nextLang);
}

function updateUITranslations() {
    // Text content i18n
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (key && t(key)) {
            el.textContent = t(key);
        }
    });

    // Attribute titles i18n
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (key && t(key)) {
            el.setAttribute('title', t(key));
        }
    });

    // Re-render switch inventory table headers if present
    const headers = document.querySelectorAll('#switches-table th');
    if (headers.length >= 7) {
        headers[0].textContent = t('ipAddress');
        headers[1].textContent = t('hostname');
        headers[2].textContent = t('model');
        headers[3].textContent = t('serialNumber');
        headers[4].textContent = t('iosVersion');
        headers[5].textContent = t('status');
        headers[6].textContent = t('actions');
    }
}

// --- Task Schedule Management ---
function loadTaskSchedules() {
    fetch('/api/tasks')
        .then(res => res.json())
        .then(tasks => {
            if (!Array.isArray(tasks)) return;
            tasks.forEach(t => {
                const toggle = document.getElementById(`toggle-${t.task_id}`);
                const valEl = document.getElementById(`interval-val-${t.task_id}`);
                if (toggle) toggle.checked = Boolean(t.enabled);
                if (valEl) valEl.textContent = t.interval_minutes;
            });
        })
        .catch(err => console.error('Failed to load task schedules:', err));
}

function toggleTask(taskId, enabled) {
    fetch(`/api/tasks/${taskId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: enabled ? 1 : 0 })
    })
    .then(res => res.json())
    .then(data => {
        console.log(`Task ${taskId} toggle set to ${enabled}`);
    })
    .catch(err => alert('Failed to update task status: ' + err));
}

function editTaskInterval(taskId) {
    const valEl = document.getElementById(`interval-val-${taskId}`);
    if (!valEl) return;

    const currentVal = valEl.textContent.trim();
    const input = document.createElement('input');
    input.type = 'number';
    input.min = '1';
    input.value = currentVal;
    input.className = 'inline-edit-input';

    valEl.replaceWith(input);
    input.focus();
    input.select();

    function finishEdit() {
        const newVal = parseInt(input.value) || 1;
        const newSpan = document.createElement('span');
        newSpan.id = `interval-val-${taskId}`;
        newSpan.textContent = newVal;
        input.replaceWith(newSpan);

        if (newVal !== parseInt(currentVal)) {
            fetch(`/api/tasks/${taskId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ interval_minutes: newVal })
            })
            .then(res => res.json())
            .then(data => {
                console.log(`Task ${taskId} interval updated to ${newVal} min`);
            })
            .catch(err => alert('Failed to update interval: ' + err));
        }
    }

    input.addEventListener('blur', finishEdit, { once: true });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            input.blur();
        }
    });
}

// --- Tab Controller ---
function switchTab(tabId) {
    document.querySelectorAll('.category-tab').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
    
    const target = document.getElementById(tabId);
    if (target) target.classList.add('active');
    
    const btns = document.querySelectorAll('.category-tab');
    for (let b of btns) {
        if (b.getAttribute('onclick') && b.getAttribute('onclick').includes(tabId)) {
            b.classList.add('active');
            break;
        }
    }
    
    if (tabId === 'tab-topology' && visNetwork) {
        setTimeout(() => visNetwork.redraw(), 100);
    }
}

function reloadCurrentTab() {
    initTopology();
    loadSwitches();
}

// --- Vis.js Interactive Topology ---
function initTopology() {
    const container = document.getElementById('vis-topology-container');
    if (!container) return;

    fetch('/api/topology')
        .then(res => res.json())
        .then(data => {
            const rawNodes = data.nodes || [];
            const rawEdges = data.edges || [];

            // Apply DESIGN.md Editorial Styling to Vis.js Network Nodes & Edges
            const styledNodes = rawNodes.map(node => {
                const isSwitch = node.group === 'switch';
                return {
                    ...node,
                    shape: isSwitch ? 'dot' : 'diamond',
                    size: isSwitch ? 22 : 14,
                    color: {
                        background: isSwitch ? '#cc785c' : '#5db8a6', // Coral for Switch, Teal for Neighbor
                        border: isSwitch ? '#a9583e' : '#479b8a',
                        highlight: {
                            background: '#e8a55a',
                            border: '#cc785c'
                        }
                    },
                    font: {
                        color: currentTheme === 'dark' ? '#faf9f5' : '#141413',
                        face: 'Inter, Vazirmatn, sans-serif',
                        size: 13
                    }
                };
            });

            const styledEdges = rawEdges.map(edge => ({
                ...edge,
                color: {
                    color: currentTheme === 'dark' ? '#504d46' : '#c4bebe',
                    highlight: '#cc785c'
                },
                width: 2
            }));

            const graphData = {
                nodes: new vis.DataSet(styledNodes),
                edges: new vis.DataSet(styledEdges)
            };

            const options = {
                physics: {
                    solver: 'forceAtlas2Based',
                    forceAtlas2Based: {
                        gravitationalConstant: -60,
                        centralGravity: 0.01,
                        springLength: 120,
                        springConstant: 0.08
                    }
                },
                interaction: {
                    hover: true,
                    dragNodes: true,
                    zoomView: true
                }
            };

            visNetwork = new vis.Network(container, graphData, options);

            visNetwork.on("doubleClick", function (params) {
                if (params.nodes.length > 0) {
                    const nodeId = params.nodes[0];
                    openSwitchDetails(nodeId);
                }
            });
        })
        .catch(err => console.error('Failed to load topology:', err));
}

function updateTopologyTheme() {
    if (!visNetwork) return;
    const fontColor = currentTheme === 'dark' ? '#faf9f5' : '#141413';
    const edgeColor = currentTheme === 'dark' ? '#504d46' : '#c4bebe';

    visNetwork.setOptions({
        nodes: { font: { color: fontColor } },
        edges: { color: { color: edgeColor } }
    });
}

// --- Data Table Loaders ---
function loadSwitches() {
    const tbody = document.querySelector('#switches-table tbody');
    if (!tbody) return;

    fetch('/api/switches')
        .then(res => res.json())
        .then(data => {
            tbody.innerHTML = '';
            if (!data || data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px;" data-i18n="noSwitchesRecorded">${t('noSwitchesRecorded')}</td></tr>`;
                return;
            }
            data.forEach(s => {
                const tr = document.createElement('tr');
                const isOnline = (s.status || 'online').toLowerCase() === 'online';
                const badgeClass = isOnline ? 'badge-pill-success' : 'badge-pill-error';
                const badgeIcon = isOnline ? '🟢' : '🔴';

                tr.innerHTML = `
                    <td><code>${s.ip}</code></td>
                    <td><strong>${s.hostname || 'N/A'}</strong></td>
                    <td>${s.model || 'N/A'}</td>
                    <td><small>${s.serial_number || 'N/A'}</small></td>
                    <td><small>${s.ios_version || 'N/A'}</small></td>
                    <td><span class="badge-pill ${badgeClass}">${badgeIcon} ${t(isOnline ? 'online' : 'offline')}</span></td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="openSwitchDetails('${s.ip}')">${t('details')}</button>
                        <a href="/terminal/${s.ip}" target="_blank" class="btn btn-sm btn-primary" style="margin-inline-start:4px;">${t('terminal')}</a>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        });
}

// --- Switch Details Modal ---
function openSwitchDetails(switchId) {
    const modal = document.getElementById('switch-details-modal');
    const titleEl = document.getElementById('sw-modal-title');
    const subTitleEl = document.getElementById('sw-modal-subtitle');
    const bodyEl = document.getElementById('sw-modal-body');

    if (!modal || !bodyEl) return;

    modal.classList.add('active');
    titleEl.textContent = `${t('switchDetailsTitle')}: ${switchId}`;
    subTitleEl.textContent = t('loadingDetails');
    bodyEl.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-subtle);">${t('loadingDetails')}</div>`;

    fetch(`/api/switch/${encodeURIComponent(switchId)}`)
        .then(res => res.json())
        .then(resData => {
            if (resData.status === 'error') {
                bodyEl.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--color-error);">❌ ${resData.message}</div>`;
                return;
            }

            const sw = resData.switch || {};
            const vlans = resData.vlans || [];
            const links = resData.links || [];
            const devices = resData.devices || [];
            const isOnline = (sw.status || 'online').toLowerCase() === 'online';
            const badgeClass = isOnline ? 'badge-pill-success' : 'badge-pill-error';
            const badgeIcon = isOnline ? '🟢' : '🔴';

            titleEl.innerHTML = `🖥️ ${sw.hostname || sw.ip} <a href="/terminal/${sw.ip}" target="_blank" class="btn btn-sm btn-primary" style="margin-inline-start: 10px;">${t('openTerminalBtn')}</a>`;
            subTitleEl.textContent = `${t('ipAddress')}: ${sw.ip} | ${t('status')}: ${t(isOnline ? 'online' : 'offline')}`;

            let vlansHtml = vlans.length > 0 
                ? vlans.map(v => `<span class="vlan-chip" title="Ports: ${v.ports || 'None'}"><b>VLAN ${v.vlan_id}</b> (${v.vlan_name || 'N/A'}) - ${v.port_count} ports</span>`).join('') 
                : `<span style="color:var(--text-subtle);">${t('noVlanData')}</span>`;

            let linksHtml = links.length > 0
                ? `<table class="mini-table"><thead><tr><th>${t('localPort')}</th><th>${t('remoteSwitch')}</th><th>${t('remotePort')}</th><th>${t('protocol')}</th></tr></thead><tbody>` +
                  links.map(l => `<tr><td><code>${l.source_port}</code></td><td><strong>${l.target_switch}</strong></td><td><code>${l.target_port || '-'}</code></td><td><span class="badge-pill">${l.protocol}</span></td></tr>`).join('') +
                  `</tbody></table>`
                : `<span style="color:var(--text-subtle);">${t('noLinksData')}</span>`;

            let devicesHtml = devices.length > 0
                ? `<table class="mini-table"><thead><tr><th>${t('port')}</th><th>${t('vlan')}</th><th>${t('macAddress')}</th><th>${t('ipAddress')}</th><th>${t('vendor')}</th></tr></thead><tbody>` +
                  devices.map(d => `<tr><td><code>${d.port}</code></td><td>VLAN ${d.vlan}</td><td><code>${d.mac_address}</code></td><td><code>${d.ip_address || '-'}</code></td><td>${d.vendor || '-'}</td></tr>`).join('') +
                  `</tbody></table>`
                : `<span style="color:var(--text-subtle);">${t('noDevicesData')}</span>`;

            bodyEl.innerHTML = `
                <div class="sw-grid">
                    <div class="sw-info-block">
                        <div class="sw-prop"><span class="sw-prop-label">${t('ipAddress')}:</span> <code>${sw.ip}</code></div>
                        <div class="sw-prop"><span class="sw-prop-label">${t('hostname')}:</span> <strong>${sw.hostname || 'N/A'}</strong></div>
                        <div class="sw-prop"><span class="sw-prop-label">${t('model')}:</span> ${sw.model || 'N/A'}</div>
                    </div>
                    <div class="sw-info-block">
                        <div class="sw-prop"><span class="sw-prop-label">${t('serialNumber')}:</span> <small>${sw.serial_number || 'N/A'}</small></div>
                        <div class="sw-prop"><span class="sw-prop-label">${t('iosVersion')}:</span> <small>${sw.ios_version || 'N/A'}</small></div>
                        <div class="sw-prop"><span class="sw-prop-label">${t('status')}:</span> <span class="badge-pill ${badgeClass}">${badgeIcon} ${t(isOnline ? 'online' : 'offline')}</span></div>
                    </div>
                </div>

                <div class="sw-section-card">
                    <h4>📊 ${t('configuredVlans')} (${vlans.length})</h4>
                    <div class="vlan-chips-wrapper">${vlansHtml}</div>
                </div>

                <div class="sw-section-card">
                    <h4>↔ ${t('cdpLinks')} (${links.length})</h4>
                    ${linksHtml}
                </div>

                <div class="sw-section-card">
                    <h4>🔌 ${t('connectedDevices')} (${devices.length})</h4>
                    ${devicesHtml}
                </div>
            `;
        })
        .catch(err => {
            bodyEl.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--color-error);">❌ ${err}</div>`;
        });
}

function closeSwitchDetailsModal() {
    const modal = document.getElementById('switch-details-modal');
    if (modal) modal.classList.remove('active');
}

// --- Floating Console Drawer Toggle ---
function toggleConsoleDrawer(forceOpen) {
    const drawer = document.getElementById('floating-console-drawer');
    if (!drawer) return;
    if (typeof forceOpen === 'boolean') {
        if (forceOpen) drawer.classList.add('active');
        else drawer.classList.remove('active');
    } else {
        drawer.classList.toggle('active');
    }
}

// --- Action Execution with Real-Time SSE Streaming ---
function runAction(actionName) {
    const terminal = document.getElementById('terminal-output');
    const status = document.getElementById('action-status');
    const trigger = document.getElementById('floating-console-trigger');

    toggleConsoleDrawer(true);
    if (trigger) trigger.classList.add('is-running');

    terminal.textContent = `>>> Executing ${actionName}...\n`;
    status.textContent = t('runningStatus');
    status.className = 'status-badge status-running';

    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource(`/api/stream-log/${actionName}`);

    eventSource.onmessage = (event) => {
        const line = event.data;
        if (line === '[PING]') return;

        if (line === '[FINISHED]') {
            eventSource.close();
            eventSource = null;
            status.textContent = t('completedStatus');
            status.className = 'status-badge status-completed';
            if (trigger) trigger.classList.remove('is-running');
            reloadCurrentTab();
            return;
        }

        terminal.textContent += line + '\n';
        terminal.scrollTop = terminal.scrollHeight;
    };

    eventSource.onerror = (err) => {
        console.error('SSE Error:', err);
        status.textContent = t('errorStatus');
        status.className = 'status-badge status-error';
        if (trigger) trigger.classList.remove('is-running');
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    };
}

function clearConsole() {
    document.getElementById('terminal-output').textContent = t('consoleCleared');
}

// --- Fullscreen Topology Toggle ---
function toggleTopologyFullscreen() {
    const pane = document.getElementById('tab-topology');
    if (!pane) return;

    pane.classList.toggle('is-fullscreen');
    const isFS = pane.classList.contains('is-fullscreen');

    if (isFS) {
        document.addEventListener('keydown', handleFullscreenEsc);
    } else {
        document.removeEventListener('keydown', handleFullscreenEsc);
    }

    if (visNetwork) {
        setTimeout(() => {
            visNetwork.redraw();
            visNetwork.fit();
        }, 150);
    }
}

function handleFullscreenEsc(e) {
    if (e.key === 'Escape') {
        const swModal = document.getElementById('switch-details-modal');
        if (swModal && swModal.classList.contains('active')) {
            closeSwitchDetailsModal();
            return;
        }
        const wizModal = document.getElementById('wizard-modal');
        if (wizModal && wizModal.classList.contains('active')) {
            closeWizardModal();
            return;
        }
        const pane = document.getElementById('tab-topology');
        if (pane && pane.classList.contains('is-fullscreen')) {
            toggleTopologyFullscreen();
        }
    }
}
document.addEventListener('keydown', handleFullscreenEsc);

// --- Setup Wizard ---
function openWizardModal() {
    document.getElementById('wizard-modal').classList.add('active');
}

function closeWizardModal() {
    document.getElementById('wizard-modal').classList.remove('active');
}

function saveSetup(event) {
    event.preventDefault();
    const payload = {
        subnet: document.getElementById('wiz-subnet').value,
        seed_ips: document.getElementById('wiz-seed').value,
        username: document.getElementById('wiz-user').value,
        password: document.getElementById('wiz-pass').value,
        device_type: document.getElementById('wiz-type').value
    };

    fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            closeWizardModal();
            runAction('scan');
        } else {
            alert('Error: ' + data.message);
        }
    })
    .catch(err => {
        alert('Failed to save settings: ' + err);
    });
}
