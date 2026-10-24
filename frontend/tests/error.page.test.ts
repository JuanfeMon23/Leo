import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { createError } from '#imports'
import { afterEach, describe, expect, it } from 'vitest'
// Lo que Nuxt monta como página de error: Leo no define `app/error.vue`, así que
// debe resolverse al de la capa Andromeda (que llega vía ../client).
import ErrorComponent from '#build/error-component.mjs'

enableAutoUnmount(afterEach)

describe('página de error (error.vue de Andromeda)', () => {
  it('404: «No encontramos esta página»', async () => {
    const wrapper = await mountSuspended(ErrorComponent, {
      props: { error: createError({ statusCode: 404, statusMessage: 'Page not found' }) }
    })
    expect(wrapper.text()).toContain('No encontramos esta página')
  })

  it('503: «Servicio no disponible», sin el texto crudo', async () => {
    const wrapper = await mountSuspended(ErrorComponent, {
      props: { error: createError({ statusCode: 503, statusMessage: 'Raw upstream failure' }) }
    })
    expect(wrapper.text()).toContain('Servicio no disponible')
    expect(wrapper.text()).not.toContain('Raw upstream failure')
  })
})
