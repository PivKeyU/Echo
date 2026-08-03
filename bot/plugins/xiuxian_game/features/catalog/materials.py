from __future__ import annotations


# =============================================================================
# 全新扩展：修仙界稀有材料 - 覆盖所有品质等级
# =============================================================================

NEW_MATERIALS = [
    # ========== 凡品(1) ==========
    {"name": "灵露滴", "quality_level": 1, "description": "晨曦初照时，灵草叶片上凝结的第一滴露珠，蕴含天地初醒的灵韵，是最基础的炼丹材料。"},
    {"name": "枯叶草", "quality_level": 1, "description": "灵山深处随处可见的灵草，虽枯犹荣，内蕴微弱灵气，新手修士常以此练手。"},
    {"name": "碎石粉", "quality_level": 1, "description": "以灵山之石细细研磨而成，粉质细腻如玉，可作为炼器时的填充辅料。"},
    {"name": "引路萤火", "quality_level": 1, "description": "灵山深处的夜晚，萤火虫所携带的灵光，可指引方向亦可入药炼丹。"},
    {"name": "残月水", "quality_level": 1, "description": "月华如水之夜，草叶上凝结的精纯露水，蕴含月之柔寒，有安神凝心之效。"},

    # ========== 下品(2) ==========
    {"name": "霜凌草", "quality_level": 2, "description": "傲霜而立于寒泉之畔，叶片如剑般挺立，蕴含刺骨寒意，是炼制冰系丹药的寒性主材。"},
    {"name": "烈阳花", "quality_level": 2, "description": "向阳而绽的火红灵花，花瓣如焰，散发着灼热气息，是火系丹药的极品主材。"},
    {"name": "风灵石", "quality_level": 2, "description": "山巅风穴之中，风灵气长年侵蚀凝结而成的结晶，轻盈剔透，是炼制轻灵法宝的良品。"},
    {"name": "浊煞泥", "quality_level": 2, "description": "幽冥阴气淤积之地所生，泥性至阴至浊，可用于炼制护体法器，护身效果极佳。"},
    {"name": "裂木甲", "quality_level": 2, "description": "雷劫古木被天雷劈开后遗留的外皮，纹理如鳞，导电性极佳，是绘制雷系符箓的良品。"},
    {"name": "幽冥粉", "quality_level": 2, "description": "幽暗深渊中生长的菌类所散发的孢子，蕴含迷幻之力，炼丹时常作为药引入药。"},

    # ========== 中品(3) ==========
    {"name": "冰魄珠", "quality_level": 3, "description": "寒潭深处的冰灵结晶，通体幽蓝剔透，可大幅提升丹药的清凉属性。"},
    {"name": "火鸾羽", "quality_level": 3, "description": "火鸾妖禽脱落的羽毛，羽尖隐隐有火焰缭绕，蕴含炽热灵力。"},
    {"name": "木灵精", "quality_level": 3, "description": "千年古木所化的精魄之物，散发着草木清香，蕴含生生不息之气。"},
    {"name": "金芒砂", "quality_level": 3, "description": "金属性灵石矿脉中析出的精华，硬度极高。"},
    {"name": "净水莲心", "quality_level": 3, "description": "灵泉中莲花的花心，散发淡淡清香，净心凝神效果极佳。"},
    {"name": "地龙髓", "quality_level": 3, "description": "地脉中灵龙残留的骨髓精华，色泽金黄如琥珀，蕴含磅礴土灵之气。"},

    # ========== 上品(4) ==========
    {"name": "玄冰精髓", "quality_level": 4, "description": "万年玄冰凝成的核心，寒气内敛却足以冻裂金丹修士护体灵光，是冰系灵物的极致。"},
    {"name": "烈凤心血", "quality_level": 4, "description": "火凤心头三滴血之一，蕴含极致火灵精华，灼热气息令人窒息。"},
    {"name": "乙木精华", "quality_level": 4, "description": "东方甲乙木之精，能催化万物生机，是木系灵物的巅峰之作。"},
    {"name": "太白精金", "quality_level": 4, "description": "金之极致凝练，传说可破天穹，锐利之气能撕裂空间。"},
    {"name": "幽冥魂晶", "quality_level": 4, "description": "幽冥界最纯净的魂魄结晶，散发着幽冷寒光，可稳固神魂、照见幽冥。"},
    {"name": "天雷符骨", "quality_level": 4, "description": "渡劫残留的天雷印记凝固而成，蕴含天雷之威，是炼器的至宝。"},

    # ========== 极品(5) ==========
    {"name": "九幽寒莲", "quality_level": 5, "description": "九幽深处绽放的寒莲，亿年凝结一朵，花瓣晶莹如冰雕，可遇不可求的绝世奇珍。"},
    {"name": "涅槃火羽", "quality_level": 5, "description": "凤凰涅槃时落下的羽翼，蕴含轮回之火，涅槃真意内敛其中。"},
    {"name": "建木之种", "quality_level": 5, "description": "上古神木建木的种子，蕴含开天辟地之力，可令枯木逢春、老树新芽。"},
    {"name": "太虚真金", "quality_level": 5, "description": "太虚之中诞生的金属，传说可铸神器，蕴含太虚玄妙之力。"},
    {"name": "轮回冥晶", "quality_level": 5, "description": "轮回之力凝聚的晶体，可令亡魂转世、轮回往生，是幽冥至宝。"},
    {"name": "天罚雷种", "quality_level": 5, "description": "天劫雷罚的本源，蕴含天道惩戒之力，可降下天罚雷劫。"},

    # ========== 仙品(6) ==========
    {"name": "鸿蒙紫莲", "quality_level": 6, "description": "鸿蒙紫气化成的莲花，通体紫色祥光缭绕，是超越仙界的至宝，蕴含鸿蒙大道。"},
    {"name": "凤凰真血", "quality_level": 6, "description": "凤凰一族至高无上的精血，赤金交织、璀璨夺目，可令万物涅槃重生。"},
    {"name": "混沌灵根", "quality_level": 6, "description": "混沌中诞生的灵根，蕴含万法之源，是先天灵根中的极品。"},
    {"name": "天玄真银", "quality_level": 6, "description": "天外玄银凝结而成，可承载天道法则，是炼制仙器的无上主材。"},
    {"name": "幽冥本源", "quality_level": 6, "description": "幽冥界的本源之力，掌管生死轮回，幽暗深邃似有无尽奥秘。"},
    {"name": "天道雷种", "quality_level": 6, "description": "天道雷罚的本源，蕴含天道意志，雷声轰鸣似天公发怒。"},

    # ========== 先天至宝(7) ==========
    {"name": "开天神石", "quality_level": 7, "description": "开天辟地时诞生的第一块神石，蕴含创世神力，是超越一切的存在。"},
    {"name": "盘古精血", "quality_level": 7, "description": "盘古大神遗落的精血，金光万丈、力可破天，是力量的极致体现。"},
    {"name": "造化玉蝶", "quality_level": 7, "description": "造化神器，传说可重塑天地法则，是造化之力的具象化体现。"},
    {"name": "天道玉髓", "quality_level": 7, "description": "蕴含完整天道法则的玉髓，晶莹剔透却深不可测，是修行的极致追求。"},
    {"name": "轮回祖符", "quality_level": 7, "description": "轮回法则的本源体现，蕴含万物轮回之理，可操控生死轮回。"},
    {"name": "本源雷种", "quality_level": 7, "description": "宇宙初开时的第一道雷霆，雷声震天动地，是雷之无上本源。"},
]

