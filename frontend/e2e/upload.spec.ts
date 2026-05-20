import { test, expect } from './fixtures';

test.describe('Document Upload', () => {
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
        await expect(page.getByRole('heading', { name: 'Dokumente hochladen' })).toBeVisible();
    });
});
