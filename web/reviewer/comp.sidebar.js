import { html, useState, useMemo, useRef, useEffect } from 'preact'


import { RunCommand } from '../common/api.js'
import { ScreenResolutions, HierarchyLevel } from '../common/const.js'
import { useSelectKeyboardNavigation } from '../common/utils.js'
import { useStore } from './store.eval.js'

const parseScore = (scoreData) => {
  if (!scoreData) return []
  const scoreList = Object.entries(scoreData).filter(([key, data]) => {
    return key.match(/^\d+x\d+$/) && data['module_stats'] && data['node_stats']
  }).map(([key, data]) => {
    const module = data['module_stats']
    const node = data['node_stats']
    if (module && node) {
      const moduleScore = module['text_score'] * 0.5 + module['shape_score'] * 0.25 + module['position_score'] * 0.25
      const nodeScore = node['iou_score'] * 0.5 + node['text_score'] * 0.25 + node['color_score'] * 0.25
      return [key, module['coverage'], moduleScore, node['coverage'], nodeScore]
    }
    return []
  })
  if (!scoreList.length) return []

  const scoreSummary = scoreList.map(([key, ...scores]) => {
    const keyShort = (key.split('x')[0] + ': ').padEnd(6, ' ')
    const scoreLine = `${keyShort}${scores.map(s => s !== undefined ? s.toFixed(2) : 'N/A').join(', ')}`
    return scoreLine
  })

  const overallScore = scoreList.reduce((acc, [key, ...scores]) => {
    if (scores.length === 4) {
      const [moduleCov, moduleScore, nodeCov, nodeScore] = scores
      const combinedScore = moduleCov * moduleScore * 0.5 + nodeCov * nodeScore * 0.5
      acc += combinedScore / scoreList.length
    }
    return acc
  }, 0)
  scoreSummary.push(`Score: ${(100 * overallScore).toFixed(2)}`)

  return scoreSummary
}

/**
 * 
 * @param {{metadata: any, refreshAutoScore: () => void, refreshManualScore: () => void }} props 
 * @returns 
 */
