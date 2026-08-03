"""Data-driven multi-step expedition rules for the Doupo game."""

from __future__ import annotations

from typing import Any


EXPEDITION_REGIONS: list[dict[str, Any]] = [
    {
        "key": "magic_beast_mountains",
        "name": "魔兽山脉",
        "description": "林海中药材与低阶魔核丰富，适合初次游历。",
        "realm_stage_min": "斗之气",
        "recommended_power": 1200,
        "entry_gold": 0,
        "max_steps": 4,
        "event_keys": ["beast_tracks", "herb_valley", "hidden_cave", "lost_mercenary"],
        "completion_bonus": {
            "douqi": 70,
            "gold": 28,
            "items": {"monster_core_low": 1},
        },
    },
    {
        "key": "tagor_desert",
        "name": "塔戈尔沙漠",
        "description": "高温与蛇人巡逻并存，能寻到护火药材和异火踪迹。",
        "realm_stage_min": "斗者",
        "recommended_power": 13500,
        "entry_gold": 40,
        "max_steps": 5,
        "event_keys": ["desert_storm", "snake_patrol", "fire_vein", "desert_caravan"],
        "completion_bonus": {
            "douqi": 130,
            "gold": 55,
            "items": {"qinglian_fire_map": 1},
        },
    },
    {
        "key": "black_corner",
        "name": "黑角域",
        "description": "没有规矩的险地，回报丰厚，但每一步都可能遭到截杀。",
        "realm_stage_min": "大斗师",
        "recommended_power": 34000,
        "entry_gold": 100,
        "max_steps": 6,
        "event_keys": ["black_market", "road_ambush", "ancient_ruin", "black_corner_pit"],
        "completion_bonus": {
            "douqi": 220,
            "gold": 110,
            "items": {"monster_core_mid": 1, "mitel_auction_token": 1},
        },
    },
    {
        "key": "canaan_inner_academy",
        "name": "迦南学院内院",
        "description": "火能森林、天焚炼气塔和寒潭矿洞交错，适合中阶修士采集炼器材料。",
        "realm_stage_min": "大斗师",
        "recommended_power": 52000,
        "entry_gold": 90,
        "max_steps": 6,
        "event_keys": ["fire_energy_forest", "tower_magma_tunnel", "inner_courtyard_market", "thunder_cliff"],
        "completion_bonus": {
            "douqi": 250,
            "gold": 90,
            "items": {"fire_energy_crystal": 1, "cold_iron_ore": 1},
        },
    },
    {
        "key": "central_plains_dan_domain",
        "name": "中州丹域",
        "description": "丹塔势力辐射的繁盛区域，药田、兽火谷与空间驿站中藏有高阶资源。",
        "realm_stage_min": "斗王",
        "recommended_power": 98000,
        "entry_gold": 180,
        "max_steps": 6,
        "event_keys": ["dan_domain_herb_field", "space_wormhole", "beast_flame_valley", "danta_ruins"],
        "completion_bonus": {
            "douqi": 360,
            "gold": 150,
            "items": {"danta_exam_token": 1, "earth_core_body_milk": 1},
        },
    },
    {
        "key": "ancient_starfall_ruins",
        "name": "星陨阁远古遗迹",
        "description": "空间裂缝后的远古药园与龙池残迹，稀有资源丰厚，危险也远超寻常区域。",
        "realm_stage_min": "斗宗",
        "recommended_power": 185000,
        "entry_gold": 320,
        "max_steps": 7,
        "event_keys": ["starfall_forest", "ancient_dragon_pool", "void_stone_chamber", "reincarnation_garden"],
        "completion_bonus": {
            "douqi": 520,
            "gold": 240,
            "items": {"starfall_token": 1, "meteorite_iron": 1, "space_stone": 1},
        },
    },
]


