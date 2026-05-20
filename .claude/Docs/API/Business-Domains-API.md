# Business Domains API Documentation

> Enterprise-grade API documentation for Ablage-System business domain endpoints

**Version:** 1.0
**Last Updated:** 2026-01-08
**Status:** Production-Ready

---

## Overview

This document provides comprehensive API documentation for all business domain endpoints in the Ablage-System. These APIs cover:

| Domain | Endpoints | Description |
|--------|-----------|-------------|
| **Kassenbuch** | 25+ | GoBD-compliant cash book management |
| **Banking** | 90+ | Bank accounts, imports, transactions, reconciliation |
| **Expenses** | 20+ | Expense reports and reimbursement workflows |
| **Finance** | 25+ | Year-based finance document management |
| **DATEV** | 15+ | Tax advisor export integration |

---

## Table of Contents

1. [Authentication & Authorization](#1-authentication--authorization)
2. [Rate Limiting](#2-rate-limiting)
3. [Error Handling](#3-error-handling)
4. [Kassenbuch API](#4-kassenbuch-api)
5. [Banking API](#5-banking-api)
6. [Expenses API](#6-expenses-api)
7. [Finance API](#7-finance-api)
8. [DATEV API](#8-datev-api)

---

## 1. Authentication & Authorization

All business domain endpoints require authentication via JWT Bearer token.

### Headers

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Permission Levels

| Permission | Description |
|------------|-------------|
| `cash_read` | View cash book entries |
| `cash_write` | Create/modify cash entries |
| `banking_read` | View bank accounts and transactions |
| `banking_write` | Create payments, reconcile transactions |
| `expense_read` | View expense reports |
| `expense_write` | Create/submit expense reports |
| `expense_approve` | Approve/reject expense reports |
| `finance_read` | View finance documents |
| `finance_write` | Create/modify finance documents |
| `finance_delete` | Delete finance documents |
| `datev_export` | Export to DATEV format |

---

## 2. Rate Limiting

All endpoints are rate-limited to prevent abuse. Limits are per-user.

### Standard Rate Limits

| Operation Type | Limit | Notes |
|---------------|-------|-------|
| Read operations | 100/minute | GET requests |
| Create operations | 30/minute | POST requests |
| Critical operations | 10/minute | Payments, exports |
| TAN confirmation | 5/minute | Brute-force protection |
| Batch operations | 10/minute | Bulk processing |

### Rate Limit Headers

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704672000
```

### Rate Limit Exceeded Response

```json
{
  "detail": "Rate limit exceeded. Please try again later.",
  "retry_after": 60
}
```

---

## 3. Error Handling

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 204 | No Content (successful deletion) |
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Invalid/missing token |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found |
| 422 | Validation Error |
| 429 | Rate Limit Exceeded |
| 500 | Internal Server Error |

### Error Response Format

```json
{
  "detail": "Dokument nicht gefunden",
  "error_code": "NOT_FOUND",
  "timestamp": "2026-01-08T12:00:00Z"
}
```

### Security Note

All error messages are generic German messages for security. Internal details are never exposed to prevent information leakage.

---

## 4. Kassenbuch API

> GoBD-compliant cash book management with APPEND-ONLY entries

**Base Path:** `/api/v1/cash`

### Design Principles

- **APPEND-ONLY**: Entries cannot be modified or deleted (GoBD compliance)
- **Storno**: Corrections are made via cancellation entries
- **Idempotency**: Duplicate prevention via idempotency keys
- **Audit Trail**: Complete history of all operations

### 4.1 Registers

#### List Cash Registers

```http
GET /api/v1/cash/registers
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `offset` | integer | No | Pagination offset (default: 0) |
| `limit` | integer | No | Max results (default: 50, max: 200) |
| `include_inactive` | boolean | No | Include inactive registers |

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Hauptkasse",
      "description": "Hauptgeschäftskasse",
      "location": "Büro EG",
      "currency": "EUR",
      "opening_balance": 500.00,
      "current_balance": 1234.56,
      "is_active": true,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total": 3,
  "offset": 0,
  "limit": 50
}
```

#### Create Cash Register

```http
POST /api/v1/cash/registers
```

**Rate Limit:** 10/minute

**Request Body:**

```json
{
  "name": "Nebenkasse",
  "description": "Kasse für Lager",
  "location": "Lager Halle 2",
  "currency": "EUR",
  "opening_balance": 200.00
}
```

**Response:** `201 Created`

#### Get Register Details

```http
GET /api/v1/cash/registers/{register_id}
```

**Response:** `200 OK`

### 4.2 Cash Entries (APPEND-ONLY)

#### List Entries

```http
GET /api/v1/cash/registers/{register_id}/entries
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `date_from` | date | Filter from date |
| `date_to` | date | Filter to date |
| `entry_type` | string | `income` or `expense` |
| `category_id` | uuid | Filter by category |
| `search` | string | Full-text search |
| `offset` | integer | Pagination offset |
| `limit` | integer | Max results (max: 200) |

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "entry_number": "K-2026-0001",
      "entry_date": "2026-01-08",
      "entry_type": "income",
      "amount": 150.00,
      "description": "Barverkauf",
      "category": {
        "id": "uuid",
        "name": "Bareinnahmen"
      },
      "reference": "RE-2026-0042",
      "created_by": "user-uuid",
      "created_at": "2026-01-08T10:30:00Z",
      "is_cancelled": false,
      "running_balance": 1384.56
    }
  ],
  "total": 156,
  "offset": 0,
  "limit": 50
}
```

#### Create Cash Entry

```http
POST /api/v1/cash/registers/{register_id}/entries
```

**Rate Limit:** 10/minute

**Request Body:**

```json
{
  "entry_date": "2026-01-08",
  "entry_type": "expense",
  "amount": 45.50,
  "description": "Büromaterial",
  "category_id": "uuid",
  "reference": "Quittung #123",
  "document_ids": ["uuid"],
  "idempotency_key": "unique-client-key"
}
```

**Idempotency:** The `idempotency_key` prevents duplicate entries on network retries. If the same key is sent twice, the original entry is returned.

**Response:** `201 Created`

```json
{
  "id": "uuid",
  "entry_number": "K-2026-0157",
  "entry_date": "2026-01-08",
  "entry_type": "expense",
  "amount": 45.50,
  "description": "Büromaterial",
  "running_balance": 1339.06,
  "created_at": "2026-01-08T11:00:00Z"
}
```

#### Cancel Entry (Storno)

```http
POST /api/v1/cash/registers/{register_id}/entries/{entry_id}/cancel
```

**Rate Limit:** 10/minute

Creates a reversal entry with negative amount. The original entry is marked as cancelled but never deleted (GoBD compliance).

**Request Body:**

```json
{
  "reason": "Fehlerhafte Buchung - falscher Betrag"
}
```

**Response:** `201 Created` - Returns the storno entry

### 4.3 Cash Count (Kassenabschluss)

#### Perform Cash Count

```http
POST /api/v1/cash/registers/{register_id}/count
```

**Rate Limit:** 5/minute

**Request Body:**

```json
{
  "count_date": "2026-01-08",
  "counted_amount": 1339.06,
  "notes": "Kassenabschluss Tagesende",
  "denomination_breakdown": {
    "500": 0,
    "200": 1,
    "100": 6,
    "50": 5,
    "20": 3,
    "10": 2,
    "5": 1,
    "2": 3,
    "1": 4,
    "0.50": 6,
    "0.20": 3,
    "0.10": 6,
    "0.05": 2,
    "0.02": 3,
    "0.01": 0
  }
}
```

**Response:** `201 Created`

```json
{
  "id": "uuid",
  "count_date": "2026-01-08",
  "expected_balance": 1339.06,
  "counted_amount": 1339.06,
  "difference": 0.00,
  "difference_status": "balanced",
  "performed_by": "user-uuid",
  "created_at": "2026-01-08T18:00:00Z"
}
```

### 4.4 Reports & Statistics

#### Daily Summary

```http
GET /api/v1/cash/registers/{register_id}/summary/daily
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `date_from` | date | Start date |
| `date_to` | date | End date |

**Response:** `200 OK`

```json
{
  "summaries": [
    {
      "date": "2026-01-08",
      "income_total": 450.00,
      "expense_total": 125.50,
      "net_change": 324.50,
      "opening_balance": 1014.56,
      "closing_balance": 1339.06,
      "entry_count": 8
    }
  ]
}
```

#### Cash Summary

```http
GET /api/v1/cash/registers/{register_id}/summary
```

**Response:** `200 OK`

```json
{
  "register_id": "uuid",
  "register_name": "Hauptkasse",
  "current_balance": 1339.06,
  "today_income": 450.00,
  "today_expense": 125.50,
  "month_income": 12500.00,
  "month_expense": 4500.00,
  "last_count_date": "2026-01-08",
  "last_count_difference": 0.00,
  "entry_count_total": 1256
}
```

### 4.5 Exports

#### Export to CSV

```http
GET /api/v1/cash/registers/{register_id}/export/csv
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `date_from` | date | Start date |
| `date_to` | date | End date |

**Response:** `200 OK` - Returns CSV file

#### Export to PDF (Kassenbuch)

```http
GET /api/v1/cash/registers/{register_id}/export/pdf
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `date_from` | date | Start date |
| `date_to` | date | End date |
| `include_signature_line` | boolean | Add signature line |

**Response:** `200 OK` - Returns PDF file

#### Export to DATEV

```http
GET /api/v1/cash/registers/{register_id}/export/datev
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `date_from` | date | Start date |
| `date_to` | date | End date |

**Response:** `200 OK` - Returns DATEV-compatible CSV

### 4.6 Categories

#### List Categories

```http
GET /api/v1/cash/categories
```

#### Create Category

```http
POST /api/v1/cash/categories
```

**Request Body:**

```json
{
  "name": "Portokosten",
  "entry_type": "expense",
  "datev_account": "4910"
}
```

---

## 5. Banking API

> Comprehensive banking management with imports, reconciliation, and dunning

**Base Path:** `/api/v1/banking`

### 5.1 Bank Accounts

#### List Accounts

```http
GET /api/v1/banking/accounts
```

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Geschäftskonto",
      "iban": "DE89370400440532013000",
      "bic": "COBADEFFXXX",
      "bank_name": "Commerzbank",
      "account_type": "checking",
      "currency": "EUR",
      "current_balance": 45678.90,
      "available_balance": 45000.00,
      "is_active": true,
      "last_sync": "2026-01-08T06:00:00Z"
    }
  ],
  "total": 3
}
```

#### Create Account

```http
POST /api/v1/banking/accounts
```

**Rate Limit:** 10/minute

**Request Body:**

```json
{
  "name": "Sparkonto",
  "iban": "DE89370400440532013001",
  "bic": "COBADEFFXXX",
  "bank_name": "Commerzbank",
  "account_type": "savings",
  "opening_balance": 10000.00
}
```

#### Get Account Balance History

```http
GET /api/v1/banking/accounts/{account_id}/balance-history
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `period` | string | `7d`, `30d`, `90d`, `1y` |

### 5.2 Imports

#### Supported Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| MT940 | `.sta`, `.940` | SWIFT standard, universal |
| CAMT.053 | `.xml` | ISO 20022, modern XML |
| CSV | `.csv` | Bank-specific formats |

Supported banks for CSV: Sparkasse, VR-Bank, DKB, N26, Commerzbank, Deutsche Bank, ING, Comdirect

#### Preview Import

```http
POST /api/v1/banking/imports/preview
```

**Rate Limit:** 30/minute

**Request:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `file` | file | Bank statement file |
| `format_hint` | string | Optional: `mt940`, `camt053`, `csv` |

**Response:** `200 OK`

```json
{
  "format_detected": "mt940",
  "format_confidence": 0.98,
  "transaction_count": 45,
  "period": {
    "from": "2026-01-01",
    "to": "2026-01-08"
  },
  "totals": {
    "income": 12500.00,
    "expense": 8900.00,
    "net": 3600.00
  },
  "sample_transactions": [
    {
      "date": "2026-01-08",
      "amount": 500.00,
      "description": "Kunde Müller GmbH",
      "reference": "RE-2026-0042"
    }
  ]
}
```

#### Import File

```http
POST /api/v1/banking/imports
```

**Rate Limit:** 20/minute

**Request:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `file` | file | Bank statement file |
| `bank_account_id` | uuid | Target account (optional, auto-detect from IBAN) |
| `format_hint` | string | Optional format hint |

**Response:** `201 Created`

```json
{
  "id": "uuid",
  "filename": "kontoauszug_2026_01.sta",
  "format": "mt940",
  "transaction_count": 45,
  "duplicate_count": 3,
  "error_count": 0,
  "imported_at": "2026-01-08T12:00:00Z"
}
```

#### Import History

```http
GET /api/v1/banking/imports/history
```

### 5.3 Transactions

#### List Transactions

```http
GET /api/v1/banking/transactions
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `bank_account_id` | uuid | Filter by account |
| `date_from` | date | From date |
| `date_to` | date | To date |
| `amount_min` | float | Minimum amount |
| `amount_max` | float | Maximum amount |
| `transaction_type` | string | `credit`, `debit` |
| `reconciliation_status` | string | `unmatched`, `matched`, `partial`, `manual` |
| `search` | string | Full-text search |
| `offset` | integer | Pagination offset |
| `limit` | integer | Max results (max: 200) |
| `sort_by` | string | `booking_date`, `amount`, `counterparty` |
| `sort_order` | string | `asc`, `desc` |

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "booking_date": "2026-01-08",
      "value_date": "2026-01-08",
      "amount": 500.00,
      "currency": "EUR",
      "transaction_type": "credit",
      "counterparty_name": "Müller GmbH",
      "counterparty_iban": "DE89370400440532013002",
      "reference": "RE-2026-0042",
      "description": "Rechnung 2026-0042",
      "reconciliation_status": "matched",
      "matched_document_id": "uuid",
      "match_confidence": 0.95,
      "category": "Umsatzerlöse",
      "tags": ["kunde-mueller", "q1-2026"]
    }
  ],
  "total": 1256,
  "offset": 0,
  "limit": 50
}
```

#### Get Transaction Details

```http
GET /api/v1/banking/transactions/{transaction_id}
```

#### Update Transaction Metadata

```http
PATCH /api/v1/banking/transactions/{transaction_id}
```

**Request Body:**

```json
{
  "notes": "Zahlungseingang für Projekt XYZ",
  "tags": ["projekt-xyz", "kunde-mueller"],
  "category": "Projekteinnahmen"
}
```

#### Get Unmatched Transactions

```http
GET /api/v1/banking/transactions/unmatched
```

#### Transaction Statistics

```http
GET /api/v1/banking/transactions/stats
```

**Response:** `200 OK`

```json
{
  "total_transactions": 1256,
  "matched_count": 1100,
  "unmatched_count": 156,
  "match_rate": 87.6,
  "total_income": 125000.00,
  "total_expense": 85000.00,
  "average_transaction": 167.50
}
```

#### Monthly Summary

```http
GET /api/v1/banking/transactions/monthly
```

#### Top Counterparties

```http
GET /api/v1/banking/transactions/counterparties
```

### 5.4 Reconciliation

#### Get Match Suggestions

```http
GET /api/v1/banking/reconciliation/suggestions/{transaction_id}
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Max suggestions (default: 5) |

**Response:** `200 OK`

```json
[
  {
    "document_id": "uuid",
    "invoice_number": "RE-2026-0042",
    "invoice_date": "2026-01-05",
    "due_date": "2026-01-19",
    "gross_amount": "500.00",
    "counterparty_name": "Müller GmbH",
    "counterparty_iban": "DE89370400440532013002",
    "confidence": 0.95,
    "match_method": "iban_amount",
    "match_details": {
      "iban_match": true,
      "amount_match": true,
      "reference_match": false
    }
  }
]
```

**Match Methods:**

| Method | Confidence | Description |
|--------|------------|-------------|
| `iban_amount` | 95% | IBAN + exact amount match |
| `reference_amount` | 90% | Invoice number in reference + amount |
| `customer_amount_date` | 80% | Customer + amount + date proximity |
| `amount_date` | 70% | Amount + date proximity |
| `fuzzy_name` | 60% | Fuzzy name matching |

#### Manual Match

```http
POST /api/v1/banking/reconciliation/match/{transaction_id}
```

**Rate Limit:** 60/minute

**Request Body:**

```json
{
  "document_id": "uuid",
  "notes": "Manuell zugeordnet - Kunde hat Referenz vergessen"
}
```

#### Unmatch Transaction

```http
POST /api/v1/banking/reconciliation/unmatch/{transaction_id}
```

**Rate Limit:** 60/minute

**Response:** `204 No Content`

#### Split Transaction

```http
POST /api/v1/banking/reconciliation/split/{transaction_id}
```

**Rate Limit:** 60/minute

For collective payments covering multiple invoices.

**Request Body:**

```json
{
  "splits": [
    {
      "document_id": "uuid-1",
      "amount": 300.00
    },
    {
      "document_id": "uuid-2",
      "amount": 200.00
    }
  ]
}
```

#### Batch Reconciliation

```http
POST /api/v1/banking/reconciliation/batch
```

**Rate Limit:** 10/minute

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `bank_account_id` | uuid | Filter by account |
| `limit` | integer | Max transactions to process |

**Response:** `200 OK`

```json
{
  "total_processed": 100,
  "matched_count": 78,
  "partial_count": 5,
  "unmatched_count": 17,
  "match_rate": 78.0
}
```

#### Auto-Reconcile Single

```http
POST /api/v1/banking/reconciliation/auto/{transaction_id}
```

**Rate Limit:** 60/minute

### 5.5 Payments (SEPA)

#### Create Payment Order

```http
POST /api/v1/banking/payments
```

**Rate Limit:** 30/minute

**Request Body:**

```json
{
  "bank_account_id": "uuid",
  "recipient_name": "Lieferant GmbH",
  "recipient_iban": "DE89370400440532013003",
  "recipient_bic": "COBADEFFXXX",
  "amount": 1500.00,
  "currency": "EUR",
  "reference": "RE-L-2026-0015",
  "purpose": "Lieferantenrechnung",
  "execution_date": "2026-01-10",
  "linked_document_id": "uuid"
}
```

**Response:** `201 Created`

```json
{
  "id": "uuid",
  "status": "draft",
  "amount": 1500.00,
  "recipient_name": "Lieferant GmbH",
  "created_at": "2026-01-08T12:00:00Z"
}
```

**Payment Status Workflow:**

```
draft → approved → submitted → pending_tan → executed
                 ↘ cancelled
```

#### List Payments

```http
GET /api/v1/banking/payments
```

#### Get Pending Payments

```http
GET /api/v1/banking/payments/pending
```

#### Get Skonto Opportunities

```http
GET /api/v1/banking/payments/skonto-opportunities
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `days_ahead` | integer | Days to look ahead (default: 14) |

**Response:** `200 OK`

```json
[
  {
    "document_id": "uuid",
    "invoice_number": "RE-L-2026-0015",
    "gross_amount": 1500.00,
    "skonto_date": "2026-01-15",
    "skonto_percent": 2.0,
    "skonto_amount": 30.00,
    "net_amount_with_skonto": 1470.00,
    "days_remaining": 7
  }
]
```

#### Approve Payment

```http
POST /api/v1/banking/payments/{payment_id}/approve
```

**Rate Limit:** 30/minute

#### Submit Payment (Initiate TAN)

```http
POST /api/v1/banking/payments/{payment_id}/submit
```

**Rate Limit:** 10/minute

**Response:** `200 OK`

```json
{
  "payment_id": "uuid",
  "tan_method": "pushTAN",
  "tan_challenge": "Überweisen Sie 1.500,00 EUR an Lieferant GmbH?",
  "expires_at": "2026-01-08T12:05:00Z"
}
```

#### Confirm Payment with TAN

```http
POST /api/v1/banking/payments/{payment_id}/confirm-tan
```

**Rate Limit:** 5/minute (Brute-force protection)

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `tan` | string | 6-digit TAN |

#### Cancel Payment

```http
POST /api/v1/banking/payments/{payment_id}/cancel
```

**Rate Limit:** 30/minute

### 5.6 Cash Flow

#### Cash Flow Forecast

```http
GET /api/v1/banking/cashflow/forecast
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `days_ahead` | integer | Forecast period (7-365 days) |
| `scenario` | string | `optimistic`, `realistic`, `pessimistic` |
| `bank_account_id` | uuid | Filter by account |

**Response:** `200 OK`

```json
{
  "period": {
    "start": "2026-01-08",
    "end": "2026-04-08",
    "scenario": "realistic"
  },
  "totals": {
    "inflow": 125000.00,
    "outflow": 95000.00,
    "net": 30000.00
  },
  "risk": {
    "min_balance": 5000.00,
    "min_balance_date": "2026-02-15",
    "days_negative": 0
  },
  "entries_count": 156
}
```

#### Cash Flow Summary

```http
GET /api/v1/banking/cashflow/summary
```

#### Daily Forecast

```http
GET /api/v1/banking/cashflow/daily
```

#### Scenario Comparison

```http
GET /api/v1/banking/cashflow/scenarios
```

### 5.7 Dunning (Mahnwesen)

#### Get Overdue Invoices

```http
GET /api/v1/banking/dunning/overdue
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `min_days` | integer | Minimum days overdue |
| `max_days` | integer | Maximum days overdue |

**Response:** `200 OK`

```json
[
  {
    "document_id": "uuid",
    "invoice_number": "RE-2026-0015",
    "creditor_name": "Kunde Meier",
    "amount": 1500.00,
    "due_date": "2025-12-15",
    "days_overdue": 24,
    "current_level": "first_reminder",
    "recommended_action": "second_reminder",
    "accumulated_fees": 5.00,
    "late_interest": 12.50,
    "total_due": 1517.50
  }
]
```

#### Create Dunning Record

```http
POST /api/v1/banking/dunning
```

**Rate Limit:** 30/minute

**Request Body:**

```json
{
  "document_id": "uuid",
  "level": "first_reminder",
  "notes": "Erste Zahlungserinnerung"
}
```

**Dunning Levels:**

| Level | Days | Action |
|-------|------|--------|
| `first_reminder` | 7+ | Freundliche Erinnerung |
| `second_reminder` | 21+ | Mahngebühr + Zinsen |
| `third_reminder` | 35+ | Letzte Mahnung |
| `collection` | 49+ | Inkasso-Androhung |
| `legal` | 63+ | Rechtliche Schritte |

#### List Dunning Records

```http
GET /api/v1/banking/dunning
```

#### Dunning Statistics

```http
GET /api/v1/banking/dunning/stats
```

#### Escalate Dunning

```http
POST /api/v1/banking/dunning/{dunning_id}/escalate
```

**Rate Limit:** 30/minute

#### Close Dunning

```http
POST /api/v1/banking/dunning/{dunning_id}/close
```

**Rate Limit:** 30/minute

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | `paid`, `cancelled`, `written_off` |
| `notes` | string | Closing notes |

#### Set Mahnstopp

```http
POST /api/v1/banking/dunning/{dunning_id}/mahnstopp
```

**Rate Limit:** 30/minute

**Request Body:**

```json
{
  "reason": "Reklamation in Bearbeitung",
  "until_date": "2026-02-01"
}
```

#### Lift Mahnstopp

```http
DELETE /api/v1/banking/dunning/{dunning_id}/mahnstopp
```

#### Calculate Verzugszinsen

```http
GET /api/v1/banking/dunning/{dunning_id}/verzugszinsen
```

**Response:** `200 OK`

```json
{
  "principal": 1500.00,
  "due_date": "2025-12-15",
  "as_of_date": "2026-01-08",
  "is_b2b": true,
  "interest_rate": 11.27,
  "days_overdue": 24,
  "interest_amount": 11.15,
  "total_with_interest": 1511.15
}
```

**Interest Rates (BGB §288):**

| Type | Rate |
|------|------|
| B2B | 11.27% (Basiszins + 9%) |
| B2C | 7.27% (Basiszins + 5%) |

#### Claim B2B Pauschale

```http
POST /api/v1/banking/dunning/{dunning_id}/b2b-pauschale
```

**Rate Limit:** 30/minute

Claims the EUR 40 flat rate according to §288 Abs. 5 BGB.

#### Automatic Dunning Process

```http
POST /api/v1/banking/dunning/process-automatic
```

**Rate Limit:** 10/minute

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `dry_run` | boolean | Simulate only (default: true) |

#### Bulk Escalate

```http
POST /api/v1/banking/dunning/bulk-escalate
```

**Rate Limit:** 10/minute

### 5.8 Mahn-Tasks

#### List Mahn Tasks

```http
GET /api/v1/banking/mahn-tasks
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `task_type` | string | `reminder`, `call`, `letter`, `email` |
| `status` | string | `pending`, `completed`, `cancelled` |
| `assigned_user_id` | uuid | Filter by assignee |
| `due_date_from` | date | Due from |
| `due_date_to` | date | Due until |
| `priority` | integer | 1-5 |
| `include_snoozed` | boolean | Include snoozed tasks |

#### Task Summary

```http
GET /api/v1/banking/mahn-tasks/summary
```

#### Create Mahn Task

```http
POST /api/v1/banking/mahn-tasks
```

**Rate Limit:** 60/minute

#### Assign Task

```http
POST /api/v1/banking/mahn-tasks/{task_id}/assign
```

**Rate Limit:** 60/minute

#### Snooze Task

```http
POST /api/v1/banking/mahn-tasks/{task_id}/snooze
```

**Rate Limit:** 60/minute

**Request Body:**

```json
{
  "snooze_until": "2026-01-15",
  "reason": "Warte auf Rückruf des Kunden"
}
```

Note: Maximum 3 snoozes per task.

#### Complete Task

```http
POST /api/v1/banking/mahn-tasks/{task_id}/complete
```

**Rate Limit:** 60/minute

#### Bulk Complete

```http
POST /api/v1/banking/mahn-tasks/bulk-complete
```

**Rate Limit:** 10/minute

### 5.9 Aging Reports

#### Receivables Aging (Forderungen)

```http
GET /api/v1/banking/aging/receivables
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `as_of_date` | date | Report date |
| `counterparty` | string | Filter by debtor |

**Response:** `200 OK`

```json
{
  "report_type": "receivables",
  "as_of_date": "2026-01-08",
  "generated_at": "2026-01-08T12:00:00Z",
  "summary": {
    "total_count": 45,
    "total_amount": 125000.00,
    "total_overdue": 35000.00,
    "average_days_overdue": 18
  },
  "buckets": [
    {"bucket": "current", "count": 20, "amount": 90000.00, "percentage": 72.0},
    {"bucket": "1_30", "count": 10, "amount": 20000.00, "percentage": 16.0},
    {"bucket": "31_60", "count": 8, "amount": 10000.00, "percentage": 8.0},
    {"bucket": "61_90", "count": 5, "amount": 4000.00, "percentage": 3.2},
    {"bucket": "over_90", "count": 2, "amount": 1000.00, "percentage": 0.8}
  ],
  "line_items": [...]
}
```

#### Payables Aging (Verbindlichkeiten)

```http
GET /api/v1/banking/aging/payables
```

#### Aging Summary

```http
GET /api/v1/banking/aging/summary
```

#### Top Debtors

```http
GET /api/v1/banking/aging/top-debtors
```

#### Top Creditors

```http
GET /api/v1/banking/aging/top-creditors
```

#### Days Sales Outstanding (DSO)

```http
GET /api/v1/banking/aging/dso
```

**Response:** `200 OK`

```json
{
  "dso": 32,
  "period_days": 90,
  "total_receivables": 125000.00,
  "total_revenue": 350000.00,
  "benchmark": {
    "industry_average": 45,
    "performance": "excellent"
  }
}
```

### 5.10 Dunning Settings (Admin)

#### Get Dunning Stages

```http
GET /api/v1/banking/settings/dunning-stages
```

**Response:** `200 OK`

```json
{
  "stages": [
    {
      "id": "uuid",
      "stage_number": 1,
      "stage_name": "Zahlungserinnerung",
      "trigger_days_after_due": 7,
      "action_type": "email",
      "template_id": "uuid",
      "fee_amount": 0.00,
      "is_active": true
    }
  ],
  "interest_rate_b2b": 11.27,
  "interest_rate_b2c": 7.27,
  "b2b_pauschale": 40.00
}
```

#### Create Dunning Stage

```http
POST /api/v1/banking/settings/dunning-stages
```

#### Update Dunning Stage

```http
PUT /api/v1/banking/settings/dunning-stages/{stage_id}
```

#### Reorder Dunning Stages

```http
PUT /api/v1/banking/settings/dunning-stages/reorder
```

### 5.11 Customer Dunning Overrides

#### Get Customer Settings

```http
GET /api/v1/banking/customers/{business_entity_id}/dunning-settings
```

#### Set Customer Settings

```http
PUT /api/v1/banking/customers/{business_entity_id}/dunning-settings
```

**Request Body:**

```json
{
  "custom_payment_terms_days": 45,
  "max_mahn_stufe": 2,
  "preferred_contact_method": "email",
  "exclude_from_auto_dunning": false,
  "exclusion_reason": null,
  "notes": "Großkunde mit Sonderkonditionen"
}
```

---

## 6. Expenses API

> Expense report management with approval workflows

**Base Path:** `/api/v1/expenses`

### 6.1 Expense Reports

#### List Reports

```http
GET /api/v1/expenses/reports
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | `draft`, `submitted`, `approved`, `rejected`, `paid` |
| `date_from` | date | From date |
| `date_to` | date | To date |
| `employee_id` | uuid | Filter by employee |
| `offset` | integer | Pagination offset |
| `limit` | integer | Max results |

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "report_number": "ER-2026-0015",
      "title": "Dienstreise München",
      "employee_id": "uuid",
      "employee_name": "Max Mustermann",
      "status": "submitted",
      "total_amount": 456.78,
      "item_count": 5,
      "trip_date_from": "2026-01-05",
      "trip_date_to": "2026-01-07",
      "submitted_at": "2026-01-08T10:00:00Z",
      "created_at": "2026-01-08T09:00:00Z"
    }
  ],
  "total": 25
}
```

#### Create Report

```http
POST /api/v1/expenses/reports
```

**Rate Limit:** 10/minute

**Request Body:**

```json
{
  "title": "Dienstreise München",
  "trip_date_from": "2026-01-05",
  "trip_date_to": "2026-01-07",
  "purpose": "Kundenmeeting",
  "project_id": "uuid"
}
```

#### Get Report Details

```http
GET /api/v1/expenses/reports/{report_id}
```

#### Update Report

```http
PUT /api/v1/expenses/reports/{report_id}
```

Only allowed when status is `draft`.

#### Delete Report

```http
DELETE /api/v1/expenses/reports/{report_id}
```

Only allowed when status is `draft`.

### 6.2 Expense Items

#### List Items

```http
GET /api/v1/expenses/reports/{report_id}/items
```

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "expense_date": "2026-01-05",
      "category": "travel",
      "description": "ICE München-Frankfurt",
      "amount": 125.50,
      "currency": "EUR",
      "has_receipt": true,
      "receipt_document_id": "uuid",
      "tax_rate": 7.0,
      "net_amount": 117.29,
      "tax_amount": 8.21
    }
  ],
  "total_amount": 456.78
}
```

