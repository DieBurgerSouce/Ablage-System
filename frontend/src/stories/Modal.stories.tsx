/**
 * Modal/Dialog Component Stories
 *
 * Dialog und AlertDialog Stories für Visual Regression Testing.
 * Basiert auf Radix UI Dialog.
 */

import type { Meta, StoryObj } from '@storybook/react';
import { useState } from 'react';
import { fn } from '@storybook/test';
import { Trash2, AlertTriangle, Info, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
    DialogClose,
} from '@/components/ui/dialog';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
    SheetTrigger,
    SheetFooter,
    SheetClose,
} from '@/components/ui/sheet';

const meta: Meta = {
    title: 'UI/Modal',
    parameters: {
        layout: 'centered',
        docs: {
            description: {
                component: 'Modal, Dialog und Sheet Komponenten.',
            },
        },
    },
    tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof meta>;

// ==================== Basic Dialog ====================

export const DialogDefault: Story = {
    render: () => (
        <Dialog>
            <DialogTrigger asChild>
                <Button>Dialog öffnen</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                    <DialogTitle>Dialog Titel</DialogTitle>
                    <DialogDescription>
                        Eine Beschreibung des Dialogs. Hier können Sie weitere
                        Informationen bereitstellen.
                    </DialogDescription>
                </DialogHeader>
                <div className="py-4">
                    <p>Dialog-Inhalt kommt hier.</p>
                </div>
                <DialogFooter>
                    <DialogClose asChild>
                        <Button variant="outline">Abbrechen</Button>
                    </DialogClose>
                    <Button>Speichern</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    ),
};

// ==================== Dialog with Form ====================

export const DialogWithForm: Story = {
    render: () => (
        <Dialog>
            <DialogTrigger asChild>
                <Button>Profil bearbeiten</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                    <DialogTitle>Profil bearbeiten</DialogTitle>
                    <DialogDescription>
                        Ändern Sie hier Ihre Profilinformationen.
                    </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="name" className="text-right">
                            Name
                        </Label>
                        <Input
                            id="name"
                            defaultValue="Max Mustermann"
                            className="col-span-3"
                        />
                    </div>
                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="email" className="text-right">
                            E-Mail
                        </Label>
                        <Input
                            id="email"
                            defaultValue="max@beispiel.de"
                            className="col-span-3"
                        />
                    </div>
                </div>
                <DialogFooter>
                    <Button type="submit">Änderungen speichern</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    ),
};

// ==================== Large Dialog ====================

export const DialogLarge: Story = {
    render: () => (
        <Dialog>
            <DialogTrigger asChild>
                <Button variant="outline">Grosser Dialog</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[600px]">
                <DialogHeader>
                    <DialogTitle>Dokumentdetails</DialogTitle>
                    <DialogDescription>
                        Vollständige Informationen zum Dokument.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <Label>Dateiname</Label>
                            <p className="text-sm text-muted-foreground">
                                Rechnung_2024_001.pdf
                            </p>
                        </div>
                        <div>
                            <Label>Größe</Label>
                            <p className="text-sm text-muted-foreground">245 KB</p>
                        </div>
                        <div>
                            <Label>Hochgeladen am</Label>
                            <p className="text-sm text-muted-foreground">
                                15. Januar 2024
                            </p>
                        </div>
                        <div>
                            <Label>Status</Label>
                            <p className="text-sm text-muted-foreground">Verarbeitet</p>
                        </div>
                    </div>
                    <div>
                        <Label>Notizen</Label>
                        <p className="text-sm text-muted-foreground mt-1">
                            Lorem ipsum dolor sit amet, consectetur adipiscing elit.
                            Sed do eiusmod tempor incididunt ut labore et dolore magna
                            aliqua.
                        </p>
                    </div>
                </div>
                <DialogFooter>
                    <DialogClose asChild>
                        <Button variant="outline">Schließen</Button>
                    </DialogClose>
                    <Button>Herunterladen</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    ),
};

// ==================== Alert Dialog ====================

export const AlertDialogDefault: Story = {
    render: () => (
        <AlertDialog>
            <AlertDialogTrigger asChild>
                <Button variant="destructive">
                    <Trash2 className="mr-2 h-4 w-4" />
                    Löschen
                </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>Sind Sie sicher?</AlertDialogTitle>
                    <AlertDialogDescription>
                        Diese Aktion kann nicht rückgängig gemacht werden. Das Dokument
                        wird dauerhaft gelöscht.
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                    <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                        Löschen
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    ),
};

export const AlertDialogWarning: Story = {
    render: () => (
        <AlertDialog>
            <AlertDialogTrigger asChild>
                <Button variant="outline">
                    <AlertTriangle className="mr-2 h-4 w-4" />
                    Warnung zeigen
                </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <div className="flex items-center gap-2">
                        <AlertTriangle className="h-5 w-5 text-yellow-500" />
                        <AlertDialogTitle>Warnung</AlertDialogTitle>
                    </div>
                    <AlertDialogDescription>
                        Sie haben ungespeicherte Änderungen. Möchten Sie die Seite
                        wirklich verlassen?
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel>Bleiben</AlertDialogCancel>
                    <AlertDialogAction>Verlassen</AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    ),
};

export const AlertDialogInfo: Story = {
    render: () => (
        <AlertDialog>
            <AlertDialogTrigger asChild>
                <Button variant="secondary">
                    <Info className="mr-2 h-4 w-4" />
                    Info anzeigen
                </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <div className="flex items-center gap-2">
                        <Info className="h-5 w-5 text-blue-500" />
                        <AlertDialogTitle>Hinweis</AlertDialogTitle>
                    </div>
                    <AlertDialogDescription>
                        Der Export wurde erfolgreich gestartet. Sie erhalten eine E-Mail,
                        sobald die Datei bereit ist.
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogAction>Verstanden</AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    ),
};

// ==================== Sheet ====================

export const SheetRight: Story = {
    render: () => (
        <Sheet>
            <SheetTrigger asChild>
                <Button variant="outline">
                    <Settings className="mr-2 h-4 w-4" />
                    Einstellungen
                </Button>
            </SheetTrigger>
            <SheetContent>
                <SheetHeader>
                    <SheetTitle>Einstellungen</SheetTitle>
                    <SheetDescription>
                        Passen Sie hier Ihre Einstellungen an.
                    </SheetDescription>
                </SheetHeader>
                <div className="grid gap-4 py-4">
                    <div className="space-y-2">
                        <Label htmlFor="settings-name">Benutzername</Label>
                        <Input id="settings-name" defaultValue="max_mustermann" />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="settings-email">E-Mail</Label>
                        <Input id="settings-email" defaultValue="max@beispiel.de" />
                    </div>
                </div>
                <SheetFooter>
                    <SheetClose asChild>
                        <Button variant="outline">Abbrechen</Button>
                    </SheetClose>
                    <Button>Speichern</Button>
                </SheetFooter>
            </SheetContent>
        </Sheet>
    ),
};

export const SheetLeft: Story = {
    render: () => (
        <Sheet>
            <SheetTrigger asChild>
                <Button variant="outline">Linkes Sheet</Button>
            </SheetTrigger>
            <SheetContent side="left">
                <SheetHeader>
                    <SheetTitle>Navigation</SheetTitle>
                    <SheetDescription>
                        Wählen Sie einen Bereich aus.
                    </SheetDescription>
                </SheetHeader>
                <div className="py-4 space-y-2">
                    <Button variant="ghost" className="w-full justify-start">
                        Dashboard
                    </Button>
                    <Button variant="ghost" className="w-full justify-start">
                        Dokumente
                    </Button>
                    <Button variant="ghost" className="w-full justify-start">
                        Berichte
                    </Button>
                    <Button variant="ghost" className="w-full justify-start">
                        Einstellungen
                    </Button>
                </div>
            </SheetContent>
        </Sheet>
    ),
};

export const SheetBottom: Story = {
    render: () => (
        <Sheet>
            <SheetTrigger asChild>
                <Button variant="outline">Unteres Sheet</Button>
            </SheetTrigger>
            <SheetContent side="bottom">
                <SheetHeader>
                    <SheetTitle>Schnellaktionen</SheetTitle>
                    <SheetDescription>
                        Wählen Sie eine Aktion aus.
                    </SheetDescription>
                </SheetHeader>
                <div className="py-4 flex gap-4 justify-center">
                    <Button>Dokument hochladen</Button>
                    <Button variant="outline">Ordner erstellen</Button>
                    <Button variant="secondary">Teilen</Button>
                </div>
            </SheetContent>
        </Sheet>
    ),
};

// ==================== Controlled Dialog ====================

function ControlledDialogExample() {
    const [open, setOpen] = useState(false);

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button>Gesteuerter Dialog</Button>
            </DialogTrigger>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>Gesteuerter Dialog</DialogTitle>
                    <DialogDescription>
                        Dieser Dialog wird programmatisch gesteuert.
                    </DialogDescription>
                </DialogHeader>
                <div className="py-4">
                    <p>Der Dialog ist {open ? 'offen' : 'geschlossen'}.</p>
                </div>
                <DialogFooter>
                    <Button onClick={() => setOpen(false)}>Schließen</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export const ControlledDialog: Story = {
    render: () => <ControlledDialogExample />,
};

// ==================== Dark Mode ====================

export const DarkMode: Story = {
    render: () => (
        <div className="flex gap-4">
            <Dialog>
                <DialogTrigger asChild>
                    <Button>Dialog</Button>
                </DialogTrigger>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Dark Mode Dialog</DialogTitle>
                        <DialogDescription>
                            Dialog im dunklen Modus.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button>OK</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <AlertDialog>
                <AlertDialogTrigger asChild>
                    <Button variant="destructive">Alert</Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Dark Mode Alert</AlertDialogTitle>
                        <AlertDialogDescription>
                            Alert Dialog im dunklen Modus.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction>OK</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
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
