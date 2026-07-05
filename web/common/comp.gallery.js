import { html, useState } from 'preact'

/**
 * @typedef {Object} GalleryProps
 * @property {string} imageUrl
 * @property {(imageSize: number[]) => preact.JSX.Element} children
 */

/**
 * Gallery component to display image with annotations/comparisons
 * @param {GalleryProps} props 
 * @returns 
 */
export function Gallery({ imageUrl, children }) {
  const [imageSize, setImageSize] = useState([])

  return html` 
    <span
      class="relative border border-gray-300"
    >
      <img
        alt="Screenshot Image"
        src="${imageUrl}"
        onload=${(e) => setImageSize([e.target.naturalWidth, e.target.naturalHeight])}
      />
      ${children?.(imageSize)}
    </span>
    `
}