/// <reference lib="webworker" />
import { precacheAndRoute } from 'workbox-precaching'

/**
 * @type {ServiceWorkerGlobalScope}
 */
const sw = /** @type {any} */ (self)

// @ts-ignore
precacheAndRoute(self.__WB_MANIFEST)

// Take over immediately instead of waiting for every tab to close.
sw.addEventListener('install', () => sw.skipWaiting())
sw.addEventListener('activate', (event) => event.waitUntil(sw.clients.claim()))

sw.addEventListener('push', (event) => {
  if (!event.data) return

  let payload
  try {
    payload = event.data.json()
  } catch {
    payload = { title: 'Gjallar', body: event.data.text() }
  }

  const options = {
    body: payload.body ?? '',
    icon: '/pwa-192x192.png',
    badge: '/pwa-192x192.png',
    tag: `gjallar-${payload.id ?? Date.now()}`,
    data: { id: payload.id },
    requireInteraction: payload.severity === 'critical',
  }

  event.waitUntil(
    sw.registration.showNotification(payload.title ?? 'Gjallar', options),
  )
})

sw.addEventListener('notificationclick', (event) => {
  event.notification.close()

  event.waitUntil(
    sw.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((clients) => {
        for (const client of clients) {
          if ('focus' in client) return client.focus()
        }
        return sw.clients.openWindow('/')
      }),
  )
})