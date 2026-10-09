import json
import os

mrc_path = r"f:\project\mrc-for-flat-nested-ner\datasets\work_ticket\mrc-ner.train"
with open(mrc_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

short_entities = []
for d in data:
    context = d['context'].replace(' ', '')
    for s, e in zip(d['start_position'], d['end_position']):
        entity = context[s:e+1]
        if len(entity) == 1:
            short_entities.append({
                'label': d['entity_label'],
                'entity': entity,
                'context': context
            })

print(f"Total short entities (1 char): {len(short_entities)}")
for item in short_entities[:20]:
    print(f"[{item['label']}] '{item['entity']}' in '{item['context'][:50]}...'")
