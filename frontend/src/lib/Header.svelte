<script>
  /** @type {{ unread?: number, down?: number }} */
  let { unread = 0, down = 0 } = $props()
</script>

<header>
  <span class="mark" aria-hidden="true">
    <svg viewBox="0 0 64 64" width="34" height="34">
      <g fill="none" stroke="currentColor" stroke-width="5.5" stroke-linecap="round">
        <path d="M 18 34 A 12 12 0 0 1 30 46" />
        <path d="M 18 26 A 20 20 0 0 1 38 46" />
        <path d="M 18 18 A 28 28 0 0 1 46 46" />
      </g>
      <circle cx="18" cy="46" r="4.5" fill="currentColor" />
    </svg>
  </span>

  <div class="titles">
    <h1>Gjallar</h1>
    <p>Heimdall&rsquo;s signal inbox</p>
  </div>

  <div class="status">
    {#if down > 0}
      <span class="badge down">{down} silent</span>
    {/if}
    {#if unread > 0}
      <span class="badge unread">{unread} unread</span>
    {:else}
      <span class="count">all read</span>
    {/if}
  </div>
</header>

<style>
  header {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.9rem;
    padding-bottom: 1.1rem;
    margin-bottom: 1.4rem;
  }

  /* A gold rule that fades out, rather than a flat grey line. */
  header::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 1px;
    background: linear-gradient(
      to right,
      var(--gold) 0%,
      rgba(217, 164, 65, 0.35) 22%,
      var(--border) 60%,
      var(--border) 100%
    );
  }

  .mark {
    color: var(--gold);
    display: flex;
    filter: drop-shadow(0 0 10px rgba(217, 164, 65, 0.25));
  }

  .titles h1 {
    font-size: 1.35rem;
    line-height: 1.1;
    background: linear-gradient(180deg, var(--gold-bright), var(--gold));
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }

  .titles p {
    margin: 0.15rem 0 0;
    font-size: 0.78rem;
    color: var(--text-dim);
    letter-spacing: 0.02em;
  }

  .status {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.78rem;
    color: var(--text-dim);
  }

  .badge {
    padding: 0.15rem 0.5rem;
    border-radius: 999px;
    font-weight: 600;
  }

  .badge.down {
    color: var(--sev-critical);
    background: rgba(255, 92, 94, 0.12);
    border: 1px solid rgba(255, 92, 94, 0.3);
  }

  .badge.unread {
    color: var(--gold-bright);
    background: var(--gold-soft);
    border: 1px solid rgba(217, 164, 65, 0.32);
  }

  @media (max-width: 480px) {
    header {
      gap: 0.7rem;
      padding-bottom: 0.9rem;
      margin-bottom: 1.1rem;
    }

    .titles h1 { font-size: 1.15rem; }
    .titles p { display: none; }
    .count { display: none; }

    .status {
      flex-direction: column;
      align-items: flex-end;
      gap: 0.25rem;
    }
  }
</style>
