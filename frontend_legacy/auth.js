/**
 * Ablage-System Authentication Module
 * Handles user authentication, token management, and session handling
 */

/**
 * Authentication Manager
 */
class AuthManager {
    constructor() {
        this.tokenRefreshInterval = null;
        this.tokenRefreshTime = 14 * 60 * 1000; // Refresh 1 minute before expiry (14 min)

        // Listen for logout events
        window.addEventListener('auth:logout', () => this.handleLogout());

        // Start token refresh if logged in
        if (this.isAuthenticated()) {
            this.startTokenRefresh();
        }
    }

    /**
     * Check if user is authenticated
     */
    isAuthenticated() {
        const token = localStorage.getItem('access_token');
        if (!token) {
            return false;
        }

        // Check if token is expired
        try {
            const payload = this.decodeToken(token);
            const now = Date.now() / 1000;
            return payload.exp > now;
        } catch {
            return false;
        }
    }

    /**
     * Decode JWT token
     */
    decodeToken(token) {
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(
                atob(base64)
                    .split('')
                    .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
                    .join('')
            );
            return JSON.parse(jsonPayload);
        } catch (error) {
            throw new Error('Ungültiges Token-Format');
        }
    }

    /**
     * Get current user from token
     */
    getCurrentUser() {
        const token = localStorage.getItem('access_token');
        if (!token) {
            return null;
        }

        try {
            const payload = this.decodeToken(token);
            return {
                id: payload.sub,
                email: payload.email,
                username: payload.username
            };
        } catch {
            return null;
        }
    }

    /**
     * Register new user
     */
    async register(userData) {
        try {
            const response = await api.post('/auth/register', userData);

            // Show success message
            if (window.showToast) {
                window.showToast('Registrierung erfolgreich! Bitte melden Sie sich an.', 'success');
            }

            return response;
        } catch (error) {
            const message = this.getErrorMessage(error);
            if (window.showToast) {
                window.showToast(message, 'error');
            }
            throw error;
        }
    }

    /**
     * Login user
     */
    async login(email, password) {
        try {
            const response = await api.post('/auth/login', {
                email,
                password
            });

            // Store tokens
            localStorage.setItem('access_token', response.access_token);
            localStorage.setItem('refresh_token', response.refresh_token);
            localStorage.setItem('token_type', response.token_type);

            // Start token refresh
            this.startTokenRefresh();

            // Emit login event
            window.dispatchEvent(new CustomEvent('auth:login', {
                detail: this.getCurrentUser()
            }));

            if (window.showToast) {
                window.showToast('Erfolgreich angemeldet!', 'success');
            }

            return response;
        } catch (error) {
            const message = this.getErrorMessage(error);
            if (window.showToast) {
                window.showToast(message, 'error');
            }
            throw error;
        }
    }

    /**
     * Logout user
     */
    async logout() {
        try {
            const refreshToken = localStorage.getItem('refresh_token');

            // Call logout endpoint
            if (refreshToken) {
                try {
                    await api.post('/auth/logout', {
                        refresh_token: refreshToken
                    });
                } catch {
                    // Ignore errors on logout endpoint
                }
            }

            this.handleLogout();
        } catch (error) {
            // Always clear local storage on logout, even if API call fails
            this.handleLogout();
        }
    }

    /**
     * Handle logout (clear tokens and redirect)
     */
    handleLogout() {
        // Clear tokens
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('token_type');

        // Stop token refresh
        this.stopTokenRefresh();

        // Emit logout event
        window.dispatchEvent(new CustomEvent('auth:logout'));

        if (window.showToast) {
            window.showToast('Erfolgreich abgemeldet', 'info');
        }
    }

    /**
     * Refresh access token
     */
    async refreshToken() {
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) {
            this.handleLogout();
            return false;
        }

        try {
            const response = await api.post('/auth/refresh', {
                refresh_token: refreshToken
            }, { skipRetry: true });

            // Update tokens
            localStorage.setItem('access_token', response.access_token);
            localStorage.setItem('refresh_token', response.refresh_token);

            return true;
        } catch (error) {
            // Refresh failed, logout
            this.handleLogout();
            return false;
        }
    }

    /**
     * Start automatic token refresh
     */
    startTokenRefresh() {
        // Clear existing interval
        this.stopTokenRefresh();

        // Set new interval
        this.tokenRefreshInterval = setInterval(async () => {
            await this.refreshToken();
        }, this.tokenRefreshTime);
    }

    /**
     * Stop automatic token refresh
     */
    stopTokenRefresh() {
        if (this.tokenRefreshInterval) {
            clearInterval(this.tokenRefreshInterval);
            this.tokenRefreshInterval = null;
        }
    }

    /**
     * Get current user info from API
     */
    async getCurrentUserInfo() {
        try {
            const user = await api.get('/auth/me');
            return user;
        } catch (error) {
            const message = this.getErrorMessage(error);
            if (window.showToast) {
                window.showToast(message, 'error');
            }
            throw error;
        }
    }

    /**
     * Update user profile
     */
    async updateProfile(userData) {
        try {
            const user = await api.put('/auth/me', userData);

            if (window.showToast) {
                window.showToast('Profil erfolgreich aktualisiert', 'success');
            }

            return user;
        } catch (error) {
            const message = this.getErrorMessage(error);
            if (window.showToast) {
                window.showToast(message, 'error');
            }
            throw error;
        }
    }

    /**
     * Change password
     */
    async changePassword(currentPassword, newPassword) {
        try {
            await api.post('/auth/change-password', {
                current_password: currentPassword,
                new_password: newPassword
            });

            if (window.showToast) {
                window.showToast('Passwort erfolgreich geändert', 'success');
            }

            return true;
        } catch (error) {
            const message = this.getErrorMessage(error);
            if (window.showToast) {
                window.showToast(message, 'error');
            }
            throw error;
        }
    }

    /**
     * Get user-friendly error message
     */
    getErrorMessage(error) {
        if (error instanceof window.APIError) {
            // Map common error messages to German
            const errorMap = {
                'Invalid email or password': 'Ungültige E-Mail-Adresse oder Passwort',
                'User account is deactivated': 'Benutzerkonto ist deaktiviert',
                'Email already registered': 'E-Mail-Adresse bereits registriert',
                'Username already taken': 'Benutzername bereits vergeben',
                'Invalid token format': 'Ungültiges Token-Format',
                'User not found': 'Benutzer nicht gefunden',
                'Invalid or expired refresh token': 'Ungültiger oder abgelaufener Refresh Token'
            };

            return errorMap[error.message] || error.message;
        }

        return 'Ein unerwarteter Fehler ist aufgetreten';
    }

    /**
     * Validate password strength
     */
    validatePassword(password) {
        const errors = [];

        if (password.length < 8) {
            errors.push('Passwort muss mindestens 8 Zeichen lang sein');
        }

        if (!/[a-z]/.test(password)) {
            errors.push('Passwort muss mindestens einen Kleinbuchstaben enthalten');
        }

        if (!/[A-Z]/.test(password)) {
            errors.push('Passwort muss mindestens einen Großbuchstaben enthalten');
        }

        if (!/[0-9]/.test(password)) {
            errors.push('Passwort muss mindestens eine Ziffer enthalten');
        }

        if (!/[^a-zA-Z0-9]/.test(password)) {
            errors.push('Passwort muss mindestens ein Sonderzeichen enthalten');
        }

        return {
            valid: errors.length === 0,
            errors
        };
    }

    /**
     * Validate email format
     */
    validateEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }
}

// Create singleton instance
const authManager = new AuthManager();

// Export
window.authManager = authManager;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { authManager, AuthManager };
}
