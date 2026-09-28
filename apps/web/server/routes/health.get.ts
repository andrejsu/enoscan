// Readiness of the ranking service, listed on /docs.
export default defineEventHandler(event =>
  proxyRequest(event, `${useRuntimeConfig().rankingBaseUrl}/health`))
