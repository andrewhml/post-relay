/* =========================================================================
   sample-data.js — sample photos for the contact-sheet demo.

   Photo object shape:
     n      number   display number (01..NN)
     file   string   original filename
     src    string   image URL (replace with your CDN / blob URLs)
     w, h   number   native pixel dimensions
     ratio  number   agent-recommended IG crop ratio (w/h: 1 = 1:1, 0.8 = 4:5, 1.91 = 1.91:1)
     ax     number   crop anchor X (0..1) — where the crop "leans"
     ay     number   crop anchor Y (0..1)
     tight  number   crop scale (1.0 = max fit; < 1 = tighter framing)
   =========================================================================
*/

const SAMPLE_PHOTOS = [
  { n: 1, file: 'IMG_4821.jpg', src: 'https://picsum.photos/seed/granary-b1/1000/750',  w: 4032, h: 3024, ratio: 1,    ax: 0.10, ay: 0.20, tight: 1.00 },
  { n: 2, file: 'IMG_4823.jpg', src: 'https://picsum.photos/seed/granary-b2/750/1000',  w: 3024, h: 4032, ratio: 0.8,  ax: 0.50, ay: 0.05, tight: 1.00 },
  { n: 3, file: 'IMG_4824.jpg', src: 'https://picsum.photos/seed/granary-b3/1000/750',  w: 4032, h: 3024, ratio: 1,    ax: 0.92, ay: 0.50, tight: 0.78 },
  { n: 4, file: 'IMG_4827.jpg', src: 'https://picsum.photos/seed/granary-b4/750/1000',  w: 3024, h: 4032, ratio: 0.8,  ax: 0.15, ay: 0.50, tight: 1.00 },
  { n: 5, file: 'IMG_4830.jpg', src: 'https://picsum.photos/seed/granary-b5/1000/750',  w: 4032, h: 3024, ratio: 1,    ax: 0.50, ay: 0.50, tight: 1.00 },
  { n: 6, file: 'IMG_4832.jpg', src: 'https://picsum.photos/seed/granary-b6/1000/525',  w: 4032, h: 2112, ratio: 1.91, ax: 0.50, ay: 0.92, tight: 1.00 },
  { n: 7, file: 'IMG_4835.jpg', src: 'https://picsum.photos/seed/granary-b7/750/1000',  w: 3024, h: 4032, ratio: 0.8,  ax: 0.20, ay: 0.95, tight: 0.92 },
  { n: 8, file: 'IMG_4838.jpg', src: 'https://picsum.photos/seed/granary-b8/1000/750',  w: 4032, h: 3024, ratio: 1,    ax: 0.80, ay: 0.80, tight: 0.85 },
  { n: 9, file: 'IMG_4840.jpg', src: 'https://picsum.photos/seed/granary-b9/1000/750',  w: 4032, h: 3024, ratio: 1,    ax: 0.95, ay: 0.08, tight: 0.70 },
];

const SAMPLE_LEAD = 5;
const SAMPLE_CAROUSEL_ORDER = [5, 3, 2, 7];
const SAMPLE_CAROUSEL_RATIO = 0.8; // 4:5 portrait — Instagram feed
const SAMPLE_CAROUSEL_CAPTION =
  'Saturday mornings at the Granary. New seasonal blend now pouring — say hi to our baristas. ☕';

/* Expose to other scripts (plain <script> globals + babel scripts). */
window.SAMPLE_PHOTOS = SAMPLE_PHOTOS;
window.SAMPLE_LEAD = SAMPLE_LEAD;
window.SAMPLE_CAROUSEL_ORDER = SAMPLE_CAROUSEL_ORDER;
window.SAMPLE_CAROUSEL_RATIO = SAMPLE_CAROUSEL_RATIO;
window.SAMPLE_CAROUSEL_CAPTION = SAMPLE_CAROUSEL_CAPTION;
