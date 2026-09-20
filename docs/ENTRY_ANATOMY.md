# Anatomy of One Weighment Entry

What a single transaction's data actually looks like, established 2026-09-20 by
pulling `serial 2026-03-19-001` in full (15 photos) and joining it to its SQL
report. Companion to `docs/DATA_AUDIT.md` (dataset-level statistics).

**Why this matters:** the S3 inventory alone says "10,085 images". It does not
say that those images come from **four different sources with four different
jobs**, only one of which is the actual subject of the vision models. Anything
that treats the folder as a homogeneous bag of truck photos will be wrong.

---

## The worked example — `2026-03-19-001`

15 photos, two visits, 18 minutes apart.

| # | time | camera / source | resolution | size | content |
|---|---|---|---|---|---|
| 01 | 08:20:38 | `WB INDOOR` (CCTV) | 2688x1520 | 0.34 MB | office, weight indicator, operator |
| 02 | 08:20:38 | `WB PLATFORM IN_2` (CCTV) | 1920x1080 | 0.23 MB | overhead platform, tractor on weighbridge |
| 03–07 | 08:21–08:23 | handheld phone | 4160x1920 | ~3 MB | **loaded** trailer, firewood, multiple angles |
| | | *— truck leaves, dumps load, returns —* | | | |
| 08 | 08:41:34 | `WB PLATFORM IN_2` (CCTV) | 1920x1080 | 0.24 MB | overhead platform |
| 09 | 08:41:34 | `WB INDOOR` (CCTV) | 2688x1520 | 0.28 MB | office, weight indicator |
| 10–14 | 08:42–08:47 | handheld phone | 4160x1920 | ~3 MB | **empty** trailer bed |
| 15 | 08:47:43 | handheld phone | 3338x1805 | 1.65 MB | **photo of the printed weigh slip** |

Its SQL row (`ai_report_fields`, `transaction_id` 98, `created_at` 08:56:47)
says *"Evidence from 15 photos…"* — matching the S3 object count exactly, which
independently confirms the serial↔folder linkage.

---

## The four image roles

### 1. `WB INDOOR` — CCTV, 2688x1520
The weighbridge office. Shows the operator, the PC running the weighbridge
software, and the **Essae electronic weight indicator**. Contains no view of
the truck or load.

- **Not usable** for load-state / material classification.
- **Is** a potential source of the live indicator reading (OCR).
- Carries a burned-in timestamp overlay, top-centre.

### 2. `WB PLATFORM IN_2` — CCTV, 1920x1080
Fixed overhead/oblique view of the weighbridge deck. The whole vehicle is in
frame with its number plate legible. Fixed geometry, so this is the one camera
where absolute-pixel reasoning is even defensible.

- Best source for **vehicle identification / plate** and for confirming
  *which* vehicle was on the scale at weigh time.
- Load is visible but obliquely and at distance — weaker for material ID.
- Burned-in camera name (bottom-left) and timestamp (top-right).

### 3. Handheld phone photos — 4160x1920 and irregular
An operator walking around the trailer. **These are the images the four
project models are actually about.** No overlay, no burned-in text.

- Gross visit: the load, close and well lit.
- Tare visit: the empty bed — and in this example a **coiled rope left in the
  bed**, exactly the "is it *truly* empty?" case from the project brief.
- Free camera pose: distance, angle and framing vary shot to shot. This is
  where the aspect-ratio spread (0.46–2.17) comes from, and why absolute-pixel
  calibration cannot transfer.

### 4. Weigh-slip document photo — irregular resolution
A phone photo of the printed dot-matrix slip. **This is machine-readable
ground truth**, printed by the weighbridge itself:

```
228                 <- slip number
19-03-2026          <- date
08:40:07            <- time
TN 76 P 8336        <- plate
5830                <- gross (kg)
3410                <- tare  (kg)
2420                <- net   (kg)
KARUVAI             <- declared material
Weighed on Essae Electronic Weigh Bri  19-03-2026:08:41:34
```

Declared **material** and declared **net weight** are the two quantities the
whole fraud question turns on, and both are printed here. An OCR pass over the
slip photos would give per-transaction numeric ground truth for ~all serials —
far stronger than the LLM's prose. Worth doing before any model training.

> Caveat: the slip is *declared* data, printed from the scale. It is ground
> truth for **what was claimed**, not for whether the claim was honest. That
> is precisely the thing the vision models must independently check.

---

## Separating the roles at scale

File size is a clean proxy, verified against this entry (CCTV frames are
heavily compressed, phone photos are not):

| | count | share | median size |
|---|---|---|---|
| < 0.8 MB (CCTV) | 3,612 | 35.8% | 0.23 MB |
| >= 0.8 MB (phone) | 6,473 | 64.2% | 2.94 MB |

Per serial, the modal composition is **6 CCTV + 9 phone** (514 and 553 serials
respectively). Spread: 84 serials have *no* CCTV frames, 4 have *no* phone
frames.

> **PROVISIONAL.** The size split is validated on one entry only. The
> authoritative signal is the burned-in `WB INDOOR` / `WB PLATFORM IN_2`
> overlay, which requires reading pixels. Before relying on this, verify on a
> larger sample — and prefer classifying by overlay text or by resolution
> bucket over raw byte size.

**Consequence for the models:** roughly a third of the archive is CCTV and a
further ~700 frames are documents, so the count of images that actually show
the load close-up is well below 10,085. Any per-class budget must be computed
after role separation, not before.

---

## Gross vs tare

Still not encoded anywhere in the key. The two-visit timestamp split (see
`docs/DATA_AUDIT.md`) is the working method and remains **provisional**. This
entry supports it cleanly: cluster 1 loaded, cluster 2 empty, 18 min apart.

The weigh slip offers a cross-check — its printed time (08:40:07) falls
between the two clusters, and gross > tare identifies which is which by weight
rather than by order.
