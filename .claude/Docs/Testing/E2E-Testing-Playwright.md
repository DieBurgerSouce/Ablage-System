# E2E-Testing mit Playwright

> **Ablage-System - Vollständiger End-to-End Testing Guide**
> Version: 1.0 | Stand: Januar 2025

---

## Übersicht

Dieses Dokument beschreibt die E2E-Testing-Strategie des Ablage-Systems mit Playwright. E2E-Tests simulieren echte Benutzerinteraktionen und validieren den gesamten Stack.

**Framework:** Playwright 1.40+
**Sprache:** TypeScript
**Browser:** Chromium, Firefox, WebKit
**Parallelisierung:** Ja (Worker-basiert)

---

## Inhaltsverzeichnis

1. [Setup](#setup)
2. [Projektstruktur](#projektstruktur)
3. [Konfiguration](#konfiguration)
4. [Test-Patterns](#test-patterns)
5. [Page Object Model](#page-object-model)
6. [Fixtures & Utilities](#fixtures--utilities)
7. [Authentifizierung](#authentifizierung)
8. [Visual Testing](#visual-testing)
9. [API-Testing](#api-testing)
10. [CI/CD-Integration](#cicd-integration)
11. [Best Practices](#best-practices)

---

## Setup

### Installation

```bash
# Playwright installieren
cd frontend
npm install -D @playwright/test

# Browser installieren
npx playwright install

# Mit Abhängigkeiten (Linux)
npx playwright install --with-deps
```

### Schnellstart

```bash
# Alle Tests ausführen
npm run test:e2e

# Mit UI
npm run test:e2e:ui

# Bestimmte Datei
npx playwright test tests/e2e/documents.spec.ts

# Debug-Modus
npx playwright test --debug

# Headed Mode (Browser sichtbar)
npx playwright test --headed

# Bestimmter Browser
npx playwright test --project=chromium
```

---

## Projektstruktur

```
frontend/
├── tests/
│   └── e2e/
│       ├── fixtures/
│       │   ├── auth.fixture.ts      # Authentifizierung
│       │   ├── documents.fixture.ts # Test-Dokumente
│       │   └── api.fixture.ts       # API-Client
│       ├── pages/
│       │   ├── BasePage.ts          # Basis-Page-Object
│       │   ├── LoginPage.ts
│       │   ├── DashboardPage.ts
│       │   ├── DocumentsPage.ts
│       │   ├── DocumentDetailPage.ts
│       │   ├── SearchPage.ts
│       │   └── AdminPage.ts
│       ├── specs/
│       │   ├── auth.spec.ts
│       │   ├── documents.spec.ts
│       │   ├── search.spec.ts
│       │   ├── ocr.spec.ts
│       │   └── admin.spec.ts
│       ├── utils/
│       │   ├── helpers.ts
│       │   ├── selectors.ts
│       │   └── constants.ts
│       └── global-setup.ts
├── playwright.config.ts
└── .env.test
```

---

## Konfiguration

### playwright.config.ts

```typescript
import { defineConfig, devices } from '@playwright/test';
import dotenv from 'dotenv';

// Umgebungsvariablen laden
dotenv.config({ path: '.env.test' });

export default defineConfig({
  testDir: './tests/e2e/specs',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 4 : undefined,
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/results.json' }],
    ['junit', { outputFile: 'test-results/junit.xml' }],
  ],

  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },

  // Globales Setup/Teardown
  globalSetup: require.resolve('./tests/e2e/global-setup.ts'),

  projects: [
    // Setup-Projekt für Authentifizierung
    {
      name: 'setup',
      testMatch: /global-setup\.ts/,
    },

    // Desktop-Browser
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
    },
    {
      name: 'firefox',
      use: {
        ...devices['Desktop Firefox'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
    },
    {
      name: 'webkit',
      use: {
        ...devices['Desktop Safari'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
    },

    // Mobile-Browser
    {
      name: 'mobile-chrome',
      use: {
        ...devices['Pixel 5'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
    },
    {
      name: 'mobile-safari',
      use: {
        ...devices['iPhone 13'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
    },

    // Admin-Tests (separater Storage-State)
    {
      name: 'admin',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth/admin.json',
      },
      testMatch: /admin\.spec\.ts/,
    },
  ],

  // Lokaler Dev-Server
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});
```

### .env.test

```env
BASE_URL=http://localhost:3000
API_URL=http://localhost:8000
TEST_USER_EMAIL=test@example.com
TEST_USER_PASSWORD=TestPassword123!
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=AdminPassword123!
```

---

## Test-Patterns

### Basis-Test-Struktur

```typescript
// tests/e2e/specs/documents.spec.ts
import { test, expect } from '@playwright/test';
import { DocumentsPage } from '../pages/DocumentsPage';
import { DocumentDetailPage } from '../pages/DocumentDetailPage';

test.describe('Dokumentenverwaltung', () => {
  let documentsPage: DocumentsPage;

  test.beforeEach(async ({ page }) => {
    documentsPage = new DocumentsPage(page);
    await documentsPage.goto();
  });

  test('sollte Dokumentenliste anzeigen', async ({ page }) => {
    await expect(documentsPage.documentList).toBeVisible();
    await expect(documentsPage.getDocumentCount()).toBeGreaterThan(0);
  });

  test('sollte Dokument hochladen können', async ({ page }) => {
    // Arrange
    const testFile = 'tests/e2e/fixtures/files/test-invoice.pdf';

    // Act
    await documentsPage.uploadDocument(testFile);

    // Assert
    await expect(page.getByText('Dokument hochgeladen')).toBeVisible();
    await expect(documentsPage.getLatestDocument()).toContainText('test-invoice.pdf');
  });

  test('sollte Dokument nach Upload verarbeiten', async ({ page }) => {
    // Arrange
    const testFile = 'tests/e2e/fixtures/files/test-invoice.pdf';

    // Act
    await documentsPage.uploadDocument(testFile);
    const documentId = await documentsPage.getLatestDocumentId();

    // Assert - Warte auf Verarbeitung
    const detailPage = new DocumentDetailPage(page);
    await detailPage.goto(documentId);

    await expect(detailPage.status).toHaveText('Verarbeitet', { timeout: 60000 });
    await expect(detailPage.extractedText).not.toBeEmpty();
  });

  test('sollte Dokument löschen können', async ({ page }) => {
    // Arrange
    const documentCount = await documentsPage.getDocumentCount();

    // Act
    await documentsPage.deleteFirstDocument();

    // Assert
    await expect(documentsPage.getDocumentCount()).toBe(documentCount - 1);
  });
});
```

### Parametrisierte Tests

```typescript
// tests/e2e/specs/ocr.spec.ts
import { test, expect } from '@playwright/test';

const testDocuments = [
  { name: 'Rechnung', file: 'invoice.pdf', expectedType: 'invoice' },
  { name: 'Vertrag', file: 'contract.pdf', expectedType: 'contract' },
  { name: 'Lieferschein', file: 'delivery-note.pdf', expectedType: 'delivery_note' },
];

test.describe('OCR-Klassifizierung', () => {
  for (const doc of testDocuments) {
    test(`sollte ${doc.name} korrekt klassifizieren`, async ({ page }) => {
      const documentsPage = new DocumentsPage(page);
      await documentsPage.goto();

      await documentsPage.uploadDocument(`fixtures/files/${doc.file}`);
      await documentsPage.waitForProcessing();

      const detailPage = new DocumentDetailPage(page);
      await detailPage.goto(await documentsPage.getLatestDocumentId());

      await expect(detailPage.documentType).toHaveText(doc.expectedType);
    });
  }
});
```

### Retry-Logik für flaky Tests

```typescript
test('sollte Dokument verarbeiten (mit Retry)', async ({ page }) => {
  // Playwright wiederholt automatisch bei Fehlern (siehe retries in config)

  // Für spezifische Assertions mit Retry
  await expect(async () => {
    const status = await page.locator('[data-testid="status"]').textContent();
    expect(status).toBe('Verarbeitet');
  }).toPass({
    timeout: 60000,
    intervals: [1000, 2000, 5000],
  });
});
```

---

## Page Object Model

### BasePage

```typescript
// tests/e2e/pages/BasePage.ts
import { Page, Locator } from '@playwright/test';

export abstract class BasePage {
  protected page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // Gemeinsame Elemente
  get header(): Locator {
    return this.page.locator('header');
  }

  get sidebar(): Locator {
    return this.page.locator('[data-testid="sidebar"]');
  }

  get loadingSpinner(): Locator {
    return this.page.locator('[data-testid="loading"]');
  }

  get toastNotification(): Locator {
    return this.page.locator('[data-testid="toast"]');
  }

  // Gemeinsame Aktionen
  async waitForPageLoad(): Promise<void> {
    await this.page.waitForLoadState('networkidle');
    await this.loadingSpinner.waitFor({ state: 'hidden', timeout: 30000 });
  }

  async waitForToast(message: string): Promise<void> {
    await this.page.getByText(message).waitFor({ state: 'visible' });
  }

  async dismissToast(): Promise<void> {
    await this.toastNotification.locator('button[aria-label="Schließen"]').click();
  }

  async navigateTo(path: string): Promise<void> {
    await this.page.goto(path);
    await this.waitForPageLoad();
  }

  // Screenshot für Visual Testing
  async takeScreenshot(name: string): Promise<void> {
    await this.page.screenshot({ path: `screenshots/${name}.png`, fullPage: true });
  }
}
```

### DocumentsPage

```typescript
// tests/e2e/pages/DocumentsPage.ts
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class DocumentsPage extends BasePage {
  // Locators
  get documentList(): Locator {
    return this.page.locator('[data-testid="document-list"]');
  }

  get uploadButton(): Locator {
    return this.page.locator('[data-testid="upload-button"]');
  }

  get uploadInput(): Locator {
    return this.page.locator('input[type="file"]');
  }

  get searchInput(): Locator {
    return this.page.locator('[data-testid="search-input"]');
  }

  get filterDropdown(): Locator {
    return this.page.locator('[data-testid="filter-dropdown"]');
  }

  get documentCards(): Locator {
    return this.documentList.locator('[data-testid="document-card"]');
  }

  get emptyState(): Locator {
    return this.page.locator('[data-testid="empty-state"]');
  }

  // Navigation
  async goto(): Promise<void> {
    await this.navigateTo('/documents');
  }

  // Aktionen
  async uploadDocument(filePath: string): Promise<void> {
    // File-Input finden und Datei setzen
    await this.uploadInput.setInputFiles(filePath);

    // Warten auf Upload-Bestätigung
    await this.waitForToast('Dokument hochgeladen');
  }

  async uploadMultipleDocuments(filePaths: string[]): Promise<void> {
    await this.uploadInput.setInputFiles(filePaths);
    await this.waitForToast(`${filePaths.length} Dokumente hochgeladen`);
  }

  async searchDocuments(query: string): Promise<void> {
    await this.searchInput.fill(query);
    await this.page.keyboard.press('Enter');
    await this.waitForPageLoad();
  }

  async filterByType(type: string): Promise<void> {
    await this.filterDropdown.click();
    await this.page.getByRole('option', { name: type }).click();
    await this.waitForPageLoad();
  }

  async deleteFirstDocument(): Promise<void> {
    const firstCard = this.documentCards.first();
    await firstCard.hover();
    await firstCard.locator('[data-testid="delete-button"]').click();

    // Bestätigungsdialog
    await this.page.getByRole('button', { name: 'Löschen' }).click();
    await this.waitForToast('Dokument gelöscht');
  }

  async waitForProcessing(timeout = 60000): Promise<void> {
    await expect(this.documentCards.first().locator('[data-testid="status"]'))
      .toHaveText('Verarbeitet', { timeout });
  }

  // Getter
  async getDocumentCount(): Promise<number> {
    return await this.documentCards.count();
  }

  async getLatestDocumentId(): Promise<string> {
    const href = await this.documentCards.first().getAttribute('href');
    return href?.split('/').pop() || '';
  }

  getLatestDocument(): Locator {
    return this.documentCards.first();
  }

  getDocumentByName(name: string): Locator {
    return this.documentCards.filter({ hasText: name });
  }
}
```

### LoginPage

```typescript
// tests/e2e/pages/LoginPage.ts
import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage';

export class LoginPage extends BasePage {
  get emailInput(): Locator {
    return this.page.locator('[data-testid="email-input"]');
  }

  get passwordInput(): Locator {
    return this.page.locator('[data-testid="password-input"]');
  }

  get loginButton(): Locator {
    return this.page.locator('[data-testid="login-button"]');
  }

  get errorMessage(): Locator {
    return this.page.locator('[data-testid="error-message"]');
  }

  get forgotPasswordLink(): Locator {
    return this.page.getByRole('link', { name: 'Passwort vergessen?' });
  }

  async goto(): Promise<void> {
    await this.navigateTo('/login');
  }

  async login(email: string, password: string): Promise<void> {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.loginButton.click();

    // Warten auf Weiterleitung
    await this.page.waitForURL('**/dashboard');
  }

  async attemptLogin(email: string, password: string): Promise<void> {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.loginButton.click();
  }
}
```

---

## Fixtures & Utilities

### Auth Fixture

```typescript
// tests/e2e/fixtures/auth.fixture.ts
import { test as base } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';

type AuthFixtures = {
  authenticatedPage: void;
  adminPage: void;
};

export const test = base.extend<AuthFixtures>({
  authenticatedPage: async ({ page }, use) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login(
      process.env.TEST_USER_EMAIL!,
      process.env.TEST_USER_PASSWORD!
    );
    await use();
  },

  adminPage: async ({ page }, use) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login(
      process.env.ADMIN_EMAIL!,
      process.env.ADMIN_PASSWORD!
    );
    await use();
  },
});

export { expect } from '@playwright/test';
```

### API Fixture

```typescript
// tests/e2e/fixtures/api.fixture.ts
import { test as base, APIRequestContext, request } from '@playwright/test';

type APIFixtures = {
  apiContext: APIRequestContext;
  authenticatedAPI: APIRequestContext;
};

export const test = base.extend<APIFixtures>({
  apiContext: async ({}, use) => {
    const context = await request.newContext({
      baseURL: process.env.API_URL,
    });
    await use(context);
    await context.dispose();
  },

  authenticatedAPI: async ({}, use) => {
    // Login und Token holen
    const context = await request.newContext({
      baseURL: process.env.API_URL,
    });

    const response = await context.post('/api/v1/auth/login', {
      data: {
        email: process.env.TEST_USER_EMAIL,
        password: process.env.TEST_USER_PASSWORD,
      },
    });

    const { access_token } = await response.json();

    // Neuer Context mit Auth
    const authContext = await request.newContext({
      baseURL: process.env.API_URL,
      extraHTTPHeaders: {
        Authorization: `Bearer ${access_token}`,
      },
    });

    await use(authContext);
    await authContext.dispose();
    await context.dispose();
  },
});

export { expect } from '@playwright/test';
```

### Test-Helpers

```typescript
// tests/e2e/utils/helpers.ts
import { Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

export async function waitForNetworkIdle(page: Page, timeout = 5000): Promise<void> {
  await page.waitForLoadState('networkidle', { timeout });
}

export async function retryAction<T>(
  action: () => Promise<T>,
  maxRetries = 3,
  delay = 1000
): Promise<T> {
  let lastError: Error | undefined;

  for (let i = 0; i < maxRetries; i++) {
    try {
      return await action();
    } catch (error) {
      lastError = error as Error;
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }

  throw lastError;
}

export function getTestFilePath(filename: string): string {
  return path.join(__dirname, '../fixtures/files', filename);
}

export async function createTempFile(content: string, extension: string): Promise<string> {
  const tempDir = path.join(__dirname, '../temp');
  if (!fs.existsSync(tempDir)) {
    fs.mkdirSync(tempDir, { recursive: true });
  }

  const filePath = path.join(tempDir, `temp-${Date.now()}.${extension}`);
  fs.writeFileSync(filePath, content);
  return filePath;
}

export async function cleanupTempFiles(): Promise<void> {
  const tempDir = path.join(__dirname, '../temp');
  if (fs.existsSync(tempDir)) {
    fs.rmSync(tempDir, { recursive: true });
  }
}

export function generateRandomString(length: number): string {
  return Math.random().toString(36).substring(2, 2 + length);
}

export async function mockAPIResponse(
  page: Page,
  url: string,
  response: object
): Promise<void> {
  await page.route(url, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response),
    });
  });
}
```

---

## Authentifizierung

### Global Setup

```typescript
// tests/e2e/global-setup.ts
import { chromium, FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  const browser = await chromium.launch();

  // Standard-Benutzer authentifizieren
  const userContext = await browser.newContext();
  const userPage = await userContext.newPage();

  await userPage.goto(`${config.projects[0].use.baseURL}/login`);
  await userPage.fill('[data-testid="email-input"]', process.env.TEST_USER_EMAIL!);
  await userPage.fill('[data-testid="password-input"]', process.env.TEST_USER_PASSWORD!);
  await userPage.click('[data-testid="login-button"]');
  await userPage.waitForURL('**/dashboard');

  // Storage-State speichern
  await userContext.storageState({ path: '.auth/user.json' });

  // Admin authentifizieren
  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();

  await adminPage.goto(`${config.projects[0].use.baseURL}/login`);
  await adminPage.fill('[data-testid="email-input"]', process.env.ADMIN_EMAIL!);
  await adminPage.fill('[data-testid="password-input"]', process.env.ADMIN_PASSWORD!);
  await adminPage.click('[data-testid="login-button"]');
  await adminPage.waitForURL('**/dashboard');

  await adminContext.storageState({ path: '.auth/admin.json' });

  await browser.close();
}

export default globalSetup;
```

### Auth-Tests

```typescript
// tests/e2e/specs/auth.spec.ts
import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';

test.describe('Authentifizierung', () => {
  // Diese Tests brauchen KEINE vorherige Auth
  test.use({ storageState: { cookies: [], origins: [] } });

  test('sollte Login-Seite anzeigen', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    await expect(loginPage.emailInput).toBeVisible();
    await expect(loginPage.passwordInput).toBeVisible();
    await expect(loginPage.loginButton).toBeVisible();
  });

  test('sollte bei korrekten Credentials anmelden', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    await loginPage.login(
      process.env.TEST_USER_EMAIL!,
      process.env.TEST_USER_PASSWORD!
    );

    await expect(page).toHaveURL(/.*dashboard/);
  });

  test('sollte bei falschen Credentials Fehler anzeigen', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    await loginPage.attemptLogin('wrong@email.com', 'wrongpassword');

    await expect(loginPage.errorMessage).toBeVisible();
    await expect(loginPage.errorMessage).toContainText('Ungültige Anmeldedaten');
  });

  test('sollte nach 3 Fehlversuchen Account sperren', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    for (let i = 0; i < 3; i++) {
      await loginPage.attemptLogin('test@example.com', 'wrongpassword');
      await page.waitForTimeout(500);
    }

    await expect(loginPage.errorMessage).toContainText('Account gesperrt');
  });
});
```

---

## Visual Testing

### Screenshot-Vergleich

```typescript
// tests/e2e/specs/visual.spec.ts
import { test, expect } from '@playwright/test';
import { DocumentsPage } from '../pages/DocumentsPage';

test.describe('Visual Regression', () => {
  test('Dashboard sollte korrekt aussehen', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    await expect(page).toHaveScreenshot('dashboard.png', {
      maxDiffPixelRatio: 0.02,
      animations: 'disabled',
    });
  });

  test('Dokumentenliste sollte korrekt aussehen', async ({ page }) => {
    const documentsPage = new DocumentsPage(page);
    await documentsPage.goto();

    await expect(documentsPage.documentList).toHaveScreenshot('document-list.png', {
      maxDiffPixelRatio: 0.02,
    });
  });

  test('Dark Mode sollte korrekt aussehen', async ({ page }) => {
    await page.goto('/dashboard');

    // Dark Mode aktivieren
    await page.evaluate(() => {
      document.documentElement.classList.add('dark');
    });

    await expect(page).toHaveScreenshot('dashboard-dark.png');
  });

  test('Mobile Ansicht sollte korrekt aussehen', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/dashboard');

    await expect(page).toHaveScreenshot('dashboard-mobile.png');
  });
});
```

### Screenshot-Updates

```bash
# Baseline-Screenshots aktualisieren
npx playwright test --update-snapshots

# Nur für bestimmte Tests
npx playwright test visual.spec.ts --update-snapshots
```

---

## API-Testing

### API-Tests mit Playwright

```typescript
// tests/e2e/specs/api.spec.ts
import { test, expect } from '../fixtures/api.fixture';

test.describe('API Tests', () => {
  test('sollte Dokumente auflisten (GET /documents)', async ({ authenticatedAPI }) => {
    const response = await authenticatedAPI.get('/api/v1/documents');

    expect(response.ok()).toBeTruthy();
    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.items).toBeInstanceOf(Array);
    expect(data.total).toBeGreaterThanOrEqual(0);
  });

  test('sollte Dokument erstellen (POST /documents)', async ({ authenticatedAPI }) => {
    const response = await authenticatedAPI.post('/api/v1/documents', {
      multipart: {
        file: {
          name: 'test.pdf',
          mimeType: 'application/pdf',
          buffer: Buffer.from('PDF content'),
        },
      },
    });

    expect(response.status()).toBe(201);

    const data = await response.json();
    expect(data.id).toBeDefined();
    expect(data.filename).toBe('test.pdf');
  });

  test('sollte Fehler bei ungültigem Token zurückgeben', async ({ apiContext }) => {
    const response = await apiContext.get('/api/v1/documents', {
      headers: {
        Authorization: 'Bearer invalid_token',
      },
    });

    expect(response.status()).toBe(401);
  });

  test('sollte Rate-Limiting anwenden', async ({ authenticatedAPI }) => {
    const requests = Array(120).fill(null).map(() =>
      authenticatedAPI.get('/api/v1/documents')
    );

    const responses = await Promise.all(requests);
    const rateLimited = responses.filter(r => r.status() === 429);

    expect(rateLimited.length).toBeGreaterThan(0);
  });
});
```

---

## CI/CD-Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/e2e-tests.yml
name: E2E Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: ablage_test
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        ports:
          - 5432:5432

      redis:
        image: redis:7
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: |
          cd frontend
          npm ci

      - name: Install Playwright browsers
        run: |
          cd frontend
          npx playwright install --with-deps

      - name: Start backend
        run: |
          docker-compose -f docker-compose.test.yml up -d backend
          ./scripts/wait-for-backend.sh

      - name: Run E2E tests
        run: |
          cd frontend
          npm run test:e2e
        env:
          BASE_URL: http://localhost:3000
          API_URL: http://localhost:8000
          TEST_USER_EMAIL: ${{ secrets.TEST_USER_EMAIL }}
          TEST_USER_PASSWORD: ${{ secrets.TEST_USER_PASSWORD }}

      - name: Upload test results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playwright-report
          path: frontend/playwright-report/
          retention-days: 30

      - name: Upload screenshots
        uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: failure-screenshots
          path: frontend/test-results/
          retention-days: 7
```

### Docker-basierte E2E-Tests

```yaml
# docker-compose.e2e.yml
version: '3.8'

services:
  e2e-runner:
    build:
      context: ./frontend
      dockerfile: Dockerfile.e2e
    volumes:
      - ./frontend/tests:/app/tests
      - ./frontend/playwright-report:/app/playwright-report
    environment:
      - BASE_URL=http://frontend:3000
      - API_URL=http://backend:8000
    depends_on:
      - frontend
      - backend
    command: npx playwright test

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"

  backend:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
```

---

## Best Practices

### 1. Stabile Selektoren verwenden

```typescript
// ❌ Schlecht - Fragile Selektoren
await page.click('.btn-primary');
await page.locator('div > div > button').click();

// ✅ Gut - Stabile Selektoren
await page.click('[data-testid="submit-button"]');
await page.getByRole('button', { name: 'Speichern' }).click();
await page.getByLabel('E-Mail').fill('test@example.com');
```

### 2. Auf sichtbare Elemente warten

```typescript
// ❌ Schlecht - Keine Wartelogik
await page.click('#dynamic-button');

// ✅ Gut - Explizites Warten
await page.locator('#dynamic-button').waitFor({ state: 'visible' });
await page.locator('#dynamic-button').click();
```

### 3. Isolation zwischen Tests

```typescript
// ❌ Schlecht - Tests sind abhängig
test('Test 1 erstellt Dokument', async () => { /* ... */ });
test('Test 2 verwendet Dokument von Test 1', async () => { /* ... */ });

// ✅ Gut - Jeder Test ist unabhängig
test.beforeEach(async ({ page }) => {
  // Test-Daten für jeden Test erstellen
  await createTestDocument();
});

test.afterEach(async ({ page }) => {
  // Aufräumen
  await cleanupTestData();
});
```

### 4. Aussagekräftige Fehlermeldungen

```typescript
// ❌ Schlecht - Generische Assertion
await expect(page.locator('.status')).toHaveText('active');

// ✅ Gut - Beschreibende Assertion
await expect(
  page.locator('[data-testid="document-status"]'),
  'Dokumentstatus sollte "Verarbeitet" sein'
).toHaveText('Verarbeitet');
```

### 5. Timeouts anpassen

```typescript
// Für langsame Operationen
await expect(page.locator('[data-testid="ocr-result"]'))
  .toBeVisible({ timeout: 60000 }); // 60s für OCR

// Für schnelle Operationen
await expect(page.locator('[data-testid="toast"]'))
  .toBeVisible({ timeout: 5000 }); // 5s für Toast
```

---

*Letzte Aktualisierung: Januar 2025*
