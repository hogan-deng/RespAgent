import { html, useState, useMemo, useEffect } from 'preact'

import { HierarchyLevel } from './const.js'
import { unzip, getIndexedColour } from './utils.js'
import { Gallery } from './comp.gallery.js'


/**
 * 
 * @typedef {import('./comp.types.js').ComparisonProps} ComparisonProps
 * @param {ComparisonProps} props 
 */
export function Comparison(props) {
  const [baseHoveredId, setBaseHoveredId] = useState()
  const [evalHoveredId, setEvalHoveredId] = useState()
  const [baseCheckedIds, setBaseCheckedIds] = useState(new Set())
  const [evalCheckedIds, setEvalCheckedIds] = useState(new Set())

  const { screenshots, metadata, hierarchy, isMetaIdVisible } = props

  const elementIds = useMemo(() => {
    if (!props.metadata || !screenshots) return [new Set(), new Set()]

    const baseIds = new Set()
    const evalIds = new Set()
    for (const size of Object.keys(screenshots)) {
      const data = props.metadata?.[size]
      if (props.hierarchy === HierarchyLevel.MODULE) {
        Object.keys(data?.source_elements?.modules || {}).forEach((id) => baseIds.add(id))
        Object.keys(data?.generated_elements?.modules || {}).forEach((id) => evalIds.add(id))
      } else if (props.hierarchy === HierarchyLevel.NODE) {
        Object.keys(data?.source_elements?.nodes || {}).forEach((id) => baseIds.add(id))
        Object.keys(data?.generated_elements?.nodes || {}).forEach((id) => evalIds.add(id))
      } else if (props.hierarchy === HierarchyLevel.LAYER) {
        Object.keys(data?.source_elements?.layers || {}).forEach((id) => baseIds.add(id))
        Object.keys(data?.generated_elements?.layers || {}).forEach((id) => evalIds.add(id))
      }
    }
    return [baseIds, evalIds]
  }, [metadata, screenshots, hierarchy])

  useEffect(() => {
    setBaseCheckedIds(elementIds[0])
    setEvalCheckedIds(elementIds[1])
  }, [elementIds])

  const changeCheckedIds = ([baseId, evalId]) => {
    if (baseId) {
      setBaseCheckedIds((prev) => {
        const newSet = new Set(prev)
        if (newSet.has(baseId)) {
          newSet.delete(baseId)
        } else {
          newSet.add(baseId)
        }
        return newSet
      })
    }
    if (evalId) {
      setEvalCheckedIds((prev) => {
        const newSet = new Set(prev)
        if (newSet.has(evalId)) {
          newSet.delete(evalId)
        } else {
          newSet.add(evalId)
        }
        return newSet
      })
    }
  }

  const updateHoveredIds = (ids) => {
    if (!ids) {
      setBaseHoveredId(undefined)
      setEvalHoveredId(undefined)
    } else {
      const [baseId, evalId] = ids
      setBaseHoveredId(baseId)
      setEvalHoveredId(evalId)
    }
  }
  
  const galleryHTML = useMemo(() => {
    if (!metadata || !Object.keys(metadata).length) {
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
    const itemHTML =  Array.from(resolutions).sort(sortFunc).map((size) => {
      const data = metadata?.[size] || {}
      const [baseModuleIds, evalModuleIds] = unzip(data.module_ids)
      const [baseNodeIds, evalNodeIds] = unzip(data.node_ids)
      const [baseLayerIds, evalLayerIds] = unzip(data.layer_ids)

      const baseRender = (imageSize) => html`
        <${ComparisonPage}
          key=${size}
          sign="left"
          imageSize=${imageSize}
          hierarchy=${hierarchy}
          elements=${data.source_elements}
          moduleIds=${baseModuleIds}
          nodeIds=${baseNodeIds}
          layerIds=${baseLayerIds}
          checkedIds=${baseCheckedIds}
          hoveredId=${baseHoveredId}
          isMetaIdVisible=${isMetaIdVisible}
        />`
      const evalRender = (imageSize) => html`
        <${ComparisonPage}
          key=${size}
          sign="right"
          imageSize=${imageSize}
          hierarchy=${hierarchy}
          elements=${data.generated_elements}
          moduleIds=${evalModuleIds}
          nodeIds=${evalNodeIds}
          layerIds=${evalLayerIds}
          checkedIds=${evalCheckedIds}
          hoveredId=${evalHoveredId}
          isMetaIdVisible=${isMetaIdVisible}
        />`
      return html`
        <div class="flex items-start mb-4 gap-1">
          <${Gallery} imageUrl=${screenshots?.[size][0]} children=${baseRender} />
          <${ComparisonFilter} 
            hierarchy=${hierarchy} 
            metadata=${data} 
            baseCheckedIds=${baseCheckedIds} 
            evalCheckedIds=${evalCheckedIds} 
            changeCheckedIds=${changeCheckedIds} 
            updateHoveredIds=${updateHoveredIds} 
          />
          <${Gallery} imageUrl=${screenshots?.[size][1]} children=${evalRender} />
        </div>
      `
    })
    return html`
      <div class="flex flex-col items-start h-screen overflow-y-scroll">
        ${itemHTML}
      </div>
    `
  }, [metadata, screenshots, hierarchy, baseCheckedIds, evalCheckedIds, baseHoveredId, evalHoveredId, isMetaIdVisible])

  return galleryHTML
}


/**
 * @typedef {import('./comp.types.js').ComparisonPageProps} ComparisonPageProps
 * @param {ComparisonPageProps} props 
 */
function ComparisonPage(props) {
  const modulesHTML = useMemo(() => {
    const [imgW, imgH] = props.imageSize
    if (imgW && imgH && props.moduleIds && props.elements.modules) {
      const matchedBoxes = []
      const unmatchedBoxes = []
      const idToIndexMap = Object.fromEntries(props.moduleIds.map((id, idx) => [id, idx]))
      
      Object.entries(props.elements.modules).forEach(([moduleId, item]) => {
        const animateClass = props.hoveredId === moduleId ? 'animate-[min-ping_1s_ease-in-out_infinite]' : ''
        if (props.moduleIds.includes(moduleId)) {
          const colour = getIndexedColour(idToIndexMap[moduleId])
          const defaultClass = props.checkedIds?.has(moduleId) ? `border border-2 border-${colour} bg-${colour}/30 bg-[repeating-linear-gradient(90deg,#0000_0_9px,#aaa6_9px_10px)]` : ''
          matchedBoxes.push(getBoxHTML(props.sign, props.isMetaIdVisible, imgW, imgH, moduleId, item, `${defaultClass} ${animateClass}`))
        } else {
          const defaultClass = props.checkedIds?.has(moduleId) ? 'border border-2 border-red-500/80 bg-red-500/80' : ''
          unmatchedBoxes.push(getBoxHTML(props.sign, props.isMetaIdVisible, imgW, imgH, moduleId, item, `${defaultClass} ${animateClass}`)) 
        }
      })
      return [...matchedBoxes, ...unmatchedBoxes]
    }
    return null
  }, [props.sign, props.isMetaIdVisible, props.imageSize, props.moduleIds, props.elements.modules, props.checkedIds, props.hoveredId])

  const nodesHTML = useMemo(() => {
    const [imgW, imgH] = props.imageSize
    if (imgW && imgH && props.nodeIds && props.elements.nodes) {
      const matchedBoxes = []
      const unmatchedBoxes = []
      const idToIndexMap = Object.fromEntries(props.nodeIds.map((id, idx) => [id, idx]))

      Object.entries(props.elements.nodes).forEach(([nodeId, item]) => {
        const animateClass = props.hoveredId === nodeId ? 'animate-[min-ping_1s_ease-in-out_infinite]' : ''
        if (props.nodeIds.includes(nodeId)) {
          const defaultClass = props.checkedIds?.has(nodeId) ? `bg-${getIndexedColour(idToIndexMap[nodeId])}/50  bg-[repeating-linear-gradient(45deg,#0000_0_9px,#aaa6_9px_10px)]` : ''
          matchedBoxes.push(getBoxesHTML(props.sign, props.isMetaIdVisible, imgW, imgH, nodeId, item, `${defaultClass} ${animateClass}`))
        } else {
          const defaultClass = props.checkedIds?.has(nodeId) ? 'bg-red-500/80' : ''
          unmatchedBoxes.push(getBoxesHTML(props.sign, props.isMetaIdVisible, imgW, imgH, nodeId, item, `${defaultClass} ${animateClass}`)) 
        }
      })
      
      return [...matchedBoxes, ...unmatchedBoxes]
    }
    return null
  }, [props.sign, props.isMetaIdVisible, props.imageSize, props.moduleIds, props.nodeIds, props.elements, props.hoveredId])


  return props.hierarchy === HierarchyLevel.MODULE ? modulesHTML : 
  props.hierarchy === HierarchyLevel.NODE ? nodesHTML : null
}

/**
 * @typedef {import('./comp.types.js').ComparisonFilterProps} ComparisonFilterProps
 * @param {ComparisonFilterProps} props
 * @returns 
 */
function ComparisonFilter(props) {
  const filterHTML = useMemo(() => {
    let matchedIds = []
    let unmatchedIds = []
    if (props.hierarchy === HierarchyLevel.MODULE) { 
      const [baseIds, evalIds] = unzip(props.metadata.module_ids)

      matchedIds = props.metadata.module_ids || []
      unmatchedIds = [
        ...Object.keys(props.metadata.source_elements.modules).filter(id => {
          return !baseIds.includes(id)
        }).map(id => [id, null]),
        ...Object.keys(props.metadata.generated_elements.modules).filter(id => {
          return !evalIds.includes(id)
        }).map(id => [null, id])
      ]
    } else if (props.hierarchy === HierarchyLevel.NODE && props.metadata.node_ids?.length) {
      const [baseIds, evalIds] = unzip(props.metadata.node_ids)

      matchedIds = props.metadata.node_ids
      unmatchedIds = [
        ...Object.keys(props.metadata.source_elements.nodes).filter(id => {
          return !baseIds.includes(id)
        }).map(id => [id, null]),
        ...Object.keys(props.metadata.generated_elements.nodes).filter(id => {
          return !evalIds.includes(id)
        }).map(id => [null, id])
      ]
    } else if (props.hierarchy === HierarchyLevel.LAYER && props.metadata.layer_ids?.length) {
      const [baseIds, evalIds] = unzip(props.metadata.layer_ids)

      matchedIds = props.metadata.layer_ids
      unmatchedIds = [
        ...Object.keys(props.metadata.source_elements.layers).filter(id => {
          return !baseIds.includes(id)
        }).map(id => [id, null]),
        ...Object.keys(props.metadata.generated_elements.layers).filter(id => {
          return !evalIds.includes(id)
        }).map(id => [null, id])
      ]
    }

    const handleDragStart = (id, sign) => (e) => {
      e.dataTransfer.setData('id', id)
      e.dataTransfer.setData('sign', sign)
    }
    const matchedCheckboxes = matchedIds.map(([base_id, eval_id], index) => {
      const colour = getIndexedColour(index)
      const isChecked = props.baseCheckedIds.has(base_id) && props.evalCheckedIds.has(eval_id)
      return html`
        <label class="label text-${colour}" onmouseenter=${() => props.updateHoveredIds([base_id, eval_id])}>
          <span draggable="true" ondragstart=${handleDragStart(base_id, 'left')}>${base_id}</span>
          <input 
            type="checkbox" 
            class="checkbox checkbox-xs" 
            checked=${isChecked} 
            onchange=${() => props.changeCheckedIds([base_id, eval_id])}
          />
          <span draggable="true" ondragstart=${handleDragStart(eval_id, 'right')}>${eval_id}</span>
        </label>
      `
    })
    const unmatchedBaseCheckboxes = unmatchedIds.map(([base_id, eval_id]) => {
      const isChecked = (base_id && props.baseCheckedIds.has(base_id)) || (eval_id && props.evalCheckedIds.has(eval_id))
      return html`
        <label class="label text-red-500" onmouseenter=${() => props.updateHoveredIds([base_id, eval_id])}>
          <span draggable="true" ondragstart=${handleDragStart(base_id, 'left')}>${base_id || '____'}</span>
          <input 
            type="checkbox" 
            class="checkbox checkbox-xs" 
            checked=${isChecked} 
            onchange=${() => props.changeCheckedIds([base_id, eval_id])}
          />
          <span draggable="true" ondragstart=${handleDragStart(eval_id, 'right')}>${eval_id || '____'}</span>
        </label>
      `
    })
    return html`${matchedCheckboxes}${unmatchedBaseCheckboxes}`
  }, [props.hierarchy, props.metadata, props.baseCheckedIds, props.evalCheckedIds, props.changeCheckedIds, props.updateHoveredIds])

  return html`
    <div class="sticky top-0 w-18 shrink-0 text-xs z-1 bg-white" onmouseleave=${() => props.updateHoveredIds()}>
      <div class="pt-2 h-6 text-center font-bold">
        ${props.hierarchy}
      </div>
      <div class="flex flex-col gap-1 max-h-[calc(100vh-2rem)] pl-0.5 min-scrollbar overflow-x-hidden">${filterHTML}</div>
    </div>
  `
}

/**
 * 
 * @param {string} sign 
 * @param {number} imgW 
 * @param {number} imgH 
 * @param {string} id 
 * @param {{bbox: [number, number, number, number], text: string}} item 
 * @param {string} extraClass 
 * @returns 
 */
function getBoxHTML(sign, isMetaIdVisible, imgW, imgH, id, item, extraClass) {
  const [x, y, w, h] = item.bbox
  const [left, top, width, height] = [x / imgW, y / imgH, w / imgW, h / imgH].map((v) => v * 100)
  const bgColourClass = extraClass.match(/bg-\S+/)?.[0]
  const idLabel = isMetaIdVisible && bgColourClass ? html`<span class="align-top text-xs ${bgColourClass} text-white p-x-1">${id}</span>` : ''
  return html`
    <span
      class="absolute ${extraClass}"
      style="left: ${left}%; top: ${top}%; width: ${width}%; height: ${height}%;"
      title="#${id}:${item.text}"
      data-meta-id="${id}"
      draggable="true"
      ondragstart=${(e) => {
        e.dataTransfer.setData('id', id)
        e.dataTransfer.setData('sign', sign)
      }}
    >${idLabel}</span>`
}

function getBoxesHTML(sign, isMetaIdVisible, imgW, imgH, id, item, extraClass) {
  return item.bboxes.map((bbox, index) => {
    const [x, y, w, h] = bbox
    const [left, top, width, height] = [x / imgW, y / imgH, w / imgW, h / imgH].map((v) => v * 100)
    const bgColourClass = extraClass.match(/bg-\S+/)?.[0]
    const idLabel = index == 0 && isMetaIdVisible && bgColourClass ? html`<span class="align-top text-xs ${bgColourClass} text-white p-x-1">${id}</span>` : ''
    return html`
      <span
        class="absolute ${extraClass}"
        style="left: ${left}%; top: ${top}%; width: ${width}%; height: ${height}%;"
        title="#${id}:${item.text}"
        data-meta-id="${id}"
        draggable="true"
        ondragstart=${(e) => {
          e.dataTransfer.setData('id', id)
          e.dataTransfer.setData('sign', sign)
        }}
      >${idLabel}</span>`
  })
}