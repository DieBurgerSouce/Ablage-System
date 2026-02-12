import { apiClient } from '@/lib/api/client'

export interface EntityContextData {
  risk_score: number | null
  risk_level: string | null
  risk_trend: string | null
  open_invoices: number
  total_outstanding: number
  avg_payment_days: number
  recent_alerts: Array<{
    id: string
    title: string
    severity: string
    created_at: string
  }>
  skonto_opportunities: number
  skonto_potential_savings: number
}

export async function getEntityContext(entityId: string): Promise<EntityContextData> {
  // Aggregate from existing endpoints
  try {
    const [riskRes, alertsRes] = await Promise.all([
      apiClient.get(`/risk-intelligence/entity/${entityId}/profile`).catch(() => null),
      apiClient.get(`/alerts`, { params: { entity_id: entityId, limit: 5, status: 'NEW' } }).catch(() => null),
    ])

    const risk = riskRes?.data
    const alerts = alertsRes?.data

    return {
      risk_score: risk?.overall_risk_score ?? null,
      risk_level: risk?.risk_level ?? null,
      risk_trend: risk?.analysis?.payment_trend ?? null,
      open_invoices: risk?.analysis?.open_invoices ?? 0,
      total_outstanding: risk?.analysis?.total_outstanding ?? 0,
      avg_payment_days: risk?.analysis?.avg_payment_days ?? 0,
      recent_alerts: (alerts?.items || alerts?.alerts || []).slice(0, 5).map((a: Record<string, unknown>) => ({
        id: String(a.id || ''),
        title: String(a.title || a.message || ''),
        severity: String(a.severity || 'MEDIUM'),
        created_at: String(a.created_at || ''),
      })),
      skonto_opportunities: 0,
      skonto_potential_savings: 0,
    }
  } catch {
    return {
      risk_score: null,
      risk_level: null,
      risk_trend: null,
      open_invoices: 0,
      total_outstanding: 0,
      avg_payment_days: 0,
      recent_alerts: [],
      skonto_opportunities: 0,
      skonto_potential_savings: 0,
    }
  }
}
