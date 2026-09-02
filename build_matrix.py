from __future__ import annotations

import json

from catalog_builder import write_artifacts


if __name__ == "__main__":
    print(json.dumps(write_artifacts(strict=True), ensure_ascii=False))
