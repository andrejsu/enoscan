<script setup lang="ts">
import { MessageCircle, RefreshCw, Send, Trash2, Wine } from '@lucide/vue'
import { extractPairingSubject } from '~/utils/pairings'

definePageMeta({ middleware: 'sommelier-enabled' })

const config = useRuntimeConfig()
const { clear, errorMessage, isSubmitting, messages, retry, send } = useSommelierChat()
const draft = ref('')
const messageList = useTemplateRef<HTMLElement>('messageList')
const suggestions = [
  'Подбери вино к запечённой рыбе',
  'Что выбрать для праздничного аперитива?',
  'Нужно насыщенное красное к мясу',
]
const isMock = computed(() => config.public.sommelierMode === 'mock')

// Прокручиваем только ленту, а не страницу: последний вопрос встаёт наверх, ответ читается под ним.
watch(() => messages.value.length, async () => {
  await nextTick()
  const list = messageList.value
  const questions = list?.querySelectorAll<HTMLElement>('.sommelier-message--user')
  const latest = questions?.[questions.length - 1]
  if (!list || !latest) return

  const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
  list.scrollTo({ top: latest.offsetTop - 12, behavior })
})

async function handleSubmit() {
  const content = draft.value
  if (!content.trim()) return
  draft.value = ''
  await send(content)
}

// Узкое окно с мышью: колесо листает ленту подсказок вбок, пока она не упрётся в край.
function handleSuggestionsWheel(event: WheelEvent) {
  const row = event.currentTarget as HTMLElement
  // На десктопе подсказки переносятся по строкам, лента не прокручивается — колесо остаётся за страницей.
  const canScroll = getComputedStyle(row).overflowX !== 'visible' && row.scrollWidth > row.clientWidth
  if (!canScroll || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return

  const isAtEdge = event.deltaY > 0
    ? row.scrollLeft + row.clientWidth >= row.scrollWidth - 1
    : row.scrollLeft <= 0
  if (isAtEdge) return

  event.preventDefault()
  row.scrollLeft += event.deltaY
}

function handleSuggestion(suggestion: string) {
  if (!isSubmitting.value) void send(suggestion)
}
</script>

<template>
  <div class="page-container sommelier-page" :class="{ 'sommelier-page--active': messages.length }">
    <aside class="sommelier-intro">
      <h1>Цифровой сомелье</h1>
      <p>Вино к блюду, событию и вашему вкусу — только из российского каталога.</p>

      <div class="sommelier-suggestions" aria-label="Быстрые темы" @wheel="handleSuggestionsWheel">
        <button
          v-for="suggestion in suggestions"
          :key="suggestion"
          type="button"
          :disabled="isSubmitting"
          @click="handleSuggestion(suggestion)"
        >
          {{ suggestion }}
        </button>
      </div>
    </aside>

    <section class="sommelier-chat" aria-labelledby="sommelier-chat-title">
      <header class="sommelier-chat__header">
        <div>
          <MessageCircle :size="22" aria-hidden="true" />
          <h2 id="sommelier-chat-title">Диалог</h2>
        </div>
        <button
          class="icon-button"
          type="button"
          aria-label="Очистить диалог"
          title="Очистить диалог"
          :disabled="!messages.length || isSubmitting"
          @click="clear"
        >
          <Trash2 :size="19" aria-hidden="true" />
        </button>
      </header>

      <p v-if="isMock" class="sommelier-demo-note">
        Демо-режим: ответы воспроизводятся без обращения к AI и живому каталогу.
      </p>

      <div ref="messageList" class="sommelier-messages" aria-live="polite" aria-relevant="additions">
        <div v-if="!messages.length" class="sommelier-empty">
          <Wine :size="38" aria-hidden="true" />
          <h2>С чего начнём?</h2>
          <p>Назовите блюдо, повод или желаемый стиль вина.</p>
        </div>

        <article
          v-for="(message, index) in messages"
          :key="message.id"
          class="sommelier-message"
          :class="`sommelier-message--${message.role}`"
        >
          <p class="sommelier-message__label">{{ message.role === 'user' ? 'Вы' : 'Сомелье' }}</p>
          <p class="sommelier-message__bubble" :class="{ 'sommelier-message__bubble--blocked': message.status === 'blocked' }">
            {{ message.content }}
          </p>
          <div v-if="message.recommendations.length" class="sommelier-recommendations">
            <SommelierWineCard
              v-for="wine in message.recommendations"
              :key="wine.slug"
              :wine="wine"
              :pairing="extractPairingSubject(messages[index - 1]?.content ?? '')"
              :reply="message.content"
            />
          </div>
        </article>

        <div v-if="isSubmitting" class="sommelier-typing" role="status">
          <RefreshCw class="spin" :size="19" aria-hidden="true" />
          <span>Сомелье сверяется с каталогом…</span>
        </div>

        <div v-if="errorMessage" class="sommelier-chat-error" role="alert">
          <p>{{ errorMessage }}</p>
          <button class="button button--secondary" type="button" @click="retry">Повторить</button>
        </div>
      </div>

      <form class="sommelier-composer" @submit.prevent="handleSubmit">
        <label class="sommelier-composer__label" for="sommelier-message">Ваш запрос</label>
        <textarea
          id="sommelier-message"
          v-model="draft"
          rows="2"
          maxlength="800"
          placeholder="Например: сухое белое к рыбе"
          :disabled="isSubmitting"
          @keydown.enter.exact.prevent="handleSubmit"
        />
        <button class="button button--primary" type="submit" aria-label="Отправить" :disabled="isSubmitting || !draft.trim()">
          <Send :size="18" aria-hidden="true" />
          <span>Отправить</span>
        </button>
      </form>
    </section>
  </div>
</template>
