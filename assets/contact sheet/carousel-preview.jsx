/* =========================================================================
   carousel-preview.jsx — <CarouselPreview>
   Finalized IG carousel from selected photos in confirmed order.

   Props:
     photos    Array<Photo>   full photo library (lookups by `n`)
     order     Array<number>  list of photo `n` values in carousel order
     ratio     number         IG aspect ratio applied to whole carousel
                              (1 = 1:1, 0.8 = 4:5, 1.91 = 1.91:1)
     caption?  string         caption preview shown below the slides

   The first item in `order` is treated as the lead (cover) image.

   Depends on globals from crop-helpers.js: cropBox, ratioLabel
   ========================================================================= */

const { useMemo: _cpUseMemo } = React;

function CarouselPreview({ photos, order, ratio, caption }) {
  const byNum = _cpUseMemo(
    () => Object.fromEntries(photos.map((p) => [p.n, p])),
    [photos]
  );
  const selected = order.map((n) => byNum[n]).filter(Boolean);
  if (selected.length === 0) return null;
  const lead = selected[0];

  return (
    <div className="cp-sheet">
      <header className="cp-head">
        <div>
          <div className="cp-eyebrow">
            <span>CAROUSEL PREVIEW</span>
            <span className="cp-dot" />
            <span>{String(selected.length).padStart(2, '0')} SLIDES</span>
            <span className="cp-dot" />
            <span className="cp-ratio">{ratioLabel(ratio).toUpperCase()}</span>
          </div>
          <h2 className="cp-title">Final post · ordered</h2>
        </div>
        <div className="cp-sub">
          LEAD <span className="cp-lead-num">{String(lead.n).padStart(2, '0')}</span>
        </div>
      </header>

      <div className="cp-body">
        {selected.map((p, i) => (
          <CarouselSlide
            key={p.n}
            photo={p}
            position={i + 1}
            total={selected.length}
            ratio={ratio}
            isLead={i === 0}
          />
        ))}
      </div>

      <div className="cp-dots">
        {selected.map((_, i) => (
          <span key={i} className={`cp-dot-pip ${i === 0 ? 'on' : ''}`} />
        ))}
      </div>

      {caption && (
        <div className="cp-caption">
          <span className="cp-caption-label">Caption</span>
          <span className="cp-caption-text">{caption}</span>
        </div>
      )}
    </div>
  );
}

function CarouselSlide({ photo, position, total, ratio, isLead }) {
  // Compute the crop at the *carousel* ratio (overrides the photo's
  // recommended ratio so all slides share one shape).
  const box = cropBox(photo, ratio);
  return (
    <div className={`cp-slide ${isLead ? 'cp-slide-lead' : ''}`}>
      <div className="cp-slide-frame" style={{ aspectRatio: ratio }}>
        <img
          src={photo.src}
          alt=""
          style={{
            position: 'absolute',
            width:    `${100 / box.w}%`,
            height:   `${100 / box.h}%`,
            left:     `${(-box.x * 100) / box.w}%`,
            top:      `${(-box.y * 100) / box.h}%`,
            display:  'block',
            maxWidth: 'none',
          }}
        />
        <div className="cp-slide-pos">
          <span className="cp-pos-num">{position}</span>
          <span className="cp-pos-sep">/</span>
          <span className="cp-pos-total">{total}</span>
        </div>
        {isLead && <div className="cp-lead-pin">LEAD</div>}
      </div>
      <div className="cp-slide-meta">
        <span className="cp-slide-num">#{String(photo.n).padStart(2, '0')}</span>
        <span className="cp-slide-file">{photo.file}</span>
      </div>
    </div>
  );
}

window.CarouselPreview = CarouselPreview;
