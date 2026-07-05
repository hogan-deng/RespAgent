import { useEffect } from 'preact'

const COLOUR_POOL = [
  // 'orange',
  // 'amber',
  // 'yellow',
  'lime',
  'green',
  'emerald',
  'teal',
  'cyan',
  'sky',
  'blue',
  'indigo',
  'violet',
  'purple',
  'fuchsia',
]

export function getIndexedColour(colourIndex, shadeIndex) {
  const colour = COLOUR_POOL[colourIndex % COLOUR_POOL.length]
  const shade = shadeIndex !== undefined  ? 6 - (shadeIndex % 6) : 6
  return `${colour}-${shade  * 100}`
}

export function unzip(arr) {
  if (!arr || !arr.length) return [[],[]]
  return arr[0].map((_, i) => arr.map(row => row[i]))
}

export function saveToLocalStorage(key, value) {
  localStorage.setItem(key, JSON.stringify(value))
}

export function loadFromLocalStorage(key, defaultValue) {
  const item = localStorage.getItem(key)
  if (item) {
    try {
      return JSON.parse(item)
    } catch (err) {
      console.error('Failed to parse localStorage item', key, err)
      return defaultValue
    }
  }
  return defaultValue
}

/**
 * Custom hook to enable keyboard navigation (ArrowUp/ArrowDown) for a select element.
 * @param {*} ref 
 */
export function useSelectKeyboardNavigation(ref) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (
        !ref.current || 
        !['ArrowDown', 'ArrowUp'].includes(e.key)
      ) return

      e.preventDefault()
      const options = Array.from(ref.current.querySelectorAll('option'))
      const index = options.findIndex(option => option.value === ref.current.value)
      const nextIndex = e.key === 'ArrowDown' ? (index + 1) : (index - 1 + options.length)
      ref.current.value = options[nextIndex % options.length ].value
      ref.current.dispatchEvent(new Event('change', { bubbles: true }))
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [ref])
}