#### Add Item

```http
POST /api/v1/expenses/reports/{report_id}/items
```

**Request Body:**

```json
{
  "expense_date": "2026-01-05",
  "category": "travel",
  "description": "ICE München-Frankfurt",
  "amount": 125.50,
  "currency": "EUR",
  "tax_rate": 7.0,
  "receipt_document_id": "uuid"
}
```

**Expense Categories:**

| Category | Description |
|----------|-------------|
| `travel` | Transportation (train, plane, car) |
| `accommodation` | Hotels, lodging |
| `meals` | Food and beverages |
| `per_diem` | Verpflegungspauschale |
| `mileage` | Kilometergeld |
| `communication` | Phone, internet |
| `office` | Office supplies |
| `other` | Other expenses |

#### Update Item

```http
PUT /api/v1/expenses/reports/{report_id}/items/{item_id}
```

#### Delete Item

```http
DELETE /api/v1/expenses/reports/{report_id}/items/{item_id}
```

### 6.3 Workflow

#### Submit Report

```http
POST /api/v1/expenses/reports/{report_id}/submit
```

**Rate Limit:** 10/minute

Changes status from `draft` to `submitted`.

#### Approve Report

```http
POST /api/v1/expenses/reports/{report_id}/approve
```

**Rate Limit:** 10/minute

