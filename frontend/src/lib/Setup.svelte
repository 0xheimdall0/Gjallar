<script>
  import { claimSetup, createSource, setToken, getToken } from './api.js'
  import { enablePush, pushSupported } from './push.js'
  import { copyText } from './clipboard.js'

  /** @type {{ configured: boolean, onDone: () => void }} */
  let { configured, onDone } = $props()

  /** 'claim' | 'signin' | 'source' | 'push' — where we are in the flow. */
  let step = $state(configured ? 'signin' : 'claim')

  let busy = $state(false)
  let error = $state('')

  let adminToken = $state('')
  let existingToken = $state('')

  let sourceName = $state('laptop')
  let sourceToken = $state('')

  let pushMessage = $state('')
  let canPush = pushSupported()

  /** Which button was last used, so it can report what happened. */
  let copied = $state('')

  /**
   * @param {string} text
   * @param {string} label
   */
  async function copy(text, label) {
    const ok = await copyText(text)
    copied = ok ? label : `${label}:failed`
    setTimeout(() => (copied = ''), 2000)
  }

  async function claim() {
    busy = true
    error = ''
    try {
      const { admin_token } = await claimSetup()
      adminToken = admin_token
      setToken(admin_token)
      step = 'source'
    } catch (e) {
      const status = /** @type {any} */ (e)?.status
      if (status === 409) {
        error = 'This instance is already set up. Enter its admin token instead.'
        step = 'signin'
      } else if (status === 403) {
        error =
          'Setup has to be done from the machine running Gjallar. Open it there ' +
          'on http://127.0.0.1:8000, or set SIGNAL_SETUP_ALLOW_REMOTE=true.'
      } else {
        error = e instanceof Error ? e.message : String(e)
      }
    } finally {
      busy = false
    }
  }

  function signIn() {
    if (!existingToken.trim()) return
    setToken(existingToken.trim())
    onDone()
  }

  async function addSource() {
    busy = true
    error = ''
    try {
      const created = await createSource(sourceName.trim())
      sourceToken = created.token
      step = 'push'
    } catch (e) {
      const status = /** @type {any} */ (e)?.status
      if (status === 422) {
        error =
          'That name has characters Gjallar won’t accept. Letters, digits, ' +
          'spaces and . _ - ( ) [ ] # / @ : + are allowed.'
      } else if (status === 409) {
        error = 'A source with that name already exists.'
      } else {
        error = e instanceof Error ? e.message : String(e)
      }
    } finally {
      busy = false
    }
  }

  async function turnOnPush() {
    pushMessage = 'Enabling…'
    try {
      await enablePush('warn', 'this device')
      pushMessage = 'Notifications enabled.'
    } catch (e) {
      pushMessage = e instanceof Error ? e.message : String(e)
    }
  }

  let curlExample = $derived(
    `curl -H "Authorization: Bearer ${sourceToken || '$TOKEN'}" \\\n` +
      `     -H "Content-Type: application/json" \\\n` +
      `     -d '{"title":"Hello from ${sourceName}","severity":"info"}' \\\n` +
      `     ${location.origin}/api/events`,
  )
</script>

