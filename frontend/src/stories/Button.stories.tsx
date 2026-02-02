/**
 * Button Component Stories
 *
 * Alle Button-Varianten fuer Visual Regression Testing.
 * Basiert auf shadcn/ui Button mit class-variance-authority.
 */

import type { Meta, StoryObj } from '@storybook/react';
import { fn } from '@storybook/test';
import { Download, Plus, Trash2, Edit, Loader2, Mail, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

const meta: Meta<typeof Button> = {
    title: 'UI/Button',
    component: Button,
    parameters: {
        layout: 'centered',
        docs: {
            description: {
                component: 'Button-Komponente mit verschiedenen Varianten und Groessen.',
            },
        },
    },
    tags: ['autodocs'],
    argTypes: {
        variant: {
            control: 'select',
            options: ['default', 'destructive', 'outline', 'secondary', 'ghost', 'link'],
            description: 'Die visuelle Variante des Buttons',
        },
        size: {
            control: 'select',
            options: ['default', 'sm', 'lg', 'icon'],
            description: 'Die Groesse des Buttons',
        },
        disabled: {
            control: 'boolean',
            description: 'Deaktiviert den Button',
        },
        asChild: {
            control: 'boolean',
            description: 'Render als Child-Element (fuer Link-Wrapper)',
        },
    },
    args: {
        onClick: fn(),
    },
};

export default meta;
type Story = StoryObj<typeof meta>;

// ==================== Varianten ====================

export const Default: Story = {
    args: {
        children: 'Button',
        variant: 'default',
    },
};

export const Destructive: Story = {
    args: {
        children: 'Loeschen',
        variant: 'destructive',
    },
};

export const Outline: Story = {
    args: {
        children: 'Abbrechen',
        variant: 'outline',
    },
};

export const Secondary: Story = {
    args: {
        children: 'Sekundaer',
        variant: 'secondary',
    },
};

export const Ghost: Story = {
    args: {
        children: 'Ghost',
        variant: 'ghost',
    },
};

export const Link: Story = {
    args: {
        children: 'Link Button',
        variant: 'link',
    },
};

// ==================== Groessen ====================

export const Small: Story = {
    args: {
        children: 'Klein',
        size: 'sm',
    },
};

export const Large: Story = {
    args: {
        children: 'Gross',
        size: 'lg',
    },
};

export const IconButton: Story = {
    args: {
        size: 'icon',
        children: <Plus className="h-4 w-4" />,
        'aria-label': 'Hinzufuegen',
    },
};

// ==================== Mit Icons ====================

export const WithLeftIcon: Story = {
    args: {
        children: (
            <>
                <Download className="h-4 w-4" />
                Herunterladen
            </>
        ),
    },
};

export const WithRightIcon: Story = {
    args: {
        children: (
            <>
                Weiter
                <ChevronRight className="h-4 w-4" />
            </>
        ),
    },
};

export const IconOnly: Story = {
    args: {
        size: 'icon',
        variant: 'outline',
        children: <Edit className="h-4 w-4" />,
        'aria-label': 'Bearbeiten',
    },
};

// ==================== Zustaende ====================

export const Disabled: Story = {
    args: {
        children: 'Deaktiviert',
        disabled: true,
    },
};

export const Loading: Story = {
    args: {
        disabled: true,
        children: (
            <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Wird geladen...
            </>
        ),
    },
};

// ==================== Kombinationen ====================

export const DestructiveWithIcon: Story = {
    args: {
        variant: 'destructive',
        children: (
            <>
                <Trash2 className="h-4 w-4" />
                Loeschen
            </>
        ),
    },
};

export const OutlineWithIcon: Story = {
    args: {
        variant: 'outline',
        children: (
            <>
                <Mail className="h-4 w-4" />
                E-Mail senden
            </>
        ),
    },
};

// ==================== Showcase ====================

export const AllVariants: Story = {
    render: () => (
        <div className="flex flex-col gap-4">
            <div className="flex items-center gap-2">
                <Button variant="default">Default</Button>
                <Button variant="secondary">Secondary</Button>
                <Button variant="outline">Outline</Button>
                <Button variant="ghost">Ghost</Button>
                <Button variant="link">Link</Button>
                <Button variant="destructive">Destructive</Button>
            </div>
            <div className="flex items-center gap-2">
                <Button size="sm">Small</Button>
                <Button size="default">Default</Button>
                <Button size="lg">Large</Button>
                <Button size="icon"><Plus className="h-4 w-4" /></Button>
            </div>
            <div className="flex items-center gap-2">
                <Button disabled>Disabled</Button>
                <Button disabled>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading
                </Button>
            </div>
        </div>
    ),
    parameters: {
        layout: 'padded',
    },
};

// ==================== Dark Mode ====================

export const DarkMode: Story = {
    args: {
        children: 'Dark Mode Button',
    },
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