**Permission Required:** `expense_approve`

**Request Body:**

```json
{
  "notes": "Genehmigt"
}
```

#### Reject Report

```http
POST /api/v1/expenses/reports/{report_id}/reject
```

**Rate Limit:** 10/minute

**Permission Required:** `expense_approve`

**Request Body:**

```json
{
  "reason": "Fehlende Belege für Position 3"
}
```

#### Mark as Paid

```http
POST /api/v1/expenses/reports/{report_id}/pay
```

**Rate Limit:** 5/minute

**Request Body:**

```json
{
  "payment_date": "2026-01-15",
  "payment_reference": "GEHALT-2026-01"
}
```

#### Recall Report

```http
POST /api/v1/expenses/reports/{report_id}/recall
```

Allows employee to recall a submitted report back to draft.

### 6.4 Calculators

#### Per-Diem Calculator (Verpflegungspauschale)

```http
POST /api/v1/expenses/calculators/per-diem
```

**Request Body:**

```json
{
  "departure_date": "2026-01-05",
  "departure_time": "08:00",
  "return_date": "2026-01-07",
  "return_time": "18:00",
  "destination_country": "DE",
  "meals_provided": {
    "2026-01-05": {"breakfast": false, "lunch": false, "dinner": true},
    "2026-01-06": {"breakfast": true, "lunch": false, "dinner": false},
    "2026-01-07": {"breakfast": true, "lunch": false, "dinner": false}
  }
}
```

