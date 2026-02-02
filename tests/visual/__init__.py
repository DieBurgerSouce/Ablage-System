# -*- coding: utf-8 -*-
"""
Visual Regression Tests Package

Contains Playwright-based visual regression tests for the Ablage-System.
Tests compare screenshots against baseline images to detect unintended
visual changes.

Test files:
- pages.visual.spec.ts: Key page screenshots
- playwright-visual.config.ts: Visual test configuration

Usage:
    npx playwright test --config=tests/visual/playwright-visual.config.ts

To update baselines:
    UPDATE_SNAPSHOTS=true npx playwright test --config=tests/visual/playwright-visual.config.ts
"""
