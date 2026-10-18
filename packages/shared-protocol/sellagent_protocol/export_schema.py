"""Write JSON Schema files for every protocol message. Run: python -m sellagent_protocol.export_schema"""

import json
import sys
from pathlib import Path

from sellagent_protocol.messages import PROTOCOL_VERSION, export_json_schemas


def main(out_dir: str | None = None) -> int:
    target = Path(out_dir) if out_dir else Path(__file__).resolve().parent.parent / "schema"
    target.mkdir(parents=True, exist_ok=True)
    schemas = export_json_schemas()
    for name, schema in schemas.items():
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["x-protocol-version"] = PROTOCOL_VERSION
        (target / f"{name.replace('.', '_')}.schema.json").write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    (target / "INDEX.json").write_text(
        json.dumps({"protocol_version": PROTOCOL_VERSION, "messages": sorted(schemas)}, indent=2) + "\n"
    )
    print(f"wrote {len(schemas)} schemas to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
