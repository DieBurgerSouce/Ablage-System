# Risk Scoring UI Feature

Enterprise-level Risk Scoring System frontend für das Ablage-System.

## Status

✅ **Production-Ready** (Stand: Januar 2026)

## Übersicht

Dieses Feature bietet eine vollständige UI für das Risk Scoring System, das Geschäftspartner (Kunden und Lieferanten) nach 5 Risikofaktoren bewertet:

1. **Zahlungsverzögerung** (35% Gewichtung)
2. **Ausfallrate** (25% Gewichtung)
3. **Rechnungsvolumen** (15% Gewichtung)
4. **Dokumenthäufigkeit** (10% Gewichtung)
5. **Beziehungsdauer** (15% Gewichtung)

## Komponenten

### Core Components

#### RiskScoreGauge
Visuelle Darstellung des Risiko-Scores als Halbkreis-Gauge.

```tsx
import { RiskScoreGauge } from '@/features/risk-scoring';

<RiskScoreGauge
  score={75}
  size="lg"
  showLabel={true}
/>
```

**Varianten:**
- `RiskScoreBadge` - Kompaktes Badge mit Score
- `RiskIndicator` - Mini-Indikator (nur Dot + Score)

#### RiskFactorBreakdown
Detaillierte Aufschlüsselung der 5 Risikofaktoren.

```tsx
import { RiskFactorBreakdown } from '@/features/risk-scoring';

<RiskFactorBreakdown
  factors={entityRisk.riskFactors}
  showWeights={true}
/>
```

#### RiskAlertBanner
Warnung-Banner für Hoch-Risiko Entities.

```tsx
import { RiskAlertBanner } from '@/features/risk-scoring';

<RiskAlertBanner
  entityRisk={entityRisk}
  showDismiss={true}
  onDismiss={() => {}}
/>
```

**Varianten:**
- `RiskAlertBadge` - Kompaktes Warn-Badge

### Dashboard Components

#### RiskDashboard
Haupt-Dashboard mit Übersicht, Statistiken und Hoch-Risiko Liste.

```tsx
import { RiskDashboard } from '@/features/risk-scoring';

<RiskDashboard />
```

**Features:**
- Filter nach Entity-Typ (Kunde/Lieferant)
- Filter nach Risikostufe
- Batch-Neuberechnung
- Risiko-Verteilung
- Trend-Chart
- Top Risikofaktoren

#### HighRiskEntitiesTable
Tabelle mit erweiterbaren Zeilen für Hoch-Risiko Entities.

```tsx
import { HighRiskEntitiesTable } from '@/features/risk-scoring';

<HighRiskEntitiesTable
  entities={highRiskEntities}
  onRecalculate={handleRecalculate}
  isRecalculating={entityId}
/>
```

**Varianten:**
- `RiskEntityList` - Einfache Liste für Sidebars

### Charts

#### RiskTrendChart
Area-Chart für Risiko-Verlauf über Zeit.

```tsx
import { RiskTrendChart } from '@/features/risk-scoring';

<RiskTrendChart
  data={statistics.trend}
  showHighRiskCount={true}
/>
```

**Varianten:**
- `RiskDistributionChart` - Verteilung nach Risikostufen
- `EntityRiskMiniChart` - Mini-Chart für Entity-Details

### Pages

#### RiskProfilePage
Vollständige Seite für detaillierte Entity-Risikoanalyse.

```tsx
import { RiskProfilePage } from '@/features/risk-scoring';

<RiskProfilePage
  entityId="entity-uuid"
  showBackButton={true}
  onBack={() => router.back()}
/>
```

## Hooks

### useEntityRisk
Lädt Risiko-Daten für eine Entity.

```tsx
import { useEntityRisk } from '@/features/risk-scoring';

const { data: entityRisk, isLoading } = useEntityRisk(entityId);
```

### useEntityRiskTrend
Lädt Risiko-Verlauf für eine Entity.

```tsx
import { useEntityRiskTrend } from '@/features/risk-scoring';

const { data: trendData } = useEntityRiskTrend(entityId, 30); // 30 Tage
```

### useHighRiskEntities
Lädt Liste der Hoch-Risiko Entities.

```tsx
import { useHighRiskEntities } from '@/features/risk-scoring';

const { data } = useHighRiskEntities({
  entityType: 'customer',
  riskLevel: 'critical',
  minScore: 75,
});
```

