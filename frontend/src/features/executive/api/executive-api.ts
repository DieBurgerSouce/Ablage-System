/**
 * Executive Dashboard API Client
 *
 * API functions for executive reporting endpoints.
 */

import type {
  KPIResponse,
  DepartmentBreakdown,
  TrendResponse,
  ExecutiveSummaryResponse,
  TrendMetric,
} from '../types/executive-types'

const API_BASE = '/api/v1/reporting'

/**
 * Fetch KPIs
 */
export async function getKPIs(): Promise<KPIResponse> {
  const response = await fetch(`${API_BASE}/kpis`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Fehler beim Abrufen der KPIs: ${response.statusText}`)
  }

  return response.json()
}

/**
 * Fetch department breakdown statistics
 */
export async function getDepartments(): Promise<DepartmentBreakdown[]> {
  const response = await fetch(`${API_BASE}/departments`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Fehler beim Abrufen der Abteilungsstatistiken: ${response.statusText}`)
  }

  return response.json()
}

/**
 * Fetch trend data for a metric
 */
export async function getTrend(metric: TrendMetric, days: number = 30): Promise<TrendResponse> {
  const response = await fetch(`${API_BASE}/trends/${metric}?days=${days}`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Fehler beim Abrufen der Trend-Daten: ${response.statusText}`)
  }

  return response.json()
}

/**
 * Fetch complete executive summary
 */
export async function getSummary(): Promise<ExecutiveSummaryResponse> {
  const response = await fetch(`${API_BASE}/summary`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Fehler beim Abrufen der Executive Summary: ${response.statusText}`)
  }

  return response.json()
}