# =============================================================================
# 全新扩展：珍稀丹药配方材料
# =============================================================================

EXTRA_PILL_MATERIALS = [
    # 下品炼丹药材
    {"name": "清心兰", "quality_level": 2, "description": "清新淡雅的兰花，散发幽幽清香，有安定心神之效，是炼制清心类丹药的常用药材。"},
    {"name": "续骨藤", "quality_level": 2, "description": "接骨续筋的灵藤，藤蔓坚韧如铁，是疗伤丹的不可或缺的主药。"},
    {"name": "化毒草", "quality_level": 2, "description": "可解百毒的灵草，叶片泛着淡淡绿光，炼丹时常作为药引入药。"},
    # 中品炼丹药材
    {"name": "九转雪莲", "quality_level": 3, "description": "在雪山之巅九转而成的雪莲，花瓣晶莹如冰雪雕琢，极其珍贵罕见。"},
    {"name": "龙涎香", "quality_level": 3, "description": "巨龙陨落后口水凝结而成，色泽金黄如琥珀，蕴含龙之精气。"},
    {"name": "凤尾草", "quality_level": 3, "description": "形似凤凰尾羽的灵草，叶片赤红如火，蕴含火凤之力。"},
    # 上品炼丹药材
    {"name": "不死神树皮", "quality_level": 4, "description": "不死神木的树皮，散发着古老而神秘的气息，据说可令枯木逢春、老树新芽。"},
    {"name": "仙鹤顶红", "quality_level": 4, "description": "仙鹤修炼精华凝聚于头顶，呈鲜红色，极其稀有难得一见。"},
    {"name": "麒麟角粉", "quality_level": 4, "description": "麒麟神兽的角研磨而成，散发着祥瑞金光，蕴含祥瑞之气。"},
    # 极品炼丹药材
    {"name": "人参果精", "quality_level": 5, "description": "万年人参修炼成精后所化，形如小人栩栩如生，蕴含无尽生机。"},
    {"name": "龙龟贝壳", "quality_level": 5, "description": "龙龟神兽的贝壳，坚硬如铁却流光溢彩，蕴含水火既济之力。"},
    {"name": "朱雀心核", "quality_level": 5, "description": "朱雀神兽的心核，赤红如血却晶莹剔透，蕴含极致的火之力量。"},
    # 仙品炼丹药材
    {"name": "混沌祖气", "quality_level": 6, "description": "混沌初开时的祖气，缭绕着混沌之力氤氲，是炼丹的至高药引。"},
    {"name": "阴阳无极水", "quality_level": 6, "description": "阴阳交泰之处诞生的神水，水面呈现黑白太极之象，可化解一切偏性。"},
    {"name": "五行本源", "quality_level": 6, "description": "金木水火土五行本源之力，五色光芒缭绕，是丹道追求的极致。"},
    # 先天至宝炼丹药材
    {"name": "天道精华", "quality_level": 7, "description": "抽取天道法则的精华炼制而成，蕴含完整天道意志，是真正的神丹之材。"},
    {"name": "时空源晶", "quality_level": 7, "description": "时空法则凝聚的晶体，表面似有时光流转，可令时光倒流。"},
    {"name": "命运之种", "quality_level": 7, "description": "命运法则的具象化，若隐若现、神秘莫测，传说可改写命数。"},
]

# =============================================================================
# 全新扩展：珍稀炼器材料
# =============================================================================

