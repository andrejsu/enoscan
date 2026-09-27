export const SCANNER_PATH = '/'

/** A click on a link to the scanner while already on it means «start a new scan». */
export function isScannerRestart(linkTo: string, currentPath: string): boolean {
  return linkTo === SCANNER_PATH && currentPath === SCANNER_PATH
}