**Response:** `200 OK`

```json
{
  "days": [
    {
      "date": "2026-01-05",
      "type": "travel_day",
      "base_rate": 14.00,
      "deductions": {"dinner": 5.60},
      "net_amount": 8.40
    },
    {
      "date": "2026-01-06",
      "type": "full_day",
      "base_rate": 28.00,
      "deductions": {"breakfast": 5.60},
      "net_amount": 22.40
    },
    {
      "date": "2026-01-07",
      "type": "travel_day",
      "base_rate": 14.00,
      "deductions": {"breakfast": 5.60},
      "net_amount": 8.40
    }
  ],
  "total_per_diem": 39.20
}
```

**German Per-Diem Rates (2026):**

| Duration | Rate |
|----------|------|
| Full day (24h) | EUR 28.00 |
| Travel day (>8h) | EUR 14.00 |
| Breakfast deduction | EUR 5.60 |
| Lunch deduction | EUR 11.20 |
| Dinner deduction | EUR 11.20 |

#### Mileage Calculator (Kilometergeld)

```http
POST /api/v1/expenses/calculators/mileage
```

**Request Body:**

```json
{
  "vehicle_type": "car",
  "distance_km": 250,
  "purpose": "Kundenbesuch München",
  "date": "2026-01-05"
}
```

