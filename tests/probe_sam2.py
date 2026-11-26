"""Probe SAM2VideoPredictor to find the correct attribute for the model."""
from sam2.build_sam import build_sam2_video_predictor
import inspect

pred = build_sam2_video_predictor(
    config_file="configs/sam2.1/sam2.1_hiera_l.yaml",
    ckpt_path=None,
    device="cpu",
)
print("type:", type(pred))
print("attrs:", [a for a in dir(pred) if not a.startswith("_")])
print()
# Check if it has a model attr
for attr in ["model", "sam_model", "_model", "net"]:
    if hasattr(pred, attr):
        m = getattr(pred, attr)
        print(f"pred.{attr}: {type(m)}")
        print(f"  state_dict keys: {len(m.state_dict())}")
        break
else:
    print("No model attr found — checking __dict__")
    for k, v in pred.__dict__.items():
        print(f"  {k}: {type(v)}")
