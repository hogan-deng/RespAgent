import { html, useState, useMemo, useEffect } from 'preact'


import { FetchJSON } from '../common/api.js'
import { Comparison } from "../common/comp.comparison.js"

import { useStore } from './store.eval.js'
import { Sidebar } from './comp.sidebar.js'


export function App() {
  const [autoScore, setAutoScore] = useState(null)
  const [manualScore, setManualScore] = useState(null)
  const { scoreType, currentFile, directory, sidebarOpen, setSidebarOpen } = useStore()

  const metadata = useMemo(() => {
    if (scoreType === 'auto') return autoScore
    if (scoreType === 'manual') return manualScore
    return null
  }, [scoreType, autoScore, manualScore])

  const refreshAutoScore = () => {
    const fileName = currentFile.replace('.html', '.json')
    const rootPath = directory
    FetchJSON(`${rootPath}/auto_score/${fileName}`)
      .then(data => setAutoScore(data))
      .catch(err => console.error('Auto score not found:', err))
  }

  const refreshManualScore = () => {
    const fileName = currentFile.replace('.html', '.json')
    const rootPath = directory
    FetchJSON(`${rootPath}/manual_score/${fileName}`)
      .then(data => setManualScore(data))
      .catch(err => {
        console.warn('Manual score not found:', err)
        Promise.all([
          FetchJSON(`/metadata/${fileName}`),
          FetchJSON(`${rootPath}/metadata/${fileName}`)
        ]).then(([sourceMeta, generatedMeta]) => {
          // Merge global and local metadata, giving precedence to local value
          const mergedMeta = Object.fromEntries(
            Object.keys(sourceMeta).map((resolution) => [
              resolution,
              {
                source_elements: sourceMeta[resolution],
                generated_elements: generatedMeta[resolution],
              },
            ])
          )
          console.log('Merged metadata for manual score fallback:', mergedMeta)
          setManualScore(mergedMeta)
        }).catch(metaErr => console.error('Metadata not found:', metaErr))
      })
  }

  const refreshScore = () => {
    if (!currentFile) return

    refreshAutoScore()
    refreshManualScore()
  }
  useEffect(refreshScore, [currentFile, directory])

  return html`
  <div class="drawer drawer-end drawer-open">
    <input id="drawer-handle" type="checkbox" class="drawer-toggle" onChange=${() => setSidebarOpen(!sidebarOpen)} />
    <div class="drawer-content relative">
      <!-- Page content here -->
      <${EvalContent} metadata=${metadata} />
    </div>

    <div class="drawer-side overflow-visible">
      <div class="flex flex-col items-start min-h-full overflow-x-hidden bg-base-200 ${sidebarOpen ? 'w-2xs' : 'w-0'}">
        <!-- Sidebar content here -->
         <${Sidebar} metadata=${metadata} refreshAutoScore=${refreshAutoScore} refreshManualScore=${refreshManualScore} />
      </div>

      <!-- button to open/close drawer -->
      <label for="drawer-handle" class="absolute bottom-0 right-full p-1 pr-0 pb-2 rounded-tl-lg bg-base-200 border-t-1 border-l-1 border-gray-200">
        <span class="badge badge-soft badge-primary"> ${currentFile} </span>
      </label>
    </div>
  </div>`
}

function EvalContent({ metadata }) {
  const { currentFile, directory, resolutions, hierarchyLevel, isMetaIdVisible } = useStore()

  const screenshots = useMemo(() => {
    const imageName = currentFile.replace('.html', '.png')
    return Object.fromEntries(resolutions.values().map(resolution => [
      resolution, 
      [
        `/screenshots/${resolution}/${imageName}`,
        `${directory}/screenshots/${resolution}/${imageName}`
      ]
    ]))
  }, [currentFile, directory, resolutions])

  return html`
  <${Comparison} 
    isMetaIdVisible=${isMetaIdVisible} 
    screenshots=${screenshots} 
    metadata=${metadata} 
    hierarchy=${hierarchyLevel} 
  />`
}