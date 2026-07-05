import { createStore as buildStore } from 'zustand'

import { FetchJSON } from './api.js'
import { ScreenResolutions, HierarchyLevel } from './const.js'
import { saveToLocalStorage, loadFromLocalStorage } from './utils.js'

/**
 * Creates a Zustand store with persistence to localStorage and keyboard navigation for file selection.
 * @param {*} store_key 
 * @returns 
 */
export function createStore(store_key, customState = () => ({})) {
  // Initialize store from localStorage
  const cacheStore = loadFromLocalStorage(store_key, {})

  const store = buildStore((set, get) => {
    return {
      config: {}, // to be loaded from /config.json

      sidebarOpen: cacheStore.sidebarOpen ?? true,
      isMetaIdVisible: cacheStore.isMetaIdVisible ?? true,
      currentFile:  cacheStore.currentFile || '',
      sortType: cacheStore.sortType || '',
      datasetScope: cacheStore.datasetScope || '',
      hierarchyLevel: cacheStore.hierarchyLevel || HierarchyLevel.MODULE,
      resolutions: new Set(cacheStore.resolutions || ScreenResolutions),

      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
      setMetaIdVisible: (isMetaIdVisible) => set({ isMetaIdVisible }),
      setCurrentFile: (currentFile) => set({ currentFile }),
      setSortType: (sortType) => set({ sortType }),
      setDatasetScope: (datasetScope) => set({ datasetScope }),
      setHierarchyLevel: (hierarchyLevel) => set({ hierarchyLevel }),
      setResolutions: (resolutions) => set({ resolutions }),

      getAllFileList: (sortByHierarchy = false) => {
        const { config, datasetScope, resolutions, hierarchyLevel } = get()
        const [resolution] = resolutions
        const nameSortKey = (name) => {
          const parts = name.match(/([^\d]*)(\d+)/)
          return parts ? [parts[1], parseInt(parts[2])] : [name]
        }

        let names = config.html || []
        if (sortByHierarchy && names.length && resolution && hierarchyLevel) {
          const weights = config[resolution][hierarchyLevel] || []
          const paired = names.map((name, index) => ({ name, count: weights[index] || 0 }))
          names = paired.sort((a, b) => {
            if (b.count !== a.count) return a.count - b.count // sort by count desc
            const aKey = nameSortKey(a.name)
            const bKey = nameSortKey(b.name)
            // shorter keys first, then lexicographically
            if (aKey.length != bKey.length) return aKey.length - bKey.length 
            // compare each part of the key
            for (let i = 0; i < aKey.length; i++) {
              if (aKey[i] !== bKey[i]) return aKey[i] < bKey[i] ? -1 : 1
            }
            return 0
          })
        } else {
          names = names.map((name) => ({ name, count: 0 }))
        }

        if (datasetScope === 'sample') {
          const sampleSet = new Set(config.samples || [])
          names = names.filter(({ name }) => sampleSet.has(name))
        }

        return names
      },

      // Spread in any extra state and actions defined by the caller
      ...customState(cacheStore, set, get),
    }
  })

  // Load config and initialize store state
  FetchJSON('/config.json').then((config) => {
    const currentFile = store.getState().currentFile || config.html[0]
    store.setState({ currentFile, config })
  })

  // Subscribe to store changes to persist to localStorage
  store.subscribe(async (state, prev) => {
    const { currentFile, currentGroup } = state
    if (prev && currentGroup !== prev.currentGroup) {
      const fileNames = state.config[currentGroup] || []
      if (!fileNames.includes(currentFile)) {
        store.setState({ currentFile: fileNames[0] || '' }) // set to first file in new group
      }
    }

    // Persist to localStorage
    const saveState = { ...state, resolutions: Array.from(state.resolutions) } // convert Set to Array for storage
    delete saveState.config // don't persist config to localStorage
    saveToLocalStorage(store_key, saveState)
  })

  return store
}