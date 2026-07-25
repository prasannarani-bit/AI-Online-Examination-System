const API_URL = '/api';

class ApiClient {
    static getToken() {
        return localStorage.getItem('token');
    }

    static setToken(token) {
        localStorage.setItem('token', token);
    }

    static clearTokens() {
        localStorage.removeItem('token');
        localStorage.removeItem('role');
        localStorage.removeItem('username');
    }

    static async request(endpoint, options = {}) {
        const token = this.getToken();
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...options.headers
        };

        const config = {
            ...options,
            headers
        };

        try {
            const response = await fetch(`${API_URL}${endpoint}`, config);
            const data = await response.json();

            if (response.status === 401 || response.status === 403) {
                // Unauthorized, redirect to login
                this.clearTokens();
                window.location.href = 'login.html';
            }

            return { ok: response.ok, status: response.status, data };
        } catch (error) {
            console.error('API Error:', error);
            return { ok: false, status: 500, data: { message: 'Network error' } };
        }
    }

    static async get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    }

    static async post(endpoint, body) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(body)
        });
    }

    static async delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    }

    static async postFormData(endpoint, formData) {
        const token = this.getToken();
        const headers = {
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        };
        // Do not set Content-Type, let browser set it with boundary
        try {
            const response = await fetch(`${API_URL}${endpoint}`, {
                method: 'POST',
                headers,
                body: formData
            });
            const data = await response.json();
            if (response.status === 401 || response.status === 403) {
                this.clearTokens();
                window.location.href = 'login.html';
            }
            return { ok: response.ok, status: response.status, data };
        } catch (error) {
            console.error('API Error:', error);
            return { ok: false, status: 500, data: { message: 'Network error' } };
        }
    }

    static checkAuth(allowedRoles = []) {
        const token = this.getToken();
        const role = localStorage.getItem('role');

        if (!token) {
            window.location.href = 'login.html';
            return;
        }

        if (allowedRoles.length > 0 && !allowedRoles.includes(role)) {
            // redirect to correct dashboard
            window.location.href = 'index.html';
            return;
        }

        // Apply themed sidebar layout automatically on all other pages
        this.applyGlobalTheme();
    }

    static applyGlobalTheme() {
        const path = window.location.pathname.toLowerCase();
        if (path.includes('landing.html') || path.includes('login.html') || path.includes('register.html') || path.includes('forgot_password.html') || path.includes('start_exam.html')) {
            return;
        }

        // If DOMContentLoaded hasn't fired yet, wait for it
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.applyGlobalTheme());
            return;
        }

        // If already themed, don't theme again
        if (document.querySelector('.dashboard-root')) {
            return;
        }

        // Make sure font is Inter and we have bootstrap icons
        if (!document.querySelector('link[href*="bootstrap-icons"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css';
            document.head.appendChild(link);
        }
        if (!document.querySelector('link[href*="style.css"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'css/style.css';
            document.head.appendChild(link);
        }

        const role = localStorage.getItem('role') || 'student';
        const username = localStorage.getItem('username') || 'User';
        const fullName = localStorage.getItem('full_name') || username;
        const initial = (fullName.charAt(0) || 'U').toUpperCase();

        // 1. Capture the original body content
        const originalBodyNodes = [];
        const scriptNodes = [];
        const styleNodes = [];

        // Remove any navbar first
        const oldNavbar = document.querySelector('nav.navbar, div.navbar');
        if (oldNavbar) {
            oldNavbar.remove();
        }

        // Move children
        while (document.body.firstChild) {
            const child = document.body.firstChild;
            if (child.tagName === 'SCRIPT') {
                scriptNodes.push(child);
                document.body.removeChild(child);
            } else if (child.tagName === 'STYLE') {
                styleNodes.push(child);
                document.body.removeChild(child);
            } else {
                originalBodyNodes.push(child);
                document.body.removeChild(child);
            }
        }

        // 2. Build the sidebar menu HTML based on role
        let sidebarClass = 'sidebar-student';
        let sidebarHeader = `
            <div class="sidebar-logo">
                <div class="sidebar-logo-icon"><i class="bi bi-mortarboard-fill"></i></div>
                <div>
                    <div class="sidebar-logo-text">Agentic AI</div>
                    <div class="sidebar-logo-sub">Exam System</div>
                </div>
            </div>
        `;
        let sidebarNavHTML = '';
        let helpModalBodyHTML = '';

        if (role === 'admin') {
            sidebarClass = 'sidebar-admin';
            sidebarNavHTML = `
                <a href="admin_dashboard.html" class="nav-item-s" id="nav-dashboard">
                    <span class="nav-icon"><i class="bi bi-grid-1x2-fill"></i></span> Dashboard
                </a>
                <a href="manage_users.html" class="nav-item-s" id="nav-users">
                    <span class="nav-icon"><i class="bi bi-people-fill"></i></span> Users
                </a>
                <a href="admin_exams.html" class="nav-item-s" id="nav-exams">
                    <span class="nav-icon"><i class="bi bi-journal-check"></i></span> Exams
                </a>
                <a href="monitor_exams.html" class="nav-item-s" id="nav-monitor">
                    <span class="nav-icon"><i class="bi bi-activity"></i></span> Monitoring
                    <span class="nav-badge">Live</span>
                </a>
                <a href="admin_results.html" class="nav-item-s" id="nav-reports">
                    <span class="nav-icon"><i class="bi bi-bar-chart-line-fill"></i></span> Reports
                </a>
                <a href="admin_files.html" class="nav-item-s" id="nav-files">
                    <span class="nav-icon"><i class="bi bi-folder-fill"></i></span> Faculty Files
                </a>
                <a href="landing.html" class="nav-item-s">
                    <span class="nav-icon"><i class="bi bi-house-door-fill"></i></span> Back to Home
                </a>
            `;
            helpModalBodyHTML = `
                <div class="help-item">
                    <div class="help-item-icon admin"><i class="bi bi-person-plus-fill"></i></div>
                    <div>
                        <div class="help-item-title">Managing Users</div>
                        <div class="help-item-desc">Go to "Manage Users" to create, activate, or deactivate faculty and student accounts.</div>
                    </div>
                </div>
                <div class="help-item">
                    <div class="help-item-icon admin"><i class="bi bi-activity"></i></div>
                    <div>
                        <div class="help-item-title">Live Monitoring</div>
                        <div class="help-item-desc">Use "Monitoring" in the sidebar to view real-time proctoring logs and detect violations.</div>
                    </div>
                </div>
            `;
        } else if (role === 'faculty') {
            sidebarClass = 'sidebar-faculty';
            sidebarNavHTML = `
                <a href="faculty_dashboard.html" class="nav-item-s" id="nav-dashboard">
                    <span class="nav-icon"><i class="bi bi-grid-1x2-fill"></i></span> Dashboard
                </a>
                <a href="faculty_dashboard.html#my-exams" class="nav-item-s" id="nav-myexams">
                    <span class="nav-icon"><i class="bi bi-journal-check"></i></span> My Exams
                </a>
                <a href="create_exam.html" class="nav-item-s" id="nav-create">
                    <span class="nav-icon"><i class="bi bi-plus-circle-fill"></i></span> Create Exam
                </a>
                <a href="faculty_dashboard.html#question-bank" class="nav-item-s" id="nav-qbank">
                    <span class="nav-icon"><i class="bi bi-collection-fill"></i></span> Question Bank
                </a>
                <a href="faculty_dashboard.html#results-section" class="nav-item-s" id="nav-students">
                    <span class="nav-icon"><i class="bi bi-people-fill"></i></span> Students
                </a>
                <a href="analytics.html" class="nav-item-s" id="nav-analytics">
                    <span class="nav-icon"><i class="bi bi-bar-chart-line-fill"></i></span> Results &amp; Analytics
                </a>
                <a href="faculty_dashboard.html#uploads" class="nav-item-s" id="nav-uploads">
                    <span class="nav-icon"><i class="bi bi-cloud-upload-fill"></i></span> Uploads
                </a>
                <a href="landing.html" class="nav-item-s">
                    <span class="nav-icon"><i class="bi bi-house-door-fill"></i></span> Back to Home
                </a>
            `;
            helpModalBodyHTML = `
                <div class="help-item">
                    <div class="help-item-icon"><i class="bi bi-plus-circle-fill"></i></div>
                    <div>
                        <div class="help-item-title">Creating an Exam</div>
                        <div class="help-item-desc">Click "Create Exam" in the sidebar or Quick Actions. Fill in the details and upload questions.</div>
                    </div>
                </div>
                <div class="help-item">
                    <div class="help-item-icon"><i class="bi bi-robot"></i></div>
                    <div>
                        <div class="help-item-title">AI Question Generation</div>
                        <div class="help-item-desc">Upload a syllabus file in Internal Storage, then click "Generate Exam" to auto-create MCQs using AI.</div>
                    </div>
                </div>
            `;
        } else {
            // Student
            sidebarClass = 'sidebar-student';
            sidebarNavHTML = `
                <a href="student_dashboard.html" class="nav-item-s" id="nav-dashboard">
                    <span class="nav-icon"><i class="bi bi-grid-1x2-fill"></i></span> Dashboard
                </a>
                <a href="student_dashboard.html#available" class="nav-item-s" id="nav-myexams">
                    <span class="nav-icon"><i class="bi bi-journal-check"></i></span> My Exams
                </a>
                <a href="results.html" class="nav-item-s" id="nav-results">
                    <span class="nav-icon"><i class="bi bi-bar-chart-line-fill"></i></span> Results
                </a>
                <a href="certificate_generator.html" class="nav-item-s" id="nav-cert">
                    <span class="nav-icon"><i class="bi bi-award-fill"></i></span> Certificates
                </a>
                <a href="landing.html" class="nav-item-s">
                    <span class="nav-icon"><i class="bi bi-house-door-fill"></i></span> Back to Home
                </a>
            `;
            helpModalBodyHTML = `
                <div class="help-item">
                    <div class="help-item-icon"><i class="bi bi-play-circle-fill"></i></div>
                    <div>
                        <div class="help-item-title">How to Start an Exam</div>
                        <div class="help-item-desc">Click "Start Exam" on any available exam card. Ensure your camera is enabled for proctoring.</div>
                    </div>
                </div>
                <div class="help-item">
                    <div class="help-item-icon"><i class="bi bi-bar-chart-line-fill"></i></div>
                    <div>
                        <div class="help-item-title">View Your Results</div>
                        <div class="help-item-desc">After submission, results appear in "Your Past Attempts" once evaluated by the system.</div>
                    </div>
                </div>
            `;
        }

        // 3. Create wrapper elements
        const rootDiv = document.createElement('div');
        rootDiv.className = 'dashboard-root';

        const sidebarElement = document.createElement('aside');
        sidebarElement.className = `sidebar ${sidebarClass}`;
        sidebarElement.innerHTML = `
            ${sidebarHeader}
            <nav class="sidebar-nav">
                ${sidebarNavHTML}
                <div class="sidebar-divider"></div>
                ${role !== 'admin' ? `
                <button class="nav-item-s" id="nav-help-btn" type="button">
                    <span class="nav-icon"><i class="bi bi-question-circle-fill"></i></span> Need Help?
                </button>` : ''}
                <button class="nav-item-s" id="nav-logout-btn" type="button" style="color:rgba(255,200,200,.85)">
                    <span class="nav-icon"><i class="bi bi-box-arrow-right"></i></span> Logout
                </button>
            </nav>
        `;

        const mainContentDiv = document.createElement('div');
        mainContentDiv.className = 'main-content';

        // Header
        const headerElement = document.createElement('header');
        headerElement.className = 'top-header';
        
        let pageTitle = 'Dashboard';
        if (path.includes('profile.html')) pageTitle = 'My Profile';
        else if (path.includes('manage_users.html')) pageTitle = 'Manage Users';
        else if (path.includes('create_exam.html')) pageTitle = 'Create Exam';
        else if (path.includes('edit_exam.html')) pageTitle = 'Edit Exam';
        else if (path.includes('analytics.html')) pageTitle = 'Analytics & Reports';
        else if (path.includes('results.html')) pageTitle = 'Exam Results';
        else if (path.includes('certificate_generator.html')) pageTitle = 'Certificate Generator';
        else if (path.includes('admin_exams.html')) pageTitle = 'Manage Exams';
        else if (path.includes('admin_files.html')) pageTitle = 'Faculty Files';
        else if (path.includes('admin_results.html')) pageTitle = 'System Reports';
        else if (path.includes('monitor_exams.html')) pageTitle = 'Live Exam Proctoring';
        else if (path.includes('pre_exam.html')) pageTitle = 'Confirm Exam Details';
        else if (path.includes('question_paper.html')) pageTitle = 'Review Question Paper';

        headerElement.innerHTML = `
            <div class="header-greeting">
                <h5>${pageTitle}</h5>
                <span>Welcome back, ${fullName}</span>
            </div>
            <div class="header-actions">
                <div style="position:relative;">
                    <button class="notif-btn" id="headerNotifBtn" type="button" title="Notifications">
                        <i class="bi bi-bell-fill"></i>
                        <span class="notif-badge" id="headerNotifBadge" style="display:none">0</span>
                    </button>
                </div>
                <div style="position:relative;">
                    <button class="profile-btn" id="headerProfileBtn" type="button">
                        <div class="profile-avatar" id="headerProfileAvatar" style="background:linear-gradient(135deg,#6366f1,#8b5cf6)">${initial}</div>
                        <span class="profile-name">${fullName}</span>
                        <i class="bi bi-chevron-down" style="font-size:10px;color:#94a3b8;margin-left:2px;"></i>
                    </button>
                </div>
            </div>

            <!-- Notification Dropdown -->
            <div class="notif-dropdown" id="headerNotifDropdown">
                <div class="notif-header">
                    <h6><i class="bi bi-bell-fill me-1 text-primary"></i> Notifications</h6>
                    <a href="#" id="headerClearNotifBtn">Mark all read</a>
                </div>
                <div id="headerNotifList">
                    <div class="notif-empty">No new notifications</div>
                </div>
            </div>

            <!-- Profile Dropdown -->
            <div class="profile-dropdown" id="headerProfileDropdown">
                <div class="profile-dd-header">
                    <div class="profile-dd-avatar" style="background:linear-gradient(135deg,#6366f1,#8b5cf6)">${initial}</div>
                    <div class="profile-dd-name">${fullName}</div>
                    <div class="profile-dd-role">${role.toUpperCase()}</div>
                </div>
                <a href="profile.html" class="profile-dd-item"><i class="bi bi-person-fill me-2 text-primary"></i> My Profile</a>
                <div class="profile-dd-divider"></div>
                <button class="profile-dd-item danger" id="headerLogoutBtn" type="button"><i class="bi bi-box-arrow-right me-2"></i> Logout</button>
            </div>
        `;

        const pageBodyDiv = document.createElement('div');
        pageBodyDiv.className = 'page-body';

        // Re-append nodes
        originalBodyNodes.forEach(node => pageBodyDiv.appendChild(node));

        mainContentDiv.appendChild(headerElement);
        mainContentDiv.appendChild(pageBodyDiv);

        rootDiv.appendChild(sidebarElement);
        rootDiv.appendChild(mainContentDiv);

        // Help Modal
        const helpModalOverlay = document.createElement('div');
        helpModalOverlay.className = 'help-modal-overlay';
        helpModalOverlay.id = 'headerHelpOverlay';
        helpModalOverlay.innerHTML = `
            <div class="help-modal">
                <div class="help-modal-header ${role === 'admin' ? 'admin-header' : ''}">
                    <h6><i class="bi bi-headset me-2"></i>Help &amp; Support</h6>
                    <button class="help-modal-close" id="headerHelpCloseBtn" type="button"><i class="bi bi-x"></i></button>
                </div>
                <div class="help-modal-body">
                    ${helpModalBodyHTML}
                    <div class="help-item">
                        <div class="help-item-icon ${role === 'admin' ? 'admin' : ''}"><i class="bi bi-envelope-fill"></i></div>
                        <div>
                            <div class="help-item-title">Contact Support</div>
                            <div class="help-item-desc">Email us at <strong>support@agenticexam.edu</strong> for technical assistance.</div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Help FAB
        const helpFab = document.createElement('button');
        helpFab.className = `help-fab ${role === 'admin' ? 'help-fab-admin' : ''}`;
        helpFab.id = 'headerHelpFab';
        helpFab.innerHTML = `<i class="bi bi-headset"></i> Need Help?`;

        document.body.appendChild(rootDiv);
        document.body.appendChild(helpFab);
        document.body.appendChild(helpModalOverlay);

        scriptNodes.forEach(node => document.body.appendChild(node));
        styleNodes.forEach(node => document.body.appendChild(node));

        // Setup Event Listeners
        const notifBtn = document.getElementById('headerNotifBtn');
        const notifDropdown = document.getElementById('headerNotifDropdown');
        const profileBtn = document.getElementById('headerProfileBtn');
        const profileDropdown = document.getElementById('headerProfileDropdown');
        const helpFabBtn = document.getElementById('headerHelpFab');
        const helpOverlay = document.getElementById('headerHelpOverlay');
        const helpCloseBtn = document.getElementById('headerHelpCloseBtn');
        const logoutBtn = document.getElementById('headerLogoutBtn');
        const sideLogoutBtn = document.getElementById('nav-logout-btn');
        const sideHelpBtn = document.getElementById('nav-help-btn');

        if (notifBtn) {
            notifBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                profileDropdown.classList.remove('open');
                notifDropdown.classList.toggle('open');
            });
        }
        if (profileBtn) {
            profileBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                notifDropdown.classList.remove('open');
                profileDropdown.classList.toggle('open');
            });
        }
        document.addEventListener('click', () => {
            if (notifDropdown) notifDropdown.classList.remove('open');
            if (profileDropdown) profileDropdown.classList.remove('open');
        });

        const openHelp = () => { if (helpOverlay) helpOverlay.classList.add('open'); };
        const closeHelp = () => { if (helpOverlay) helpOverlay.classList.remove('open'); };

        if (helpFabBtn) helpFabBtn.addEventListener('click', openHelp);
        if (sideHelpBtn) sideHelpBtn.addEventListener('click', openHelp);
        if (helpCloseBtn) helpCloseBtn.addEventListener('click', closeHelp);
        if (helpOverlay) {
            helpOverlay.addEventListener('click', (e) => {
                if (e.target === helpOverlay) closeHelp();
            });
        }

        const handleLogout = () => {
            this.clearTokens();
            window.location.href = 'login.html';
        };

        if (logoutBtn) logoutBtn.addEventListener('click', handleLogout);
        if (sideLogoutBtn) sideLogoutBtn.addEventListener('click', handleLogout);

        const navLinks = sidebarElement.querySelectorAll('.nav-item-s');
        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (href && path.includes(href)) {
                link.classList.add('active');
            }
        });
    }

    static setupNav() {
        // No-op: The new sidebar dashboards render their own header with
        // profile avatar (top-right) and logout. Legacy pages that still
        // call setupNav() will not break; the old #user-nav element simply
        // stays empty and the new layout handles navigation.
        const navContainer = document.getElementById('user-nav');
        if (navContainer) {
            navContainer.innerHTML = ''; // clear any legacy markup
        }
    }

    static formatDateTime(utcStr) {
        if (!utcStr) return '—';
        let cleanStr = utcStr.trim();
        if (cleanStr.indexOf('T') === -1) {
            cleanStr = cleanStr.replace(' ', 'T');
        }
        if (!cleanStr.endsWith('Z') && cleanStr.indexOf('+') === -1) {
            cleanStr += 'Z';
        }
        const date = new Date(cleanStr);
        return date.toLocaleString();
    }

    static formatDate(utcStr) {
        if (!utcStr) return '—';
        let cleanStr = utcStr.trim();
        if (cleanStr.indexOf('T') === -1) {
            cleanStr = cleanStr.replace(' ', 'T');
        }
        if (!cleanStr.endsWith('Z') && cleanStr.indexOf('+') === -1) {
            cleanStr += 'Z';
        }
        const date = new Date(cleanStr);
        return date.toLocaleDateString();
    }
}
