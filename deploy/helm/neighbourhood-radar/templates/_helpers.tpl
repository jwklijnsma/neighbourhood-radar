{{- define "ol.name" -}}{{ .Release.Name | trunc 63 | trimSuffix "-" }}{{- end -}}
{{- define "ol.labels" -}}
app.kubernetes.io/name: neighbourhood-radar
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
{{- define "ol.selector" -}}
app.kubernetes.io/name: neighbourhood-radar
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "ol.secretName" -}}
{{- if .Values.secrets.existingSecret -}}{{ .Values.secrets.existingSecret }}{{- else -}}{{ include "ol.name" . }}{{- end -}}
{{- end -}}
