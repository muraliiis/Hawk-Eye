import sys, torch

for pkg in ["sam2", "samurai", "ultralytics", "supervision", "easyocr"]:
    try:
        m = __import__(pkg)
        ver = getattr(m, "__version__", "installed")
        print(f"{pkg}: {ver}")
    except ImportError:
        print(f"{pkg}: NOT installed")

print(f"torch: {torch.__version__}")
print(f"CUDA: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    p = torch.cuda.get_device_properties(0)
    print(f"GPU: {p.name}")
    print(f"VRAM: {p.total_memory / 1e9:.1f} GB")