EXTRA_ARTIFACT_MATERIALS = [
    # 凡品炼器材料
    {"name": "玄铁残片", "quality_level": 1, "description": "普通玄铁的边角料，色泽深沉，可用于练手炼器。"},
    {"name": "灵木碎屑", "quality_level": 1, "description": "灵木加工时的碎屑，有微弱灵气，适合新手练手用。"},
    # 下品炼器材料
    {"name": "精钢", "quality_level": 2, "description": "提炼过的优质钢材，色泽银亮，有一定灵性，可用于打造基础兵器。"},
    {"name": "千年阴沉木", "quality_level": 2, "description": "埋藏千年的木头，质地紧密如铁，色泽黑沉，蕴含阴柔之力。"},
    {"name": "银丝草", "quality_level": 2, "description": "可抽取银丝的灵草，柔韧度极佳，是炼制绳索类法宝的上好材料。"},
    # 中品炼器材料
    {"name": "寒铁", "quality_level": 3, "description": "寒泉中淬炼的铁，硬度极高且耐高温，散发着冷冽光芒。"},
    {"name": "火牛角", "quality_level": 3, "description": "火牛妖的角，蕴含火属性灵力，角尖隐隐有火焰缭绕。"},
    {"name": "玄武岩", "quality_level": 3, "description": "蕴含玄武血脉的岩石，厚重如山，防御力极强。"},
    # 上品炼器材料
    {"name": "陨铁寒晶", "quality_level": 4, "description": "天外陨铁中提炼的寒晶，寒气逼人却内蕴星辉，是极品炼器材料。"},
    {"name": "金翅大鹏羽", "quality_level": 4, "description": "金翅大鹏的羽毛，金光灿烂、羽纹如风，蕴含极速之力。"},
    {"name": "白虎神金", "quality_level": 4, "description": "白虎血脉凝聚的金属，散发着杀伐之气，攻伐之力无双。"},
    # 极品炼器材料
    {"name": "九天玄玉", "quality_level": 5, "description": "九天神玉，五色光芒缭绕，蕴含天地至理，可遇不可求。"},
    {"name": "青龙帝藤", "quality_level": 5, "description": "青龙神木的藤蔓，青光流转、生机勃勃，蕴含生命之力。"},
    {"name": "玄武龟甲", "quality_level": 5, "description": "玄武神兽的龟甲，坚硬如磐石、是防御之最，可为主人抵挡致命攻击。"},
    # 仙品炼器材料
    {"name": "天外玄铁", "quality_level": 6, "description": "天外星辰坠落的玄铁，表面有星辰纹路，只在传说中出现。"},
    {"name": "鲲鹏巨羽", "quality_level": 6, "description": "鲲鹏神兽的羽毛，宽大如云、扶摇直上九万里，蕴含极速真意。"},
    {"name": "麒麟神金", "quality_level": 6, "description": "麒麟神兽精华凝聚的金属，金光灿灿、样瑞缠身，祥瑞与力量并存。"},
    # 先天至宝炼器材料
    {"name": "创世神铁", "quality_level": 7, "description": "开天辟地时诞生的神铁，蕴含创世神力，是超越一切的最强炼器材料。"},
    {"name": "混沌羽毛", "quality_level": 7, "description": "混沌中诞生的羽毛，紫气氤氲，蕴含混沌之力，可撕裂诸天万界。"},
    {"name": "大道金莲", "quality_level": 7, "description": "承载大道的金莲，莲台之上道纹流转，是无上至宝的象征。"},
]

# =============================================================================
# 全新扩展：符箓材料
# =============================================================================

EXTRA_TALISMAN_MATERIALS = [
    # 凡品符箓材料
    {"name": "黄纸符", "quality_level": 1, "description": "最基础的符纸，色泽土黄，可绘制最简单的符箓，是符师入门的首选。"},
    {"name": "朱砂", "quality_level": 1, "description": "普通朱砂，色泽赤红，是绘制符箓的基本材料，可引导灵力入符。"},
    # 下品符箓材料
    {"name": "灵蚕丝", "quality_level": 2, "description": "灵蚕吐的丝，银白细腻、柔韧有力，可绘制更持久的符箓。"},
    {"name": "黑狗血", "quality_level": 2, "description": "黑狗血可辟邪，是符箓常用的引子材料，带有凛然正气。"},
    # 中品符箓材料
    {"name": "妖狐尾毛", "quality_level": 3, "description": "妖狐的尾巴毛，毛尖泛着幽光，蕴含幻化之力，可增强符箓的迷惑性。"},
    {"name": "雷击桃木", "quality_level": 3, "description": "被天雷劈中的桃木，木心焦黑却灵纹隐现，辟邪效果极佳。"},
    {"name": "鬼画符骨", "quality_level": 3, "description": "古修用鬼文刻写的符骨，骨面幽光流转，有神秘力量蛰伏其中。"},
    # 上品符箓材料
    {"name": "天师袍角", "quality_level": 4, "description": "得道天师袍角的一角，布帛上灵纹流转，蕴含道法之力。"},
    {"name": "白虎胡须", "quality_level": 4, "description": "白虎神兽的胡须，金白相间、锋锐如针，可增强符箓威力。"},
    {"name": "真武水精", "quality_level": 4, "description": "真武荡魔大帝遗落的水精，晶莹剔透却蕴含荡魔之力。"},
    # 极品符箓材料
    {"name": "天师传承符骨", "quality_level": 5, "description": "历代天师传承的符骨，骨面刻满道纹，蕴含完整道统。"},
    {"name": "青龙之鳞", "quality_level": 5, "description": "青龙神兽的鳞片，青光流转、电弧缭绕，蕴含生命与风雷之力。"},
    {"name": "朱雀神羽", "quality_level": 5, "description": "朱雀神兽的羽毛，火焰缭绕、涅槃之意内敛，蕴含涅槃真火。"},
    # 仙品符箓材料
    {"name": "大道符纸", "quality_level": 6, "description": "用大道之力书写的符纸，表面道纹流转，可承载天威。"},
    {"name": "天罚雷竹", "quality_level": 6, "description": "承受天罚雷劫的竹子，竹身焦黑却雷纹密布，蕴含天道惩罚之力。"},
    {"name": "六道轮回砂", "quality_level": 6, "description": "六道轮回之地的黄砂，六色流转、蕴含轮回法则碎片。"},
    # 先天至宝符箓材料
    {"name": "天道玉纸", "quality_level": 7, "description": "以天道之力凝聚的玉纸，通透如冰却蕴含天道法则，可书写命运。"},
    {"name": "混沌雷种", "quality_level": 7, "description": "混沌中诞生的雷种，紫雷缭绕、混沌气翻涌，蕴含混沌神雷。"},
    {"name": "轮回大道符", "quality_level": 7, "description": "由轮回法则凝聚的神符，幽光弥漫、因果缠绕，可逆转生死。"},
    {"name": "补天玉彩", "quality_level": 7, "description": "女娲补天时遗留的玉彩，五色交织、流光溢彩，蕴含造化之力，可重塑肢体，是疗伤圣物的极致材料。"},
    {"name": "盘古战鼓皮", "quality_level": 7, "description": "以盘古皮膜制成的鼓面，金光灿灿、蕴含开天之力，敲响时可震动诸天万界。"},
]


