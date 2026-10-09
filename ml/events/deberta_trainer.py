"""Reproducible DeBERTa-v3 fine-tuning pipeline for ProofFlow Event Extraction."""

import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

os.environ.setdefault("HF_HOME", os.path.abspath(".cache/huggingface"))

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath("."))

from ml.events.deberta_config import (
    Canonical18DebertaConfig,
    DebertaEventConfig,
    canonical18_deberta_config,
    default_deberta_config,
    detect_execution_device,
)


def load_jsonl_dataset(file_path: str) -> List[Dict[str, Any]]:
    """Loads JSONL formatted dataset."""
    records = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


class ProofFlowEventDataset:
    """PyTorch Dataset wrapper for ProofFlow event sequence classification."""

    def __init__(self, data: List[Dict[str, Any]], tokenizer: Any, max_len: int, label2id: Dict[str, int]):
        self.data = data
        self.tokenizer = tokenizer
        self.max_len = max_len
        self.label2id = label2id

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        item = self.data[idx]
        text = str(item["text"])
        label_str = str(item.get("canonical_event_type") or item.get("event_type"))
        label_id = self.label2id.get(label_str, self.label2id.get("NO_EVENT", 0))

        encoding = self.tokenizer(
            text,
            truncation=True,
            max_length=self.max_len,
            padding="max_length",
            return_tensors="pt",
        )

        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels": label_id,
            "text": text,
            "event_type": label_str,
            "sample_id": item.get("sample_id", f"s_{idx}"),
        }


