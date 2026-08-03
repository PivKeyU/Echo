from __future__ import annotations

EXTRA_TALISMANS = [
    {
        "name": "逐浪符",
        "rarity": "下品",
        "body_movement_bonus": 8,
        "description": "符纹细长如水痕，激发后脚下如有浪头托行，身法会明显变得轻快。",
        "combat_config": {
            "skills": [
                {
                    "name": "踏浪错步",
                    "kind": "dodge",
                    "chance": 18,
                    "dodge_bonus": 10,
                    "duration": 1,
                    "text": "逐浪符一闪，身形像踩着一层薄浪横移出去。",
                }
            ]
        },
        "materials": [("银鳞藻", 1), ("月魄蚌珠", 1), ("黄纸符", 1)],
        "success": 70,
    },
    {
        "name": "凝潮符",
        "rarity": "中品",
        "defense_bonus": 14,
        "true_yuan_bonus": 18,
        "description": "以潮音珊瑚调墨绘成，激发后身前会汇起一层层重叠潮幕。",
        "combat_config": {
            "skills": [
                {
                    "name": "叠潮护身",
                    "kind": "shield",
                    "chance": 24,
                    "flat_shield": 18,
                    "ratio_percent": 14,
                    "text": "凝潮符化作几重潮幕，把来势尽数缓了下来。",
                }
            ]
        },
        "materials": [("潮音珊瑚", 1), ("龙涡骨片", 1), ("朱砂", 1)],
        "success": 60,
    },
    {
        "name": "寒月映波符",
        "rarity": "上品",
        "defense_bonus": 12,
        "divine_sense_bonus": 10,
        "body_movement_bonus": 10,
        "description": "符成时如一轮寒月倒映水面，最擅迷惑目力、偏转对手判断。",
        "combat_config": {
            "skills": [
                {
                    "name": "月影偏潮",
                    "kind": "dodge",
                    "chance": 28,
                    "dodge_bonus": 18,
                    "duration": 1,
                    "text": "寒月映波符投下一层冷月倒影，对手的判断被水光带偏了一瞬。",
                }
            ]
        },
        "materials": [("月魄蚌珠", 1), ("星潮玄砂", 1), ("白虎胡须", 1)],
        "success": 52,
    },
    {
        "name": "沸海裂岸符",
        "rarity": "极品",
        "attack_bonus": 24,
        "defense_bonus": 8,
        "description": "以熔鳞砂和赤髓炎珀绘成，符火炸开时像整片海岸被灼浪掀翻。",
        "combat_config": {
            "skills": [
                {
                    "name": "裂岸炎潮",
                    "kind": "armor_break",
                    "chance": 32,
                    "defense_ratio_percent": 20,
                    "duration": 2,
                    "text": "沸海裂岸符炸开一道炎潮，对手护体灵光被当场冲散。",
                }
            ]
        },
        "materials": [("熔鳞砂", 1), ("赤髓炎珀", 1), ("曜金雷髓", 1)],
        "success": 42,
    },
    {
        "name": "星渊牵机符",
        "rarity": "仙品",
        "attack_bonus": 18,
        "divine_sense_bonus": 16,
        "duel_rate_bonus": 5,
        "description": "星海牵机、潮线引命，最适合抢夺斗法先机与捕捉转瞬即逝的破绽。",
        "combat_config": {
            "skills": [
                {
                    "name": "牵星引机",
                    "kind": "extra_damage",
                    "chance": 34,
                    "flat_damage": 26,
                    "ratio_percent": 22,
                    "text": "星渊牵机符轻轻一振，像有无形潮线提前把攻势送到了对手身前。",
                }
            ]
        },
        "materials": [("星渊潮核", 1), ("海眼寒晶", 1), ("天眷符骨", 1)],
        "success": 34,
    },
    {
        "name": "回澜符",
        "rarity": "上品",
        "defense_bonus": 18,
        "true_yuan_bonus": 26,
        "duel_rate_bonus": 3,
        "description": "符成如水纹倒卷，擅长在硬拼时缓冲对手的冲势。",
        "combat_config": {
            "skills": [
                {
                    "name": "回澜护潮",
                    "kind": "shield",
                    "chance": 30,
                    "flat_shield": 22,
                    "ratio_percent": 18,
                    "text": "回澜符水纹翻涌，将来势层层卸开。",
                }
            ]
        },
        "materials": [("定魄灵砂", 1), ("玄龟骨晶", 1), ("龙门真水", 1)],
        "success": 54,
    },
    {
        "name": "惊鸿符",
        "rarity": "极品",
        "attack_bonus": 20,
        "body_movement_bonus": 20,
        "duel_rate_bonus": 5,
        "description": "此符以惊鸿为名，燃符之日如鸿雁掠空，一击即出，势不可挡，最宜抢先手与突进追击。",
        "combat_config": {
            "skills": [
                {
                    "name": "惊鸿掠影",
                    "kind": "extra_damage",
                    "chance": 32,
                    "flat_damage": 20,
                    "ratio_percent": 20,
                    "text": "惊鸿符划开一抹长影，下一击几乎同时落下。",
                }
            ]
        },
        "materials": [("霓裳花露", 1), ("星命玉枝", 1), ("璇玑星砂", 1)],
        "success": 42,
    },
    {
        "name": "照影符",
        "rarity": "极品",
        "attack_bonus": 10,
        "divine_sense_bonus": 14,
        "body_movement_bonus": 18,
        "duel_rate_bonus": 4,
        "description": "此符以镜为引，祭起之时如在敌眼留下虚影，令其判断失误，坐失良机。",
        "combat_config": {
            "skills": [
                {
                    "name": "镜影错身",
                    "kind": "dodge",
                    "chance": 30,
                    "dodge_bonus": 22,
                    "duration": 1,
                    "text": "照影符反折出一道镜影，来势几乎擦着衣角落空。",
                }
            ]
        },
        "materials": [("镜尘玄晶", 1), ("霓裳花露", 1), ("星命玉枝", 1)],
        "success": 46,
    },
    {
        "name": "镇魄封脉符",
        "rarity": "仙品",
        "attack_bonus": 16,
        "defense_bonus": 12,
        "duel_rate_bonus": 5,
        "description": "专门针对护体灵气与经脉运行，适合打高防对手。",
        "combat_config": {
            "skills": [
                {
                    "name": "封脉钉灵",
                    "kind": "armor_break",
                    "chance": 32,
                    "defense_ratio_percent": 20,
                    "duration": 2,
                    "text": "镇魄封脉符化作数枚黯金钉芒，直钉护体灵气节点。",
                }
            ]
        },
        "materials": [("离魄藤种", 1), ("天眷符骨", 1), ("曜金雷髓", 1)],
        "success": 36,
    },
    {
        "name": "多次探索符",
        "rarity": "仙品",
        "divine_sense_bonus": 14,
        "fortune_bonus": 12,
        "description": "符纹分化数道灵影，启用后可在一次秘境探索中牵引多重机缘，将主要掉落与灵石结算按次数累积。",
        "combat_config": {
            "active_effects": {
                "exploration_repeat_count": 3,
                "exploration_drop_bonus": 12,
                "exploration_quantity_bonus": 18,
                "exploration_stone_bonus": 18,
            },
        },
        "materials": [("天眷符骨", 1), ("星渊潮核", 1), ("太清星尘", 1)],
        "success": 32,
    },
    # ========== 新增：凡品符箓 ==========
    {
        "name": "醒神符",
        "rarity": "凡品",
        "defense_bonus": 4,
        "comprehension_bonus": 2,
        "description": "最低级的符箓，可短暂提升悟性。",
        "combat_config": {},
        "materials": [("黄纸符", 1), ("朱砂", 1)],
        "success": 76,
    },
    {
        "name": "护身符",
        "rarity": "凡品",
        "defense_bonus": 6,
        "description": "基础护身符箓，新手常用。",
        "combat_config": {
            "skills": [
                {
                    "name": "护身微光",
                    "kind": "shield",
                    "chance": 16,
                    "flat_shield": 8,
                    "ratio_percent": 10,
                    "text": "护身符微微发光，勉强挡住一击。",
                }
            ],
        },
        "materials": [("黄纸符", 2), ("朱砂", 1)],
        "success": 74,
    },
    # ========== 新增：下品符箓 ==========
    {
        "name": "寒冰符",
        "rarity": "下品",
        "attack_bonus": 8,
        "defense_bonus": 4,
        "description": "可释放寒冰之力，冰封敌人。",
        "combat_config": {
            "skills": [
                {
                    "name": "寒冰刺",
                    "kind": "extra_damage",
                    "chance": 20,
                    "flat_damage": 10,
                    "ratio_percent": 12,
                    "text": "寒冰符化作冰刺，直刺对手要害。",
                }
            ],
        },
        "materials": [("灵蚕丝", 1), ("霜凌草", 1), ("黑狗血", 1)],
        "success": 68,
    },
    {
        "name": "烈焰符",
        "rarity": "下品",
        "attack_bonus": 10,
        "description": "释放火焰攻击，灼烧敌人。",
        "combat_config": {
            "skills": [
                {
                    "name": "烈焰灼烧",
                    "kind": "burn",
                    "chance": 18,
                    "flat_damage": 8,
                    "ratio_percent": 10,
                    "duration": 2,
                    "text": "烈焰符爆发，火焰缠上对手。",
                }
            ],
        },
        "materials": [("灵蚕丝", 1), ("烈阳花", 1), ("朱砂", 1)],
        "success": 66,
    },
    {
        "name": "清风符",
        "rarity": "下品",
        "body_movement_bonus": 10,
        "description": "轻身符箓，提升身法。",
        "combat_config": {
            "skills": [
                {
                    "name": "轻身术",
                    "kind": "dodge",
                    "chance": 20,
                    "dodge_bonus": 12,
                    "duration": 1,
                    "text": "清风符激活，身形飘忽不定。",
                }
            ],
        },
        "materials": [("灵蚕丝", 1), ("风灵石", 1)],
        "success": 70,
    },
    # ========== 新增：中品符箓 ==========
    {
        "name": "冰魄符",
        "rarity": "中品",
        "attack_bonus": 14,
        "divine_sense_bonus": 6,
        "description": "以冰魄珠为引，可大范围冰封。",
        "combat_config": {
            "skills": [
                {
                    "name": "冰魄封天",
                    "kind": "extra_damage",
                    "chance": 24,
                    "flat_damage": 16,
                    "ratio_percent": 14,
                    "text": "冰魄符激活，寒气席卷四方。",
                }
            ],
        },
        "materials": [("妖狐尾毛", 1), ("冰魄珠", 1), ("雷击桃木", 1)],
        "success": 58,
    },
    {
        "name": "火鸾符",
        "rarity": "中品",
        "attack_bonus": 16,
        "duel_rate_bonus": 3,
        "description": "火鸾之力灌注，攻击带有火鸾真火。",
        "combat_config": {
            "skills": [
                {
                    "name": "火鸾展翅",
                    "kind": "extra_damage",
                    "chance": 26,
                    "flat_damage": 14,
                    "ratio_percent": 16,
                    "text": "火鸾符化作火鸾虚影，展翅攻击。",
                }
            ],
        },
        "materials": [("火鸾羽", 1), ("烈阳花", 2), ("鬼画符骨", 1)],
        "success": 56,
    },
    {
        "name": "金刚符",
        "rarity": "中品",
        "defense_bonus": 20,
        "qi_blood_bonus": 30,
        "description": "防御符箓，激活后金身护体。",
        "combat_config": {
            "skills": [
                {
                    "name": "金刚护体",
                    "kind": "shield",
                    "chance": 26,
                    "flat_shield": 24,
                    "ratio_percent": 16,
                    "text": "金刚符激活，肉身如金似铁。",
                }
            ],
        },
        "materials": [("玄武岩", 1), ("金芒砂", 1), ("寒铁", 1)],
        "success": 54,
    },
    # ========== 新增：上品符箓 ==========
    {
        "name": "玄冰符",
        "rarity": "上品",
        "attack_bonus": 22,
        "defense_bonus": 8,
        "divine_sense_bonus": 10,
        "description": "万年玄冰为引，可冻裂金丹修士。",
        "combat_config": {
            "skills": [
                {
                    "name": "玄冰裂天",
                    "kind": "extra_damage",
                    "chance": 30,
                    "flat_damage": 24,
                    "ratio_percent": 20,
                    "text": "玄冰符斩出，天地凝结成冰。",
                }
            ],
        },
        "materials": [("玄冰精髓", 1), ("冰魄珠", 1), ("白虎胡须", 1)],
        "success": 46,
    },
    {
        "name": "烈凤符",
        "rarity": "上品",
        "attack_bonus": 26,
        "body_movement_bonus": 14,
        "description": "凤凰真火凝聚，攻击蕴含轮回之力。",
        "combat_config": {
            "skills": [
                {
                    "name": "烈凤焚天",
                    "kind": "burn",
                    "chance": 30,
                    "flat_damage": 22,
                    "ratio_percent": 18,
                    "duration": 3,
                    "text": "烈凤符激活，涅槃之火焚尽一切。",
                }
            ],
        },
        "materials": [("烈凤心血", 1), ("朱雀神羽", 1), ("真武水精", 1)],
        "success": 44,
    },
    {
        "name": "天师符",
        "rarity": "上品",
        "attack_bonus": 18,
        "defense_bonus": 16,
        "duel_rate_bonus": 5,
        "description": "天师袍角之力，正道降魔之符。",
        "combat_config": {
            "skills": [
                {
                    "name": "天师降魔",
                    "kind": "extra_damage",
                    "chance": 28,
                    "flat_damage": 20,
                    "ratio_percent": 16,
                    "text": "天师符金光大盛，妖魔退散。",
                }
            ],
        },
        "materials": [("天师袍角", 1), ("天雷符骨", 1), ("青龙之鳞", 1)],
        "success": 42,
    },
    # ========== 新增：极品符箓 ==========
    {
        "name": "九幽寒莲符",
        "rarity": "极品",
        "attack_bonus": 30,
        "defense_bonus": 14,
        "divine_sense_bonus": 12,
        "description": "九幽寒莲之力，可冻结万物生机。",
        "combat_config": {
            "skills": [
                {
                    "name": "九幽冻魂",
                    "kind": "armor_break",
                    "chance": 34,
                    "defense_ratio_percent": 22,
                    "duration": 3,
                    "text": "九幽寒莲符激活，连神魂都被冻结。",
                }
            ],
        },
        "materials": [("九幽寒莲", 1), ("玄冰精髓", 1), ("轮回冥晶", 1)],
        "success": 36,
    },
    {
        "name": "涅槃符",
        "rarity": "极品",
        "defense_bonus": 22,
        "qi_blood_bonus": 60,
        "description": "凤凰涅槃之羽，可浴火重生。",
        "combat_config": {
            "skills": [
                {
                    "name": "涅槃再生",
                    "kind": "heal",
                    "chance": 28,
                    "flat_heal": 36,
                    "ratio_percent": 20,
                    "text": "涅槃符激活，浴火重生，伤势复原。",
                }
            ],
        },
        "materials": [("涅槃火羽", 1), ("凤凰真血", 1), ("朱雀心核", 1)],
        "success": 34,
    },
    {
        "name": "建木符",
        "rarity": "极品",
        "cultivation_bonus": 14,
        "fortune_bonus": 10,
        "description": "建木之种之力，加速修炼。",
        "combat_config": {
            "skills": [
                {
                    "name": "建木生机",
                    "kind": "heal",
                    "chance": 26,
                    "flat_heal": 28,
                    "ratio_percent": 16,
                    "text": "建木符激活，生命之力涌动。",
                }
            ],
        },
        "materials": [("建木之种", 1), ("青龙帝藤", 1), ("人参果精", 1)],
        "success": 32,
    },
    # ========== 新增：仙品符箓 ==========
    {
        "name": "鸿蒙符",
        "rarity": "仙品",
        "attack_bonus": 38,
        "defense_bonus": 20,
        "cultivation_bonus": 16,
        "description": "鸿蒙紫莲之力，一符可破天穹。",
        "combat_config": {
            "skills": [
                {
                    "name": "鸿蒙破空",
                    "kind": "extra_damage",
                    "chance": 38,
                    "flat_damage": 36,
                    "ratio_percent": 28,
                    "text": "鸿蒙符激活，紫气东来，破尽万法。",
                }
            ],
        },
        "materials": [("鸿蒙紫莲", 1), ("混沌祖气", 1), ("天外玄铁", 1)],
        "success": 26,
    },
    {
        "name": "天罚符",
        "rarity": "仙品",
        "attack_bonus": 42,
        "duel_rate_bonus": 8,
        "description": "天罚雷种之力，代表天道惩罚。",
        "combat_config": {
            "skills": [
                {
                    "name": "天罚降世",
                    "kind": "extra_damage",
                    "chance": 40,
                    "flat_damage": 40,
                    "ratio_percent": 30,
                    "text": "天罚符激活，天道雷罚降临。",
                }
            ],
        },
        "materials": [("天罚雷种", 1), ("天道雷种", 1), ("混沌雷种", 1)],
        "success": 24,
    },
    # ========== 新增：先天至宝符箓 ==========
    {
        "name": "开天符",
        "rarity": "先天至宝",
        "attack_bonus": 60,
        "defense_bonus": 30,
        "cultivation_bonus": 24,
        "description": "开天神石之力，一符可开天辟地。",
        "combat_config": {
            "skills": [
                {
                    "name": "开天辟地",
                    "kind": "extra_damage",
                    "chance": 48,
                    "flat_damage": 80,
                    "ratio_percent": 40,
                    "text": "开天符激活，创世之力毁天灭地。",
                }
            ],
        },
        "materials": [("开天神石", 1), ("盘古精血", 1), ("造化玉蝶", 1)],
        "success": 15,
    },
    {
        "name": "轮回符",
        "rarity": "先天至宝",
        "attack_bonus": 45,
        "defense_bonus": 35,
        "true_yuan_bonus": 100,
        "description": "轮回法则本源，可逆转生死。",
        "combat_config": {
            "skills": [
                {
                    "name": "六道轮回",
                    "kind": "armor_break",
                    "chance": 45,
                    "defense_ratio_percent": 35,
                    "duration": 4,
                    "text": "轮回符激活，六道轮回之力搅动时空。",
                }
            ],
        },
        "materials": [("轮回祖符", 1), ("本源雷种", 1), ("命运之种", 1)],
        "success": 12,
    },
    # ========== 补齐：秘境与奇遇引用缺失符箓 ==========
    {
        "name": "镇魂符",
        "rarity": "上品",
        "attack_bonus": 10,
        "defense_bonus": 12,
        "divine_sense_bonus": 12,
        "description": "专为镇压神魂动荡与慑服阴灵所绘，燃符后能强压对手识海波澜。",
        "combat_config": {
            "skills": [
                {
                    "name": "镇魂定魄",
                    "kind": "armor_break",
                    "chance": 30,
                    "defense_ratio_percent": 18,
                    "duration": 2,
                    "text": "镇魂符化作一缕幽光压入识海，对手护体灵光顿时一滞。",
                }
            ],
        },
        "materials": [("幽冥魂晶", 1), ("鬼画符骨", 1), ("净水莲心", 1)],
        "success": 42,
    },
    {
        "name": "白虎破军符",
        "rarity": "极品",
        "attack_bonus": 30,
        "body_movement_bonus": 8,
        "duel_rate_bonus": 6,
        "description": "白虎杀伐之意尽凝于符中，一旦祭出便如军阵冲锋，最善撕开正面防线。",
        "combat_config": {
            "skills": [
                {
                    "name": "白虎破阵",
                    "kind": "extra_damage",
                    "chance": 34,
                    "flat_damage": 28,
                    "ratio_percent": 22,
                    "text": "白虎破军符化作金白虎影扑杀而出，一击直破敌阵。",
                }
            ],
        },
        "materials": [("白虎神金", 1), ("白虎胡须", 1), ("金芒砂", 1)],
        "success": 34,
    },
]

