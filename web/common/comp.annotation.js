import { html, useState, useMemo, useEffect } from 'preact'

import { HierarchyLevel } from './const.js'
import { Gallery } from './comp.gallery.js'


/**
 * 
 * @typedef {import('./comp.types.js').AnnotationProps} AnnotationProps
 * @param {AnnotationProps} props 
 */
export function Annotation(props) {
  const [hoveredId, setHoveredId] = useState()
  const [checkedIds, setCheckedIds] = useState(new Set())
  const { screenshots, metadata, hierarchy, isMetaIdVisible } = props

  const elementIds = useMemo(() => {
    if (!props.metadata || !screenshots) return []
    const ids = new Set()
    for (const size of Object.keys(screenshots)) {
      const data = props.metadata?.[size]
      const items = props.hierarchy === HierarchyLevel.MODULE ? data?.modules :
                    props.hierarchy === HierarchyLevel.NODE ? data?.nodes :
                    props.hierarchy === HierarchyLevel.LAYER ? data?.layers : null
      if (items) {
        Object.keys(items).forEach((id) => ids.add(id))
      }
    }
    return Array.from(ids).sort((idA, idB) => parseInt(idA, 16) - parseInt(idB, 16))
  }, [metadata, screenshots, hierarchy])

  useEffect(() => {
    setCheckedIds(new Set(elementIds))
  }, [elementIds])
  
  const toggleId = (id) => {
    const newSet = new Set(checkedIds)
    if (newSet.has(id)) {
      newSet.delete(id)
    } else {
      newSet.add(id)
    }
    setCheckedIds(newSet)
  }

  const toggleAll = () => {
    if (checkedIds.size === 0) {
      setCheckedIds(new Set(elementIds))
    } else {
      setCheckedIds(new Set())
    }
  }

  const galleryHTML = useMemo(() => {
    if (!metadata) {
      return html`
        <div class="w-full h-full flex items-center justify-center">
          <i class="mr-2 status status-info animate-bounce" />No metadata available.
        </div>
      `
    }

    const resolutions = Object.keys(screenshots || {})
    if (!resolutions.length) {
      return html`
        <div class="w-full h-full flex items-center justify-center">
          <i class="mr-2 status status-error animate-bounce" />Please select at least one resolution.
        </div>
      `
    }

    const sortFunc = (a, b) => b.split('x')[0] - a.split('x')[0]
    return Array.from(resolutions).sort(sortFunc).map((size) => {
      const elements = metadata?.[size]
      const render = (imageSize) => html`
        <${AnnotationPage}
          key=${size}
          isMetaIdVisible=${isMetaIdVisible}
          resolution=${size}
          imageSize=${imageSize}
          elements=${elements}
          hierarchy=${hierarchy}
          checkedIds=${checkedIds}
          hoveredId=${hoveredId}
        />
      `
      return html`<${Gallery} imageUrl=${screenshots?.[size]} children=${render} />`
    })
  }, [metadata, screenshots, hierarchy, elementIds, checkedIds, hoveredId, isMetaIdVisible])

  const filterHTML = useMemo(() => {
    const handleDragStart = (event) => {
      const metaId = event.target.getAttribute('data-meta-id')
      if (metaId) {
        event.dataTransfer.setData('id', metaId)
      }
    }
    return elementIds.map((id) => html`
      <label class="label" draggable="true" data-meta-id=${id} ondragstart=${handleDragStart} onmouseenter=${() => setHoveredId(id)}>
        <input 
          type="checkbox" 
          class="checkbox checkbox-xs" 
          checked=${checkedIds.has(id)} 
          onchange=${() => toggleId(id)}
        />
          ${id}
      </label>
    `)
  }, [elementIds, checkedIds])

  return html`
    <div class="flex items-start h-screen overflow-y-scroll">
      <div class="sticky top-0 w-12 h-full shrink-0 text-xs z-1 bg-white" onmouseleave=${() => setHoveredId(undefined)}>
        <div class="pt-2 h-11 text-center font-bold">${props.hierarchy}
          <input class="toggle toggle-xs" type="checkbox" checked=${checkedIds.size !== 0} onchange=${() => toggleAll()} />
        </div>
        <div class="flex flex-col gap-1 h-[calc(100vh-3rem)] pl-0.5 min-scrollbar">${filterHTML}</div>
      </div>

      ${galleryHTML}
    </div>
  `
}


/**
 * @typedef {import('./comp.types.js').AnnotationPageProps} AnnotationPageProps
 * @param {AnnotationPageProps} props 
 */
