<script>
  /** @type {{ heartbeats: import('./api.js').Heartbeat[] }} */
  let { heartbeats } = $props()

  const STATE_VARS = {
    ok: 'var(--ok)',
    late: 'var(--sev-warn)',
    down: 'var(--sev-critical)',
  }

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

{#if heartbeats.length > 0}
  <section class="panel">
    <h2>Heartbeats</h2>
    <ul>
      {#each heartbeats as hb (hb.source + '/' + hb.name)}
        <li class:paused={hb.paused} style="--dot: {STATE_VARS[hb.state]}">
          <span class="dot" class:pulse={hb.state === 'down' && !hb.paused}></span>
          <span class="name">
            <span class="source">{hb.source}</span><span class="sep">/</span>{hb.name}
          </span>
          <span class="state">{hb.paused ? 'paused' : hb.state}</span>
          <span class="seen">{ago(hb.last_ping_at)}</span>
        </li>
      {/each}
    </ul>
  </section>
{/if}

<style>
  .panel {
    margin-bottom: 1.5rem;
  }

  h2 {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: var(--gold);
    opacity: 0.85;
    margin: 0 0 0.5rem;
  }

  ul {
    list-style: none;
    padding: 0;
    margin: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }

  li {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    padding: 0.5rem 0.85rem;
    background: var(--surface);
    font-size: 0.83rem;
  }

  li + li {
    border-top: 1px solid var(--border);
  }

  li.paused {
    opacity: 0.45;
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: none;
    background: var(--dot);
    box-shadow: 0 0 8px var(--dot);
  }

  /* A silent heartbeat is the one thing on this page that should move. */
  .pulse {
    animation: pulse 1.8s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }

  @media (prefers-reduced-motion: reduce) {
    .pulse { animation: none; }
  }

  .name {
    font-family: var(--mono);
    color: var(--text);
  }

  .source { color: var(--text-muted); }
  .sep { color: var(--text-dim); }

  .state {
    color: var(--dot);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 600;
  }

  .seen {
    margin-left: auto;
    color: var(--text-dim);
    font-size: 0.76rem;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  @media (max-width: 480px) {
    li {
      padding: 0.55rem 0.7rem;
      font-size: 0.78rem;
    }

    /* Long source/name pairs truncate rather than pushing the state off-screen. */
    .name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      min-width: 0;
    }

    .state {
      display: none;
    }
  }
</style>
