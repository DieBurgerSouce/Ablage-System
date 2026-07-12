/**
 * Regressionstest F-P1-004 (Perception-Audit 2026-07-12).
 *
 * Beim ersten Login oeffneten sich drei Onboarding-Ebenen gleichzeitig
 * (OnboardingWizard-Modal + WelcomeModal + gefuehrte Produkt-Tour), die sich
 * gegenseitig ueberlagerten und u.a. das Suchfeld blockierten.
 *
 * isPrimaryOnboardingPending() ist die gemeinsame Quelle-der-Wahrheit, an der
 * sich die sekundaeren Systeme (Tour) koppeln: solange der Wizard aussteht,
 * darf nichts anderes automatisch aufgehen.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { isPrimaryOnboardingPending } from '../use-onboarding'

const KEY = 'ablage_onboarding_v2'

describe('isPrimaryOnboardingPending (F-P1-004)', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('ist pending, wenn noch kein State existiert (frischer Nutzer)', () => {
    expect(isPrimaryOnboardingPending()).toBe(true)
  })

  it('ist pending, solange weder completed noch skipped', () => {
    window.localStorage.setItem(
      KEY,
      JSON.stringify({ completed: false, skipped: false, currentStep: 1 }),
    )
    expect(isPrimaryOnboardingPending()).toBe(true)
  })

  it('ist NICHT mehr pending, wenn der Wizard abgeschlossen wurde', () => {
    window.localStorage.setItem(KEY, JSON.stringify({ completed: true, skipped: false }))
    expect(isPrimaryOnboardingPending()).toBe(false)
  })

  it('ist NICHT mehr pending, wenn der Wizard uebersprungen wurde', () => {
    window.localStorage.setItem(KEY, JSON.stringify({ completed: false, skipped: true }))
    expect(isPrimaryOnboardingPending()).toBe(false)
  })

  it('ist pending (fail-safe), wenn der State-Eintrag kaputt ist', () => {
    window.localStorage.setItem(KEY, '{kaputt')
    expect(isPrimaryOnboardingPending()).toBe(true)
  })
})
