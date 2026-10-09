"""Configuration for DeBERTa-v3 event extraction fine-tuning and inference."""

import os
import sys
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath("."))

from ml.events.data.event_dataset import ALL_EVENT_CLASSES, LABEL2ID, ID2LABEL


class DebertaEventConfig(BaseModel):
    """Reproducible configuration for DeBERTa-v3 event classifier."""

    # Model architecture & versioning
    model_name: str = Field(
        default_factory=lambda: os.getenv("MODEL_NAME", "microsoft/deberta-v3-base"),
        description="Pretrained foundation transformer backbone",
    )
    model_version: str = Field(
        default_factory=lambda: os.getenv("MODEL_VERSION", "1.0.0"),
        description="Trained model version",
    )
    dataset_version: str = Field(default="2.0.0-improved")
    taxonomy_version: str = Field(default="1.0.0")

    # Runtime & Deployment
    device: str = Field(
        default_factory=lambda: os.getenv("MODEL_DEVICE", "cuda"),
        description="Execution device",
    )
    environment: str = Field(
        default_factory=lambda: os.getenv("ML_ENVIRONMENT", "development"),
        description="ML runtime environment",
    )

    # Hyperparameters (tuned conservatively for 6 GB VRAM)
    seed: int = Field(default=42)
    max_seq_length: int = Field(default=128)
    num_train_epochs: int = Field(default=8)
    per_device_train_batch_size: int = Field(default=8)
    per_device_eval_batch_size: int = Field(default=8)
    gradient_accumulation_steps: int = Field(default=1)
    learning_rate: float = Field(default=2.5e-5)
    weight_decay: float = Field(default=0.01)
    warmup_ratio: float = Field(default=0.1)
    mixed_precision: bool = Field(default=False)
    early_stopping_patience: int = Field(default=3)
    early_stopping_min_delta: float = Field(default=0.005)

    # Directories
    train_data_path: str = Field(default="ml/events/data/train.jsonl")
    val_data_path: str = Field(default="ml/events/data/val.jsonl")
    test_data_path: str = Field(default="ml/events/data/test.jsonl")
    output_dir: str = Field(
        default_factory=lambda: os.getenv("MODEL_PATH", "ml/checkpoints/deberta_v3_event")
    )

    # Labels
    num_classes: int = Field(default=len(ALL_EVENT_CLASSES))
    classes: List[str] = Field(default_factory=lambda: list(ALL_EVENT_CLASSES))
    label2id: Dict[str, int] = Field(default_factory=lambda: dict(LABEL2ID))
    id2label: Dict[int, str] = Field(default_factory=lambda: dict(ID2LABEL))


def detect_execution_device() -> Dict[str, Any]:
    """Inspects environment for NVIDIA GPU / CUDA availability and returns device context."""
    device_info = {
        "cuda_available": False,
        "selected_device": "cpu",
        "gpu_name": None,
        "vram_gb": None,
        "cuda_version": None,
        "reason": None,
    }

    try:
        import torch

        if torch.cuda.is_available():
            device_info["cuda_available"] = True
            device_info["selected_device"] = "cuda"
            device_info["gpu_name"] = torch.cuda.get_device_name(0)
            total_mem_bytes = torch.cuda.get_device_properties(0).total_memory
            device_info["vram_gb"] = round(total_mem_bytes / (1024**3), 2)
            device_info["cuda_version"] = torch.version.cuda
            print(f"Device: cuda")
            print(f"GPU: {device_info['gpu_name']}")
            print(f"VRAM: {device_info['vram_gb']} GB")
            print(f"CUDA: {device_info['cuda_version']}")
        else:
            device_info["cuda_available"] = False
            device_info["selected_device"] = "cpu"
            device_info["reason"] = "PyTorch CUDA runtime not active or no CUDA devices reported."
            print("CUDA available: False")
            print(f"Reason: {device_info['reason']}")
            print("Device: cpu")
    except ImportError:
        device_info["cuda_available"] = False
        device_info["selected_device"] = "cpu"
        device_info["reason"] = "PyTorch is not installed in the current environment."
        print("CUDA available: False")
        print(f"Reason: {device_info['reason']}")
        print("Device: cpu")

    return device_info


# Canonical 18 + NO_EVENT (19 Classes) Taxonomy Mapping
CANONICAL_19_CLASSES: List[str] = [
    "ORDER_PLACED",        # 0
    "PAYMENT_MADE",         # 1
    "PAYMENT_FAILED",       # 2
    "REFUND_REQUESTED",     # 3
    "REFUND_INITIATED",     # 4
    "REFUND_COMPLETED",     # 5
    "REFUND_FAILED",        # 6
    "ORDER_CANCELLED",      # 7
    "ITEM_SHIPPED",         # 8
    "DELIVERY_ATTEMPTED",   # 9
    "ITEM_DELIVERED",       # 10
    "RETURN_REQUESTED",     # 11
    "RETURN_PICKED_UP",     # 12
    "RETURN_COMPLETED",     # 13
    "MESSAGE_SENT",         # 14
    "MESSAGE_RECEIVED",     # 15
    "SUPPORT_CONTACTED",    # 16
    "SUPPORT_RESPONSE",     # 17
    "NO_EVENT",             # 18
]
CANONICAL_19_LABEL2ID: Dict[str, int] = {label: idx for idx, label in enumerate(CANONICAL_19_CLASSES)}
CANONICAL_19_ID2LABEL: Dict[int, str] = {idx: label for idx, label in enumerate(CANONICAL_19_CLASSES)}


class Canonical18DebertaConfig(DebertaEventConfig):
    """Configuration for DeBERTa-v3 on v3.0.0-canonical-18 dataset."""

    dataset_version: str = Field(default="3.0.0-canonical-18")
    taxonomy_version: str = Field(default="1.0.0-canonical-18")

    train_data_path: str = Field(default="ml/events/data/v3/train.jsonl")
    val_data_path: str = Field(default="ml/events/data/v3/val.jsonl")
    test_data_path: str = Field(default="ml/events/data/v3/test.jsonl")
    output_dir: str = Field(
        default_factory=lambda: os.getenv("MODEL_PATH", "ml/checkpoints/deberta_v3_event_canonical18")
    )

    num_classes: int = Field(default=len(CANONICAL_19_CLASSES))
    classes: List[str] = Field(default_factory=lambda: list(CANONICAL_19_CLASSES))
    label2id: Dict[str, int] = Field(default_factory=lambda: dict(CANONICAL_19_LABEL2ID))
    id2label: Dict[int, str] = Field(default_factory=lambda: dict(CANONICAL_19_ID2LABEL))
    use_class_weights: bool = Field(default=True)


# Global default configuration instances
default_deberta_config = DebertaEventConfig()
canonical18_deberta_config = Canonical18DebertaConfig()

