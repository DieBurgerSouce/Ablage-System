/**
 * Alert Component Stories
 *
 * Alert-Komponenten für Visual Regression Testing.
 * Basiert auf shadcn/ui Alert.
 */

import type { Meta, StoryObj } from '@storybook/react';
import {
    AlertCircle,
    CheckCircle,
    Info,
    Terminal,
    TriangleAlert,
    XCircle,
} from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

const meta: Meta<typeof Alert> = {
    title: 'UI/Alert',
    component: Alert,
    parameters: {
        layout: 'centered',
        docs: {
            description: {
                component: 'Zeigt wichtige Nachrichten und Hinweise an.',
            },
        },
    },
    tags: ['autodocs'],
    argTypes: {
        variant: {
            control: 'select',
            options: ['default', 'destructive'],
            description: 'Die visuelle Variante des Alerts',
        },
    },
};

export default meta;
type Story = StoryObj<typeof meta>;

// ==================== Basis-Varianten ====================

export const Default: Story = {
    render: () => (
        <Alert className="w-[400px]">
            <Terminal className="h-4 w-4" />
            <AlertTitle>Hinweis</AlertTitle>
            <AlertDescription>
                Dies ist eine Standard-Benachrichtigung.
            </AlertDescription>
        </Alert>
    ),
};

export const Destructive: Story = {
    render: () => (
        <Alert variant="destructive" className="w-[400px]">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Fehler</AlertTitle>
            <AlertDescription>
                Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.
            </AlertDescription>
        </Alert>
    ),
};

// ==================== Mit verschiedenen Icons ====================

export const Info: Story = {
    render: () => (
        <Alert className="w-[400px]">
            <Info className="h-4 w-4" />
            <AlertTitle>Information</AlertTitle>
            <AlertDescription>
                Ihre Änderungen wurden gespeichert.
            </AlertDescription>
        </Alert>
    ),
};

export const Success: Story = {
    render: () => (
        <Alert className="w-[400px] border-green-500/50 text-green-600 [&>svg]:text-green-600">
            <CheckCircle className="h-4 w-4" />
            <AlertTitle>Erfolgreich</AlertTitle>
            <AlertDescription>
                Das Dokument wurde erfolgreich hochgeladen.
            </AlertDescription>
        </Alert>
    ),
};

export const Warning: Story = {
    render: () => (
        <Alert className="w-[400px] border-yellow-500/50 text-yellow-600 [&>svg]:text-yellow-600">
            <TriangleAlert className="h-4 w-4" />
            <AlertTitle>Warnung</AlertTitle>
            <AlertDescription>
                Ihr Speicherplatz ist fast voll. Bitte bereinigen Sie alte Dokumente.
            </AlertDescription>
        </Alert>
    ),
};

export const Error: Story = {
    render: () => (
        <Alert variant="destructive" className="w-[400px]">
            <XCircle className="h-4 w-4" />
            <AlertTitle>Kritischer Fehler</AlertTitle>
            <AlertDescription>
                Die Verbindung zum Server wurde unterbrochen.
                Bitte kontaktieren Sie den Support.
            </AlertDescription>
        </Alert>
    ),
};

// ==================== Nur Titel ====================

export const TitleOnly: Story = {
    render: () => (
        <Alert className="w-[400px]">
            <Info className="h-4 w-4" />
            <AlertTitle>Nur ein Titel ohne Beschreibung</AlertTitle>
        </Alert>
    ),
};

// ==================== Nur Beschreibung ====================

export const DescriptionOnly: Story = {
    render: () => (
        <Alert className="w-[400px]">
            <Info className="h-4 w-4" />
            <AlertDescription>
                Nur eine Beschreibung ohne Titel.
            </AlertDescription>
        </Alert>
    ),
};

// ==================== Mit langem Inhalt ====================

export const LongContent: Story = {
    render: () => (
        <Alert className="w-[500px]">
            <Info className="h-4 w-4" />
            <AlertTitle>Wichtige Information</AlertTitle>
            <AlertDescription>
                Lorem ipsum dolor sit amet, consectetur adipiscing elit.
                Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
                Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris
                nisi ut aliquip ex ea commodo consequat.
            </AlertDescription>
        </Alert>
    ),
};

// ==================== Mit Liste ====================

export const WithList: Story = {
    render: () => (
        <Alert className="w-[400px]">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Validierungsfehler</AlertTitle>
            <AlertDescription>
                <ul className="list-disc list-inside mt-2 space-y-1">
                    <li>E-Mail-Adresse ist ungültig</li>
                    <li>Passwort muss mindestens 8 Zeichen haben</li>
                    <li>Benutzername ist bereits vergeben</li>
                </ul>
            </AlertDescription>
        </Alert>
    ),
};

// ==================== Alle Varianten ====================

export const AllVariants: Story = {
    render: () => (
        <div className="flex flex-col gap-4 w-[450px]">
            <Alert>
                <Info className="h-4 w-4" />
                <AlertTitle>Info</AlertTitle>
                <AlertDescription>
                    Standard-Informationsmeldung.
                </AlertDescription>
            </Alert>

            <Alert className="border-green-500/50 text-green-600 [&>svg]:text-green-600">
                <CheckCircle className="h-4 w-4" />
                <AlertTitle>Erfolg</AlertTitle>
                <AlertDescription>
                    Aktion erfolgreich ausgeführt.
                </AlertDescription>
            </Alert>

            <Alert className="border-yellow-500/50 text-yellow-600 [&>svg]:text-yellow-600">
                <TriangleAlert className="h-4 w-4" />
                <AlertTitle>Warnung</AlertTitle>
                <AlertDescription>
                    Achtung, bitte prüfen Sie Ihre Eingaben.
                </AlertDescription>
            </Alert>

            <Alert variant="destructive">
                <XCircle className="h-4 w-4" />
                <AlertTitle>Fehler</AlertTitle>
                <AlertDescription>
                    Ein kritischer Fehler ist aufgetreten.
                </AlertDescription>
            </Alert>
        </div>
    ),
    parameters: {
        layout: 'padded',
    },
};

// ==================== Dark Mode ====================

export const DarkMode: Story = {
    render: () => (
        <div className="flex flex-col gap-4 w-[400px]">
            <Alert>
                <Info className="h-4 w-4" />
                <AlertTitle>Dark Mode</AlertTitle>
                <AlertDescription>
                    Alert im dunklen Modus.
                </AlertDescription>
            </Alert>
            <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Fehler</AlertTitle>
                <AlertDescription>
                    Destructive Alert im dunklen Modus.
                </AlertDescription>
            </Alert>
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
