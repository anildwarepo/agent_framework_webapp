declare global {
  interface CanvasRenderingContext2D {
    roundRect?(
      x: number, y: number, w: number, h: number, r: number | number[]
    ): CanvasRenderingContext2D;
  }
}
export {};