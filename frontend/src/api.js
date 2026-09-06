const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function parseResponse(response) {
  if (response.ok) {
    return response.json()
  }

  let detail = 'Request failed'

  try {
    const body = await response.json()

    if (typeof body.detail === 'string') {
      detail = body.detail
    }
  } catch {
    // Keep fallback message when backend does not return JSON.
  }

  const error = new Error(detail)
  error.status = response.status
  throw error
}

export async function getNetworkSummary() {
  const response = await fetch(`${API_BASE_URL}/network/summary`)
  return parseResponse(response)
}

export async function getGridActivity(gridId) {
  const response = await fetch(`${API_BASE_URL}/network/grid/${gridId}`)
  return parseResponse(response)
}

export async function getHotspots(limit = 10) {
  const response = await fetch(
    `${API_BASE_URL}/network/hotspots?limit=${limit}`
  )

  return parseResponse(response)
}

export async function getAlerts(limit = 10, severity = '') {
  const params = new URLSearchParams({
    limit: String(limit),
  })

  if (severity) {
    params.set('severity', severity)
  }

  const response = await fetch(
    `${API_BASE_URL}/network/alerts?${params.toString()}`
  )

  return parseResponse(response)
}
export async function predictRisk(features) {
  const response = await fetch(
    `${API_BASE_URL}/network/predict-risk`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(features),
    }
  )

  return parseResponse(response)
}

export { API_BASE_URL }