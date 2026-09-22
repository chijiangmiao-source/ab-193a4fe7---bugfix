// Built-in sample: diffraction spots on a coarse area-12 lattice
// b1=(4,0), b2=(1,3) (10 genuine spots) plus three contaminants that live
// on the over-dense area-6 supermesh (2,0),(1,3).  Used only to populate
// the editor; the audit itself goes through the real backend.
export const SAMPLE_POINTS = [
  // n=0 row, y=0, x = 4m
  { id: 'g0', x: -4, y: 0 },
  { id: 'g1', x: 0, y: 0 },
  { id: 'g2', x: 4, y: 0 },
  { id: 'g3', x: 8, y: 0 },
  // n=1 row, y=3, x = 4m+1
  { id: 'g4', x: -3, y: 3 },
  { id: 'g5', x: 1, y: 3 },
  { id: 'g6', x: 5, y: 3 },
  // n=-1 row, y=-3, x = 4m-1
  { id: 'g7', x: -1, y: -3 },
  { id: 'g8', x: 3, y: -3 },
  // n=2 row, y=6, x = 4m+2
  { id: 'g9', x: 2, y: 6 },
  // contaminants on the area-6 supermesh only (odd x at y=0/-3)
  { id: 'b0', x: -2, y: 0 },
  { id: 'b1', x: 2, y: 0 },
  { id: 'b2', x: 1, y: -3 }
];

export const SAMPLE_AREA = 12;
export const SAMPLE_OUTLIERS = 3;
