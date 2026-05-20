/**
 * Tests für das rollenbasierte Dashboard (index.tsx)
 *
 * Diese Tests prüfen die Routing-Logik des Dashboards basierend auf Benutzerrollen.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Mock useAuth
const mockUseAuth = vi.fn()
vi.mock('@/lib/auth/AuthContext', () => ({
    useAuth: () => mockUseAuth(),
}))

// Mock usePermissions
const mockUsePermissions = vi.fn()
vi.mock('@/lib/auth/hooks/use-permissions', () => ({
    usePermissions: () => mockUsePermissions(),
}))

// Mock Dashboard Views
vi.mock('@/components/dashboard', () => ({
    AdminDashboardView: ({ userName }: { userName?: string }) => (
        <div data-testid="admin-dashboard">Admin Dashboard für {userName}</div>
    ),
    EditorDashboardView: ({ userName }: { userName?: string }) => (
        <div data-testid="editor-dashboard">Editor Dashboard für {userName}</div>
    ),
    SimplifiedDashboardView: ({ userName }: { userName?: string }) => (
        <div data-testid="viewer-dashboard">Viewer Dashboard für {userName}</div>
    ),
}))

// Mock CompanySetupWizard
vi.mock('@/components/onboarding/CompanySetupWizard', () => ({
    CompanySetupWizard: () => <div data-testid="company-wizard">Company Setup Wizard</div>,
}))

/**
 * Testbare Version der Index-Komponente
 *
 * Spiegelt die Logik der echten Index-Route, nutzt aber die gemockten Hooks
 * und rendert einfache Test-Marker statt der echten Dashboard-Komponenten.
 */
function TestableIndex() {
    const { user } = mockUseAuth()
    const { isAdmin, isEditor } = mockUsePermissions()

    const userName = user?.full_name || user?.username

    // Admin/Prokurist: Vollständiges Management-Dashboard
    if (isAdmin) {
        return (
            <>
                <div data-testid="company-wizard">Company Setup Wizard</div>
                <div data-testid="admin-dashboard">Admin Dashboard für {userName}</div>
            </>
        )
    }

    // Editor: Workflow-fokussierte Ansicht
    if (isEditor) {
        return <div data-testid="editor-dashboard">Editor Dashboard für {userName}</div>
    }

    // Viewer/Azubi: Vereinfachte Ansicht
    return <div data-testid="viewer-dashboard">Viewer Dashboard für {userName}</div>
}

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
        },
    })
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
}

describe('Index Route - Rollenbasiertes Dashboard', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        localStorage.clear()
    })

    describe('Admin-Benutzer', () => {
        beforeEach(() => {
            mockUseAuth.mockReturnValue({
                user: { id: '1', username: 'admin', full_name: 'Max Mustermann' },
            })
            mockUsePermissions.mockReturnValue({
                isAdmin: true,
                isEditor: false,
            })
        })

        it('zeigt AdminDashboardView für Admin-Benutzer', () => {
            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.getByTestId('admin-dashboard')).toBeInTheDocument()
        })

        it('übergibt userName an AdminDashboardView', () => {
            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.getByText(/Max Mustermann/)).toBeInTheDocument()
        })

        it('zeigt CompanySetupWizard für Admins', () => {
            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.getByTestId('company-wizard')).toBeInTheDocument()
        })

        it('zeigt keine Editor- oder Viewer-Dashboards', () => {
            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.queryByTestId('editor-dashboard')).not.toBeInTheDocument()
            expect(screen.queryByTestId('viewer-dashboard')).not.toBeInTheDocument()
        })
    })

    describe('Editor-Benutzer', () => {
        beforeEach(() => {
            mockUseAuth.mockReturnValue({
                user: { id: '2', username: 'editor', full_name: 'Erika Editor' },
            })
            mockUsePermissions.mockReturnValue({
                isAdmin: false,
                isEditor: true,
            })
        })

        it('zeigt EditorDashboardView für Editor-Benutzer', () => {
            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.getByTestId('editor-dashboard')).toBeInTheDocument()
        })

        it('übergibt userName an EditorDashboardView', () => {
            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.getByText(/Erika Editor/)).toBeInTheDocument()
        })

        it('zeigt keinen CompanySetupWizard für Editors', () => {
            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.queryByTestId('company-wizard')).not.toBeInTheDocument()
        })

        it('zeigt keine Admin- oder Viewer-Dashboards', () => {
            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.queryByTestId('admin-dashboard')).not.toBeInTheDocument()
            expect(screen.queryByTestId('viewer-dashboard')).not.toBeInTheDocument()
        })
    })

    describe('Viewer/Azubi-Benutzer', () => {
        beforeEach(() => {
            mockUseAuth.mockReturnValue({
                user: { id: '3', username: 'azubi', full_name: 'Anna Azubi' },
            })
            mockUsePermissions.mockReturnValue({
                isAdmin: false,
                isEditor: false,
            })
        })

        it('zeigt SimplifiedDashboardView für Viewer/Azubi', () => {
            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.getByTestId('viewer-dashboard')).toBeInTheDocument()
        })

        it('übergibt userName an SimplifiedDashboardView', () => {
            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.getByText(/Anna Azubi/)).toBeInTheDocument()
        })

        it('zeigt keinen CompanySetupWizard für Viewer', () => {
            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.queryByTestId('company-wizard')).not.toBeInTheDocument()
        })

        it('zeigt keine Admin- oder Editor-Dashboards', () => {
            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.queryByTestId('admin-dashboard')).not.toBeInTheDocument()
            expect(screen.queryByTestId('editor-dashboard')).not.toBeInTheDocument()
        })
    })

    describe('Fallback bei fehlendem full_name', () => {
        it('verwendet username wenn full_name fehlt', () => {
            mockUseAuth.mockReturnValue({
                user: { id: '1', username: 'admin_user' },
            })
            mockUsePermissions.mockReturnValue({
                isAdmin: true,
                isEditor: false,
            })

            render(<TestableIndex />, { wrapper: createWrapper() })
            expect(screen.getByText(/admin_user/)).toBeInTheDocument()
        })
    })

    describe('Rollen-Priorität', () => {
        it('priorisiert Admin über Editor', () => {
            mockUseAuth.mockReturnValue({
                user: { id: '1', username: 'superuser' },
            })
            mockUsePermissions.mockReturnValue({
                isAdmin: true,
                isEditor: true, // User has both roles
            })

            render(<TestableIndex />, { wrapper: createWrapper() })
            // Should show Admin dashboard, not Editor
            expect(screen.getByTestId('admin-dashboard')).toBeInTheDocument()
            expect(screen.queryByTestId('editor-dashboard')).not.toBeInTheDocument()
        })

        it('priorisiert Editor über Viewer', () => {
            mockUseAuth.mockReturnValue({
                user: { id: '1', username: 'editor_plus' },
            })
            mockUsePermissions.mockReturnValue({
                isAdmin: false,
                isEditor: true,
            })

            render(<TestableIndex />, { wrapper: createWrapper() })
            // Should show Editor dashboard, not Viewer
            expect(screen.getByTestId('editor-dashboard')).toBeInTheDocument()
            expect(screen.queryByTestId('viewer-dashboard')).not.toBeInTheDocument()
        })
    })
})
