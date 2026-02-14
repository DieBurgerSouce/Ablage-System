/**
 * Authentication Helper Library for K6 Load Tests
 *
 * Provides centralized authentication handling:
 * - Login with automatic retry
 * - Token refresh handling
 * - Token caching per VU
 * - Graceful handling of rate limits
 */

import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { BASE_URL, API_PREFIX, TEST_USER, getHeaders } from '../config.js';

// ==================== Auth Metrics ====================

export const authMetrics = {
  loginDuration: new Trend('auth_lib_login_duration', true),
  refreshDuration: new Trend('auth_lib_refresh_duration', true),
  authErrors: new Rate('auth_lib_errors'),
  rateLimitHits: new Counter('auth_lib_rate_limits'),
  tokenRefreshes: new Counter('auth_lib_token_refreshes'),
};

// ==================== Token Storage ====================

// Per-VU token storage (not shared between VUs)
const tokenStore = {
  accessToken: null,
  refreshToken: null,
  expiresAt: null,
  userId: null,
};

// Token expiry buffer (refresh 60 seconds before expiry)
const TOKEN_EXPIRY_BUFFER_MS = 60000;

// ==================== Core Auth Functions ====================

/**
 * Login and retrieve tokens
 * @param {string} email - User email
 * @param {string} password - User password
 * @param {Object} options - Additional options
 * @returns {Object|null} Token object or null on failure
 */
export function login(email = null, password = null, options = {}) {
  const userEmail = email || TEST_USER.email;
  const userPassword = password || TEST_USER.password;
  const maxRetries = options.maxRetries || 3;
  const retryDelay = options.retryDelay || 1000;

  let lastError = null;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    const payload = JSON.stringify({
      email: userEmail,
      password: userPassword,
    });

    const response = http.post(
      `${BASE_URL}${API_PREFIX}/auth/login`,
      payload,
      {
        headers: getHeaders(),
        tags: { endpoint: 'login', attempt: String(attempt) },
        timeout: '10s',
      }
    );

    authMetrics.loginDuration.add(response.timings.duration);

    // Handle rate limiting
    if (response.status === 429) {
      authMetrics.rateLimitHits.add(1);

      if (attempt < maxRetries) {
        const retryAfter = parseRetryAfter(response);
        const waitTime = retryAfter || retryDelay * attempt;
        console.log(`Rate limited on login (attempt ${attempt}), waiting ${waitTime}ms`);
        __ENV.SLEEP_MS && sleep(waitTime / 1000);
        continue;
      }

      lastError = 'Rate limited';
      break;
    }

    // Check for success
    const success = check(response, {
      'login status is 200': (r) => r.status === 200,
    });

    if (success) {
      try {
        const body = JSON.parse(response.body);

        if (body.access_token) {
          const tokens = {
            accessToken: body.access_token,
            refreshToken: body.refresh_token || null,
            expiresIn: body.expires_in || 900, // Default 15 min
            userId: body.user_id || body.user?.id || null,
          };

          // Store tokens
          storeTokens(tokens);

          authMetrics.authErrors.add(0);
          return tokens;
        }
      } catch (e) {
        lastError = `Parse error: ${e.message}`;
      }
    } else {
      lastError = `HTTP ${response.status}`;
    }

    // Wait before retry
    if (attempt < maxRetries) {
      __ENV.SLEEP_MS && sleep(retryDelay / 1000);
    }
  }

  authMetrics.authErrors.add(1);
  console.error(`Login failed after ${maxRetries} attempts: ${lastError}`);
  return null;
}

/**
 * Refresh the access token using refresh token
 * @param {string} refreshToken - Refresh token (optional, uses stored token)
 * @returns {Object|null} New token object or null on failure
 */
export function refreshTokens(refreshToken = null) {
  const token = refreshToken || tokenStore.refreshToken;

  if (!token) {
    console.error('No refresh token available');
    return null;
  }

  const payload = JSON.stringify({
    refresh_token: token,
  });

  const response = http.post(
    `${BASE_URL}${API_PREFIX}/auth/refresh`,
    payload,
    {
      headers: getHeaders(),
      tags: { endpoint: 'refresh' },
      timeout: '10s',
    }
  );

  authMetrics.refreshDuration.add(response.timings.duration);

  if (response.status === 429) {
    authMetrics.rateLimitHits.add(1);
    return null;
  }

  if (response.status === 200) {
    try {
      const body = JSON.parse(response.body);

      if (body.access_token) {
        const tokens = {
          accessToken: body.access_token,
          refreshToken: body.refresh_token || token,
          expiresIn: body.expires_in || 900,
          userId: tokenStore.userId,
        };

        storeTokens(tokens);
        authMetrics.tokenRefreshes.add(1);
        authMetrics.authErrors.add(0);
        return tokens;
      }
    } catch (e) {
      console.error(`Refresh token parse error: ${e.message}`);
    }
  }

  authMetrics.authErrors.add(1);
  return null;
}

