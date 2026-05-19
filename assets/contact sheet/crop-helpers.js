/* =========================================================================
   crop-helpers.js — pure helper functions for Post Relay crop math.
   No dependencies. Plain ES — works in any project.
   =========================================================================
*/

/**
 * Compute the largest crop rectangle with the given aspect ratio that fits
 * inside an image, anchored toward (ax, ay) in normalised image coords.
 *
 * @param {number} imgW   image width (px or any consistent unit)
 * @param {number} imgH   image height
 * @param {number} ratio  target crop ratio = cropW / cropH
 * @param {number} ax     anchor X (0..1) — 0 = left-aligned, 1 = right-aligned
 * @param {number} ay     anchor Y (0..1)
 * @returns {{x:number,y:number,w:number,h:number}} crop box in image-normalised coords
 */
function fitCrop(imgW, imgH, ratio, ax = 0.5, ay = 0.5) {
  const imgAspect = imgW / imgH;
  let cw, ch;
  if (ratio > imgAspect) {
    cw = 1;
    ch = imgAspect / ratio;
  } else {
    cw = ratio / imgAspect;
    ch = 1;
  }
  return { x: (1 - cw) * ax, y: (1 - ch) * ay, w: cw, h: ch };
}

/**
 * Compute the final crop box for a photo, optionally overriding its
 * recommended ratio (e.g., when locking a whole carousel to one ratio).
 *
 * @param {object} photo  must have w, h, ratio, ax, ay, optional tight
 * @param {number} [overrideRatio]
 * @returns {{x:number,y:number,w:number,h:number}}
 */
function cropBox(photo, overrideRatio) {
  const r = overrideRatio != null ? overrideRatio : photo.ratio;
  const base = fitCrop(photo.w, photo.h, r, photo.ax, photo.ay);
  const t = photo.tight != null ? photo.tight : 1;
  const cw = base.w * t;
  const ch = base.h * t;
  return { x: (1 - cw) * photo.ax, y: (1 - ch) * photo.ay, w: cw, h: ch };
}

/** Render a crop ratio (w/h) as a human label: "1:1", "4:5", "1.91:1", … */
function ratioLabel(r) {
  if (Math.abs(r - 1)      < 0.01) return '1:1';
  if (Math.abs(r - 0.8)    < 0.01) return '4:5';
  if (Math.abs(r - 1.91)   < 0.02) return '1.91:1';
  if (Math.abs(r - 9 / 16) < 0.01) return '9:16';
  return r.toFixed(2);
}

/**
 * 5×5 chess-style coord (A1..E5) from anchor.
 * A = left column, E = right column; 1 = top row, 5 = bottom row.
 */
function chessFromAnchor(ax, ay) {
  const col = Math.min(4, Math.max(0, Math.round(ax * 4)));
  const row = Math.min(4, Math.max(0, Math.round(ay * 4)));
  return String.fromCharCode(65 + col) + (row + 1);
}

/** Cells the crop overlaps in the 5×5 grid. Returns { c0, c1, r0, r1 }. */
function chessSpan(box) {
  const c0 = Math.max(0, Math.min(4, Math.floor(box.x * 5)));
  const c1 = Math.max(0, Math.min(4, Math.ceil((box.x + box.w) * 5) - 1));
  const r0 = Math.max(0, Math.min(4, Math.floor(box.y * 5)));
  const r1 = Math.max(0, Math.min(4, Math.ceil((box.y + box.h) * 5) - 1));
  return { c0, c1, r0, r1 };
}

/** Named tightness label for a tight value in [0, 1]. */
function tightnessLabel(t) {
  if (t >= 0.95) return 'wide';
  if (t >= 0.83) return 'medium';
  return 'snug';
}
