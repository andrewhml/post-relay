/* =========================================================================
   contact-sheet.jsx — <ContactSheet>
   The Post Relay photo-review contact sheet.

   Props:
     photos     Array<Photo>   list of photo objects (see sample-data.js)
     leadNum?   number         `n` of the lead/cover photo to designate
     title      string         sheet title (e.g., project · feed candidates)
     sub        string         eyebrow subtitle (e.g., shoot date)

   Depends on globals from crop-helpers.js:
     cropBox, ratioLabel, chessFromAnchor, chessSpan, tightnessLabel
   ========================================================================= */

const { useMemo: _csUseMemo } = React;

function ContactSheet({ photos, leadNum, title, sub }) {
  return (
    <div className="cs-sheet">
      <header className="cs-head">
        <div>
          <div className="cs-eyebrow">
            <span>CONTACT SHEET</span>
            <span className="cs-dot" />
            <span>{String(photos.length).padStart(2, '0')} PHOTOS</span>
            <span className="cs-dot" />
            <span className="cs-eyebrow-accent">A1–E5 GRID</span>
          </div>
          <h1 className="cs-title">{title}</h1>
        </div>
        <div className="cs-sub">{sub}</div>
      </header>

      <div className="cs-body">
        {photos.map((p) => (
          <PhotoCard
            key={p.n}
            photo={p}
            isLead={leadNum != null && p.n === leadNum}
          />
        ))}
      </div>

      <div className="cs-foot">
        <span className="cs-foot-label">Crop talk</span>
        <kbd>shift 03 to B2</kbd>
        <kbd>span 04 across A2–C4</kbd>
        <kbd>tighten 06</kbd>
        <kbd>lead 03</kbd>
      </div>
    </div>
  );
}

function PhotoCard({ photo, isLead }) {
  const box = cropBox(photo);
  const coord = chessFromAnchor(photo.ax, photo.ay);
  const tightL = tightnessLabel(photo.tight);

  return (
    <div className={`cs-card ${isLead ? 'cs-card-lead' : ''}`}>
      <div className="cs-cell">
        <div
          className="cs-photo"
          style={{ aspectRatio: `${photo.w} / ${photo.h}` }}
        >
          <img src={photo.src} alt="" />
          <div
            className="cs-crop"
            style={{
              left:   `${box.x * 100}%`,
              top:    `${box.y * 100}%`,
              width:  `${box.w * 100}%`,
              height: `${box.h * 100}%`,
            }}
          />
          <GridOverlay box={box} active={coord} />
        </div>
        <div className="cs-sticker">{String(photo.n).padStart(2, '0')}</div>
        {isLead && <div className="cs-lead-pin">LEAD</div>}
      </div>
      <div className="cs-meta">
        <div className="cs-meta-row">
          <span className="cs-meta-file">{photo.file}</span>
          {isLead && <span className="cs-meta-lead">▲ LEAD</span>}
        </div>
        <div className="cs-meta-attrs">
          <span className="cs-val">{ratioLabel(photo.ratio)}</span>
          <span className="cs-sep">·</span>
          <span className="cs-anchor">◎ {coord}</span>
          <span className="cs-sep">·</span>
          <span className="cs-val">{tightL}</span>
        </div>
      </div>
    </div>
  );
}

function GridOverlay({ box, active }) {
  const { c0, c1, r0, r1 } = chessSpan(box);
  const cells = [];
  for (let r = 0; r < 5; r++) {
    for (let c = 0; c < 5; c++) {
      const coord = String.fromCharCode(65 + c) + (r + 1);
      const inCrop = c >= c0 && c <= c1 && r >= r0 && r <= r1;
      const isActive = coord === active;
      cells.push(
        <div
          key={coord}
          className={`cs-grid-cell ${isActive ? 'active' : inCrop ? 'in-crop' : ''}`}
        >
          {coord}
        </div>
      );
    }
  }
  return <div className="cs-grid">{cells}</div>;
}

window.ContactSheet = ContactSheet;
