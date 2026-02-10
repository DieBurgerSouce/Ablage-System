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
import { Menu } from 'lucide-react'
import { cn } from '@/lib/utils'

function AppLayoutInner({ children, id }: { children: React.ReactNode; id?: string }) {
    const { isOpen, toggle, close } = useMobileSidebar();

    return (
        <div id={id} className="flex h-screen bg-background overflow-hidden">
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
                        {/* Tour Launcher & WebSocket Status Indicator */}
                        <div className="flex items-center gap-1 flex-shrink-0">
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
            {/* Session Timeout Warning - Zeigt Warnung wenn Session bald ablaeuft */}
            <SessionTimeoutWarning />
            {/* Global AI Assistant - Floating Widget auf jeder Seite */}
            <GlobalAIAssistant />
        </div>
    )
}

export function AppLayout({ children, id }: { children: React.ReactNode; id?: string }) {
    return (
        <MobileSidebarProvider>
            <AppLayoutInner id={id}>{children}</AppLayoutInner>
        </MobileSidebarProvider>
    )
}
