/**
 * The header's «Сканер» link points at `/`. On the scanner page itself that
 * navigation is a no-op for the router, so the page would keep showing the
 * previous result; the header bumps this counter instead and the page resets.
 */
export function useScannerReset() {
  const requests = useState('scanner-reset-requests', () => 0)

  function request() {
    requests.value += 1
  }

  return {
    requests: readonly(requests),
    request,
  }
}
