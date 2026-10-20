<script setup lang="ts">
import type { AuditCatalog, AuditEventRead } from '../types/audit'
import {
  auditActionName, auditActorLabel, auditApplicationName, auditEntityLabel, auditModuleName
} from '../utils/auditLabels'

/**
 * Detalle de un evento: qué acción, sobre qué, quién, cuándo, de qué módulo
 * de qué aplicación, con el resultado, los datos técnicos (IP, navegador,
 * sesión, request_id) y el diff de lo que cambió.
 */
const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ event: AuditEventRead | null, catalog: AuditCatalog }>()

const entity = computed(() => (props.event ? auditEntityLabel(props.event) : null))
const actionName = computed(() => (props.event ? auditActionName(props.catalog, props.event.application_id, props.event.action_tag) : ''))
const description = computed(() => {
  const e = props.event
  if (!e) return undefined
  return `${auditApplicationName(props.catalog, e.application_id)} → ${auditModuleName(props.catalog, e.application_id, e.module)}`
})
</script>

<template>
  <UiModal v-model:open="open" :title="actionName" :description="description" size="xl">
    <div v-if="event" class="space-y-6" data-testid="audit-detail">
      <dl class="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
        <div>
          <dt class="text-xs font-medium text-text-muted">Cuándo</dt>
          <dd data-testid="detail-when">{{ formatLocalDateTime(event.occurred_at, { seconds: true }) }}</dd>
        </div>
        <div>
          <dt class="text-xs font-medium text-text-muted">Resultado</dt>
          <dd><AuditResultBadge :result="event.result" /></dd>
        </div>
        <div>
          <dt class="text-xs font-medium text-text-muted">Quién</dt>
          <dd data-testid="detail-actor">
            {{ auditActorLabel(event) }}
            <span v-if="event.actor_user_id" class="block break-all text-xs text-text-muted"><code>{{ event.actor_user_id }}</code></span>
          </dd>
        </div>
        <div>
          <dt class="text-xs font-medium text-text-muted">Acción</dt>
          <dd>
            {{ actionName }}
            <span class="block text-xs text-text-muted"><code>{{ event.action_tag }}</code></span>
          </dd>
        </div>
        <div>
          <dt class="text-xs font-medium text-text-muted">Aplicación</dt>
          <dd>{{ auditApplicationName(catalog, event.application_id) }}</dd>
        </div>
        <div>
          <dt class="text-xs font-medium text-text-muted">Módulo</dt>
          <dd>{{ auditModuleName(catalog, event.application_id, event.module) }}</dd>
        </div>
        <div>
          <dt class="text-xs font-medium text-text-muted">Sobre qué</dt>
          <dd data-testid="detail-entity">
            <template v-if="entity">
              {{ entity.type }}
              <span v-if="entity.id" class="block break-all text-xs text-text-muted"><code>{{ entity.id }}</code></span>
            </template>
            <template v-else>—</template>
          </dd>
        </div>
        <div>
          <dt class="text-xs font-medium text-text-muted">Motivo</dt>
          <dd>{{ event.reason || '—' }}</dd>
        </div>
        <div>
          <dt class="text-xs font-medium text-text-muted">Dirección IP</dt>
          <dd data-testid="detail-ip">{{ event.ip || '—' }}</dd>
        </div>
        <div>
          <dt class="text-xs font-medium text-text-muted">Navegador</dt>
          <dd data-testid="detail-agent">
            {{ summarizeUserAgent(event.user_agent) }}
            <span v-if="event.user_agent" class="block break-all text-xs text-text-muted">{{ event.user_agent }}</span>
          </dd>
        </div>
        <div>
          <dt class="text-xs font-medium text-text-muted">Sesión</dt>
          <dd class="break-all"><code v-if="event.session_id">{{ event.session_id }}</code><template v-else>—</template></dd>
        </div>
        <div>
          <dt class="text-xs font-medium text-text-muted">Identificador de petición</dt>
          <dd class="break-all" data-testid="detail-request"><code v-if="event.request_id">{{ event.request_id }}</code><template v-else>—</template></dd>
        </div>
        <div class="sm:col-span-2">
          <dt class="text-xs font-medium text-text-muted">Identificador del evento</dt>
          <dd class="break-all"><code>{{ event.id }}</code></dd>
        </div>
      </dl>

      <section aria-labelledby="audit-diff-title" class="space-y-2">
        <h3 id="audit-diff-title" class="text-sm font-semibold text-text">Qué cambió</h3>
        <AuditDiffTable :changes="event.changes" />
      </section>
    </div>

    <template #footer="{ close }">
      <UiButton variant="secondary" @click="close()">Cerrar</UiButton>
    </template>
  </UiModal>
</template>
