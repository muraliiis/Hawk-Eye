import sam2, os
print("sam2 path:", os.path.dirname(sam2.__file__))
# List public API
members = [x for x in dir(sam2) if not x.startswith("_")]
print("sam2 modules:", members)

# Try to import predictor
try:
    from sam2.build_sam import build_sam2_video_predictor
    print("build_sam2_video_predictor: OK")
except Exception as e:
    print("build_sam2_video_predictor:", e)

try:
    from sam2.sam2_video_predictor import SAM2VideoPredictor
    print("SAM2VideoPredictor: OK")
except Exception as e:
    print("SAM2VideoPredictor:", e)

# Check config files available
sam2_dir = os.path.dirname(sam2.__file__)
for root, dirs, files in os.walk(sam2_dir):
    for f in files:
        if f.endswith(".yaml") or f.endswith(".yml"):
            print("Config:", os.path.join(root, f).replace(sam2_dir, ""))
