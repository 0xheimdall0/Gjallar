/**
 * Copy text to the clipboard, with a fallback.
 *
 * navigator.clipboard only exists in a secure context — HTTPS or localhost.
 * Reached over plain HTTP on a LAN address it is simply `undefined`, so the
 * modern API silently isn't there. The textarea trick still works everywhere,
 * which matters for a self-hosted tool people will inevitably open over http://
 * before they set up TLS.
 *
 * @param {string} text
 * @returns {Promise<boolean>} whether the copy succeeded
 */
export async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Permission denied, or the document wasn't focused. Fall through.
    }
  }

  try {
    const area = document.createElement('textarea')
    area.value = text

    // Off-screen but still focusable — display:none would break the selection.
    area.style.position = 'fixed'
    area.style.top = '-1000px'
    area.setAttribute('readonly', '')

    document.body.appendChild(area)
    area.select()

    const ok = document.execCommand('copy')
    document.body.removeChild(area)
    return ok
  } catch {
    return false
  }
}
