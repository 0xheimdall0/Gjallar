<script>
  import { onMount } from 'svelte'
  import {
    fetchSources,
    createSource,
    revokeSource,
    deleteSource,
    fetchHeartbeats,
    pauseHeartbeat,
    deleteHeartbeat,
  } from './api.js'

  /** @type {{ onClose: () => void }} */
  let { onClose } = $props()

  /** @type {import('./api.js').Source[]} */
  let sources = $state([])

  /** @type {import('./api.js').Heartbeat[]} */
  let heartbeats = $state([])

  let error = $state('')
  let busy = $state(false)

  let newName = $state('')
  let newDescription = $state('')

  /** The token is only knowable at creation, so it lives here until you leave. */
  let freshToken = $state('')
  let freshName = $state('')

  // Snippet builder
  let snippetSource = $state('')
  let snippetTitle = $state('Backup finished')
  let snippetSeverity = $state('info')
  let snippetMessage = $state('')
  let snippetTags = $state('backup')
  let snippetShell = $state('bash')
  let snippetKind = $state('event')
  let heartbeatName = $state('nightly-backup')
  let heartbeatEvery = $state(93600)
  let heartbeatGrace = $state(3600)

  let copied = $state('')

  async function refresh() {
    error = ''
    try {
      sources = await fetchSources()
      heartbeats = await fetchHeartbeats()
      if (!snippetSource && sources.length > 0) snippetSource = sources[0].name
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }

  onMount(refresh)

  async function addSource() {
    if (!newName.trim()) return
    busy = true
    error = ''
    try {
      const created = await createSource(newName.trim(), newDescription.trim())
      freshToken = created.token
      freshName = created.name
      snippetSource = created.name
      newName = ''
      newDescription = ''
      await refresh()
    } catch (e) {
      const status = /** @type {any} */ (e)?.status
      error =
        status === 409
          ? 'A source with that name already exists.'
          : status === 422
            ? 'That name has characters Gjallar won’t accept.'
            : e instanceof Error
              ? e.message
              : String(e)
    } finally {
      busy = false
    }
  }

  /** @param {import('./api.js').Source} source */
  async function revoke(source) {
    if (!confirm(`Revoke the token for "${source.name}"?\n\nIt will stop being able to report. Its history is kept.`)) return
    try {
      await revokeSource(source.id)
      await refresh()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }

  /** @param {import('./api.js').Source} source */
  async function remove(source) {
    if (!confirm(
      `Delete "${source.name}" and everything it ever sent?\n\n` +
      `All of its events and heartbeats are deleted too. This cannot be undone.`
    )) return
    try {
      await deleteSource(source.id)
      await refresh()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }

  /** @param {import('./api.js').Heartbeat} hb */
  async function togglePause(hb) {
    try {
      await pauseHeartbeat(hb.id, !hb.paused)
      await refresh()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }

  /** @param {import('./api.js').Heartbeat} hb */
  async function dropHeartbeat(hb) {
    if (!confirm(`Stop watching "${hb.source}/${hb.name}"?\n\nIt comes back if that source pings again.`)) return
    try {
      await deleteHeartbeat(hb.id)
      await refresh()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }

  /** @param {string} text */
  async function copy(text, label = '') {
    try {
      await navigator.clipboard.writeText(text)
      copied = label
      setTimeout(() => (copied = ''), 1500)
    } catch {
      /* clipboard needs a secure context */
    }
  }

  // The token is only ever knowable at creation time, so snippets use the
  // environment variable unless you just made this source.
  let tokenExpr = $derived(
    snippetSource === freshName && freshToken
      ? freshToken
      : snippetShell === 'bash'
        ? '$GJALLAR_TOKEN'
        : '$env:GJALLAR_TOKEN',
  )

  let tagList = $derived(
    snippetTags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean),
  )

  let snippet = $derived.by(() => {
    const base = location.origin

    if (snippetKind === 'heartbeat') {
      if (snippetShell === 'bash') {
        return [
          `curl -fsS -X POST "${base}/api/heartbeats/${heartbeatName}/ping" \\`,
          `  -H "Authorization: Bearer ${tokenExpr}" \\`,
          `  -H "Content-Type: application/json" \\`,
          `  -d '{"expected_interval_seconds":${heartbeatEvery},"grace_seconds":${heartbeatGrace}}'`,
        ].join('\n')
      }
      return [
        `$h = @{ Authorization = "Bearer ${tokenExpr}" }`,
        `Invoke-RestMethod -Method Post -Uri "${base}/api/heartbeats/${heartbeatName}/ping" \``,
        `  -Headers $h -ContentType 'application/json; charset=utf-8' \``,
        `  -Body (@{ expected_interval_seconds = ${heartbeatEvery}; grace_seconds = ${heartbeatGrace} } | ConvertTo-Json)`,
      ].join('\n')
    }

    if (snippetShell === 'bash') {
      const body = {
        title: snippetTitle,
        severity: snippetSeverity,
        ...(snippetMessage ? { message: snippetMessage } : {}),
        ...(tagList.length ? { tags: tagList } : {}),
      }
      return [
        `curl -fsS -X POST "${base}/api/events" \\`,
        `  -H "Authorization: Bearer ${tokenExpr}" \\`,
        `  -H "Content-Type: application/json" \\`,
        `  -d '${JSON.stringify(body)}'`,
      ].join('\n')
    }

    const parts = [`title = ${JSON.stringify(snippetTitle)}`, `severity = '${snippetSeverity}'`]
    if (snippetMessage) parts.push(`message = ${JSON.stringify(snippetMessage)}`)
    if (tagList.length) parts.push(`tags = @(${tagList.map((t) => `'${t}'`).join(', ')})`)

    return [
      `$h = @{ Authorization = "Bearer ${tokenExpr}" }`,
      `Invoke-RestMethod -Method Post -Uri "${base}/api/events" \``,
      `  -Headers $h -ContentType 'application/json; charset=utf-8' \``,
      `  -Body (@{ ${parts.join('; ')} } | ConvertTo-Json)`,
    ].join('\n')
  })

  /** @param {string|null} iso */
  function ago(iso) {
    if (!iso) return 'never'
    const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
    if (seconds < 60) return `${seconds}s ago`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
    return `${Math.floor(seconds / 86400)}d ago`
  }
</script>

<div class="manage">
  <div class="bar">
    <h2>Manage</h2>
    <button onclick={onClose}>Back to timeline</button>
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if freshToken}
    <div class="fresh">
      <p><strong>{freshName}</strong> created. This token is shown once.</p>
      <div class="secret">
        <code>{freshToken}</code>
        <button onclick={() => copy(freshToken, 'token')}>
          {copied === 'token' ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  {/if}

  <!-- ---- sources ---------------------------------------------------- -->
  <h3>Sources</h3>

  <ul class="rows">
    {#each sources as source (source.id)}
      <li class:revoked={source.revoked}>
        <span class="name">{source.name}</span>
        {#if source.revoked}<span class="tag">revoked</span>{/if}
        <span class="meta">{ago(source.last_seen_at)}</span>
        <span class="actions">
          {#if !source.revoked}
            <button onclick={() => revoke(source)}>Revoke</button>
          {/if}
          <button class="danger" onclick={() => remove(source)}>Delete</button>
        </span>
      </li>
    {:else}
      <li class="none">No sources yet.</li>
    {/each}
  </ul>

  <div class="row">
    <input bind:value={newName} placeholder="New source name" />
    <input bind:value={newDescription} placeholder="Description (optional)" />
    <button class="primary" onclick={addSource} disabled={busy || !newName.trim()}>
      {busy ? 'Creating…' : 'Create'}
    </button>
  </div>

  <!-- ---- heartbeats ------------------------------------------------- -->
  <h3>Heartbeats</h3>

  <ul class="rows">
    {#each heartbeats as hb (hb.id)}
      <li class:revoked={hb.paused}>
        <span class="name">{hb.source}/{hb.name}</span>
        <span class="tag">{hb.paused ? 'paused' : hb.state}</span>
        <span class="meta">every {hb.expected_interval_seconds}s · {ago(hb.last_ping_at)}</span>
        <span class="actions">
          <button onclick={() => togglePause(hb)}>{hb.paused ? 'Resume' : 'Pause'}</button>
          <button class="danger" onclick={() => dropHeartbeat(hb)}>Delete</button>
        </span>
      </li>
    {:else}
      <li class="none">Nothing is being watched for silence yet.</li>
    {/each}
  </ul>

  <!-- ---- snippet builder -------------------------------------------- -->
  <h3>Command builder</h3>
  <p class="hint">
    Build the line to paste into a script. Tokens can&rsquo;t be read back, so
    unless you just created the source this uses the
    <code>GJALLAR_TOKEN</code> environment variable.
  </p>

  <div class="grid">
    <label>
      Kind
      <select bind:value={snippetKind}>
        <option value="event">Event</option>
        <option value="heartbeat">Heartbeat ping</option>
      </select>
    </label>

    <label>
      Shell
      <select bind:value={snippetShell}>
        <option value="bash">bash / sh</option>
        <option value="powershell">PowerShell</option>
      </select>
    </label>

    <label>
      Source
      <select bind:value={snippetSource}>
        {#each sources.filter((s) => !s.revoked) as source (source.id)}
          <option value={source.name}>{source.name}</option>
        {/each}
      </select>
    </label>

    {#if snippetKind === 'event'}
      <label>
        Severity
        <select bind:value={snippetSeverity}>
          <option value="debug">debug</option>
          <option value="info">info</option>
          <option value="warn">warn</option>
          <option value="error">error</option>
          <option value="critical">critical</option>
        </select>
      </label>

      <label class="wide">
        Title
        <input bind:value={snippetTitle} />
      </label>

      <label class="wide">
        Message (optional)
        <input bind:value={snippetMessage} />
      </label>

      <label class="wide">
        Tags, comma separated
        <input bind:value={snippetTags} />
      </label>
    {:else}
      <label>
        Heartbeat name
        <input bind:value={heartbeatName} />
      </label>

      <label>
        Expected every (seconds)
        <input type="number" bind:value={heartbeatEvery} min="1" />
      </label>

      <label>
        Grace (seconds)
        <input type="number" bind:value={heartbeatGrace} min="0" />
      </label>
    {/if}
  </div>

  <div class="snippet">
    <pre><code>{snippet}</code></pre>
    <button onclick={() => copy(snippet, 'snippet')}>
      {copied === 'snippet' ? 'Copied' : 'Copy'}
    </button>
  </div>
</div>

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .bar h2 {
    font-size: 1.05rem;
    margin-right: auto;
    color: var(--gold);
  }

  h3 {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: var(--gold);
    opacity: 0.85;
    margin: 1.75rem 0 0.5rem;
  }

  .hint {
    font-size: 0.78rem;
    color: var(--text-dim);
    margin: 0 0 0.75rem;
  }

  .rows {
    list-style: none;
    padding: 0;
    margin: 0 0 0.75rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .rows li {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.55rem 0.8rem;
    background: var(--surface);
    font-size: 0.84rem;
    flex-wrap: wrap;
  }

  .rows li + li { border-top: 1px solid var(--border); }
  .rows li.revoked { opacity: 0.5; }
  .rows li.none { color: var(--text-dim); justify-content: center; }

  .name { font-family: var(--mono); }

  .tag {
    font-size: 0.66rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-dim);
    border: 1px solid var(--border-strong);
    border-radius: 999px;
    padding: 0.05rem 0.45rem;
  }

  .meta {
    color: var(--text-dim);
    font-size: 0.76rem;
  }

  .actions {
    margin-left: auto;
    display: flex;
    gap: 0.35rem;
  }

  .actions button {
    padding: 0.25rem 0.55rem;
    font-size: 0.76rem;
  }

  .danger:hover:not(:disabled) {
    color: var(--sev-error);
    border-color: rgba(217, 83, 79, 0.5);
    background: rgba(217, 83, 79, 0.1);
  }

  .row {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .row input { flex: 1; min-width: 9rem; }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
    gap: 0.6rem;
    margin-bottom: 0.9rem;
  }

  .grid label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-dim);
  }

  .grid label.wide { grid-column: 1 / -1; }
  .grid input, .grid select { text-transform: none; letter-spacing: normal; }

  .snippet {
    position: relative;
    background: var(--bg-raised);
    border: 1px solid rgba(217, 164, 65, 0.28);
    border-radius: var(--radius-sm);
    padding: 0.75rem;
  }

  .snippet pre {
    margin: 0;
    overflow-x: auto;
    font-family: var(--mono);
    font-size: 0.74rem;
    color: var(--text-muted);
  }

  .snippet button {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    padding: 0.2rem 0.5rem;
    font-size: 0.72rem;
  }

  .fresh {
    background: var(--gold-soft);
    border: 1px solid rgba(217, 164, 65, 0.35);
    border-radius: var(--radius);
    padding: 0.75rem 0.9rem;
    margin-bottom: 1rem;
  }

  .fresh p { margin: 0 0 0.5rem; font-size: 0.85rem; }

  .secret {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.5rem 0.6rem;
  }

  .secret code {
    flex: 1;
    word-break: break-all;
    font-family: var(--mono);
    font-size: 0.76rem;
    color: var(--gold-bright);
  }

  .error {
    color: var(--sev-error);
    background: rgba(217, 83, 79, 0.1);
    border: 1px solid rgba(217, 83, 79, 0.3);
    border-radius: var(--radius-sm);
    padding: 0.6rem 0.8rem;
    font-size: 0.85rem;
  }
</style>