**Response:** `200 OK`

```json
{
  "vehicle_type": "car",
  "distance_km": 250,
  "rate_per_km": 0.30,
  "total_amount": 75.00,
  "tax_free": true
}
```

**Mileage Rates (2026):**

| Vehicle | Rate |
|---------|------|
| Car | EUR 0.30/km |
| Motorcycle | EUR 0.20/km |
| Bicycle | EUR 0.05/km |

### 6.5 Statistics

#### Expense Statistics

```http
GET /api/v1/expenses/stats
```

**Response:** `200 OK`

```json
{
  "total_reports": 125,
  "pending_approval": 8,
  "total_amount_ytd": 45678.90,
  "by_category": {
    "travel": 15000.00,
    "accommodation": 12000.00,
    "meals": 8000.00,
    "per_diem": 6000.00,
    "other": 4678.90
  },
  "average_processing_days": 3.5
}
```

---

## 7. Finance API

> Year-based finance document management

**Base Path:** `/api/v1/finance`

### 7.1 Document Categories

| Package | Categories |
|---------|------------|
| **Steuern** | Einkommensteuererklärung, Umsatzsteuervoranmeldung, Gewerbesteuererklärung, Körperschaftssteuererklärung |
| **Personal** | Lohnsteuerbescheinigung, Sozialversicherungsmeldung, Arbeitsverträge, Lohnabrechnungen |
| **Versicherung** | Haftpflichtversicherung, Krankenversicherung, Rentenversicherung, Berufsunfähigkeit |
| **Bank** | Kontoauszüge, Kreditverträge, Bürgschaften, Anlagebestätigungen |

