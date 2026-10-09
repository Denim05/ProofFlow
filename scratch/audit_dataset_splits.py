import json
from collections import Counter
from difflib import SequenceMatcher

def load(path):
    with open(path, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]

train = load('ml/events/data/train.jsonl')
val = load('ml/events/data/val.jsonl')
test = load('ml/events/data/test.jsonl')

print(f"Split counts: Train={len(train)}, Val={len(val)}, Test={len(test)}, Total={len(train)+len(val)+len(test)}")

all_samples = train + val + test
texts = [s['text'].strip().lower() for s in all_samples]
print(f"Unique texts across all splits: {len(set(texts))} / {len(texts)}")

train_t = set(s['text'].strip().lower() for s in train)
val_t = set(s['text'].strip().lower() for s in val)
test_t = set(s['text'].strip().lower() for s in test)

print("Exact overlaps:")
print(f"  Train-Val: {len(train_t & val_t)}")
print(f"  Train-Test: {len(train_t & test_t)}")
print(f"  Val-Test: {len(val_t & test_t)}")

near_88, near_80 = [], []
for t_s in test:
    for tr_s in train:
        sim = SequenceMatcher(None, t_s['text'].lower(), tr_s['text'].lower()).ratio()
        if sim >= 0.88:
            near_88.append((sim, t_s['text'], tr_s['text']))
        elif sim >= 0.80:
            near_80.append((sim, t_s['text'], tr_s['text']))

print(f"Near duplicates Train-Test (>=0.88): {len(near_88)}")
print(f"Near duplicates Train-Test (0.80-0.87): {len(near_80)}")
if near_80:
    for sim, t1, t2 in near_80[:5]:
        print(f"  Sim {sim:.2f}: \"{t1}\" vs \"{t2}\"")

# Class breakdown in test
test_counts = Counter(s['event_type'] for s in test)
print("\nTest Class Distribution:")
for c, cnt in sorted(test_counts.items(), key=lambda x: -x[1]):
    print(f"  {c:<25}: {cnt}")
