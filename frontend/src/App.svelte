<script>
  import { onMount } from 'svelte'
  import { getToken, setToken, fetchEvents } from './lib/api.js'
  import EventCard from './lib/EventCard.svelte';

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
      nextBefore = page.next_before
    } catch (e) {
      error = e instanceof Error ? e.message: String(e)
    } finally {
      loading = false
    }
  }

  function saveToken() {
    setToken(token)
    load()
  }

  onMount(() => {
    if (getToken()) load()
  })
</script>

<main>
  <h1>Gjallar</h1>

  <section class="token">
    <input
      type="password"
      placeholder="Admin token"
      bind:value={token}
      onkeydown={(e) => e.key === 'Enter' && saveToken()}
    />
    <button onclick={saveToken}>Save</button>
  </section>

  <section class="filters">
    <select bind:value={severity} onchange={() => load()}>
      <option value="">All severities</option>
      <option value="debug">debug</option>
      <option value="info">info</option>
      <option value="warn">warn</option>
      <option value="error">error</option>
      <option value="critical">critical</option>
    </select>

    <input
      type="search"
      placeholder="Search..."
      bind:value={q}
      onkeydown={(e) => e.key === 'Enter' && load()}
    />

    <label>
      <input type="checkbox" bind:checked={unread} onchange={() => load()} />
      Unread only
    </label>

    <button onclick={() => load()} disabled={loading}>
      {loading ? 'Loading...' : 'Refresh'}
    </button>
  </section>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if events.length === 0 && !loading && !error}
    <p class="empty">No events yet.</p>
  {/if}

  {#each events as event (event.id)}
    <EventCard {event} />
  {/each}

  {#if nextBefore}
    <button class="more" onclick={() => load({ append: true })} disabled={loading}>
      Load more
    </button>
  {/if}
</main>

<style>
  main { max-width: 720px; margin: 0 auto; padding: 1.5rem; }
  h1 { font-size: 1.5rem; margin-bottom: 1rem; }
  .token, .filters {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
    flex-wrap: wrap;
    align-items: center;
  }
  input, select, button {
    padding: 0.4rem 0.6rem;
    border-radius: 4px;
    border: 1px solid #374151;
    background: #111;
    color: inherit;
    font: inherit;
  }
  input[type='search'], .token input { flex: 1; min-width: 12rem; }
  label { display: flex; align-items: center; gap: 0.35rem; font-size: 0.9rem; }
  .error { color: #ef4444; }
  .empty { color: #6b7280; }
  .more { width: 100%; margin-top: 0.5rem; }
</style>