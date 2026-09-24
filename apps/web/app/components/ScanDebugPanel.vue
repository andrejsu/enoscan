<script setup lang="ts">
import type { ScanDebug, ScanDebugField, ScanStatus } from '#shared/contracts'
import { Bug, ChevronDown } from '@lucide/vue'
import {
  clampShare,
  cropBoxStyle,
  firstFieldWithCandidates,
  formatScore,
  rankingSegments,
  scanDebugFieldLabels,
  scanDebugStages,
} from '~/utils/scan-debug'

const props = defineProps<{
  debug: ScanDebug
  totalMs: number
}>()

const statusLabels: Readonly<Record<ScanStatus, string>> = {
  matched: 'совпадение',
  uncertain: 'неуверенно',
  not_found: 'не найдено',
}

const stages = computed(() => scanDebugStages(props.debug))

const selectedField = ref<ScanDebugField | null>(firstFieldWithCandidates(props.debug.ocr.fields))
watch(() => props.debug, (debug) => { selectedField.value = firstFieldWithCandidates(debug.ocr.fields) })
const selectedCandidates = computed(() =>
  props.debug.ocr.fields.find(field => field.field === selectedField.value)?.candidates ?? [])

const preprocessingMetrics = computed(() => {
  const { metrics, usedSam } = props.debug.preprocessing
  return [
    { label: 'Режим', value: usedSam ? 'SAM' : 'кроп' },
    { label: 'Этикетка', value: metrics.labelWidth && metrics.labelHeight ? `${metrics.labelWidth}×${metrics.labelHeight}` : '—' },
    { label: 'Резкость', value: metrics.sharpness?.toFixed(0) ?? '—' },
    { label: 'Шум σ', value: metrics.noiseSigma?.toFixed(2) ?? '—' },
    { label: 'Блики', value: metrics.glareFraction?.toFixed(3) ?? '—' },
    { label: 'Денойз', value: metrics.isDenoised ? 'да' : 'нет' },
  ]
})

const visibleWarnings = computed(() =>
  props.debug.preprocessing.warnings.filter(warning => warning !== 'sam_skipped'))

const rankingRows = computed(() => props.debug.ranking.candidates.map(candidate => ({
  ...candidate,
  segments: rankingSegments(candidate.fields),
})))

const rankingLegend = computed(() => {
  const fields = new Set(rankingRows.value.flatMap(row => row.segments.map(segment => segment.field)))
  return [...fields]
})

function barStyle(score: number) {
  return { width: `${clampShare(score) * 100}%` }
}
</script>

