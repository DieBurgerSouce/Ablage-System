/**
 * Card Component Stories
 *
 * Card-Komponenten für Visual Regression Testing.
 * Basiert auf shadcn/ui Card.
 */

import type { Meta, StoryObj } from '@storybook/react';
import { Bell, CreditCard, Settings, User } from 'lucide-react';
import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';

const meta: Meta<typeof Card> = {
    title: 'UI/Card',
    component: Card,
    parameters: {
        layout: 'centered',
        docs: {
            description: {
                component: 'Container-Komponente für gruppierte Inhalte.',
            },
        },
    },
    tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof meta>;

// ==================== Basis ====================

export const Default: Story = {
    render: () => (
        <Card className="w-[350px]">
            <CardHeader>
                <CardTitle>Karten-Titel</CardTitle>
                <CardDescription>Kurze Beschreibung der Karte</CardDescription>
            </CardHeader>
            <CardContent>
                <p>Hier ist der Hauptinhalt der Karte.</p>
            </CardContent>
            <CardFooter>
                <Button>Aktion</Button>
            </CardFooter>
        </Card>
    ),
};

export const SimpleCard: Story = {
    render: () => (
        <Card className="w-[350px]">
            <CardContent className="pt-6">
                <p>Eine einfache Karte ohne Header oder Footer.</p>
            </CardContent>
        </Card>
    ),
};

export const HeaderOnly: Story = {
    render: () => (
        <Card className="w-[350px]">
            <CardHeader>
                <CardTitle>Nur Header</CardTitle>
                <CardDescription>Karte mit Header und Content</CardDescription>
            </CardHeader>
            <CardContent>
                <p>Inhalt ohne Footer.</p>
            </CardContent>
        </Card>
    ),
};

// ==================== Mit Formularen ====================

export const FormCard: Story = {
    render: () => (
        <Card className="w-[400px]">
            <CardHeader>
                <CardTitle>Anmelden</CardTitle>
                <CardDescription>
                    Geben Sie Ihre Anmeldedaten ein
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="space-y-2">
                    <Label htmlFor="email">E-Mail</Label>
                    <Input id="email" type="email" placeholder="name@beispiel.de" />
                </div>
                <div className="space-y-2">
                    <Label htmlFor="password">Passwort</Label>
                    <Input id="password" type="password" />
                </div>
            </CardContent>
            <CardFooter className="flex justify-between">
                <Button variant="outline">Abbrechen</Button>
                <Button>Anmelden</Button>
            </CardFooter>
        </Card>
    ),
};

// ==================== Mit Icons ====================

export const WithIcon: Story = {
    render: () => (
        <Card className="w-[350px]">
            <CardHeader className="flex flex-row items-center gap-4">
                <div className="p-2 bg-primary/10 rounded-lg">
                    <CreditCard className="h-6 w-6 text-primary" />
                </div>
                <div>
                    <CardTitle>Zahlungsmethode</CardTitle>
                    <CardDescription>Ihre aktuelle Zahlungsart</CardDescription>
                </div>
            </CardHeader>
            <CardContent>
                <p className="text-sm text-muted-foreground">
                    Visa endet auf **** 4242
                </p>
            </CardContent>
        </Card>
    ),
};

// ==================== Statistik-Karten ====================

export const StatCard: Story = {
    render: () => (
        <Card className="w-[200px]">
            <CardHeader className="pb-2">
                <CardDescription>Dokumente</CardDescription>
                <CardTitle className="text-3xl">1.234</CardTitle>
            </CardHeader>
            <CardContent>
                <p className="text-xs text-muted-foreground">
                    +12% seit letztem Monat
                </p>
            </CardContent>
        </Card>
    ),
};

export const StatCardWithIcon: Story = {
    render: () => (
        <Card className="w-[250px]">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardDescription>Benutzer</CardDescription>
                <User className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-bold">+2.350</div>
                <p className="text-xs text-muted-foreground">
                    +180.1% seit letztem Monat
                </p>
            </CardContent>
        </Card>
    ),
};

// ==================== Mit Badge ====================

export const WithBadge: Story = {
    render: () => (
        <Card className="w-[350px]">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <CardTitle>Premium Plan</CardTitle>
                    <Badge>Aktiv</Badge>
                </div>
                <CardDescription>
                    Ihr aktueller Tarif
                </CardDescription>
            </CardHeader>
            <CardContent>
                <ul className="space-y-2 text-sm">
                    <li>Unbegrenzte Dokumente</li>
                    <li>Prioritäts-Support</li>
                    <li>API-Zugang</li>
                </ul>
            </CardContent>
            <CardFooter>
                <Button variant="outline" className="w-full">
                    Plan verwalten
                </Button>
            </CardFooter>
        </Card>
    ),
};

// ==================== Einstellungs-Karte ====================

export const SettingsCard: Story = {
    render: () => (
        <Card className="w-[400px]">
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Settings className="h-5 w-5" />
                    Benachrichtigungen
                </CardTitle>
                <CardDescription>
                    Verwalten Sie Ihre Benachrichtigungseinstellungen
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                        <Label>E-Mail-Benachrichtigungen</Label>
                        <p className="text-sm text-muted-foreground">
                            Erhalten Sie Updates per E-Mail
                        </p>
                    </div>
                    <Switch defaultChecked />
                </div>
                <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                        <Label>Push-Benachrichtigungen</Label>
                        <p className="text-sm text-muted-foreground">
                            Erhalten Sie Push-Nachrichten
                        </p>
                    </div>
                    <Switch />
                </div>
            </CardContent>
        </Card>
    ),
};

// ==================== Grid von Karten ====================

export const CardGrid: Story = {
    render: () => (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
                { title: 'Dokumente', value: '1.234', icon: CreditCard, change: '+12%' },
                { title: 'Benutzer', value: '56', icon: User, change: '+3%' },
                { title: 'Alerts', value: '8', icon: Bell, change: '-2%' },
            ].map((stat) => (
                <Card key={stat.title}>
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardDescription>{stat.title}</CardDescription>
                        <stat.icon className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stat.value}</div>
                        <p className="text-xs text-muted-foreground">
                            {stat.change} seit letztem Monat
                        </p>
                    </CardContent>
                </Card>
            ))}
        </div>
    ),
    parameters: {
        layout: 'padded',
    },
};

// ==================== Dark Mode ====================

export const DarkMode: Story = {
    render: () => (
        <Card className="w-[350px]">
            <CardHeader>
                <CardTitle>Dark Mode Karte</CardTitle>
                <CardDescription>Darstellung im dunklen Modus</CardDescription>
            </CardHeader>
            <CardContent>
                <p>Inhalt im Dark Mode.</p>
            </CardContent>
            <CardFooter>
                <Button>Aktion</Button>
            </CardFooter>
        </Card>
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
