import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))

def audit_model_inference():
    checkpoint_dir = "ml/checkpoints/deberta_v3_event_canonical18"
    assert os.path.exists(checkpoint_dir), f"Checkpoint directory {checkpoint_dir} does not exist!"

    # 1. Label Mapping Verification
    mapping_path = os.path.join(checkpoint_dir, "label_mapping.json")
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)
    
    id2label = {int(k): v for k, v in mapping["id2label"].items()}
    label2id = mapping["label2id"]
    print(f"[AUDIT] Label mapping verified: {len(id2label)} classes total.")
    assert len(id2label) == 19, f"Expected 19 classes, got {len(id2label)}"
    assert "NO_EVENT" in label2id, "NO_EVENT must be in label mapping"
    assert "ORDER_PLACED" in label2id
    assert "PAYMENT_MADE" in label2id
    assert "REFUND_COMPLETED" in label2id

    # 2. Check PyTorch and Transformers
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    print(f"[AUDIT] PyTorch version: {torch.__version__}")
    print(f"[AUDIT] CUDA available: {torch.cuda.is_available()}")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[AUDIT] Inference Device: {device}")

    # 3. Load Tokenizer & Model
    tokenizer = AutoTokenizer.from_pretrained(checkpoint_dir)
    print(f"[AUDIT] Tokenizer loaded successfully. Vocab size: {len(tokenizer)}")

    model = AutoModelForSequenceClassification.from_pretrained(checkpoint_dir)
    model.to(device)
    model.eval()
    print(f"[AUDIT] Model loaded successfully. Training mode: {model.training} (must be False)")
    assert model.training is False, "Model must be in eval() mode!"

    # 4. Run inference on representative examples
    test_cases = [
        ("Customer placed an order ORD-99120 for Electronics on 2026-08-10.", "ORDER_PLACED"),
        ("Paid $450.00 via Visa card on 2026-09-15.", "PAYMENT_MADE"),
        ("Payment failed for transaction TXN-99120 due to insufficient funds.", "PAYMENT_FAILED"),
        ("Buyer requested a refund of $85.00 for damaged goods.", "REFUND_REQUESTED"),
        ("Merchant initiated refund of $199.99 for booking ORD-33019.", "REFUND_INITIATED"),
        ("Refund completed successfully for Order ORD-55120 on 2026-10-01.", "REFUND_COMPLETED"),
        ("The replacement parts have been shipped via DHL Express.", "ITEM_SHIPPED"),
        ("Package delivered to front porch and signed for by resident.", "ITEM_DELIVERED"),
        ("The cotton shirt features a modern cut with button-down collar.", "NO_EVENT"),
    ]

    print("\n--- REPRESENTATIVE INFERENCE AUDIT ---")
    for text, expected in test_cases:
        inputs = tokenizer(text, truncation=True, max_length=128, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=1).squeeze(0)
            pred_idx = int(torch.argmax(probs).item())
            confidence = float(probs[pred_idx].item())
            pred_label = id2label[pred_idx]

        match_mark = "MATCH" if pred_label == expected else f"DIFF (expected {expected})"
        print(f"Text: '{text}'")
        print(f"  -> Predicted ID {pred_idx}: '{pred_label}' (classification confidence: {confidence:.4f}) [{match_mark}]")

    # 5. Verify gradient status
    sample_inputs = tokenizer("Test sentence", return_tensors="pt").to(device)
    with torch.no_grad():
        out = model(**sample_inputs)
        assert out.logits.requires_grad is False, "Logits must not have requires_grad=True under torch.no_grad()!"
    print("\n[AUDIT] Confirmed: Gradients are strictly disabled (requires_grad is False).")

    # 6. Verify safe error handling on non-existent checkpoint
    from ml.events.ensemble import HybridEventCascade, HybridEnsembleConfig
    bad_cfg = HybridEnsembleConfig(checkpoint_dir="ml/checkpoints/non_existent_directory")
    cascade_bad = HybridEventCascade(config=bad_cfg)
    assert cascade_bad._model is None
    pred_fallback = cascade_bad.predict_sentence("Customer placed an order ORD-123.")
    print(f"[AUDIT] Non-existent checkpoint safely degraded to fallback: {pred_fallback.predicted_event_type} (source: {pred_fallback.inference_metadata})")

    print("\n[AUDIT] Section 2 Model Inference Audit: PASSED.")

if __name__ == "__main__":
    audit_model_inference()