<template>
  <details class="scan-debug">
    <summary class="scan-debug__summary">
      <Bug :size="18" aria-hidden="true" />
      <span>Отладка скана</span>
      <small>{{ totalMs }} мс · {{ statusLabels[debug.ranking.status] }}</small>
      <ChevronDown class="scan-debug__chevron" :size="18" aria-hidden="true" />
    </summary>

    <div class="scan-debug__body">
      <ol class="scan-debug__pipeline" aria-label="Этапы скана">
        <li
          v-for="(stage, index) in stages"
          :key="stage.key"
          :class="{ 'is-problem': stage.hasProblem }"
        >
          <span class="scan-debug__step-number" aria-hidden="true">{{ index + 1 }}</span>
          <span class="scan-debug__stage-text">
            <strong>{{ stage.title }}</strong>
            <span>{{ stage.summary }}</span>
          </span>
          <span class="scan-debug__ms">{{ stage.durationMs }} мс</span>
        </li>
      </ol>

      <div class="scan-debug__grid">
        <!-- 1. label_prep -->
        <section class="debug-step" aria-labelledby="debug-step-preprocessing">
          <header class="debug-step__header">
            <span class="scan-debug__step-number" aria-hidden="true">1</span>
            <h3 id="debug-step-preprocessing">Обработка фото</h3>
            <span class="scan-debug__ms">{{ debug.preprocessing.durationMs }} мс</span>
          </header>
          <p class="debug-step__caption">scripts/label_prep.py → визуальная и OCR-ветки</p>

          <div class="debug-step__body">
            <div class="debug-prep">
              <figure>
                <div class="debug-prep__thumb">
                  <div class="debug-prep__frame">
                    <img :src="debug.preprocessing.images.source" alt="Загруженный кадр">
                    <span
                      v-if="debug.preprocessing.cropBox"
                      class="debug-prep__crop"
                      :style="cropBoxStyle(debug.preprocessing.cropBox)"
                      aria-hidden="true"
                    />
                  </div>
                </div>
                <figcaption>Кадр{{ debug.preprocessing.cropBox ? ' + кроп' : '' }}</figcaption>
              </figure>
              <figure>
                <img :src="debug.preprocessing.images.visual" alt="Визуальная ветка: цветной кроп этикетки">
                <figcaption>Визуальная</figcaption>
              </figure>
              <figure>
                <img :src="debug.preprocessing.images.ocr" alt="OCR-ветка: кадр, который прочитал OCR">
                <figcaption>Для OCR</figcaption>
              </figure>
            </div>

            <dl class="debug-metrics">
              <div v-for="metric in preprocessingMetrics" :key="metric.label">
                <dt>{{ metric.label }}</dt>
                <dd>{{ metric.value }}</dd>
              </div>
            </dl>

            <ul v-if="visibleWarnings.length" class="debug-warnings">
              <li v-for="warning in visibleWarnings" :key="warning">{{ warning }}</li>
            </ul>
          </div>
        </section>

        <!-- 2. OCR -->
        <section class="debug-step" aria-labelledby="debug-step-ocr">
          <header class="debug-step__header">
            <span class="scan-debug__step-number" aria-hidden="true">2</span>
            <h3 id="debug-step-ocr">OCR: параметры</h3>
            <span class="scan-debug__ms">{{ debug.ocr.durationMs }} мс</span>
          </header>
          <p class="debug-step__caption">
            {{ debug.ocr.wordCount }} слов
            · ср. уверенность {{ debug.ocr.meanConfidence ?? '—' }}
            · {{ debug.ocr.passes.join(' + ') }}
            <template v-if="debug.ocr.error"> · <span class="debug-error">{{ debug.ocr.error }}</span></template>
          </p>

          <div class="debug-step__body">
            <p class="debug-ocr__text"><code>{{ debug.ocr.text || 'текст не распознан' }}</code></p>

            <div class="debug-tabs" role="tablist" aria-label="Поле этикетки">
              <button
                v-for="field in debug.ocr.fields"
                :key="field.field"
                type="button"
                role="tab"
                :aria-selected="selectedField === field.field"
                :class="{ 'is-empty': !field.candidates.length }"
                @click="selectedField = field.field"
              >
                {{ scanDebugFieldLabels[field.field] }}
                <span>{{ field.candidates.length }}</span>
              </button>
            </div>

            <ol v-if="selectedCandidates.length" class="debug-rows" role="tabpanel">
              <li v-for="(candidate, index) in selectedCandidates" :key="candidate.value">
                <span class="debug-rows__rank">{{ index + 1 }}</span>
                <span class="debug-rows__label">{{ candidate.value }}</span>
                <span class="debug-bar"><span :style="barStyle(candidate.score)" /></span>
                <span class="debug-rows__score">{{ formatScore(candidate.score) }}</span>
              </li>
            </ol>
            <p v-else class="debug-empty" role="tabpanel">Для этого поля OCR не нашёл кандидатов.</p>
          </div>
        </section>

        <!-- 3. Visual retriever -->
        <section class="debug-step" aria-labelledby="debug-step-retriever">
          <header class="debug-step__header">
            <span class="scan-debug__step-number" aria-hidden="true">3</span>
            <h3 id="debug-step-retriever">Ретривер: этикетки</h3>
            <span class="scan-debug__ms">{{ debug.retriever.durationMs }} мс</span>
          </header>
          <p class="debug-step__caption">
            DINOv2 + SIFT/RANSAC · запрос против {{ debug.retriever.candidates.length }} эталонов
            <template v-if="debug.retriever.error"> · <span class="debug-error">{{ debug.retriever.error }}</span></template>
          </p>

          <div class="debug-step__body">
            <ol v-if="debug.retriever.candidates.length" class="debug-rows debug-rows--images">
              <li v-for="(candidate, index) in debug.retriever.candidates" :key="candidate.slug">
                <span class="debug-rows__rank">{{ index + 1 }}</span>
                <span class="debug-pair">
                  <img :src="debug.preprocessing.images.visual" alt="" loading="lazy">
                  <img
                    v-if="candidate.wine?.imagePreviewUrl"
                    :src="candidate.wine.imagePreviewUrl"
                    :alt="`Эталон ${candidate.slug}`"
                    loading="lazy"
                  >
                  <span v-else class="debug-pair__missing" aria-label="Нет фото в каталоге">—</span>
                </span>
                <span class="debug-rows__label">
                  <code>{{ candidate.slug }}</code>
                  <small>inliers {{ candidate.inliers ?? '—' }} · matches {{ candidate.goodMatches ?? '—' }}</small>
                </span>
                <span class="debug-bar"><span :style="barStyle(candidate.score)" /></span>
                <span class="debug-rows__score">{{ formatScore(candidate.score) }}</span>
              </li>
            </ol>
            <p v-else class="debug-empty">
              {{ debug.retriever.error ? 'Ретривер не ответил — ранжирование шло только по OCR.' : 'Ретривер не вернул кандидатов.' }}
            </p>
          </div>
        </section>

        <!-- 4. Ranking -->
        <section class="debug-step" aria-labelledby="debug-step-ranking">
          <header class="debug-step__header">
            <span class="scan-debug__step-number" aria-hidden="true">4</span>
            <h3 id="debug-step-ranking">Ранжирование</h3>
            <span class="scan-debug__ms">{{ debug.ranking.durationMs }} мс</span>
          </header>
          <p class="debug-step__caption">
            Порог {{ formatScore(debug.ranking.threshold) }} · итог {{ formatScore(debug.ranking.score) }}
            · {{ statusLabels[debug.ranking.status] }}
          </p>

          <div class="debug-step__body">
            <ul v-if="rankingLegend.length" class="debug-legend" aria-label="Вклад полей">
              <li v-for="field in rankingLegend" :key="field">
                <span :class="`debug-field--${field}`" aria-hidden="true" />
                {{ scanDebugFieldLabels[field] }}
              </li>
            </ul>

            <ol v-if="rankingRows.length" class="debug-rows debug-rows--ranking">
              <li
                v-for="(row, index) in rankingRows"
                :key="row.slug"
                :class="{ 'is-winner': index === 0 && debug.ranking.status === 'matched' }"
              >
                <span class="debug-rows__rank">{{ index + 1 }}</span>
                <span class="debug-rows__label">
                  <code>{{ row.slug }}</code>
                  <small>{{ row.wine.name }}</small>
                </span>
                <span
                  class="debug-stack"
                  :style="{ '--threshold': `${clampShare(debug.ranking.threshold) * 100}%` }"
                  :title="row.fields.map(term => `${scanDebugFieldLabels[term.field]}: ${formatScore(term.score)} × ${term.weight}`).join('\n')"
                >
                  <span class="sr-only">
                    {{ row.fields.map(term => `${scanDebugFieldLabels[term.field]} ${formatScore(term.score)}`).join(', ') }}
                  </span>
                  <span
                    v-for="segment in row.segments"
                    :key="segment.field"
                    :class="`debug-field--${segment.field}`"
                    :style="barStyle(segment.contribution)"
                  />
                </span>
                <span class="debug-rows__score">{{ formatScore(row.score) }}</span>
              </li>
            </ol>
            <p v-else class="debug-empty">Каталог пуст — ранжировать нечего.</p>
          </div>
        </section>
      </div>
    </div>
  </details>
</template>
