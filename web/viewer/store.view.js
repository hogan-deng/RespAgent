import { useState, useEffect } from 'preact'

import { createStore } from '../common/store.js'

// Create a Zustand store instance for the viewer module
const store = createStore('viewer_store', (cacheStore, set) => ({
  //
}))

// Custom hook to use the viewer store in components
export function useStore(selector = (s) => s) {
  const [state, setState] = useState(selector(store.getState()))
  useEffect(() => store.subscribe(() => setState(selector(store.getState()))), [])
  return state
}