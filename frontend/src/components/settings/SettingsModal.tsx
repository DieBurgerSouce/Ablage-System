/**
 * Einstellungen Modal Komponente.
 *
 * Haupt-Modal für alle Benutzer- und Admin-Einstellungen.
 * Tabs: Konto, Anzeige, OCR, Benachrichtigungen, Datenschutz, Firmendaten (Admin), Tags (Admin)
 */

import { useState } from 'react';
import { Settings, Monitor, Cpu, Bell, Shield, Building2, UserCircle, Tag } from 'lucide-react';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAuth } from '@/lib/auth/AuthContext';
import { AccountSettingsTab } from './AccountSettingsTab';
import { DisplaySettingsTab } from './DisplaySettingsTab';
import { OCRSettingsTab } from './OCRSettingsTab';
import { NotificationSettingsTab } from './NotificationSettingsTab';
import { PrivacySettingsTab } from './PrivacySettingsTab';
import { CompanySettingsTab } from './CompanySettingsTab';
import { TagSettingsTab } from './TagSettingsTab';

export function SettingsModal() {
    const [open, setOpen] = useState(false);
    const { user } = useAuth();

    const isAdmin = user?.is_superuser || user?.role === 'admin';

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <button
                    className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                    aria-label="Einstellungen öffnen"
                >
                    <Settings className="w-4 h-4" aria-hidden="true" />
                    Einstellungen
                </button>
            </DialogTrigger>
            <DialogContent className="max-w-4xl max-h-[85vh] overflow-hidden flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Settings className="w-5 h-5" />
                        Einstellungen
                    </DialogTitle>
                    <DialogDescription>
                        Passen Sie Ihre persönlichen Einstellungen und Präferenzen an.
                    </DialogDescription>
                </DialogHeader>

                <Tabs defaultValue="account" className="flex-1 overflow-hidden flex flex-col">
                    <TabsList className={`grid w-full ${isAdmin ? 'grid-cols-7' : 'grid-cols-5'}`}>
                        <TabsTrigger value="account" className="flex items-center gap-1.5">
                            <UserCircle className="w-3.5 h-3.5" />
                            <span className="hidden sm:inline">Konto</span>
                        </TabsTrigger>
                        <TabsTrigger value="display" className="flex items-center gap-1.5">
                            <Monitor className="w-3.5 h-3.5" />
                            <span className="hidden sm:inline">Anzeige</span>
                        </TabsTrigger>
                        <TabsTrigger value="ocr" className="flex items-center gap-1.5">
                            <Cpu className="w-3.5 h-3.5" />
                            <span className="hidden sm:inline">OCR</span>
                        </TabsTrigger>
                        <TabsTrigger value="notifications" className="flex items-center gap-1.5">
                            <Bell className="w-3.5 h-3.5" />
                            <span className="hidden sm:inline">Benachr.</span>
                        </TabsTrigger>
                        <TabsTrigger value="privacy" className="flex items-center gap-1.5">
                            <Shield className="w-3.5 h-3.5" />
                            <span className="hidden sm:inline">Datenschutz</span>
                        </TabsTrigger>
                        {isAdmin && (
                            <TabsTrigger value="company" className="flex items-center gap-1.5">
                                <Building2 className="w-3.5 h-3.5" />
                                <span className="hidden sm:inline">Firma</span>
                            </TabsTrigger>
                        )}
                        {isAdmin && (
                            <TabsTrigger value="tags" className="flex items-center gap-1.5">
                                <Tag className="w-3.5 h-3.5" />
                                <span className="hidden sm:inline">Tags</span>
                            </TabsTrigger>
                        )}
                    </TabsList>

                    <div className="flex-1 overflow-y-auto mt-4 pr-2">
                        <TabsContent value="account" className="mt-0">
                            <AccountSettingsTab onClose={() => setOpen(false)} />
                        </TabsContent>
                        <TabsContent value="display" className="mt-0">
                            <DisplaySettingsTab />
                        </TabsContent>
                        <TabsContent value="ocr" className="mt-0">
                            <OCRSettingsTab />
                        </TabsContent>
                        <TabsContent value="notifications" className="mt-0">
                            <NotificationSettingsTab />
                        </TabsContent>
                        <TabsContent value="privacy" className="mt-0">
                            <PrivacySettingsTab />
                        </TabsContent>
                        {isAdmin && (
                            <TabsContent value="company" className="mt-0">
                                <CompanySettingsTab />
                            </TabsContent>
                        )}
                        {isAdmin && (
                            <TabsContent value="tags" className="mt-0">
                                <TagSettingsTab />
                            </TabsContent>
                        )}
                    </div>
                </Tabs>
            </DialogContent>
        </Dialog>
    );
}
