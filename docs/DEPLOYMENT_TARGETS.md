# Deployment-Target-First Decision Guide

**Rule (CLAUDE.md Gate 3): the final system architecture is decided — or at
least explicitly questioned — before any training platform or model
architecture is chosen.** A model that cannot run where the end user needs it
is a dead end at any accuracy.

The two failure modes this guide exists to prevent (both from Tile_Sorting):

1. **Weights that can't leave the platform.** Roboflow's hosted ViT training
   exports no weights — inference API only. If the end system must run
   locally/offline, a hosted-only model can never ship, so don't train the
   production model there. (Hosted platforms remain fine for labeling,
   dataset management, and quick baselines.)
2. **Models the target can't carry.** ViT-Base exported to a 328 MB ONNX vs
   21 MB for yolo26s-cls — on an edge board with no vision NPU, only the
   small model is a realistic real-time candidate, whatever the val accuracy.

---

## The questionnaire (answer and record before training)

### A. Where does inference run in the end system?

- [ ] Cloud / hosted API (internet always available, latency tolerant)
- [ ] On-prem server or industrial PC (x86, possibly discrete GPU)
- [ ] Desktop/laptop (x86, maybe GPU)
- [ ] Single-board computer — Raspberry Pi / Arduino UNO Q / Jetson class
- [ ] Microcontroller (TFLite-Micro class)

Also: online or fully offline? What happens when the network is down?

### B. Throughput and latency

- Items per second/minute the line actually runs at, and the per-item
  inference budget that implies (include capture + preprocessing).
- Is a missed deadline a quality problem or a line stoppage?

### C. Export requirements

- Does the target need exportable weights? In which format —
  `.pt` / `.safetensors` / `.onnx` / `.tflite` / vendor package?
- **Does the intended training platform actually provide that export?**
  Verify before training, not after. If not: train locally, or train a
  local twin of the hosted recipe (Tile_Sorting's `cam_vit` pattern).

### D. Target compute and memory budget

- CPU (arch, cores, clock), GPU/NPU (and whether the runtime actually uses
  it), RAM, storage.
- Candidate model's parameter count and exported file size — with headroom
  for the rest of the pipeline (capture, dashboard, control).
- Reference points from Tile_Sorting:

| Target class | Example | Realistic model class |
|---|---|---|
| Server/desktop w/ NVIDIA GPU | dev machine, RTX 1000 Ada 6GB | ViT-Base (86M/328MB ONNX) fine; batch training too |
| SBC, CPU-only or weak GPU, no vision NPU | Arduino UNO Q (QRB2210, 2–4GB), Raspberry Pi 4/5 | Small classification heads: yolo26s-cls (5.4M/21MB), yolo26n-cls (1.5M), MobileNet/EfficientNet-Lite class |
| Accelerated edge | Jetson, Pi + Coral TPU | Mid-size models, quantized |
| MCU | Cortex-M | TFLite-Micro int8, tiny CNNs only |

### E. Verification and fallback plan

- How will the model be profiled **on the real device** before integration
  (Edge Impulse BYOM profiling, onnxruntime benchmark on the board, …)?
- What is the designated fallback architecture if the first candidate is too
  slow/large? Name it now (Tile_Sorting: yolo26n-cls, then
  MobileNet/EfficientNet-Lite) — it changes nothing today and saves a
  restart later.
- After any export: spot-check the exported model against the original on
  N≥20 images and record the agreement; record the file size.

---

## Recording the decision

Log in `Claude_log.md` (and the project charter/docs if durable):

```
Deployment target decision (YYYY-MM-DD):
- Target: <device / API>, offline-capable: <yes/no>, latency budget: <ms/item>
- Export format required: <onnx/tflite/...>; training path providing it: <...>
- Primary candidate: <model> (<params>, <expected export size>)
- Fallback: <model>
- On-target profiling plan: <how, when, what blocks it>
```

Revisit the decision whenever the target hardware changes — absolute-pixel
calibrations, device indices, and latency budgets all move with it.
