# Nanoblock part list (reference)

Source: nanoblock.info kit search, block list (<https://nanoblock.info/nbks/?mode=blockList>) and
block & colour combination list (`?mode=combi`), fetched 2026-10-15. The site lists 56 block types
and 45 colours; the colours are already in `src/brickbuilder/profiles/nanoblock.toml`.

Columns:
- **nanoblock.info**: the site's name (`<footprint> : <variant>`).
- **#**: the site's block number (its picture is `https://nanoblock.info/nbks/img/block/block<#>.png`).
- **BrickBuilder**: our part id, where we have one.
- **LDraw**: file in the unofficial library at `D:\Nanoblocks\LDrawData` (shapes only; its
  dimensions are approximate).
- **Shape**: from the site's pictures. ❓ = not confirmed. ⏭ **skipped** = the part exists but is
  de-prioritised (rare, and not needed for now); don't add it to the library without asking.

Naming notes:
- **"1/2" codes are the plain bricks**: 1/2A = 2×4, 1/2B = 2×2, 1/2C = 1×2, 1/2D = 1×4,
  1/2E = 1×1, 1/2A2 = 2×8, 1/2BO-3 = 1×3. 1/2F is a round 1×1, 1/2BO-1 a 1×2 with one centre stud.
  The P codes are base plates.
- "(DF有)" follows the 1/2 codes on the combination page; meaning unknown ❓.
- 凸 = stud: "1凸" = one stud, "2凸" = two studs.
- JO = joint: **JO-C = socket (cup)**, **JO-D = ball**, on the side of the brick.

| nanoblock.info | # | BrickBuilder | LDraw | Shape |
|---|---|---|---|---|
| 1x1 : 1/2E | 34 | `brick_1x1` | NB101 | plain 1×1 |
| 1x1 : 1/2F | 32 | | NB101R | round 1×1 |
| 1x1 : 2凸 | 27 | | NB101S | 1×1 with a side stud |
| 1x1 : Cylinder | 17 | | | tall thin cylinder ❓ |
| 1x2 : 1/2C | 29 | `brick_1x2` | NB102 | plain 1×2 |
| 1x2 : 1/2BO-1 | 33 | `brick_1x2_1_stud` | NB102S | 1×2 with one centre stud (half-offset stud; fine rotation) |
| 1x2 : flat | 25 | `flat_1x2` | NB102F | 1×2, no studs; top flush with a brick's body top |
| 1x2 : JO-C(?) | 5 | | NB201S ❓ | 1×2 with a socket on the side |
| 1x2 : JO-D(?) | 6 | | NB201B ❓ | 1×2 with a ball on the side |
| 1x2 : Ring | 51 | | | 1×2 with a flat loop attached. ⏭ **skipped**: keychain-style kits |
| 1x2 : Round | 40 | | NB102R | 1×2 with rounded ends |
| 1x2 : Slope 1 | 12 | `slope_1x2_wedge_1x1` | NB102A | |
| 1x2 : Slope 2 | 11 | `slope_1x2_wedge_1x2` | NB10202A | (LDraw drawn 1 mm too short) |
| 1x2 : SlopeRev 1 | 16 | `slope_1x2_wedge_1x1_inverted` | NB102B | |
| 1x2 : SlopeRev 2 | 18 | `slope_1x2_wedge_1x2_inverted` | NB10202V | |
| 1x3 : 1/2BO-3 | 24 | `brick_1x3` | NB103 | plain 1×3 |
| 1x3 : 2凸 | 19 | `brick_1x3_2_studs` | NB103S2 | 1×3 with 2 studs, on the cell boundaries |
| 1x3 : Round | 30 | | NB103R | 1×3 with rounded ends |
| 1x3 : Slope 1 | 14 | `slope_1x3_wedge_2x1` | NB103A | |
| 1x4 : 1/2D | 21 | `brick_1x4` | NB104 | plain 1×4 |
| 1x4 : Round | 26 | | NB104R | 1×4 with rounded ends |
| 1x6 | 7 | `brick_1x6` | NB106 | plain 1×6 |
| 2x2 : 1/2B | 22 | `brick_2x2` | NB202 | plain 2×2 |
| 2x2 : 1凸 | 10 | `brick_2x2_1_stud` | NB202S1 | 2×2 with one centre stud (fine rotation) |
| 2x2 : Axle | 42 | | NB202X | ⏭ **skipped**: train/car part |
| 2x2 : Fan-shaped | 46 | | NB202C | quarter round |
| 2x2 : JO-C | 3 | | NB202S | 2×2 with a socket on the side |
| 2x2 : JO-D | 4 | | NB202B | 2×2 with a ball on the side |
| 2x2 : L | 20 | `brick_2x2_l` | NB202L | L of three cells, a stud on each |
| 2x2 : Round | 15 | | NB202R | |
| 2x2 : Slope 1 | 41 | `slope_2x2_wedge_1x1` | | |
| 2x2 : Tire | 44 | | | ⏭ **skipped**: train/car part |
| 2x2 : Wheel | 43 | | NB202W | ⏭ **skipped**: train/car part |
| 2x3 | 8 | `brick_2x3` | NB203 | plain 2×3 |
| 2x3 : Slope 1 | 13 | `slope_2x3_wedge_2x1` | NB203A | |
| 2x3 : T | 9 | `brick_2x3_t` | NB203T | row of three plus one on the middle's side, a stud on each |
| 2x4 : 1/2A | 31 | `brick_2x4` | NB204 | plain 2×4 |
| 2x4 : flat | 28 | `flat_2x4` | NB204F | 2×4, no studs; top flush with a brick's body top |
| 2x4 : Slope 1 | 35 | `slope_2x4_wedge_1x1` | NB204A | |
| 2x6 : Base of wheel | | | | the only 2×6 on the site (no plain 2×6 brick exists). ⏭ **skipped**: train/car part |
| 2x8 : 1/2A2 | 23 | `brick_2x8` | NB208 | plain 2×8 |
| 4x4 : Tire | 45 | | NB404W ❓ | large wheel. ⏭ **skipped**: train/car part |
| 10x10 : 1/2P1010 | 1 | `plate_10x10` | NB10Base | base plate: brick height, studs on every cell |
| 20x20 : 1/2P2020 | 2 | `plate_20x20` | NB20Base | base plate: brick height, studs on every cell |
| 20x20 : holed | | | | base plate with holes. ⏭ **skipped**: only in one Christmas tree set, paired with the LED plate (presumably to let the light through) |

⏭ **Skipped**, all special parts without a picture on the list page: Nanoid Face, Nanoid Hair, MotorUnitCover,
Puddle, Charger, Chassis, Railway wheel, Nanobbit, Miffy (Nijntje), LED PLATE,
LED PLATE : Optical fiber, LED PLATE : USB.

There is no plain 2×6 brick, so the starter set doesn't include one (`brick_2x6` was removed).
