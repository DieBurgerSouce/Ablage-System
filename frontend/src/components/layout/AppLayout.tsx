import { useState } from 'react'
import { Sidebar } from './Sidebar'
import { Toaster } from '@/components/ui/toaster'
import { Breadcrumbs } from '@/components/ui/breadcrumb'
import { SessionTimeoutWarning } from '@/components/SessionTimeoutWarning'
import { MobileSidebarProvider, useMobileSidebar } from '@/context/MobileSidebarContext'
import { GlobalAIAssistantV2 as GlobalAIAssistant } from '@/features/ai-assistant'
import { WebSocketStatusIndicator } from './WebSocketStatusIndicator'
// Feature 12: Guided Product Tours
import { TourLauncher } from '@/features/product-tour'
import { OfflineIndicator } from './OfflineIndicator'
import { SmartUploadOverlay } from '@/features/upload/components/SmartUploadOverlay'
import { SpotlightDialog } from '@/features/spotlight'
import { Menu, Bell } from 'lucide-react'
import { cn } from '@/lib/utils'
import { RecentActionsPanel, usePendingReviewCount } from '@/features/auto-learning'
import { NotificationBell } from '@/features/notifications'

function RecentActionsButton() {
    const [panelOpen, setPanelOpen] = useState(false)
    const { data: pendingCounts } = usePendingReviewCount()

    const totalPending = pendingCounts
        ? Object.values(pendingCounts).reduce((sum, count) => sum + count, 0)
        : 0

    return (
        <>
            <button
                onClick={() => setPanelOpen(true)}
                className="relative p-2 rounded-md hover:bg-accent transition-colors"
                aria-label="KI-Aktionen anzeigen"
                title="Letzte KI-Aktionen"
            >
                <Bell className="h-4 w-4" />
                {totalPending > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground">
                        {totalPending > 99 ? '99+' : totalPending}
                    </span>
                )}
            </button>
            <RecentActionsPanel open={panelOpen} onOpenChange={setPanelOpen} />
        </>
    )
}

function AppLayoutInner({ children, id }: { children: React.ReactNode; id?: string }) {
    const { isOpen, toggle, close } = useMobileSidebar();

    return (
        <SmartUploadOverlay>
            <div className="flex h-screen bg-background overflow-hidden">
                {/* Mobile Overlay */}
                {isOpen && (
                    <div
                        className="fixed inset-0 bg-black/50 z-40 md:hidden"
                        onClick={close}
                        aria-hidden="true"
                    />
                )}

                {/* Sidebar Container - responsive */}
                <div
                    data-tour="sidebar"
                    className={cn(
                        // Base: Fixed positioning on mobile, relative on desktop
                        "fixed inset-y-0 left-0 z-50 md:relative md:z-0",
                        // Transform: Slide in/out on mobile, always visible on desktop
                        "transform transition-transform duration-200 ease-in-out",
                        isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
                    )}
                >
                    <Sidebar onNavigate={close} />
                </div>

                {/* Main Content */}
                <main
                    id={id}
                    className="flex-1 flex flex-col overflow-hidden relative w-full"
                    tabIndex={-1}
                    role="main"
                    aria-label="Hauptinhalt"
                >
                    {/* Offline Banner */}
                    <OfflineIndicator />
                    {/* Mobile Header with Hamburger + Breadcrumbs + WebSocket Status */}
                    <div data-tour="search-bar" className="flex-none sticky top-0 z-10 bg-background/80 backdrop-blur-sm border-b border-white/5 px-4 md:px-6 py-3">
                        <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-3 flex-1 min-w-0">
                                {/* Hamburger Menu - only visible on mobile */}
                                <button
                                    onClick={toggle}
                                    className="md:hidden p-2 -ml-2 rounded-md hover:bg-accent flex-shrink-0"
                                    aria-label="Menü öffnen"
                                    aria-expanded={isOpen}
                                >
                                    <Menu className="h-5 w-5" />
                                </button>
                                <Breadcrumbs showHomeIcon maxItems={5} />
                            </div>
                            {/* KI-Aktionen, Tour Launcher & WebSocket Status Indicator */}
                            <div className="flex items-center gap-1 flex-shrink-0">
                                <NotificationBell />
                                <RecentActionsButton />
                                <TourLauncher variant="icon" />
                                <WebSocketStatusIndicator />
                            </div>
                        </div>
                    </div>
                    {/* Page Content */}
                    <div className="flex-1 overflow-auto relative">
                        {children}
                    </div>
                </main>
                <Toaster />
                {/* Session Timeout Warning - Zeigt Warnung wenn Session bald abläuft */}
                <SessionTimeoutWarning />
                {/* Global AI Assistant - Floating Widget auf jeder Seite */}
                <GlobalAIAssistant />
            </div>
            <SpotlightDialog />
        </SmartUploadOverlay>
    )
}

export function AppLayout({ children, id }: { children: React.ReactNode; id?: string }) {
    return (
        <MobileSidebarProvider>
            <AppLayoutInner id={id}>{children}</AppLayoutInner>
        </MobileSidebarProvider>
    )
}