export const Sidebar = ({ metadata, refreshAutoScore, refreshManualScore }) => {
  const { currentFile, directory, setDirectory } = useStore()

  return html`
    <div class="flex flex-col w-full h-screen gap-2 px-2 pt-3 pb-2">
      <${ CompFileList }/>

      <div class="bg-base-100 border border-gray-300 rounded px-2 grow">
        <fieldset class="fieldset">
          <legend class="fieldset-legend">Directory</legend>
          <div class="flex w-full items-center">
            <input  
              type="text" 
              class="input input-xs input-ghost" 
              placeholder="Type here" 
              value=${directory} 
              onchange=${(e) => setDirectory(e.target.value)} 
            />
          </div>
        </fieldset>

        <${CompResolution} />
        <${CompHierarchy} name="eval" />
        
        <${CompEvaluation} metadata=${metadata} refreshAutoScore=${refreshAutoScore} refreshManualScore=${refreshManualScore} />
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
    <label class="floating-label">
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
        class="select select-xs join-item flex-1" 
        name="datasetScope" 
        value=${datasetScope} 
        onchange=${(e) => setDatasetScope(e.target.value)}
      >
        <option value="" selected>Full Dataset</option>
        <option value="sample">Sample Dataset</option>
      </select>
      <select 
        class="select select-xs join-item flex-1" 
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

function CompEvaluation({ metadata, refreshAutoScore, refreshManualScore }) {
  const [scoreStr, setScoreStr] = useState('')
  const { scoreType, setScoreType } = useStore()

  useEffect(() => {
    const scoreList = parseScore(metadata)
    setScoreStr(scoreList.join('\n'))
  }, [metadata])

  return html`
    <fieldset class="fieldset">
      <legend class="fieldset-legend">Evaluation</legend>
      <div class="join w-full">
        <input 
          class="join-item btn btn-xs flex-1" 
          type="radio" 
          name="eval_type" 
          aria-label="Auto" 
          value="auto" 
          checked=${scoreType === 'auto'} 
          onchange=${(e) => setScoreType(e.target.value)} 
        />
        <input 
          class="join-item btn btn-xs flex-1" 
          type="radio" 
          name="eval_type" 
          aria-label="Manual" 
          value="manual" 
          checked=${scoreType === 'manual'} 
          onchange=${(e) => setScoreType(e.target.value)} 
        />
      </div>
    </fieldset>
    <fieldset class="fieldset">
      <legend class="fieldset-legend">Scores</legend>
      <pre class="p-2 rounded bg-olive-500 text-white text-sm"><code>${scoreStr}</code></pre>
    </fieldset>
    <${AutoScoreHandle} isShow=${scoreType === 'auto'} refreshAutoScore=${refreshAutoScore} />
    <${ManualScoreHandle} metadata=${metadata} isShow=${scoreType === 'manual'} refreshManualScore=${refreshManualScore} />
  ` 
}

function AutoScoreHandle({ isShow, refreshAutoScore }) {
  const [loading, setLoading] = useState(false)
  const { currentFile, directory } = useStore()

  const onRebuild = async () => {
    setLoading(true)
    try {
      await RunCommand('/common/web_api', ['rebuild_auto_score'], { file_name: currentFile, root_path: directory })
    } catch (err) {
      console.error('Failed to rebuild auto score:', err)
    } finally {
      setLoading(false)
      refreshAutoScore()
    }
  }

  if (!isShow) return null

  return html`
    <button class="btn btn-xs btn-primary w-full my-2" onclick=${onRebuild} disabled=${loading}>
      ${loading ? '⏳ Rebuilding...' : '🔄 Rebuild Auto Score'}
    </button>
  `

}

function ManualScoreHandle({ metadata, isShow, refreshManualScore }) {
  const [loading, setLoading] = useState(false)
  const [baseModule, setBaseModule] = useState([])
  const [evalModule, setEvalModule] = useState([])
  const [baseNode, setBaseNode] = useState([])
  const [evalNode, setEvalNode] = useState([])
  const [baseMergeModule, setBaseMergeModule] = useState([])
  const [evalMergeModule, setEvalMergeModule] = useState([])
  const { currentFile, directory } = useStore()

  useEffect(() => {
    // Clear all manual score inputs when switching files
    setBaseModule([])
    setEvalModule([])
    setBaseNode([])
    setEvalNode([])
    setBaseMergeModule([])
    setEvalMergeModule([])

  }, [currentFile])

  useEffect(() => {
    if (!metadata || !metadata['manual_config']) return

    // Pre-fill inputs based on existing metadata for easier adjustments
    const config = metadata['manual_config'] || {}
    const base_prior = config['base_prior'] || [[], [], []]
    const eval_prior = config['eval_prior'] || [[], [], []]

    setBaseModule(base_prior[0]?.sort() || [])
    setBaseNode(base_prior[1]?.sort() || [])
    setBaseMergeModule(base_prior[2].map((ids) => ids.sort().join('+')) || [])
    setEvalModule(eval_prior[0]?.sort() || [])
    setEvalNode(eval_prior[1]?.sort() || [])
    setEvalMergeModule(eval_prior[2].map((ids) => ids.sort().join('+')) || [])
  }, [metadata])

  
  const onRebuild = async () => {
    setLoading(true)
    try {
      await RunCommand('/common/web_api', ['rebuild_manual_score'], {
        file_name: currentFile,
        root_path: directory,
        base_prior: JSON.stringify([baseModule, baseNode, baseMergeModule.map(i => i.split(/\W/))]),
        eval_prior: JSON.stringify([evalModule, evalNode, evalMergeModule.map(i => i.split(/\W/))]),
      })
    } catch (err) {
      console.error('Failed to rebuild manual score:', err)
    } finally {
      setLoading(false)
      refreshManualScore()
    }
  }

  const addFromInput = (setList) => (e) => {
    if (e.key !== 'Enter') return
    const values = e.target.value.trim().split(/\s+/).filter(Boolean)
    if (!values.length) return

    setList((prev) => [...new Set([...prev, ...values])])
    e.target.value = ''
  }

  const removeAt = (setList) => (index) => {
    setList((prev) => prev.filter((_, i) => i !== index))
  }

  const addFromDrop = (kind) => (e) => {
    e.preventDefault()
    const id = e.dataTransfer.getData('id')
    const sign = e.dataTransfer.getData('sign') // "left" | "right"
    if (!id || (sign !== 'left' && sign !== 'right')) return

    const setByKindAndSide = {
      module: { left: setBaseModule, right: setEvalModule },
      node: { left: setBaseNode, right: setEvalNode },
    }

    setByKindAndSide[kind][sign]((prev) => (prev.includes(id) ? prev : [...prev, id]))
  }

  const renderBadges = (items, onRemove) =>
    items.map((item, index) => html`
      <div class="badge badge-xs badge-soft badge-primary cursor-crosshair" onclick=${() => onRemove(index)}>
        ${item}
      </div>
    `)

  const leftModuleHTML = useMemo(() => renderBadges(baseModule, removeAt(setBaseModule)), [baseModule])
  const rightModuleHTML = useMemo(() => renderBadges(evalModule, removeAt(setEvalModule)), [evalModule])
  const leftMergeHTML = useMemo(() => renderBadges(baseMergeModule, removeAt(setBaseMergeModule)), [baseMergeModule])
  const rightMergeHTML = useMemo(() => renderBadges(evalMergeModule, removeAt(setEvalMergeModule)), [evalMergeModule])
  const leftNodeHTML = useMemo(() => renderBadges(baseNode, removeAt(setBaseNode)), [baseNode])
  const rightNodeHTML = useMemo(() => renderBadges(evalNode, removeAt(setEvalNode)), [evalNode])

  if (!isShow) return null

  return html`
    <fieldset class="fieldset relative">
      <legend class="fieldset-legend">Include Modules:</legend>
      <div
        class="grid grid-cols-2 min-h-12 rounded bg-lime-600 text-white border-3 border-dotted divide-x-3 divide-dotted"
        onDrop=${addFromDrop('module')}
        onDragOver=${(e) => e.preventDefault()}
      >
        <div class="flex flex-col">
          <input type="text" placeholder="SRC: drop/type here" class="input input-xs input-ghost w-full" onKeyDown=${addFromInput(setBaseModule)} />
          <div class="flex flex-wrap gap-1 p-1">${leftModuleHTML}</div>
        </div>
        <div class="flex flex-col">
          <input type="text" placeholder="GEN: drop/type here" class="input input-xs input-ghost w-full" onKeyDown=${addFromInput(setEvalModule)} />
          <div class="flex flex-wrap gap-1 p-1">${rightModuleHTML}</div>
        </div>
      </div>
    </fieldset>

    <fieldset class="fieldset relative">
      <legend class="fieldset-legend">Exclude Nodes:</legend>
      <div
        class="grid grid-cols-2 min-h-12 rounded bg-yellow-600 text-white border-3 border-dotted divide-x-3 divide-dotted"
        onDrop=${addFromDrop('node')}
        onDragOver=${(e) => e.preventDefault()}
      >
        <div class="flex flex-col">
          <input type="text" placeholder="SRC: drop/type here" class="input input-xs input-ghost w-full" onKeyDown=${addFromInput(setBaseNode)} />
          <div class="flex flex-wrap gap-1 p-1">${leftNodeHTML}</div>
        </div>
        <div class="flex flex-col">
          <input type="text" placeholder="GEN: drop/type here" class="input input-xs input-ghost w-full" onKeyDown=${addFromInput(setEvalNode)} />
          <div class="flex flex-wrap gap-1 p-1">${rightNodeHTML}</div>
        </div>
      </div>
    </fieldset>

    <fieldset class="fieldset relative">
      <legend class="fieldset-legend">Merge Modules:</legend>
      <div
        class="grid grid-cols-2 min-h-12 rounded bg-cyan-600 text-white border-3 border-dotted divide-x-3 divide-dotted"
      >
        <div class="flex flex-col">
          <input type="text" placeholder="SRC: type here" class="input input-xs input-ghost w-full" onKeyDown=${addFromInput(setBaseMergeModule)} />
          <div class="flex flex-wrap gap-1 p-1">${leftMergeHTML}</div>
        </div>
        <div class="flex flex-col">
          <input type="text" placeholder="GEN: type here" class="input input-xs input-ghost w-full" onKeyDown=${addFromInput(setEvalMergeModule)} />
          <div class="flex flex-wrap gap-1 p-1">${rightMergeHTML}</div>
        </div>
      </div>
    </fieldset>

    <button class="btn btn-xs btn-primary w-full my-2" onclick=${onRebuild} disabled=${loading}>
      ${loading ? '⏳ Rebuilding...' : '🛠 Rebuild Manual Score'}
    </button>
  `
}