EXTRA_MATERIALS = [
    # ========== 原有珍稀材料 ==========
    {"name": "定魄灵砂", "quality_level": 3, "description": "带着沉静神魂波动的细砂，色泽银白，多用来炼制定心、守神一类灵物。"},
    {"name": "霓裳花露", "quality_level": 3, "description": "只在朝霞最盛时凝成的花露，灵气温润而轻盈，散发七彩虹光。"},
    {"name": "承运木心", "quality_level": 4, "description": "千年灵木最深处的心材，色泽金黄、纹理如云，能稳住气运与因果牵引。"},
    {"name": "星命玉枝", "quality_level": 4, "description": "被夜色浸透的玉化枝条，通体墨绿隐隐发光，常见于推演命数类器物。"},
    {"name": "龙门真水", "quality_level": 5, "description": "逆流而上的灵水结晶，晶莹剔透却蕴含龙门之力，最适合炼制蜕变、问心类奇药。"},
    {"name": "天眷符骨", "quality_level": 5, "description": "自古阵遗骸中析出的符骨，骨面刻满神秘纹路，常用来承载高阶机缘符纹。"},
    {"name": "镜尘玄晶", "quality_level": 4, "description": "长年被镜湖幻光磨洗后的玄晶粉尘，剔透如镜，能稳神识、照见气机细节。"},
    {"name": "离魄藤种", "quality_level": 4, "description": "埋在阴阳交汇处的古藤种子，外壳漆黑如墨，既可封脉也可守窍。"},
    {"name": "曜金雷髓", "quality_level": 5, "description": "雷火同炼后的曜金精髓，金红交织、雷电缭绕，最适合打造高压攻伐灵物。"},
    {"name": "烬天火纹石", "quality_level": 5, "description": "被天火烙出天然火纹的异石，石面火纹流转、炽热难当，蕴含持久炽烈的爆发力。"},
    # ========== 新增：垂钓主题材料 ==========
    {"name": "溪纹石", "quality_level": 1, "description": "常年浸在浅溪中的卵石，石面自生水纹灵痕，是初学炼器时常见的温润辅材。"},
    {"name": "银鳞藻", "quality_level": 1, "description": "细长如丝的浅水灵藻，叶面泛着鱼鳞般微光，可入丹也可作符墨辅料。"},
    {"name": "月魄蚌珠", "quality_level": 2, "description": "寒月灵湖深处老蚌所孕之珠，珠内含一缕柔寒月华，常用于宁神养识。"},
    {"name": "寒潭藻心", "quality_level": 2, "description": "生于冷潭暗流中央的藻心，触手冰凉，最适合炼制寒性丹药与凝神符水。"},
    {"name": "熔鳞砂", "quality_level": 3, "description": "火鳞熔潭边缘析出的赤金细砂，摸上去仍有余温，是火土双属灵材。"},
    {"name": "潮音珊瑚", "quality_level": 3, "description": "吸纳潮声灵韵而生的珊瑚枝，贴耳可闻若有若无的海潮回响。"},
    {"name": "星潮玄砂", "quality_level": 4, "description": "只在夜潮最盛时浮上水面的幽蓝砂砾，兼具星辉与潮汐气机，善养神识。"},
    {"name": "龙涡骨片", "quality_level": 4, "description": "深水妖兽遗骨被漩涡磨成的骨片，表面遍布旋流纹，最擅承载卸力护身之势。"},
    {"name": "海眼寒晶", "quality_level": 5, "description": "星渊古海海眼喷涌后凝成的寒晶，内外温差极端，常被用来炼制重宝。"},
    {"name": "赤髓炎珀", "quality_level": 5, "description": "熔潭最深处浮出的炎珀，内部似有熔火髓液缓缓流动，极适合攻伐类灵物。"},
    {"name": "星渊潮核", "quality_level": 6, "description": "由星潮与古海灵压共同压成的潮汐核心，握于手中仿佛能牵动整片海面。"},
    {"name": "归墟道纹贝", "quality_level": 7, "description": "极少自归墟暗流中漂出的古贝，道纹天然成环，内蕴深海大道余韵。"},
    # ========== 新增：凡品材料 ==========
    {"name": "灵露滴", "quality_level": 1, "description": "晨露凝聚的灵力露珠，晶莹剔透，最基础的灵材之一。"},
    {"name": "枯叶草", "quality_level": 1, "description": "随处可见的灵草，枯黄叶片却蕴含微弱灵气，适合新手练手用。"},
    {"name": "碎石粉", "quality_level": 1, "description": "普通山石研磨而成，粉质细腻，可作为炼器时的填充辅料。"},
    {"name": "引路萤火", "quality_level": 1, "description": "夜晚灵山里闪光的萤火，如星点洒落，可指引方向也可用作炼材。"},
    {"name": "残月水", "quality_level": 1, "description": "月光下凝结的水滴，泛着淡淡银光，有微弱的安神效果。"},
    {"name": "翠竹片", "quality_level": 1, "description": "灵山翠竹削下的薄片，色泽翠绿、蕴含清风气息，是炼制杖类法宝的基础材料。"},
    {"name": "草灵纤维", "quality_level": 1, "description": "灵草精华编织而成的纤维，柔韧却蕴含生机之力。"},
    # ========== 新增：下品材料 ==========
    {"name": "霜凌草", "quality_level": 2, "description": "在寒霜中生长的灵草，叶片如剑、锋芒内敛，性寒，可用于炼制冰系丹药。"},
    {"name": "烈阳花", "quality_level": 2, "description": "向阳而开的灵花，花瓣如火、热情炽烈，性热，是火系丹药的主材。"},
    {"name": "风灵石", "quality_level": 2, "description": "蕴含风灵气的结晶，轻盈剔透、随风摇曳，可用于炼制轻灵类法宝。"},
    {"name": "浊煞泥", "quality_level": 2, "description": "阴气淤积之地产生的泥垢，漆黑如墨、可用于炼制护体类法器。"},
    {"name": "裂木甲", "quality_level": 2, "description": "被雷劈开的灵木外皮，纹理如鳞、残留雷痕，导电性好，适合雷系符箓。"},
    {"name": "幽冥粉", "quality_level": 2, "description": "幽暗处生长的菌类孢子，幽光隐隐，有迷幻效果，可入药。"},
    {"name": "清心兰", "quality_level": 2, "description": "清新淡雅的兰花，散发幽幽清香，有安定心神之效。"},
    {"name": "续骨藤", "quality_level": 2, "description": "接骨续筋的灵藤，藤蔓如铁、韧性十足，是疗伤丹的主药。"},
    {"name": "化毒草", "quality_level": 2, "description": "可解百毒的灵草，叶片翠绿泛光，炼丹时常作为药引。"},
    {"name": "精钢", "quality_level": 2, "description": "提炼过的优质钢材，色泽银亮，有一定灵性。"},
    {"name": "千年阴沉木", "quality_level": 2, "description": "埋藏千年的木头，质地紧密、色泽黑沉，蕴含阴柔之力。"},
    {"name": "银丝草", "quality_level": 2, "description": "可抽取银丝的灵草，柔韧度极佳，是炼制绳索类法宝的上好材料。"},
    {"name": "灵蚕丝", "quality_level": 2, "description": "灵蚕吐的丝，银白细腻，可绘制更持久的符箓。"},
    {"name": "黑狗血", "quality_level": 2, "description": "黑狗血可辟邪，色泽黑红，是符箓常用的引子材料。"},
    {"name": "雷击桃木心", "quality_level": 2, "description": "被天雷劈中的桃木内心，木心焦黑却灵纹隐现，蕴含天雷余威，是炼制雷系法宝的上佳材料。"},
    {"name": "导电精金", "quality_level": 2, "description": "精金经过雷劫淬炼，金光中夹杂雷纹，导电性极佳，是雷系法宝的优良载体。"},
    {"name": "霜风草", "quality_level": 2, "description": "在寒风中生长的灵草，叶片泛着霜光，蕴含霜风之气，可用于冰风双系法宝。"},
    {"name": "玄武岩片", "quality_level": 2, "description": "玄武岩削成的薄片，厚重如山、质地坚硬，是炼制盾类法宝的好材料。"},
    # ========== 新增：中品材料 ==========
    {"name": "冰魄珠", "quality_level": 3, "description": "寒潭深处的冰灵结晶，通体幽蓝剔透，可大幅提升丹药的清凉属性。"},
    {"name": "火鸾羽", "quality_level": 3, "description": "火鸾妖禽脱落的羽毛，羽尖隐隐有火焰缭绕，蕴含炽热灵力。"},
    {"name": "木灵精", "quality_level": 3, "description": "千年古木所化的精魄之物，散发着草木清香，蕴含生生不息之气。"},
    {"name": "金芒砂", "quality_level": 3, "description": "金属性灵石矿脉中析出的精华，硬度极高。"},
    {"name": "净水莲心", "quality_level": 3, "description": "灵泉中莲花的花心，散发淡淡清香，净心凝神效果极佳。"},
    {"name": "地龙髓", "quality_level": 3, "description": "地脉中灵龙残留的骨髓精华，色泽金黄如琥珀，蕴含磅礴土灵之气。"},
    {"name": "九转雪莲", "quality_level": 3, "description": "在雪山之巅九转而成的雪莲，花瓣晶莹如冰雪雕琢，极其珍贵。"},
    {"name": "龙涎香", "quality_level": 3, "description": "巨龙陨落后口水凝结而成，色泽金黄如琥珀，蕴含龙之精气。"},
    {"name": "凤尾草", "quality_level": 3, "description": "形似凤凰尾羽的灵草，叶片赤红如火，蕴含火凤之力。"},
    {"name": "寒铁", "quality_level": 3, "description": "寒泉中淬炼的铁，散发着冷冽光芒，硬度极高且耐高温。"},
    {"name": "火牛角", "quality_level": 3, "description": "火牛妖的角，角尖隐有火焰跳动，蕴含火属性灵力。"},
    {"name": "玄武岩", "quality_level": 3, "description": "蕴含玄武血脉的岩石，厚重如山，防御力极强。"},
    {"name": "妖狐尾毛", "quality_level": 3, "description": "妖狐的尾巴毛，毛尖泛着幽光，蕴含幻化之力。"},
    {"name": "雷击桃木", "quality_level": 3, "description": "被天雷劈中的桃木，木心焦黑却灵纹隐现，辟邪效果极佳。"},
    {"name": "鬼画符骨", "quality_level": 3, "description": "古修用鬼文刻写的符骨，骨面幽光流转，有神秘力量蛰伏。"},
    {"name": "仙鹤腿骨", "quality_level": 3, "description": "仙鹤妖禽的腿骨，剑形天生、骨质如玉，是炼制剑类法宝的珍稀材料。"},
    {"name": "仙鹤羽", "quality_level": 3, "description": "仙鹤妖禽的羽毛，轻盈如雪、洁白无瑕，可作为剑穗或扇面材料。"},
    {"name": "焰虎牙", "quality_level": 3, "description": "火虎妖的獠牙，牙尖火焰缭绕，蕴含猛烈火焰精华，是炼制斧类法宝的上等材料。"},
    {"name": "玄狐皮", "quality_level": 3, "description": "玄色妖狐的皮毛，柔韧如绸、泛着幽光，可编织成盾面，卸力卸法。"},
    {"name": "树灵根", "quality_level": 3, "description": "千年古树的树根精华，散发着草木清香，蕴含生生不息之气，是疗伤类法宝的材料。"},
    # ========== 新增：上品材料 ==========
    {"name": "玄冰精髓", "quality_level": 4, "description": "万年玄冰凝成的核心，寒气内敛却足以冻裂金丹修士护体灵光，是冰系灵物的极致。"},
    {"name": "烈凤心血", "quality_level": 4, "description": "火凤心头三滴血之一，蕴含极致火灵精华，灼热气息令人窒息。"},
    {"name": "乙木精华", "quality_level": 4, "description": "东方甲乙木之精，能催化万物生机，是木系灵物的巅峰之作。"},
    {"name": "太白精金", "quality_level": 4, "description": "金之极致凝练，传说可破天穹，锐利之气能撕裂空间。"},
    {"name": "幽冥魂晶", "quality_level": 4, "description": "幽冥界最纯净的魂魄结晶，散发着幽冷寒光，可稳固神魂、照见幽冥。"},
    {"name": "天雷符骨", "quality_level": 4, "description": "渡劫残留的天雷印记凝固而成，蕴含天雷之威，是炼器的至宝。"},
    {"name": "不死神树皮", "quality_level": 4, "description": "不死神木的树皮，散发着古老而神秘的气息，据说可令枯木逢春、老树新芽。"},
    {"name": "仙鹤顶红", "quality_level": 4, "description": "仙鹤修炼精华凝聚于头顶，呈鲜红色，极其稀有难得一见。"},
    {"name": "麒麟角粉", "quality_level": 4, "description": "麒麟神兽的角研磨而成，散发着祥瑞金光，蕴含祥瑞之气。"},
    {"name": "陨铁寒晶", "quality_level": 4, "description": "天外陨铁中提炼的寒晶，是极品炼器材料。"},
    {"name": "金翅大鹏羽", "quality_level": 4, "description": "金翅大鹏的羽毛，金光灿烂、羽纹如风，蕴含极速之力。"},
    {"name": "白虎神金", "quality_level": 4, "description": "白虎血脉凝聚的金属，散发着杀伐之气，攻伐之力无双。"},
    {"name": "天师袍角", "quality_level": 4, "description": "得道天师袍角的一角，布帛上灵纹流转，蕴含道法之力。"},
    {"name": "白虎胡须", "quality_level": 4, "description": "白虎神兽的胡须，金白相间、锋锐如针，可增强符箓威力。"},
    {"name": "真武水精", "quality_level": 4, "description": "真武荡魔大帝遗落的水精，晶莹剔透却蕴含荡魔之力。"},
    {"name": "月华霜", "quality_level": 4, "description": "寒月精华凝结而成的霜晶，蕴含月华之力，可令万物凝结成霜。"},
    {"name": "朱雀心血", "quality_level": 4, "description": "朱雀神兽的心头精血，比烈凤心血更为炽热，是火系法宝的至高材料。"},
    {"name": "冥幽铁", "quality_level": 4, "description": "幽冥界深处的寒铁，漆黑如墨，蕴含幽冥之力，是炼制幽冥甲的核心材料。"},
    # ========== 新增：极品材料 ==========
    {"name": "九幽寒莲", "quality_level": 5, "description": "九幽深处绽放的寒莲，亿年凝结一朵，花瓣晶莹如冰雕，可遇不可求的绝世奇珍。"},
    {"name": "涅槃火羽", "quality_level": 5, "description": "凤凰涅槃时落下的羽翼，蕴含轮回之火，涅槃真意内敛其中。"},
    {"name": "建木之种", "quality_level": 5, "description": "上古神木建木的种子，蕴含开天辟地之力，可令枯木逢春、老树新芽。"},
    {"name": "太虚真金", "quality_level": 5, "description": "太虚之中诞生的金属，传说可铸神器，蕴含太虚玄妙之力。"},
    {"name": "轮回冥晶", "quality_level": 5, "description": "轮回之力凝聚的晶体，可令亡魂转世、轮回往生，是幽冥至宝。"},
    {"name": "天罚雷种", "quality_level": 5, "description": "天劫雷罚的本源，蕴含天道惩戒之力，可降下天罚雷劫。"},
    {"name": "人参果精", "quality_level": 5, "description": "万年人参修炼成精后所化，形如小人栩栩如生，蕴含无尽生机。"},
    {"name": "龙龟贝壳", "quality_level": 5, "description": "龙龟神兽的贝壳，坚硬如铁却流光溢彩，蕴含水火既济之力。"},
    {"name": "朱雀心核", "quality_level": 5, "description": "朱雀神兽的心核，赤红如血却晶莹剔透，蕴含极致的火之力量。"},
    {"name": "九天玄玉", "quality_level": 5, "description": "九天神玉，五色光芒缭绕，蕴含天地至理，可遇不可求。"},
    {"name": "青龙帝藤", "quality_level": 5, "description": "青龙神木的藤蔓，青光流转、生机勃勃，蕴含生命之力。"},
    {"name": "玄武龟甲", "quality_level": 5, "description": "玄武神兽的龟甲，坚硬如磐石，是防御之最，可为主人抵挡致命攻击。"},
    {"name": "天师传承符骨", "quality_level": 5, "description": "历代天师传承的符骨，蕴含完整道统。"},
    {"name": "青龙之鳞", "quality_level": 5, "description": "青龙神兽的鳞片，蕴含生命与风雷之力。"},
    {"name": "朱雀神羽", "quality_level": 5, "description": "朱雀神兽的羽毛，蕴含涅槃真火。"},
    {"name": "六道轮回砂", "quality_level": 5, "description": "六道轮回之地的黄砂，蕴含轮回法则碎片，是炼制轮回类法宝的必需材料。"},
    {"name": "天裂雷晶", "quality_level": 5, "description": "天雷劈开大地时凝结的晶体，蕴含天裂之威，是炼制天罚类法宝的核心材料。"},
    # ========== 新增：仙品材料 ==========
    {"name": "鸿蒙紫莲", "quality_level": 6, "description": "鸿蒙紫气化成的莲花，通体紫色祥光缭绕，是超越仙界的至宝，蕴含鸿蒙大道。"},
    {"name": "凤凰真血", "quality_level": 6, "description": "凤凰一族至高无上的精血，赤金交织、璀璨夺目，可令万物涅槃重生。"},
    {"name": "混沌灵根", "quality_level": 6, "description": "混沌中诞生的灵根，蕴含万法之源，是先天灵根中的极品。"},
    {"name": "天玄真银", "quality_level": 6, "description": "天外玄银凝结而成，可承载天道法则，是炼制仙器的无上主材。"},
    {"name": "幽冥本源", "quality_level": 6, "description": "幽冥界的本源之力，掌管生死轮回，幽暗深邃似有无尽奥秘。"},
    {"name": "天道雷种", "quality_level": 6, "description": "天道雷罚的本源，蕴含天道意志，雷声轰鸣似天公发怒。"},
    {"name": "混沌祖气", "quality_level": 6, "description": "混沌初开时的祖气，缭绕着混沌之力氤氲，是炼丹的至高药引。"},
    {"name": "阴阳无极水", "quality_level": 6, "description": "阴阳交泰之处诞生的神水，水面呈现黑白太极之象，可化解一切偏性。"},
    {"name": "五行本源", "quality_level": 6, "description": "金木水火土五行本源之力，五色光芒缭绕，是丹道追求的极致。"},
    {"name": "天外玄铁", "quality_level": 6, "description": "天外星辰坠落的玄铁，只在传说中出现。"},
    {"name": "鲲鹏巨羽", "quality_level": 6, "description": "鲲鹏神兽的羽毛，可扶摇直上九万里。"},
    {"name": "麒麟神金", "quality_level": 6, "description": "麒麟神兽精华凝聚的金属，祥瑞与力量并存。"},
    {"name": "大道符纸", "quality_level": 6, "description": "用大道之力书写的符纸，可承载天威。"},
    {"name": "天罚雷竹", "quality_level": 6, "description": "承受天罚雷劫的竹子，蕴含天道惩罚之力。"},
    {"name": "六道轮回砂", "quality_level": 6, "description": "六道轮回之地的黄砂，蕴含轮回法则。"},
    {"name": "星辰之泪", "quality_level": 6, "description": "星辰之力凝结成的晶体，如泪滴形，蕴含星辰本源之力，是炼制琴类法宝的神材。"},
    # ========== 新增：先天至宝材料 ==========
    {"name": "开天神石", "quality_level": 7, "description": "开天辟地时诞生的第一块神石，蕴含创世神力，是超越一切的存在。"},
    {"name": "盘古精血", "quality_level": 7, "description": "盘古大神遗落的精血，金光万丈、力可破天，是力量的极致体现。"},
    {"name": "造化玉蝶", "quality_level": 7, "description": "造化神器，传说可重塑天地法则，是造化之力的具象化体现。"},
    {"name": "天道玉髓", "quality_level": 7, "description": "蕴含完整天道法则的玉髓，晶莹剔透却深不可测，是修行的极致追求。"},
    {"name": "轮回祖符", "quality_level": 7, "description": "轮回法则的本源体现，蕴含万物轮回之理，可操控生死轮回。"},
    {"name": "本源雷种", "quality_level": 7, "description": "宇宙初开时的第一道雷霆，雷声震天动地，是雷之无上本源。"},
    {"name": "天道精华", "quality_level": 7, "description": "抽取天道法则的精华炼制而成，蕴含完整天道意志，是真正的神丹之材。"},
    {"name": "时空源晶", "quality_level": 7, "description": "时空法则凝聚的晶体，表面似有时光流转，可令时光倒流。"},
    {"name": "命运之种", "quality_level": 7, "description": "命运法则的具象化，若隐若现、神秘莫测，传说可改写命数。"},
    {"name": "创世神铁", "quality_level": 7, "description": "开天辟地时诞生的神铁，蕴含创世神力，是超越一切的最强炼器材料。"},
    {"name": "混沌羽毛", "quality_level": 7, "description": "混沌中诞生的羽毛，紫气氤氲，蕴含混沌之力，可撕裂诸天万界。"},
    {"name": "大道金莲", "quality_level": 7, "description": "承载大道的金莲，莲台之上道纹流转，是无上至宝的象征。"},
    {"name": "天道玉纸", "quality_level": 7, "description": "以天道之力凝聚的玉纸，可书写命运。"},
    {"name": "混沌雷种", "quality_level": 7, "description": "混沌中诞生的雷种，蕴含混沌神雷。"},
    {"name": "轮回大道符", "quality_level": 7, "description": "由轮回法则凝聚的神符，可逆转生死。"},
]


