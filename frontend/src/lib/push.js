import { fetchPushKey, savePushSubscription } from './api.js'

export function pushSupported() {
    return (
        'serviceWorker' in navigator &&
        'PushManager' in window &&
        'Notification' in window
    )
}

/** 
 * @param {string} base64url
*/
function urlBase64ToUint8Array(base64url) {
  const padding = '='.repeat((4 - (base64url.length % 4)) % 4)
  const base64 = (base64url + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  const bytes = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) {
    bytes[i] = raw.charCodeAt(i)
  }
  return bytes
}

/**
 * Does an existing subscription use the key we're about to subscribe with?
 * @param {PushSubscription} subscription
 * @param {Uint8Array} wanted
 */
function usesKey(subscription, wanted) {
  const current = subscription.options?.applicationServerKey
  if (!current) return false

  const bytes = new Uint8Array(current)
  if (bytes.length !== wanted.length) return false

  return bytes.every((byte, i) => byte === wanted[i])
}

/**
 * @param {string} [minSeverity]
 * @param {string} [label]
 */
export async function enablePush(minSeverity = 'warn', label = 'this device') {
  if (!pushSupported()) {
    throw new Error('This browser does not support push notifications')
  }

  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    throw new Error('Notification permission was not granted')
  }

  const { public_key } = await fetchPushKey()
  const applicationServerKey = urlBase64ToUint8Array(public_key)
  const registration = await navigator.serviceWorker.ready

  // A subscription is bound to the key it was created with. If the server's
  // VAPID pair has changed since — a fresh setup, or keys regenerated — the
  // browser refuses to re-subscribe until the stale one is dropped.
  let subscription = await registration.pushManager.getSubscription()

  if (subscription && !usesKey(subscription, applicationServerKey)) {
    await subscription.unsubscribe()
    subscription = null
  }

  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey,
    })
  }

  const json = subscription.toJSON()
  if (!json.endpoint || !json.keys) {
    throw new Error("Browser returned an incomplete push subscription.")
  }
  await savePushSubscription({
    endpoint: json.endpoint,
    p256dh: json.keys.p256dh,
    auth: json.keys.auth,
    label,
    min_severity: minSeverity,
  })
}