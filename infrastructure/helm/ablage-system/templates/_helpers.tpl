{{/*
=============================================================================
Ablage-System Helm Chart - Template Helpers
=============================================================================
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "ablage-system.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "ablage-system.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "ablage-system.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "ablage-system.labels" -}}
helm.sh/chart: {{ include "ablage-system.chart" . }}
{{ include "ablage-system.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: ablage-system
{{- end }}

{{/*
Selector labels
*/}}
{{- define "ablage-system.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ablage-system.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend labels
*/}}
{{- define "ablage-system.backend.labels" -}}
{{ include "ablage-system.labels" . }}
app.kubernetes.io/component: api
{{- end }}

{{- define "ablage-system.backend.selectorLabels" -}}
{{ include "ablage-system.selectorLabels" . }}
app.kubernetes.io/component: api
{{- end }}

{{/*
Worker labels
*/}}
{{- define "ablage-system.worker.labels" -}}
{{ include "ablage-system.labels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{- define "ablage-system.worker.selectorLabels" -}}
{{ include "ablage-system.selectorLabels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{/*
Frontend labels
*/}}
{{- define "ablage-system.frontend.labels" -}}
{{ include "ablage-system.labels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{- define "ablage-system.frontend.selectorLabels" -}}
{{ include "ablage-system.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
PostgreSQL labels
*/}}
{{- define "ablage-system.postgresql.labels" -}}
{{ include "ablage-system.labels" . }}
app.kubernetes.io/component: database
{{- end }}

{{/*
Redis labels
*/}}
{{- define "ablage-system.redis.labels" -}}
{{ include "ablage-system.labels" . }}
app.kubernetes.io/component: cache
{{- end }}

{{/*
MinIO labels
*/}}
{{- define "ablage-system.minio.labels" -}}
{{ include "ablage-system.labels" . }}
app.kubernetes.io/component: storage
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "ablage-system.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "ablage-system.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Return the proper image name
*/}}
{{- define "ablage-system.image" -}}
{{- $registryName := .imageRoot.registry -}}
{{- $repositoryName := .imageRoot.repository -}}
{{- $tag := .imageRoot.tag | toString -}}
{{- if .global.imageRegistry }}
    {{- $registryName = .global.imageRegistry -}}
{{- end -}}
{{- if $registryName }}
{{- printf "%s/%s:%s" $registryName $repositoryName $tag -}}
{{- else -}}
{{- printf "%s:%s" $repositoryName $tag -}}
{{- end -}}
{{- end -}}

{{/*
Return secret name
*/}}
{{- define "ablage-system.secretName" -}}
{{- if .Values.secrets.existingSecret }}
{{- .Values.secrets.existingSecret }}
{{- else }}
{{- include "ablage-system.fullname" . }}-secrets
{{- end }}
{{- end }}

{{/*
Database URL
*/}}
{{- define "ablage-system.databaseUrl" -}}
postgresql://{{ .Values.postgresql.auth.username }}:$(POSTGRES_PASSWORD)@{{ include "ablage-system.fullname" . }}-postgresql:5432/{{ .Values.postgresql.auth.database }}
{{- end }}

{{/*
Redis URL
*/}}
{{- define "ablage-system.redisUrl" -}}
redis://{{ include "ablage-system.fullname" . }}-redis:6379/0
{{- end }}

{{/*
MinIO endpoint
*/}}
{{- define "ablage-system.minioEndpoint" -}}
{{ include "ablage-system.fullname" . }}-minio:9000
{{- end }}