### 7.2 Document Management

#### List Documents

```http
GET /api/v1/finance/documents
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `year` | integer | Filter by year |
| `category` | string | Filter by category |
| `package` | string | Filter by package |
| `status` | string | `pending`, `complete`, `overdue` |
| `search` | string | Full-text search |
| `offset` | integer | Pagination offset |
| `limit` | integer | Max results |

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "year": 2026,
      "category": "einkommensteuererklarung",
      "package": "steuern",
      "title": "Einkommensteuererklärung 2025",
      "status": "pending",
      "deadline": "2026-07-31",
      "days_until_deadline": 204,
      "document_ids": ["uuid"],
      "notes": "Steuerberater kontaktieren",
      "created_at": "2026-01-08T10:00:00Z",
      "updated_at": "2026-01-08T10:00:00Z"
    }
  ],
  "total": 45
}
```

#### Create Document

```http
POST /api/v1/finance/documents
```

**Request Body:**

```json
{
  "year": 2026,
  "category": "umsatzsteuervoranmeldung",
  "title": "USt-VA Januar 2026",
  "deadline": "2026-02-10",
  "document_ids": ["uuid"],
  "notes": "Monatliche Meldung"
}
```

#### Get Document

```http
GET /api/v1/finance/documents/{document_id}
```

