<script setup lang="ts">
import type { UserRead } from '../types/users'
import { usersStatus } from '../utils/userDisplay'

/** Estado legible del usuario: Activo / Inactivo / Bloqueado hasta HH:MM. */
const props = defineProps<{ user: Pick<UserRead, 'is_active' | 'locked_until'> }>()

const status = computed(() => usersStatus(props.user))
const variant = computed(() => ({ active: 'success', inactive: 'danger', locked: 'warning' } as const)[status.value.kind])
</script>

<template>
  <UiStatusBadge :variant="variant" :label="status.label" dot :data-status="status.kind" data-testid="user-status" />
</template>