def _merge_material_catalogs(*catalogs: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    for catalog in catalogs:
        for item in catalog:
            merged[str(item["name"])] = dict(item)
    return list(merged.values())


FARMABLE_MATERIAL_RULES: dict[str, dict[str, object]] = {
    "灵露滴": {
        "can_plant": True,
        "seed_price_stone": 10,
        "growth_minutes": 30,
        "yield_min": 2,
        "yield_max": 4,
        "unlock_realm_stage": "炼气",
        "unlock_realm_layer": 1,
    },
    "枯叶草": {
        "can_plant": True,
        "seed_price_stone": 8,
        "growth_minutes": 36,
        "yield_min": 2,
        "yield_max": 5,
        "unlock_realm_stage": "炼气",
        "unlock_realm_layer": 1,
    },
    "残月水": {
        "can_plant": True,
        "seed_price_stone": 14,
        "growth_minutes": 45,
        "yield_min": 2,
        "yield_max": 3,
        "unlock_realm_stage": "炼气",
        "unlock_realm_layer": 2,
    },
    "清心兰": {
        "can_plant": True,
        "seed_price_stone": 28,
        "growth_minutes": 90,
        "yield_min": 1,
        "yield_max": 3,
        "unlock_realm_stage": "炼气",
        "unlock_realm_layer": 5,
    },
    "续骨藤": {
        "can_plant": True,
        "seed_price_stone": 32,
        "growth_minutes": 100,
        "yield_min": 1,
        "yield_max": 3,
        "unlock_realm_stage": "筑基",
        "unlock_realm_layer": 1,
    },
    "化毒草": {
        "can_plant": True,
        "seed_price_stone": 36,
        "growth_minutes": 110,
        "yield_min": 1,
        "yield_max": 3,
        "unlock_realm_stage": "筑基",
        "unlock_realm_layer": 2,
    },
    "霜凌草": {
        "can_plant": True,
        "seed_price_stone": 48,
        "growth_minutes": 126,
        "yield_min": 1,
        "yield_max": 3,
        "unlock_realm_stage": "筑基",
        "unlock_realm_layer": 3,
    },
    "烈阳花": {
        "can_plant": True,
        "seed_price_stone": 52,
        "growth_minutes": 132,
        "yield_min": 1,
        "yield_max": 3,
        "unlock_realm_stage": "筑基",
        "unlock_realm_layer": 3,
    },
    "凤尾草": {
        "can_plant": True,
        "seed_price_stone": 88,
        "growth_minutes": 180,
        "yield_min": 1,
        "yield_max": 2,
        "unlock_realm_stage": "金丹",
        "unlock_realm_layer": 1,
    },
    "净水莲心": {
        "can_plant": True,
        "seed_price_stone": 96,
        "growth_minutes": 198,
        "yield_min": 1,
        "yield_max": 2,
        "unlock_realm_stage": "金丹",
        "unlock_realm_layer": 2,
    },
    "九转雪莲": {
        "can_plant": True,
        "seed_price_stone": 128,
        "growth_minutes": 240,
        "yield_min": 1,
        "yield_max": 2,
        "unlock_realm_stage": "元婴",
        "unlock_realm_layer": 1,
    },
}


AUTO_FARMABLE_PRICE_BASE = {
    1: 12,
    2: 34,
    3: 86,
    4: 150,
    5: 260,
    6: 460,
    7: 760,
}
AUTO_FARMABLE_GROWTH_MINUTES = {
    1: 42,
    2: 105,
    3: 180,
    4: 270,
    5: 390,
    6: 540,
    7: 720,
}
AUTO_FARMABLE_UNLOCKS = {
    1: ("炼气", 1),
    2: ("炼气", 5),
    3: ("筑基", 3),
    4: ("金丹", 3),
    5: ("元婴", 3),
    6: ("化神", 3),
    7: ("合体", 1),
}
NON_PLANTABLE_RECIPE_MATERIAL_TERMS = ("残页", "丹谱", "符谱", "炼制图")


def _pill_recipe_material_names(recipes: list[dict[str, object]] | None) -> set[str]:
    names: set[str] = set()
    for recipe in recipes or []:
        if str(recipe.get("recipe_kind") or "") != "pill" and str(recipe.get("result_kind") or "") != "pill":
            continue
        for ingredient in recipe.get("ingredients") or []:
            if not isinstance(ingredient, dict):
                continue
            name = str(ingredient.get("material_name") or "").strip()
            if not name or any(term in name for term in NON_PLANTABLE_RECIPE_MATERIAL_TERMS):
                continue
            names.add(name)
    return names


def _auto_farmable_material_rule(material: dict[str, object]) -> dict[str, object]:
    name = str(material.get("name") or "").strip()
    quality = max(min(int(material.get("quality_level") or 1), 7), 1)
    price_base = AUTO_FARMABLE_PRICE_BASE.get(quality, AUTO_FARMABLE_PRICE_BASE[7])
    price_offset = sum(ord(char) for char in name) % 4
    yield_min, yield_max = (2, 5) if quality <= 1 else (1, 3) if quality <= 3 else (1, 2) if quality <= 5 else (1, 1)
    unlock_stage, unlock_layer = AUTO_FARMABLE_UNLOCKS.get(quality, AUTO_FARMABLE_UNLOCKS[7])
    return {
        "can_plant": True,
        "seed_price_stone": price_base + price_offset * max(quality * 4, 4),
        "growth_minutes": AUTO_FARMABLE_GROWTH_MINUTES.get(quality, AUTO_FARMABLE_GROWTH_MINUTES[7]) + price_offset * 6,
        "yield_min": yield_min,
        "yield_max": yield_max,
        "unlock_realm_stage": unlock_stage,
        "unlock_realm_layer": unlock_layer,
    }


def apply_farmable_material_overrides(
    materials: list[dict[str, object]],
    recipes: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    pill_material_names = _pill_recipe_material_names(recipes)
    rows: list[dict[str, object]] = []
    for item in materials:
        payload = dict(item)
        name = str(payload.get("name") or "").strip()
        payload.update(FARMABLE_MATERIAL_RULES.get(name, {}))
        if name in pill_material_names and not bool(payload.get("can_plant")):
            payload.update(_auto_farmable_material_rule(payload))
        rows.append(payload)
    return rows


ALL_EXTRA_MATERIALS = apply_farmable_material_overrides(_merge_material_catalogs(
    NEW_MATERIALS,
    EXTRA_PILL_MATERIALS,
    EXTRA_ARTIFACT_MATERIALS,
    EXTRA_TALISMAN_MATERIALS,
    EXTRA_MATERIALS,
))

