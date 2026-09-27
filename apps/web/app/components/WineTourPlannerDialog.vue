<script setup lang="ts">
import { BookmarkCheck, CalendarDays, Check, ExternalLink, Minus, Plus, Trash2, UsersRound, X } from '@lucide/vue'
import type { WineTour } from '#shared/tours/catalog'
import type { SavedTourPlan, TourDatePreference } from '~/utils/tour-plans'

const props = defineProps<{
  tour: WineTour
  existingPlan?: SavedTourPlan
}>()

const emit = defineEmits<{
  closed: []
  planSaved: [plan: Omit<SavedTourPlan, 'savedAt'>]
  planRemoved: [tourId: string]
}>()

const dialog = ref<HTMLDialogElement>()
const datePreference = ref<TourDatePreference>(props.existingPlan?.datePreference ?? 'nearest-saturday')
const guests = ref(props.existingPlan?.guests ?? 2)
const isSaved = ref(Boolean(props.existingPlan))

const dateOptions: Array<{ value: TourDatePreference, label: string, hint: string }> = [
  { value: 'nearest-saturday', label: 'Суббота', hint: 'ближайшая' },
  { value: 'nearest-sunday', label: 'Воскресенье', hint: 'ближайшее' },
  { value: 'decide-later', label: 'Позже', hint: 'без даты' },
]

const totalPrice = computed(() => new Intl.NumberFormat('ru-RU').format(props.tour.price * guests.value))
const guestLabel = computed(() => {
  const count = guests.value
  const suffix = count === 1 ? 'гость' : count >= 2 && count <= 4 ? 'гостя' : 'гостей'
  return `${count} ${suffix}`
})

watch([datePreference, guests], () => {
  isSaved.value = false
})

onMounted(() => {
  if (dialog.value && !dialog.value.open) {
    dialog.value.showModal()
  }
})

function handleBackdropClick(event: MouseEvent) {
  if (event.target === dialog.value) {
    dialog.value?.close()
  }
}

function handleSave() {
  emit('planSaved', {
    tourId: props.tour.id,
    datePreference: datePreference.value,
    guests: guests.value,
  })
  isSaved.value = true
}

function handleRemove() {
  emit('planRemoved', props.tour.id)
  dialog.value?.close()
}
</script>

<template>
  <dialog
    ref="dialog"
    class="tour-dialog"
    :aria-labelledby="`tour-dialog-title-${tour.id}`"
    @click="handleBackdropClick"
    @close="emit('closed')"
  >
    <div class="tour-dialog__sheet">
      <button
        type="button"
        class="tour-dialog__close"
        aria-label="Закрыть планировщик"
        @click="dialog?.close()"
      >
        <X :size="21" aria-hidden="true" />
      </button>

      <div class="tour-dialog__media">
        <img :src="tour.image" :alt="tour.imageAlt" width="1536" height="1024">
        <div class="tour-dialog__media-copy">
          <span>{{ tour.regionLabel }} · {{ tour.location }}</span>
          <p>{{ tour.winery }}</p>
        </div>
      </div>

      <div class="tour-dialog__content">
        <h2 :id="`tour-dialog-title-${tour.id}`">{{ tour.title }}</h2>
        <p class="tour-dialog__lead">{{ tour.summary }}</p>

        <div class="tour-dialog__included" aria-label="Что входит">
          <span v-for="item in tour.includes" :key="item">
            <Check :size="15" aria-hidden="true" />{{ item }}
          </span>
          <span v-if="tour.ageRestriction">
            {{ tour.ageRestriction }}
          </span>
        </div>

        <a
          v-if="tour.sourceUrl"
          class="tour-dialog__source"
          :href="tour.sourceUrl"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span>
            <strong>Официальная программа</strong>
            <small v-if="tour.sourceCheckedAt">Проверено {{ tour.sourceCheckedAt }}</small>
          </span>
          <ExternalLink :size="18" aria-hidden="true" />
        </a>

        <section class="tour-dialog__program" :aria-labelledby="`tour-program-title-${tour.id}`">
          <h3 :id="`tour-program-title-${tour.id}`">Как пройдёт маршрут</h3>
          <ol>
            <li v-for="item in tour.program" :key="item.time">
              <time>{{ item.time }}</time>
              <div>
                <strong>{{ item.title }}</strong>
                <p>{{ item.description }}</p>
              </div>
            </li>
          </ol>
        </section>

        <section class="tour-dialog__planner" :aria-labelledby="`tour-date-title-${tour.id}`">
          <div class="tour-dialog__planner-heading">
            <div>
              <CalendarDays :size="21" aria-hidden="true" />
              <h3 :id="`tour-date-title-${tour.id}`">Когда удобно</h3>
            </div>
            <span>предпочтение, не бронь</span>
          </div>

          <div class="tour-dialog__dates">
            <label v-for="option in dateOptions" :key="option.value">
              <input v-model="datePreference" type="radio" :value="option.value">
              <span><strong>{{ option.label }}</strong><small>{{ option.hint }}</small></span>
            </label>
          </div>

          <div class="tour-dialog__guests">
            <div>
              <UsersRound :size="21" aria-hidden="true" />
              <span><strong>Компания</strong><small>{{ guestLabel }}</small></span>
            </div>
            <div class="tour-dialog__stepper">
              <button
                type="button"
                :disabled="guests <= 1"
                aria-label="Уменьшить число гостей"
                @click="guests -= 1"
              >
                <Minus :size="18" aria-hidden="true" />
              </button>
              <output :aria-label="`Гостей: ${guests}`">{{ guests }}</output>
              <button
                type="button"
                :disabled="guests >= 8"
                aria-label="Увеличить число гостей"
                @click="guests += 1"
              >
                <Plus :size="18" aria-hidden="true" />
              </button>
            </div>
          </div>

          <button type="button" class="tour-dialog__save" @click="handleSave">
            <BookmarkCheck :size="19" aria-hidden="true" />
            {{ isSaved ? 'План сохранён' : `Сохранить план · ${totalPrice} ₽` }}
          </button>

          <p class="tour-dialog__note" role="status">
            {{ isSaved ? 'Маршрут сохранён на этом устройстве.' : (tour.bookingNote ?? 'Расписание и итоговую стоимость нужно подтвердить у винодельни.') }}
          </p>

          <button
            v-if="existingPlan"
            type="button"
            class="tour-dialog__remove"
            @click="handleRemove"
          >
            <Trash2 :size="17" aria-hidden="true" />
            Убрать из планов
          </button>
        </section>
      </div>
    </div>
  </dialog>
