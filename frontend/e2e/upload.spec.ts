import { test, expect } from '@playwright/test';

test.describe('Document Upload', () => {
    test('should load upload page', async ({ page }) => {
        await page.goto('/upload');
        await expect(page).toHaveTitle(/Ablage/);
        await expect(page.getByText('Dateien hierher ziehen')).toBeVisible();
    });
});
