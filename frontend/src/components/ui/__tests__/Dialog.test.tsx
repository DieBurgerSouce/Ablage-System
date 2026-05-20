/**
 * Dialog Component Tests
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, userEvent, waitFor } from '@/test/utils';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from '../dialog';
import { Button } from '../button';

describe('Dialog', () => {
  it('renders trigger and opens dialog on click', async () => {
    const user = userEvent.setup();

    render(
      <Dialog>
        <DialogTrigger asChild>
          <Button>Open Dialog</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Test Dialog</DialogTitle>
            <DialogDescription>This is a test dialog</DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    );

    const trigger = screen.getByRole('button', { name: /open dialog/i });
    expect(trigger).toBeInTheDocument();

    // Dialog sollte initial nicht sichtbar sein
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await user.click(trigger);

    // Dialog sollte jetzt sichtbar sein
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    expect(screen.getByText('Test Dialog')).toBeInTheDocument();
    expect(screen.getByText('This is a test dialog')).toBeInTheDocument();
  });

  it('closes dialog when close button is clicked', async () => {
    const user = userEvent.setup();

    render(
      <Dialog defaultOpen>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Closeable Dialog</DialogTitle>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    );

    // Dialog sollte offen sein
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    // Finde close button (X button mit aria-label)
    const closeButton = screen.getByRole('button', { name: /schließen/i });
    await user.click(closeButton);

    // Dialog sollte geschlossen sein
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('displays German accessibility labels', () => {
    render(
      <Dialog defaultOpen>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>German Dialog</DialogTitle>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    );

    // Close button sollte deutsches aria-label haben
    const closeButton = screen.getByLabelText(/dialog schließen/i);
    expect(closeButton).toBeInTheDocument();

    // Screen reader text sollte deutsch sein
    expect(screen.getByText('Schließen')).toHaveClass('sr-only');
  });

  it('renders with header, footer and custom content', () => {
    render(
      <Dialog defaultOpen>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Full Dialog</DialogTitle>
            <DialogDescription>Complete dialog example</DialogDescription>
          </DialogHeader>

          <div>Custom dialog content</div>

          <DialogFooter>
            <Button variant="outline">Abbrechen</Button>
            <Button>Speichern</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );

    expect(screen.getByText('Full Dialog')).toBeInTheDocument();
    expect(screen.getByText('Complete dialog example')).toBeInTheDocument();
    expect(screen.getByText('Custom dialog content')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /abbrechen/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /speichern/i })).toBeInTheDocument();
  });

  it('can be controlled with open prop', () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <Dialog open={false} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogTitle>Controlled Dialog</DialogTitle>
        </DialogContent>
      </Dialog>
    );

    // Dialog sollte geschlossen sein
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    // Open state ändern
    rerender(
      <Dialog open={true} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogTitle>Controlled Dialog</DialogTitle>
        </DialogContent>
      </Dialog>
    );

    // Dialog sollte jetzt offen sein
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('supports keyboard navigation (Escape to close)', async () => {
    const user = userEvent.setup();

    render(
      <Dialog defaultOpen>
        <DialogContent>
          <DialogTitle>Keyboard Dialog</DialogTitle>
        </DialogContent>
      </Dialog>
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();

    // ESC drücken sollte Dialog schließen
    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });
});
