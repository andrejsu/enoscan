import type { ScanResponse } from '#shared/contracts'
import { validateScanFile } from '~/utils/scan-file'

type ScannerState =
  | { status: 'idle' }
  | { status: 'ready', file: File, previewUrl: string }
  | { status: 'processing', file: File, previewUrl: string }
  | { status: 'success', previewUrl: string, response: ScanResponse }
  | { status: 'error', previewUrl?: string, message: string }

export function useWineScanner() {
  const state = ref<ScannerState>({ status: 'idle' })

  function revokePreview() {
    if ('previewUrl' in state.value && state.value.previewUrl) {
      URL.revokeObjectURL(state.value.previewUrl)
    }
  }

  function selectFile(file: File) {
    const error = validateScanFile(file)

    if (error) {
      revokePreview()
      state.value = { status: 'error', message: error }
      return
    }

    revokePreview()
    state.value = {
      status: 'ready',
      file,
      previewUrl: URL.createObjectURL(file),
    }
  }

  async function scan() {
    if (state.value.status !== 'ready') {
      return
    }

    const { file, previewUrl } = state.value
    state.value = { status: 'processing', file, previewUrl }

    const body = new FormData()
    body.append('image', file)

    try {
      const response = await $fetch<ScanResponse>('/api/scans', {
        method: 'POST',
        body,
      })

      state.value = { status: 'success', previewUrl, response }
    }
    catch {
      state.value = {
        status: 'error',
        previewUrl,
        message: 'Не удалось обработать фото. Проверьте соединение и попробуйте ещё раз.',
      }
    }
  }

  function reset() {
    revokePreview()
    state.value = { status: 'idle' }
  }

  onBeforeUnmount(revokePreview)

  return {
    state: readonly(state),
    selectFile,
    scan,
    reset,
  }
}
