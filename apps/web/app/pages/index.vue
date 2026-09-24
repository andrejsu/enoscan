<script setup lang="ts">
import { Clock3, ShieldCheck, Sparkles } from '@lucide/vue'

const scanner = useWineScanner()

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

      <section class="trust-strip" aria-label="Как работает сервис">
        <article>
          <ShieldCheck :size="23" aria-hidden="true" />
          <div>
            <strong>Ищем конкретную позицию</strong>
            <span>Учитываем год, серию и детали этикетки</span>
          </div>
        </article>
        <article>
          <Clock3 :size="23" aria-hidden="true" />
          <div>
            <strong>Цель — до 3 секунд</strong>
            <span>Полное время измеряется от загрузки до ответа</span>
          </div>
        </article>
        <article>
          <Sparkles :size="23" aria-hidden="true" />
          <div>
            <strong>Без ложной уверенности</strong>
            <span>Попросим переснять, если данных недостаточно</span>
          </div>
        </article>
      </section>
    </div>
  </div>
</template>
