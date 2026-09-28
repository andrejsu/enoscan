// OpenAPI spec that /docs (the ranking service's Swagger UI) loads.
export default defineEventHandler(event =>
  proxyRequest(event, `${useRuntimeConfig().rankingBaseUrl}/openapi.json`))
