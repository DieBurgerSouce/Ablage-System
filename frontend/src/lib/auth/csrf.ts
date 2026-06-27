/**
 * G03: CSRF-Double-Submit-Helfer.
 *
 * Seit der Umstellung auf httpOnly-Auth-Cookies sendet der Browser den Auth-Token
 * automatisch mit (same-origin). Da damit der Bearer-Bypass der CSRFMiddleware
 * entfaellt, muss bei state-changing Requests (POST/PUT/PATCH/DELETE) das
 * nicht-httpOnly `csrf_token`-Cookie ausgelesen und im `X-CSRF-Token`-Header
 * gespiegelt werden (Double-Submit-Pattern, siehe app/middleware/csrf.py).
 */

/** Liest ein Cookie nach Namen aus document.cookie (oder null). */
export function readCookie(name: string): string | null {
    if (typeof document === 'undefined' || !document.cookie) return null;
    const escaped = name.replace(/[.$?*|{}()[\]\\/+^]/g, '\\$&');
    const match = document.cookie.match(new RegExp('(?:^|; )' + escaped + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : null;
}

/** CSRF-Token aus dem csrf_token-Cookie (oder null, falls noch keins gesetzt). */
export function getCsrfToken(): string | null {
    return readCookie('csrf_token');
}

/**
 * Liefert die CSRF-Header fuer fetch()-basierte state-changing Requests (SSE/Streaming).
 * Gibt ein leeres Objekt zurueck, wenn (noch) kein Token vorliegt.
 */
export function csrfHeaders(): Record<string, string> {
    const token = getCsrfToken();
    return token ? { 'X-CSRF-Token': token } : {};
}
