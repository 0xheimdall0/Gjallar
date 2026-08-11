<script>
  /** @typedef {import('./api.js').SignalEvent} SignalEvent */

  /**
   * @type {{
   *   event: SignalEvent,
   *   onToggleRead: (event: SignalEvent) => void,
   *   onDelete: (event: SignalEvent) => void,
   *   selectable?: boolean,
   *   selected?: boolean,
   *   onToggleSelect?: (event: SignalEvent) => void,
   * }}
   */
  let {
    event,
    onToggleRead,
    onDelete,
    selectable = false,
    selected = false,
    onToggleSelect = () => {},
  } = $props()

  /** @type {Record<import('./api.js').Severity, [string, string]>} */
  const SEVERITY = {
    debug: ['#5f7387', 'rgba(95, 115, 135, 0.14)'],
    info: ['#6aa9e0', 'rgba(106, 169, 224, 0.14)'],
    warn: ['#e0952f', 'rgba(224, 149, 47, 0.15)'],
    error: ['#d9534f', 'rgba(217, 83, 79, 0.15)'],
    critical: ['#ff5c5e', 'rgba(255, 92, 94, 0.16)'],
  }

  let colour = $derived(SEVERITY[event.severity][0])
  let tint = $derived(SEVERITY[event.severity][1])

  let when = $derived(
    new Date(event.received_at).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }),
  )

  // In selection mode a click picks the card instead of marking it read —
  // one gesture, one meaning, depending on the mode you're in.
  function activate() {
    if (selectable) onToggleSelect(event)
    else onToggleRead(event)
  }

  function handleActivate() {
    // Selecting text inside a card shouldn't also toggle it.
    const selection = window.getSelection()
    if (selection && selection.toString().length > 0) return

    activate()
  }

  /** @param {KeyboardEvent} e */
  function handleKey(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      activate()
    }
  }
</script>

<article
  style="--accent: {colour}; --tint: {tint}"
  class:critical={event.severity === 'critical'}
  class:read={event.read_at !== null}
  class:selected
  role="button"
  tabindex="0"
  aria-pressed={selectable ? selected : event.read_at !== null}
  title={selectable
    ? 'Click to select'
    : event.read_at
      ? 'Click to mark unread'
      : 'Click to mark read'}
  onclick={handleActivate}
  onkeydown={handleKey}
>
  <header>
    {#if selectable}
      <input
        type="checkbox"
        class="pick"
        checked={selected}
        tabindex="-1"
        aria-hidden="true"
        onclick={(e) => e.stopPropagation()}
        onchange={() => onToggleSelect(event)}
      />
    {:else}
      <span class="dot" class:unread={event.read_at === null}></span>
    {/if}
    <span class="severity">{event.severity}</span>
    <span class="source">{event.source}</span>
    <time datetime={event.received_at}>{when}</time>

    <!-- stopPropagation, or deleting would also toggle read on the way up. -->
    <button
      class="delete"
      title="Delete this event"
      aria-label="Delete this event"
      onclick={(e) => { e.stopPropagation(); onDelete(event) }}
    >&times;</button>
  </header>

  <h3>{event.title}</h3>

  {#if event.message}
    <p class="message">{event.message}</p>
  {/if}

  {#if event.tags.length > 0}
    <ul class="tags">
      {#each event.tags as tag}
        <li>{tag}</li>
      {/each}
    </ul>
  {/if}
</article>

<style>
  article {
    position: relative;
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius);
    padding: 0.8rem 1rem;
    margin-bottom: 0.6rem;
    text-align: left;
    cursor: pointer;
    transition: border-color 0.12s ease, background 0.12s ease, opacity 0.12s ease;
  }

  article:focus-visible {
    outline: none;
    border-color: var(--gold);
    box-shadow: 0 0 0 3px var(--gold-soft);
  }

  article.selected {
    background: var(--gold-soft);
    border-color: rgba(217, 164, 65, 0.55);
    opacity: 1;
  }

  .pick {
    width: 0.95rem;
    height: 0.95rem;
    flex: none;
  }

  article:hover {
    background: var(--surface-hover);
    border-color: rgba(217, 164, 65, 0.35);
    border-left-color: var(--accent);
  }

  /* Critical events get a faint glow — visible when scanning, not shouting. */
  article.critical {
    box-shadow: 0 0 0 1px rgba(255, 92, 94, 0.15), 0 0 24px rgba(255, 92, 94, 0.06);
  }

  /* Read events recede. Unread ones keep full contrast. */
  article.read {
    opacity: 0.6;
  }

  article.read:hover {
    opacity: 1;
  }

  header {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.72rem;
  }

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    border: 1px solid var(--text-dim);
    flex: none;
    transition: all 0.12s ease;
  }

  .dot.unread {
    background: var(--gold);
    border-color: var(--gold);
    box-shadow: 0 0 7px rgba(217, 164, 65, 0.7);
  }

  article:hover .dot {
    border-color: var(--gold-bright);
  }

  .severity {
    color: var(--accent);
    background: var(--tint);
    border: 1px solid var(--accent);
    border-radius: 999px;
    padding: 0.05rem 0.45rem;
    text-transform: uppercase;
    font-weight: 700;
    font-size: 0.65rem;
    letter-spacing: 0.06em;
  }

  .source {
    font-family: var(--mono);
    color: var(--text-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  time {
    margin-left: auto;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .delete {
    padding: 0 0.3rem;
    border: none;
    background: none;
    color: var(--text-dim);
    font-size: 1rem;
    line-height: 1;
    opacity: 0;
    transition: opacity 0.12s ease, color 0.12s ease;
  }

  article:hover .delete,
  .delete:focus-visible {
    opacity: 1;
  }

  .delete:hover:not(:disabled) {
    background: none;
    color: var(--sev-error);
  }

  /* No hover on touch, so the control is always visible there. */
  @media (hover: none) {
    .delete { opacity: 0.6; }
  }

  h3 {
    margin: 0.4rem 0 0;
    font-size: 0.97rem;
    font-weight: 600;
  }

  .message {
    margin: 0.35rem 0 0;
    color: var(--text-muted);
    font-size: 0.87rem;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    list-style: none;
    padding: 0;
    margin: 0.6rem 0 0;
  }

  .tags li {
    font-size: 0.68rem;
    font-family: var(--mono);
    background: var(--gold-soft);
    border: 1px solid rgba(217, 164, 65, 0.28);
    color: var(--gold);
    padding: 0.1rem 0.45rem;
    border-radius: 999px;
  }

  @media (max-width: 480px) {
    article {
      padding: 0.75rem 0.85rem;
    }

    /* The timestamp drops to its own line rather than squeezing the source. */
    header {
      flex-wrap: wrap;
      row-gap: 0.2rem;
    }

    time {
      margin-left: 0;
      flex-basis: 100%;
      order: 4;
    }

    h3 {
      font-size: 0.94rem;
    }

    /* Read cards stay legible on a phone — hover doesn't exist to reveal them. */
    article.read {
      opacity: 0.72;
    }
  }
</style>
