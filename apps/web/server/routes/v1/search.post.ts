// Product scan route of the ranking service, so /docs "Try it out" works on the site's origin.
export default defineEventHandler(event =>
  proxyRequest(event, `${useRuntimeConfig().rankingBaseUrl}/v1/search`))
