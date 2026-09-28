// Swagger UI of the ranking service, served on the site's own origin.
export default defineEventHandler(event =>
  proxyRequest(event, `${useRuntimeConfig().rankingBaseUrl}/docs`))
