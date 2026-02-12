import { createFileRoute } from '@tanstack/react-router'
import { useAuth } from '@/lib/auth/AuthContext'
import { usePermissions } from '@/lib/auth/hooks/use-permissions'
import {
    AdminDashboardView,
    EditorDashboardView,
    SimplifiedDashboardView
} from '@/components/dashboard'
import { CompanySetupWizard } from '@/components/onboarding/CompanySetupWizard'
import { AnimatedPage } from '@/components/animations'

export const Route = createFileRoute('/')({
    component: Index,
})

/**
 * Rollenbasiertes Dashboard
 *
 * - Admin/Superuser: Volles Dashboard mit KPIs, Finanz-Übersicht, Management-Tools
 * - Editor: Workflow-fokussiert mit Validierungsaufgaben und Statistiken
 * - Viewer/Azubi: Vereinfachte Ansicht mit Quick-Actions und Upload
 *
 * Der Company-Setup-Wizard wird automatisch angezeigt, wenn:
 * - Der Benutzer Admin ist UND
 * - Noch keine Firma existiert UND
 * - Der Wizard noch nicht übersprungen wurde
 */
function Index() {
    const { user } = useAuth()
    const { isAdmin, isEditor } = usePermissions()

    const userName = user?.full_name || user?.username

    // Admin/Prokurist: Vollständiges Management-Dashboard
    if (isAdmin) {
        return (
            <AnimatedPage>
                {/* Company-Setup-Wizard für Admins ohne Firma */}
                <CompanySetupWizard />
                <AdminDashboardView userName={userName} />
            </AnimatedPage>
        )
    }

    // Editor: Workflow-fokussierte Ansicht
    if (isEditor) {
        return <AnimatedPage><EditorDashboardView userName={userName} /></AnimatedPage>
    }

    // Viewer/Azubi: Vereinfachte Ansicht
    return <AnimatedPage><SimplifiedDashboardView userName={userName} /></AnimatedPage>
}
