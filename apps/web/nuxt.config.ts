import { isFeatureEnabled } from './shared/utils/feature-flags'

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  css: ['~/assets/css/main.css'],
  devtools: { enabled: true },
  modules: ['@nuxt/eslint'],
  runtimeConfig: {
    retrievalBaseUrl: process.env.NUXT_RETRIEVAL_BASE_URL || 'http://127.0.0.1:8000',
    // Scanner-only: /api/scans (POST) calls this final resolved result, not
    // retrievalBaseUrl. Everything else (image proxy, /admin, /astro) reads
    // the plain catalog and keeps using retrievalBaseUrl — ranking has no
    // /v1/catalog of its own. See services/retrieval/app/ranking_main.py.
    rankingBaseUrl: process.env.NUXT_RANKING_BASE_URL || 'http://127.0.0.1:8000',
    databaseUrl: process.env.NUXT_DATABASE_URL || '',
    sommelierProvider: process.env.NUXT_SOMMELIER_PROVIDER || 'openai',
    sommelierModel: process.env.NUXT_SOMMELIER_MODEL || '',
    sommelierMaxRequests: Number.parseInt(process.env.NUXT_SOMMELIER_MAX_REQUESTS || '20', 10),
    sommelierApiKey: process.env.NUXT_SOMMELIER_API_KEY || '',
    storage: {
      endpoint: process.env.NUXT_STORAGE_ENDPOINT || 'http://127.0.0.1:9000',
      region: process.env.NUXT_STORAGE_REGION || 'us-east-1',
      accessKey: process.env.NUXT_STORAGE_ACCESS_KEY || 'vinolog',
      secretKey: process.env.NUXT_STORAGE_SECRET_KEY || 'vinolog-secret',
      imagesBucket: process.env.NUXT_STORAGE_IMAGES_BUCKET || 'vinolog-images',
    },
    public: {
      scanMode: process.env.NUXT_PUBLIC_SCAN_MODE || 'mock',
      astroEnabled: isFeatureEnabled(process.env.NUXT_PUBLIC_ASTRO_ENABLED),
      sommelierMode: process.env.NUXT_PUBLIC_SOMMELIER_MODE || 'mock',
    },
  },
  typescript: {
    typeCheck: true,
  },
  app: {
    head: {
      htmlAttrs: { lang: 'ru' },
      title: 'Сканер российских вин',
      meta: [
        {
          name: 'description',
          content: 'Наведите камеру на этикетку и найдите точную карточку российского вина.',
        },
        { name: 'theme-color', content: '#e7e5de' },
      ],
    },
  },
})