<div class="wrap">
  <div class="card">
    <span class="mark" aria-hidden="true">
      <svg viewBox="0 0 64 64" width="40" height="40">
        <g fill="none" stroke="currentColor" stroke-width="5.5" stroke-linecap="round">
          <path d="M 18 34 A 12 12 0 0 1 30 46" />
          <path d="M 18 26 A 20 20 0 0 1 38 46" />
          <path d="M 18 18 A 28 28 0 0 1 46 46" />
        </g>
        <circle cx="18" cy="46" r="4.5" fill="currentColor" />
      </svg>
    </span>

    {#if step === 'claim'}
      <h1>Set up Gjallar</h1>
      <p>
        This instance hasn&rsquo;t been claimed yet. Setting it up generates an
        admin token for the interface and a key pair for push notifications,
        and writes them to <code>backend/.env</code>.
      </p>
      <p class="note">
        Anyone who reaches an unclaimed Gjallar can take ownership of it, so
        this only works from the machine it runs on. Do it now.
      </p>
      <button class="primary" onclick={claim} disabled={busy}>
        {busy ? 'Setting up…' : 'Set up this instance'}
      </button>

    {:else if step === 'signin'}
      <h1>Unlock Gjallar</h1>
      <p>This instance is already set up. Enter its admin token.</p>
      <input
        type="password"
        placeholder="Admin token"
        bind:value={existingToken}
        onkeydown={(e) => e.key === 'Enter' && signIn()}
      />
      <button class="primary" onclick={signIn}>Continue</button>
      <p class="note">
        It&rsquo;s the <code>SIGNAL_ADMIN_TOKEN</code> line in
        <code>backend/.env</code>.
      </p>

    {:else if step === 'source'}
      <h1>Save your admin token</h1>
      <p>
        This is shown <strong>once</strong>. It&rsquo;s already saved in this
        browser, but store it somewhere safe — there is no way to recover it.
      </p>
      <div class="secret">
        <code>{adminToken}</code>
        <button onclick={() => copy(adminToken, 'token')}>
          {copied === 'token' ? 'Copied' : copied === 'token:failed' ? 'Select it' : 'Copy'}
        </button>
      </div>
      <p class="note">
        It is also written to <code>backend/.env</code> as
        <code>SIGNAL_ADMIN_TOKEN</code>, so it can be recovered from the server
        if you lose it.
      </p>

      <h2>Name your first source</h2>
      <p>
        One credential per machine or script, so any of them can be revoked on
        its own.
      </p>
      <div class="row">
        <input
          bind:value={sourceName}
          placeholder="laptop"
          onkeydown={(e) => e.key === 'Enter' && addSource()}
        />
        <button class="primary" onclick={addSource} disabled={busy || !sourceName.trim()}>
          {busy ? 'Creating…' : 'Create'}
        </button>
      </div>
      <p class="note">
        Something you&rsquo;ll recognise in a notification at 3am &mdash;
        <code>laptop</code>, <code>nas</code>, <code>Server (HOST)</code>.
      </p>

    {:else if step === 'push'}
      <h1>Token for {sourceName}</h1>
      <p>
        Give this to the machine that will report. It is shown
        <strong>once</strong> and cannot be recovered — if you lose it, revoke
        the source and create another.
      </p>
      <div class="secret">
        <code>{sourceToken}</code>
        <button onclick={() => copy(sourceToken, 'source')}>
          {copied === 'source' ? 'Copied' : copied === 'source:failed' ? 'Select it' : 'Copy'}
        </button>
      </div>

      <h2>Send your first event</h2>
      <p>Run this anywhere that can reach Gjallar:</p>
      <div class="secret block">
        <pre><code>{curlExample}</code></pre>
        <button onclick={() => copy(curlExample, 'curl')}>
          {copied === 'curl' ? 'Copied' : copied === 'curl:failed' ? 'Select it' : 'Copy'}
        </button>
      </div>

      {#if canPush}
        <h2>Notifications</h2>
        <p>Get events on this device even when Gjallar is closed.</p>
        <button onclick={turnOnPush}>Enable notifications</button>
        {#if pushMessage}<p class="note">{pushMessage}</p>{/if}
      {:else}
        <p class="note">
          Push needs HTTPS or localhost. Reach Gjallar over HTTPS — Tailscale is
          the easy way — and on iOS install it to the home screen first.
        </p>
      {/if}

      <button class="primary wide" onclick={onDone}>Open the timeline</button>
    {/if}

    {#if error}
      <p class="error">{error}</p>
    {/if}
  </div>
</div>

<style>
  .wrap {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 1.5rem;
  }

  .card {
    width: 100%;
    max-width: 520px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.75rem;
    box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
  }

  .mark {
    color: var(--gold);
    display: block;
    margin-bottom: 0.9rem;
    filter: drop-shadow(0 0 12px rgba(217, 164, 65, 0.3));
  }

  h1 {
    font-size: 1.25rem;
    margin-bottom: 0.5rem;
    background: linear-gradient(180deg, var(--gold-bright), var(--gold));
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }

  h2 {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: var(--gold);
    opacity: 0.85;
    margin: 1.5rem 0 0.4rem;
  }

  p {
    margin: 0 0 0.9rem;
    color: var(--text-muted);
    font-size: 0.88rem;
  }

  .note {
    font-size: 0.78rem;
    color: var(--text-dim);
  }

  code {
    font-family: var(--mono);
    font-size: 0.82em;
    color: var(--gold);
  }

  input {
    width: 100%;
    font-family: var(--mono);
  }

  .row {
    display: flex;
    gap: 0.5rem;
  }

  .row input { flex: 1; }

  .secret {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--bg-raised);
    border: 1px solid rgba(217, 164, 65, 0.3);
    border-radius: var(--radius-sm);
    padding: 0.6rem 0.7rem;
    margin-bottom: 0.9rem;
  }

  .secret code {
    flex: 1;
    word-break: break-all;
    color: var(--gold-bright);
    font-size: 0.78rem;
  }

  .secret.block {
    flex-direction: column;
    align-items: stretch;
  }

  .secret pre {
    margin: 0;
    overflow-x: auto;
    font-size: 0.72rem;
  }

  .secret.block button { align-self: flex-end; }

  button { margin-top: 0.25rem; }

  .wide {
    width: 100%;
    margin-top: 1.5rem;
  }

  .error {
    color: var(--sev-error);
    background: rgba(217, 83, 79, 0.1);
    border: 1px solid rgba(217, 83, 79, 0.3);
    border-radius: var(--radius-sm);
    padding: 0.6rem 0.75rem;
    font-size: 0.83rem;
    margin: 1rem 0 0;
  }
</style>
