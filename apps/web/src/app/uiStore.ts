import { create } from 'zustand'

interface UiState {
  message: string | null
  xp: number | null
  show: (message: string) => void
  celebrate: (xp: number) => void
  clear: () => void
}

let toastTimer: ReturnType<typeof setTimeout> | null = null
let xpTimer: ReturnType<typeof setTimeout> | null = null

export const useToastStore = create<UiState>((set) => ({
  message: null,
  xp: null,
  show: (message) => {
    set({ message })
    if (toastTimer) clearTimeout(toastTimer)
    toastTimer = setTimeout(() => set({ message: null }), 3200)
  },
  celebrate: (xp) => {
    set({ xp })
    if (xpTimer) clearTimeout(xpTimer)
    xpTimer = setTimeout(() => set({ xp: null }), 1700)
  },
  clear: () => set({ message: null }),
}))

export const toast = (message: string) => useToastStore.getState().show(message)
export const celebrateXp = (xp: number) => useToastStore.getState().celebrate(xp)