#### Update Document

```http
PUT /api/v1/finance/documents/{document_id}
```

#### Delete Document

```http
DELETE /api/v1/finance/documents/{document_id}
```

**Permission Required:** `finance_delete`

### 7.3 Bulk Operations

#### Bulk Create

```http
POST /api/v1/finance/documents/bulk
```

**Request Body:**

```json
{
  "documents": [
    {
      "year": 2026,
      "category": "umsatzsteuervoranmeldung",
      "title": "USt-VA Februar 2026",
      "deadline": "2026-03-10"
    },
    {
      "year": 2026,
      "category": "umsatzsteuervoranmeldung",
      "title": "USt-VA März 2026",
      "deadline": "2026-04-10"
    }
  ]
}
```

#### Bulk Update Status

```http
PATCH /api/v1/finance/documents/bulk/status
```

**Request Body:**

```json
{
  "document_ids": ["uuid-1", "uuid-2"],
  "status": "complete"
}
```

#### Bulk Delete

```http
DELETE /api/v1/finance/documents/bulk
```

**Request Body:**

```json
{
  "document_ids": ["uuid-1", "uuid-2"]
}
```

### 7.4 Deadlines

#### Get Upcoming Deadlines

```http
GET /api/v1/finance/deadlines
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `days_ahead` | integer | Days to look ahead (default: 30) |
| `status` | string | Filter by status |

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "title": "USt-VA Januar 2026",
      "deadline": "2026-02-10",
      "days_remaining": 33,
      "status": "pending",
      "priority": "high"
    }
  ],
  "overdue_count": 0,
  "due_this_week": 2,
  "due_this_month": 5
}
```

#### Get Deadline Calendar

```http
GET /api/v1/finance/deadlines/calendar
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `year` | integer | Calendar year |
| `month` | integer | Month (optional) |

### 7.5 Year Overview

#### Get Year Summary

```http
GET /api/v1/finance/years/{year}/summary
```

**Response:** `200 OK`

```json
{
  "year": 2026,
  "total_documents": 48,
  "by_status": {
    "pending": 35,
    "complete": 10,
    "overdue": 3
  },
  "by_package": {
    "steuern": 12,
    "personal": 15,
    "versicherung": 10,
    "bank": 11
  },
  "completion_rate": 20.8
}
```

#### Compare Years

```http
GET /api/v1/finance/years/compare
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `years` | string | Comma-separated years (e.g., "2024,2025,2026") |

### 7.6 History & Audit

#### Get Document History

```http
GET /api/v1/finance/documents/{document_id}/history
```

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "action": "status_change",
      "old_value": "pending",
      "new_value": "complete",
      "changed_by": "uuid",
      "changed_by_name": "Max Mustermann",
      "changed_at": "2026-01-08T15:00:00Z"
    }
  ]
}
```

---

## 8. DATEV API

> Tax advisor export integration for German accounting

**Base Path:** `/api/v1/datev`

### 8.1 Overview

The DATEV API enables export of accounting data in DATEV Buchungsstapel format for seamless integration with tax advisors.

**Export Format Specifications:**

| Property | Value |
|----------|-------|
| Format | CSV (semicolon-separated) |
| Encoding | Windows-1252 (CP1252) |
| Version | DATEV Format Version 700 |
| Line Ending | CRLF |

### 8.2 Configuration

#### Get Configuration

```http
GET /api/v1/datev/config
```

**Response:** `200 OK`

```json
{
  "id": "uuid",
  "consultant_number": 12345,
  "client_number": 67890,
  "fiscal_year_start": "2026-01-01",
  "kontenrahmen": "SKR03",
  "account_length": 4,
  "default_tax_key": 0,
  "default_cost_center": null,
  "export_settings": {
    "include_documents": true,
    "include_receipts": true,
    "auto_generate_account_mapping": true
  },
  "updated_at": "2026-01-08T10:00:00Z"
}
```

#### Update Configuration

```http
PUT /api/v1/datev/config
```

**Request Body:**

```json
{
  "consultant_number": 12345,
  "client_number": 67890,
  "kontenrahmen": "SKR03",
  "account_length": 4
}
```

**Kontenrahmen Options:**

| Code | Description |
|------|-------------|
| `SKR03` | Standardkontenrahmen für Gewerbebetriebe |
| `SKR04` | Standardkontenrahmen für Kapitalgesellschaften |

### 8.3 Vendor Mappings

#### List Vendor Mappings

```http
GET /api/v1/datev/vendor-mappings
```

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "vendor_name": "Lieferant GmbH",
      "vendor_id": "uuid",
      "datev_account": "70001",
      "cost_center": "1000",
      "tax_key": 9,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total": 25
}
```

