# Project principles

Status: adopted by the project owner 2026-11-16. Applies to every increment
from Increment 3 on.

## Purpose of the game

The Florida Agroecosystem Farm Simulator measures how well the player builds a
healthy, sustainable agroecosystem. **Profit is not the goal.** Money is a
constraint the player has to live within: costs, prices and land costs in the
data pack stay real and cited, but income is only one part of one score.

The project uses the term *agroecology*. Permaculture fits inside it as a
design approach, so requirements say "agroecology (permaculture-compatible)".

## Framework: four foundational principles

Brym and Reeve (2016) found that agroecology's competing agendas share four
principles. The UF/IFAS guide *Introducing Agroecology* (Brym, Cohen, Wooten,
Matcham and Outerbridge, EDIS SS-AGR-476/AG472, June 2023,
https://doi.org/10.32473/edis-ag472-2023) defines them for practice:

| Principle | Definition (AG472) | How the game will use it (scoring increment) |
|---|---|---|
| Productivity | Materials and wealth generated through both biological and economic currencies such as biomass, carbon, nitrogen, yield and income | Biomass, soil carbon, nitrogen balance, yield and net income, each scored; income is one input, not the total |
| Diversity | The plants, animals, microbes, fungi and cultures coexisting in an environment that promotes beneficial interaction | Crop and cover-crop diversity, hedgerows, buffers, habitat, livestock integration |
| Resilience | The ability to maintain or rebound productivity, biodiversity and community after hardship or disturbance such as extreme weather, pests or disease, or market failure | Performance across dry, median and wet weather years and price shocks; recovery after a bad year |
| Systems thinking | Reflection and planning that looks at how agricultural, ecological and social factors are interconnected | Rewards decisions that link fields, neighbours, water and community (for example riparian buffers, nutrient recycling, fair labour) |

AG472's "getting started" steps already describe the game loop: map your
agroecosystem (including zoning), set 1-year and 5-year targets, act, evaluate.
Increment 3 builds the first step (the county map).

## Rules for later increments

1. No increment may introduce profit, revenue or net worth as the single
   end-of-game score.
2. Every scored quantity must cite a source, like every data-pack value.
3. Scoring weights are data (in a pack or config), not code, so they can be
   reviewed with the agroecology expert at the end of the project (see
   `docs/deferred-items.md`).
4. Accessibility and the data-privacy rules in `CONTRIBUTING.md` still apply.

Scoring itself is out of scope for Increment 3. This document must be merged
before the scoring work starts.
