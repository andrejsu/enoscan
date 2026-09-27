<script setup lang="ts">
import type { WineTour } from '#shared/tours/catalog'
import type { SavedTourPlan } from '~/utils/tour-plans'

const selectedTour = ref<WineTour | null>(null)
const tourPlans = useTourPlans()

const selectedPlan = computed(() => selectedTour.value
  ? tourPlans.getPlan(selectedTour.value.id)
  : undefined)

useHead({
  title: 'Карта винных туров — Своё вино',
  meta: [
    {
      name: 'description',
      content: 'Интерактивная карта виноделен Крыма и юга России с фильтрами и ИИ-планировщиком маршрутов.',
    },
  ],
})

function handlePlanSaved(plan: Omit<SavedTourPlan, 'savedAt'>) {
  tourPlans.save(plan)
}
</script>

<template>
  <main class="page-container tours-page">
    <TourRouteStudio @tour-opened="selectedTour = $event" />

    <WineTourPlannerDialog
      v-if="selectedTour"
      :key="selectedTour.id"
      :tour="selectedTour"
      :existing-plan="selectedPlan"
      @closed="selectedTour = null"
      @plan-saved="handlePlanSaved"
      @plan-removed="tourPlans.remove"
    />
  </main>
</template>

<style scoped>
.tours-page {
  padding-block: clamp(18px, 3vw, 36px) 64px;
}
</style>
