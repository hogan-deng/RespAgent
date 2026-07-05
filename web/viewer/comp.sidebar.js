import { html, useState, useEffect, useMemo, useRef } from 'preact'


import { ScreenResolutions, HierarchyLevel } from '../common/const.js'
import { useSelectKeyboardNavigation } from '../common/utils.js'
import { useStore } from './store.view.js'

/**
 * 
 * @param {{metadata: any, refreshMetadata: () => void }} props 
 * @returns 
 */
export const Sidebar = (props) => {  
  return html`
    <div class="flex flex-col w-full h-screen gap-2 px-2 pt-3 pb-1">
      <${ CompFileList }/>

      <div class="h-full bg-base-100 border border-gray-300 rounded px-2">
        <${CompResolution} />
        <${CompHierarchy} name="view" />

        <${CompMetaPreview} metadata=${props.metadata} />
      </div>
    </div>
  `
}

function CompFileList() {
  const selectRef = useRef(null)
  const { 
    config, 
    currentFile, 
    sortType, 
    resolution, 
    hierarchyLevel, 
    datasetScope, 
    setCurrentFile, 
    setSortType, 
    setDatasetScope,
    getAllFileList, 
  } = useStore()

  // Enable keyboard navigation for file selection
  useSelectKeyboardNavigation(selectRef)

  const fileGroupHTML = useMemo(() => {
    const nbsp = "\xA0\xA0"
    const fileNames = getAllFileList(sortType == 'hierarchy')
    return fileNames.map(({name, count}, index) => {
      const orderStr = String(index + 1).padStart(3, '0')
      const countStr = count ? `<${String(count).padStart(3, '0')}>` : ''
      return html`
        <option value="${name}">#${orderStr}${countStr}${nbsp}${name} </option>
      `
    })
  }, [config, sortType, resolution, hierarchyLevel, datasetScope])

  return html`
    <label class="floating-label grow">
      <select
        ref=${selectRef}
        class="select join-item"
        name="fileSelect"
        value=${currentFile}
        onchange=${(e) => setCurrentFile(e.target.value)}
      >
        ${fileGroupHTML}
      </select>
      <span>HTML</span>
    </label>
    <div class="join w-full">
      <select 
        class="select select-xs join-item w-48" 
        name="datasetScope" 
        value=${datasetScope} 
        onchange=${(e) => setDatasetScope(e.target.value)}
      >
        <option value="" selected>Full Dataset</option>
        <option value="sample">Sample Dataset</option>
      </select>
      <select 
        class="select select-xs join-item w-48" 
        name="fileGroupSelect" 
        value=${sortType} 
        onchange=${(e) => setSortType(e.target.value)}
      >
        <option value="" selected>Sort by Name</option>
        <option value="hierarchy">Sort by Hierarchy</option>
      </select>
    </div>
  `
}

function CompResolution() {
  const { resolutions, setResolutions} = useStore()
  const onChange = (e) => {
    const res = e.target.value
    const checked = e.target.checked

    const newSet = new Set(resolutions)
    if (checked) {
      newSet.add(res)
    } else {
      newSet.delete(res)
    }
    setResolutions(newSet)
  }

  const resolutionCheckboxHTML = useMemo(() => {
    return ScreenResolutions.map((res) => {
      const key = res.split("x")[0]
      return html`<input
        class="join-item btn btn-xs"
        type="checkbox"
        name="resolution"
        value="${res}"
        checked=${resolutions.has(res)}
        aria-label="${key}"
        onchange=${onChange}
      />`
    })
  }, [resolutions])


  return html`
    <fieldset class="fieldset">
      <legend class="fieldset-legend">Resolution</legend>
      <div class="join">${resolutionCheckboxHTML}</div>
    </fieldset>
  `
}