</template>

<style scoped>
.tour-dialog {
  width: min(1100px, calc(100% - 32px));
  max-width: none;
  max-height: min(880px, calc(100dvh - 32px));
  padding: 0;
  overflow: hidden;
  border: 0;
  border-radius: var(--radius-lg);
  color: var(--color-ink);
  background: var(--color-paper);
  box-shadow: 0 30px 100px rgb(27 14 23 / 38%);
}

.tour-dialog::backdrop {
  background: rgb(26 16 22 / 74%);
  backdrop-filter: blur(7px);
}

.tour-dialog__sheet {
  position: relative;
  max-height: min(880px, calc(100dvh - 32px));
  overflow-y: auto;
  display: grid;
  grid-template-columns: minmax(280px, .7fr) minmax(0, 1.3fr);
}

.tour-dialog__close {
  position: fixed;
  z-index: 4;
  width: 46px;
  height: 46px;
  display: grid;
  place-items: center;
  margin: 18px;
  border: 1px solid rgb(255 255 255 / 40%);
  border-radius: 50%;
  color: var(--color-on-tour-dark);
  background: rgb(48 25 41 / 76%);
  cursor: pointer;
  backdrop-filter: blur(10px);
}

.tour-dialog__media {
  position: sticky;
  top: 0;
  height: min(880px, calc(100dvh - 32px));
  min-height: 580px;
  overflow: hidden;
  background: var(--color-tour-plum);
}

.tour-dialog__media::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, transparent 48%, rgb(35 18 30 / 76%));
}

.tour-dialog__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.tour-dialog__media-copy {
  position: absolute;
  z-index: 1;
  right: 28px;
  bottom: 30px;
  left: 28px;
  color: var(--color-on-tour-dark);
}

.tour-dialog__media-copy span {
  font-size: 14px;
  font-weight: 600;
}

.tour-dialog__media-copy p {
  margin: 4px 0 0;
  font-family: var(--font-display);
  font-size: 30px;
  font-weight: 500;
  line-height: 1.25;
}

.tour-dialog__content {
  padding: clamp(32px, 5vw, 64px);
}

.tour-dialog h2 {
  margin: 0;
  font-size: clamp(32px, 4vw, 42px);
}

.tour-dialog__lead {
  max-width: 620px;
  margin: 22px 0;
  color: var(--color-muted);
  font-size: 18px;
  line-height: 1.55;
}

.tour-dialog__included {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* Чипы как на vino-svoe.ru. */
.tour-dialog__included span {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border: 1px solid var(--color-chip-line);
  border-radius: 16px;
  color: var(--color-ink);
  background: var(--color-paper);
  font-size: 14px;
  font-weight: 600;
}

.tour-dialog__source {
  min-height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 9px 12px;
  margin-top: 16px;
  border-radius: 12px;
  color: var(--color-wine);
  background: var(--color-soft-wine);
  font-weight: 600;
  transition: background-color 0.3s ease-in;
}

.tour-dialog__source:hover {
  background: var(--color-soft-wine-hover);
}

.tour-dialog__source span {
  min-width: 0;
  display: grid;
}

.tour-dialog__source small {
  color: var(--color-muted);
  font-size: 13px;
  font-weight: 400;
}

.tour-dialog__program,
.tour-dialog__planner {
  margin-top: 42px;
}

.tour-dialog h3 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 500;
  line-height: 1.25;
}

