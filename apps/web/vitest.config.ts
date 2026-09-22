import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

// Unit tests run without Nuxt, so mirror the `#shared` alias Nuxt provides.
export default defineConfig({
  resolve: {
    alias: {
      '#shared': fileURLToPath(new URL('./shared', import.meta.url)),
    },
  },
})