function AnnotationPage(props) {

  // Set data to drag event
  const handleDragStart = (event) => {
    const metaId = event.target.getAttribute('data-meta-id')
    if (metaId) {
      event.dataTransfer.setData('id', metaId)
    }
    if (props.resolution) {
      event.dataTransfer.setData('resolution', props.resolution)
    }
  }

  const modulesHTML = useMemo(() => {
    if (props.hierarchy !== HierarchyLevel.MODULE) return null

    const [imgW, imgH] = props.imageSize
    if (imgW && imgH && props.elements.modules) {
      return Object.entries(props.elements.modules).map(([moduleId, item]) => {
        const [x, y, w, h] = item.bbox
        const [left, top, width, height] = [x / imgW, y / imgH, w / imgW, h / imgH].map((v) => v * 100)
        const animateClass = props.hoveredId === moduleId ? 'animate-[min-ping_1s_ease-in-out_infinite]' : ''
        const defaultClass = props.checkedIds.has(moduleId) ?  'border border-green-500 bg-green-500/30 bg-[repeating-linear-gradient(90deg,#0000_0_9px,#aaa6_9px_10px)]' : ''
        const idLabel = props.checkedIds.has(moduleId) && props.isMetaIdVisible ? html`<span class="align-top text-xs bg-green-500 text-white p-x-1">${moduleId}</span>` : ''
        return html`
          <span
            class="absolute ${animateClass} ${defaultClass}"
            style="left: ${left}%; top: ${top}%; width: ${width}%; height: ${height}%;"
            title="#${moduleId}:${item.text}"
            data-meta-id="${moduleId}"
            draggable="true"
            ondragstart=${handleDragStart}
          >${idLabel}</span>`
      })
    }
    return null
  }, [props.imageSize, props.checkedIds, props.hierarchy, props.elements.modules, props.hoveredId, props.isMetaIdVisible])

  const nodesHTML = useMemo(() => {
    if (props.hierarchy !== HierarchyLevel.NODE) return null

    const [imgW, imgH] = props.imageSize
    if (imgW && imgH && props.elements.nodes) {
      return Object.entries(props.elements.nodes).map(([nodeId, item]) => {
        const boxesHTML = item.bboxes.map((bbox, boxIdx) => {
          const [cx, cy, cw, ch] = bbox
          const [cleft, ctop, cwidth, cheight] = [cx / imgW, cy / imgH, cw / imgW, ch / imgH].map((v) => v * 100)
          const animateClass = props.hoveredId === nodeId ? 'animate-[min-ping_1s_ease-in-out_infinite]' : ''
          const defaultClass = props.checkedIds.has(nodeId) ?  'bg-green-500/30 bg-[repeating-linear-gradient(45deg,#0000_0_9px,#aaa6_9px_10px)]' : ''
          const idLabel = props.checkedIds.has(nodeId) && props.isMetaIdVisible && boxIdx === 0 ? html`<span class="align-top text-xs bg-green-500 text-white p-x-1">${nodeId}</span>` : ''
          return html`
            <span
              class="absolute ${animateClass} ${defaultClass}"
              style="left: ${cleft}%; top: ${ctop}%; width: ${cwidth}%; height: ${cheight}%;"
              title="#${nodeId}:${item.text}"
              data-meta-id="${nodeId}"
              draggable="true"
              ondragstart=${handleDragStart}
            >${idLabel}</span>`
        })
        return boxesHTML
      })
    }
  }, [props.imageSize, props.checkedIds, props.hierarchy, props.elements.nodes, props.hoveredId, props.isMetaIdVisible])
  
  const layersHTML = useMemo(() => {
    if (props.hierarchy !== HierarchyLevel.LAYER) return null

    const [imgW, imgH] = props.imageSize
    if (imgW && imgH && props.elements.layers) {
      return Object.entries(props.elements.layers).map(([layerId, item]) => {
        const [x, y, w, h] = item.bbox
        const [left, top, width, height] = [x / imgW, y / imgH, w / imgW, h / imgH].map((v) => v * 100)
        const animateClass = props.hoveredId === layerId ? 'animate-[min-ping_1s_ease-in-out_infinite]' : ''
        const defaultClass = props.checkedIds.has(layerId) ?  'border border-green-500 border-2' : ''
        const idLabel = props.checkedIds.has(layerId) && props.isMetaIdVisible ? html`<span class="align-top text-xs bg-green-500 text-white p-x-1">${layerId}</span>` : ''
        return html`
          <span
            class="absolute ${animateClass} ${defaultClass}"
            style="left: ${left}%; top: ${top}%; width: ${width}%; height: ${height}%;"
            title="${layerId}:"
            data-meta-id="${layerId}"
            draggable="true"
            ondragstart=${handleDragStart}
          >${idLabel}</span>`
      })
    }
  }, [props.imageSize, props.checkedIds, props.hierarchy, props.elements.layers, props.hoveredId, props.isMetaIdVisible])

  return props.hierarchy == HierarchyLevel.MODULE ? modulesHTML :
        props.hierarchy == HierarchyLevel.NODE ? nodesHTML :
        props.hierarchy == HierarchyLevel.LAYER ? layersHTML : null
}