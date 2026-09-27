import type { ScanRecommendation, ScanResponse } from '#shared/contracts'

export const MAX_SCAN_RECOMMENDATIONS = 3

/** Related catalog wines to offer when the scan found no match; never next to a confirmed card. */
export function visibleRecommendations(
  result: Pick<ScanResponse, 'status' | 'recommendations'>,
): readonly ScanRecommendation[] {
  if (result.status === 'matched') {
    return []
  }
  return (result.recommendations ?? []).slice(0, MAX_SCAN_RECOMMENDATIONS)
}
