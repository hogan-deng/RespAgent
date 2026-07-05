const MODULE_URL = "http://localhost:8000"

export async function FetchJSON (url) {
  const res = await fetch(url, { headers: { 'Accept': 'application/json' } })
  if (!res.ok) {
    const msg = await res.text().catch(() => "")
    throw new Error(`HTTP ${res.status} ${res.statusText}${msg ? ` - ${msg}` : ""}`)
  }
  return res.json()
}

export async function FetchJSONL (url) {
  const res = await fetch(url, { headers: { 'Accept': 'application/json' } })
  if (!res.ok) {
    const msg = await res.text().catch(() => "")
    throw new Error(`HTTP ${res.status} ${res.statusText}${msg ? ` - ${msg}` : ""}`)
  }
  const text = await res.text()
  return text.trim().split('\n').map(line => JSON.parse(line))
}

/**
 * Run a command on the server.
 * @param {*} url The module path to the command.
 * @param {*} args Positional arguments for the command.
 * @param {*} kwargs Keyword arguments for the command.
 * @returns 
 */
export function RunCommand (url, args, kwargs) {
  return fetch(`${MODULE_URL}${url}`, { method: "POST", body: JSON.stringify({ args, kwargs }) }).then(res => {
    if (!res.ok) {
      return res.text().then(msg => {
        alert(`Error: ${msg}`)
        throw new Error(`HTTP ${res.status} ${res.statusText}${msg ? ` - ${msg}` : ""}`)
      })
    }
    return res.json()
  })
}
