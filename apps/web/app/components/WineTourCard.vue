<script setup lang="ts">
import { ArrowUpRight, BookmarkCheck, Clock3, MapPin, UsersRound } from '@lucide/vue'
import type { WineTour } from '#shared/tours/catalog'

const props = withDefaults(defineProps<{
  tour: WineTour
  position: number
  isFeatured?: boolean
  isPlanned?: boolean
}>(), {
  isFeatured: false,
  isPlanned: false,
})

const emit = defineEmits<{
  opened: [tour: WineTour]
}>()

const priceLabel = computed(() => new Intl.NumberFormat('ru-RU').format(props.tour.price))
</script>

<template>
  <article
    class="tour-card"
    :class="[`tour-card--${tour.tone}`, { 'tour-card--featured': isFeatured }]"
  >
    <div class="tour-card__media">
      <img
        :src="tour.image"
        :alt="tour.imageAlt"
        loading="lazy"
        width="768"
        height="512"
      >
      <span class="tour-card__number" aria-hidden="true">{{ String(position).padStart(2, '0') }}</span>
      <span v-if="isPlanned" class="tour-card__planned">
        <BookmarkCheck :size="15" aria-hidden="true" />
        В планах
      </span>
    </div>

    <div class="tour-card__body">
      <div class="tour-card__kicker">
        <span>{{ tour.winery }}</span>
        <span>{{ tour.formatLabel }}</span>
      </div>

      <h3>{{ tour.title }}</h3>
      <p class="tour-card__summary">{{ tour.summary }}</p>

      <ul class="tour-card__facts" aria-label="Параметры тура">
        <li><MapPin :size="17" aria-hidden="true" />{{ tour.location }}</li>
        <li><Clock3 :size="17" aria-hidden="true" />{{ tour.duration }}</li>
        <li><UsersRound :size="17" aria-hidden="true" />{{ tour.groupLabel }}</li>
      </ul>

      <div class="tour-card__footer">
        <p><span>от</span> {{ priceLabel }} ₽ <small>за человека</small></p>
        <button type="button" @click="emit('opened', tour)">
          Спланировать
          <ArrowUpRight :size="18" aria-hidden="true" />
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.tour-card {
  --card-accent: var(--color-tour-plum);
  min-width: 0;
  overflow: hidden;
  display: grid;
  grid-template-rows: auto 1fr;
  border: 1px solid var(--color-tour-line);
  border-radius: var(--radius-lg);
  background: var(--color-paper);
  box-shadow: var(--shadow-paper);
}

.tour-card--sage {
  --card-accent: var(--color-green-dark);
}

.tour-card--amber {
  --card-accent: var(--color-tour-ochre-dark);
}

.tour-card__media {
  position: relative;
  min-height: 264px;
  overflow: hidden;
  background: var(--color-soft-green);
}

.tour-card__media::after {
  content: '';
  position: absolute;
  inset: auto 0 0;
  height: 45%;
  background: linear-gradient(transparent, rgb(35 23 29 / 44%));
  pointer-events: none;
}

.tour-card__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 700ms cubic-bezier(.2, .75, .25, 1);
}

.tour-card:hover .tour-card__media img {
  transform: scale(1.025);
}

.tour-card__number,
.tour-card__planned {
  position: absolute;
  z-index: 1;
  color: var(--color-on-tour-dark);
}

.tour-card__number {
  top: 20px;
  left: 22px;
  font-family: var(--font-display);
  font-size: 44px;
  line-height: 1;
  letter-spacing: -0.06em;
  text-shadow: 0 2px 14px rgb(0 0 0 / 22%);
}

.tour-card__planned {
  right: 16px;
  bottom: 16px;
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 12px;
  border: 1px solid rgb(255 255 255 / 42%);
  border-radius: var(--radius-pill);
  color: var(--color-on-tour-dark);
  background: rgb(48 25 41 / 78%);
  font-size: 12px;
  font-weight: 700;
  backdrop-filter: blur(12px);
}

.tour-card__body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 24px;
}

.tour-card__kicker {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 6px 16px;
  margin-bottom: 14px;
  color: var(--card-accent);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .1em;
  text-transform: uppercase;
}

.tour-card h3 {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(1.55rem, 4vw, 2rem);
  font-weight: 600;
  line-height: 1.08;
  letter-spacing: -.03em;
  text-wrap: balance;
}

.tour-card__summary {
  margin: 14px 0 18px;
  color: var(--color-muted);
  line-height: 1.55;
}

.tour-card__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 9px 16px;
  padding: 0;
  margin: 0 0 24px;
  list-style: none;
}

.tour-card__facts li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-muted);
  font-size: 13px;
}

.tour-card__facts svg {
  flex: 0 0 auto;
  color: var(--card-accent);
}

.tour-card__footer {
  margin-top: auto;
  padding-top: 18px;
  border-top: 1px solid var(--color-tour-line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.tour-card__footer p {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  white-space: nowrap;
}

.tour-card__footer p span,
.tour-card__footer p small {
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 600;
}

.tour-card__footer button {
  min-height: 46px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 15px;
  border: 1px solid var(--card-accent);
  border-radius: var(--radius-pill);
  color: var(--color-paper);
  background: var(--card-accent);
  font-weight: 700;
  cursor: pointer;
  transition: background 180ms ease, box-shadow 180ms ease;
}

.tour-card__footer button:hover {
  box-shadow: 0 8px 22px rgb(48 25 41 / 18%);
}

.tour-card__footer button:active {
  opacity: .82;
}

@media (min-width: 860px) {
  .tour-card--featured {
    grid-column: 1 / -1;
    grid-template-columns: minmax(0, 1.35fr) minmax(340px, .65fr);
    grid-template-rows: minmax(440px, auto);
  }

  .tour-card--featured .tour-card__media {
    min-height: 100%;
  }

  .tour-card--featured .tour-card__body {
    padding: clamp(28px, 4vw, 48px);
  }

  .tour-card--featured h3 {
    font-size: clamp(2rem, 4vw, 3.25rem);
  }
}

@media (max-width: 520px) {
  .tour-card__media {
    min-height: 230px;
  }

  .tour-card__body {
    padding: 20px;
  }

  .tour-card__footer {
    align-items: stretch;
    flex-direction: column;
  }

  .tour-card__footer button {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .tour-card__media img {
    transition: none;
  }

  .tour-card:hover .tour-card__media img {
    transform: none;
  }
}
</style>