function CompHierarchy({ name }) {
  const { hierarchyLevel, isMetaIdVisible, setHierarchyLevel, setMetaIdVisible } = useStore()

  const radioHTML = useMemo(() => {
    const levels = Object.values(HierarchyLevel)
    return levels.map((level) => html`
      <input 
        class="join-item btn btn-xs" 
        type="radio" 
        name="${name}_filter" 
        aria-label="${level.replace(/^(\w)/, (c) => c.toUpperCase())}" 
        value="${level}" 
        checked=${hierarchyLevel === level}
        onchange=${(e) => setHierarchyLevel(e.target.value)} 
      />
    `)
  }, [hierarchyLevel])

  return html`
    <fieldset class="fieldset">
      <legend class="fieldset-legend">Hierarchy</legend>
      <div class="flex items-center justify-between">
        <div class="join">${radioHTML}</div>
        <label class="label">
          <input 
            type="checkbox" 
            class="toggle toggle-xs toggle-primary" 
            checked=${isMetaIdVisible} 
            onchange=${(e) => setMetaIdVisible(e.target.checked)} 
          />
          Show ID
        </label>
      </div>
    </fieldset>
  `
}

function CompMetaPreview({ metadata }) {
  const [reviewId, setReviewId] = useState()
  const [reviewSize, setReviewSize] = useState()
  const [reviewConfig, setReviewConfig] = useState('')
  const { resolutions, hierarchyLevel } = useStore()

  useEffect(() => {
    if (reviewSize || !resolutions.size) {
      return
    }
    // Initialize size 
    for (const size of ScreenResolutions) {
      if (resolutions.has(size)) {
        setReviewSize(size)
        break
      }
    }
  }, [reviewSize, resolutions])

  useEffect(() => {
    if (!metadata || !reviewSize) {
      setReviewId(null)
      return
    }
    const configData = metadata?.[reviewSize]?.[hierarchyLevel]?.[reviewId]
    if (!configData) {
      setReviewConfig('Drop ID to here to preview metadata')
      return
    }
    const reviewData = Object.entries(configData).reduce((acc, [key, value]) => {
      acc[key] = Array.isArray(value) ? JSON.stringify(value, null).replace(/"/g, "") : value
      return acc
    }, {})
    const reviewDataString = JSON.stringify(reviewData, null, 2)
    setReviewConfig(reviewDataString.replace(/^{\n|\s+}$/g, ''))
  }, [metadata, reviewSize, hierarchyLevel, reviewId])

  // Drag and Drop handlers
  const handleDrop = (e) => {
    e.preventDefault()
    const id = e.dataTransfer.getData("id")
    const resolution = e.dataTransfer.getData("resolution")
    if (id) {
      setReviewId(id)
    }
    if (resolution) {
      setReviewSize(resolution)
    }
  }

  const metaIdOptionsHTML = useMemo(() => {
    const itemData = metadata?.[reviewSize]?.[hierarchyLevel] || {}
    return Object.keys(itemData).map((id) => html`<option value="${id}">${id}</option>`)
  }, [hierarchyLevel, reviewSize, metadata])

  const sizeOptionsHTML = useMemo(() => {
    const sizeList = ScreenResolutions
    return sizeList.map((size) => html`<option value="${size}">${size.split('x')[0]}</option>`)
  }, [])

  return html`
    <fieldset class="fieldset">
      <legend class="fieldset-legend">Metadata 🎯</legend>
      <div 
        class="overflow-hidden rounded bg-olive-500 text-white border-3 border-dotted"
        onDrop=${handleDrop}
        onDragOver=${(e) => e.preventDefault()}
      >
        <div class="join w-full border-b-3 border-dotted border-olive-400"> 
          <select
            class="select select-xs select-ghost join-item"
            name="metaIdSelect"
            value=${reviewId}
            onchange=${(e) => setReviewId(e.target.value)}
          >
            <option value="" disabled selected>ID List</option>
            ${metaIdOptionsHTML}
          </select>
          <select 
            class="select select-xs select-ghost join-item w-24" 
            name="sizeSelect" 
            value=${reviewSize} 
            onchange=${(e) => setReviewSize(e.target.value)}
          >
            ${sizeOptionsHTML}
          </select>
        </div>
        <pre class="max-h-64 p-2 overflow-auto"><code>${reviewConfig}</code></pre>
      </div>
    </fieldset>
    `
}