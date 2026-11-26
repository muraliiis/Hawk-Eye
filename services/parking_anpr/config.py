from pydantic_settings import BaseSettings, SettingsConfigDict


class ParkingANPRConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PARKING_")

    vehicle_model_path: str = "services/parking_anpr/models/yolov8n.pt"
    plate_model_repo: str = "Koushim/yolov8-license-plate-detection"
    plate_model_filename: str = "best.pt"
    vehicle_confidence: float = 0.45
    plate_confidence: float = 0.50
    ocr_confidence: float = 0.60
    parked_frame_threshold: int = 30
    frame_skip_parking: int = 5
    frame_skip_anpr: int = 15
    plate_retention_hours: int = 24
    flagged_retention_days: int = 7
    models_dir: str = "services/parking_anpr/models"


settings = ParkingANPRConfig()
