import { html, useState, useMemo, useEffect } from 'preact'


import { FetchJSON } from '../common/api.js'
import { Annotation } from "../common/comp.annotation.js"

import { useStore } from './store.view.js'
import { Sidebar } from './comp.sidebar.js'
  

export function App() {
  const [metadata, setMetadata] = useState(null)
  const { currentFile, sidebarOpen, setSidebarOpen } = useStore()

  useEffect(() => {
    if (currentFile) {
      setMetadata(null) // clear metadata on file or dataset change
      refreshViewMetadata() // fetch new metadata
    }
  }, [currentFile])
  
  const refreshViewMetadata = async () => {
    const data = await FetchJSON(`/metadata/` + currentFile.replace('.html', '.json'))
    setMetadata(data)
  }
  
  return html`
  <div class="drawer drawer-end drawer-open">
    <input id="drawer-handle" type="checkbox" class="drawer-toggle" onChange=${() => setSidebarOpen(!sidebarOpen)} />
    <div class="drawer-content relative">
      <!-- Page content here -->
      <${ViewContent} metadata=${metadata} />
    </div>

    <div class="drawer-side overflow-visible">
      <div class="flex flex-col items-start min-h-full overflow-x-hidden bg-base-200 ${sidebarOpen ? 'w-2xs' : 'w-0'}">
        <!-- Sidebar content here -->
        <${Sidebar} metadata=${metadata} refreshMetadata=${refreshViewMetadata} />
      </div>

      <!-- button to open/close drawer -->
      <label for="drawer-handle" class="absolute bottom-0 right-full p-1 pr-0 pb-2 rounded-tl-lg bg-base-200 border-t-1 border-l-1 border-gray-200">
        <span class="badge badge-soft badge-primary"> ${currentFile}</span>
      </label>
    </div>
  </div>`
}


function ViewContent(props) {
  const { currentFile, resolutions, hierarchyLevel, isMetaIdVisible } = useStore()
  const screenshots = useMemo(() => {
    return Object.fromEntries(resolutions.values().map(resolution => [
      resolution,
      `/screenshots/${resolution}/` + currentFile.replace('.html', '.png')
    ]))
  }, [currentFile, resolutions])

  return html`<${Annotation} isMetaIdVisible=${isMetaIdVisible} screenshots=${screenshots} metadata=${props.metadata} hierarchy=${hierarchyLevel} />`
}