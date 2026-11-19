/**
 * Stacking order of overlays mounted on <body> through ModalPortal, bottom to top.
 * In-page sticky bars use z-40 and BottomNav z-50; the offline banner (z-[100]) stays above all.
 * Full class strings, so Tailwind's scanner picks them up.
 */
export const LAYERS = {
  sheet: 'z-[60]',
  viewer: 'z-[70]',
} as const;

export type Layer = keyof typeof LAYERS;