#### Create Vendor Mapping

```http
POST /api/v1/datev/vendor-mappings
```

**Request Body:**

```json
{
  "vendor_id": "uuid",
  "datev_account": "70002",
  "cost_center": "1000",
  "tax_key": 9
}
```

#### Update Vendor Mapping

```http
PUT /api/v1/datev/vendor-mappings/{mapping_id}
```

#### Delete Vendor Mapping

```http
DELETE /api/v1/datev/vendor-mappings/{mapping_id}
```

### 8.4 Account Mappings

#### List Account Mappings

```http
GET /api/v1/datev/account-mappings
```

#### Create Account Mapping

```http
POST /api/v1/datev/account-mappings
```

**Request Body:**

```json
{
  "internal_category": "office_supplies",
  "datev_account": "4930",
  "description": "Bürobedarf",
  "tax_key": 9
}
```

### 8.5 Export

#### Export Preview

```http
POST /api/v1/datev/export/preview
```

**Request Body:**

```json
{
  "date_from": "2026-01-01",
  "date_to": "2026-01-31",
  "include_cash": true,
  "include_bank": true,
  "include_invoices": true
}
```

**Response:** `200 OK`

```json
{
  "period": {
    "from": "2026-01-01",
    "to": "2026-01-31"
  },
  "record_count": 156,
  "total_debit": 125000.00,
  "total_credit": 125000.00,
  "by_type": {
    "cash": 45,
    "bank": 89,
    "invoices": 22
  },
  "warnings": [
    {
      "type": "missing_mapping",
      "message": "3 Buchungen ohne Kontenzuordnung",
      "affected_ids": ["uuid-1", "uuid-2", "uuid-3"]
    }
  ],
  "sample_records": [
    {
      "booking_date": "2026-01-05",
      "amount": 500.00,
      "debit_account": "1200",
      "credit_account": "8400",
      "description": "Umsatzerlöse"
    }
  ]
}
```

#### Export Buchungsstapel

```http
POST /api/v1/datev/export
```

**Request Body:**

```json
{
  "date_from": "2026-01-01",
  "date_to": "2026-01-31",
  "include_cash": true,
  "include_bank": true,
  "include_invoices": true,
  "filename": "buchungen_2026_01"
}
```

**Response:** `200 OK` - Returns ZIP file containing:

- `EXTF_Buchungsstapel.csv` - Main booking file
- `EXTF_Stammdaten.csv` - Master data (optional)
- `documents/` - Linked document files (optional)

### 8.6 VIES Validation

#### Validate VAT ID

```http
POST /api/v1/datev/vies/validate
```

**Request Body:**

```json
{
  "vat_id": "DE123456789"
}
```

**Response:** `200 OK`

```json
{
  "vat_id": "DE123456789",
  "valid": true,
  "company_name": "Beispiel GmbH",
  "company_address": "Musterstraße 1, 12345 Musterstadt",
  "validated_at": "2026-01-08T12:00:00Z",
  "request_id": "uuid"
}
```

#### Batch Validate

```http
POST /api/v1/datev/vies/validate/batch
```

**Request Body:**

```json
{
  "vat_ids": ["DE123456789", "AT987654321", "FR12345678901"]
}
```

### 8.7 Tax Keys (Steuerschlüssel)

#### List Tax Keys

```http
GET /api/v1/datev/tax-keys
```

**Response:** `200 OK`

```json
{
  "items": [
    {"key": 0, "description": "Ohne Steuer", "rate": 0.0},
    {"key": 1, "description": "USt frei mit Vorsteuerabzug", "rate": 0.0},
    {"key": 2, "description": "USt 7%", "rate": 7.0},
    {"key": 3, "description": "USt 19%", "rate": 19.0},
    {"key": 8, "description": "VSt 7%", "rate": 7.0},
    {"key": 9, "description": "VSt 19%", "rate": 19.0}
  ]
}
```

---

## Appendix A: Common Schemas

### Pagination Response

```json
{
  "items": [...],
  "total": 100,
  "offset": 0,
  "limit": 50
}
```

### Error Response

```json
{
  "detail": "Fehlermeldung auf Deutsch",
  "error_code": "ERROR_CODE",
  "timestamp": "2026-01-08T12:00:00Z"
}
```

### UUID Format

All IDs use UUID v4 format: `xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`

### Date Formats

| Type | Format | Example |
|------|--------|---------|
| Date | ISO 8601 | `2026-01-08` |
| DateTime | ISO 8601 | `2026-01-08T12:00:00Z` |
| Time | ISO 8601 | `12:00:00` |

### Currency

All monetary amounts are in EUR unless otherwise specified. Amounts are represented as decimal numbers with 2 decimal places.

---

## Appendix B: Rate Limit Reference

| Endpoint Category | Limit | Notes |
|-------------------|-------|-------|
| List/Read | 100/min | Standard reads |
| Create | 30/min | New records |
| Update | 60/min | Modifications |
| Delete | 30/min | Deletions |
| Cash Entry Create | 10/min | GoBD compliance |
| Cash Count | 5/min | Critical operation |
| Bank Import | 20/min | Resource intensive |
| Import Preview | 30/min | Analysis only |
| Payment Create | 30/min | Financial transaction |
| Payment Submit | 10/min | Bank communication |
| TAN Confirm | 5/min | Brute-force protection |
| Reconciliation Batch | 10/min | Bulk processing |
| Dunning Operations | 30/min | Workflow actions |
| Bulk Operations | 10/min | Mass updates |
| DATEV Export | 10/min | Heavy processing |

---

## Appendix C: Webhook Events

Business domain APIs emit the following webhook events:

| Event | Payload |
|-------|---------|
| `cash.entry.created` | Entry details |
| `cash.entry.cancelled` | Entry + storno details |
| `bank.transaction.imported` | Transaction details |
| `bank.transaction.reconciled` | Match details |
| `expense.report.submitted` | Report details |
| `expense.report.approved` | Report + approver |
| `expense.report.rejected` | Report + reason |
| `finance.document.deadline` | Document + days remaining |
| `datev.export.completed` | Export details |
| `dunning.escalated` | Dunning + new level |

---

*Documentation generated: 2026-01-08*
*API Version: 1.0*
*Ablage-System Enterprise Platform*
