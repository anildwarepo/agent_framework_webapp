// Runtime polyfill: add roundRect if missing
if (!CanvasRenderingContext2D.prototype.roundRect) {
  // eslint-disable-next-line no-extend-native
  CanvasRenderingContext2D.prototype.roundRect = function (
    x: number, y: number, w: number, h: number, r: number | number[]
  ) {
    let radii: [number, number, number, number];
    if (Array.isArray(r)) {
      const [tl = 0, tr = 0, br = 0, bl = 0] = r;
      radii = [tl, tr, br, bl];
    } else {
      radii = [r, r, r, r];
    }
    const [tl, tr, br, bl] = radii.map(v => Math.max(0, Math.min(v, Math.min(w, h) / 2))) as [number, number, number, number];

    this.beginPath();
    this.moveTo(x + tl, y);
    this.lineTo(x + w - tr, y);
    this.quadraticCurveTo(x + w, y, x + w, y + tr);
    this.lineTo(x + w, y + h - br);
    this.quadraticCurveTo(x + w, y + h, x + w - br, y + h);
    this.lineTo(x + bl, y + h);
    this.quadraticCurveTo(x, y + h, x, y + h - bl);
    this.lineTo(x, y + tl);
    this.quadraticCurveTo(x, y, x + tl, y);
    return this;
  };
}
