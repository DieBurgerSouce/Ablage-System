/**
 * Tests für Company-Setup-Utilities
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
    STORAGE_KEY,
    STORAGE_KEY_SKIPPED,
    resetCompanySetup,
    isCompanySetupComplete,
    isCompanySetupSkipped,
    markCompanySetupComplete,
    markCompanySetupSkipped,
} from '../company-setup-utils'

describe('company-setup-utils', () => {
    beforeEach(() => {
        // Clear localStorage before each test
        localStorage.clear()
        vi.clearAllMocks()
    })

    describe('STORAGE_KEY constants', () => {
        it('hat korrekte Storage-Keys', () => {
            expect(STORAGE_KEY).toBe('ablage_company_setup_complete')
            expect(STORAGE_KEY_SKIPPED).toBe('ablage_company_setup_skipped')
        })
    })

    describe('isCompanySetupComplete', () => {
        it('gibt false zurück wenn nicht gesetzt', () => {
            expect(isCompanySetupComplete()).toBe(false)
        })

        it('gibt false zurück wenn auf falschen Wert gesetzt', () => {
            localStorage.setItem(STORAGE_KEY, 'false')
            expect(isCompanySetupComplete()).toBe(false)
        })

        it('gibt true zurück wenn auf "true" gesetzt', () => {
            localStorage.setItem(STORAGE_KEY, 'true')
            expect(isCompanySetupComplete()).toBe(true)
        })
    })

    describe('isCompanySetupSkipped', () => {
        it('gibt false zurück wenn nicht gesetzt', () => {
            expect(isCompanySetupSkipped()).toBe(false)
        })

        it('gibt false zurück wenn auf falschen Wert gesetzt', () => {
            localStorage.setItem(STORAGE_KEY_SKIPPED, 'false')
            expect(isCompanySetupSkipped()).toBe(false)
        })

        it('gibt true zurück wenn auf "true" gesetzt', () => {
            localStorage.setItem(STORAGE_KEY_SKIPPED, 'true')
            expect(isCompanySetupSkipped()).toBe(true)
        })
    })

    describe('markCompanySetupComplete', () => {
        it('setzt complete-Flag auf true', () => {
            markCompanySetupComplete()
            expect(localStorage.getItem(STORAGE_KEY)).toBe('true')
        })

        it('entfernt skipped-Flag wenn vorhanden', () => {
            localStorage.setItem(STORAGE_KEY_SKIPPED, 'true')
            markCompanySetupComplete()
            expect(localStorage.getItem(STORAGE_KEY_SKIPPED)).toBeNull()
        })

        it('isCompanySetupComplete gibt danach true zurück', () => {
            markCompanySetupComplete()
            expect(isCompanySetupComplete()).toBe(true)
        })
    })

    describe('markCompanySetupSkipped', () => {
        it('setzt skipped-Flag auf true', () => {
            markCompanySetupSkipped()
            expect(localStorage.getItem(STORAGE_KEY_SKIPPED)).toBe('true')
        })

        it('isCompanySetupSkipped gibt danach true zurück', () => {
            markCompanySetupSkipped()
            expect(isCompanySetupSkipped()).toBe(true)
        })

        it('überschreibt complete-Status nicht', () => {
            localStorage.setItem(STORAGE_KEY, 'true')
            markCompanySetupSkipped()
            expect(localStorage.getItem(STORAGE_KEY)).toBe('true')
            expect(localStorage.getItem(STORAGE_KEY_SKIPPED)).toBe('true')
        })
    })

    describe('resetCompanySetup', () => {
        it('entfernt complete-Flag', () => {
            localStorage.setItem(STORAGE_KEY, 'true')
            resetCompanySetup()
            expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
        })

        it('entfernt skipped-Flag', () => {
            localStorage.setItem(STORAGE_KEY_SKIPPED, 'true')
            resetCompanySetup()
            expect(localStorage.getItem(STORAGE_KEY_SKIPPED)).toBeNull()
        })

        it('entfernt beide Flags', () => {
            localStorage.setItem(STORAGE_KEY, 'true')
            localStorage.setItem(STORAGE_KEY_SKIPPED, 'true')
            resetCompanySetup()
            expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
            expect(localStorage.getItem(STORAGE_KEY_SKIPPED)).toBeNull()
        })

        it('isCompanySetupComplete und isCompanySetupSkipped geben danach false zurück', () => {
            markCompanySetupComplete()
            markCompanySetupSkipped()
            resetCompanySetup()
            expect(isCompanySetupComplete()).toBe(false)
            expect(isCompanySetupSkipped()).toBe(false)
        })
    })

    describe('Workflow Integration', () => {
        it('kompletter Workflow: Setup → Complete', () => {
            // Initial
            expect(isCompanySetupComplete()).toBe(false)
            expect(isCompanySetupSkipped()).toBe(false)

            // User completes setup
            markCompanySetupComplete()
            expect(isCompanySetupComplete()).toBe(true)
            expect(isCompanySetupSkipped()).toBe(false)

            // Reset for testing
            resetCompanySetup()
            expect(isCompanySetupComplete()).toBe(false)
        })

        it('kompletter Workflow: Setup → Skip', () => {
            // Initial
            expect(isCompanySetupComplete()).toBe(false)
            expect(isCompanySetupSkipped()).toBe(false)

            // User skips setup
            markCompanySetupSkipped()
            expect(isCompanySetupComplete()).toBe(false)
            expect(isCompanySetupSkipped()).toBe(true)

            // Reset for testing
            resetCompanySetup()
            expect(isCompanySetupSkipped()).toBe(false)
        })

        it('Complete nach Skip setzt Skip zurück', () => {
            markCompanySetupSkipped()
            expect(isCompanySetupSkipped()).toBe(true)

            // User completes setup later
            markCompanySetupComplete()
            expect(isCompanySetupComplete()).toBe(true)
            expect(isCompanySetupSkipped()).toBe(false)
        })
    })
})
