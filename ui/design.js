window.CodenotchDesign = (function () {
  const SCALE = 44 / 117;
  let scale = SCALE;
  const px = (n) => n * scale;
  function setScale(multiplier) {
    const value = Number(multiplier ?? 1);
    scale = SCALE * (Number.isFinite(value) ? Math.max(0.75, Math.min(1.5, value)) : 1);
    document.documentElement.style.setProperty("--scale", scale);
  }

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
    claude: `<svg viewBox="0 0 24 24" fill="white"><path fill-rule="evenodd" d="M6.63 0.03L6.12 0.31L5.53 1.01L5.54 1.87L5.98 2.84L7.94 6.04L9.03 8.13L9.06 8.60L8.59 8.54L4.55 5.43L4.22 5.06L3.44 4.58L2.72 4.46L2.37 4.57L1.81 5.20L1.84 5.94L1.99 6.30L2.54 6.90L3.70 7.67L4.01 8.01L6.84 9.77L7.15 10.11L9.18 11.33L9.26 11.67L8.77 11.81L4.94 11.39L0.67 11.18L0.15 11.34L0.01 11.78L0.37 12.39L1.26 12.70L8.85 12.88L9.19 12.98L9.28 13.18L8.78 13.73L7.23 14.49L5.93 15.34L5.33 15.56L2.97 17.12L2.45 17.78L2.47 18.25L3.11 18.70L4.30 18.51L9.61 14.98L9.98 14.90L10.10 15.01L10.03 15.30L9.18 16.13L7.95 17.89L5.51 20.87L5.32 21.60L5.48 22.07L5.86 22.23L6.28 22.17L7.96 20.51L11.01 16.37L11.27 15.81L11.53 15.68L11.73 15.82L11.72 16.39L10.47 22.79L10.81 23.70L11.49 24.00L12.12 23.70L12.28 23.43L12.62 21.47L12.98 16.88L13.16 16.57L13.69 16.84L14.93 18.95L17.09 22.01L17.49 22.23L18.14 22.18L18.41 22.01L18.54 21.68L18.43 20.46L16.26 17.19L15.95 16.89L15.98 16.51L16.24 16.51L17.15 17.43L20.68 20.20L20.98 20.26L21.26 20.15L21.45 19.92L21.47 19.64L20.22 18.21L16.51 14.85L16.00 14.25L16.01 14.05L16.27 13.99L19.20 14.80L22.41 15.49L23.24 15.33L23.99 14.65L23.68 14.03L22.89 13.36L20.74 13.24L19.75 13.07L17.67 13.07L17.15 12.94L16.88 12.72L16.96 12.52L17.28 12.39L23.21 11.18L23.53 10.97L23.73 10.63L23.85 10.18L23.76 9.84L23.49 9.65L22.84 9.55L20.40 9.88L17.93 10.34L16.94 10.65L16.57 10.52L17.48 8.84L20.44 5.08L20.71 3.98L20.58 3.43L20.22 2.97L19.76 2.70L19.36 2.69L18.68 2.93L17.02 4.60L14.68 7.69L14.22 8.23L14.00 8.29L13.84 8.07L13.84 7.68L14.74 3.89L15.05 1.56L14.75 0.81L14.24 0.39L13.87 0.41L13.32 0.89L12.86 1.71L12.62 5.25L12.35 6.69L12.27 8.10L12.13 8.75L11.92 8.88L11.08 6.77L9.18 3.16L8.48 1.32L7.98 0.45L7.65 0.21L6.95 0.00L6.63 0.03Z"/></svg>`,
    openai: `<svg viewBox="0 0 24 24" fill="white"><path fill-rule="evenodd" d="M10.44 0.01L8.83 0.20L7.61 0.73L6.24 1.78L5.29 3.11L4.86 4.00L3.96 4.48L3.19 4.70L1.72 5.80L0.67 7.26L0.14 8.57L0.00 10.23L0.15 11.74L0.69 13.03L1.52 14.28L1.26 15.22L1.20 15.99L1.29 17.12L1.68 18.42L2.69 20.02L3.25 20.63L4.86 21.64L6.22 22.08L7.72 22.16L8.38 22.08L8.77 22.18L9.94 23.11L10.58 23.33L11.19 23.72L12.75 23.99L14.03 24.00L15.61 23.60L17.18 22.65L18.62 21.08L19.25 19.85L20.00 19.62L21.05 19.09L22.53 17.88L23.18 17.01L23.68 15.97L24.00 14.45L23.99 13.32L23.65 11.66L22.51 9.82L22.74 8.40L22.66 6.67L22.15 5.26L21.09 3.71L19.80 2.72L18.81 2.21L17.09 1.87L15.47 2.00L14.54 1.20L13.73 0.68L12.96 0.46L12.53 0.19L10.44 0.00ZM14.33 14.97L14.53 14.98L14.64 15.20L14.67 16.81L14.59 17.05L14.04 17.56L13.35 17.84L12.19 18.61L11.64 18.82L9.44 20.13L7.81 20.58L6.74 20.56L5.50 20.18L4.34 19.44L3.72 18.74L3.18 17.89L2.87 16.51L2.88 15.75L3.02 15.54L3.54 15.64L4.18 16.09L4.80 16.31L5.96 17.09L6.61 17.32L7.74 18.12L8.41 18.23L8.81 18.12L14.32 14.97ZM4.22 6.04L4.48 6.10L4.60 6.47L4.66 11.95L6.29 13.09L9.47 14.75L9.84 15.13L10.46 15.35L10.55 15.63L10.36 15.95L9.18 16.63L8.76 16.72L8.31 16.63L7.92 16.30L5.29 14.79L4.77 14.61L3.29 13.64L2.25 12.50L1.71 11.45L1.59 10.41L1.63 9.23L2.17 7.86L3.12 6.73L3.74 6.24L4.22 6.04ZM15.90 11.26L16.22 11.30L17.61 12.21L17.78 12.47L17.78 18.39L17.61 19.43L16.62 21.07L15.98 21.63L14.97 22.14L13.79 22.41L11.89 22.25L10.69 21.71L10.55 21.46L10.66 21.27L11.30 20.83L13.54 19.64L13.92 19.31L14.46 19.12L14.81 18.81L15.33 18.57L15.62 18.23L15.74 17.67L15.71 11.60L15.89 11.26ZM10.36 1.58L11.98 1.69L13.17 2.20L13.33 2.54L13.04 2.97L12.42 3.21L11.26 4.01L8.88 5.23L8.25 5.86L8.22 12.26L8.12 12.58L7.89 12.69L7.67 12.63L7.30 12.27L6.70 12.06L6.14 11.45L6.14 5.86L6.23 4.98L6.71 3.82L7.67 2.68L8.30 2.18L9.23 1.75L10.35 1.58ZM16.36 3.47L17.20 3.48L18.32 3.71L19.26 4.25L19.79 4.73L20.60 5.80L21.02 6.85L21.18 8.02L21.07 8.45L20.76 8.50L19.82 8.06L18.71 7.28L18.12 7.05L16.90 6.26L15.66 5.72L14.55 6.24L9.78 8.99L9.36 8.94L9.32 7.20L9.56 6.74L14.77 3.77L16.36 3.47ZM14.91 7.24L15.38 7.26L20.52 10.19L21.65 11.32L22.14 12.14L22.40 13.80L22.17 15.47L21.58 16.55L20.42 17.66L19.62 17.92L19.40 17.72L19.39 12.59L19.16 11.82L16.93 10.57L16.57 10.25L16.05 10.07L13.29 8.51L13.38 8.18L14.52 7.58L14.91 7.24ZM11.70 9.12L12.53 9.23L13.71 10.03L14.33 10.27L14.58 10.56L14.66 11.01L14.60 13.46L13.67 14.11L12.03 14.88L11.76 14.86L10.20 14.06L9.49 13.49L9.31 12.91L9.31 11.00L9.48 10.46L11.69 9.12Z"/></svg>`,
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

  return { SCALE, px, setScale, sideNotchPath, pillPath, glyphSvg, ringSvg };
})();
