const { chromium } = require('playwright');

(async () => {
    console.log('Starting login test...');

    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    try {
        // Go to login page
        console.log('Navigating to login page...');
        await page.goto('http://localhost/login', { waitUntil: 'networkidle' });
        await page.waitForTimeout(2000);

        // Screenshot before
        await page.screenshot({ path: 'screenshots/debug-login-1-initial.png', fullPage: true });
        console.log('Screenshot 1: Initial page');

        // Check for email field
        const emailField = await page.$('#email');
        console.log('Email field found:', !!emailField);

        const passwordField = await page.$('#password');
        console.log('Password field found:', !!passwordField);

        if (!emailField || !passwordField) {
            console.log('Fields not found. Page content:');
            const content = await page.content();
            console.log(content.substring(0, 2000));
            await browser.close();
            return;
        }

        // Fill the form
        console.log('Filling email...');
        await emailField.click();
        await page.keyboard.type('admin@localhost.com', { delay: 50 });

        console.log('Filling password...');
        await passwordField.click();
        await page.keyboard.type('admin123', { delay: 50 });

        await page.waitForTimeout(500);
        await page.screenshot({ path: 'screenshots/debug-login-2-filled.png', fullPage: true });
        console.log('Screenshot 2: Form filled');

        // Submit
        console.log('Clicking submit...');
        const submitBtn = await page.$('button[type="submit"]');
        if (submitBtn) {
            await submitBtn.click();
        } else {
            console.log('Submit button not found!');
        }

        // Wait for navigation
        await page.waitForTimeout(5000);
        await page.screenshot({ path: 'screenshots/debug-login-3-after.png', fullPage: true });
        console.log('Screenshot 3: After submit');

        // Check URL
        const url = page.url();
        console.log('Final URL:', url);

        if (!url.includes('/login')) {
            console.log('Login SUCCESS!');
        } else {
            console.log('Login FAILED - still on login page');
            // Check for error message
            const errorDiv = await page.$('.text-destructive');
            if (errorDiv) {
                const errorText = await errorDiv.textContent();
                console.log('Error message:', errorText);
            }
        }

    } catch (e) {
        console.error('Error:', e.message);
        await page.screenshot({ path: 'screenshots/debug-login-error.png', fullPage: true });
    }

    await browser.close();
    console.log('Done.');
})();
