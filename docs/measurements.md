# Measurements (Nanoblock, mm)

Taken with calipers from real parts. ✅ = consistent, ❓ = needs a recheck. The profile
(`profiles/nanoblock.toml`) and part files use these; where the LDraw library disagrees, these win.

## Grid and studs
| what | value | note |
|---|---|---|
| stud pitch | 4.00 ✅ | |
| 1×1 body width | 4.000 | measured across a row of 20, which really measures pitch; the real gap isn't resolvable |
| stacking pitch | 3.125 ✅ | 10-brick stack, top stud excluded. Use it for proportions: a cell is **not a cube** (height / width ≈ 0.78) |
| single body height | 3.05 ✅ | ~0.075 seating gap per layer (first derived as 5.05 total incl. stud − a 2.00 stud; the stud was re-measured smaller, see below) |
| stud | Ø2.45 × 1.60, solid ✅ | re-measured (first measured Ø2.65 × 2.00); side studs are the same |
| side stud (1×1 "2凸") | centred across the face, centre 0.875 above the bottom (0.28 of a layer); base flush with the face ✅ | |

The widely quoted "4×4×5" includes the 2 mm stud; nominal is 4 × 4 × 3 (Lego: 5 × 5 × 4).

## Undersides
| what | value | note |
|---|---|---|
| wall, 1×N / 2×N | 0.85 / 0.95 | |
| 1×1 inner opening | 2.2 ❓ | consistent with the walls (0.85 + 2.2 + 0.85 = 3.9 ≈ pitch − gap). Magnifier photos: a **round counterbore at the mouth**, then a deeper **square cavity whose corners are clipped by the circle**. Best guess: the stud grips in the round bore and 2.2 is the deeper square. To confirm: round bore diameter + depth (caliper depth rod). Parked: rendering only |
| 1×N underside | hollow | one slot along the middle: studs fit anywhere along it |
| 2×N underside | double ribs along the long axis; a 2×2 photo shows a centre bar with two round holes | wall → rib gap 2.15 ❓ (< stud Ø, measure at the bottom edge); ribs + gap 1.70; ribs recessed 0.75 from the bottom edge |

Underside numbers affect rendering only; where studs fit comes from the slot rules
(`part_format.md` "Undersides"). Decision: render an antistud as a plain round hole of stud diameter;
don't model the exact cavity unless a close-up view ever needs it.

## Ball joints (JO-C cup, JO-D ball)
| what | value | note |
|---|---|---|
| faces apart, straight | 8.00 (2 cells) ✅ | |
| pivot (ball centre) from the cup part's face | 4.25 ✅ | 1.0625 cells: off the half-cell grid, fine since a jointed part gets its own frame |
| pivot from the ball part's face | 3.75 ✅ | 0.9375 cells |
| height | mid-height ✅ | a pair with one side rolled 180° lines up with top and bottom swapped. Use half a layer (half the body height differs by 0.04) |
| ball | Ø4.00–4.05 ✅ | modelled Ø4.0 |
| arm | tapered; Ø1.95 at the ball end ✅ | modelled as a plain Ø1.95 cylinder |
| cup | Ø5.20, out to 5.90 from the face ✅ | |
| cup neck | widens from Ø2.9 at the face to Ø5.20 over 2.75 ✅ | modelled as a tapered cylinder, then the Ø5.20 cup |
| range | 30° cone, or up to 90° either way in the vertical slot ✅ | from the parts and the manual; see `design.md` "Ball joints" |

The LDraw files (NB201B/S, NB202B/S) disagree: ball centre 3.6 and cup centre 3.24 from the faces
(6.84 total instead of 8), ball Ø ≈ 3.4, arm Ø 1.6. Treat them as rough shapes only.

## Slopes
The LDraw NB10202A (1×2×2 slope) is drawn 2.5 LDU (1 mm) too short: the real one peaks 3 layers above
its bottom (a 2-layer wedge on a 1-layer base).
