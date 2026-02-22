/**
 * WebhooksPage
 *
 * Admin-Seite fuer Outbound-Webhook-Management mit 3 Tabs:
 * - Endpoints: CRUD, Test, Zustellungshistorie
 * - Dead Letter Queue: Fehlgeschlagene Zustellungen + Retry
 * - Event-Protokoll: Event-Log mit Filter + Replay
 */

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  Webhook,
  Plus,
  AlertTriangle,
  ScrollText,
  CheckCircle,
  XCircle,
  Hash,
} from 'lucide-react'
import {
  EndpointTable,
  EndpointDialog,
  SecretRevealDialog,
  TestWebhookDialog,
  DeliveryTable,
  EventLogTable,
  BulkReplayDialog,
} from './components'
import { useWebhookEndpoints, useDLQ, useEndpointDeliveries } from './api'
import type { WebhookEndpointResponse, WebhookEndpointWithSecret } from './types'

export function WebhooksPage() {
  // Endpoint-Dialog State
  const [endpointDialogOpen, setEndpointDialogOpen] = useState(false)
  const [editingEndpoint, setEditingEndpoint] = useState<WebhookEndpointResponse | null>(null)

  // Secret-Dialog State
  const [secretDialogOpen, setSecretDialogOpen] = useState(false)
  const [createdEndpoint, setCreatedEndpoint] = useState<WebhookEndpointWithSecret | null>(null)

  // Test-Dialog State
  const [testDialogOpen, setTestDialogOpen] = useState(false)
  const [testingEndpoint, setTestingEndpoint] = useState<WebhookEndpointResponse | null>(null)

  // Delivery-History State
  const [deliveryEndpoint, setDeliveryEndpoint] = useState<WebhookEndpointResponse | null>(null)
  const [deliveryPage, setDeliveryPage] = useState(1)

  // DLQ State
  const [dlqPage, setDlqPage] = useState(1)

  // Bulk Replay State
  const [bulkReplayOpen, setBulkReplayOpen] = useState(false)

  // Filter
  const [showInactive, setShowInactive] = useState(false)

  // Queries
  const { data: endpointData, isLoading: endpointsLoading } = useWebhookEndpoints({
    include_inactive: showInactive,
  })
  const { data: dlqData, isLoading: dlqLoading } = useDLQ({ page: dlqPage, per_page: 20 })
  const { data: deliveryData, isLoading: deliveryLoading } = useEndpointDeliveries(
    deliveryEndpoint?.id ?? '',
    { page: deliveryPage, per_page: 20 }
  )

  const endpoints = endpointData?.items ?? []
  const dlqItems = dlqData?.items ?? []

  // Stats
  const totalEndpoints = endpoints.length
  const activeEndpoints = endpoints.filter((e) => e.is_active).length
  const dlqCount = dlqItems.length

  // Handlers
  const handleCreate = () => {
    setEditingEndpoint(null)
    setEndpointDialogOpen(true)
  }

  const handleEdit = (endpoint: WebhookEndpointResponse) => {
    setEditingEndpoint(endpoint)
    setEndpointDialogOpen(true)
  }

  const handleEndpointDialogClose = (open: boolean) => {
    setEndpointDialogOpen(open)
    if (!open) setEditingEndpoint(null)
  }

  const handleCreated = (endpoint: WebhookEndpointWithSecret) => {
    setCreatedEndpoint(endpoint)
    setSecretDialogOpen(true)
  }

  const handleTest = (endpoint: WebhookEndpointResponse) => {
    setTestingEndpoint(endpoint)
    setTestDialogOpen(true)
  }

  const handleViewDeliveries = (endpoint: WebhookEndpointResponse) => {
    setDeliveryEndpoint(endpoint)
    setDeliveryPage(1)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Webhook className="h-6 w-6" />
            Outbound-Webhooks
          </h1>
          <p className="text-muted-foreground">
            Verwalten Sie Ihre Webhook-Endpoints, Zustellungen und Event-Replays.
          </p>
        </div>

        <Button onClick={handleCreate}>
          <Plus className="h-4 w-4 mr-2" />
          Neuer Endpoint
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Endpoints gesamt
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Hash className="h-4 w-4 text-muted-foreground" />
              <span className="text-2xl font-bold">{totalEndpoints}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Aktive Endpoints
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-green-500" />
              <span className="text-2xl font-bold">{activeEndpoints}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Dead Letter Queue
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <XCircle className="h-4 w-4 text-red-500" />
              <span className="text-2xl font-bold">{dlqCount}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="endpoints">
        <TabsList>
          <TabsTrigger value="endpoints">Endpoints</TabsTrigger>
          <TabsTrigger value="dlq" className="gap-1">
            <AlertTriangle className="h-3.5 w-3.5" />
            Dead Letter Queue
            {dlqCount > 0 && (
              <span className="ml-1 bg-destructive text-destructive-foreground rounded-full text-xs px-1.5">
                {dlqCount}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="events" className="gap-1">
            <ScrollText className="h-3.5 w-3.5" />
            Event-Protokoll
          </TabsTrigger>
        </TabsList>

        {/* Tab: Endpoints */}
        <TabsContent value="endpoints">
          <Card>
            <CardHeader>
              <div className="flex flex-col md:flex-row md:items-center gap-4">
                <div className="flex-1">
                  <CardTitle>Webhook-Endpoints</CardTitle>
                  <CardDescription>
                    Registrierte Outbound-Webhook-Endpoints Ihres Mandanten.
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Switch
                    checked={showInactive}
                    onCheckedChange={setShowInactive}
                    id="show-inactive-ep"
                  />
                  <Label htmlFor="show-inactive-ep" className="text-sm whitespace-nowrap">
                    Inaktive
                  </Label>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <EndpointTable
                endpoints={endpoints}
                isLoading={endpointsLoading}
                onEdit={handleEdit}
                onTest={handleTest}
                onViewDeliveries={handleViewDeliveries}
              />
            </CardContent>
          </Card>

          {/* Zustellungshistorie fuer ausgewaehlten Endpoint */}
          {deliveryEndpoint && (
            <Card className="mt-4">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base">
                      Zustellungen: {deliveryEndpoint.url}
                    </CardTitle>
                    <CardDescription>
                      Zustellungshistorie des ausgewaehlten Endpoints.
                    </CardDescription>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeliveryEndpoint(null)}
                  >
                    Schliessen
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <DeliveryTable
                  deliveries={deliveryData?.items ?? []}
                  isLoading={deliveryLoading}
                  page={deliveryPage}
                  hasMore={deliveryData?.has_more ?? false}
                  onPageChange={setDeliveryPage}
                />
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Tab: Dead Letter Queue */}
        <TabsContent value="dlq">
          <Card>
            <CardHeader>
              <CardTitle>Dead Letter Queue</CardTitle>
              <CardDescription>
                Fehlgeschlagene Zustellungen, bei denen alle Versuche erschoepft wurden.
                Wiederholen Sie einzelne Eintraege manuell.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <DeliveryTable
                deliveries={dlqItems}
                isLoading={dlqLoading}
                showRetry
                page={dlqPage}
                hasMore={dlqData?.has_more ?? false}
                onPageChange={setDlqPage}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab: Event-Protokoll */}
        <TabsContent value="events">
          <Card>
            <CardHeader>
              <CardTitle>Event-Protokoll</CardTitle>
              <CardDescription>
                Alle publizierten Webhook-Events. Filtern Sie nach Typ und Zeitraum
                oder starten Sie einen Replay.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <EventLogTable onBulkReplay={() => setBulkReplayOpen(true)} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Dialoge */}
      <EndpointDialog
        open={endpointDialogOpen}
        onOpenChange={handleEndpointDialogClose}
        endpoint={editingEndpoint}
        onCreated={handleCreated}
      />

      {createdEndpoint && (
        <SecretRevealDialog
          open={secretDialogOpen}
          onOpenChange={setSecretDialogOpen}
          secret={createdEndpoint.secret}
          endpointUrl={createdEndpoint.url}
        />
      )}

      <TestWebhookDialog
        open={testDialogOpen}
        onOpenChange={setTestDialogOpen}
        endpoint={testingEndpoint}
      />

      <BulkReplayDialog
        open={bulkReplayOpen}
        onOpenChange={setBulkReplayOpen}
      />
    </div>
  )
}
