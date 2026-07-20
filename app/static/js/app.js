/* ==========================================================================
   CiscoToolsV2 - Frontend Application & Vis.js Interactive Topology
   ========================================================================== */

let visNetwork = null;
let eventSource = null;

document.addEventListener('DOMContentLoaded', () => {
    initTopology();
    loadSwitches();
});

// --- Tab Controller ---
function switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
    
    const target = document.getElementById(tabId);
    if (target) target.classList.add('active');
    
    // Highlight matching tab button
    const btns = document.querySelectorAll('.tab-btn');
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
            const nodes = new vis.DataSet(data.nodes || []);
            const edges = new vis.DataSet(data.edges || []);

            const graphData = { nodes: nodes, edges: edges };
            const options = {
                physics: {
                    solver: 'forceAtlas2Based',
                    forceAtlas2Based: {
                        gravitationalConstant: -50,
                        centralGravity: 0.01,
                        springLength: 100,
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

// --- Data Table Loaders ---
function loadSwitches() {
    const tbody = document.querySelector('#switches-table tbody');
    if (!tbody) return;

    fetch('/api/switches')
        .then(res => res.json())
        .then(data => {
            tbody.innerHTML = '';
            if (!data || data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center">No switches recorded in database.</td></tr>`;
                return;
            }
            data.forEach(s => {
                const tr = document.createElement('tr');
                const isOnline = (s.status || 'online').toLowerCase() === 'online';
                const badgeClass = isOnline ? 'badge-green' : 'badge-red';
                const badgeIcon = isOnline ? '🟢' : '🔴';

                tr.innerHTML = `
                    <td><code>${s.ip}</code></td>
                    <td><strong>${s.hostname || 'N/A'}</strong></td>
                    <td>${s.model || 'N/A'}</td>
                    <td><small>${s.serial_number || 'N/A'}</small></td>
                    <td><small>${s.ios_version || 'N/A'}</small></td>
                    <td><span class="badge ${badgeClass}">${badgeIcon} ${s.status || 'online'}</span></td>
                    <td>
                        <button class="btn btn-sm btn-cyan" onclick="openSwitchDetails('${s.ip}')">🔍 Details</button>
                        <a href="/terminal/${s.ip}" target="_blank" class="btn btn-sm btn-purple" style="text-decoration:none; margin-left:4px;">📟 Terminal</a>
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
    titleEl.textContent = `🖥️ Switch: ${switchId}`;
    subTitleEl.textContent = 'Loading detailed device configuration...';
    bodyEl.innerHTML = '<div class="text-center text-muted" style="padding: 40px;">⏳ Querying switch data...</div>';

    fetch(`/api/switch/${encodeURIComponent(switchId)}`)
        .then(res => res.json())
        .then(resData => {
            if (resData.status === 'error') {
                bodyEl.innerHTML = `<div class="text-center text-red" style="padding: 20px;">❌ ${resData.message}</div>`;
                return;
            }

            const sw = resData.switch || {};
            const vlans = resData.vlans || [];
            const links = resData.links || [];
            const devices = resData.devices || [];
            const isOnline = (sw.status || 'online').toLowerCase() === 'online';
            const badgeClass = isOnline ? 'badge-green' : 'badge-red';
            const badgeIcon = isOnline ? '🟢' : '🔴';

            titleEl.innerHTML = `🖥️ ${sw.hostname || sw.ip} <a href="/terminal/${sw.ip}" target="_blank" class="btn btn-sm btn-purple" style="text-decoration:none; margin-left: 10px; font-weight:normal;">📟 Open Terminal</a>`;
            subTitleEl.textContent = `IP Address: ${sw.ip} | Status: ${sw.status || 'online'}`;

            let vlansHtml = vlans.length > 0 
                ? vlans.map(v => `<span class="vlan-chip" title="Ports: ${v.ports || 'None'}"><b>VLAN ${v.vlan_id}</b> (${v.vlan_name || 'N/A'}) - ${v.port_count} ports</span>`).join('') 
                : '<span class="text-muted">No VLAN data recorded</span>';

            let linksHtml = links.length > 0
                ? `<table class="mini-table"><thead><tr><th>Local Port</th><th>Remote Switch</th><th>Remote Port</th><th>Protocol</th></tr></thead><tbody>` +
                  links.map(l => `<tr><td><code>${l.source_port}</code></td><td><strong>${l.target_switch}</strong></td><td><code>${l.target_port || '-'}</code></td><td><span class="badge badge-purple">${l.protocol}</span></td></tr>`).join('') +
                  `</tbody></table>`
                : '<span class="text-muted">No neighbor links recorded</span>';

            let devicesHtml = devices.length > 0
                ? `<table class="mini-table"><thead><tr><th>Port</th><th>VLAN</th><th>MAC Address</th><th>IP</th><th>Vendor</th></tr></thead><tbody>` +
                  devices.map(d => `<tr><td><code>${d.port}</code></td><td>VLAN ${d.vlan}</td><td><code>${d.mac_address}</code></td><td><code>${d.ip_address || '-'}</code></td><td>${d.vendor || '-'}</td></tr>`).join('') +
                  `</tbody></table>`
                : '<span class="text-muted">No connected edge devices recorded</span>';

            bodyEl.innerHTML = `
                <div class="sw-details-grid">
                    <div class="sw-info-card">
                        <div class="sw-prop"><span>IP Address:</span> <code>${sw.ip}</code></div>
                        <div class="sw-prop"><span>Hostname:</span> <strong>${sw.hostname || 'N/A'}</strong></div>
                        <div class="sw-prop"><span>Model:</span> ${sw.model || 'N/A'}</div>
                    </div>
                    <div class="sw-info-card">
                        <div class="sw-prop"><span>Serial Number:</span> <small>${sw.serial_number || 'N/A'}</small></div>
                        <div class="sw-prop"><span>IOS Version:</span> <small>${sw.ios_version || 'N/A'}</small></div>
                        <div class="sw-prop"><span>Status:</span> <span class="badge ${badgeClass}">${badgeIcon} ${sw.status || 'online'}</span></div>
                    </div>
                </div>

                <div class="sw-section">
                    <h4>📊 Configured VLANs (${vlans.length})</h4>
                    <div class="vlan-chips-container">${vlansHtml}</div>
                </div>

                <div class="sw-section">
                    <h4>↔ CDP Inter-Switch Links (${links.length})</h4>
                    ${linksHtml}
                </div>

                <div class="sw-section">
                    <h4>🔌 Connected Edge Devices (${devices.length})</h4>
                    ${devicesHtml}
                </div>
            `;
        })
        .catch(err => {
            bodyEl.innerHTML = `<div class="text-center text-red" style="padding: 20px;">❌ Failed to load switch details: ${err}</div>`;
        });
}

function closeSwitchDetailsModal() {
    const modal = document.getElementById('switch-details-modal');
    if (modal) modal.classList.remove('active');
}

// --- Action Execution with Real-Time Terminal Streaming ---
function runAction(actionName) {
    const terminal = document.getElementById('terminal-output');
    const status = document.getElementById('action-status');

    terminal.textContent = `>>> Executing ${actionName}...\n`;
    status.textContent = 'Running...';
    status.className = 'status-running';

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
            status.textContent = 'Completed';
            status.className = 'status-idle';
            reloadCurrentTab();
            return;
        }

        terminal.textContent += line + '\n';
        terminal.scrollTop = terminal.scrollHeight;
    };

    eventSource.onerror = (err) => {
        console.error('SSE Error:', err);
        status.textContent = 'Error';
        eventSource.close();
        eventSource = null;
    };
}

function clearConsole() {
    document.getElementById('terminal-output').textContent = 'Console cleared.';
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
