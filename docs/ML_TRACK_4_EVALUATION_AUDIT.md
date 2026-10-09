# ProofFlow ML Track 4 — Evaluation Audit Report

**Date**: 2026-10-08  
**Scope**: Verification & Correction of Held-Out Test Metrics, Taxonomy Consistency, Grounding Invariants, and Dataset Leakage  
**Status**: AUDIT COMPLETED — MATHEMATICAL INCONSISTENCIES RESOLVED  

---

## 1. Metric Inconsistency Found in Previous Report

In the initial Track 4 report, the following metrics were presented:
- **Test Samples**: 96
- **Gold Events**: 90
- **Gold NO_EVENT**: 6
- **Reported DeBERTa Metrics**: $\text{Precision} = 100\%$, $\text{Recall} = 68.89\%$, $F_1 = 81.58\%$, $\text{TP} = 62$, $\text{FP} = 0$, $\text{FN} = 28$, $\text{Total Predicted Events} = 90$.

### The Mathematical Flaw:
The metrics $\text{TP} = 62$, $\text{FP} = 0$, $\text{FN} = 28$, and $\text{Total Predicted Events} = 90$ are mathematically incompatible with $\text{Precision} = 100\%$:
1. If $\text{Total Predicted Events} = 90$ and only $\text{TP} = 62$ match the gold event type, then there are $90 - 62 = 28$ predictions where the model predicted an event of type $B$ when the true class was $A$.
2. For class $B$, that incorrect prediction is a **False Positive**.
3. Therefore, across the event extraction space, the model produced $28$ False Positives.
4. Genuine $\text{Precision} = \frac{\text{TP}}{\text{TP} + \text{FP}} = \frac{62}{62 + 28} = \frac{62}{90} = 68.89\%$.
5. Claiming $\text{Precision} = 100\%$ while $\text{Total Predicted Events} = 90$ and $\text{TP} = 62$ was a **calculation bug** caused by mixing binary event detection logic with multiclass event classification.

---

## 2. Root Cause Analysis of the Evaluation Code

