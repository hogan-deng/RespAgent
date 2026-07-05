export type BoundingBox = [number, number, number, number] // (x, y, width, height)

export interface NodeElement {
  type: string
  text: string
  bboxes: BoundingBox[]
  style: Record<string, string>
  children: string[]
}

export interface LayerElement {
  bbox: BoundingBox
  style: Record<string, string>
  children: string[]
}

export interface ModuleElement {
  text: string
  bbox: BoundingBox
  leaf_texts: string[]
  leaf_signs: string[]
}

export interface PageElements {
  nodes: Record<string, NodeElement>
  layers: Record<string, LayerElement>
  modules: Record<string, ModuleElement>
}

export interface EvaluationResults {
  module_stats: Record<string, number>
  node_stats: Record<string, number>

  module_ids: Array<[string, string]>
  node_ids: Array<[string, string]>
  
  source_elements: PageElements
  generated_elements: PageElements
}

// Common Gallery Props
export type GalleryProps = {
   screenshot: string, 
   hierarchy: HierarchyLevel
   nodes: Record<string, NodeElement>,
   colour?: string
   hoveredId?: string,
}

type HierarchyLevel = 'node' | 'layer' | 'module'
export type AnnotationProps = {
  isMetaIdVisible: boolean,
  screenshots: Record<string, string>, 
  metadata: Record<string, PageElements>, 
  hierarchy: HierarchyLevel
}
export type AnnotationPageProps = {
  isMetaIdVisible: boolean,
  resolution: string,
  imageSize: [number, number],
  hierarchy: HierarchyLevel,
  elements: PageElements,
  checkedIds: Set<string>,
  hoveredId?: string,
}

export type ComparisonProps = {
  screenshots: Record<string, [string, string]>, 
  metadata: Record<string, EvaluationResults>, 
  hierarchy: HierarchyLevel 
  isMetaIdVisible: boolean
}
export type ComparisonPageProps = {
  sign: string,
  imageSize: [number, number],
  hierarchy: HierarchyLevel,
  elements: PageElements,
  moduleIds: Array<string>
  nodeIds: Array<string>
  layerIds: Array<string>
  checkedIds: Set<string>,
  hoveredId?: string,
  isMetaIdVisible: boolean
}
export type ComparisonFilterProps = {
  metadata: EvaluationResults,
  hierarchy: HierarchyLevel,
  baseCheckedIds: Set<string>,
  evalCheckedIds: Set<string>,
  changeCheckedIds: (id: [string, string]) => void,
  updateHoveredIds: (id?: [string, string]) => void,
}