import React, { createContext, useContext, useEffect, useState } from 'react';
import { authService, type User } from '@/lib/api/services/auth';

interface AuthContextType {
    user: User | null;
    isLoading: boolean;
    login: typeof authService.login;
    logout: typeof authService.logout;
    isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const initAuth = async () => {
            try {
                const currentUser = authService.getCurrentUser();
                if (currentUser) {
                    setUser(currentUser);
                    // Optional: Verify token validity with backend here
                }
            } catch (error) {
                console.error('Auth initialization failed', error);
                authService.logout();
            } finally {
                setIsLoading(false);
            }
        };

        initAuth();
    }, []);

    const login: typeof authService.login = async (email, password) => {
        const response = await authService.login(email, password);
        setUser(response.user);
        return response;
    };

    const logout = () => {
        authService.logout();
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{
            user,
            isLoading,
            login,
            logout,
            isAuthenticated: !!user
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