.tour-dialog__program ol {
  padding: 0;
  margin: 22px 0 0;
  list-style: none;
}

.tour-dialog__program li {
  position: relative;
  display: grid;
  grid-template-columns: 58px 1fr;
  gap: 16px;
  padding-bottom: 24px;
}

.tour-dialog__program li:not(:last-child)::before {
  content: '';
  position: absolute;
  top: 26px;
  bottom: 0;
  left: 25px;
  width: 1px;
  background: var(--color-line);
}

.tour-dialog__program time {
  z-index: 1;
  width: 52px;
  height: 30px;
  align-self: start;
  display: grid;
  place-items: center;
  border: 1px solid var(--color-chip-line);
  border-radius: 16px;
  background: var(--color-paper);
  color: var(--color-wine);
  font-size: 12px;
  font-weight: 600;
}

.tour-dialog__program strong {
  font-size: 16px;
}

.tour-dialog__program p {
  margin: 4px 0 0;
  color: var(--color-muted);
  font-size: 14px;
}

.tour-dialog__planner {
  padding: 24px;
  border-radius: 24px;
  background: var(--color-scanner-surface);
}

.tour-dialog__planner-heading,
.tour-dialog__planner-heading > div,
.tour-dialog__guests,
.tour-dialog__guests > div:first-child {
  display: flex;
  align-items: center;
}

.tour-dialog__planner-heading {
  justify-content: space-between;
  gap: 16px;
}

.tour-dialog__planner-heading > div,
.tour-dialog__guests > div:first-child {
  gap: 10px;
}

.tour-dialog__planner-heading > span {
  color: var(--color-muted);
  font-size: 12px;
}

.tour-dialog__dates {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 18px;
}

.tour-dialog__dates label {
  position: relative;
  min-width: 0;
  cursor: pointer;
}

.tour-dialog__dates input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.tour-dialog__dates label > span {
  min-height: 66px;
  display: grid;
  align-content: center;
  padding: 10px 12px;
  border: 1px solid var(--color-chip-line);
  border-radius: 12px;
  background: var(--color-paper);
  cursor: pointer;
  transition: border-color 0.3s ease-in, background-color 0.3s ease-in;
}

.tour-dialog__dates label:hover > span {
  border-color: var(--color-wine);
}

.tour-dialog__dates input:checked + span {
  border-color: var(--color-wine);
  background: var(--color-soft-wine);
  box-shadow: inset 0 0 0 1px var(--color-wine);
}

.tour-dialog__dates input:focus-visible + span {
  outline: 3px solid rgb(143 61 66 / 38%);
  outline-offset: 3px;
}

.tour-dialog__dates strong,
.tour-dialog__dates small {
  overflow: hidden;
  text-overflow: ellipsis;
}

.tour-dialog__dates small {
  color: var(--color-muted);
}

.tour-dialog__guests {
  min-height: 70px;
  justify-content: space-between;
  gap: 16px;
  margin-top: 12px;
}

.tour-dialog__guests span {
  display: grid;
}

.tour-dialog__guests small {
  color: var(--color-muted);
}

.tour-dialog__stepper {
  display: grid;
  grid-template-columns: 44px 42px 44px;
  align-items: center;
}

.tour-dialog__stepper button {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border: 1px solid var(--color-chip-line);
  border-radius: 50%;
  color: var(--color-wine);
  background: var(--color-paper);
  cursor: pointer;
}

.tour-dialog__stepper button:disabled {
  cursor: not-allowed;
  opacity: .38;
}

.tour-dialog__stepper output {
  text-align: center;
  font-weight: 600;
}

.tour-dialog__save {
  width: 100%;
  min-height: 54px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  margin-top: 10px;
  padding: 12px 18px;
  border: 0;
  border-radius: 12px;
  color: var(--color-paper);
  background: var(--color-wine);
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.3s ease-in;
}

.tour-dialog__save:hover {
  background: var(--color-wine-hover);
}

.tour-dialog__note {
  margin: 10px 0 0;
  color: var(--color-muted);
  font-size: 12px;
  text-align: center;
}

.tour-dialog__remove {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  margin-top: 4px;
  border: 0;
  color: var(--color-wine);
  background: transparent;
  font-weight: 600;
  cursor: pointer;
}

.tour-dialog button:active {
  opacity: .82;
}

@media (max-width: 740px) {
  .tour-dialog {
    width: 100%;
    max-height: calc(100dvh - 16px);
    margin: auto 0 0;
    border-radius: 28px 28px 0 0;
  }

  .tour-dialog__sheet {
    max-height: calc(100dvh - 16px);
    display: block;
  }

  .tour-dialog__close {
    top: 0;
    right: 0;
  }

  .tour-dialog__media {
    position: relative;
    height: 310px;
    min-height: 0;
  }

  .tour-dialog__content {
    padding: 28px 20px calc(28px + env(safe-area-inset-bottom));
  }

  .tour-dialog__dates {
    grid-template-columns: 1fr;
  }

  .tour-dialog__dates label > span {
    min-height: 56px;
  }
}
</style>
