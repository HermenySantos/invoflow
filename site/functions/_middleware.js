import { blockedPath, notFound } from './guard.js';

export async function onRequest(context) {
  const path = new URL(context.request.url).pathname;
  if (blockedPath(path)) return notFound();
  return context.next();
}