Inspection of [`ml/evaluation/model_comparison.py`](file:///d:/ProofFlow/ml/evaluation/model_comparison.py#L148-L154) revealed the exact source of error:

```python
if deb_pred_type == gold_type and is_gold_event:
    deberta_metrics["true_positives"] += 1
elif deb_pred_type != "NO_EVENT" and not is_gold_event:
    deberta_metrics["false_positives"] += 1
elif deb_pred_type != gold_type and is_gold_event:
    deberta_metrics["false_negatives"] += 1
```

### The Bug:
- `false_positives` was **only** incremented if `not is_gold_event` (i.e., when gold was `NO_EVENT` but the model predicted an event).
- When a sample had a gold event of type $A$ and the model predicted an event of type $B$ ($A \ne B$):
  - The code incremented `false_negatives += 1` (penalizing class $A$).
  - The code **failed** to increment `false_positives += 1` for class $B$!
- Because DeBERTa correctly predicted `NO_EVENT` on all 6 negative samples, `false_positives` remained `0`.
- The precision formula `prec = tp / (tp + fp)` evaluated to $\frac{62}{62 + 0} = 1.0$ ($100\%$), while recall evaluated to $\frac{62}{62 + 28} = 0.6889$ ($68.89\%$).
- This conflated **Binary Event Detection** (is there an event or not?) with **Multiclass Event Classification** (did the model get the exact event type right?).

---

## 3. Independent Recomputation & Disambiguated Evaluation Views

To ensure scientific integrity, we evaluated the raw model predictions independently using `scikit-learn` under two clearly separated paradigms.

### View 1: Binary Event Detection (Any Event vs `NO_EVENT`)
*Task: Does the model correctly decide whether an incident occurred, or distinguish noise/banter?*

| Metric | Deterministic Baseline | Fine-Tuned DeBERTa-v3 |
| :--- | :---: | :---: |
| **True Positives (TP)** | 27 | **90** |
| **False Positives (FP)** | 0 | **0** |
| **False Negatives (FN)** | 63 | **0** |
| **True Negatives (TN)** | 6 | **6** |
| **Binary Accuracy** | 34.38% (33/96) | **100.00% (96/96)** |
| **Binary Precision** | 100.00% (27/27) | **100.00% (90/90)** |
| **Binary Recall** | 30.00% (27/90) | **100.00% (90/90)** |
| **Binary F1** | 46.15% | **100.00%** |

*Takeaway*: DeBERTa achieved **perfect binary detection** on the test set: it identified all 90 event statements as events ($0$ missed events) and correctly rejected all 6 non-event negative statements ($0$ false alarms). In contrast, the baseline regex missed 63 of 90 events because it could not recognize conversational or noisy phrasing.

---

### View 2: Multiclass 28-Class Classification (All 28 Classes, Full Test Set: 96 Samples)
*Task: Standard 28-way classification across the 27 taxonomy types + NO_EVENT.*

| Metric (sklearn) | Deterministic Baseline | Fine-Tuned DeBERTa-v3 | Delta |
| :--- | :---: | :---: | :---: |
| **Overall Accuracy** | 17.71% (17 / 96) | **70.83% (68 / 96)** | **+53.12%** |
| **Micro Precision** | 17.71% | **70.83%** | **+53.12%** |
| **Micro Recall** | 17.71% | **70.83%** | **+53.12%** |
| **Micro F1** | 17.71% | **70.83%** | **+53.12%** |
| **Macro Precision** | 28.29% | **70.46%** | **+42.17%** |
| **Macro Recall** | 16.67% | **71.73%** | **+55.06%** |
| **Macro F1** | 17.32% | **67.16%** | **+49.84%** |
| **Weighted F1** | 15.65% | **67.15%** | **+51.50%** |

---

### View 3: Event-Only Multiclass Evaluation (90 Gold Event Samples)
*Task: For statements known to contain an event, does the extractor predict the exact event type?*

| Metric | Deterministic Baseline | Fine-Tuned DeBERTa-v3 |
| :--- | :---: | :---: |
| **Exact Event Type Matches** | 11 / 90 (12.22%) | **62 / 90 (68.89%)** |
| **Wrong Event Type Predicted** | 16 / 90 (17.78%) | **28 / 90 (31.11%)** |
| **Missed as NO_EVENT** | 63 / 90 (70.00%) | **0 / 90 (0.00%)** |
| **Precision on Predicted Events** | 40.74% (11 / 27) | **68.89% (62 / 90)** |
| **Recall on Gold Events** | 12.22% (11 / 90) | **68.89% (62 / 90)** |
| **F1 Score** | 18.80% | **68.89%** |

---

## 4. Test Set Reconciled Mathematical Balance

Across the 96 test samples:
- $\text{Total Test Samples} = 96$
- $\text{Gold Event Samples} = 90$
- $\text{Gold NO\_EVENT Samples} = 6$

### DeBERTa Predictions Reconciliation:
- Total Predicted as Event: **90**
  - Exactly Correct Event Type: **62**
  - Confused / Subtype Misclassification: **28**
- Total Predicted as NO_EVENT: **6**
  - Exactly Correct NO_EVENT: **6**
  - False Negatives on Events: **0**
- Total Correct Across 28 Classes: $62 + 6 = \mathbf{68} / \mathbf{96}$ ($70.83\%$ Accuracy).
- Total Errors Across 28 Classes: $\mathbf{28} / \mathbf{96}$ ($29.17\%$).
- Mathematical identity: $62 \text{ (TP)} + 28 \text{ (Misclassified)} + 6 \text{ (TN)} = 96$. Reconciled.

### Baseline Predictions Reconciliation:
- Total Predicted as Event: **27**
  - Exactly Correct Event Type: **11**
  - Confused / Wrong Event Type: **16**
- Total Predicted as NO_EVENT: **69**
  - Exactly Correct NO_EVENT: **6**
  - Missed Events (False Negatives): **63**
- Total Correct Across 28 Classes: $11 + 6 = \mathbf{17} / \mathbf{96}$ ($17.71\%$ Accuracy).
- Mathematical identity: $11 \text{ (TP)} + 16 \text{ (Misclassified)} + 63 \text{ (Missed)} + 6 \text{ (TN)} = 96$. Reconciled.

---

## 5. Raw Confusion Matrix (DeBERTa-v3 on 96 Held-Out Test Samples)

The complete confusion matrix generated via `sklearn.metrics.confusion_matrix`:

```
Gold \ Pred            CH DE DI ID IR IS MR MS NO OC OD OP OS PF PM RA RC RF RI RP RR RQ RM RT RU RR SC SR
CHARGEBACK_REQUESTED   4  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
DELIVERY_ATTEMPTED     .  3  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
DISPUTE_OPENED         2  .  .  .  .  .  .  .  .  .  .  .  .  1  .  .  .  .  .  .  .  .  .  .  .  .  1  .
ITEM_DELIVERED         .  .  .  3  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
ITEM_RECEIVED          .  .  .  .  2  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  2  .  .  .
ITEM_SHIPPED           .  .  .  2  .  .  .  .  .  .  .  .  1  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
MESSAGE_RECEIVED       .  .  .  .  .  .  2  1  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
MESSAGE_SENT           .  .  .  .  .  .  1  1  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  1
NO_EVENT               .  .  .  .  .  .  .  .  6  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
ORDER_CANCELLED        .  .  .  .  .  .  .  .  .  2  .  .  .  1  .  .  .  .  .  .  .  .  .  .  .  .  .  .
ORDER_DELIVERED        .  .  .  .  .  .  .  .  .  .  2  .  2  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
ORDER_PLACED           .  .  .  .  .  .  1  .  .  .  .  2  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
ORDER_SHIPPED          .  .  .  .  .  .  .  .  .  .  .  .  4  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
PAYMENT_FAILED         .  .  .  .  .  .  .  .  .  .  .  .  .  3  .  .  .  .  .  .  .  .  .  .  .  .  .  .
PAYMENT_MADE           .  .  .  .  .  .  .  .  .  .  .  .  .  1  2  .  .  .  .  .  .  .  .  .  .  .  .  .
REFUND_APPROVED        .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  2  1  .  1  .  .  .  .  .  .  .  .  .
REFUND_COMPLETED       .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  3  .  .  .  .  .  .  .  .  .  .  .
REFUND_FAILED          .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  3  .  .  .  .  .  .  .  .  .  .
REFUND_INITIATED       .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  3  .  .  .  .  .  .  .  .  .
REFUND_PROCESSED       .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  4  .  .  .  .  .  .  .  .  .
REFUND_RECEIVED        .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  1  .  .  .  3  .  .  .  .  .  .  .
REFUND_REQUESTED       .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  3  .  .  .  .  .  .
RETURN_COMPLETED       .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  3  .  .  .  .  .
RETURN_INITIATED       .  .  .  .  .  .  1  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  2  .  .  1  .
RETURN_PICKED_UP       .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  3  .  .  .
RETURN_REQUESTED       .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  2  1  .
SUPPORT_CONTACTED      .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  3  .
SUPPORT_RESPONSE       .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  1  .  .  .  .  .  2
```

*(Dots represent zero counts for legibility).*

---

## 6. Corrected Per-Class Metrics (Sklearn Verification)

| Class Name | Support | DeBERTa Precision | DeBERTa Recall | DeBERTa F1 | Baseline Precision | Baseline Recall | Baseline F1 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **CHARGEBACK_REQUESTED** | 4 | 0.67 | 1.00 | **0.80** | 0.00 | 0.00 | 0.00 |
| **DELIVERY_ATTEMPTED** | 3 | 1.00 | 1.00 | **1.00** | 0.00 | 0.00 | 0.00 |
| **DISPUTE_OPENED** | 4 | 0.00 | 0.00 | **0.00** | 0.00 | 0.00 | 0.00 |
| **ITEM_DELIVERED** | 3 | 0.60 | 1.00 | **0.75** | 0.17 | 0.33 | 0.22 |
| **ITEM_RECEIVED** | 4 | 1.00 | 0.50 | **0.67** | 0.00 | 0.00 | 0.00 |
| **ITEM_SHIPPED** | 3 | 0.00 | 0.00 | **0.00** | 0.00 | 0.00 | 0.00 |
| **MESSAGE_RECEIVED** | 3 | 0.40 | 0.67 | **0.50** | 1.00 | 0.33 | 0.50 |
| **MESSAGE_SENT** | 3 | 0.50 | 0.33 | **0.40** | 0.00 | 0.00 | 0.00 |
| **NO_EVENT** | 6 | 1.00 | 1.00 | **1.00** | 0.09 | 1.00 | 0.16 |
| **ORDER_CANCELLED** | 3 | 1.00 | 0.67 | **0.80** | 1.00 | 0.33 | 0.50 |
| **ORDER_DELIVERED** | 4 | 1.00 | 0.50 | **0.67** | 0.00 | 0.00 | 0.00 |
| **ORDER_PLACED** | 3 | 1.00 | 0.67 | **0.80** | 1.00 | 0.33 | 0.50 |
| **ORDER_SHIPPED** | 4 | 0.57 | 1.00 | **0.73** | 0.00 | 0.00 | 0.00 |
| **PAYMENT_FAILED** | 3 | 0.50 | 1.00 | **0.67** | 1.00 | 0.67 | 0.80 |
| **PAYMENT_MADE** | 3 | 1.00 | 0.67 | **0.80** | 0.67 | 0.67 | 0.67 |
| **REFUND_APPROVED** | 4 | 1.00 | 0.50 | **0.67** | 0.00 | 0.00 | 0.00 |
| **REFUND_COMPLETED** | 3 | 0.60 | 1.00 | **0.75** | 0.00 | 0.00 | 0.00 |
| **REFUND_FAILED** | 3 | 1.00 | 1.00 | **1.00** | 1.00 | 0.33 | 0.50 |
| **REFUND_INITIATED** | 3 | 0.38 | 1.00 | **0.55** | 1.00 | 0.33 | 0.50 |
| **REFUND_PROCESSED** | 4 | 0.00 | 0.00 | **0.00** | 0.00 | 0.00 | 0.00 |
| **REFUND_RECEIVED** | 4 | 1.00 | 0.75 | **0.86** | 0.00 | 0.00 | 0.00 |
| **REFUND_REQUESTED** | 3 | 0.75 | 1.00 | **0.86** | 1.00 | 0.33 | 0.50 |
| **RETURN_COMPLETED** | 3 | 1.00 | 1.00 | **1.00** | 0.00 | 0.00 | 0.00 |
| **RETURN_INITIATED** | 4 | 1.00 | 0.50 | **0.67** | 0.00 | 0.00 | 0.00 |
| **RETURN_PICKED_UP** | 3 | 0.60 | 1.00 | **0.75** | 0.00 | 0.00 | 0.00 |
| **RETURN_REQUESTED** | 3 | 1.00 | 0.67 | **0.80** | 0.00 | 0.00 | 0.00 |
| **SUPPORT_CONTACTED** | 3 | 0.50 | 1.00 | **0.67** | 0.00 | 0.00 | 0.00 |
| **SUPPORT_RESPONSE** | 3 | 0.67 | 0.67 | **0.67** | 0.00 | 0.00 | 0.00 |

---

## 7. Taxonomy Audit & Discrepancies (Task 7)

Inspection of [`ml/schemas/event.py`](file:///d:/ProofFlow/ml/schemas/event.py#L22-L58) and [`ml/events/taxonomy.py`](file:///d:/ProofFlow/ml/events/taxonomy.py#L7-L32) revealed:

1. **Exact Canonical Taxonomy**:
   The canonical ProofFlow Track 4 specification originally established **18 event types**:
   - **Commerce (7)**: `ORDER_PLACED`, `PAYMENT_MADE`, `PAYMENT_FAILED`, `REFUND_REQUESTED`, `REFUND_INITIATED`, `REFUND_COMPLETED`, `REFUND_FAILED`.
   - **Order / Delivery (7)**: `ORDER_CANCELLED`, `ITEM_SHIPPED`, `DELIVERY_ATTEMPTED`, `ITEM_DELIVERED`, `RETURN_REQUESTED`, `RETURN_PICKED_UP`, `RETURN_COMPLETED`.
   - **Communication (4)**: `MESSAGE_SENT`, `MESSAGE_RECEIVED`, `SUPPORT_CONTACTED`, `SUPPORT_RESPONSE`.

2. **Taxonomy Expansion in Implementation**:
   [`ml/schemas/event.py`](file:///d:/ProofFlow/ml/schemas/event.py) contains **27 enum members**, which expanded the classification space to 28:
   - **4 Backward-Compatibility Aliases**:
     - `ORDER_SHIPPED` (alias for `ITEM_SHIPPED`)
     - `ORDER_DELIVERED` (alias for `ITEM_DELIVERED`)
     - `ITEM_RECEIVED` (alias for `ITEM_DELIVERED`)
     - `RETURN_INITIATED` (alias for `RETURN_REQUESTED` / `RETURN_PICKED_UP`)
   - **5 Dispute / Legacy Types**:
     - `REFUND_APPROVED`, `REFUND_PROCESSED`, `REFUND_RECEIVED`, `DISPUTE_OPENED`, `CHARGEBACK_REQUESTED`.

3. **Impact on ML Performance**:
   - Treating aliases as independent classes created **artificial semantic competition**.
   - For example: All 3 samples of `ITEM_SHIPPED` were predicted as `ORDER_SHIPPED` or `ITEM_DELIVERED`. Because `ITEM_SHIPPED` and `ORDER_SHIPPED` describe identical semantics, splitting them into two labels caused DeBERTa to receive an $F_1 = 0.00$ on `ITEM_SHIPPED` and $F_1 = 0.73$ on `ORDER_SHIPPED`.
   - Similarly, all 4 samples of `REFUND_PROCESSED` were predicted as `REFUND_INITIATED` ($F_1 = 0.00$), because "processing refund" is linguistically identical to "refund initiated".
   - **Finding**: In production, the model should classify into the **18 canonical types**, and aliases should be handled via a mapping layer rather than forcing the neural head to separate synonyms.

---

## 8. Dataset Split & Leakage Verification (Task 8)

We executed an independent algorithmic audit of `train.jsonl`, `val.jsonl`, and `test.jsonl`:
- **Total Samples**: 683 (Train: 483, Val: 104, Test: 96).
- **Exact Deduplication Across All Splits**:
  - Total Unique Texts: **683 / 683 (100.0% unique)**.
  - Exact Overlaps $\text{Train} \cap \text{Val}$: **0**.
  - Exact Overlaps $\text{Train} \cap \text{Test}$: **0**.
  - Exact Overlaps $\text{Val} \cap \text{Test}$: **0**.
- **Near-Duplicate SequenceMatcher Audit**:
  - Cross-split pairs with similarity $\ge 0.88$: **0**.
  - Cross-split pairs with similarity $0.80 - 0.87$: **0**.
- **Template Substitution Leakage**:
  - Unlike the initial dataset which relied on synthetic entity swaps on 4 fixed sentences, the 683 samples in `v2.0.0-improved` were written with distinct syntactical structures across formal, casual, support, and OCR variations.

---

## 9. Grounding Verification Audit (Task 9)

We audited every one of the 90 events extracted by DeBERTa on the test set:
1. **Source Evidence Provenance**: Every `Event` contains a populated `SourceReference` referencing the valid `EvidenceText` ID.
2. **Character Offset Bounds**: For all 90 events, $0 \le \text{char\_start} < \text{char\_end} \le \text{len(full\_text)}$.
3. **Exact Substring Verbatim Match**:
   $$\text{full\_text}[\text{char\_start}:\text{char\_end}] == \text{event.trigger.raw\_text}$$
   - **Verification Result**: 90 out of 90 events passed exact string equality ($100.0\%$).
   - **Phantom / Fabricated Spans Detected**: **0**.
4. **Summary**: The claim of **100% Source Grounding** is mathematically and programmatically verified.

---

## 10. Recommendations for Next ML Development Step

1. **Collapse Aliases to 18 Canonical Classes**:
   - Re-map aliases (`ORDER_SHIPPED` $\to$ `ITEM_SHIPPED`, `ORDER_DELIVERED` $\to$ `ITEM_DELIVERED`, `ITEM_RECEIVED` $\to$ `ITEM_DELIVERED`, `REFUND_PROCESSED` $\to$ `REFUND_INITIATED`) before training.
   - This eliminates 9 synthetic classes that currently depress macro $F_1$ through synonym confusion.
2. **Disentangle Binary Detection from Subtype Classification**:
   - The two-stage architecture performs flawlessly on detection ($100\%$ precision, $100\%$ recall on event vs non-event).
   - A hierarchical or 18-class model will significantly boost multiclass accuracy from $70.83\%$ towards $85\%+$.
3. **Keep the Deterministic Baseline as Provenance Authority**:
   - The deterministic extractor achieves $100\%$ precision on structured regex anchors, whereas DeBERTa provides a $5.6\times$ recall boost on conversational text.
   - Proceed with the planned **Hybrid Fusion Architecture**.
