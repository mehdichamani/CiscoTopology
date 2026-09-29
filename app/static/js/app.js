/* ==========================================================================
   Simban - Frontend Application Logic & Switch Health Monitor
   ========================================================================== */

let eventSource = null;

let currentLang = 'fa';
let currentTheme = 'dark';

document.addEventListener('DOMContentLoaded', () => {
    initThemeAndLanguage();
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

    // Update switch table sort indicator icons and classes
    updateSortHeadersUI();
}

// --- Table Sorting & Switch State ---
let currentSwitchesData = [];
let currentSortColumn = null;
let currentSortDirection = 'asc'; // 'asc' or 'desc'

function ipToNumeric(ip) {
    if (!ip) return 0;
    const parts = ip.split('.').map(num => parseInt(num, 10));
    if (parts.length !== 4 || parts.some(isNaN)) return 0;
    return ((parts[0] << 24) >>> 0) + ((parts[1] << 16) >>> 0) + ((parts[2] << 8) >>> 0) + (parts[3] >>> 0);
}

function sortTable(columnKey) {
    if (currentSortColumn === columnKey) {
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortColumn = columnKey;
        currentSortDirection = 'asc';
    }

    applySwitchSorting();
    renderSwitchesTable(currentSwitchesData);
    updateSortHeadersUI();
}

function applySwitchSorting() {
    if (!currentSortColumn || !currentSwitchesData || currentSwitchesData.length === 0) return;

    currentSwitchesData.sort((a, b) => {
        let valA, valB;

        switch (currentSortColumn) {
            case 'ip':
                valA = ipToNumeric(a.ip);
                valB = ipToNumeric(b.ip);
                break;
            case 'hostname':
                valA = (a.hostname || '').toLowerCase();
                valB = (b.hostname || '').toLowerCase();
                break;
            case 'model':
                valA = (a.model || '').toLowerCase();
                valB = (b.model || '').toLowerCase();
                break;
            case 'status':
                valA = (a.status || '').toLowerCase();
                valB = (b.status || '').toLowerCase();
                break;
            case 'latency_ms':
                valA = a.latency_ms != null ? Number(a.latency_ms) : 999999;
                valB = b.latency_ms != null ? Number(b.latency_ms) : 999999;
                break;
            case 'ports_up':
                valA = a.ports_up != null ? Number(a.ports_up) : -1;
                valB = b.ports_up != null ? Number(b.ports_up) : -1;
                break;
            case 'last_seen':
                valA = a.last_seen || '';
                valB = b.last_seen || '';
                break;
            default:
                return 0;
        }

        let comparison = 0;
        if (typeof valA === 'string') {
            comparison = valA.localeCompare(valB);
        } else {
            comparison = valA < valB ? -1 : (valA > valB ? 1 : 0);
        }

        return currentSortDirection === 'asc' ? comparison : -comparison;
    });
}

function updateSortHeadersUI() {
    const headers = document.querySelectorAll('#switches-table th.sortable-th');
    headers.forEach(th => {
        const sortKey = th.getAttribute('data-sort-key');
        const iconSpan = th.querySelector('.sort-icon');
        
        th.classList.remove('sorted-asc', 'sorted-desc');
        if (sortKey === currentSortColumn) {
            th.classList.add(currentSortDirection === 'asc' ? 'sorted-asc' : 'sorted-desc');
            if (iconSpan) {
                iconSpan.textContent = currentSortDirection === 'asc' ? '▲' : '▼';
            }
        } else {
            if (iconSpan) {
                iconSpan.textContent = '↕';
            }
        }
    });
}

// --- Data Table Loaders ---
function loadSwitches() {
    fetch('/api/switches')
        .then(res => res.json())
        .then(data => {
            currentSwitchesData = Array.isArray(data) ? data : [];
            if (currentSortColumn) {
                applySwitchSorting();
            }
            renderSwitchesTable(currentSwitchesData);
        })
        .catch(err => console.error('Failed to load switches:', err));
}

function renderSwitchesTable(switches) {
    const tbody = document.querySelector('#switches-table tbody');
    if (!tbody) return;

    tbody.innerHTML = '';
    if (!switches || switches.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:24px;" data-i18n="noSwitchesRecorded">${t('noSwitchesRecorded')}</td></tr>`;
        return;
    }

    switches.forEach(s => {
        const tr = document.createElement('tr');
        const isOnline = (s.status || 'online').toLowerCase() === 'online';
        const badgeClass = isOnline ? 'badge-pill-success' : 'badge-pill-error';
        const badgeIcon = isOnline ? '🟢' : '🔴';

        const latencyText = isOnline && s.latency_ms > 0 ? `<code>${s.latency_ms} ms</code>` : `<span style="color:var(--text-subtle);">-</span>`;
        const portsText = s.ports_total > 0 ? `<strong>${s.ports_up}</strong> / ${s.ports_total}` : `<span style="color:var(--text-subtle);">N/A</span>`;
        const lastSeenText = s.last_seen ? `<small style="font-family:monospace;">${s.last_seen.replace('T', ' ').substring(0, 19)}</small>` : `<span style="color:var(--text-subtle);">-</span>`;

        tr.innerHTML = `
            <td data-label="${t('ipAddress')}"><code>${s.ip}</code></td>
            <td data-label="${t('hostname')}"><strong>${s.hostname || 'N/A'}</strong></td>
            <td data-label="${t('model')}">${s.model || 'N/A'}</td>
            <td data-label="${t('status')}"><span class="badge-pill ${badgeClass}">${badgeIcon} ${t(isOnline ? 'online' : 'offline')}</span></td>
            <td data-label="${t('latency')}">${latencyText}</td>
            <td data-label="${t('ports')}">${portsText}</td>
            <td data-label="${t('lastSeen')}">${lastSeenText}</td>
            <td data-label="${t('actions')}" class="table-actions-cell">
                <button class="btn btn-sm btn-secondary" onclick="openSwitchDetails('${s.ip}')">${t('details')}</button>
                <a href="/terminal/${s.ip}" target="_blank" class="btn btn-sm btn-primary" style="margin-inline-start:4px;">${t('terminal')}</a>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// --- Modal Switch Details & Tabs State ---
let currentModalSwitchData = null;
let currentModalActiveTab = 'ports';
let currentModalPorts = [];
let currentModalPortSearch = '';
let currentModalPortStatusFilter = 'all'; // 'all', 'up', 'down'
let currentModalPortSortCol = 'port_name';
let currentModalPortSortDir = 'asc';

let currentModalDevices = [];
let currentModalDeviceSearch = '';

function parsePortName(name) {
    if (!name) return { prefix: '', numbers: [] };
    const match = name.match(/^([a-zA-Z\s\-_]+)?(.*)$/);
    const prefix = (match && match[1] ? match[1] : '').toLowerCase();
    const rest = (match && match[2] ? match[2] : '');
    const numbers = rest.match(/\d+/g) ? rest.match(/\d+/g).map(Number) : [];
    return { prefix, numbers, raw: name };
}

function comparePortNames(a, b) {
    const pA = parsePortName(a);
    const pB = parsePortName(b);
    if (pA.prefix !== pB.prefix) {
        return pA.prefix.localeCompare(pB.prefix);
    }
    const len = Math.max(pA.numbers.length, pB.numbers.length);
    for (let i = 0; i < len; i++) {
        const numA = pA.numbers[i] !== undefined ? pA.numbers[i] : -1;
        const numB = pB.numbers[i] !== undefined ? pB.numbers[i] : -1;
        if (numA !== numB) return numA - numB;
    }
    return (pA.raw || '').localeCompare(pB.raw || '');
}

function switchModalTab(tabId) {
    currentModalActiveTab = tabId;
    document.querySelectorAll('.modal-tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
    });
    document.querySelectorAll('.modal-tab-pane').forEach(pane => {
        pane.classList.toggle('active', pane.id === `modal-tab-${tabId}`);
    });
}

function filterModalPortsSearch(searchTerm) {
    currentModalPortSearch = (searchTerm || '').trim().toLowerCase();
    renderModalPortsTable();
}

function setModalPortStatusFilter(statusFilter) {
    currentModalPortStatusFilter = statusFilter;
    document.querySelectorAll('.modal-filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-filter') === statusFilter);
    });
    renderModalPortsTable();
}

function sortModalPorts(columnKey) {
    if (currentModalPortSortCol === columnKey) {
        currentModalPortSortDir = currentModalPortSortDir === 'asc' ? 'desc' : 'asc';
    } else {
        currentModalPortSortCol = columnKey;
        currentModalPortSortDir = 'asc';
    }
    renderModalPortsTable();
}

function filterModalDevicesSearch(searchTerm) {
    currentModalDeviceSearch = (searchTerm || '').trim().toLowerCase();
    renderModalDevicesTable();
}

function getFilteredAndSortedPorts() {
    let list = [...currentModalPorts];

    // Status filter
    if (currentModalPortStatusFilter === 'up') {
        list = list.filter(p => (p.status || '').toLowerCase() === 'up');
    } else if (currentModalPortStatusFilter === 'down') {
        list = list.filter(p => (p.status || '').toLowerCase() !== 'up');
    }

    // Text search filter
    if (currentModalPortSearch) {
        list = list.filter(p => {
            const pName = (p.port_name || '').toLowerCase();
            const pMac = (p.mac_address || '').toLowerCase();
            const pVlan = String(p.vlan || '').toLowerCase();
            const pDev = (p.connected_device || '').toLowerCase();
            return pName.includes(currentModalPortSearch) || 
                   pMac.includes(currentModalPortSearch) || 
                   pVlan.includes(currentModalPortSearch) ||
                   pDev.includes(currentModalPortSearch);
        });
    }

    // Sorting
    list.sort((a, b) => {
        let comparison = 0;
        switch (currentModalPortSortCol) {
            case 'port_name':
                comparison = comparePortNames(a.port_name || '', b.port_name || '');
                break;
            case 'status':
                const sA = (a.status || '').toLowerCase();
                const sB = (b.status || '').toLowerCase();
                comparison = sA.localeCompare(sB);
                break;
            case 'vlan':
                const vA = parseInt(a.vlan, 10) || 0;
                const vB = parseInt(b.vlan, 10) || 0;
                comparison = vA - vB;
                break;
            case 'mac_address':
                const mA = (a.mac_address || '').toLowerCase();
                const mB = (b.mac_address || '').toLowerCase();
                comparison = mA.localeCompare(mB);
                break;
            case 'speed':
                const spA = (a.speed || '').toLowerCase();
                const spB = (b.speed || '').toLowerCase();
                comparison = spA.localeCompare(spB);
                break;
            default:
                comparison = 0;
        }
        return currentModalPortSortDir === 'asc' ? comparison : -comparison;
    });

    return list;
}

function renderModalPortsTable() {
    const tbody = document.getElementById('modal-ports-tbody');
    const countBadge = document.getElementById('modal-tab-ports-count');
    if (!tbody) return;

    const filtered = getFilteredAndSortedPorts();
    if (countBadge) countBadge.textContent = `${filtered.length}/${currentModalPorts.length}`;

    // Update Header Sort indicators
    const headers = document.querySelectorAll('#modal-ports-table th.sortable-th');
    headers.forEach(th => {
        const sortKey = th.getAttribute('data-sort-key');
        const iconSpan = th.querySelector('.sort-icon');
        th.classList.remove('sorted-asc', 'sorted-desc');
        if (sortKey === currentModalPortSortCol) {
            th.classList.add(currentModalPortSortDir === 'asc' ? 'sorted-asc' : 'sorted-desc');
            if (iconSpan) iconSpan.textContent = currentModalPortSortDir === 'asc' ? '▲' : '▼';
        } else if (iconSpan) {
            iconSpan.textContent = '↕';
        }
    });

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 24px; color:var(--text-subtle);">${t('noPortData')}</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(p => {
        const pUp = (p.status || '').toLowerCase() === 'up';
        const badgeClass = pUp ? 'badge-pill-success' : 'badge-pill-error';
        const badgeIcon = pUp ? '🟢' : '⚪';
        const speedText = p.speed && p.speed !== 'N/A' ? `<span style="font-size:0.75rem; color:var(--text-subtle);">${p.speed}</span>` : '';
        const macDisplay = p.mac_address ? `<code>${p.mac_address}</code>` : '<span style="color:var(--text-subtle);">-</span>';

        return `<tr>
            <td><code>${p.port_name || '-'}</code></td>
            <td><span class="badge-pill ${badgeClass}">${badgeIcon} ${pUp ? 'Up' : 'Down'}</span> ${speedText}</td>
            <td><span class="vlan-chip" style="padding:2px 8px; font-size:0.75rem;">VLAN ${p.vlan || '1'}</span></td>
            <td>${macDisplay}</td>
            <td>${p.connected_device ? `<strong>${p.connected_device}</strong>` : '<span style="color:var(--text-subtle);">-</span>'}</td>
        </tr>`;
    }).join('');
}

function renderModalDevicesTable() {
    const tbody = document.getElementById('modal-devices-tbody');
    if (!tbody) return;

    let list = [...currentModalDevices];
    if (currentModalDeviceSearch) {
        list = list.filter(d => {
            const str = `${d.port || ''} ${d.mac_address || ''} ${d.ip_address || ''} ${d.vendor || ''} ${d.name || ''}`.toLowerCase();
            return str.includes(currentModalDeviceSearch);
        });
    }

    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 24px; color:var(--text-subtle);">${t('noDevicesData')}</td></tr>`;
        return;
    }

    tbody.innerHTML = list.map(d => `<tr>
        <td><code>${d.port || '-'}</code></td>
        <td><code>${d.mac_address || '-'}</code></td>
        <td>${d.ip_address ? `<code>${d.ip_address}</code>` : '<span style="color:var(--text-subtle);">-</span>'}</td>
        <td>${d.vendor || '<span style="color:var(--text-subtle);">-</span>'}</td>
        <td><span class="vlan-chip" style="padding:2px 8px; font-size:0.75rem;">VLAN ${d.vlan || '-'}</span></td>
    </tr>`).join('');
}

// --- Switch Details Modal Opener ---
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

            currentModalSwitchData = resData;
            const sw = resData.switch || {};
            const vlans = resData.vlans || [];
            const links = resData.links || [];
            const ports = resData.ports || [];
            const devices = resData.devices || [];
            
            const isOnline = (sw.status || 'online').toLowerCase() === 'online';
            const badgeClass = isOnline ? 'badge-pill-success' : 'badge-pill-error';
            const badgeIcon = isOnline ? '🟢' : '🔴';

            const totalPorts = sw.ports_total || sw.total_ports || ports.length || 0;
            const portsUp = sw.ports_up || ports.filter(p => (p.status || '').toLowerCase() === 'up').length || 0;
            const utilPercent = totalPorts > 0 ? Math.round((portsUp / totalPorts) * 100) : 0;

            // Reset modal filter states
            currentModalPorts = Array.isArray(ports) ? [...ports] : [];
            currentModalDevices = Array.isArray(devices) ? [...devices] : [];
            currentModalPortSearch = '';
            currentModalDeviceSearch = '';
            currentModalPortStatusFilter = 'all';
            currentModalPortSortCol = 'port_name';
            currentModalPortSortDir = 'asc';
            currentModalActiveTab = 'ports';

            titleEl.innerHTML = `🖥️ ${sw.hostname || sw.ip} <span class="badge-pill ${badgeClass}" style="margin-inline-start:8px; vertical-align:middle; font-size:0.8rem;">${badgeIcon} ${t(isOnline ? 'online' : 'offline')}</span>`;
            subTitleEl.innerHTML = `<div class="modal-header-actions" style="margin-top:4px;">
                <span>${t('ipAddress')}: <code>${sw.ip}</code></span>
                <a href="/terminal/${sw.ip}" target="_blank" class="btn btn-xs btn-primary">${t('openTerminalBtn')} ↗</a>
            </div>`;

            // Build Tab Content HTML
            let vlansHtml = vlans.length > 0 
                ? vlans.map(v => `<span class="vlan-chip" title="Ports: ${v.ports || 'None'}"><b>VLAN ${v.vlan_id}</b> (${v.vlan_name || 'N/A'}) - <strong>${v.port_count}</strong> ports</span>`).join('') 
                : `<div style="padding:20px; text-align:center; color:var(--text-subtle);">${t('noVlanData')}</div>`;

            let linksHtml = links.length > 0
                ? `<div class="table-wrapper"><table class="mini-table"><thead><tr><th>${t('localPort')}</th><th>${t('remoteSwitch')}</th><th>${t('remotePort')}</th><th>${t('protocol')}</th></tr></thead><tbody>` +
                  links.map(l => `<tr><td><code>${l.source_port}</code></td><td><strong>${l.target_switch}</strong></td><td><code>${l.target_port || '-'}</code></td><td><span class="badge-pill">${l.protocol}</span></td></tr>`).join('') +
                  `</tbody></table></div>`
                : `<div style="padding:24px; text-align:center; color:var(--text-subtle);">${t('noLinksData')}</div>`;

            bodyEl.innerHTML = `
                <!-- Compact KPI Overview Strip -->
                <div class="sw-overview-bar">
                    <div class="kpi-mini-card">
                        <span class="kpi-mini-label">${t('model')} / ${t('iosVer')}</span>
                        <span class="kpi-mini-value">${sw.model || 'Cisco Switch'}</span>
                        <small style="color:var(--text-subtle); font-size:0.75rem;">${sw.ios_version || 'IOS Standard'}</small>
                    </div>
                    <div class="kpi-mini-card">
                        <span class="kpi-mini-label">${t('portUtilization')}</span>
                        <span class="kpi-mini-value"><strong>${portsUp}</strong> / ${totalPorts} <small style="color:var(--text-subtle); font-weight:normal;">(${utilPercent}%)</small></span>
                        <div class="kpi-progress-bar"><div class="kpi-progress-fill" style="width: ${utilPercent}%;"></div></div>
                    </div>
                    <div class="kpi-mini-card">
                        <span class="kpi-mini-label">${t('latency')} (Ping)</span>
                        <span class="kpi-mini-value">${isOnline && sw.latency_ms > 0 ? `<code>${sw.latency_ms} ms</code>` : `<span style="color:var(--text-subtle);">-</span>`}</span>
                        <small style="color:var(--text-subtle); font-size:0.75rem;">${sw.last_seen ? sw.last_seen.replace('T', ' ').substring(0, 19) : '-'}</small>
                    </div>
                    <div class="kpi-mini-card">
                        <span class="kpi-mini-label">${t('serialNumber')}</span>
                        <span class="kpi-mini-value" style="font-family:monospace; font-size:0.85rem;">${sw.serial_number || 'N/A'}</span>
                    </div>
                </div>

                <!-- Modal Tabs Nav -->
                <div class="modal-tabs-nav">
                    <button class="modal-tab-btn active" data-tab="ports" onclick="switchModalTab('ports')">
                        ${t('tabPorts')} <span class="modal-tab-badge" id="modal-tab-ports-count">${ports.length}</span>
                    </button>
                    <button class="modal-tab-btn" data-tab="cdp" onclick="switchModalTab('cdp')">
                        ${t('tabCdp')} <span class="modal-tab-badge">${links.length}</span>
                    </button>
                    <button class="modal-tab-btn" data-tab="vlans" onclick="switchModalTab('vlans')">
                        ${t('tabVlans')} <span class="modal-tab-badge">${vlans.length}</span>
                    </button>
                    <button class="modal-tab-btn" data-tab="devices" onclick="switchModalTab('devices')">
                        ${t('tabDevices')} <span class="modal-tab-badge">${devices.length}</span>
                    </button>
                </div>

                <!-- Tab 1: Ports Pane -->
                <div class="modal-tab-pane active" id="modal-tab-ports">
                    <div class="modal-toolbar">
                        <div class="modal-search-box">
                            <input type="text" placeholder="${t('searchPortsPlaceholder')}" oninput="filterModalPortsSearch(this.value)">
                            <span class="modal-search-icon">🔍</span>
                        </div>
                        <div class="modal-filter-group">
                            <button class="modal-filter-btn active" data-filter="all" onclick="setModalPortStatusFilter('all')">${t('filterAll')}</button>
                            <button class="modal-filter-btn" data-filter="up" onclick="setModalPortStatusFilter('up')">${t('filterUp')}</button>
                            <button class="modal-filter-btn" data-filter="down" onclick="setModalPortStatusFilter('down')">${t('filterDown')}</button>
                        </div>
                    </div>
                    <div class="table-wrapper" style="max-height: 380px; overflow-y: auto;">
                        <table class="mini-table" id="modal-ports-table">
                            <thead>
                                <tr>
                                    <th class="sortable-th" data-sort-key="port_name" onclick="sortModalPorts('port_name')">
                                        <span>${t('port')}</span> <span class="sort-icon">↕</span>
                                    </th>
                                    <th class="sortable-th" data-sort-key="status" onclick="sortModalPorts('status')">
                                        <span>${t('status')} / ${t('speed')}</span> <span class="sort-icon">↕</span>
                                    </th>
                                    <th class="sortable-th" data-sort-key="vlan" onclick="sortModalPorts('vlan')">
                                        <span>${t('vlan')}</span> <span class="sort-icon">↕</span>
                                    </th>
                                    <th class="sortable-th" data-sort-key="mac_address" onclick="sortModalPorts('mac_address')">
                                        <span>${t('macAddress')}</span> <span class="sort-icon">↕</span>
                                    </th>
                                    <th>${t('connectedDevice')}</th>
                                </tr>
                            </thead>
                            <tbody id="modal-ports-tbody"></tbody>
                        </table>
                    </div>
                </div>

                <!-- Tab 2: CDP & Neighbors Pane -->
                <div class="modal-tab-pane" id="modal-tab-cdp">
                    <div class="sw-section-card" style="margin-bottom:0;">
                        <h4>↔ ${t('cdpLinks')} (${links.length})</h4>
                        ${linksHtml}
                    </div>
                </div>

                <!-- Tab 3: VLANs Pane -->
                <div class="modal-tab-pane" id="modal-tab-vlans">
                    <div class="sw-section-card" style="margin-bottom:0;">
                        <h4>📊 ${t('configuredVlans')} (${vlans.length})</h4>
                        <div class="vlan-chips-wrapper">${vlansHtml}</div>
                    </div>
                </div>

                <!-- Tab 4: Connected Devices Pane -->
                <div class="modal-tab-pane" id="modal-tab-devices">
                    <div class="modal-toolbar">
                        <div class="modal-search-box">
                            <input type="text" placeholder="${t('searchDevicesPlaceholder')}" oninput="filterModalDevicesSearch(this.value)">
                            <span class="modal-search-icon">🔍</span>
                        </div>
                    </div>
                    <div class="table-wrapper" style="max-height: 380px; overflow-y: auto;">
                        <table class="mini-table">
                            <thead>
                                <tr>
                                    <th>${t('port')}</th>
                                    <th>${t('macAddress')}</th>
                                    <th>${t('ipAddress')}</th>
                                    <th>${t('vendor')}</th>
                                    <th>${t('vlan')}</th>
                                </tr>
                            </thead>
                            <tbody id="modal-devices-tbody"></tbody>
                        </table>
                    </div>
                </div>
            `;

            renderModalPortsTable();
            renderModalDevicesTable();
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
        excluded_ips: document.getElementById('wiz-excluded') ? document.getElementById('wiz-excluded').value : '',
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
