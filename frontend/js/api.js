const API_URL = 'https://ai-online-examination-system-1.onrender.com/api/login';

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
        }
    }

    static setupNav() {
        const username = localStorage.getItem('username');
        const role = localStorage.getItem('role');
        const navContainer = document.getElementById('user-nav');

        if (username && role && navContainer) {
            navContainer.innerHTML = `
                <li class="nav-item">
                    <span class="nav-link text-white">Welcome, ${username} <span class="badge bg-secondary">${role}</span></span>
                </li>
                <li class="nav-item">
                    <a class="nav-link text-danger fw-bold" href="#" onclick="ApiClient.clearTokens(); window.location.href='login.html'">Logout</a>
                </li>
            `;
        }
    }
}