/**
 * Get a valid access token, refreshing if necessary
 * @param {Object} options - Options
 * @returns {string|null} Valid access token or null
 */
export function getValidToken(options = {}) {
  const forceLogin = options.forceLogin || false;
  const forceRefresh = options.forceRefresh || false;

  // Check if we need to login
  if (!tokenStore.accessToken || forceLogin) {
    const result = login();
    return result ? result.accessToken : null;
  }

  // Check if token is expired or about to expire
  const now = Date.now();
  const isExpired = tokenStore.expiresAt && now >= tokenStore.expiresAt - TOKEN_EXPIRY_BUFFER_MS;

  if (isExpired || forceRefresh) {
    // Try to refresh
    if (tokenStore.refreshToken) {
      const result = refreshTokens();
      if (result) {
        return result.accessToken;
      }
    }

    // Refresh failed, try full login
    const result = login();
    return result ? result.accessToken : null;
  }

  return tokenStore.accessToken;
}

/**
 * Ensure we have valid authentication
 * Convenience wrapper for getValidToken
 * @returns {string|null} Valid access token or null
 */
export function ensureAuth() {
  return getValidToken();
}

/**
 * Logout and clear stored tokens
 * @param {string} accessToken - Access token (optional, uses stored token)
 * @returns {boolean} True if logout successful
 */
export function logout(accessToken = null) {
  const token = accessToken || tokenStore.accessToken;

  if (!token) {
    clearTokens();
    return true;
  }

  const response = http.post(
    `${BASE_URL}${API_PREFIX}/auth/logout`,
    null,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'logout' },
    }
  );

  clearTokens();

  return response.status >= 200 && response.status < 300;
}

/**
 * Get current user information
 * @param {string} accessToken - Access token (optional, uses stored token)
 * @returns {Object|null} User object or null
 */
export function getCurrentUser(accessToken = null) {
  const token = accessToken || getValidToken();

  if (!token) {
    return null;
  }

  const response = http.get(
    `${BASE_URL}${API_PREFIX}/auth/me`,
    {
      headers: getHeaders(token),
      tags: { endpoint: 'me' },
    }
  );

  if (response.status === 200) {
    try {
      return JSON.parse(response.body);
    } catch (e) {
      return null;
    }
  }

  return null;
}

// ==================== Helper Functions ====================

/**
 * Store tokens in VU-local storage
 * @param {Object} tokens - Token object
 */
function storeTokens(tokens) {
  tokenStore.accessToken = tokens.accessToken;
  tokenStore.refreshToken = tokens.refreshToken;
  tokenStore.userId = tokens.userId;

  // Calculate expiry time
  if (tokens.expiresIn) {
    tokenStore.expiresAt = Date.now() + (tokens.expiresIn * 1000);
  }
}

/**
 * Clear stored tokens
 */
function clearTokens() {
  tokenStore.accessToken = null;
  tokenStore.refreshToken = null;
  tokenStore.expiresAt = null;
  tokenStore.userId = null;
}

/**
 * Parse Retry-After header
 * @param {Object} response - HTTP response
 * @returns {number|null} Retry delay in ms or null
 */
function parseRetryAfter(response) {
  const header = response.headers['Retry-After'] || response.headers['retry-after'];

  if (!header) {
    return null;
  }

  // Try to parse as seconds
  const seconds = parseInt(header, 10);
  if (!isNaN(seconds)) {
    return seconds * 1000;
  }

  // Try to parse as date
  const date = new Date(header);
  if (!isNaN(date.getTime())) {
    return Math.max(0, date.getTime() - Date.now());
  }

  return null;
}

/**
 * Get stored token info (for debugging)
 * @returns {Object} Token info
 */
export function getTokenInfo() {
  return {
    hasAccessToken: !!tokenStore.accessToken,
    hasRefreshToken: !!tokenStore.refreshToken,
    expiresAt: tokenStore.expiresAt,
    isExpired: tokenStore.expiresAt ? Date.now() >= tokenStore.expiresAt : null,
    userId: tokenStore.userId,
  };
}

// ==================== Exports ====================

export default {
  login,
  refreshTokens,
  getValidToken,
  ensureAuth,
  logout,
  getCurrentUser,
  getTokenInfo,
  authMetrics,
};