def train_deberta_model(config: DebertaEventConfig = canonical18_deberta_config) -> Dict[str, Any]:
    """Trains DeBERTa-v3 model with full hardware detection and metric tracking."""
    import random
    from collections import Counter
    import numpy as np
    import torch
    from torch.utils.data import DataLoader
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

    # 1. Reproducibility & Seed
    random.seed(config.seed)
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.seed)

    # 2. Hardware Inspection & Strict CUDA Enforcement
    device_info = detect_execution_device()
    if not device_info["cuda_available"] or device_info["selected_device"] != "cuda":
        raise RuntimeError(
            f"CUDA GPU is strictly required for DeBERTa training, but unavailable: {device_info.get('reason')}. "
            f"Refusing to silently fall back to CPU."
        )
    device = torch.device(device_info["selected_device"])

    # 3. Load Data & Filter Non-canonical Unmapped Samples
    raw_train = load_jsonl_dataset(config.train_data_path)
    raw_val = load_jsonl_dataset(config.val_data_path)
    raw_test = load_jsonl_dataset(config.test_data_path)

    # If dataset has v3 canonical fields, filter to canonical & negative samples only
    if any("is_canonical" in s for s in raw_train):
        train_data = [s for s in raw_train if s.get("is_canonical") and s.get("canonical_event_type") is not None]
        val_data = [s for s in raw_val if s.get("is_canonical") and s.get("canonical_event_type") is not None]
        test_data = [s for s in raw_test if s.get("is_canonical") and s.get("canonical_event_type") is not None]
        print(f"Filtered canonical samples: Train={len(train_data)} (excluded {len(raw_train) - len(train_data)} legacy), "
              f"Val={len(val_data)} (excluded {len(raw_val) - len(val_data)} legacy), "
              f"Test={len(test_data)} (excluded {len(raw_test) - len(test_data)} legacy)", flush=True)
    else:
        train_data = raw_train
        val_data = raw_val
        test_data = raw_test
        print(f"Loaded datasets: Train={len(train_data)}, Val={len(val_data)}, Test={len(test_data)}", flush=True)

    # 4. Tokenizer & Model
    print(f"Initializing tokenizer and model: {config.model_name} with {config.num_classes} classes", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(config.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        config.model_name,
        num_labels=config.num_classes,
        id2label=config.id2label,
        label2id=config.label2id,
        dtype=torch.float32,
        problem_type="single_label_classification",
    )
    model.to(device)

    # 5. Class Weights for Balanced CrossEntropyLoss
    loss_criterion = torch.nn.CrossEntropyLoss()
    if getattr(config, "use_class_weights", False):
        counts = Counter(s.get("canonical_event_type") or s.get("event_type") for s in train_data)
        total_s = len(train_data)
        n_cls = config.num_classes
        raw_w = [total_s / (n_cls * max(1, counts.get(config.id2label[i], 1))) for i in range(n_cls)]
        mean_w = sum(raw_w) / len(raw_w)
        norm_w = [w / mean_w for w in raw_w]
        weights_tensor = torch.tensor(norm_w, dtype=torch.float32).to(device)
        loss_criterion = torch.nn.CrossEntropyLoss(weight=weights_tensor)
        print(f"Computed normalized class weights for {n_cls} classes: min={min(norm_w):.2f}, max={max(norm_w):.2f}", flush=True)

    # 6. DataLoaders
    train_dataset = ProofFlowEventDataset(train_data, tokenizer, config.max_seq_length, config.label2id)
    val_dataset = ProofFlowEventDataset(val_data, tokenizer, config.max_seq_length, config.label2id)

    train_loader = DataLoader(train_dataset, batch_size=config.per_device_train_batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=config.per_device_eval_batch_size, shuffle=False)

    # 7. Optimizer & Scheduler
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        eps=1e-6,
        weight_decay=config.weight_decay,
    )
    total_steps = len(train_loader) * config.num_train_epochs
    warmup_steps = int(total_steps * config.warmup_ratio)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )

    # 8. Training Loop
    start_time = time.time()
    best_val_loss = float("inf")
    best_val_f1 = 0.0
    best_epoch = 0
    epochs_without_improvement = 0
    history = []

    use_bf16 = (device.type == "cuda" and torch.cuda.is_bf16_supported() and getattr(config, "mixed_precision", False))
    grad_accum_steps = getattr(config, "gradient_accumulation_steps", 1)

    print(f"Beginning training for {config.num_train_epochs} epochs on {device} (Precision={'BFloat16' if use_bf16 else 'Float32'}, GradAccum={grad_accum_steps})...", flush=True)

    for epoch in range(1, config.num_train_epochs + 1):
        model.train()
        total_loss = 0.0
        optimizer.zero_grad()

        for step, batch in enumerate(train_loader):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            if use_bf16:
                with torch.amp.autocast("cuda", dtype=torch.bfloat16):
                    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                    loss = loss_criterion(outputs.logits, labels) / grad_accum_steps
            else:
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                loss = loss_criterion(outputs.logits, labels) / grad_accum_steps

            loss.backward()
            total_loss += loss.item() * grad_accum_steps

            if (step + 1) % grad_accum_steps == 0 or (step + 1) == len(train_loader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()
                optimizer.zero_grad()
                scheduler.step()

        avg_train_loss = total_loss / len(train_loader)

        # Validation evaluation
        model.eval()
        val_preds, val_targets = [], []
        val_loss_sum = 0.0

        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                labels = batch["labels"].to(device)

                if use_bf16:
                    with torch.amp.autocast("cuda", dtype=torch.bfloat16):
                        outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                        val_loss = loss_criterion(outputs.logits, labels)
                else:
                    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                    val_loss = loss_criterion(outputs.logits, labels)

                val_loss_sum += val_loss.item()
                preds = torch.argmax(outputs.logits, dim=1).cpu().tolist()
                val_preds.extend(preds)
                val_targets.extend(labels.cpu().tolist())

        avg_val_loss = val_loss_sum / len(val_loader)
        correct = sum(1 for p, t in zip(val_preds, val_targets) if p == t)
        val_acc = correct / len(val_targets) if val_targets else 0.0

        # Compute Macro F1 across classes present in val
        classes_in_val = set(val_targets)
        f1_list = []
        for c in classes_in_val:
            tp = sum(1 for p, t in zip(val_preds, val_targets) if p == c and t == c)
            fp = sum(1 for p, t in zip(val_preds, val_targets) if p == c and t != c)
            fn = sum(1 for p, t in zip(val_preds, val_targets) if p != c and t == c)
            p_score = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            r_score = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f_score = (2 * p_score * r_score) / (p_score + r_score) if (p_score + r_score) > 0 else 0.0
            f1_list.append(f_score)
        val_macro_f1 = sum(f1_list) / len(f1_list) if f1_list else 0.0

        epoch_stats = {
            "epoch": epoch,
            "train_loss": round(avg_train_loss, 4),
            "val_loss": round(avg_val_loss, 4),
            "val_accuracy": round(val_acc, 4),
            "val_macro_f1": round(val_macro_f1, 4),
        }
        history.append(epoch_stats)
        peak_vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024) if torch.cuda.is_available() else 0.0
        print(f"Epoch {epoch}/{config.num_train_epochs} - Train Loss: {avg_train_loss:.4f} - Val Loss: {avg_val_loss:.4f} - Val Acc: {val_acc:.4f} - Val Macro F1: {val_macro_f1:.4f} (Peak VRAM: {peak_vram_mb:.1f} MB)", flush=True)

        # Validation-based Model Selection
        if avg_val_loss < (best_val_loss - config.early_stopping_min_delta):
            best_val_loss = avg_val_loss
            best_val_f1 = val_macro_f1
            best_epoch = epoch
            epochs_without_improvement = 0
            os.makedirs(config.output_dir, exist_ok=True)
            model.save_pretrained(config.output_dir)
            tokenizer.save_pretrained(config.output_dir)

            # Save label mapping and config alongside checkpoint
            with open(os.path.join(config.output_dir, "label_mapping.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "classes": config.classes,
                    "label2id": config.label2id,
                    "id2label": config.id2label,
                    "num_classes": config.num_classes,
                }, f, indent=2)

            with open(os.path.join(config.output_dir, "training_config.json"), "w", encoding="utf-8") as f:
                json.dump(config.model_dump(), f, indent=2)

            print(f"  -> Best model checkpoint saved to {config.output_dir} (Val Loss: {avg_val_loss:.4f}, Macro F1: {val_macro_f1:.4f})", flush=True)
        else:
            epochs_without_improvement += 1
            print(f"  -> Validation did not improve ({epochs_without_improvement}/{config.early_stopping_patience})", flush=True)
            if epochs_without_improvement >= config.early_stopping_patience:
                print(f"Early stopping triggered at epoch {epoch}! Best epoch was {best_epoch}.", flush=True)
                break

    total_duration = time.time() - start_time

    summary = {
        "status": "COMPLETED",
        "model_name": config.model_name,
        "checkpoint_dir": config.output_dir,
        "dataset_version": config.dataset_version,
        "device_info": device_info,
        "hyperparameters": {
            "seed": config.seed,
            "epochs": config.num_train_epochs,
            "train_batch_size": config.per_device_train_batch_size,
            "eval_batch_size": config.per_device_eval_batch_size,
            "learning_rate": config.learning_rate,
            "weight_decay": config.weight_decay,
            "max_seq_length": config.max_seq_length,
            "num_classes": config.num_classes,
            "use_class_weights": getattr(config, "use_class_weights", False),
        },
        "dataset_splits": {
            "train_count": len(train_data),
            "val_count": len(val_data),
            "test_count": len(test_data),
        },
        "best_epoch": best_epoch,
        "best_val_loss": round(best_val_loss, 4),
        "best_val_macro_f1": round(best_val_f1, 4),
        "training_time_seconds": round(total_duration, 2),
        "history": history,
    }

    summary_path = os.path.join(config.output_dir, "training_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Model saved successfully to {config.output_dir} in {total_duration:.2f}s")
    return summary


if __name__ == "__main__":
    train_deberta_model()

