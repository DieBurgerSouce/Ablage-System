/**
 * Navigation Component Stories
 *
 * Navigation-Komponenten für Visual Regression Testing.
 * Tabs, Breadcrumbs, Pagination, etc.
 */

import type { Meta, StoryObj } from '@storybook/react';
import { useState } from 'react';
import {
    ChevronLeft,
    ChevronRight,
    ChevronsLeft,
    ChevronsRight,
    FileText,
    Home,
    Inbox,
    Settings,
    User,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    Breadcrumb,
    BreadcrumbItem,
    BreadcrumbLink,
    BreadcrumbList,
    BreadcrumbPage,
    BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

const meta: Meta = {
    title: 'UI/Navigation',
    parameters: {
        layout: 'centered',
        docs: {
            description: {
                component: 'Navigation-Komponenten: Tabs, Breadcrumbs, Pagination.',
            },
        },
    },
    tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof meta>;

// ==================== Tabs ====================

export const TabsDefault: Story = {
    render: () => (
        <Tabs defaultValue="account" className="w-[400px]">
            <TabsList>
                <TabsTrigger value="account">Konto</TabsTrigger>
                <TabsTrigger value="password">Passwort</TabsTrigger>
                <TabsTrigger value="settings">Einstellungen</TabsTrigger>
            </TabsList>
            <TabsContent value="account" className="p-4 border rounded-lg mt-2">
                <h3 className="font-medium">Kontoinformationen</h3>
                <p className="text-sm text-muted-foreground mt-1">
                    Verwalten Sie hier Ihre Kontodaten.
                </p>
            </TabsContent>
            <TabsContent value="password" className="p-4 border rounded-lg mt-2">
                <h3 className="font-medium">Passwort ändern</h3>
                <p className="text-sm text-muted-foreground mt-1">
                    Aktualisieren Sie Ihr Passwort.
                </p>
            </TabsContent>
            <TabsContent value="settings" className="p-4 border rounded-lg mt-2">
                <h3 className="font-medium">Einstellungen</h3>
                <p className="text-sm text-muted-foreground mt-1">
                    Passen Sie Ihre Praeferenzen an.
                </p>
            </TabsContent>
        </Tabs>
    ),
};

export const TabsWithIcons: Story = {
    render: () => (
        <Tabs defaultValue="documents" className="w-[450px]">
            <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="documents" className="flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    <span className="hidden sm:inline">Dokumente</span>
                </TabsTrigger>
                <TabsTrigger value="inbox" className="flex items-center gap-2">
                    <Inbox className="h-4 w-4" />
                    <span className="hidden sm:inline">Posteingang</span>
                </TabsTrigger>
                <TabsTrigger value="profile" className="flex items-center gap-2">
                    <User className="h-4 w-4" />
                    <span className="hidden sm:inline">Profil</span>
                </TabsTrigger>
                <TabsTrigger value="settings" className="flex items-center gap-2">
                    <Settings className="h-4 w-4" />
                    <span className="hidden sm:inline">Einstellungen</span>
                </TabsTrigger>
            </TabsList>
            <TabsContent value="documents" className="p-4 border rounded-lg mt-2">
                Dokumente-Inhalt
            </TabsContent>
            <TabsContent value="inbox" className="p-4 border rounded-lg mt-2">
                Posteingang-Inhalt
            </TabsContent>
            <TabsContent value="profile" className="p-4 border rounded-lg mt-2">
                Profil-Inhalt
            </TabsContent>
            <TabsContent value="settings" className="p-4 border rounded-lg mt-2">
                Einstellungen-Inhalt
            </TabsContent>
        </Tabs>
    ),
};

export const TabsVertical: Story = {
    render: () => (
        <div className="flex gap-4 w-[500px]">
            <Tabs defaultValue="general" orientation="vertical" className="flex">
                <TabsList className="flex-col h-auto">
                    <TabsTrigger value="general" className="w-full justify-start">
                        Allgemein
                    </TabsTrigger>
                    <TabsTrigger value="security" className="w-full justify-start">
                        Sicherheit
                    </TabsTrigger>
                    <TabsTrigger value="notifications" className="w-full justify-start">
                        Benachrichtigungen
                    </TabsTrigger>
                    <TabsTrigger value="privacy" className="w-full justify-start">
                        Datenschutz
                    </TabsTrigger>
                </TabsList>
                <div className="flex-1 ml-4">
                    <TabsContent value="general" className="p-4 border rounded-lg">
                        <h3 className="font-medium">Allgemeine Einstellungen</h3>
                        <p className="text-sm text-muted-foreground mt-2">
                            Grundlegende Konfiguration Ihres Kontos.
                        </p>
                    </TabsContent>
                    <TabsContent value="security" className="p-4 border rounded-lg">
                        <h3 className="font-medium">Sicherheitseinstellungen</h3>
                        <p className="text-sm text-muted-foreground mt-2">
                            Passwort und Zwei-Faktor-Authentifizierung.
                        </p>
                    </TabsContent>
                    <TabsContent value="notifications" className="p-4 border rounded-lg">
                        <h3 className="font-medium">Benachrichtigungen</h3>
                        <p className="text-sm text-muted-foreground mt-2">
                            E-Mail und Push-Benachrichtigungen.
                        </p>
                    </TabsContent>
                    <TabsContent value="privacy" className="p-4 border rounded-lg">
                        <h3 className="font-medium">Datenschutz</h3>
                        <p className="text-sm text-muted-foreground mt-2">
                            Sichtbarkeit und Datenfreigabe.
                        </p>
                    </TabsContent>
                </div>
            </Tabs>
        </div>
    ),
};

// ==================== Breadcrumbs ====================

export const BreadcrumbDefault: Story = {
    render: () => (
        <Breadcrumb>
            <BreadcrumbList>
                <BreadcrumbItem>
                    <BreadcrumbLink href="/">
                        <Home className="h-4 w-4" />
                    </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                    <BreadcrumbLink href="/documents">Dokumente</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                    <BreadcrumbLink href="/documents/invoices">Rechnungen</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                    <BreadcrumbPage>Rechnung_2024_001.pdf</BreadcrumbPage>
                </BreadcrumbItem>
            </BreadcrumbList>
        </Breadcrumb>
    ),
};

export const BreadcrumbSimple: Story = {
    render: () => (
        <Breadcrumb>
            <BreadcrumbList>
                <BreadcrumbItem>
                    <BreadcrumbLink href="/">Start</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                    <BreadcrumbPage>Aktuelle Seite</BreadcrumbPage>
                </BreadcrumbItem>
            </BreadcrumbList>
        </Breadcrumb>
    ),
};

export const BreadcrumbWithDropdown: Story = {
    render: () => (
        <Breadcrumb>
            <BreadcrumbList>
                <BreadcrumbItem>
                    <BreadcrumbLink href="/">
                        <Home className="h-4 w-4" />
                    </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                    <DropdownMenu>
                        <DropdownMenuTrigger className="flex items-center gap-1 text-muted-foreground hover:text-foreground">
                            ...
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start">
                            <DropdownMenuItem>Dokumente</DropdownMenuItem>
                            <DropdownMenuItem>Projekte</DropdownMenuItem>
                            <DropdownMenuItem>Archiv</DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                    <BreadcrumbLink href="/documents/2024">2024</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                    <BreadcrumbPage>Januar</BreadcrumbPage>
                </BreadcrumbItem>
            </BreadcrumbList>
        </Breadcrumb>
    ),
};

// ==================== Pagination ====================

interface PaginationProps {
    currentPage: number;
    totalPages: number;
    onPageChange: (page: number) => void;
}

function Pagination({ currentPage, totalPages, onPageChange }: PaginationProps) {
    const pages = Array.from({ length: totalPages }, (_, i) => i + 1);
    const visiblePages = pages.slice(
        Math.max(0, currentPage - 2),
        Math.min(totalPages, currentPage + 1)
    );

    return (
        <nav className="flex items-center gap-1" aria-label="Pagination">
            <Button
                variant="outline"
                size="icon"
                onClick={() => onPageChange(1)}
                disabled={currentPage === 1}
                aria-label="Erste Seite"
            >
                <ChevronsLeft className="h-4 w-4" />
            </Button>
            <Button
                variant="outline"
                size="icon"
                onClick={() => onPageChange(currentPage - 1)}
                disabled={currentPage === 1}
                aria-label="Vorherige Seite"
            >
                <ChevronLeft className="h-4 w-4" />
            </Button>

            {currentPage > 3 && (
                <>
                    <Button
                        variant="outline"
                        size="icon"
                        onClick={() => onPageChange(1)}
                    >
                        1
                    </Button>
                    <span className="px-2 text-muted-foreground">...</span>
                </>
            )}

            {visiblePages.map((page) => (
                <Button
                    key={page}
                    variant={currentPage === page ? 'default' : 'outline'}
                    size="icon"
                    onClick={() => onPageChange(page)}
                    aria-current={currentPage === page ? 'page' : undefined}
                >
                    {page}
                </Button>
            ))}

            {currentPage < totalPages - 2 && (
                <>
                    <span className="px-2 text-muted-foreground">...</span>
                    <Button
                        variant="outline"
                        size="icon"
                        onClick={() => onPageChange(totalPages)}
                    >
                        {totalPages}
                    </Button>
                </>
            )}

            <Button
                variant="outline"
                size="icon"
                onClick={() => onPageChange(currentPage + 1)}
                disabled={currentPage === totalPages}
                aria-label="Nächste Seite"
            >
                <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
                variant="outline"
                size="icon"
                onClick={() => onPageChange(totalPages)}
                disabled={currentPage === totalPages}
                aria-label="Letzte Seite"
            >
                <ChevronsRight className="h-4 w-4" />
            </Button>
        </nav>
    );
}

function PaginationExample() {
    const [currentPage, setCurrentPage] = useState(5);
    const totalPages = 10;

    return (
        <div className="space-y-4">
            <Pagination
                currentPage={currentPage}
                totalPages={totalPages}
                onPageChange={setCurrentPage}
            />
            <p className="text-sm text-muted-foreground text-center">
                Seite {currentPage} von {totalPages}
            </p>
        </div>
    );
}

export const PaginationDefault: Story = {
    render: () => <PaginationExample />,
};

export const PaginationCompact: Story = {
    render: () => {
        const [currentPage, setCurrentPage] = useState(1);
        const totalPages = 5;

        return (
            <div className="flex items-center gap-2">
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                >
                    <ChevronLeft className="h-4 w-4 mr-1" />
                    Zurück
                </Button>
                <span className="text-sm">
                    Seite {currentPage} von {totalPages}
                </span>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                >
                    Weiter
                    <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
            </div>
        );
    },
};

// ==================== Dropdown Menu ====================

export const DropdownMenuDefault: Story = {
    render: () => (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="outline">Menue öffnen</Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-56">
                <DropdownMenuLabel>Mein Konto</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem>
                    <User className="mr-2 h-4 w-4" />
                    Profil
                </DropdownMenuItem>
                <DropdownMenuItem>
                    <Settings className="mr-2 h-4 w-4" />
                    Einstellungen
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="text-destructive">
                    Abmelden
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    ),
};

// ==================== Dark Mode ====================

export const DarkMode: Story = {
    render: () => (
        <div className="space-y-8">
            <Tabs defaultValue="tab1" className="w-[400px]">
                <TabsList>
                    <TabsTrigger value="tab1">Tab 1</TabsTrigger>
                    <TabsTrigger value="tab2">Tab 2</TabsTrigger>
                    <TabsTrigger value="tab3">Tab 3</TabsTrigger>
                </TabsList>
                <TabsContent value="tab1" className="p-4 border rounded-lg mt-2">
                    Inhalt Tab 1
                </TabsContent>
            </Tabs>

            <Breadcrumb>
                <BreadcrumbList>
                    <BreadcrumbItem>
                        <BreadcrumbLink href="/">Start</BreadcrumbLink>
                    </BreadcrumbItem>
                    <BreadcrumbSeparator />
                    <BreadcrumbItem>
                        <BreadcrumbPage>Seite</BreadcrumbPage>
                    </BreadcrumbItem>
                </BreadcrumbList>
            </Breadcrumb>

            <Pagination currentPage={3} totalPages={5} onPageChange={() => {}} />
        </div>
    ),
    parameters: {
        backgrounds: { default: 'dark' },
    },
    decorators: [
        (Story) => (
            <div className="dark">
                <Story />
            </div>
        ),
    ],
};