### useRiskStatistics
Lädt Risiko-Statistiken.

```tsx
import { useRiskStatistics } from '@/features/risk-scoring';

const { data: statistics } = useRiskStatistics('customer');
```

### useCalculateEntityRisk
Mutation zum Neuberechnen des Risiko-Scores.

```tsx
import { useCalculateEntityRisk } from '@/features/risk-scoring';

const calculateMutation = useCalculateEntityRisk();

await calculateMutation.mutateAsync(entityId);
```

### useRiskDashboard
Kombiniert mehrere Queries für Dashboard.

```tsx
import { useRiskDashboard } from '@/features/risk-scoring';

const {
  statistics,
  highRiskEntities,
  isLoading
} = useRiskDashboard('customer');
```

## Risikostufen

| Stufe | Score-Bereich | Farbe | Beschreibung |
|-------|---------------|-------|--------------|
| **Niedrig** | 0-24 | Grün | Stabiler Geschäftspartner |
| **Mittel** | 25-49 | Gelb | Regelmäßige Überwachung |
| **Hoch** | 50-74 | Orange | Erhöhte Aufmerksamkeit |
| **Kritisch** | 75-100 | Rot | Sofortige Maßnahmen erforderlich |

## Farbschema

Die Komponenten verwenden konsistente Farben für alle Risikostufen:

```typescript
const RISK_LEVEL_COLORS = {
  low: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-700 dark:text-green-400',
    border: 'border-green-500',
  },
  // ... weitere Stufen
};
```

## API Integration

Das Feature nutzt die folgenden Backend-Endpoints:

- `GET /api/v1/entities/{id}/risk` - Entity-Risiko
- `POST /api/v1/entities/{id}/risk/calculate` - Neuberechnung
- `GET /api/v1/entities/risk/high-risk` - Hoch-Risiko Liste
- `GET /api/v1/entities/risk/statistics` - Statistiken
- `GET /api/v1/entities/{id}/risk/trend` - Trend-Daten

## Best Practices

### 1. Performance

```tsx
// ✅ Nutze kombinierte Hooks für Dashboard
const { statistics, highRiskEntities } = useRiskDashboard();

// ❌ Vermeide separate Queries
const stats = useRiskStatistics();
const highRisk = useHighRiskEntities();
```

### 2. Conditional Rendering

```tsx
// ✅ Alert nur bei hohem/kritischem Risiko
{(entityRisk.riskLevel === 'high' || entityRisk.riskLevel === 'critical') && (
  <RiskAlertBanner entityRisk={entityRisk} />
)}
```

### 3. Error Handling

```tsx
const { data, isError, error } = useEntityRisk(entityId);

if (isError) {
  toast.error(error.message || 'Fehler beim Laden');
  return null;
}
```

## Beispiel: Entity Detail Page

```tsx
import { useParams } from '@tanstack/react-router';
import {
  RiskProfilePage,
  RiskAlertBadge,
  useEntityRisk,
} from '@/features/risk-scoring';

export function EntityDetailPage() {
  const { entityId } = useParams();
  const { data: entityRisk } = useEntityRisk(entityId);

  return (
    <div className="space-y-6">
      {/* Header mit Risk Badge */}
      <div className="flex items-center justify-between">
        <h1>Geschäftspartner Details</h1>
        {entityRisk && (
          <RiskAlertBadge
            riskLevel={entityRisk.riskLevel}
            score={entityRisk.riskScore}
          />
        )}
      </div>

      {/* Vollständiges Risiko-Profil */}
      <RiskProfilePage entityId={entityId} />
    </div>
  );
}
```

## Accessibility

Alle Komponenten folgen WCAG 2.1 AA Standards:

- Keyboard-Navigation unterstützt
- ARIA-Labels für Screen Reader
- Ausreichende Farbkontraste
- Focus-Indikatoren sichtbar

## Weitere Ressourcen

- **Backend Service**: `app/services/risk_scoring_service.py`
- **API Docs**: `.claude/Docs/API/` (siehe CLAUDE.md)
- **Migration**: `092_entity_risk_scoring.py`
- **Celery Tasks**: Automatische Berechnung täglich 02:00

## Support

Bei Fragen oder Issues siehe:
- `.claude/memory/KNOWN_ISSUES.md`
- `.claude/Docs/Frontend/Components.md`