EXPEDITION_EVENTS: dict[str, dict[str, Any]] = {
    "beast_tracks": {
        "title": "密林兽踪",
        "story": "潮湿泥地上留着新鲜爪印，前方灌木间传来低沉兽吼。",
        "choices": [
            {
                "key": "detour",
                "label": "绕路采集",
                "description": "避开正面冲突，沿林缘搜集药材。",
                "risk": "稳妥",
                "base_chance": 100,
                "success": {"damage": [0, 3], "douqi": [8, 16], "gold": [2, 7], "danger": -1, "drops": {"ice_spirit_flame_grass": 45, "clotting_grass": 75, "purple_blue_leaf": 55}},
            },
            {
                "key": "hunt",
                "label": "设伏猎杀",
                "description": "判断行进路线后设伏，正面争夺魔核。",
                "risk": "均衡",
                "base_chance": 74,
                "success": {"damage": [4, 10], "douqi": [25, 48], "gold": [8, 18], "danger": 1, "drops": {"monster_core_low": 78, "beast_bone_shard": 68, "beast_hide": 52}},
                "failure": {"damage": [17, 28], "douqi": [4, 10], "gold": [0, 3], "danger": 2},
            },
            {
                "key": "track_nest",
                "label": "追入巢穴",
                "description": "追踪到巢穴深处，赌一次稀有收获。",
                "risk": "凶险",
                "base_chance": 56,
                "success": {"damage": [8, 15], "douqi": [40, 72], "gold": [14, 28], "danger": 2, "drops": {"monster_core_low": 100, "monster_core_mid": 24, "beast_bone_shard": 100, "beast_hide": 72}},
                "failure": {"damage": [24, 38], "douqi": [5, 14], "gold": [0, 4], "danger": 3},
            },
        ],
    },
    "herb_valley": {
        "title": "幽谷药香",
        "story": "山风送来浓郁药香，谷底灵草成片，岩壁上却盘踞着守药魔兽。",
        "choices": [
            {"key": "edge", "label": "谷口采药", "description": "只取外围成熟药草。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [0, 2], "douqi": [6, 13], "gold": [1, 5], "danger": -1, "drops": {"ice_spirit_flame_grass": 80, "snake_shed_grass": 38, "clotting_grass": 85, "bone_growth_flower": 65, "purple_blue_leaf": 72}}},
            {"key": "lure", "label": "引兽离谷", "description": "制造声响引开魔兽，再进入谷底。", "risk": "均衡", "base_chance": 70, "success": {"damage": [3, 8], "douqi": [18, 35], "gold": [5, 12], "danger": 1, "drops": {"blood_lotus_essence": 70, "seven_leaf_lotus": 18}}, "failure": {"damage": [14, 24], "douqi": [3, 8], "danger": 2}},
            {"key": "challenge", "label": "强夺灵药", "description": "击败守药魔兽，搜尽谷底。", "risk": "凶险", "base_chance": 54, "success": {"damage": [8, 14], "douqi": [35, 62], "gold": [10, 20], "danger": 2, "drops": {"blood_lotus_essence": 100, "seven_leaf_lotus": 42}}, "failure": {"damage": [23, 36], "douqi": [4, 10], "danger": 3}},
        ],
    },
    "hidden_cave": {
        "title": "前人洞府",
        "story": "藤蔓后露出半扇石门，门内斗气流转，禁制尚未完全消散。",
        "choices": [
            {"key": "meditate", "label": "门外感悟", "description": "不触碰禁制，只借残余斗气修炼。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [0, 2], "douqi": [20, 34], "gold": [0, 3], "danger": -1}},
            {"key": "probe", "label": "破解禁制", "description": "寻找禁制薄弱处进入外室。", "risk": "均衡", "base_chance": 68, "success": {"damage": [3, 9], "douqi": [26, 48], "gold": [12, 24], "danger": 1, "drops": {"black_iron_ore": 65, "green_rock_ore": 78, "spirit_pattern_wood": 32, "flame_method_fragment": 12}}, "failure": {"damage": [16, 27], "douqi": [5, 10], "danger": 2}},
            {"key": "break", "label": "强破石门", "description": "以斗技撼动整座禁制。", "risk": "凶险", "base_chance": 50, "success": {"damage": [9, 16], "douqi": [45, 78], "gold": [20, 38], "danger": 2, "drops": {"flame_method_fragment": 40, "baji_beng_scroll": 10}}, "failure": {"damage": [27, 42], "douqi": [4, 12], "danger": 3}},
        ],
    },
    "lost_mercenary": {
        "title": "负伤佣兵",
        "story": "一名佣兵靠在树下喘息，包裹散落在远处，附近似乎还有追兵。",
        "choices": [
            {"key": "guide", "label": "指明归路", "description": "提供方向后继续上路。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [0, 1], "douqi": [8, 15], "gold": [5, 10], "danger": -1}},
            {"key": "escort", "label": "护送离山", "description": "护送佣兵穿过魔兽活动区。", "risk": "均衡", "base_chance": 76, "success": {"damage": [3, 8], "douqi": [18, 32], "gold": [16, 28], "danger": 0, "drops": {"healing_powder": 35}}, "failure": {"damage": [12, 22], "douqi": [3, 8], "danger": 2}},
            {"key": "recover_pack", "label": "夺回包裹", "description": "循着痕迹追击劫匪。", "risk": "凶险", "base_chance": 58, "success": {"damage": [7, 14], "douqi": [32, 58], "gold": [25, 44], "danger": 2, "drops": {"monster_core_low": 55, "beast_hide": 65, "beast_bone_shard": 72}}, "failure": {"damage": [22, 34], "douqi": [4, 10], "danger": 3}},
        ],
    },
    "desert_storm": {
        "title": "黑沙暴",
        "story": "天际卷起黑色沙墙，火属性能量在风暴中心躁动不休。",
        "choices": [
            {"key": "shelter", "label": "寻找背风处", "description": "保存体力，等待风暴减弱。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [2, 6], "douqi": [10, 18], "gold": [0, 4], "danger": -2}},
            {"key": "cross", "label": "斗气护体", "description": "以斗气护住经脉，穿越沙墙。", "risk": "均衡", "base_chance": 70, "success": {"damage": [6, 12], "douqi": [30, 52], "gold": [8, 16], "danger": 1, "drops": {"snake_shed_grass": 62}}, "failure": {"damage": [20, 32], "douqi": [6, 12], "danger": 2}},
            {"key": "center", "label": "追逐火流", "description": "深入风暴中心吸收火属性能量。", "risk": "凶险", "base_chance": 52, "success": {"damage": [10, 18], "douqi": [48, 82], "gold": [12, 24], "danger": 3, "drops": {"earth_core_fire_mushroom": 70, "fire_spirit_root": 58, "flame_crystal_core": 36, "qinglian_fire_map": 18}}, "failure": {"damage": [28, 44], "douqi": [5, 13], "danger": 4}},
        ],
    },
    "snake_patrol": {
        "title": "蛇人巡队",
        "story": "蛇人巡逻队封锁了绿洲入口，沙丘后还能看见一条隐蔽小径。",
        "choices": [
            {"key": "wait", "label": "隐匿等待", "description": "收敛气息，等巡队离开。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [1, 4], "douqi": [9, 16], "gold": [2, 6], "danger": -1}},
            {"key": "trail", "label": "潜行小径", "description": "借沙丘遮蔽绕过封锁。", "risk": "均衡", "base_chance": 72, "success": {"damage": [4, 9], "douqi": [24, 43], "gold": [10, 20], "danger": 1, "drops": {"snake_shed_grass": 75, "blood_lotus_essence": 35}}, "failure": {"damage": [17, 28], "douqi": [4, 9], "danger": 3}},
            {"key": "breakthrough", "label": "正面突围", "description": "击溃巡队，夺取补给。", "risk": "凶险", "base_chance": 55, "success": {"damage": [9, 16], "douqi": [42, 70], "gold": [18, 34], "danger": 3, "drops": {"snake_people_token": 45, "scale_guard_armor": 8}}, "failure": {"damage": [26, 40], "douqi": [5, 12], "danger": 4}},
        ],
    },
    "fire_vein": {
        "title": "地火裂隙",
        "story": "岩层裂开一道赤红缝隙，精纯火劲不断涌出，深处隐约有异火气息。",
        "choices": [
            {"key": "observe", "label": "记录火脉", "description": "观察流向并记录安全路线。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [1, 5], "douqi": [14, 24], "gold": [2, 7], "danger": -1, "drops": {"earth_core_fire_mushroom": 35}}},
            {"key": "temper", "label": "引火淬体", "description": "引导地火淬炼经脉。", "risk": "均衡", "base_chance": 67, "success": {"damage": [7, 13], "douqi": [36, 64], "gold": [7, 14], "danger": 2, "drops": {"earth_core_fire_mushroom": 72}}, "failure": {"damage": [22, 35], "douqi": [8, 16], "danger": 3}},
            {"key": "descend", "label": "深入裂隙", "description": "向异火气息最浓处深入。", "risk": "凶险", "base_chance": 48, "success": {"damage": [12, 20], "douqi": [58, 96], "gold": [15, 30], "danger": 4, "drops": {"qinglian_fire_map": 52, "fallen_heart_flame_trace": 14, "fire_spirit_root": 64, "flame_crystal_core": 42}}, "failure": {"damage": [32, 48], "douqi": [7, 18], "danger": 5}},
        ],
    },
    "desert_caravan": {
        "title": "沙漠商队",
        "story": "一支商队被流沙困住，领队愿意用货物换取援手。",
        "choices": [
            {"key": "directions", "label": "告知水源", "description": "交换地图情报，各自赶路。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [0, 2], "douqi": [7, 14], "gold": [8, 14], "danger": -1}},
            {"key": "rescue", "label": "协助脱困", "description": "以斗气托起陷入流沙的货车。", "risk": "均衡", "base_chance": 78, "success": {"damage": [3, 8], "douqi": [20, 36], "gold": [20, 34], "danger": 0, "drops": {"fire_guard_pill": 32}}, "failure": {"damage": [12, 22], "douqi": [4, 9], "danger": 2}},
            {"key": "escort", "label": "护送穿沙", "description": "一路护送到下一处据点。", "risk": "凶险", "base_chance": 60, "success": {"damage": [7, 14], "douqi": [34, 60], "gold": [34, 56], "danger": 2, "drops": {"mitel_auction_token": 38}}, "failure": {"damage": [21, 34], "douqi": [5, 11], "danger": 3}},
        ],
    },
    "black_market": {
        "title": "黑市暗局",
        "story": "摊主压低声音兜售来路不明的纳戒，几道目光同时盯上了你。",
        "choices": [
            {"key": "leave", "label": "识破离场", "description": "不碰赃物，记下黑市布局。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [0, 3], "douqi": [12, 22], "gold": [5, 12], "danger": -1}},
            {"key": "bargain", "label": "压价交易", "description": "利用对方急于出手的心理周旋。", "risk": "均衡", "base_chance": 66, "success": {"damage": [2, 7], "douqi": [28, 48], "gold": [28, 50], "danger": 2, "drops": {"monster_core_mid": 36}}, "failure": {"damage": [18, 30], "douqi": [4, 10], "danger": 3}},
            {"key": "take_ring", "label": "夺戒反杀", "description": "顺势掀桌，解决埋伏者。", "risk": "凶险", "base_chance": 48, "success": {"damage": [11, 19], "douqi": [55, 90], "gold": [48, 82], "danger": 4, "drops": {"low_grade_storage_ring": 30, "monster_core_high": 18}}, "failure": {"damage": [34, 50], "douqi": [6, 15], "danger": 5}},
        ],
    },
    "road_ambush": {
        "title": "峡谷截杀",
        "story": "峡谷两端同时落下巨石，数名蒙面斗者从岩壁跃下。",
        "choices": [
            {"key": "smoke", "label": "烟尘脱身", "description": "击碎岩壁制造烟尘，保存实力。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [3, 8], "douqi": [14, 26], "gold": [4, 10], "danger": -1}},
            {"key": "leader", "label": "擒贼先擒王", "description": "越过围攻直取领头者。", "risk": "均衡", "base_chance": 64, "success": {"damage": [8, 15], "douqi": [40, 68], "gold": [35, 60], "danger": 2, "drops": {"black_iron_sword": 24}}, "failure": {"damage": [25, 38], "douqi": [6, 13], "danger": 4}},
            {"key": "counter", "label": "全数反杀", "description": "封住退路，以战养战。", "risk": "凶险", "base_chance": 46, "success": {"damage": [14, 23], "douqi": [62, 102], "gold": [60, 96], "danger": 5, "drops": {"monster_core_mid": 68, "flame_guard_bracer": 15}}, "failure": {"damage": [38, 56], "douqi": [8, 18], "danger": 6}},
        ],
    },
    "ancient_ruin": {
        "title": "远古残殿",
        "story": "破败石殿沉在峡谷尽头，墙上残留着高阶斗技运转痕迹。",
        "choices": [
            {"key": "rubbing", "label": "临摹石壁", "description": "只记录可辨认的斗气路线。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [1, 4], "douqi": [24, 40], "gold": [3, 9], "danger": -1}},
            {"key": "outer_hall", "label": "搜寻外殿", "description": "避开主阵，搜索坍塌偏殿。", "risk": "均衡", "base_chance": 62, "success": {"damage": [7, 14], "douqi": [45, 76], "gold": [30, 54], "danger": 2, "drops": {"flame_method_fragment": 55, "thunder_steps_scroll": 16, "meteorite_iron": 32, "space_stone": 10}}, "failure": {"damage": [25, 39], "douqi": [7, 15], "danger": 4}},
            {"key": "main_hall", "label": "闯入主殿", "description": "硬抗残阵，争夺核心传承。", "risk": "凶险", "base_chance": 43, "success": {"damage": [15, 25], "douqi": [75, 120], "gold": [55, 90], "danger": 5, "drops": {"flame_divide_scroll": 34, "thunder_steps_scroll": 30}}, "failure": {"damage": [42, 62], "douqi": [9, 20], "danger": 6}},
        ],
    },
    "black_corner_pit": {
        "title": "黑角域斗兽坑",
        "story": "城下的石坑中传出此起彼伏的嘶吼，围观的斗者把金魂币扔进坑中，赌斗的奴隶与魔兽在血腥味里缠斗。",
        "choices": [
            {"key": "watch", "label": "观战押注", "description": "不下场，只观察斗兽规律并小押一手。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [0, 3], "douqi": [14, 24], "gold": [12, 22], "danger": -1, "drops": {"beast_hide": 45, "black_corner_black_card": 8}}},
            {"key": "fix_fight", "label": "暗手操盘", "description": "暗中买通看台，操纵一场赌斗的走向。", "risk": "均衡", "base_chance": 66, "success": {"damage": [4, 10], "douqi": [34, 58], "gold": [42, 72], "danger": 2, "drops": {"black_corner_black_card": 30, "mid_grade_storage_ring": 6}}, "failure": {"damage": [18, 30], "douqi": [5, 12], "danger": 4}},
            {"key": "step_in", "label": "下场生死斗", "description": "被认作过江猛龙，不得不上台一战。", "risk": "凶险", "base_chance": 47, "success": {"damage": [13, 22], "douqi": [62, 102], "gold": [66, 108], "danger": 5, "drops": {"black_corner_black_card": 68, "monster_core_mid": 55, "low_grade_storage_ring": 10}}, "failure": {"damage": [36, 54], "douqi": [8, 18], "danger": 6}},
        ],
    },
    "fire_energy_forest": {
        "title": "火能森林",
        "story": "古木间漂浮着细碎火能，寒潭与兽径把森林分成数条路线。",
        "choices": [
            {"key": "forest_edge", "label": "沿林缘采集", "description": "避开火能浓郁区，搜集寒髓草与灵纹木。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [1, 4], "douqi": [18, 30], "gold": [3, 9], "danger": -1, "drops": {"cold_marrow_grass": 72, "spirit_pattern_wood": 58}}},
            {"key": "hunt_fire_beast", "label": "追猎火兽", "description": "循着焦黑兽印猎取火晶核和火能晶。", "risk": "均衡", "base_chance": 69, "success": {"damage": [6, 12], "douqi": [42, 72], "gold": [14, 28], "danger": 2, "drops": {"flame_crystal_core": 76, "fire_energy_crystal": 46, "beast_hide": 42}}, "failure": {"damage": [21, 34], "douqi": [7, 14], "danger": 3}},
            {"key": "deep_spring", "label": "潜入地脉泉眼", "description": "穿过兽群争夺地脉凝乳和玉骨果。", "risk": "凶险", "base_chance": 49, "success": {"damage": [12, 20], "douqi": [68, 108], "gold": [24, 42], "danger": 4, "drops": {"jade_bone_fruit": 48, "earth_core_body_milk": 22, "monster_core_mid": 55}}, "failure": {"damage": [34, 50], "douqi": [9, 18], "danger": 5}},
        ],
    },
    "tower_magma_tunnel": {
        "title": "炼气塔岩浆支脉",
        "story": "塔底旧通道被岩浆照得通红，冷热矿层在火流两侧交替裸露。",
        "choices": [
            {"key": "mark_route", "label": "测绘安全路线", "description": "记录岩浆涨落，只取通道口的火灵根。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [2, 6], "douqi": [22, 38], "gold": [4, 10], "danger": -1, "drops": {"fire_spirit_root": 62, "cold_iron_ore": 35}}},
            {"key": "temper_crystal", "label": "引火炼晶", "description": "借地火提纯火晶核与冰晶髓。", "risk": "均衡", "base_chance": 65, "success": {"damage": [8, 14], "douqi": [48, 80], "gold": [12, 24], "danger": 2, "drops": {"flame_crystal_core": 80, "ice_crystal_marrow": 58, "fallen_heart_flame_trace": 18}}, "failure": {"damage": [24, 38], "douqi": [8, 16], "danger": 4}},
            {"key": "magma_floor", "label": "下探岩浆底层", "description": "直入火流最深处寻找地心淬体乳和陨星铁。", "risk": "凶险", "base_chance": 46, "success": {"damage": [14, 23], "douqi": [78, 122], "gold": [25, 46], "danger": 5, "drops": {"earth_core_body_milk": 42, "meteorite_iron": 22, "fallen_heart_flame_trace": 38}}, "failure": {"damage": [40, 58], "douqi": [10, 20], "danger": 6}},
        ],
    },
    "inner_courtyard_market": {
        "title": "内院火能集市",
        "story": "学员把试炼所得摆上石台，火能牌、矿石和药材在这里快速流转。",
        "choices": [
            {"key": "run_errand", "label": "接取跑腿委托", "description": "帮摊主运送货物，换取少量火能和材料。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [0, 2], "douqi": [16, 28], "gold": [12, 20], "danger": -1, "drops": {"fire_energy_crystal": 58, "spirit_pattern_wood": 46}}},
            {"key": "bargain_ore", "label": "与强榜学员议价", "description": "用眼力换取寒铁、冰晶和雷纹矿。", "risk": "均衡", "base_chance": 72, "success": {"damage": [2, 7], "douqi": [34, 58], "gold": [20, 36], "danger": 1, "drops": {"cold_iron_ore": 78, "ice_crystal_marrow": 62, "thunder_pattern_ore": 24}}, "failure": {"damage": [15, 25], "douqi": [5, 11], "danger": 2}},
            {"key": "sealed_lot", "label": "竞拍封印纳戒", "description": "赌一批来路不明的遗迹残材。", "risk": "凶险", "base_chance": 50, "success": {"damage": [7, 14], "douqi": [56, 92], "gold": [38, 68], "danger": 3, "drops": {"space_stone": 20, "meteorite_iron": 32, "bronze_cauldron": 7}}, "failure": {"damage": [28, 42], "douqi": [7, 16], "gold": [0, 4], "danger": 5}},
        ],
    },
    "thunder_cliff": {
        "title": "雷鸣崖",
        "story": "乌云常年压在崖顶，银色雷弧沿矿脉游走，空气中满是焦灼气味。",
        "choices": [
            {"key": "after_rain", "label": "雷雨后拾矿", "description": "等雷势稍缓，从崖脚回收被震落的矿石。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [2, 5], "douqi": [20, 34], "gold": [5, 12], "danger": -1, "drops": {"cold_iron_ore": 68, "green_rock_ore": 82}}},
            {"key": "mine_thunder", "label": "斗气包裹采矿", "description": "以斗气隔绝雷弧，切取完整雷纹矿。", "risk": "均衡", "base_chance": 63, "success": {"damage": [8, 15], "douqi": [46, 76], "gold": [14, 26], "danger": 2, "drops": {"thunder_pattern_ore": 74, "cold_iron_ore": 52}}, "failure": {"damage": [26, 40], "douqi": [8, 17], "danger": 4}},
            {"key": "face_lightning", "label": "引雷淬体", "description": "迎向雷瀑淬炼身法，并争夺最深处矿芯。", "risk": "凶险", "base_chance": 44, "success": {"damage": [15, 25], "douqi": [82, 128], "gold": [26, 48], "danger": 5, "drops": {"thunder_pattern_ore": 100, "fire_energy_crystal": 48, "thunder_pattern_boots": 8}}, "failure": {"damage": [43, 62], "douqi": [11, 22], "danger": 6}},
        ],
    },
    "dan_domain_herb_field": {
        "title": "丹域万药田",
        "story": "连绵药田被阵法分隔，每片药圃都有丹塔弟子与傀儡轮值看守。",
        "choices": [
            {"key": "public_field", "label": "照料公用药圃", "description": "完成除草与灌灵，领取成熟药材。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [0, 3], "douqi": [28, 44], "gold": [10, 18], "danger": -1, "drops": {"fire_spirit_root": 76, "star_mist_grass": 42}}},
            {"key": "night_harvest", "label": "夜巡成熟药田", "description": "协助赶走偷药魔兽，按战果分取灵药。", "risk": "均衡", "base_chance": 67, "success": {"damage": [7, 13], "douqi": [58, 92], "gold": [24, 42], "danger": 2, "drops": {"earth_core_body_milk": 52, "jade_bone_fruit": 48, "monster_core_mid": 58}}, "failure": {"damage": [24, 36], "douqi": [9, 18], "danger": 4}},
            {"key": "sealed_garden", "label": "闯封禁古药园", "description": "破解旧阵争夺帝流浆与轮回草。", "risk": "凶险", "base_chance": 45, "success": {"damage": [14, 23], "douqi": [92, 142], "gold": [42, 72], "danger": 5, "drops": {"emperor_flow_serum": 38, "nine_leaf_reincarnation_grass": 18, "void_spirit_leaf": 22}}, "failure": {"damage": [41, 60], "douqi": [12, 24], "danger": 6}},
        ],
    },
    "space_wormhole": {
        "title": "空间虫洞驿站",
        "story": "银色空间之力在巨大通道中旋转，不时有碎石和旧物从裂缝中坠出。",
        "choices": [
            {"key": "collect_fragments", "label": "收集通道碎石", "description": "只在阵法边缘回收稳定残材。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [2, 6], "douqi": [30, 48], "gold": [12, 22], "danger": -1, "drops": {"meteorite_iron": 46, "green_rock_ore": 72}}},
            {"key": "stabilize_node", "label": "协助稳定节点", "description": "向阵眼灌注斗气，换取空间晶石。", "risk": "均衡", "base_chance": 64, "success": {"damage": [8, 15], "douqi": [64, 100], "gold": [28, 50], "danger": 2, "drops": {"space_stone": 58, "meteorite_iron": 62}}, "failure": {"damage": [28, 42], "douqi": [10, 19], "danger": 4}},
            {"key": "cross_rift", "label": "穿越临时裂隙", "description": "进入未标记的空间夹层搜寻虚灵叶。", "risk": "凶险", "base_chance": 42, "success": {"damage": [16, 26], "douqi": [102, 158], "gold": [50, 86], "danger": 6, "drops": {"space_stone": 100, "void_spirit_leaf": 38, "mid_grade_storage_ring": 6}}, "failure": {"damage": [46, 66], "douqi": [13, 26], "danger": 7}},
        ],
    },
    "beast_flame_valley": {
        "title": "兽火谷",
        "story": "众多火属性魔兽在谷中争夺兽火，赤红晶核散发出灼热波动。",
        "choices": [
            {"key": "gather_ashes", "label": "收集余烬", "description": "待兽群离开后，从战场边缘筛选火晶。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [3, 7], "douqi": [32, 50], "gold": [8, 16], "danger": -1, "drops": {"flame_crystal_core": 72, "fire_spirit_root": 48}}},
            {"key": "isolate_beast", "label": "诱离火兽", "description": "引出落单魔兽，夺取完整兽火晶核。", "risk": "均衡", "base_chance": 61, "success": {"damage": [10, 17], "douqi": [70, 108], "gold": [26, 48], "danger": 3, "drops": {"flame_crystal_core": 100, "monster_core_mid": 76, "beast_hide": 48}}, "failure": {"damage": [31, 46], "douqi": [11, 21], "danger": 5}},
            {"key": "valley_lord", "label": "挑战谷主", "description": "强夺谷地深处的高阶魔核与兽火。", "risk": "凶险", "base_chance": 40, "success": {"damage": [18, 29], "douqi": [112, 172], "gold": [52, 90], "danger": 6, "drops": {"monster_core_high": 62, "flame_crystal_core": 100, "emperor_flow_serum": 14}}, "failure": {"damage": [50, 70], "douqi": [14, 28], "danger": 7}},
        ],
    },
    "danta_ruins": {
        "title": "丹塔旧试场",
        "story": "废弃试场里仍残留着丹雷痕迹，封闭丹室偶尔会飘出药香。",
        "choices": [
            {"key": "read_marks", "label": "临摹炼药刻痕", "description": "不触动丹室，只记录前人火候心得。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [1, 5], "douqi": [38, 58], "gold": [8, 16], "danger": -1, "drops": {"danta_exam_token": 42, "star_mist_grass": 34}}},
            {"key": "open_lab", "label": "开启外层丹室", "description": "修复机关后搜寻遗留药材和药鼎碎片。", "risk": "均衡", "base_chance": 60, "success": {"damage": [9, 16], "douqi": [76, 116], "gold": [34, 58], "danger": 3, "drops": {"earth_core_body_milk": 62, "meteorite_iron": 48, "danta_exam_token": 70}}, "failure": {"damage": [30, 45], "douqi": [11, 22], "danger": 5}},
            {"key": "sealed_pill_room", "label": "强开封印丹室", "description": "硬抗丹雷，争夺最高层封存的奇药与冷火残息。", "risk": "凶险", "base_chance": 39, "success": {"damage": [19, 30], "douqi": [118, 180], "gold": [58, 96], "danger": 6, "drops": {"emperor_flow_serum": 48, "nine_leaf_reincarnation_grass": 24, "bone_spirit_cold_fire_trace": 14}}, "failure": {"damage": [52, 72], "douqi": [15, 30], "danger": 8}},
        ],
    },
    "starfall_forest": {
        "title": "星陨古林",
        "story": "古树叶面映着星光，林间灵气比外界浓郁数倍，却也藏着高阶魔兽。",
        "choices": [
            {"key": "follow_starlight", "label": "循星光采药", "description": "只沿阁中标记路线收集星雾草和灵木。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [3, 7], "douqi": [44, 66], "gold": [12, 22], "danger": -1, "drops": {"star_mist_grass": 82, "spirit_pattern_wood": 68}}},
            {"key": "guard_herb", "label": "挑战守药魔兽", "description": "争夺古林深处的高阶灵药。", "risk": "均衡", "base_chance": 58, "success": {"damage": [11, 19], "douqi": [88, 132], "gold": [36, 62], "danger": 3, "drops": {"emperor_flow_serum": 38, "monster_core_high": 58, "starfall_token": 42}}, "failure": {"damage": [36, 52], "douqi": [13, 25], "danger": 5}},
            {"key": "ancient_pavilion", "label": "探查林中古阁", "description": "穿过残阵搜寻星陨阁旧藏。", "risk": "凶险", "base_chance": 38, "success": {"damage": [20, 32], "douqi": [132, 198], "gold": [66, 110], "danger": 6, "drops": {"starfall_token": 100, "meteorite_iron": 62, "flame_divide_scroll": 20}}, "failure": {"damage": [54, 76], "douqi": [16, 32], "danger": 8}},
        ],
    },
    "ancient_dragon_pool": {
        "title": "古龙涎池",
        "story": "石池上方盘旋着淡淡龙威，池底沉积着金色灵液与碎鳞。",
        "choices": [
            {"key": "collect_mist", "label": "收集池边灵雾", "description": "不触碰龙威，只凝取外围稀薄药液。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [4, 8], "douqi": [48, 72], "gold": [10, 20], "danger": -1, "drops": {"ancient_dragon_saliva": 28, "dragon_blood_branch": 12}}},
            {"key": "dive_shallow", "label": "潜入浅池", "description": "以斗气抵抗龙威，采集较完整的古龙涎。", "risk": "均衡", "base_chance": 55, "success": {"damage": [13, 21], "douqi": [94, 142], "gold": [38, 68], "danger": 4, "drops": {"ancient_dragon_saliva": 74, "dragon_blood_branch": 36, "taixu_dragon_scale": 12}}, "failure": {"damage": [39, 56], "douqi": [14, 28], "danger": 6}},
            {"key": "dragon_bone", "label": "探查池底龙骨", "description": "直面残存龙威，争取古龙鳞与高阶奇药。", "risk": "凶险", "base_chance": 36, "success": {"damage": [22, 35], "douqi": [142, 214], "gold": [72, 118], "danger": 7, "drops": {"ancient_dragon_saliva": 100, "taixu_dragon_scale": 38, "nine_leaf_reincarnation_grass": 18}}, "failure": {"damage": [58, 80], "douqi": [18, 36], "danger": 9}},
        ],
    },
    "void_stone_chamber": {
        "title": "虚空石室",
        "story": "石室悬在空间乱流之间，墙体由陨星铁与空间晶石共同支撑。",
        "choices": [
            {"key": "outer_wall", "label": "剥离外墙残材", "description": "保持退路，回收松动的陨铁碎片。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [4, 9], "douqi": [50, 76], "gold": [14, 26], "danger": -1, "drops": {"meteorite_iron": 78, "space_stone": 24}}},
            {"key": "repair_array", "label": "修复空间阵纹", "description": "修复一处阵眼，换取完整空间石。", "risk": "均衡", "base_chance": 53, "success": {"damage": [14, 23], "douqi": [100, 150], "gold": [42, 74], "danger": 4, "drops": {"space_stone": 82, "meteorite_iron": 68, "void_spirit_leaf": 24}}, "failure": {"damage": [42, 60], "douqi": [15, 30], "danger": 7}},
            {"key": "void_core", "label": "闯入虚空核心", "description": "穿越乱流争夺石室阵心中的空间宝物。", "risk": "凶险", "base_chance": 34, "success": {"damage": [24, 38], "douqi": [152, 228], "gold": [78, 128], "danger": 8, "drops": {"space_stone": 100, "void_spirit_leaf": 52, "black_demon_cauldron_replica": 3}}, "failure": {"damage": [62, 84], "douqi": [20, 40], "danger": 10}},
        ],
    },
    "reincarnation_garden": {
        "title": "轮回古药园",
        "story": "九片颜色各异的药圃围绕古泉生长，灵魂感知在这里被不断拉扯。",
        "choices": [
            {"key": "outer_leaves", "label": "采集外围药叶", "description": "不靠近古泉，只采成熟的温魂药材。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [3, 8], "douqi": [54, 82], "gold": [12, 24], "danger": -1, "drops": {"soul_warming_lotus": 62, "star_mist_grass": 70}}},
            {"key": "break_puppet", "label": "破解守园药傀", "description": "击败药傀，进入中层药圃采摘轮回草。", "risk": "均衡", "base_chance": 51, "success": {"damage": [15, 24], "douqi": [106, 160], "gold": [46, 80], "danger": 5, "drops": {"nine_leaf_reincarnation_grass": 66, "emperor_flow_serum": 44, "soul_warming_lotus": 72}}, "failure": {"damage": [45, 64], "douqi": [16, 32], "danger": 7}},
            {"key": "ancient_spring", "label": "汲取轮回古泉", "description": "顶住灵魂冲击，争夺药园最珍贵的成熟奇药。", "risk": "凶险", "base_chance": 32, "success": {"damage": [25, 40], "douqi": [162, 242], "gold": [82, 136], "danger": 9, "drops": {"nine_leaf_reincarnation_grass": 100, "emperor_flow_serum": 72, "bodhi_seed": 32, "ancient_dragon_saliva": 28}}, "failure": {"damage": [66, 88], "douqi": [22, 44], "danger": 11}},
        ],
    },
}


def expedition_region(region_key: str) -> dict[str, Any] | None:
    return next((dict(region) for region in EXPEDITION_REGIONS if region["key"] == str(region_key)), None)


# ---------------------------------------------------------------------------
# 区域首领（Boss）：每个正典区域一位，战力门槛、讨伐奖励与讨伐战绩可配。
# ---------------------------------------------------------------------------
EXPEDITION_BOSSES: list[dict[str, Any]] = [
    {
        "key": "purple_wing_lion",
        "region_key": "magic_beast_mountains",
        "name": "紫晶翼狮王",
        "title": "魔兽山脉之王",
        "story": "紫晶翼狮王盘踞山脉最深处，紫晶鳞甲能抵卸寻常斗气，嘶吼间林海为之震颤。若能胜之，其幼崽与晶核皆归你手。",
        "realm_stage_min": "斗师",
        "power": 6800,
        "rewards": {
            "douqi": [140, 220],
            "gold": [60, 100],
            "boss_score": 30,
            "items": {"amethyst_lion_cub": 30, "purple_spirit_crystal": 55, "monster_core_mid": 80, "beast_hide": 100},
        },
    },
    {
        "key": "twin_head_fire_serpent",
        "region_key": "tagor_desert",
        "name": "双头火灵蛇",
        "title": "塔戈尔沙渊之蟒",
        "story": "潜伏于沙漠地火深处的双头火灵蛇，两首各喷灼焰与毒息，靠吞噬魔兽晋阶，守着一处异火线索。",
        "realm_stage_min": "斗师",
        "power": 26000,
        "rewards": {
            "douqi": [200, 320],
            "gold": [90, 150],
            "boss_score": 45,
            "items": {"sea_heart_flame_trace": 18, "flame_crystal_core": 70, "monster_core_mid": 85, "snake_shed_grass": 100},
        },
    },
    {
        "key": "blood_butcher",
        "region_key": "black_corner",
        "name": "黑角域血屠",
        "title": "黑榜前茅的杀神",
        "story": "黑角域赫赫有名的血屠，以屠戮成名，名下护着整条黑市街。他腰间那枚纳戒，据说装着半座城的财富。",
        "realm_stage_min": "大斗师",
        "power": 60000,
        "rewards": {
            "douqi": [300, 460],
            "gold": [130, 210],
            "boss_score": 60,
            "items": {"black_corner_black_card": 35, "mid_grade_storage_ring": 12, "monster_core_mid": 80, "beast_bone_shard": 90},
        },
    },
    {
        "key": "magma_fire_spirit_king",
        "region_key": "canaan_inner_academy",
        "name": "岩浆火灵王",
        "title": "天焚炼气塔底之灵",
        "story": "蛰伏在天焚炼气塔底层岩浆中的火灵王，凝聚万载地火而生，火劲之纯几乎不输异火，令整座塔都隐隐发热。",
        "realm_stage_min": "大斗师",
        "power": 90000,
        "rewards": {
            "douqi": [380, 580],
            "gold": [160, 260],
            "boss_score": 75,
            "items": {"fallen_heart_flame_trace": 22, "earth_core_body_milk": 40, "flame_crystal_core": 85, "meteorite_iron": 35},
        },
    },
    {
        "key": "myriad_pill_beast_king",
        "region_key": "central_plains_dan_domain",
        "name": "万药丹兽王",
        "title": "丹域古药园之主",
        "story": "丹域深处由万载药力孕育的丹兽之王，以奇药为食，吐息带药香，周身筋骨早已化作最上等的炼丹材料。",
        "realm_stage_min": "斗王",
        "power": 170000,
        "rewards": {
            "douqi": [520, 780],
            "gold": [240, 380],
            "boss_score": 95,
            "items": {"emperor_flow_serum": 35, "nine_leaf_reincarnation_grass": 18, "danta_exam_token": 70, "ancient_dragon_saliva": 25},
        },
    },
    {
        "key": "taixu_ancient_dragon_wraith",
        "region_key": "ancient_starfall_ruins",
        "name": "太虚古龙残魂",
        "title": "星陨遗迹的龙威",
        "story": "远古遗迹最深处盘踞着一缕太虚古龙残魂，龙威如实质般压下。若能取走它凝出的古龙鳞，无异于得到一条龙脉机缘。",
        "realm_stage_min": "斗宗",
        "power": 320000,
        "rewards": {
            "douqi": [720, 1080],
            "gold": [360, 560],
            "boss_score": 120,
            "items": {"taixu_dragon_scale": 45, "ancient_dragon_saliva": 70, "nine_leaf_reincarnation_grass": 30, "space_stone": 55, "void_spirit_leaf": 35},
        },
    },
]


# ---------------------------------------------------------------------------
# 隐藏事件：低概率触发，需达到对应境界才可能遇见，回报远超常规事件。
# ---------------------------------------------------------------------------
EXPEDITION_HIDDEN_EVENTS: dict[str, dict[str, Any]] = {
    "hidden_void_crack": {
        "title": "虚空裂缝",
        "story": "空间突然裂开一道仅供一人穿行的细缝，缝隙中溢出的空间之力卷着宝光，正缓缓闭合。",
        "realm_stage_min": "斗之气",
        "choices": [
            {"key": "record", "label": "记录坐标", "description": "记下裂缝坐标，交给途经的炼药师换些报酬。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [0, 2], "douqi": [18, 30], "gold": [12, 20], "danger": -1, "drops": {"space_stone": 18}}},
            {"key": "collect_edge", "label": "捞取边缘残片", "description": "在裂缝边缘抄起坠落的空间晶石。", "risk": "均衡", "base_chance": 62, "success": {"damage": [6, 12], "douqi": [40, 66], "gold": [24, 40], "danger": 2, "drops": {"space_stone": 55, "mid_grade_storage_ring": 6}}, "failure": {"damage": [20, 32], "douqi": [6, 13], "danger": 4}},
            {"key": "dive", "label": "纵身跃入", "description": "在裂缝闭合前钻入空间夹层，赌一场大机缘。", "risk": "凶险", "base_chance": 40, "success": {"damage": [12, 20], "douqi": [70, 112], "gold": [44, 76], "danger": 4, "drops": {"space_stone": 100, "void_spirit_leaf": 25, "mid_grade_storage_ring": 12}}, "failure": {"damage": [30, 48], "douqi": [8, 18], "danger": 6}},
        ],
    },
    "hidden_herb_whirlwind": {
        "title": "药灵旋涡",
        "story": "一阵反常的药香卷成旋涡，灵草随着气流倒卷上天，数株高阶药材在半空旋转不止。",
        "realm_stage_min": "斗者",
        "choices": [
            {"key": "net", "label": "张网截取", "description": "用斗气织网兜住外围药材。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [1, 4], "douqi": [24, 38], "gold": [8, 14], "danger": -1, "drops": {"emperor_flow_serum": 22, "star_mist_grass": 40}}},
            {"key": "chase", "label": "追入旋涡", "description": "追着灵草旋入药气最浓处。", "risk": "均衡", "base_chance": 58, "success": {"damage": [9, 16], "douqi": [62, 96], "gold": [30, 52], "danger": 3, "drops": {"emperor_flow_serum": 55, "nine_leaf_reincarnation_grass": 15}}, "failure": {"damage": [26, 40], "douqi": [8, 17], "danger": 5}},
            {"key": "devour", "label": "张口鲸吞", "description": "引动斗气强行吞噬药灵，淬炼自身。", "risk": "凶险", "base_chance": 36, "success": {"damage": [16, 26], "douqi": [98, 148], "gold": [30, 56], "danger": 5, "drops": {"emperor_flow_serum": 100, "nine_leaf_reincarnation_grass": 30, "bodhi_seed": 12}}, "failure": {"damage": [42, 62], "douqi": [14, 28], "danger": 7}},
        ],
    },
    "hidden_fallen_fire": {
        "title": "陨火遗烬",
        "story": "夜空划过一道赤红流星，坠地后留下仍在灼烧的陨火遗烬，余温中透着异常精纯的火劲。",
        "realm_stage_min": "大斗师",
        "choices": [
            {"key": "study", "label": "远观研习", "description": "不近火源，只揣摩其火势轨迹。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [2, 6], "douqi": [30, 48], "gold": [6, 12], "danger": -1, "drops": {"flame_crystal_core": 30}}},
            {"key": "absorb", "label": "引火入体", "description": "牵引陨火淬炼经脉，借其纯粹火劲修行。", "risk": "均衡", "base_chance": 54, "success": {"damage": [12, 20], "douqi": [74, 116], "gold": [16, 30], "danger": 4, "drops": {"fallen_heart_flame_trace": 30, "flame_crystal_core": 85, "fire_spirit_root": 60}}, "failure": {"damage": [32, 48], "douqi": [10, 20], "danger": 6}},
            {"key": "core", "label": "夺取陨火之核", "description": "深入灼烧核心，取出火种级的晶核。", "risk": "凶险", "base_chance": 33, "success": {"damage": [18, 30], "douqi": [120, 178], "gold": [28, 50], "danger": 6, "drops": {"fallen_heart_flame_trace": 70, "flame_crystal_core": 100, "qinglian_fire_map": 22}}, "failure": {"damage": [48, 70], "douqi": [16, 32], "danger": 8}},
        ],
    },
    "hidden_treasure_hunt": {
        "title": "前贤洞天",
        "story": "岩壁后藏着一座封存多年的洞府，石台上留有高阶斗技残卷与一炉未冷却的矿材。",
        "realm_stage_min": "斗王",
        "choices": [
            {"key": "rubbing", "label": "临摹石壁", "description": "只拓下可辨认的斗技路线。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [2, 5], "douqi": [38, 60], "gold": [10, 18], "danger": -1, "drops": {"flame_method_fragment": 40}}},
            {"key": "open", "label": "开启洞府", "description": "破解禁制，取走完整传承与矿材。", "risk": "均衡", "base_chance": 50, "success": {"damage": [14, 22], "douqi": [84, 128], "gold": [40, 68], "danger": 4, "drops": {"flame_divide_scroll": 35, "thunder_steps_scroll": 25, "meteorite_iron": 55}}, "failure": {"damage": [34, 50], "douqi": [12, 24], "danger": 6}},
            {"key": "deep", "label": "闯阵眼密室", "description": "直奔洞府最深处，赌一份压箱底的机缘。", "risk": "凶险", "base_chance": 30, "success": {"damage": [20, 32], "douqi": [128, 190], "gold": [60, 100], "danger": 6, "drops": {"flame_divide_scroll": 100, "thunder_steps_scroll": 40, "meteorite_iron": 80, "buddha_lotus_scroll": 10}}, "failure": {"damage": [52, 74], "douqi": [18, 36], "danger": 8}},
        ],
    },
    "hidden_soul_fragment": {
        "title": "残魂洞窟",
        "story": "阴风从地窟深处涌出，石壁上浮现着破碎的魂印，一缕远古残魂正低声呓语。",
        "realm_stage_min": "斗皇",
        "choices": [
            {"key": "listen", "label": "静听残魂", "description": "不打断呓语，从中捕捉修炼心得。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [3, 7], "douqi": [46, 70], "gold": [8, 16], "danger": -1, "drops": {"soul_warming_lotus": 35}}},
            {"key": "converse", "label": "与残魂交易", "description": "以心头精血为代价，换一段失传魂术。", "risk": "均衡", "base_chance": 46, "success": {"damage": [12, 20], "douqi": [90, 136], "gold": [24, 44], "danger": 4, "drops": {"soul_restoring_pill": 30, "yin_yang_life_soul_pill": 12, "soul_warming_lotus": 70}}, "failure": {"damage": [30, 48], "douqi": [12, 24], "danger": 6}},
            {"key": "seize", "label": "炼化残魂", "description": "强行镇压残魂，吞噬其精纯魂力。", "risk": "凶险", "base_chance": 28, "success": {"damage": [22, 34], "douqi": [136, 204], "gold": [30, 56], "danger": 7, "drops": {"yin_yang_life_soul_pill": 45, "soul_restoring_pill": 80, "bone_spirit_cold_fire_trace": 18}}, "failure": {"damage": [55, 78], "douqi": [20, 40], "danger": 9}},
        ],
    },
    "hidden_dragon_relic": {
        "title": "古龙遗骸",
        "story": "巨骨斜插在深谷间，骨髓早已枯竭，但龙骨表面仍浮着淡淡龙威与金色灵光。",
        "realm_stage_min": "斗宗",
        "choices": [
            {"key": "carve", "label": "刮取龙屑", "description": "小心刮取骨面碎屑，不惊动残余龙威。", "risk": "稳妥", "base_chance": 100, "success": {"damage": [4, 8], "douqi": [54, 82], "gold": [10, 20], "danger": -1, "drops": {"ancient_dragon_saliva": 35}}},
            {"key": "extract", "label": "抽取髓液", "description": "以斗气引渡深藏的龙髓灵液。", "risk": "均衡", "base_chance": 44, "success": {"damage": [14, 24], "douqi": [104, 156], "gold": [34, 60], "danger": 5, "drops": {"taixu_dragon_scale": 30, "ancient_dragon_saliva": 85, "dragon_blood_branch": 30}}, "failure": {"damage": [38, 58], "douqi": [14, 28], "danger": 7}},
            {"key": "channel", "label": "引龙威淬体", "description": "直面龙威，借古龙残威冲刷道基。", "risk": "凶险", "base_chance": 26, "success": {"damage": [24, 38], "douqi": [152, 228], "gold": [40, 76], "danger": 8, "drops": {"taixu_dragon_scale": 100, "ancient_dragon_saliva": 100, "nine_leaf_reincarnation_grass": 25, "emperor_flow_serum": 40}}, "failure": {"damage": [58, 82], "douqi": [22, 44], "danger": 10}},
        ],
    },
}


def expedition_boss_for_region(region_key: str) -> dict[str, Any] | None:
    for boss in EXPEDITION_BOSSES:
        if boss["region_key"] == str(region_key):
            return dict(boss)
    return None


def _boss_event_payload(boss: dict[str, Any]) -> dict[str, Any] | None:
    if not boss:
        return None
    rewards = dict(boss.get("rewards") or {})
    douqi_range = list(rewards.get("douqi") or [0, 0])
    gold_range = list(rewards.get("gold") or [0, 0])
    items = dict(rewards.get("items") or {})
    low_douqi = max(int(douqi_range[0] if len(douqi_range) > 0 else 0) * 3 // 5, 20)
    high_douqi = max(int(douqi_range[1] if len(douqi_range) > 1 else 0) * 3 // 5, 40)
    low_gold = max(int(gold_range[0] if len(gold_range) > 0 else 0) * 2 // 5, 10)
    high_gold = max(int(gold_range[1] if len(gold_range) > 1 else 0) * 2 // 5, 20)
    return {
        "kind": "boss",
        "boss_key": str(boss.get("key") or ""),
        "boss_name": str(boss.get("name") or "区域首领"),
        "boss_power": max(int(boss.get("power") or 0), 1),
        "title": f"区域首领：{boss.get('name')}",
        "story": str(boss.get("story") or ""),
        "choices": [
            {
                "key": "fight",
                "label": "正面讨伐",
                "description": "正面对决区域首领，胜则名扬四方并记讨伐战绩。",
                "risk": "凶险",
                "base_chance": 60,
                "boss_fight": True,
                "success": {
                    "damage": [12, 22],
                    "douqi": douqi_range,
                    "gold": gold_range,
                    "danger": 3,
                    "drops": dict(items),
                },
                "failure": {"damage": [34, 55], "douqi": [8, 18], "danger": 5},
            },
            {
                "key": "stalk",
                "label": "伺机截宝",
                "description": "借其分神之际夺取外围战利品，风险更低但无战绩。",
                "risk": "均衡",
                "base_chance": 80,
                "success": {
                    "damage": [7, 14],
                    "douqi": [low_douqi, high_douqi],
                    "gold": [low_gold, high_gold],
                    "danger": 1,
                    "drops": {key: max(int(chance or 0) * 2 // 5, 5) for key, chance in items.items()},
                },
                "failure": {"damage": [24, 38], "douqi": [6, 13], "danger": 4},
            },
            {
                "key": "shun",
                "label": "暂避锋芒",
                "description": "记住首领行踪，等实力足够再来讨伐。",
                "risk": "稳妥",
                "base_chance": 100,
                "success": {"damage": [2, 6], "douqi": [10, 18], "gold": [0, 4], "danger": -2},
            },
        ],
    }


def expedition_event_for_key(event_key: str | None) -> dict[str, Any] | None:
    """Resolve a stored event key to a playable event dict.

    优先级：常规事件 → Boss 伪事件（``boss:<region_key>``，动态由首领目录生成）→ 隐藏事件。
    返回的事件一律携带 ``kind`` 供前端区分渲染。
    """
    key = str(event_key or "")
    normal = EXPEDITION_EVENTS.get(key)
    if normal is not None:
        return {**dict(normal), "kind": "normal"}
    if key.startswith("boss:"):
        boss = expedition_boss_for_region(key.split(":", 1)[1])
        return _boss_event_payload(boss)
    hidden = EXPEDITION_HIDDEN_EVENTS.get(key)
    if hidden is not None:
        return {**dict(hidden), "kind": "hidden"}
    return None


def expedition_boss_keys() -> set[str]:
    return {f"boss:{boss['region_key']}" for boss in EXPEDITION_BOSSES if boss.get("region_key")}
