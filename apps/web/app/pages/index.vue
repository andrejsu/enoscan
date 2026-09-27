<script setup lang="ts">
const scanner = useWineScanner()
const scannerReset = useScannerReset()

watch(scannerReset.requests, () => {
  scanner.reset()
  window.scrollTo({ top: 0 })
})

const panelStatus = computed(() => scanner.state.value.status === 'success'
  ? 'success'
  : scanner.state.value.status)

const previewUrl = computed(() => 'previewUrl' in scanner.state.value
  ? scanner.state.value.previewUrl
  : undefined)

const error = computed(() => scanner.state.value.status === 'error'
  ? scanner.state.value.message
  : undefined)

const response = computed(() => scanner.state.value.status === 'success'
  ? scanner.state.value.response
  : undefined)
</script>

<template>
  <div>
    <div class="page-container home-page">
      <ScannerPanel
        v-if="!response"
        :status="panelStatus"
        :preview-url="previewUrl"
        :error="error"
        @file-selected="scanner.selectFile"
        @scan-requested="scanner.scan"
        @reset-requested="scanner.reset"
      />

      <template v-else>
        <WineResultCard
          :result="response"
          @reset-requested="scanner.reset"
        />
        <ScanDebugPanel
          v-if="response.debug"
          :debug="response.debug"
          :total-ms="response.timing.totalMs"
        />
      </template>
    </div>
  </div>
</template>
