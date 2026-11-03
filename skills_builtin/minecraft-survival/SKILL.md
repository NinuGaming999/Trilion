---
name: minecraft-survival
description: Basic Minecraft survival loop: wood, crafting, tools, food, safety. Load this when asked to gather or survive.
---
1. Punch a tree: mc_aim at a log, mc_walk forward until it is close, mc_mine about 3000 ms per log (look to confirm it broke). Collect 4-6 logs.
2. Crafting: mc_inventory opens a 2x2 grid with a recipe book button next to it. Click the recipe book, click the wanted recipe (planks, then crafting table), then shift-click the result with game_click shift=true. Place the crafting table: mc_hotbar to its slot, mc_aim at the ground, mc_use. Right-click it with mc_use to get the 3x3 grid, then use the recipe book again for sticks and a wooden pickaxe.
3. Progress: wooden pickaxe, then stone (mine stone with the pickaxe), stone pickaxe, torches, a shelter before night.
4. Eat when the hunger bar drops: select the food with mc_hotbar, then mc_use with ms 1700 to hold it.
5. Safety: check hearts every step. At night or when a hostile mob is close, fight with mc_attack or retreat and block yourself in. Never dig straight down, keep away from lava and water edges.
