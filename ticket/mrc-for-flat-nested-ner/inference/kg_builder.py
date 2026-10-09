import json
import uuid
from datetime import datetime

class KnowledgeGraphBuilder:
    def __init__(self):
        self.nodes = []
        self.relationships = []
        self.person_cache = {}
        self.device_cache = {}
        self.location_cache = {}

    def clean_value(self, value):
        if not value:
            return ""
        return value.replace("'", "\\'").replace('"', '\\"')

    def process_ner_results(self, ner_result):
        """
        Process NER results and build graph structure.
        Expects ner_result to be a dict with 'blocks' containing 'entities'.
        """
        # Aggregate entities from all blocks
        all_entities = {}
        for block in ner_result.get("blocks", []):
            for entity in block.get("entities", []):
                label = entity['type']
                text = entity['text']
                if label not in all_entities:
                    all_entities[label] = []
                all_entities[label].append(text)

        # 1. Create WorkTask Node
        ticket_no = all_entities.get("工作票编号", ["Unknown_" + str(uuid.uuid4())[:8]])[0]
        work_content = " ".join(all_entities.get("工作任务", []))
        
        task_id = f"task_{ticket_no}"
        task_props = {
            "id": task_id,
            "ticket_no": ticket_no,
            "content": work_content,
            "created_at": datetime.now().isoformat()
        }
        
        # Handle Time
        times = all_entities.get("计划工作时间", [])
        if times:
            task_props["planned_time"] = " | ".join(times)

        self.create_node("WorkTask", task_props)

        # 2. Create Person Nodes and Relationships
        # Assuming '工作负责人' is a label
        managers = all_entities.get("工作负责人", [])
        for person_name in managers:
            person_id = self.get_or_create_person(person_name)
            self.create_relationship(person_id, "RESPONSIBLE_FOR", task_id, {"role": "负责人"})
            
        members = all_entities.get("工作班成员", [])
        for person_name in members:
            person_id = self.get_or_create_person(person_name)
            self.create_relationship(person_id, "RESPONSIBLE_FOR", task_id, {"role": "成员"})

        # 3. Create Device Nodes
        devices = all_entities.get("设备名称", [])
        for device_name in devices:
            device_id = self.get_or_create_device(device_name)
            self.create_relationship(task_id, "ACTS_ON", device_id)

        # 4. Create Location Nodes
        locations = all_entities.get("工作地点", [])
        for loc_name in locations:
            loc_id = self.get_or_create_location(loc_name)
            # Relationship between Task and Location? Or Device and Location?
            # Technical route says Device LOCATED_AT Location.
            # But usually we also know Task is at Location.
            # For now, let's link Task to Location directly for simplicity, or inferred from device.
            # Let's link Device to Location if we have pairs, but here we have lists.
            # We'll link Task to Location (HAPPENS_AT - though not explicitly in Section 5.1, it's useful).
            # Section 5.1 says LOCATED_AT connects Device and Location.
            # Let's assume all devices in this ticket are at these locations (simplification).
            for device_name in devices:
                device_id = self.get_or_create_device(device_name)
                self.create_relationship(device_id, "LOCATED_AT", loc_id)

    def get_or_create_person(self, name):
        if name in self.person_cache:
            return self.person_cache[name]
        person_id = f"p_{uuid.uuid5(uuid.NAMESPACE_DNS, name)}"
        self.create_node("Person", {"id": person_id, "name": name})
        self.person_cache[name] = person_id
        return person_id

    def get_or_create_device(self, name):
        if name in self.device_cache:
            return self.device_cache[name]
        device_id = f"d_{uuid.uuid5(uuid.NAMESPACE_DNS, name)}"
        self.create_node("Device", {"id": device_id, "name": name})
        self.device_cache[name] = device_id
        return device_id

    def get_or_create_location(self, name):
        if name in self.location_cache:
            return self.location_cache[name]
        loc_id = f"l_{uuid.uuid5(uuid.NAMESPACE_DNS, name)}"
        self.create_node("Location", {"id": loc_id, "name": name})
        self.location_cache[name] = loc_id
        return loc_id

    def create_node(self, label, properties):
        props_str = ", ".join([f"{k}: '{self.clean_value(str(v))}'" for k, v in properties.items()])
        query = f"MERGE (n:{label} {{id: '{properties['id']}'}}) ON CREATE SET n += {{{props_str}}} ON MATCH SET n += {{{props_str}}}"
        self.nodes.append(query)

    def create_relationship(self, start_id, rel_type, end_id, properties=None):
        props_str = ""
        if properties:
            props_str = " {" + ", ".join([f"{k}: '{self.clean_value(str(v))}'" for k, v in properties.items()]) + "}"
        
        query = f"""
        MATCH (a), (b)
        WHERE a.id = '{start_id}' AND b.id = '{end_id}'
        MERGE (a)-[r:{rel_type}]->(b)
        {f"SET r += {props_str}" if properties else ""}
        """
        self.relationships.append(query.strip())

    def generate_cypher(self):
        return "\n".join(self.nodes + self.relationships)

    def save_cypher(self, output_path):
        content = self.generate_cypher()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        return content

if __name__ == "__main__":
    # Test
    pass
