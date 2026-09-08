window.CodenotchDesign = (function () {
  const SCALE = 44 / 117;
  const px = (n) => n * SCALE;

  function sideNotchPath(depth, length, curlRadius = px(103), cornerRadius = px(78.8)) {
    const wanted = Math.max(0, Math.min(cornerRadius, depth / 2));
    const curl = Math.max(0, Math.min(curlRadius, length / 2, depth - wanted));
    const corner = Math.max(0, Math.min(wanted, (length - 2 * curl) / 2));
    const bodyTop = curl;
    const bodyBottom = length - curl;
    const maxX = depth;

    const arc = (cx, cy, r, startDeg, endDeg, clockwise) => {
      const start = (startDeg * Math.PI) / 180;
      const end = (endDeg * Math.PI) / 180;
      const x2 = cx + r * Math.cos(end);
      const y2 = cy + r * Math.sin(end);
      let delta = end - start;
      if (clockwise && delta > 0) delta -= 2 * Math.PI;
      if (!clockwise && delta < 0) delta += 2 * Math.PI;
      const large = Math.abs(delta) > Math.PI ? 1 : 0;
      const sweep = clockwise ? 0 : 1;
      return `A ${r} ${r} 0 ${large} ${sweep} ${x2} ${y2}`;
    };

    let d = `M ${maxX} 0`;
    if (curl > 0) {
      d += ` ${arc(maxX - curl, 0, curl, 0, 90, false)}`;
    } else {
      d += ` L ${maxX} ${bodyTop}`;
    }
    d += ` L ${corner} ${bodyTop}`;
    d += ` ${arc(corner, bodyTop + corner, corner, 270, 180, true)}`;
    d += ` L 0 ${bodyBottom - corner}`;
    d += ` ${arc(corner, bodyBottom - corner, corner, 180, 90, true)}`;
    d += ` L ${maxX - curl} ${bodyBottom}`;
    if (curl > 0) {
      d += ` ${arc(maxX - curl, length, curl, 270, 360, false)}`;
    }
    d += " Z";
    return d;
  }

  function pillPath(depth, length) {
    const r = Math.min(depth, length) / 2;
    return `M ${depth} 0 L ${r} 0 A ${r} ${r} 0 0 0 0 ${r} L 0 ${length - r} A ${r} ${r} 0 0 0 ${r} ${length} L ${depth} ${length} Z`;
  }

  const GLYPHS = {
    claude: `<svg viewBox="0 0 24 24" fill="white"><path d="M12.8 2.1c-.5.1-1 .4-1.3 1.1L8.2 10.4 4.9 8.2c-.6-.4-1.4-.3-1.8.4-.3.6 0 1.3.6 1.6l4.2 2.3-3.5 1.7c-.6.3-.8 1.1-.5 1.7.3.5 1 .7 1.5.4l8.2-.8-2.3 4.8c-.3.6 0 1.4.7 1.6.6.3 1.3 0 1.6-.6l2.8-5.8 3.6 3.6c.4.4 1.1.4 1.5 0 .4-.4.4-1.1 0-1.5l-4.1-4.1 5.3-1.3c.6-.2 1-.8.8-1.4-.2-.6-.8-1-1.4-.8l-6.7 1.6L14.7 3c-.2-.5-.6-.9-1.1-.9-.3 0-.5 0-.8 0z"/></svg>`,
    openai: `<svg viewBox="0 0 24 24" fill="white"><path d="M22.3 10.5a5.5 5.5 0 0 0-.5-5.1 5.6 5.6 0 0 0-6-2.5A5.6 5.6 0 0 0 6.4 1.4a5.5 5.5 0 0 0-3.7 4 5.6 5.6 0 0 0-3.7 5.1 5.5 5.5 0 0 0 2 4.4 5.5 5.5 0 0 0 .5 5.1 5.6 5.6 0 0 0 6 2.5 5.6 5.6 0 0 0 9.4 1.5 5.5 5.5 0 0 0 3.7-4 5.6 5.6 0 0 0 3.7-5.1 5.5 5.5 0 0 0-2-4.4zm-8.4 9.4a4.1 4.1 0 0 1-2.6-.9l.1-.1 3.4-2v-.9l-3.9 2.2a4.1 4.1 0 0 1-5.6-1.5 4.1 4.1 0 0 1 .5-4.5l.1.1 3.4 2v.9L6 12.1a4.1 4.1 0 0 1-.1-2.7 4.1 4.1 0 0 1 5.6-2.3v2.5a1.7 1.7 0 0 0-.8.2l-2.9 1.7v.1l3.9-2.3a4.1 4.1 0 0 1 5.6 1.5c.4.8.5 1.7.1 2.6l-.1-.1-3.4-2v-.9l3.4 1.9a4.1 4.1 0 0 1-4.5 5.9z"/></svg>`,
    cursor: `<svg viewBox="0 0 24 24" fill="white"><path d="M12 2 4.5 6.5v11L12 22l7.5-4.5v-11L12 2zm0 2.2 5.5 3.3v1.4L12 12.1 6.5 8.9V7.5L12 4.2zm-5.5 6.5 5 3v5.6l-5-3v-5.6zm6.5 8.6v-5.6l5-3v5.6l-5 3z"/></svg>`,
    third: `<svg viewBox="0 0 24 24" fill="white"><path d="M12 2 14.2 9.8 22 12l-7.8 2.2L12 22l-2.2-7.8L2 12l7.8-2.2L12 2z"/></svg>`,
  };

  function glyphSvg(name) {
    return GLYPHS[name] || GLYPHS.third;
  }

  function ringSvg(fraction, color) {
    const r = 44;
    const c = 2 * Math.PI * (r / 2 - 4);
    const track = 5.8;
    const progress = 3.0;
    const f = Math.max(0, Math.min(1, fraction ?? 0));
    const dash = f * c;
    return `<svg viewBox="0 0 ${r} ${r}">
      <circle cx="${r / 2}" cy="${r / 2}" r="${r / 2 - 4}" fill="none" stroke="#303030" stroke-width="${track}" />
      <circle cx="${r / 2}" cy="${r / 2}" r="${r / 2 - 4}" fill="none" stroke="${color}" stroke-width="${progress}" stroke-linecap="round" stroke-dasharray="${dash} ${c}" />
    </svg>`;
  }

  return { SCALE, px, sideNotchPath, pillPath, glyphSvg, ringSvg };
})();
