<script>
  import { onMount } from 'svelte'
  import {
    getToken,
    setToken,
    fetchEvents,
    fetchHeartbeats,
    setEventRead,
    markAllRead,
    fetchSetupStatus,
  } from './lib/api.js'
  import Setup from './lib/Setup.svelte'
  import { enablePush, pushSupported } from './lib/push.js'
  import EventCard from './lib/EventCard.svelte'
  import HeartbeatPanel from './lib/HeartbeatPanel.svelte'
  import Header from './lib/Header.svelte'

  /** @typedef {import('./lib/api.js').SignalEvent} SignalEvent */
  /** @typedef {import('./lib/api.js').Severity} Severity */

  let token = $state(getToken())

  /** @type {SignalEvent[]} */
  let events = $state([])

  /** @type {number|null} */
  let nextBefore = $state(null)

  let error = $state('')
  let loading = $state(false)

  /** @type {Severity|''} */
  let severity = $state('')
  let q = $state('')
  let unread = $state(false)

  let pushState = $state('')
  let canPush = pushSupported()

  /** @type {import('./lib/api.js').Heartbeat[]} */
  let heartbeats = $state([])

  // The token field is only in the way once a token is saved.
  let showSettings = $state(false)

  let booting = $state(true)
  let needsSetup = $state(false)
  let serverConfigured = $state(true)

  let unreadCount = $state(0)

  let silentCount = $derived(
    heartbeats.filter((hb) => hb.state === 'down' && !hb.paused).length,
  )

  /**
   * Flip one event's read state. The list updates immediately and the request
   * follows — the alternative is a visible delay on every click.
   * @param {SignalEvent} event
   */
  async function toggleRead(event) {
    const nowRead = event.read_at === null
    const previous = event.read_at

    event.read_at = nowRead ? new Date().toISOString() : null
    unreadCount += nowRead ? -1 : 1

    try {
      await setEventRead(event.id, nowRead)
    } catch (e) {
      // Put it back if the server disagreed.
      event.read_at = previous
      unreadCount += nowRead ? 1 : -1
      error = e instanceof Error ? e.message : String(e)
    }
  }

  async function readEverything() {
    try {
      await markAllRead()
      await load()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }

  async function turnOnPush() {
    pushState = 'Enabling…'
    try {
      await enablePush('warn', 'this device')
      pushState = 'Notifications enabled'
    } catch (e) {
      pushState = e instanceof Error ? e.message : String(e)
    }
  }

  /**
   * @param {object} [opts]
   * @param {boolean} [opts.append] append to the list instead of replacing it
   */
  async function load({ append = false } = {}) {
    loading = true
    error = ''
    try {
      const page = await fetchEvents({
        severity,
        q,
        unread,
        before: append ? nextBefore : undefined,
        limit: 25,
      })
      events = append ? [...events, ...page.events] : page.events
      if (!append) {
        heartbeats = await fetchHeartbeats()
      }
      nextBefore = page.next_before
      unreadCount = page.unread_count
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      loading = false
    }
  }

  function saveToken() {
    setToken(token)
    showSettings = false
    load()
  }

  function finishSetup() {
    needsSetup = false
    token = getToken()
    load()
  }

  onMount(async () => {
    try {
      const status = await fetchSetupStatus()
      serverConfigured = status.configured
      // Either the server has never been set up, or this browser has no token.
      needsSetup = !status.configured || !getToken()
    } catch {
      // If the status call fails the server is unreachable; fall back to the
      // normal screen so the error is visible rather than a stuck wizard.
      needsSetup = !getToken()
    } finally {
      booting = false
    }

    if (!needsSetup) load()
  })
</script>

{#if booting}
  <div class="booting"></div>
{:else if needsSetup}
  <Setup configured={serverConfigured} onDone={finishSetup} />
{:else}
<main>
  <Header unread={unreadCount} down={silentCount} />

  <div class="toolbar">
    <select bind:value={severity} onchange={() => load()} aria-label="Severity">
      <option value="">All severities</option>
      <option value="debug">debug</option>
      <option value="info">info</option>
      <option value="warn">warn</option>
      <option value="error">error</option>
      <option value="critical">critical</option>
    </select>

    <input
      type="search"
      placeholder="Search title or message…"
      bind:value={q}
      onkeydown={(e) => e.key === 'Enter' && load()}
    />

    <label class="check">
      <input type="checkbox" bind:checked={unread} onchange={() => load()} />
      Unread
    </label>

    {#if unreadCount > 0}
      <button onclick={readEverything} title="Mark every event as read">
        Mark all read
      </button>
    {/if}

    <button onclick={() => load()} disabled={loading}>
      {loading ? 'Loading…' : 'Refresh'}
    </button>

    <button
      class="icon"
      onclick={() => (showSettings = !showSettings)}
      aria-label="Settings"
      title="Settings"
    >&#9881;</button>
  </div>

  {#if showSettings}
    <div class="settings">
      <div class="row">
        <input
          type="password"
          placeholder="Admin token"
          bind:value={token}
          onkeydown={(e) => e.key === 'Enter' && saveToken()}
        />
        <button class="primary" onclick={saveToken}>Save</button>
      </div>

      {#if canPush}
        <div class="row">
          <button onclick={turnOnPush}>Enable notifications</button>
          {#if pushState}<span class="hint">{pushState}</span>{/if}
        </div>
      {:else}
        <p class="hint">
          This browser can&rsquo;t receive push notifications here. Notifications
          need HTTPS or localhost, and on iOS the app must be installed to the
          home screen.
        </p>
      {/if}
    </div>
  {/if}

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <HeartbeatPanel {heartbeats} />

  {#if events.length === 0 && !loading && !error}
    <div class="empty">
      <p class="empty-title">Nothing has reported yet</p>
      <p>Send your first event:</p>
      <pre><code>curl -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '&lbrace;"title":"Hello from my laptop"&rbrace;' \
     {location.origin}/api/events</code></pre>
    </div>
  {/if}

  {#each events as event (event.id)}
    <EventCard {event} onToggleRead={toggleRead} />
  {/each}

  {#if nextBefore}
    <button class="more" onclick={() => load({ append: true })} disabled={loading}>
      Load more
    </button>
  {/if}
</main>
{/if}

<style>
  /* Held blank for the moment it takes to ask whether setup is needed —
     showing the timeline and then replacing it with a wizard would flash. */
  .booting {
    min-height: 100vh;
  }

  main {
    max-width: 760px;
    margin: 0 auto;
    /* env() keeps content clear of the notch and home indicator when the app
       is installed and running full-screen on a phone. */
    padding-top: calc(1.5rem + env(safe-area-inset-top, 0px));
    padding-bottom: calc(3rem + env(safe-area-inset-bottom, 0px));
    padding-left: max(1.25rem, env(safe-area-inset-left, 0px));
    padding-right: max(1.25rem, env(safe-area-inset-right, 0px));
  }

  .toolbar {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 1rem;
  }

  .toolbar input[type='search'] {
    flex: 1;
    min-width: 10rem;
  }

  .check {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.45rem 0.7rem 0.45rem 0.55rem;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--bg-raised);
    font-size: 0.85rem;
    color: var(--text-muted);
    white-space: nowrap;
    cursor: pointer;
    transition: border-color 0.12s ease, color 0.12s ease;
  }

  .check:hover {
    border-color: rgba(217, 164, 65, 0.45);
    color: var(--text);
  }

  .check:has(input:checked) {
    border-color: rgba(217, 164, 65, 0.55);
    color: var(--gold-bright);
  }

  .icon {
    padding: 0.45rem 0.6rem;
    line-height: 1;
    color: var(--text-muted);
  }

  .settings {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.9rem;
    margin-bottom: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
  }

  .row input[type='password'] {
    flex: 1;
    min-width: 12rem;
    font-family: var(--mono);
  }

  .hint {
    font-size: 0.8rem;
    color: var(--text-dim);
    margin: 0;
  }

  .error {
    color: var(--sev-error);
    background: rgba(217, 83, 79, 0.1);
    border: 1px solid rgba(217, 83, 79, 0.3);
    border-radius: var(--radius-sm);
    padding: 0.6rem 0.8rem;
    font-size: 0.9rem;
  }

  .empty {
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius);
    padding: 1.75rem;
    text-align: center;
    color: var(--text-dim);
  }

  .empty-title {
    color: var(--text-muted);
    font-weight: 600;
    margin: 0 0 0.75rem;
  }

  .empty pre {
    text-align: left;
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.75rem;
    overflow-x: auto;
    font-family: var(--mono);
    font-size: 0.75rem;
    color: var(--text-muted);
    margin: 0.5rem 0 0;
  }

  .more {
    width: 100%;
    margin-top: 0.75rem;
  }

  /* ---- phones ------------------------------------------------------- */

  @media (max-width: 620px) {
    /* Search gets its own full-width row above the controls. */
    .toolbar input[type='search'] {
      order: -1;
      flex-basis: 100%;
      min-width: 0;
    }

    .toolbar select {
      flex: 1;
      min-width: 0;
    }

    /* Comfortable tap targets — 44px is the usual minimum. */
    .toolbar button,
    .toolbar select,
    .check {
      min-height: 2.6rem;
    }

    .settings .row input[type='password'] {
      flex-basis: 100%;
    }

    .settings .row button {
      flex: 1;
    }

    .empty {
      padding: 1.25rem 0.9rem;
    }

    .empty pre {
      font-size: 0.68rem;
    }
  }
</style>
