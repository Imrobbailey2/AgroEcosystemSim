# Schemas

JSON Schemas shared by the game (`/game`) and the data pipeline (`/pipeline`).

| Schema | Describes |
|---|---|
| `datapack.schema.json` | A region data pack. Definitions (`$defs`) cover sources, review flags, soil-test ratings, soil units and layers, crops, custom operations (equipment hired as custom work), budgets, tenure options, market channels and weather years. |

Every number in a data pack must be covered by a `prov` object citing a
registered source and a location; `agroeco-pipeline validate` enforces this in
addition to the schema.

Input-product prices (fertilizer, lime, seed) are not yet separate records in
v0: they are carried in the budget lines with cell references and will be
mapped to typed products in Increment 5 (Economics).
