/** Full page load: drops every in-memory cache of the signed-out user. */
export function hardNavigate(url: string) {
  window.location.assign(url);
}

/** Reload the current page (e.g. to retry loading a script that never arrived). */
export function reloadPage() {
  window.location.reload();
}
