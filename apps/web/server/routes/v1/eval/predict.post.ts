// Organizer's evaluation endpoint (data/eval/participant_test.sh), served on the site's own origin.
export default defineEventHandler(event =>
  proxyRequest(event, `${useRuntimeConfig().rankingBaseUrl}/v1/eval/predict`))
