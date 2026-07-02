import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { authService, type User, type LoginResult, type AuthResponse, type TwoFactorRequiredResponse } from '@/lib/api/services/auth';
import { logger } from '@/lib/logger';

// Type guard to check if result requires 2FA
export function is2FARequired(result: LoginResult): result is TwoFactorRequiredResponse {
    return 'requires_2fa' in result && result.requires_2fa === true;
}

// Session-Konstanten
const SESSION_DURATION_MS = 15 * 60 * 1000; // 15 Minuten (Standard JWT Expiry)
const SESSION_WARNING_THRESHOLD_MS = 5 * 60 * 1000; // Warnung 5 Minuten vor Ablauf

interface AuthContextType {
    user: User | null;
    isLoading: boolean;
    login: (email: string, password: string) => Promise<LoginResult>;
    verify2FA: (tempToken: string, code: string) => Promise<AuthResponse>;
    logout: typeof authService.logout;
    isAuthenticated: boolean;
    /** Session-Ablaufzeit als Unix Timestamp */
    sessionExpiresAt: number | null;
    /** Verbleibende Zeit bis Session abläuft (in ms) */
    sessionTimeRemaining: number | null;
    /** Zeigt an ob Session bald abläuft (< 5 min) */
    sessionExpiringSoon: boolean;
    /** Session verlängern (Token refresh) */
    refreshSession: () => Promise<void>;
    /** Letzte Aktivität aktualisieren */
    recordActivity: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [sessionExpiresAt, setSessionExpiresAt] = useState<number | null>(null);
    const [sessionTimeRemaining, setSessionTimeRemaining] = useState<number | null>(null);

    // Refs für Timer
    const sessionTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const activityTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Session-Ablauf berechnen
    const updateSessionExpiry = useCallback(() => {
        const now = Date.now();
        setSessionExpiresAt(now + SESSION_DURATION_MS);
    }, []);

    // Timer für verbleibende Zeit
    useEffect(() => {
        if (!sessionExpiresAt || !user) {
            setSessionTimeRemaining(null);
            return;
        }

        const updateRemaining = () => {
            const remaining = sessionExpiresAt - Date.now();
            setSessionTimeRemaining(Math.max(0, remaining));

            // Auto-Logout wenn abgelaufen
            if (remaining <= 0) {
                authService.logout();
                setUser(null);
            }
        };

        // Sofort aktualisieren
        updateRemaining();

        // Jede Sekunde aktualisieren
        sessionTimerRef.current = setInterval(updateRemaining, 1000);

        return () => {
            if (sessionTimerRef.current) {
                clearInterval(sessionTimerRef.current);
            }
        };
    }, [sessionExpiresAt, user]);

    // Session-Expiring-Soon berechnen
    const sessionExpiringSoon = sessionTimeRemaining !== null && sessionTimeRemaining <= SESSION_WARNING_THRESHOLD_MS && sessionTimeRemaining > 0;

    // Session verlängern
    const refreshSession = useCallback(async () => {
        try {
            await authService.refreshToken();
            updateSessionExpiry();
        } catch (error) {
            logger.error('Session refresh fehlgeschlagen', error);
            authService.logout();
            setUser(null);
        }
    }, [updateSessionExpiry]);

    // Aktivität aufzeichnen (verlängert implizit die Session)
    const recordActivity = useCallback(() => {
        // Debounce: Nur alle 30 Sekunden tatsaechlich refreshen
        if (activityTimeoutRef.current) return;

        activityTimeoutRef.current = setTimeout(() => {
            activityTimeoutRef.current = null;
        }, 30000);

        // Session-Expiry aktualisieren bei Aktivität
        updateSessionExpiry();
    }, [updateSessionExpiry]);

    // Cleanup bei Unmount
    useEffect(() => {
        return () => {
            if (sessionTimerRef.current) clearInterval(sessionTimerRef.current);
            if (activityTimeoutRef.current) clearTimeout(activityTimeoutRef.current);
        };
    }, []);

    // W2-22/F1: Auf 'session-expired' reagieren (vom API-Interceptor bei
    // fehlgeschlagenem Token-Refresh dispatcht). Der Interceptor hat den
    // sessionStorage bereits geleert -> hier NUR den lokalen React-State
    // zuruecksetzen (KEIN erneuter API-Call/Redirect). setUser(null) laesst
    // isAuthenticated auf false fallen, womit der Route-Guard in __root.tsx
    // <Navigate to="/login"> ausloest. Ohne diesen Handler bliebe
    // isAuthenticated=true und es entstuende eine 401-Welle hinter dem Modal.
    useEffect(() => {
        const handleSessionExpired = () => {
            if (sessionTimerRef.current) clearInterval(sessionTimerRef.current);
            if (activityTimeoutRef.current) {
                clearTimeout(activityTimeoutRef.current);
                activityTimeoutRef.current = null;
            }
            setUser(null);
            setSessionExpiresAt(null);
            setSessionTimeRemaining(null);
            // User-Kontext aus Loki-Logging entfernen und gepufferte Logs flushen
            logger.setUser(null);
            logger.flush();
        };

        window.addEventListener('session-expired', handleSessionExpired);

        return () => {
            window.removeEventListener('session-expired', handleSessionExpired);
        };
    }, []);

    useEffect(() => {
        const initAuth = async () => {
            try {
                const currentUser = authService.getCurrentUser();
                if (currentUser) {
                    setUser(currentUser);
                    updateSessionExpiry();
                    // Setze User-Kontext für Loki-Logging bei bestehendem Session
                    // SECURITY: Keine PII (E-Mail) in Logs!
                    logger.setUser({ id: currentUser.id });
                }
            } catch (error) {
                logger.error('Auth-Initialisierung fehlgeschlagen', error);
                authService.logout();
            } finally {
                setIsLoading(false);
            }
        };

        initAuth();
    }, [updateSessionExpiry]);

    const login = async (email: string, password: string): Promise<LoginResult> => {
        const response = await authService.login(email, password);
        // Only set user if we got a full auth response (not 2FA required)
        if (!is2FARequired(response)) {
            setUser(response.user);
            updateSessionExpiry();
            // Setze User-Kontext für Loki-Logging
            // SECURITY: Keine PII (E-Mail) in Logs!
            logger.setUser({ id: response.user.id });
        }
        return response;
    };

    const verify2FA = async (tempToken: string, code: string): Promise<AuthResponse> => {
        const response = await authService.verify2FA(tempToken, code);
        setUser(response.user);
        updateSessionExpiry();
        // Setze User-Kontext für Loki-Logging
        // SECURITY: Keine PII (E-Mail) in Logs!
        logger.setUser({ id: response.user.id });
        return response;
    };

    const logout = () => {
        if (sessionTimerRef.current) clearInterval(sessionTimerRef.current);
        authService.logout();
        setUser(null);
        setSessionExpiresAt(null);
        setSessionTimeRemaining(null);
        // Entferne User-Kontext aus Loki-Logging und flushe gepufferte Logs
        logger.setUser(null);
        logger.flush();
    };

    return (
        <AuthContext.Provider value={{
            user,
            isLoading,
            login,
            verify2FA,
            logout,
            isAuthenticated: !!user,
            sessionExpiresAt,
            sessionTimeRemaining,
            sessionExpiringSoon,
            refreshSession,
            recordActivity,
        }}>
            {children}
        </AuthContext.Provider>
    );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
