/** Full page load: drops every in-memory cache of the signed-out user. */
export function hardNavigate(url: string) {
  window.location.assign(url);
}
