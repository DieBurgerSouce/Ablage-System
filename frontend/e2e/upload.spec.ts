import { test, expect } from './fixtures';

test.describe('Document Upload', () => {
    // Reaktiviert 2026-06-21: Der React.lazy-Suspense-Hang ist behoben.
    // /upload nutzt jetzt lazyRoute (src/lib/lazyRoute.tsx), das den
    // dynamischen Import selbst via setState erzwingt statt auf den
    // Suspense-Ping zu vertrauen — der UploadWizard mountet im Build.

    test('should load upload page', async ({ authenticatedPage: page }) => {
        await page.goto('/upload');
        await expect(page).toHaveTitle(/Ablage/);

        // Close welcome dialog if present
        const closeButton = page.getByRole('button', { name: /Schliessen|Close/i });
        if (await closeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
            await closeButton.click();
        }

        // Verify upload area is visible with actual text from the UI
        await expect(page.getByText('Drag & Drop oder klicken zum Auswählen')).toBeVisible();
        // Seitentitel ist die h1 des UploadWizard. "Dokumente hochladen" steht
        // zusaetzlich als h3 in der Dropzone -> gezielt level:1 ansprechen
        // (sonst strict-mode-Verletzung).
        await expect(
            page.getByRole('heading', { name: 'Dokumente hochladen', level: 1 })
        ).toBeVisible();
    });
});
