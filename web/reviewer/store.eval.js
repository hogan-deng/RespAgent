import { useState, useEffect } from 'preact'

import { createStore } from '../common/store.js'

// Create a Zustand store instance for the evaluation module
const store = createStore('evaluation_store', (cacheStore, set) => ({
  directory: cacheStore.directory || '',
  setDirectory: (dir) => set({ directory: dir }),
  scoreType: cacheStore.scoreType || 'auto',
  setScoreType: (type) => set({ scoreType: type }),
}))

// Custom hook to use the evaluation store in components
export function useStore(selector = (s) => s) {
  const [state, setState] = useState(selector(store.getState()))
  useEffect(() => store.subscribe(() => setState(selector(store.getState()))), [])
  return state
}