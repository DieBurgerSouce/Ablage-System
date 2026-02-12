export interface EntityContext {
  id: string
  name: string
  entity_type: 'customer' | 'supplier'
  risk_score: number | null
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | null
  risk_trend: 'IMPROVING' | 'STABLE' | 'WORSENING' | null
}

export interface ChainContext {
  chain_id: string | null
  position: number | null
  total_docs: number
  is_complete: boolean
  open_discrepancies: number
  has_quote: boolean
  has_order: boolean
  has_delivery_note: boolean
  has_invoice: boolean
  has_credit_note: boolean
}

export interface PaymentContext {
  status: 'paid' | 'partial' | 'open' | 'overdue' | 'unknown'
  paid_amount: number | null
  total_amount: number | null
  skonto_available: boolean
  skonto_deadline: string | null
  skonto_amount: number | null
  skonto_percent: number | null
  days_overdue: number
}

export interface PendingAction {
  id: string
  action_type: string
  priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  reason: string
  impact_description: string
}

export interface RelatedDocument {
  id: string
  filename: string
  document_type: string | null
  created_at: string | null
}

export interface DocumentContextData {
  entity: EntityContext | null
  chain: ChainContext | null
  payment: PaymentContext | null
  related_documents: RelatedDocument[]
  pending_actions: PendingAction[]
}
