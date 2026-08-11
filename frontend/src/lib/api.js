/**
 * @typedef {'debug'|'info'|'warn'|'error'|'critical'} Severity
 *
 * @typedef {object} SignalEvent
 * @property {number} id
 * @property {string} source
 * @property {string} title
 * @property {string|null} message
 * @property {Severity} severity
 * @property {string[]} tags
 * @property {Record<string, unknown>|null} metadata
 * @property {string|null} link
 * @property {string} received_at
 * @property {string|null} read_at
 *
 * @typedef {object} EventPage
 * @property {SignalEvent[]} events
 * @property {number|null} next_before
 * @property {number} unread_count
 */

const TOKEN_KEY = 'gjallar.adminToken'

/** @returns {string} */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

/** @param {string} token */
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

/**
 * @param {string} path
 * @param {RequestInit} [options]
 * @returns {Promise<any>}
 */
async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${getToken()}`,
    },
  })

  if (!response.ok) {
    const message =
      response.status === 401
        ? 'Unauthorized. Check your admin token.'
        : `Request failed: ${response.status} ${response.statusText}`

    // Attach the status so callers can branch on it (409 already-configured,
    // 403 remote setup refused) instead of parsing the message text.
    const failure = /** @type {Error & {status?: number}} */ (new Error(message))
    failure.status = response.status
    throw failure
  }

  // 204 means success with no body — calling .json() on it would throw.
  if (response.status === 204) return null

  return response.json()
}

/**
 * @param {object} [filters]
 * @param {number|null} [filters.before]
 * @param {Severity|''} [filters.severity]
 * @param {string} [filters.tag]
 * @param {string} [filters.q]
 * @param {boolean} [filters.unread]
 * @param {number} [filters.limit]
 * @returns {Promise<EventPage>}
 */
export function fetchEvents({ before, severity, tag, q, unread, limit = 50 } = {}) {
  const params = new URLSearchParams()

  params.set('limit', String(limit))
  if (before) params.set('before', String(before))
  if (severity) params.set('severity', severity)
  if (tag) params.set('tag', tag)
  if (q) params.set('q', q)
  if (unread) params.set('unread', 'true')

  return request(`/api/events?${params}`)
}

/**
 * @typedef {object} Source
 * @property {number} id
 * @property {string} name
 * @property {string|null} description
 * @property {string} created_at
 * @property {string|null} last_seen_at
 * @property {boolean} revoked
 */

/** @returns {Promise<Source[]>} */
export function fetchSources() {
  return request('/api/sources')
}

/** @param {number} id */
export function revokeSource(id) {
  return request(`/api/sources/${id}/revoke`, { method: 'POST' })
}

/** @param {number} id */
export function deleteSource(id) {
  return request(`/api/sources/${id}`, { method: 'DELETE' })
}

/** @param {number} id */
export function deleteEvent(id) {
  return request(`/api/events/${id}`, { method: 'DELETE' })
}

/**
 * Delete many events at once.
 * @param {number[]} ids
 * @returns {Promise<{deleted: number}>}
 */
export function deleteEvents(ids) {
  return request('/api/events/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  })
}

/** @param {number} id */
export function deleteHeartbeat(id) {
  return request(`/api/heartbeats/${id}`, { method: 'DELETE' })
}

/**
 * @param {number} id
 * @param {boolean} paused
 */
export function pauseHeartbeat(id, paused) {
  return request(`/api/heartbeats/${id}/pause?paused=${paused}`, { method: 'POST' })
}

/**
 * Whether this instance has been configured yet. Needs no authentication.
 * @returns {Promise<{configured: boolean, push_configured: boolean, source_count: number}>}
 */
export function fetchSetupStatus() {
  return request('/api/setup/status')
}

/**
 * Claim an unconfigured instance: provisions the admin token and VAPID keys.
 * @returns {Promise<{admin_token: string}>}
 */
export function claimSetup() {
  return request('/api/setup/claim', { method: 'POST' })
}

/**
 * Create a source. The token comes back once and is never retrievable again.
 * @param {string} name
 * @param {string} [description]
 * @returns {Promise<{name: string, token: string}>}
 */
export function createSource(name, description) {
  return request('/api/sources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description: description || null }),
  })
}

/**
 * Mark one event read or unread.
 * @param {number} id
 * @param {boolean} read
 */
export function setEventRead(id, read) {
  return request(`/api/events/${id}/read?read=${read}`, { method: 'POST' })
}

/** Mark every unread event as read. */
export function markAllRead() {
  return request('/api/events/read-all', { method: 'POST' })
}

/** @returns {Promise<{public_key: string}>} */
export function fetchPushKey() {
  return request('/api/push/key')
}

/** @param {object} body */
export function savePushSubscription(body) {
  return request('/api/push/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/**
 * @typedef {object} Heartbeat
 * @property {string} name
 * @property {string} source
 * @property {'ok'|'late'|'down'} state
 * @property {number} expected_interval_seconds
 * @property {number} grace_seconds
 * @property {string|null} last_ping_at
 * @property {boolean} paused
 */

/** @returns {Promise<Heartbeat[]>} */
export function fetchHeartbeats() {
  return request('/api/heartbeats')
}