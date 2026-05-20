/**
 * Form Components Stories
 *
 * Formular-Komponenten für Visual Regression Testing.
 * Input, Select, Checkbox, Radio, Textarea, etc.
 */

import type { Meta, StoryObj } from '@storybook/react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Switch } from '@/components/ui/switch';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Form,
    FormControl,
    FormDescription,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from '@/components/ui/form';

const meta: Meta = {
    title: 'UI/Form',
    parameters: {
        layout: 'centered',
        docs: {
            description: {
                component: 'Formular-Komponenten basierend auf shadcn/ui.',
            },
        },
    },
    tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof meta>;

// ==================== Input ====================

export const InputDefault: Story = {
    render: () => (
        <div className="w-[300px] space-y-2">
            <Label htmlFor="email">E-Mail</Label>
            <Input id="email" type="email" placeholder="name@beispiel.de" />
        </div>
    ),
};

export const InputDisabled: Story = {
    render: () => (
        <div className="w-[300px] space-y-2">
            <Label htmlFor="disabled">Deaktiviert</Label>
            <Input id="disabled" disabled placeholder="Nicht bearbeitbar" />
        </div>
    ),
};

export const InputWithError: Story = {
    render: () => (
        <div className="w-[300px] space-y-2">
            <Label htmlFor="error">E-Mail</Label>
            <Input
                id="error"
                type="email"
                placeholder="name@beispiel.de"
                className="border-destructive"
                aria-invalid="true"
            />
            <p className="text-sm text-destructive">
                Bitte geben Sie eine gültige E-Mail-Adresse ein.
            </p>
        </div>
    ),
};

export const InputTypes: Story = {
    render: () => (
        <div className="w-[300px] space-y-4">
            <div className="space-y-2">
                <Label htmlFor="text">Text</Label>
                <Input id="text" type="text" placeholder="Textfeld" />
            </div>
            <div className="space-y-2">
                <Label htmlFor="password">Passwort</Label>
                <Input id="password" type="password" placeholder="Passwort" />
            </div>
            <div className="space-y-2">
                <Label htmlFor="number">Zahl</Label>
                <Input id="number" type="number" placeholder="0" />
            </div>
            <div className="space-y-2">
                <Label htmlFor="date">Datum</Label>
                <Input id="date" type="date" />
            </div>
            <div className="space-y-2">
                <Label htmlFor="file">Datei</Label>
                <Input id="file" type="file" />
            </div>
        </div>
    ),
};

// ==================== Textarea ====================

export const TextareaDefault: Story = {
    render: () => (
        <div className="w-[400px] space-y-2">
            <Label htmlFor="message">Nachricht</Label>
            <Textarea
                id="message"
                placeholder="Geben Sie Ihre Nachricht ein..."
                rows={4}
            />
        </div>
    ),
};

export const TextareaDisabled: Story = {
    render: () => (
        <div className="w-[400px] space-y-2">
            <Label htmlFor="readonly">Nur lesen</Label>
            <Textarea
                id="readonly"
                disabled
                value="Dieser Text kann nicht bearbeitet werden."
                rows={3}
            />
        </div>
    ),
};

// ==================== Select ====================

export const SelectDefault: Story = {
    render: () => (
        <div className="w-[300px] space-y-2">
            <Label htmlFor="document-type">Dokumenttyp</Label>
            <Select>
                <SelectTrigger id="document-type">
                    <SelectValue placeholder="Typ auswählen" />
                </SelectTrigger>
                <SelectContent>
                    <SelectItem value="rechnung">Rechnung</SelectItem>
                    <SelectItem value="lieferschein">Lieferschein</SelectItem>
                    <SelectItem value="angebot">Angebot</SelectItem>
                    <SelectItem value="vertrag">Vertrag</SelectItem>
                </SelectContent>
            </Select>
        </div>
    ),
};

export const SelectDisabled: Story = {
    render: () => (
        <div className="w-[300px] space-y-2">
            <Label htmlFor="disabled-select">Deaktiviert</Label>
            <Select disabled>
                <SelectTrigger id="disabled-select">
                    <SelectValue placeholder="Nicht verfügbar" />
                </SelectTrigger>
                <SelectContent>
                    <SelectItem value="option">Option</SelectItem>
                </SelectContent>
            </Select>
        </div>
    ),
};

// ==================== Checkbox ====================

export const CheckboxDefault: Story = {
    render: () => (
        <div className="flex items-center space-x-2">
            <Checkbox id="terms" />
            <Label htmlFor="terms">Ich akzeptiere die AGB</Label>
        </div>
    ),
};

export const CheckboxChecked: Story = {
    render: () => (
        <div className="flex items-center space-x-2">
            <Checkbox id="checked" defaultChecked />
            <Label htmlFor="checked">Aktiviert</Label>
        </div>
    ),
};

export const CheckboxDisabled: Story = {
    render: () => (
        <div className="space-y-2">
            <div className="flex items-center space-x-2">
                <Checkbox id="disabled1" disabled />
                <Label htmlFor="disabled1" className="text-muted-foreground">
                    Deaktiviert (unchecked)
                </Label>
            </div>
            <div className="flex items-center space-x-2">
                <Checkbox id="disabled2" disabled defaultChecked />
                <Label htmlFor="disabled2" className="text-muted-foreground">
                    Deaktiviert (checked)
                </Label>
            </div>
        </div>
    ),
};

export const CheckboxGroup: Story = {
    render: () => (
        <div className="space-y-4">
            <Label>Benachrichtigungen</Label>
            <div className="space-y-2">
                <div className="flex items-center space-x-2">
                    <Checkbox id="email-notif" defaultChecked />
                    <Label htmlFor="email-notif">E-Mail</Label>
                </div>
                <div className="flex items-center space-x-2">
                    <Checkbox id="push-notif" />
                    <Label htmlFor="push-notif">Push</Label>
                </div>
                <div className="flex items-center space-x-2">
                    <Checkbox id="sms-notif" />
                    <Label htmlFor="sms-notif">SMS</Label>
                </div>
            </div>
        </div>
    ),
};

// ==================== Radio Group ====================

export const RadioGroupDefault: Story = {
    render: () => (
        <div className="space-y-2">
            <Label>Zahlungsmethode</Label>
            <RadioGroup defaultValue="card">
                <div className="flex items-center space-x-2">
                    <RadioGroupItem value="card" id="card" />
                    <Label htmlFor="card">Kreditkarte</Label>
                </div>
                <div className="flex items-center space-x-2">
                    <RadioGroupItem value="paypal" id="paypal" />
                    <Label htmlFor="paypal">PayPal</Label>
                </div>
                <div className="flex items-center space-x-2">
                    <RadioGroupItem value="bank" id="bank" />
                    <Label htmlFor="bank">Banküberweisung</Label>
                </div>
            </RadioGroup>
        </div>
    ),
};

// ==================== Switch ====================

export const SwitchDefault: Story = {
    render: () => (
        <div className="flex items-center space-x-2">
            <Switch id="airplane" />
            <Label htmlFor="airplane">Flugmodus</Label>
        </div>
    ),
};

export const SwitchChecked: Story = {
    render: () => (
        <div className="flex items-center space-x-2">
            <Switch id="active" defaultChecked />
            <Label htmlFor="active">Aktiv</Label>
        </div>
    ),
};

export const SwitchDisabled: Story = {
    render: () => (
        <div className="space-y-2">
            <div className="flex items-center space-x-2">
                <Switch id="disabled-off" disabled />
                <Label htmlFor="disabled-off" className="text-muted-foreground">
                    Deaktiviert (aus)
                </Label>
            </div>
            <div className="flex items-center space-x-2">
                <Switch id="disabled-on" disabled defaultChecked />
                <Label htmlFor="disabled-on" className="text-muted-foreground">
                    Deaktiviert (an)
                </Label>
            </div>
        </div>
    ),
};

// ==================== Complete Form ====================

const formSchema = z.object({
    name: z.string().min(2, 'Name muss mindestens 2 Zeichen haben'),
    email: z.string().email('Ungültige E-Mail-Adresse'),
    documentType: z.string().min(1, 'Bitte wählen Sie einen Dokumenttyp'),
    description: z.string().optional(),
    notifications: z.boolean(),
});

function CompleteFormExample() {
    const form = useForm<z.infer<typeof formSchema>>({
        resolver: zodResolver(formSchema),
        defaultValues: {
            name: '',
            email: '',
            documentType: '',
            description: '',
            notifications: false,
        },
    });

    function onSubmit(values: z.infer<typeof formSchema>) {
        console.log(values);
    }

    return (
        <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 w-[400px]">
                <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                        <FormItem>
                            <FormLabel>Name</FormLabel>
                            <FormControl>
                                <Input placeholder="Max Mustermann" {...field} />
                            </FormControl>
                            <FormDescription>
                                Ihr vollständiger Name.
                            </FormDescription>
                            <FormMessage />
                        </FormItem>
                    )}
                />

                <FormField
                    control={form.control}
                    name="email"
                    render={({ field }) => (
                        <FormItem>
                            <FormLabel>E-Mail</FormLabel>
                            <FormControl>
                                <Input
                                    type="email"
                                    placeholder="name@beispiel.de"
                                    {...field}
                                />
                            </FormControl>
                            <FormMessage />
                        </FormItem>
                    )}
                />

                <FormField
                    control={form.control}
                    name="documentType"
                    render={({ field }) => (
                        <FormItem>
                            <FormLabel>Dokumenttyp</FormLabel>
                            <Select
                                onValueChange={field.onChange}
                                defaultValue={field.value}
                            >
                                <FormControl>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Typ auswählen" />
                                    </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                    <SelectItem value="rechnung">Rechnung</SelectItem>
                                    <SelectItem value="lieferschein">Lieferschein</SelectItem>
                                    <SelectItem value="angebot">Angebot</SelectItem>
                                </SelectContent>
                            </Select>
                            <FormMessage />
                        </FormItem>
                    )}
                />

                <FormField
                    control={form.control}
                    name="description"
                    render={({ field }) => (
                        <FormItem>
                            <FormLabel>Beschreibung</FormLabel>
                            <FormControl>
                                <Textarea
                                    placeholder="Optionale Beschreibung..."
                                    {...field}
                                />
                            </FormControl>
                            <FormMessage />
                        </FormItem>
                    )}
                />

                <FormField
                    control={form.control}
                    name="notifications"
                    render={({ field }) => (
                        <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                            <div className="space-y-0.5">
                                <FormLabel className="text-base">
                                    Benachrichtigungen
                                </FormLabel>
                                <FormDescription>
                                    E-Mail-Updates erhalten.
                                </FormDescription>
                            </div>
                            <FormControl>
                                <Switch
                                    checked={field.value}
                                    onCheckedChange={field.onChange}
                                />
                            </FormControl>
                        </FormItem>
                    )}
                />

                <Button type="submit" className="w-full">
                    Speichern
                </Button>
            </form>
        </Form>
    );
}

export const CompleteForm: Story = {
    render: () => <CompleteFormExample />,
};

// ==================== Dark Mode ====================

export const DarkMode: Story = {
    render: () => (
        <div className="w-[300px] space-y-4">
            <div className="space-y-2">
                <Label htmlFor="dark-input">Eingabe</Label>
                <Input id="dark-input" placeholder="Dark Mode Input" />
            </div>
            <div className="space-y-2">
                <Label htmlFor="dark-select">Auswahl</Label>
                <Select>
                    <SelectTrigger id="dark-select">
                        <SelectValue placeholder="Auswählen..." />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="1">Option 1</SelectItem>
                        <SelectItem value="2">Option 2</SelectItem>
                    </SelectContent>
                </Select>
            </div>
            <div className="flex items-center space-x-2">
                <Checkbox id="dark-checkbox" />
                <Label htmlFor="dark-checkbox">Checkbox</Label>
            </div>
            <div className="flex items-center space-x-2">
                <Switch id="dark-switch" />
                <Label htmlFor="dark-switch">Switch</Label>
            </div>
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
