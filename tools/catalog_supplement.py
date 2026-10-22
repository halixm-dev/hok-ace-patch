"""Translations for text the game added after the catalog was built, merged into the catalog as it loads.

The catalog is the PC pipeline's file and is not edited here (`AGENTS.md`), so data updates that add or
reword strings in tables the catalog already covers leave those rows Chinese until upstream catches up.
Game data 1.5.0.1 and 1.6.0.1 added about 1200 such strings to package `1`: an achievement-title system
whose titles come in numbered tiers (`完美橱窗(二)`), four weekly leaderboards ranked 1 to 100, the King of
Kings sub-account, the Line Puppy event, and card texts whose numbers changed. Game data 1.7.0.1 added 335
more: the Super Hero mode, room settings, the reworked Lineup Recommendation, strategy tags, and talent texts
split from their series header. `apply` fills them in.
The official lineups' strategy text is here too: it lives in config bins the catalog does not cover, inside
their share codes, for the share-code pass to write.
`derived` adds the short forms the card-pack covers label each cover with (`逆天改命卡包`, `河洛-李白`),
whose wording the catalog carries only inside its own longer strings; that bin itself was withdrawn. It
also splits the catalog's two-line talent texts into the effect and the series name the new tables hold.

Three rules keep this from becoming a second catalog:

- An entry is added only when the catalog has **no** translation for its Chinese source; a catalog entry
  always wins, so an upstream re-import supersedes this file one string at a time.
- Every target keeps its source's `{placeholders}`, `%s` and `<tags>` exactly; `translate_table` drops a
  record whose placeholders changed, and `check` proves none did.
- Tiered titles and leaderboard ranks are generated, not listed: a tier is the catalog's own name for the
  base title plus a Roman numeral, and a rank is the catalog's own sentence for that leaderboard.

It runs before the glossary (`terminology.apply`), so a supplied string obeys the same one-name-per-keyword
rule as the catalog's.
"""
from __future__ import annotations

import re

# Chinese numerals as the game writes them in tier suffixes and ranks (一 .. 一百).
_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ROMAN = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")
# translate_table compares these between source and target.
_MARKUP = re.compile(r"\{[^{}]*\}|%[sd]|<[^<>]*>")

# zh -> (English, Indonesian). Grouped by where the game shows them.
TEXTS: dict[str, tuple[str, str]] = {
    # Card and skill texts 1.6.0.1 reworded.
    "你的召唤单位阵亡时，会对周围敌人造成{ResCardInfoDataBin_1771_17711_0: 30}点物理伤害。每次召唤还会额外提升该伤害。": (
        "When your summoned units die, they deal {ResCardInfoDataBin_1771_17711_0: 30} Physical Damage to nearby enemies. Each Summon further increases this Damage.",
        "Saat unit summon-mu mati, mereka memberikan {ResCardInfoDataBin_1771_17711_0: 30} Physical Damage ke musuh di dekatnya. Setiap Summon semakin meningkatkan damage ini."),
    "你的召唤单位阵亡时，会对周围敌人造成{ResCardInfoDataBin_1771_17711_1: 60}点物理伤害。每次召唤还会额外提升该伤害。": (
        "When your Summoned Unit is Defeated, it deals {ResCardInfoDataBin_1771_17711_1: 60} Physical Damage to nearby enemies. Each subsequent Summon further increases this Damage.",
        "Saat Summoned Unit-mu dikalahkan, ia memberikan {ResCardInfoDataBin_1771_17711_1: 60} Physical Damage ke musuh di dekatnya. Setiap Summon berikutnya semakin meningkatkan damage ini."),
    "<color=#FFE897>你的召唤单位</color>等级+6。每回合开始时，再+6。": (
        "<color=#FFE897>Your summoned units</color> gain +6 levels. At the start of each Round, gain another +6.",
        "<color=#FFE897>Unit yang kau panggil</color> mendapatkan +6 level. Pada awal setiap Ronde, mendapatkan +6 lagi."),
    "你的单位每合计进行25次普攻，所有己方英雄等级永久+2。": (
        "Every 25 total basic attacks performed by your units, all allied Hero levels permanently +2.",
        "Setiap total 25 serangan dasar yang dilakukan unit kamu, level semua Hero ally +2 secara permanen."),
    "<a href=3><color=#ffffff>╪<b>开团</b></color></a>：距离最近的{HPtuteng31080:2}名己方英雄获得装备<color=#ffffff><b>玄微之种</b></color>。": (
        "<a href=3><color=#ffffff>╪<b>Initiate</b></color></a>: The {HPtuteng31080:2} nearest allied Heroes gain the"
        " <color=#ffffff><b>Seed of Xuanwei</b></color> Equipment.",
        "<a href=3><color=#ffffff>╪<b>Initiate</b></color></a>: {HPtuteng31080:2} Hero ally terdekat mendapat Equipment"
        " <color=#ffffff><b>Seed of Xuanwei</b></color>."),
    "蒙犽发射12枚导弹攻击随机敌人，每枚造成<color=#dfa15e>[524311p1q1]+[524311p1q2/100]%物理攻击力的物理伤害</color>。多枚导弹命中同一目标时，后续伤害衰减40%。": (
        "Meng Ya fires 12 missiles at random enemies, each dealing <color=#dfa15e>[524311p1q1]+[524311p1q2/100]%"
        " Physical Attack as Physical Damage</color>. When several missiles hit the same target, each further hit"
        " deals 40% less Damage.",
        "Meng Ya meluncurkan 12 rudal untuk menyerang musuh acak, masing-masing memberikan <color=#dfa15e>Physical"
        " Damage sebesar [524311p1q1]+[524311p1q2/100]% Physical Attack</color>. Saat beberapa rudal mengenai target"
        " yang sama, damage berikutnya berkurang 40%."),
    "战斗开始时，随机传送1个临时等级100级的英雄进入战场（不含卡牌效果），该等级每回合+40。": (
        "At the start of battle, randomly Teleport 1 Hero with a temporary Level of 100 into the Battlefield"
        " (excluding card effects). This Level increases by 40 each Round.",
        "Di awal pertempuran, teleportasi secara acak 1 Hero dengan Level sementara 100 ke Medan Pertempuran"
        " (tidak termasuk efek kartu). Level ini bertambah 40 setiap Ronde."),
    "战斗开始时，随机传送1个100级的英雄进入战场（不含卡牌效果），传送等级每回合+40。": (
        "At the start of battle, randomly teleports 1 Lv. 100 Hero into the Battlefield (excluding card effects)."
        " Teleport Level increases by 40 each Round.",
        "Di awal pertempuran, teleportasi secara acak 1 Hero Lv. 100 ke Medan Pertempuran (tidak termasuk efek"
        " kartu). Level teleportasi bertambah 40 setiap Ronde."),
    "战斗开始时，亚瑟周围一格的友方英雄<color=#FFE897>变身为圣殿骑士</color>。亚瑟的普攻变为为血量最低的圣殿骑士回复生命值；技能改为指挥全体圣殿骑士朝敌人<color=#FFE897>冲锋</color>。": (
        "At the start of Battle, allied Heroes within 1 grid of Arthur <color=#FFE897>transform into Templars</color>."
        " Arthur's basic attacks now restore HP to the Templar with the lowest HP; his Skill is changed to command"
        " all Templars to <color=#FFE897>Charge</color> at enemies.",
        "Di awal Pertempuran, Hero ally dalam jarak 1 petak dari Arthur <color=#FFE897>berubah menjadi"
        " Templar</color>. Basic attack Arthur kini memulihkan HP ke Templar dengan HP terendah; Skill-nya berubah"
        " menjadi memerintahkan semua Templar untuk <color=#FFE897>Charge</color> ke musuh."),
    "随机<color=#FFE897>获得1件星源装备</color>，且星源装备的【日落海】专属效果对穿戴它的任意英雄生效。": (
        "Randomly <color=#FFE897>gain 1 Star Source Equipment</color>, and the [Sunset] Exclusive effect of the"
        " Star Source Equipment applies to any Hero wearing it.",
        "Secara acak <color=#FFE897>dapatkan 1 Equipment Star Source</color>, dan efek eksklusif [Sunset] dari"
        " Equipment Star Source berlaku untuk Hero mana pun yang memakainya."),
    "回合开始时，场上友方英雄获得已觉醒英雄数量×2的等级。": (
        "At the start of the Round, allied heroes on the field gain levels equal to the number of Awaken Heroes ×2.",
        "Di awal Ronde, hero ally di lapangan mendapat level sebesar jumlah Hero Awaken ×2."),
    "基于场上英雄、阵营（至少3名）获取一套梦幻手牌。": (
        "Obtain a set of dream cards based on the heroes and factions (at least 3) on the board.",
        "Dapatkan satu set kartu impian berdasarkan Hero dan faksi (minimal 3) di papan."),
    "战斗开始时，<color=#FFE897>干将莫邪</color>获得1件【法源之杯】。": (
        "At the start of combat, <color=#FFE897>Gan & Mo</color> gains 1 [Mana Chalice].",
        "Di awal pertarungan, <color=#FFE897>Gan & Mo</color> mendapatkan 1 [Mana Chalice]."),
    "战斗开始时，将敌方等级最高的英雄复制，临时加入我方战场。": (
        "At the start of combat, Copy the Enemy's highest-Level Hero and add them to your battlefield temporarily.",
        "Di awal pertarungan, salin Hero Musuh dengan Level tertinggi dan tambahkan sementara ke medan pertempuranmu."),
    "指定1名英雄，场上和其品阶相同的英雄等级+4。": (
        "Target 1 Hero. Increase the Level of all Heroes on the board with the same Tier by 4.",
        "Pilih 1 Hero. Tingkatkan Level semua Hero di papan dengan Tier yang sama sebesar 4."),
    "指定移除一名英雄，获得能量。此英雄0/1/2/3觉醒进度时，获得3/6/9/12能量。": (
        "Designate a Hero to Remove and Gain Energy. Gain 3/6/9/12 Energy based on the Hero's 0/1/2/3 Awaken Progress.",
        "Tunjuk satu Hero untuk dihapus dan dapatkan Energy. Dapatkan 3/6/9/12 Energy berdasarkan Awaken Progress"
        " Hero 0/1/2/3."),
    "获得1张亚瑟，战斗开始时，亚瑟周围一格的友方英雄<color=#FFE897>变身为圣殿骑士</color>。亚瑟的普攻变为为血量最低的圣殿骑士回复生命值；技能改为指挥全体圣殿骑士朝敌人<color=#FFE897>冲锋</color>。": (
        "Gain 1 Arthur. At the start of Battle, allied Heroes within 1 grid of Arthur <color=#FFE897>transform into"
        " Templars</color>. Arthur's basic attacks now restore HP to the Templar with the lowest HP; his Skill is"
        " changed to command all Templars to <color=#FFE897>Charge</color> at enemies.",
        "Dapatkan 1 Arthur. Di awal Pertempuran, Hero ally dalam jarak 1 petak dari Arthur <color=#FFE897>berubah"
        " menjadi Templar</color>. Basic attack Arthur kini memulihkan HP ke Templar dengan HP terendah; Skill-nya"
        " berubah menjadi memerintahkan semua Templar untuk <color=#FFE897>Charge</color> ke musuh."),
    "第6/11回合，获得1张秘技牌<b>命运馈赠</b>。": (
        "On Round 6/11, Obtain 1 Secret Skill card <b>Fate Gift</b>.",
        "Di Ronde 6/11, dapatkan 1 kartu Secret Skill <b>Fate Gift</b>."),
    "随机抽取5张技能所选阵营的英雄牌。": (
        "Randomly draw 5 Hero cards of the selected Faction.",
        "Tarik 5 Hero Card dari Faction yang dipilih secara acak."),
    "开局<color=#98cbff>随机5名</color>棋手，选择其一。": (
        "At the start of the match, <color=#98cbff>5 Random</color> Chessplayers will be provided for you to choose one.",
        "Di awal pertandingan, <color=#98cbff>5 Chessplayer Acak</color> akan disediakan untuk kamu pilih salah satu."),
    "英雄的法力值上限最低可降低至10点。": (
        "A Hero's max Mana can be reduced to a minimum of 10.",
        "Max Mana Hero bisa dikurangi hingga minimal 10."),
    "导弹伤害提升至30+150%物理攻击力": (
        "Missile Damage Up to 30+150% Physical Attack",
        "Damage Misil Naik menjadi 30+150% Physical Attack"),
    "导弹数量提升至20枚；每施法1次，下次技能导弹数量增加1枚（至多30枚）": (
        "Missile count increased to 20; every 1 Skill cast increases missile count for the next Skill by 1 (up to 30)",
        "Jumlah misil meningkat menjadi 20; setiap 1 Skill cast menambah 1 misil untuk Skill berikutnya (maksimal 30)"),
    "干将·强化": ("Gan: Enhanced", "Gan: Diperkuat"),
    "<b>十分钟</b>1场，等级飞涨": ("<b>Ten minutes</b> a match, levels soaring", "<b>Sepuluh menit</b> per pertandingan, level melonjak"),
    "一冻到底，直升<b>百级</b>": ("Freeze all the way, straight to <b>Level 100</b>", "Bekukan terus, langsung ke <b>Level 100</b>"),
    "超级英雄，越买<b>越高</b>": ("Super Heroes: the more you buy, the <b>higher</b>", "Super Hero: makin banyak dibeli, makin <b>tinggi</b>"),
    "镀闪·蔡文姬": ("Gilded Flash · Cai Yan", "Gilded Flash · Cai Yan"),

    # Achievements: conditions and descriptions.
    "在万象大赛中，排位赛夺冠率": ("Championship Rate in ACE Tournament-Ranked", "Championship Rate di ACE Tournament-Ranked"),
    "在钻石狂潮中，排位赛夺冠率": ("Championship Rate in Diamond Frenzy-Ranked", "Championship Rate di Diamond Frenzy-Ranked"),
    "在万象大赛的一局游戏中，使用英雄【蔡文姬】累计造成20000点伤害": (
        "Deal a total of 20,000 damage using [Cai Yan] in a single ACE Tournament match.",
        "Berikan total 20.000 damage menggunakan [Cai Yan] dalam satu pertandingan ACE Tournament."),
    "在万象大赛的一局游戏中，在超过10回合都是第六名的情况下最终夺冠": (
        "In a single ACE Tournament match, win the Championship after being in 6th place for more than 10 rounds.",
        "Dalam satu pertandingan ACE Tournament, raih Juara setelah berada di peringkat 6 lebih dari 10 ronde."),
    "在万象大赛的最后一回合中，上阵7名及以上已觉醒的英雄，全员存活并夺冠": (
        "In the final Round of the ACE Tournament, deploy 7 or more Awakened Heroes, keep them all alive and win the"
        " Championship.",
        "Di Ronde terakhir ACE Tournament, deploy 7 atau lebih Hero yang sudah Awaken, jaga semuanya tetap hidup dan"
        " menangkan Kejuaraan."),
    "在万象大赛的最后一回合中，我方上场的英雄均与【整备】相关并最终夺冠": (
        "In the final Round of the ACE Tournament, have every deployed hero relate to [Prepare] and win the Championship.",
        "Di Ronde terakhir ACE Tournament, buat semua hero yang di-deploy terkait [Prepare] dan menangkan Kejuaraan."),
    "在钻石狂潮中，初始阵容三选一时，选择【逆天改命-米莱狄】初始卡包": (
        "In Diamond Frenzy, when choosing one of three Initial lineups, Select the [Defy Fate - Milady] Initial Card Pack.",
        "Di Diamond Frenzy, saat memilih satu dari tiga lineup awal, pilih Paket Kartu Awal [Defy Fate - Milady]."),
    "在【小王庆生礼】活动中，获得【王王王】纪念称号": (
        "Obtain the [King King King] commemorative title in the [Little King's Birthday] event",
        "Dapatkan gelar kenangan [King King King] di event [Ulang Tahun Little King]"),
    "在【小王庆生礼】活动中，规定时间内完成三端登录": (
        "Log in on all three platforms within the time limit during the [Little King's Birthday] event",
        "Login di ketiga platform dalam batas waktu selama event [Ulang Tahun Little King]"),
    "完成好奇鬼和彩蛋猎人成就": (
        "Complete the Curious Ghost and Easter Egg Hunter achievements",
        "Selesaikan achievement Curious Ghost dan Easter Egg Hunter"),
    "完成生涯历程相关的所有成就": ("Complete all achievements related to Career.", "Selesaikan semua achievement terkait Karier."),
    "完成钻石狂潮相关的所有成就": (
        "Complete all achievements related to Diamond Frenzy.", "Selesaikan semua achievement terkait Diamond Frenzy."),
    "完成1局抉择之弈": ("Complete 1 Choice Chess match", "Selesaikan 1 pertandingan Choice Chess"),
    "完成3局抉择之弈": ("Complete 3 Choice Chess matches", "Selesaikan 3 pertandingan Choice Chess"),
    "抉择之弈进入前3名": ("Finish in the top 3 in Choice Chess", "Masuk 3 besar di Choice Chess"),
    "对局中遇到王中王玩家（含自己）": (
        "Meet a King of Kings player in a match (including yourself)",
        "Bertemu pemain King of Kings dalam pertandingan (termasuk diri sendiri)"),
    "每日获得1次万象大赛前三": ("Finish top 3 in the ACE Tournament once a day", "Masuk 3 besar ACE Tournament sekali sehari"),
    "每日进行1次组队对局": ("Play 1 team match a day", "Main 1 pertandingan tim per hari"),
    "拥有【蔡文姬】5级卡牌": ("Own a Level 5 [Cai Yan] Card", "Miliki Kartu [Cai Yan] Level 5"),
    "全服前9999名最强王者获得此称号": (
        "The top 9999 Strongest Kings on the server earn this title",
        "9999 Strongest King teratas di server mendapatkan gelar ini"),
    "赛季结束后的前9999名玩家获得此称号": (
        "The top 9999 players at the end of the season earn this title",
        "9999 pemain teratas di akhir season mendapatkan gelar ini"),
    "累计获得任意20个不同棋手的代言人称号，且为全服前9999名达成者": (
        "Obtain 20 different Chessplayer spokesperson titles in total, among the first 9999 players on the server to do so",
        "Dapatkan total 20 gelar juru bicara Chessplayer yang berbeda, termasuk 9999 pemain pertama di server yang"
        " mencapainya"),
    "达到王者段位，下赛季可激活成就并获得唯一称号": (
        "Reach Honor rank to activate the achievement next season and earn a unique title",
        "Capai rank Honor untuk mengaktifkan achievement di season berikutnya dan dapatkan gelar unik"),
    "入选并成为当期“荣耀王牌计划”创作者": (
        "Be selected as a creator in this period's \"Honor Ace Program\"",
        "Terpilih sebagai kreator \"Honor Ace Program\" periode ini"),
    "参与电竞赛事活动获取": ("Obtained by joining esports events", "Didapat dengan mengikuti event esports"),
    "参与电竞赛事活动获取。": ("Obtained by joining esports events.", "Didapat dengan mengikuti event esports."),
    "王王王": ("King King King", "King King King"),
    "电竞选手": ("Esports Player", "Pemain Esports"),
    "我是主播": ("I'm a Streamer", "Aku Streamer"),
    "都是王者呀": ("All Honor Here", "Semuanya Honor"),

    # King of Kings: the sub-account an Honor-rank player unlocks.
    "王者{0}分": ("Honor {0} pts", "Honor {0} poin"),
    "达到王者1000分": ("Reach Honor 1000 pts", "Capai Honor 1000 poin"),
    "达到王者2000分": ("Reach Honor 2000 pts", "Capai Honor 2000 poin"),
    "达到王者3000分": ("Reach Honor 3000 pts", "Capai Honor 3000 poin"),
    "已扩大搜寻范围：最强王者{0}分及以上": (
        "Search range widened: Strongest King {0} pts and above", "Jangkauan pencarian diperluas: Strongest King {0} poin ke atas"),
    "段位达到王者时会解锁一个王中王子账号，可以重复挑战上王者段位": (
        "Reaching Honor rank unlocks a King of Kings sub-account, which lets you climb to Honor rank again",
        "Mencapai rank Honor membuka sub-akun King of Kings, yang memungkinkan kamu naik ke rank Honor lagi"),
    "本赛季达到王者段位后 即可开启挑战多冠王者": (
        "Reach Honor rank this Season to unlock the Multi-Champion King challenge",
        "Capai rank Honor di Season ini untuk membuka tantangan Multi-Champion King"),
    "挑战多冠王者最多还可获得54000钻石": (
        "The Multi-Champion King challenge can still earn up to 54000 Diamonds",
        "Tantangan Multi-Champion King masih bisa memberi hingga 54000 Diamond"),
    "子账号达到王者段位\n均可领取奖励": (
        "Any sub-account that reaches Honor rank\ncan claim the rewards",
        "Setiap sub-akun yang mencapai rank Honor\nbisa mengklaim hadiah"),
    "当前子账号未达到王者段位": ("This sub-account has not reached Honor rank", "Sub-akun ini belum mencapai rank Honor"),
    "切换王中王": ("Switch to King of Kings", "Ganti ke King of Kings"),
    "王中王奖励": ("King of Kings Rewards", "Hadiah King of Kings"),
    "王中王奖励可领取": ("King of Kings rewards available", "Hadiah King of Kings bisa diklaim"),
    "王中王活动奖励": ("King of Kings Event Rewards", "Hadiah Event King of Kings"),
    "王中王解锁": ("King of Kings Unlocked", "King of Kings Terbuka"),
    "解锁王中王，切换至全新段位即可参加活动": (
        "Unlock King of Kings and switch to the new rank to join the event",
        "Buka King of Kings dan ganti ke rank baru untuk ikut event"),
    "这里也可以进入王中王系统": ("You can also enter King of Kings from here", "Kamu juga bisa masuk King of Kings dari sini"),
    "账号不匹配，请切换至该对局所对应的王中王账号后使用。": (
        "Account mismatch. Switch to the King of Kings account this match belongs to and try again.",
        "Akun tidak cocok. Ganti ke akun King of Kings milik pertandingan ini lalu coba lagi."),
    "该系统需达到王者段位解锁，暂时无法前往~": (
        "This feature unlocks at Honor rank; it is not available yet~",
        "Fitur ini terbuka di rank Honor; belum bisa diakses~"),
    "达到王者可获奖励": ("Reach Honor to earn rewards", "Capai Honor untuk mendapat hadiah"),
    "达到王者可获得奖励": ("Reach Honor to earn rewards", "Capai Honor untuk mendapat hadiah"),
    "达成指定王者分数领钻石": ("Reach the set Honor points to claim Diamonds", "Capai poin Honor yang ditentukan untuk klaim Diamond"),
    "王者段位冲分有礼": ("Honor Rank Climb Gifts", "Hadiah Naik Rank Honor"),
    "王者段位冲分领钻石": ("Climb Honor Rank for Diamonds", "Naik Rank Honor untuk Diamond"),
    "冲分钻石礼": ("Rank Climb Diamond Gift", "Hadiah Diamond Naik Rank"),

    # Diamond Frenzy zones of the weekly leaderboard.
    "上周钻石狂潮小赢区排名前五十": (
        "Top 50 in the Diamond Frenzy Small Win zone last week", "50 besar zona Small Win Diamond Frenzy minggu lalu"),
    "上周钻石狂潮稳赢区排名前五十": (
        "Top 50 in the Diamond Frenzy Sure Win zone last week", "50 besar zona Sure Win Diamond Frenzy minggu lalu"),
    "上周钻石狂潮大赢区排名前五十": (
        "Top 50 in the Diamond Frenzy Big Win zone last week", "50 besar zona Big Win Diamond Frenzy minggu lalu"),
    "上周钻石狂潮爽赢区排名前五十": (
        "Top 50 in the Diamond Frenzy Sweet Win zone last week", "50 besar zona Sweet Win Diamond Frenzy minggu lalu"),
    "上周钻石狂潮赢麻区排名前五十": (
        "Top 50 in the Diamond Frenzy Win Overload zone last week", "50 besar zona Win Overload Diamond Frenzy minggu lalu"),

    # Ace Duel guessing and dividends.
    "助力王牌对决": ("Support Ace Duel", "Dukung Ace Duel"),
    "助力王牌对决奖励": ("Ace Duel Support Rewards", "Hadiah Dukungan Ace Duel"),
    "王牌对决-万象大赛分红发放": ("Ace Duel - ACE Tournament dividend distributed", "Ace Duel - Dividen ACE Tournament dibagikan"),
    "王牌对决-钻石狂潮分红发放": ("Ace Duel - Diamond Frenzy dividend distributed", "Ace Duel - Dividen Diamond Frenzy dibagikan"),
    "王牌对决对局分红": ("Ace Duel match dividend", "Dividen pertandingan Ace Duel"),
    "竞猜心仪棋手 瓜分竞猜奖池": (
        "Guess your favorite Chessplayer and share the prize pool", "Tebak Chessplayer favoritmu dan bagi prize pool"),
    "{0}天后本期竞猜截止": ("Guessing closes in {0} days", "Tebakan ditutup dalam {0} hari"),
    "{0}小时{1}分后本期竞猜截止": ("Guessing closes in {0} hr {1} min", "Tebakan ditutup dalam {0} jam {1} menit"),
    "{0}分{1}秒后本期竞猜截止": ("Guessing closes in {0} min {1} sec", "Tebakan ditutup dalam {0} menit {1} detik"),
    "每期结束后可以在这里查看竞猜结果，祝你好运~": (
        "Check the guessing results here after each round ends. Good luck~",
        "Cek hasil tebakan di sini setelah tiap periode berakhir. Semoga beruntung~"),
    "系统送你一张钻石抵扣券，可以免费竞猜一次": (
        "The system gives you a Diamond Discount Coupon for one free guess",
        "Sistem memberimu satu Kupon Diskon Diamond untuk satu tebakan gratis"),
    "支持已超过上限，最多每名玩家支持{0}钻石": (
        "Support limit exceeded: up to {0} Diamonds per player", "Batas dukungan terlampaui: maksimal {0} Diamond per pemain"),
    "对该选手的支持金额已达上限": ("You have reached the support limit for this player", "Batas dukungan untuk pemain ini sudah tercapai"),
    "参赛选手不能参与支持": ("Contestants cannot give support", "Peserta tidak bisa memberi dukungan"),
    "输入的数量超过最大拥有数量，按拥有最大数量投注": (
        "The amount exceeds what you own; your full amount will be bet", "Jumlah melebihi yang kamu miliki; seluruh milikmu akan dipasang"),
    "距本场开赛时间太近，无法加入了": ("Too close to the start of this match to join", "Terlalu dekat dengan mulainya pertandingan ini untuk bergabung"),
    "比赛已开始": ("The match has started", "Pertandingan sudah dimulai"),
    "等待结果揭晓": ("Waiting for the results", "Menunggu hasil diumumkan"),
    "恭喜您本期获得钻石": ("Congratulations, you won Diamonds this round", "Selamat, kamu mendapat Diamond periode ini"),
    "竞猜人次": ("Guesses", "Jumlah Tebakan"),
    "获奖人次": ("Winners", "Jumlah Pemenang"),
    "获得奖励人次": ("Rewarded", "Jumlah Penerima Hadiah"),
    "金牌奖励名单": ("Gold Reward List", "Daftar Hadiah Gold"),
    "金牌玩家{0}位：": ("{0} Gold players:", "{0} pemain Gold:"),
    "金牌获奖人数": ("Gold Winners", "Jumlah Pemenang Gold"),
    "选择{0}/{1}个棋手": ("Select {0}/{1} Chessplayers", "Pilih {0}/{1} Chessplayer"),
    "已为您自动使用合适的抵扣券": ("A suitable Discount Coupon was applied for you", "Kupon Diskon yang sesuai sudah dipakai otomatis"),
    "抵扣券抵扣": ("Coupon discount", "Potongan kupon"),
    "完成任务领取钻石抵扣券": ("Complete missions to claim Diamond Discount Coupons", "Selesaikan misi untuk klaim Kupon Diskon Diamond"),
    "登录即可领取钻石抵扣券": ("Log in to claim a Diamond Discount Coupon", "Login untuk klaim Kupon Diskon Diamond"),
    "价格超过限制或参数设置非法，请稍后再试": (
        "Price over the limit or invalid setting. Please try again later.",
        "Harga melebihi batas atau pengaturan tidak valid. Coba lagi nanti."),
    "已自动调整至允许的最高价格": ("Adjusted to the highest allowed price", "Disesuaikan ke harga tertinggi yang diizinkan"),
    "已达最大数量，设置为最大数量": ("Maximum reached; set to the maximum", "Jumlah maksimum tercapai; diatur ke maksimum"),

    # Events: Super Weekend, Super Holiday, Rose Bonus, Choice Chess.
    "超级周末": ("Super Weekend", "Super Weekend"),
    "超级周末 钻石加码": ("Super Weekend Diamond Bonus", "Bonus Diamond Super Weekend"),
    "超级周末活动奖励": ("Super Weekend Event Rewards", "Hadiah Event Super Weekend"),
    "超级假期": ("Super Holiday", "Super Holiday"),
    "超级假期活动奖励": ("Super Holiday Event Rewards", "Hadiah Event Super Holiday"),
    "超级假期钻石加码": ("Super Holiday Diamond Bonus", "Bonus Diamond Super Holiday"),
    "蔷薇加码": ("Rose Bonus", "Bonus Rose"),
    "蔷薇加码最后一波": ("Rose Bonus: Final Wave", "Bonus Rose: Gelombang Terakhir"),
    "蔷薇加码活动奖励": ("Rose Bonus Event Rewards", "Hadiah Event Bonus Rose"),
    "抉择之弈活动奖励": ("Choice Chess Event Rewards", "Hadiah Event Choice Chess"),
    "期间更有对局翻牌钻石加倍": ("Match card-flip Diamonds are doubled during the event", "Selama event, Diamond dari balik kartu pertandingan digandakan"),
    "限时福利：每天前{1}次翻出钻石翻倍（{0} / {1}）": (
        "Limited-time perk: Diamonds doubled on your first {1} flips each day ({0} / {1})",
        "Bonus terbatas: Diamond digandakan pada {1} balikan pertama tiap hari ({0} / {1})"),
    "夺冠福袋": ("Championship Lucky Bag", "Lucky Bag Juara"),
    "恭喜获胜！前往玩法大厅领取奖励吧！": (
        "Congratulations on the win! Go to the Mode Lobby to claim your rewards!",
        "Selamat atas kemenangannya! Pergi ke Lobi Mode untuk klaim hadiah!"),
    "9月13日": ("Sep 13", "13 Sep"),
    "9月14日": ("Sep 14", "14 Sep"),
    "{0}月{1}日{2}点 上架": ("On sale {0}/{1} at {2}:00", "Dijual bulan {0} tanggal {1} pukul {2}.00"),

    # Line Puppy event: wishes, Sky Screen, exchange shop.
    "线条小狗的旅行": ("Line Puppy's Journey", "Perjalanan Line Puppy"),
    "线条小狗祈愿币": ("Line Puppy Prayer Coin", "Koin Doa Line Puppy"),
    "线条小狗祈愿获取": ("Obtained via Line Puppy Prayer", "Didapat dari Doa Line Puppy"),
    "线条小狗积分": ("Line Puppy Points", "Poin Line Puppy"),
    "线条小狗累抽奖励": ("Line Puppy Cumulative Draw Rewards", "Hadiah Draw Kumulatif Line Puppy"),
    "线条小狗累抽礼包": ("Line Puppy Cumulative Draw Pack", "Paket Draw Kumulatif Line Puppy"),
    "线条小狗商城": ("Line Puppy Store", "Toko Line Puppy"),
    "线条小狗商店有奖励可兑换": ("Rewards are available to exchange in the Line Puppy Shop.", "Hadiah bisa ditukar di Toko Line Puppy."),
    "线条小狗天幕祈愿上线": ("Line Puppy Sky Screen Prayer Available", "Doa Sky Screen Line Puppy Tersedia"),
    "线条小狗天幕祈愿在成长之路达到2级后开启": (
        "Line Puppy Sky Screen Prayer opens at Growth Path Level 2", "Doa Sky Screen Line Puppy terbuka di Growth Path Level 2"),
    "线条小狗天幕祈愿尚未开启": ("Line Puppy Sky Screen Prayer is not open yet", "Doa Sky Screen Line Puppy belum dibuka"),
    "线条小狗传送特效": ("Line Puppy Teleport Effect", "Efek Teleportasi Line Puppy"),
    "线条小狗全都有": ("Line Puppy Has It All", "Line Puppy Punya Semuanya"),
    "线条小狗出动": ("Line Puppy, Go!", "Line Puppy, Berangkat!"),
    "线条小狗拍立得": ("Line Puppy Polaroid", "Polaroid Line Puppy"),
    "线条小狗带你一起赴约~": ("Line Puppy takes you along to the meetup~", "Line Puppy mengajakmu ke janji temu~"),
    "跟着线条小狗快乐出发吧！": ("Set off happily with Line Puppy!", "Ayo berangkat gembira bersama Line Puppy!"),
    "收下线条小狗的爱心吧！（个性戳戳，可在组队界面对其他玩家使用）": (
        "Take Line Puppy's love! (Personalized Poke, usable on other players in the team screen)",
        "Terima cinta dari Line Puppy! (Personalized Poke, bisa dipakai ke pemain lain di layar tim)"),
    "活动货币，用于在线条小狗奖池兑换商店兑换奖励。": (
        "Event Currency used to redeem rewards in the Line Puppy prize pool exchange shop.",
        "Mata uang Event untuk menukar hadiah di toko penukaran prize pool Line Puppy."),
    "天幕·线条小狗的旅行7天限时卡": (
        "Sky Screen: Line Puppy's Journey 7-Day Trial Card", "Kartu Trial 7 Hari Sky Screen: Perjalanan Line Puppy"),
    "获得【天幕·线条小狗的旅行】7天限时体验。": (
        "Get a 7-day trial of [Sky Screen: Line Puppy's Journey].", "Dapatkan trial 7 hari [Sky Screen: Perjalanan Line Puppy]."),
    "{0}，可以兑换天幕啦~": ("{0}, you can exchange for the Sky Screen now~", "{0}, kamu sudah bisa menukar Sky Screen~"),
    "{0}，差{1}兑线条小狗天幕": ("{0}, {1} more for the Line Puppy Sky Screen", "{0}, kurang {1} untuk Sky Screen Line Puppy"),
    "{0}，来兑换商店看看~": ("{0}, take a look at the Exchange Shop~", "{0}, yuk lihat Toko Penukaran~"),
    "积分足够时可兑换天幕大奖": (
        "Exchange for the Sky Screen grand prize once you have enough points",
        "Tukar hadiah utama Sky Screen saat poinmu cukup"),
    "每次祈愿有概率获得积分和限定天幕": (
        "Each Prayer has a chance to give points and a limited Sky Screen",
        "Setiap Doa berpeluang memberi poin dan Sky Screen terbatas"),
    "累计祈愿{0}次获得{1}天幕": ("Accumulate {0} Prayers to obtain the {1} Sky Screen", "Kumpulkan {0} Doa untuk mendapatkan Sky Screen {1}"),
    "累抽奖励已领取完毕": ("All cumulative draw rewards claimed", "Semua hadiah draw kumulatif sudah diklaim"),
    "每抽取<color=#F8EE9A>10次</color>可获得自选礼包，最多领取<color=#F8EE9A>6次</color>": (
        "Every <color=#F8EE9A>10 draws</color> grants a Customizable pack, up to <color=#F8EE9A>6 times</color>",
        "Setiap <color=#F8EE9A>10 draw</color> memberi Paket yang bisa dikustomisasi, maksimal"
        " <color=#F8EE9A>6 kali</color>"),
    "恭喜获得<color=#ed6962ff>{0}x{1}</color>，首抽仅需<color=#ed6962ff>{2}{3}</color>": (
        "Congratulations on <color=#ed6962ff>{0}x{1}</color>! Your first draw costs only <color=#ed6962ff>{2}{3}</color>",
        "Selamat mendapat <color=#ed6962ff>{0}x{1}</color>! Draw pertama hanya <color=#ed6962ff>{2}{3}</color>"),
    "抽奖需要{0}个{1}，去搞点摇摇币~": ("A draw needs {0} {1}. Go get some Shake Coins~", "Draw butuh {0} {1}. Ayo cari Shake Coin~"),
    "当前祈愿活动已结束，将为您进入其他祈愿活动": (
        "This Prayer event has ended; taking you to another Prayer event",
        "Event Doa ini sudah berakhir; kamu akan dibawa ke event Doa lain"),
    "UI界面异常，请退回大厅重新进入祈愿界面": (
        "Screen error. Return to the lobby and reopen the Prayer screen.", "Layar error. Kembali ke lobi dan buka ulang layar Doa."),
    "），是否继续祈愿获得积分": ("). Continue Prayer to earn points?", "). Lanjutkan Doa untuk mendapatkan poin?"),
    "天幕未解锁": ("Sky Screen not unlocked", "Sky Screen belum terbuka"),
    "天幕还不可用": ("Sky Screen not available yet", "Sky Screen belum tersedia"),
    "日月行者商城": ("Sun & Moon Traveler Store", "Toko Sun & Moon Traveler"),
    "日月行者在成长之路达到2级后开启": (
        "Sun & Moon Traveler opens at Growth Path Level 2", "Sun & Moon Traveler terbuka di Growth Path Level 2"),
    "日月行者尚未开启": ("Sun & Moon Traveler is not open yet", "Sun & Moon Traveler belum dibuka"),
    "夺宝在成长之路达到2级后开启": ("Treasure Hunt opens at Growth Path Level 2", "Treasure Hunt terbuka di Growth Path Level 2"),
    "三分钟训练即可领取闹闹": ("Train for three minutes to get Naonao", "Latihan tiga menit untuk mendapatkan Naonao"),

    # Shop and exchange.
    ", 是否兑换{0}": (", exchange for {0}?", ", tukar dengan {0}?"),
    "使用{0}兑换": ("Exchange with {0}", "Tukar dengan {0}"),
    "兑换时间：{0}": ("Exchange time: {0}", "Waktu penukaran: {0}"),
    "兑换后将发直接放给您，不可转赠": (
        "After redemption, it is sent straight to you. Cannot be gifted.", "Setelah ditukar, langsung dikirim kepadamu. Tidak dapat dihadiahkan."),
    "可兑换次数不足": ("Not enough exchanges left", "Sisa penukaran tidak cukup"),
    "该奖励最多领取1次~": ("This reward can be claimed only once~", "Hadiah ini hanya bisa diklaim sekali~"),
    "{0}不足且购买数量已达上限": ("Insufficient {0} and purchase limit reached", "{0} tidak cukup dan batas pembelian tercapai"),
    "{0}购买数量已达上限": ("Purchase limit for {0} reached.", "Batas pembelian untuk {0} tercapai."),
    "{0}不足（": ("Insufficient {0} (", "{0} tidak cukup ("),
    "{0}(分解为{1}{2})": ("{0} (breaks down into {1}{2})", "{0} (diurai menjadi {1}{2})"),
    "{0}·{1}预览": ("{0} · {1} Preview", "Pratinjau {0} · {1}"),
    "已选奖励{0}/{1}个": ("Rewards selected {0}/{1}", "Hadiah dipilih {0}/{1}"),
    "礼包或限时道具可使用": ("Packs or limited-time items can be used", "Paket atau item terbatas bisa dipakai"),
    "亲密度道具": ("Intimacy Items", "Item Intimacy"),
    "获得好感度": ("Favorability gained", "Favorability didapat"),

    # Number refresh (personal ID).
    "新编号 {0}": ("New ID {0}", "ID baru {0}"),
    "旧编号 {0}，是否使用当前新编号": ("Old ID {0}. Use the new ID?", "ID lama {0}. Pakai ID baru ini?"),
    "编号已刷新": ("ID refreshed", "ID sudah di-refresh"),
    "新编号已被占用，本次免费重试": ("The new ID is taken; retry for free", "ID baru sudah dipakai; coba lagi gratis"),
    "当前编号已被其他玩家抢先使用，您的下次刷新将免费": (
        "Another player took this ID first; your next refresh is free",
        "Pemain lain lebih dulu memakai ID ini; refresh berikutnya gratis"),
    "本次刷新免费": ("This refresh is free", "Refresh kali ini gratis"),

    # Match screens, social, emotes.
    "继续等待": ("Keep Waiting", "Tetap Menunggu"),
    "依然退出": ("Quit Anyway", "Tetap Keluar"),
    "投降后排名": ("Rank after surrender", "Peringkat setelah menyerah"),
    "对局时长": ("Match Duration", "Durasi Pertandingan"),
    "对局时间：": ("Match time:", "Waktu pertandingan:"),
    "对局结算点赞奖励": ("Match result Like reward", "Hadiah Like hasil pertandingan"),
    "点赞成功，获得5钻石（本日剩余{0}/{1}次）": (
        "Liked! Got 5 Diamonds ({0}/{1} left today)", "Berhasil Like! Dapat 5 Diamond (sisa {0}/{1} hari ini)"),
    "胜场次数": ("Wins", "Jumlah Menang"),
    "总战力：": ("Total Combat Power:", "Total Combat Power:"),
    "总盈利：": ("Total profit:", "Total keuntungan:"),
    "好友排行": ("Friend Ranking", "Peringkat Teman"),
    "点击切换模式": ("Tap to switch mode", "Ketuk untuk ganti mode"),
    "禁用：": ("Banned:", "Dilarang:"),
    "英雄知识": ("Hero Knowledge", "Pengetahuan Hero"),
    "对方正忙，暂时无法成为您的私教": ("Player is busy and cannot be your coach right now", "Pemain sedang sibuk dan belum bisa menjadi coach-mu"),
    "发送验证码失败": ("Failed to send the verification code", "Gagal mengirim kode verifikasi"),
    "蓝牙权限": ("Bluetooth Permission", "Izin Bluetooth"),
    "提供连接蓝牙设备服务，用于游戏内可使用蓝牙耳机进行语音聊天。": (
        "Connects Bluetooth devices so you can use a Bluetooth headset for in-game voice chat.",
        "Menghubungkan perangkat Bluetooth agar kamu bisa memakai headset Bluetooth untuk voice chat di dalam game."),
    "扔心心表情": ("Throw Hearts Emote", "Emote Lempar Hati"),
    "接住心心表情": ("Catch Hearts Emote", "Emote Tangkap Hati"),
    "接收心心": ("Receive Hearts", "Terima Hati"),
    "挥手表情": ("Wave Emote", "Emote Melambai"),
    "走了表情": ("I'm Leaving Emote", "Emote Aku Pergi"),

    # Chessplayer voice lines and flavor text.
    "全力以赴的表演，会收获最热烈的掌声。（专属）": (
        "A performance that goes all out will receive the warmest applause. (Exclusive)",
        "Penampilan yang dikerahkan sepenuh hati akan mendapat tepuk tangan paling hangat. (Eksklusif)"),
    "接下来该我把控节奏了。（专属）": ("It is my turn to control the rhythm. (Exclusive)", "Sekarang giliranku mengendalikan ritme. (Eksklusif)"),
    "我的套路它都知道，搞不好要输": ("It knows all my tricks, I might lose", "Dia tahu semua trikku, bisa-bisa aku kalah"),
    "这次我们不浪费每一点等级": ("This time we won't waste a single level", "Kali ini kita tidak menyia-nyiakan satu level pun"),
    "所托不再非人": ("No longer entrusted to the wrong hands", "Tak lagi dititipkan pada orang yang salah"),
    "做一朵凋谢的小浪花": ("Be a little wave that fades away", "Jadilah ombak kecil yang memudar"),
    "听！潮汐的胜利之歌！": ("Listen! The tide's song of victory!", "Dengar! Lagu kemenangan sang pasang!"),
    "涟漪的形状从来不被定义。": ("The shape of a ripple is never defined.", "Bentuk riak tidak pernah didefinisikan."),
    "追逐鱼群，与浪花同游。": ("Chase the shoals and swim with the waves.", "Kejar kawanan ikan dan berenang bersama ombak."),

    # Official lineups (Lineup > Official recommendation): the text inside the share codes of config bins
    # F79FB1A213A9DA90, 6A2B886E5DCF22DC and C0C56FEFDCA0EA5D, plus two of their row fields. The catalog
    # already translates three more (召唤自爆流, 核心输出, 核心坦克). Names stay short: they sit on a narrow
    # card and in the share code's 【name】 prefix.

    # ResSeasonAILineupDataBin: EquipDesc
    "主C李信，其它英雄都是挂件，战斗中靠李信一打多，装备优先给李信。": (
        "Li Xin is the Main Carry and the other Heroes just support him; in battle Li Xin takes on many at once, so"
        " give him Equipment first.",
        "Li Xin adalah Main Carry dan Hero lain hanya pendukung; dalam Pertempuran Li Xin melawan banyak musuh"
        " sekaligus, jadi prioritaskan Equipment untuk Li Xin."),
    "亚连会给装备最多的英雄加等级，装备穿给主C，保证他穿的装备最多。": (
        "Allain gives Levels to the Hero with the most Equipment, so put the Equipment on the Main Carry and make sure"
        " he wears the most.",
        "Allain menambah Level Hero dengan Equipment terbanyak, jadi pakaikan Equipment ke Main Carry dan pastikan"
        " dia memakai Equipment paling banyak."),
    "亚连会给装备最多的英雄加等级，装备穿给主C，保证他穿的装备最多。可以在商店购买效果卡-远洋宝藏来获得【日落海】专属装备。": (
        "Allain gives Levels to the Hero with the most Equipment, so put the Equipment on the Main Carry and make sure"
        " he wears the most. You can buy the Effect Card Ocean Treasure in the Shop to get 【Sunset】 Exclusive"
        " Equipment.",
        "Allain menambah Level Hero dengan Equipment terbanyak, jadi pakaikan Equipment ke Main Carry dan pastikan"
        " dia memakai Equipment paling banyak. Kamu bisa membeli Effect Card Ocean Treasure di Shop untuk mendapatkan"
        " Equipment eksklusif 【Sunset】."),
    "司空震必备金色圣剑，推荐再带一个炽热支配者解控，最后一件没有其他特殊装备的话就带痛苦面具。": (
        "Sikong Zhen must have Golden Blade. Sanguine Dominator is also recommended to remove crowd control, and for"
        " the last slot take Mask of Agony if no other special Equipment is available.",
        "Sikong Zhen wajib memakai Golden Blade. Disarankan juga membawa Sanguine Dominator untuk menghapus crowd"
        " control, dan untuk slot terakhir bawa Mask of Agony jika tidak ada Equipment khusus lain."),
    "所有装备都优先穿给C位，芈月的英雄效果只对穿戴装备最多的英雄生效。": (
        "Give all Equipment to the Carry first; Mi Yue's Hero Effect only works on the Hero wearing the most"
        " Equipment.",
        "Prioritaskan semua Equipment untuk Carry; Efek Hero Mi Yue hanya berlaku untuk Hero yang memakai Equipment"
        " terbanyak."),
    "玄策推荐带一个炽热支配者解控。": (
        "Xuance should carry a Sanguine Dominator to remove crowd control.",
        "Xuance disarankan membawa Sanguine Dominator untuk menghapus crowd control."),
    "装备优先给主C，云中君的卡牌效果可以提升穿戴装备英雄的等级。": (
        "Give Equipment to the Main Carry first; Cirrus's Card Effect raises the Level of Heroes wearing Equipment.",
        "Prioritaskan Equipment untuk Main Carry; Efek Kartu Cirrus meningkatkan Level Hero yang memakai Equipment."),
    "装备前期可以给虞姬，后期来了敖隐等级高之后再给敖隐。": (
        "Early on, Equipment can go to Consort Yu; later, once Ao'yin arrives and his Level is high, give it to"
        " Ao'yin.",
        "Di awal, Equipment bisa diberikan ke Consort Yu; nanti setelah Ao'yin datang dan Level-nya tinggi, berikan"
        " ke Ao'yin."),

    # ResSeasonAILineupDataBin: LordInfos.Desc
    "乔汐专属天赋召唤的英雄也算获得临时等级，非常适配司空震的卡牌效果。": (
        "Heroes summoned by Qiao Xi's Exclusive Talent also count as gaining Temporary Levels, which suits Sikong"
        " Zhen's Card Effect very well.",
        "Hero yang di-Summon oleh Exclusive Talent Qiao Xi juga dihitung mendapat Temporary Level, sangat cocok"
        " dengan Efek Kartu Sikong Zhen."),
    "使用技能每回合稳定提升等级，操作简单，发挥稳定。秘技牌需要等上阵4名英雄后再使用。": (
        "Use the Skill every Round to raise Levels steadily. Simple to play and consistent. Wait until you have 4"
        " Heroes on the board before using the Secret Skill Card.",
        "Gunakan Skill setiap Ronde untuk menaikkan Level dengan stabil. Mudah dimainkan dan konsisten. Tunggu sampai"
        " ada 4 Hero di papan sebelum menggunakan Kartu Secret Skill."),
    "大河流域的低阶英雄能够为香香提供可观的攻击力加成，帮助她在前期打出稳定且强力的输出，后期香香也有很强的作战能力。": (
        "Low-Tier Riverlands Heroes give Xiangxiang a sizable Attack bonus, helping her deal steady, strong damage"
        " early on; Xiangxiang also fights well in the late game.",
        "Hero Riverlands Tier rendah memberi Xiangxiang bonus Attack yang besar, membantunya memberikan damage yang"
        " stabil dan kuat di awal; di akhir game Xiangxiang juga kuat bertarung."),
    "姜导适配养单C的阵容，能增加英雄等级和提供吸血。技能给百里玄策使用。": (
        "Director Jiang suits Lineups built around a single Carry: he raises Hero Levels and grants Lifesteal. Use his"
        " Skill on Xuance.",
        "Director Jiang cocok untuk Lineup yang membangun satu Carry: menaikkan Level Hero dan memberi Lifesteal."
        " Gunakan Skill-nya pada Xuance."),
    "庄小鱼的秘技牌可以帮助阵容快速成型，很容易搜到李信。玩庄小鱼需要快速升到5级开技能拿李信。": (
        "Zhuang Xiaoyu's Secret Skill Card helps the Lineup come together fast and makes Li Xin easy to find. With"
        " Zhuang Xiaoyu, rush to Lv. 5 and use the Skill to get Li Xin.",
        "Kartu Secret Skill Zhuang Xiaoyu membantu Lineup cepat terbentuk dan membuat Li Xin mudah ditemukan. Dengan"
        " Zhuang Xiaoyu, cepat naik ke Lv. 5 lalu gunakan Skill untuk mendapat Li Xin."),
    "庄小鱼秘技卡能够帮助玩家更快找到大河流域的高阶英雄，提升大河图腾流的阵容强度与过渡效率。": (
        "Zhuang Xiaoyu's Secret Skill Card helps you find high-Tier Riverlands Heroes faster, making the Riverlands"
        " Totem Build stronger and smoother to transition.",
        "Kartu Secret Skill Zhuang Xiaoyu membantumu menemukan Hero Riverlands Tier tinggi lebih cepat, membuat Build"
        " Riverlands Totem lebih kuat dan transisinya lebih lancar."),
    "庄小鱼秘技卡能够帮助玩家更快找到河洛的高阶英雄，提升这套阵容的强度。": (
        "Zhuang Xiaoyu's Secret Skill Card helps you find high-Tier Central Plains Heroes faster, making this Lineup"
        " stronger.",
        "Kartu Secret Skill Zhuang Xiaoyu membantumu menemukan Hero Central Plains Tier tinggi lebih cepat, membuat"
        " Lineup ini lebih kuat."),
    "打出4张3阶及以下英雄能获得宝藏牌，这套阵容全部是1-3阶英雄，比较适合搭配马可。": (
        "Playing 4 Heroes of Tier 3 or lower grants a Treasure Card. This Lineup is all Tier 1-3 Heroes, so it pairs"
        " well with Marco.",
        "Memainkan 4 Hero Tier 3 atau lebih rendah memberi Treasure Card. Lineup ini semuanya Hero Tier 1-3, jadi"
        " cocok dipasangkan dengan Marco."),
    "打出4张3阶及以下英雄能获得宝藏牌，这套阵容前期低阶英雄多，比较适合搭配马可。": (
        "Playing 4 Heroes of Tier 3 or lower grants a Treasure Card. This Lineup has many low-Tier Heroes early on, so"
        " it pairs well with Marco.",
        "Memainkan 4 Hero Tier 3 atau lebih rendah memberi Treasure Card. Lineup ini punya banyak Hero Tier rendah"
        " di awal, jadi cocok dipasangkan dengan Marco."),
    "派对泡泡选日落海，每回合使用棋手技能稳定拿一张日落海英雄牌，能快速凑齐阵容。秘技牌推荐4级/5级再用，补齐高阶英雄。": (
        "Pick Sunset for Party Bubble and use the Chessplayer Skill every Round to reliably get a Sunset Hero Card,"
        " completing the Lineup quickly. Use the Secret Skill Card at Lv. 4/5 to fill in high-Tier Heroes.",
        "Pilih Sunset untuk Party Bubble dan gunakan Skill Chessplayer setiap Ronde untuk pasti mendapat satu Kartu"
        " Hero Sunset, sehingga Lineup cepat lengkap. Gunakan Kartu Secret Skill di Lv. 4/5 untuk melengkapi Hero"
        " Tier tinggi."),
    "派对泡泡选河洛，每回合使用棋手技能稳定拿一张河洛英雄牌，能快速凑齐阵容。秘技牌推荐4级/5级再用，补齐高阶英雄。": (
        "Pick Central Plains for Party Bubble and use the Chessplayer Skill every Round to reliably get a Central"
        " Plains Hero Card, completing the Lineup quickly. Use the Secret Skill Card at Lv. 4/5 to fill in high-Tier"
        " Heroes.",
        "Pilih Central Plains untuk Party Bubble dan gunakan Skill Chessplayer setiap Ronde untuk pasti mendapat satu"
        " Kartu Hero Central Plains, sehingga Lineup cepat lengkap. Gunakan Kartu Secret Skill di Lv. 4/5 untuk"
        " melengkapi Hero Tier tinggi."),
    "派对泡泡选逐鹿，每回合使用棋手技能稳定拿一张逐鹿英雄牌，能快速凑齐阵容。秘技牌推荐4级/5级再用，补齐高阶英雄。": (
        "Pick Zhulu Plateau for Party Bubble and use the Chessplayer Skill every Round to reliably get a Zhulu Plateau"
        " Hero Card, completing the Lineup quickly. Use the Secret Skill Card at Lv. 4/5 to fill in high-Tier Heroes.",
        "Pilih Zhulu Plateau untuk Party Bubble dan gunakan Skill Chessplayer setiap Ronde untuk pasti mendapat satu"
        " Kartu Hero Zhulu Plateau, sehingga Lineup cepat lengkap. Gunakan Kartu Secret Skill di Lv. 4/5 untuk"
        " melengkapi Hero Tier tinggi."),
    "瑶妹的小鹿能提供稳定前排，配合图腾流前期不俗的战力来取得胜利；后期小鹿的等级奉献还能进一步提升图腾全队的等级。": (
        "Yaria's deer gives a steady frontline that, with the Totem Build's strong early power, wins fights; later,"
        " the deer's Level devotion raises the whole Totem team's Levels further.",
        "Rusa Yaria memberi frontline yang stabil, bersama kekuatan awal Build Totem yang lumayan untuk meraih"
        " kemenangan; nanti, Level yang dipersembahkan rusa semakin menaikkan Level seluruh tim Totem."),
    "白歌在合成4次后可获得场上的英雄牌，能加速英雄觉醒。秘技牌能复制需要的卡牌，技能简单实用。": (
        "After 4 Combines, Bai Ge can get Hero Cards of Heroes on the board, speeding up Awakening. The Secret Skill"
        " Card copies the cards you need. A simple, practical Skill.",
        "Setelah 4 kali Combine, Bai Ge bisa mendapat Kartu Hero dari Hero di papan, mempercepat Awaken Hero. Kartu"
        " Secret Skill bisa menyalin kartu yang dibutuhkan. Skill yang simpel dan praktis."),
    "白歌的技能能够提供大量的同名卡，帮助玩家进行更多的英雄合成，并由此获得更多战术牌。": (
        "Bai Ge's Skill provides plenty of Same-Name Cards, letting you Combine more Heroes and so gain more Tactics"
        " Cards.",
        "Skill Bai Ge memberi banyak Kartu Bernama Sama, membantumu melakukan lebih banyak Combine Hero dan dengan"
        " itu mendapat lebih banyak Tactics Card."),
    "神奇小鹿·奉献可以让小鹿在阵亡时，把自身等级以临时等级的方式分配给存活英雄，很适合李信。": (
        "Magic Deer: Devotion makes the deer, when it falls, share its own Level among surviving Heroes as Temporary"
        " Levels. Great with Li Xin.",
        "Magic Deer: Devotion membuat rusa, saat gugur, membagikan Level-nya ke Hero yang masih hidup sebagai"
        " Temporary Level. Sangat cocok untuk Li Xin."),
    "这套阵容主要靠使用效果牌时，触发芈月的卡牌效果培养英雄，小妲己能提供更多的效果牌，非常适合有芈月的阵容。": (
        "This Lineup mainly grows Heroes by playing Effect Cards to trigger Mi Yue's Card Effect. Little Daji provides"
        " more Effect Cards, a great fit for Lineups with Mi Yue.",
        "Lineup ini terutama membesarkan Hero dengan menggunakan Effect Card untuk memicu Efek Kartu Mi Yue. Little Daji"
        " memberi lebih banyak Effect Card, sangat cocok untuk Lineup dengan Mi Yue."),
    "闹闹的技能只花1点能量拿牌，前期经常能随到需要的牌。秘技牌在4级用，有概率能出李信。": (
        "Naonao's Skill gets a card for just 1 Energy and often rolls the card you need early on. Use the Secret Skill"
        " Card at Lv. 4 for a chance at Li Xin.",
        "Skill Naonao mengambil kartu hanya dengan 1 Energy dan di awal sering mendapat kartu yang dibutuhkan."
        " Gunakan Kartu Secret Skill di Lv. 4 untuk peluang mendapat Li Xin."),
    "靠棋手技能稳定提升英雄等级，操作简单。秘技牌最好等上齐4个英雄再用，对每个英雄只能触发1次。": (
        "Raises Hero Levels steadily with the Chessplayer Skill. Simple to play. Best to use the Secret Skill Card"
        " once all 4 Heroes are on the board; it triggers only once per Hero.",
        "Menaikkan Level Hero dengan stabil lewat Skill Chessplayer. Mudah dimainkan. Sebaiknya gunakan Kartu Secret"
        " Skill setelah keempat Hero ada di papan; efeknya hanya terpicu 1 kali per Hero."),
    "香香可以主动攻击敌人，前期非常强势。拥有超过10级的1-3阶英雄越多香香攻击力越高，这套阵容低阶英雄多很适合香香。": (
        "Xiangxiang can attack enemies herself and is very strong early. The more Tier 1-3 Heroes above Lv. 10 you"
        " have, the higher her Attack; this Lineup has many low-Tier Heroes, so it suits Xiangxiang well.",
        "Xiangxiang bisa menyerang musuh sendiri dan sangat kuat di awal. Makin banyak Hero Tier 1-3 di atas Lv. 10"
        " yang kamu miliki, makin tinggi Attack Xiangxiang; Lineup ini punya banyak Hero Tier rendah, jadi sangat"
        " cocok untuk Xiangxiang."),

    # ResSeasonAILineupDataBin: Name (a narrow card and the share code's 【name】 prefix)
    "三分登场流": ("Three Kingdoms Deploy Build", "Build Deploy Three Kingdoms"),
    "乔汐速六司空震": ("Qiao Xi Rush-6 Sikong Zhen", "Qiao Xi Rush 6 Sikong Zhen"),
    "古币成长流": ("Ancient Coin Growth Build", "Build Growth Ancient Coin"),
    "图腾成长流": ("Totem Growth Build", "Build Growth Totem"),
    "大河图腾流": ("Riverlands Totem Build", "Build Riverlands Totem"),
    "嫦娥四小队": ("Chang'e Squad of Four", "Regu Empat Chang'e"),
    "安琪拉整备流": ("Angela Prepare Build", "Build Prepare Angela"),
    "常小娥四人队": ("Chang Xiao'e Team of Four", "Tim Empat Chang Xiao'e"),
    "战术牌成长流": ("Tactics Card Growth Build", "Build Growth Tactics Card"),
    "日落海整备流": ("Sunset Prepare Build", "Build Prepare Sunset"),
    "河洛古币流": ("Central Plains Ancient Coin Build", "Build Ancient Coin Central Plains"),
    "河洛牺牲李信": ("Central Plains Sacrifice Li Xin", "Li Xin Sacrifice Central Plains"),
    "逐鹿战术牌流": ("Zhulu Plateau Tactics Card Build", "Build Tactics Card Zhulu Plateau"),
    "马可万血猪": ("Marco 10K-HP Zhu Bajie", "Marco Zhu Bajie 10K HP"),
    "马可四驱兄弟": ("Marco Four Brothers", "Marco Empat Bersaudara"),

    # ResSeasonAILineupDataBin: OperationDetails.Desc
    "1至3回合凑齐四驱兄弟，优先觉醒曜牛魔和干将。如果禁了大河没有干将可以用孙膑替代。": (
        "In Rounds 1-3, assemble the Four Brothers and Awaken Yao, Niu Mo and Gan first. If Riverlands is banned and"
        " there is no Gan, use Sun Bin instead.",
        "Di Ronde 1-3, kumpulkan Empat Bersaudara dan prioritaskan Awaken Yao, Niu Mo, dan Gan. Jika Riverlands"
        " di-ban dan tidak ada Gan, ganti dengan Sun Bin."),
    "2级可以开始搜百里玄策，搜到快觉醒升3级，升级后继续拿其它可产古币的英雄牌（盾山、程咬金），产出古币全部给百里玄策养单C。": (
        "At Lv. 2 start searching for Xuance; once he is close to Awakening, level up to 3, then keep taking other"
        " Hero Cards that produce Ancient Coins (Dunshan, Cheng Yaojin) and give all the Ancient Coins to Xuance as"
        " the single Carry.",
        "Di Lv. 2 mulai cari Xuance; begitu dia hampir Awaken, naik ke Lv. 3, lalu terus ambil Kartu Hero lain yang"
        " menghasilkan Ancient Coin (Dunshan, Cheng Yaojin) dan berikan semua Ancient Coin ke Xuance sebagai Carry"
        " tunggal."),
    "4至7回合不花能量自动升级，获得的效果牌优先选找3阶英雄的，最好效果牌开出猪八戒或拍卖拿到，没有的话，8至11回合升至3级去找猪八戒。梦奇必拿，上阵后再卖掉非常划算。": (
        "In Rounds 4-7, spend no Energy and level up automatically. For Effect Cards, prefer ones that find Tier 3"
        " Heroes; ideally get Zhu Bajie from an Effect Card or the Auction, otherwise level up to 3 in Rounds 8-11 to"
        " look for him. Always take Menki: fielding him and then selling him is great value.",
        "Di Ronde 4-7, jangan pakai Energy dan biarkan naik level otomatis. Untuk Effect Card, utamakan yang mencari"
        " Hero Tier 3; idealnya dapatkan Zhu Bajie dari Effect Card atau Lelang, kalau tidak, naik ke Lv. 3 di Ronde"
        " 8-11 untuk mencarinya. Menki wajib diambil: turunkan ke papan lalu jual, sangat menguntungkan."),
    "5级后主要找吕布，吕布吸血效果能大幅增加英雄的生存能力，吕布也是一个强力输出英雄，后期可以培养他。如果有换帅可以把低阶英雄的等级换给吕布。有遗志和传承对孙尚香使用，孙尚香输出低后期建议换掉。": (
        "After Lv. 5, look mainly for Lu Bu: his Lifesteal greatly improves Hero survival, and he is also a strong"
        " damage dealer worth building up late. With Change of Commander, swap a low-Tier Hero's Levels onto Lu Bu."
        " Use Last Will and Inheritance on Lady Sun; her damage is low, so replace her late.",
        "Setelah Lv. 5, cari terutama Lu Bu: Lifesteal-nya sangat meningkatkan daya tahan Hero, dan dia juga damage"
        " dealer kuat yang layak dibesarkan di akhir. Dengan Pergantian Komandan, pindahkan Level Hero Tier rendah ke"
        " Lu Bu. Gunakan Last Will dan Inheritance pada Lady Sun; damage-nya rendah, jadi sebaiknya diganti di akhir."),
    "不搜牌，有多余能量就升级，升到4级开始搜马超和瑶。": (
        "Don't search for cards; spend spare Energy on levelling up, and at Lv. 4 start searching for Ma Chao and"
        " Yaria.",
        "Jangan cari kartu; pakai sisa Energy untuk naik level, dan di Lv. 4 mulai cari Ma Chao dan Yaria."),
    "不花能量刷新商店，如果自动刷出需要的英雄牌可以购买，有铠推荐买，前期战力很强。": (
        "Don't spend Energy to Refresh the Shop; buy needed Hero Cards if the automatic Refresh shows them. Kaizer is"
        " worth buying: he is very strong early.",
        "Jangan pakai Energy untuk Refresh Shop; beli Kartu Hero yang dibutuhkan jika muncul dari Refresh otomatis."
        " Kaizer layak dibeli: sangat kuat di awal."),
    "前期可以单挂一张弈星，不刷商店升到3级": (
        "Early on you can field just one Yixing and level up to 3 without Refreshing the Shop",
        "Di awal kamu bisa menurunkan satu Yixing saja dan naik ke Lv. 3 tanpa Refresh Shop"),
    "升到3级开始刷阵容里的卡牌，最好等刷到猪八戒再开始合成。手上留一张猪八戒，马可技能牌提供的冰曜宝石镜优先复制猪八戒让他觉醒。": (
        "At Lv. 3 start rolling for the Lineup's cards; ideally wait until you find Zhu Bajie before Combining. Keep"
        " one Zhu Bajie in hand and use the Ice Crystal Gemstone Mirror from Marco's Skill card to copy Zhu Bajie"
        " first so he Awakens.",
        "Di Lv. 3 mulai Refresh untuk kartu Lineup; sebaiknya tunggu sampai dapat Zhu Bajie sebelum Combine. Simpan"
        " satu Zhu Bajie di tangan dan gunakan Cermin Permata Kristal Es dari kartu Skill Marco untuk menyalin Zhu"
        " Bajie lebih dulu agar dia Awaken."),
    "合成后获得的效果锦囊优先拿传承、遗志、换帅，后期把孙尚香等级换给吕布或周瑜。其它英雄可以用遗志、传承把等级都换给C位。": (
        "From the Effect Guides you get after Combining, take Inheritance, Last Will and Change of Commander first,"
        " and later swap Lady Sun's Levels onto Lu Bu or Zhou Yu. Other Heroes can pass all their Levels to the Carry"
        " with Last Will and Inheritance.",
        "Dari Panduan Efek yang didapat setelah Combine, utamakan Inheritance, Last Will, dan Pergantian Komandan,"
        " lalu di akhir pindahkan Level Lady Sun ke Lu Bu atau Zhou Yu. Hero lain bisa memindahkan semua Level-nya ke"
        " Carry dengan Last Will dan Inheritance."),
    "后期可以找太乙复活猪八戒，如果血量健康能量充足，升到6级，马可的专属天赋可以让英雄伤害提升。": (
        "Late game, find Taiyi to Revive Zhu Bajie. If your HP is healthy and Energy plentiful, level up to 6: Marco's"
        " Exclusive Talent raises Hero damage.",
        "Di akhir, cari Taiyi untuk Revive Zhu Bajie. Jika HP aman dan Energy cukup, naik ke Lv. 6: Exclusive Talent"
        " Marco meningkatkan damage Hero."),
    "回合12升5级，主要找海诺，海诺在每次阿科米亚核心提升等级时都可提供额外等级。": (
        "Level up to 5 in Round 12 and look mainly for Heino, who gives extra Levels every time the Arcomia Core"
        " levels up.",
        "Naik ke Lv. 5 di Ronde 12 dan cari terutama Heino, yang memberi Level tambahan setiap kali Arcomia Core naik"
        " Level."),
    "回合12升5级，找吕布，吕布吸血效果能大幅增加英雄的生存能力。留一个空位用来不断使用【登场】英雄牌再删除。": (
        "Level up to 5 in Round 12 and find Lu Bu, whose Lifesteal greatly improves Hero survival. Keep one slot free"
        " to keep playing 【Deploy】 Hero Cards and then removing them.",
        "Naik ke Lv. 5 di Ronde 12 dan cari Lu Bu, yang Lifesteal-nya sangat meningkatkan daya tahan Hero. Sisakan"
        " satu slot kosong untuk terus memainkan Kartu Hero 【Deploy】 lalu menghapusnya."),
    "回合1优先买孙尚香，次选牛魔弈星。回合2升2级，优先购买阵容必备英雄。找到蔡文姬后，再使用三分英雄牌都能提升等级。推荐搭配赵云和曹操，曹操每回合固定触发赵云卡牌效果提升战力。第一次拍卖优先选择蔡文姬、曹操、赵云。": (
        "In Round 1 buy Lady Sun first, then Niu Mo or Yixing. Level up to 2 in Round 2 and buy the Lineup's key"
        " Heroes first. Once you have Cai Yan, every Three Kingdoms Hero Card you play raises Levels. Zilong and Cao"
        " Cao are recommended: Cao Cao triggers Zilong's Card Effect every Round to boost power. In the first Auction,"
        " pick Cai Yan, Cao Cao or Zilong first.",
        "Di Ronde 1 utamakan beli Lady Sun, lalu Niu Mo atau Yixing. Naik ke Lv. 2 di Ronde 2 dan utamakan beli Hero"
        " inti Lineup. Setelah dapat Cai Yan, setiap Kartu Hero Three Kingdoms yang dimainkan menaikkan Level."
        " Disarankan memakai Zilong dan Cao Cao: Cao Cao memicu Efek Kartu Zilong setiap Ronde untuk menambah"
        " kekuatan. Di Lelang pertama, utamakan Cai Yan, Cao Cao, atau Zilong."),
    "回合1优先购买曜和弈星。回合2升2级，回合3搜芈月，芈月的词条配合战术牌升级是这套阵容的核心，芈月必须觉醒。第一次拍卖优先选芈月、西施、老夫子、白起。": (
        "In Round 1 buy Yao and Yixing first. Level up to 2 in Round 2 and search for Mi Yue in Round 3: levelling"
        " through her Trait with Tactics Cards is this Lineup's core, so Mi Yue must Awaken. In the first Auction,"
        " pick Mi Yue, Shi, Fuzi or Bai Qi first.",
        "Di Ronde 1 utamakan beli Yao dan Yixing. Naik ke Lv. 2 di Ronde 2 dan cari Mi Yue di Ronde 3: naik level"
        " lewat Trait-nya dengan Tactics Card adalah inti Lineup ini, jadi Mi Yue wajib Awaken. Di Lelang pertama,"
        " utamakan Mi Yue, Shi, Fuzi, atau Bai Qi."),
    "回合1可选干将、弈星、牛魔过渡。回合2升2级，回合3-4主要找虞姬和鬼谷子，鬼谷子能召唤图腾，配合虞姬的卡牌效果提升等级。第一次拍卖优先选少司缘和张良。": (
        "In Round 1, Gan, Yixing or Niu Mo can serve as stopgaps. Level up to 2 in Round 2; in Rounds 3-4 look mainly"
        " for Consort Yu and Guiguzi: Guiguzi Summons Totems, which raise Levels with Consort Yu's Card Effect. In the"
        " first Auction, pick Dyadia and Liang first.",
        "Di Ronde 1, Gan, Yixing, atau Niu Mo bisa jadi pengisi sementara. Naik ke Lv. 2 di Ronde 2; di Ronde 3-4"
        " cari terutama Consort Yu dan Guiguzi: Guiguzi bisa Summon Totem, yang menaikkan Level bersama Efek Kartu"
        " Consort Yu. Di Lelang pertama, utamakan Dyadia dan Liang."),
    "回合1最佳拿李元芳和苏烈，每回合自己成长前期战力不俗。备选弈星，拿到可快速升级。回合2升2级，回合3开始存能量继续升级。每回合商店自动刷新碰到需要的阵容牌可以购买。": (
        "In Round 1, Fang and Su Lie are the best picks: they grow on their own each Round and are strong early."
        " Yixing is the backup and helps you level fast. Level up to 2 in Round 2, and from Round 3 save Energy to"
        " keep levelling. Buy the Lineup cards you need whenever the Shop's automatic Refresh shows them.",
        "Di Ronde 1, Fang dan Su Lie adalah pilihan terbaik: mereka tumbuh sendiri setiap Ronde dan kuat di awal."
        " Yixing jadi cadangan dan membantu naik level dengan cepat. Naik ke Lv. 2 di Ronde 2, dan mulai Ronde 3"
        " simpan Energy untuk terus naik level. Beli kartu Lineup yang dibutuhkan saat muncul dari Refresh otomatis"
        " Shop setiap Ronde."),
    "回合1购买李元芳和苏烈巩固战力，回合2升2级。回合3-4刷新商店，购买百里玄策、盾山，用古币拉高玄策等级。第一次拍卖优先拍百里玄策，其次程咬金和盾山。": (
        "In Round 1 buy Fang and Su Lie to shore up your power, and level up to 2 in Round 2. In Rounds 3-4 Refresh"
        " the Shop, buy Xuance and Dunshan, and raise Xuance's Level with Ancient Coins. In the first Auction bid for"
        " Xuance first, then Cheng Yaojin and Dunshan.",
        "Di Ronde 1 beli Fang dan Su Lie untuk memperkuat kekuatan, dan naik ke Lv. 2 di Ronde 2. Di Ronde 3-4"
        " Refresh Shop, beli Xuance dan Dunshan, dan naikkan Level Xuance dengan Ancient Coin. Di Lelang pertama"
        " utamakan Xuance, lalu Cheng Yaojin dan Dunshan."),
    "回合2升2级，升级后主要找虞姬，鬼谷子能召唤图腾，配合虞姬的词条提升等级。": (
        "Level up to 2 in Round 2, then look mainly for Consort Yu. Guiguzi Summons Totems, which raise Levels with"
        " Consort Yu's Trait.",
        "Naik ke Lv. 2 di Ronde 2, lalu cari terutama Consort Yu. Guiguzi bisa Summon Totem, yang menaikkan Level"
        " bersama Trait Consort Yu."),
    "回合2升2级，升级后优先找芈月，芈月的词条配合战术牌升级是这套阵容的核心，芈月必须觉醒。": (
        "Level up to 2 in Round 2, then look for Mi Yue first: levelling through her Trait with Tactics Cards is this"
        " Lineup's core, so Mi Yue must Awaken.",
        "Naik ke Lv. 2 di Ronde 2, lalu utamakan mencari Mi Yue: naik level lewat Trait-nya dengan Tactics Card"
        " adalah inti Lineup ini, jadi Mi Yue wajib Awaken."),
    "回合3-4优先购买米莱狄和亚连。第一次拍卖优先选朵莉亚和安琪拉。回合4升3级（第一次拍卖后），优先找朵莉亚，其它位置全部用带【整备】关键词的英雄，核心输出选择安琪拉。回合5-7继续寻找阵容英雄牌合成，优先觉醒朵莉亚和安琪拉。": (
        "In Rounds 3-4 buy Milady and Allain first. In the first Auction, pick Dolia and Angela first. Level up to 3"
        " in Round 4 (after the first Auction) and look for Dolia first; fill every other slot with Heroes with the"
        " 【Prepare】 keyword, with Angela as the core damage dealer. In Rounds 5-7 keep finding the Lineup's Hero Cards"
        " to Combine, Awakening Dolia and Angela first.",
        "Di Ronde 3-4 utamakan beli Milady dan Allain. Di Lelang pertama, utamakan Dolia dan Angela. Naik ke Lv. 3 di"
        " Ronde 4 (setelah Lelang pertama) dan utamakan mencari Dolia; isi semua posisi lain dengan Hero ber-keyword"
        " 【Prepare】, dengan Angela sebagai damage dealer inti. Di Ronde 5-7 terus cari Kartu Hero Lineup untuk"
        " Combine, prioritaskan Awaken Dolia dan Angela."),
    "回合3升2级，找到蔡文姬后，再使用三分英雄牌都能提升等级。推荐搭配赵云和曹操，曹操每回合固定触发赵云词条提升战力。": (
        "Level up to 2 in Round 3. Once you have Cai Yan, every Three Kingdoms Hero Card you play raises Levels."
        " Zilong and Cao Cao are recommended: Cao Cao triggers Zilong's Trait every Round to boost power.",
        "Naik ke Lv. 2 di Ronde 3. Setelah dapat Cai Yan, setiap Kartu Hero Three Kingdoms yang dimainkan menaikkan"
        " Level. Disarankan memakai Zilong dan Cao Cao: Cao Cao memicu Trait Zilong setiap Ronde untuk menambah"
        " kekuatan."),
    "回合4-5升3级，升级后主要找张良和少司缘，开团英雄可以配合张良卡牌效果升级，少司缘召唤的图腾也能配合虞姬的卡牌效果升级。可以暂时用瑶和云中君过渡，后期再换。回合6-7继续寻找阵容英雄，优先觉醒张良和虞姬。第二次拍卖优先拍敖隐。": (
        "Level up to 3 in Rounds 4-5, then look mainly for Liang and Dyadia: Initiate Heroes level up with Liang's"
        " Card Effect, and the Totems Dyadia Summons level up with Consort Yu's Card Effect. Yaria and Cirrus can hold"
        " the line for now and be swapped out later. In Rounds 6-7 keep finding Lineup Heroes, Awakening Liang and"
        " Consort Yu first. In the second Auction, bid for Ao'yin first.",
        "Naik ke Lv. 3 di Ronde 4-5, lalu cari terutama Liang dan Dyadia: Hero Initiate naik level bersama Efek Kartu"
        " Liang, dan Totem yang di-Summon Dyadia naik level bersama Efek Kartu Consort Yu. Yaria dan Cirrus bisa jadi"
        " pengisi sementara lalu diganti nanti. Di Ronde 6-7 terus cari Hero Lineup, prioritaskan Awaken Liang dan"
        " Consort Yu. Di Lelang kedua, utamakan Ao'yin."),
    "回合4-5升3级，继续找蔡文姬和曹操并优先觉醒。3级后可养貂蝉当输出。回合6-7升4级，找核心英雄小乔，找到后不断使用【登场】英雄牌，触发小乔的卡牌效果来增加整体英雄等级，找到小乔后升5级。第二次拍卖优先选择吕布、周瑜。": (
        "Level up to 3 in Rounds 4-5, keep looking for Cai Yan and Cao Cao and Awaken them first. After Lv. 3 you can"
        " build up Diaochan as a damage dealer. Level up to 4 in Rounds 6-7 and find the core Hero Xiao Qiao; then"
        " keep playing 【Deploy】 Hero Cards to trigger her Card Effect and raise every Hero's Level, and level up to 5"
        " once you have her. In the second Auction, pick Lu Bu or Zhou Yu first.",
        "Naik ke Lv. 3 di Ronde 4-5, terus cari Cai Yan dan Cao Cao lalu prioritaskan Awaken mereka. Setelah Lv. 3"
        " kamu bisa membesarkan Diaochan sebagai damage dealer. Naik ke Lv. 4 di Ronde 6-7 dan cari Hero inti Xiao"
        " Qiao; setelah itu terus mainkan Kartu Hero 【Deploy】 untuk memicu Efek Kartu-nya dan menaikkan Level semua"
        " Hero, lalu naik ke Lv. 5 setelah mendapatkannya. Di Lelang kedua, utamakan Lu Bu atau Zhou Yu."),
    "回合4-5提升棋手到3级，继续刷新商店，优先觉醒百里玄策，再补充程咬金、钟馗。程咬金和盾山可以产出古币，给玄策使用。回合6-8将棋手升到4级，只购买必备英雄增强战力，其余能量留着升级。第二次拍卖优先拍太乙真人和上官婉儿。": (
        "Raise your Chessplayer to Lv. 3 in Rounds 4-5 and keep Refreshing the Shop. Awaken Xuance first, then add"
        " Cheng Yaojin and Kui. Cheng Yaojin and Dunshan produce Ancient Coins for Xuance. In Rounds 6-8 raise your"
        " Chessplayer to Lv. 4, buy only key Heroes to add power, and save the rest of your Energy for levelling. In"
        " the second Auction, bid for Taiyi Zhenren and Shangguan first.",
        "Naikkan Chessplayer ke Lv. 3 di Ronde 4-5 dan terus Refresh Shop. Prioritaskan Awaken Xuance, lalu tambahkan"
        " Cheng Yaojin dan Kui. Cheng Yaojin dan Dunshan menghasilkan Ancient Coin untuk Xuance. Di Ronde 6-8 naikkan"
        " Chessplayer ke Lv. 4, beli hanya Hero inti untuk menambah kekuatan, dan simpan sisa Energy untuk naik"
        " level. Di Lelang kedua, utamakan Taiyi Zhenren dan Shangguan."),
    "回合4升3级（第一次拍卖后）。这套阵容核心牌集中在3级，需要快速升级。优先找朵莉亚，其它位置全部用带【整备】关键词的英雄，如安琪拉、米莱狄、亚连。回合8升4级，继续提升战力，补充带【整备】关键词的英雄。": (
        "Level up to 3 in Round 4 (after the first Auction). This Lineup's key cards are concentrated at Lv. 3, so"
        " level up fast. Look for Dolia first and fill every other slot with Heroes with the 【Prepare】 keyword, such"
        " as Angela, Milady and Allain. Level up to 4 in Round 8, keep building power and add more Heroes with the"
        " 【Prepare】 keyword.",
        "Naik ke Lv. 3 di Ronde 4 (setelah Lelang pertama). Kartu inti Lineup ini terkumpul di Lv. 3, jadi naik level"
        " dengan cepat. Utamakan mencari Dolia dan isi semua posisi lain dengan Hero ber-keyword 【Prepare】 seperti"
        " Angela, Milady, dan Allain. Naik ke Lv. 4 di Ronde 8, terus tambah kekuatan dan lengkapi Hero ber-keyword"
        " 【Prepare】."),
    "回合4升3级，升级后优先找西施，西施的战术牌使用次数越多越强。其它位置可搭配任意产出战术牌的英雄如白起老夫子。觉醒顺序芈月＞西施＞白起。回合4-7找齐阵容英雄后，提升棋手到4级。第二次拍卖优先选择蒙犽，其次庄周。": (
        "Level up to 3 in Round 4, then look for Shi first: the more Tactics Cards are used, the stronger she gets."
        " Fill other slots with any Hero that produces Tactics Cards, such as Bai Qi or Fuzi. Awaken in this order: Mi"
        " Yue > Shi > Bai Qi. Once the Lineup's Heroes are complete in Rounds 4-7, raise your Chessplayer to Lv. 4. In"
        " the second Auction, pick Meng Ya first, then Zhuangzi.",
        "Naik ke Lv. 3 di Ronde 4, lalu utamakan mencari Shi: makin sering Tactics Card dipakai, makin kuat dia. Isi"
        " posisi lain dengan Hero apa pun yang menghasilkan Tactics Card, seperti Bai Qi atau Fuzi. Urutan Awaken: Mi"
        " Yue > Shi > Bai Qi. Setelah Hero Lineup lengkap di Ronde 4-7, naikkan Chessplayer ke Lv. 4. Di Lelang"
        " kedua, utamakan Meng Ya, lalu Zhuangzi."),
    "回合4升3级，升级后优先找西施，西施的战术牌使用次数越多越强。其它位置可搭配任意英雄稳住血量。": (
        "Level up to 3 in Round 4, then look for Shi first: the more Tactics Cards are used, the stronger she gets."
        " Fill other slots with any Heroes to protect your HP.",
        "Naik ke Lv. 3 di Ronde 4, lalu utamakan mencari Shi: makin sering Tactics Card dipakai, makin kuat dia. Isi"
        " posisi lain dengan Hero apa pun untuk menjaga HP."),
    "回合5-7升4级，尝试搜几次李信，没搜到继续存能量升级。第二次拍卖优先拍李信。": (
        "Level up to 4 in Rounds 5-7 and search for Li Xin a few times; if he doesn't show up, keep saving Energy to"
        " level up. In the second Auction, bid for Li Xin first.",
        "Naik ke Lv. 4 di Ronde 5-7 dan coba cari Li Xin beberapa kali; jika belum dapat, terus simpan Energy untuk"
        " naik level. Di Lelang kedua, utamakan Li Xin."),
    "回合5升3级，升级后主要找张良，上阵开团英雄配合张良词条升级。有图腾英雄也继续购买。可以暂时用瑶和云中君过渡，后期再换。": (
        "Level up to 3 in Round 5, then look mainly for Liang; field Initiate Heroes to level up with Liang's Trait."
        " Keep buying Totem Heroes too. Yaria and Cirrus can hold the line for now and be swapped out later.",
        "Naik ke Lv. 3 di Ronde 5, lalu cari terutama Liang; turunkan Hero Initiate untuk naik level bersama Trait"
        " Liang. Terus beli Hero Totem juga. Yaria dan Cirrus bisa jadi pengisi sementara lalu diganti nanti."),
    "回合5升3级，继续稳战力。回合8升4级，找核心英雄小乔，找到后不断使用【登场】英雄牌，触发小乔的词条来增加整体英雄等级。": (
        "Level up to 3 in Round 5 and keep your power steady. Level up to 4 in Round 8 and find the core Hero Xiao"
        " Qiao; then keep playing 【Deploy】 Hero Cards to trigger her Trait and raise every Hero's Level.",
        "Naik ke Lv. 3 di Ronde 5 dan jaga kekuatan tetap stabil. Naik ke Lv. 4 di Ronde 8 dan cari Hero inti Xiao"
        " Qiao; setelah itu terus mainkan Kartu Hero 【Deploy】 untuk memicu Trait-nya dan menaikkan Level semua Hero."),
    "回合8-10升5级开始搜李信和其他阵容牌。婉儿搭配花木兰可以让花木兰多复活1次触发牺牲效果。后期有【整备】效果牌拿到给婉儿用。小明多多益善，每回合保留李信战斗中提升的等级。": (
        "Level up to 5 in Rounds 8-10 and start searching for Li Xin and the other Lineup cards. Shangguan with Mulan"
        " lets Mulan Revive once more to trigger a Sacrifice effect. Late game, give any 【Prepare】 Effect Card you get"
        " to Shangguan. The more Ming the better: he keeps the Levels Li Xin gains in battle each Round.",
        "Naik ke Lv. 5 di Ronde 8-10 dan mulai cari Li Xin serta kartu Lineup lainnya. Shangguan bersama Mulan"
        " membuat Mulan bisa Revive 1 kali lagi untuk memicu efek Sacrifice. Di akhir, berikan Effect Card 【Prepare】"
        " yang didapat ke Shangguan. Makin banyak Ming makin baik: dia menyimpan Level yang didapat Li Xin dalam"
        " Pertempuran setiap Ronde."),
    "回合8升4级，优先找主C蒙犽，继续搜能提供战术牌的英雄，通过不断使用战术牌提升主C等级。": (
        "Level up to 4 in Round 8 and look for the Main Carry Meng Ya first; keep searching for Heroes that provide"
        " Tactics Cards, and keep using Tactics Cards to raise the Main Carry's Level.",
        "Naik ke Lv. 4 di Ronde 8 dan utamakan mencari Main Carry Meng Ya; terus cari Hero yang memberi Tactics Card,"
        " dan terus gunakan Tactics Card untuk menaikkan Level Main Carry."),
    "回合8升4级，升级后优先找太乙，太乙可以复活百里玄策。上官婉儿能产出古币增加整体战力，钟馗可以降低对方主C的等级。": (
        "Level up to 4 in Round 8, then look for Taiyi first: Taiyi can Revive Xuance. Shangguan produces Ancient"
        " Coins to raise overall power, and Kui can lower the enemy Main Carry's Level.",
        "Naik ke Lv. 4 di Ronde 8, lalu utamakan mencari Taiyi: Taiyi bisa Revive Xuance. Shangguan menghasilkan"
        " Ancient Coin untuk menambah kekuatan keseluruhan, dan Kui bisa menurunkan Level Main Carry lawan."),
    "回合8升4级，继续补充图腾英雄和开团英雄。回合12升5级，升级后主要找敖隐，场上图腾全部放最后排战斗中持续给敖隐加等级。东皇的卡牌效果使图腾不会被优先攻击，搭配敖隐让敖隐在战斗中稳定升级。": (
        "Level up to 4 in Round 8 and keep adding Totem and Initiate Heroes. Level up to 5 in Round 12, then look"
        " mainly for Ao'yin; put every Totem on the back row so they keep giving Ao'yin Levels in battle. Donghuang's"
        " Card Effect keeps Totems from being targeted first, so with him Ao'yin levels up steadily in battle.",
        "Naik ke Lv. 4 di Ronde 8 dan terus tambah Hero Totem dan Hero Initiate. Naik ke Lv. 5 di Ronde 12, lalu cari"
        " terutama Ao'yin; taruh semua Totem di baris paling belakang agar terus memberi Level ke Ao'yin dalam"
        " Pertempuran. Efek Kartu Donghuang membuat Totem tidak diserang lebih dulu, sehingga bersamanya Level Ao'yin"
        " naik stabil dalam Pertempuran."),
    "回合8升优先找主C蒙犽，继续搜能提供战术牌的英雄，通过不断使用战术牌提升主C等级。回合9-11继续将棋手升到5级，上阵鲁班七号。": (
        "Level up in Round 8 and look for the Main Carry Meng Ya first; keep searching for Heroes that provide Tactics"
        " Cards, and keep using Tactics Cards to raise the Main Carry's Level. In Rounds 9-11 keep raising your"
        " Chessplayer to Lv. 5 and field Luban No.7.",
        "Naik level di Ronde 8 dan utamakan mencari Main Carry Meng Ya; terus cari Hero yang memberi Tactics Card,"
        " dan terus gunakan Tactics Card untuk menaikkan Level Main Carry. Di Ronde 9-11 terus naikkan Chessplayer ke"
        " Lv. 5 dan turunkan Luban No.7."),
    "回合9-11提升棋手到5级，主要搜太乙真人，太乙可以复活玄策增加容错。上官婉儿每回合固定对阵容英雄使用古币增加整体战力。优先觉醒太乙和钟馗。": (
        "Raise your Chessplayer to Lv. 5 in Rounds 9-11 and search mainly for Taiyi Zhenren: Taiyi can Revive Xuance,"
        " giving you room for error. Shangguan uses Ancient Coins on the Lineup's Heroes every Round, raising overall"
        " power. Awaken Taiyi and Kui first.",
        "Naikkan Chessplayer ke Lv. 5 di Ronde 9-11 dan cari terutama Taiyi Zhenren: Taiyi bisa Revive Xuance,"
        " memberi ruang untuk kesalahan. Shangguan memakai Ancient Coin pada Hero Lineup setiap Ronde, menambah"
        " kekuatan keseluruhan. Prioritaskan Awaken Taiyi dan Kui."),
    "尽快把棋手升到6级，搜司空震和其他需要的卡牌。": (
        "Raise your Chessplayer to Lv. 6 as fast as possible and search for Sikong Zhen and the other cards you need.",
        "Naikkan Chessplayer ke Lv. 6 secepat mungkin dan cari Sikong Zhen serta kartu lain yang dibutuhkan."),
    "开局买一张狂铁，狂铁每回合自动成长适合前期过渡，回合2升2级。": (
        "Buy a Biron at the start: he grows automatically each Round, a good early stopgap. Level up to 2 in Round 2.",
        "Beli satu Biron di awal: dia tumbuh otomatis setiap Ronde, cocok sebagai pengisi sementara di awal. Naik ke"
        " Lv. 2 di Ronde 2."),
    "开局买一张狂铁，狂铁每回合自动成长适合前期过渡，没有狂铁可以用牛魔或弈星过渡。回合2升2级。": (
        "Buy a Biron at the start: he grows automatically each Round, a good early stopgap. Without Biron, use Niu Mo"
        " or Yixing as stopgaps. Level up to 2 in Round 2.",
        "Beli satu Biron di awal: dia tumbuh otomatis setiap Ronde, cocok sebagai pengisi sementara di awal. Tanpa"
        " Biron, pakai Niu Mo atau Yixing sebagai pengisi sementara. Naik ke Lv. 2 di Ronde 2."),
    "开局拿一张李元芳过渡，回合2升2级。": (
        "Take a Fang at the start as a stopgap, and level up to 2 in Round 2.",
        "Ambil satu Fang di awal sebagai pengisi sementara, dan naik ke Lv. 2 di Ronde 2."),
    "找到马超和瑶之后继续升级到6级，补一张吕布给马超加吸血。血量健康的话棋手秘技牌等凑齐4个英雄再使用，血量低可看情况提前用。": (
        "After finding Ma Chao and Yaria, keep levelling up to 6 and add a Lu Bu to give Ma Chao Lifesteal. If your HP"
        " is healthy, wait until you have all 4 Heroes before using the Chessplayer's Secret Skill Card; if HP is low,"
        " use it earlier as needed.",
        "Setelah mendapat Ma Chao dan Yaria, terus naik level sampai Lv. 6 dan tambahkan Lu Bu untuk memberi"
        " Lifesteal ke Ma Chao. Jika HP aman, tunggu sampai keempat Hero lengkap sebelum menggunakan Kartu Secret"
        " Skill Chessplayer; jika HP rendah, gunakan lebih awal sesuai situasi."),
    "有弈星可以拿一张，每回合只花费1能量使用棋手技能，开出什么英雄上什么英雄，其余能量都留着升级。优先选经济类的天赋或加血的天赋。": (
        "Take a Yixing if you see one. Spend only 1 Energy per Round on the Chessplayer Skill and field whatever Hero"
        " it gives; save the rest of your Energy for levelling. Prefer economy Talents or healing Talents.",
        "Ambil satu Yixing jika ada. Pakai hanya 1 Energy per Ronde untuk Skill Chessplayer dan turunkan Hero apa pun"
        " yang didapat; simpan sisa Energy untuk naik level. Utamakan Talent ekonomi atau Talent penambah HP."),
    "第二次拍卖优先选海诺和雅典娜。回合8-11将棋手升到5级，主要找海诺和雅典娜，海诺在每次阿科米亚核心提升等级时都可提供额外等级。": (
        "In the second Auction, pick Heino and Athena first. Raise your Chessplayer to Lv. 5 in Rounds 8-11 and look"
        " mainly for Heino and Athena; Heino gives extra Levels every time the Arcomia Core levels up.",
        "Di Lelang kedua, utamakan Heino dan Athena. Naikkan Chessplayer ke Lv. 5 di Ronde 8-11 dan cari terutama"
        " Heino dan Athena; Heino memberi Level tambahan setiap kali Arcomia Core naik Level."),
    "苏烈一定要拿，觉醒后的苏烈前期战力很强。单挂一张苏烈，棋手技能都用给苏烈，有多余的英雄可以开战前上阵打完卖掉。": (
        "Always take Su Lie: an Awakened Su Lie is very strong early. Field a single Su Lie and use every Chessplayer"
        " Skill on him; spare Heroes can be fielded before battle and sold afterwards.",
        "Su Lie wajib diambil: Su Lie yang sudah Awaken sangat kuat di awal. Turunkan satu Su Lie saja dan gunakan"
        " semua Skill Chessplayer padanya; Hero sisa bisa diturunkan sebelum Pertempuran lalu dijual setelahnya."),

    # ResSeasonAILineupDataBin: PositionDesc
    "决赛圈注意下安琪拉的站位，如果对方有闪现的英雄，则用雅典娜和其他友方英雄将安琪拉包围住，防止闪现英雄近身。": (
        "In the finals, mind Angela's position: if the enemy has Flash Heroes, surround Angela with Athena and other"
        " allied Heroes to keep Flash Heroes from reaching her.",
        "Di final, perhatikan posisi Angela: jika lawan punya Hero Flash, kelilingi Angela dengan Athena dan Hero"
        " sekutu lain agar Hero Flash tidak bisa mendekat."),
    "明世隐和太乙真人连司空震。钟馗两侧都要放英雄来触发他的卡牌效果。": (
        "Link Ming and Taiyi Zhenren to Sikong Zhen. Place Heroes on both sides of Kui to trigger his Card Effect.",
        "Hubungkan Ming dan Taiyi Zhenren ke Sikong Zhen. Taruh Hero di kedua sisi Kui untuk memicu Efek Kartu-nya."),
    "李元芳和百里玄策放在一起，触发李元芳卡牌效果（李元芳周围不要放其它英雄，其英雄效果只对最近英雄生效）。太乙放在玄策旁边复活玄策。": (
        "Place Fang next to Xuance to trigger Fang's Card Effect (put no other Heroes around Fang; his Hero Effect"
        " only works on the nearest Hero). Put Taiyi beside Xuance to Revive him.",
        "Taruh Fang bersebelahan dengan Xuance untuk memicu Efek Kartu Fang (jangan taruh Hero lain di sekitar Fang;"
        " Efek Hero-nya hanya berlaku untuk Hero terdekat). Taruh Taiyi di samping Xuance untuk Revive Xuance."),
    "瑶、明世隐、太乙真人都连猪八戒。": (
        "Link Yaria, Ming and Taiyi Zhenren all to Zhu Bajie.",
        "Hubungkan Yaria, Ming, dan Taiyi Zhenren semuanya ke Zhu Bajie."),
    "瑶连马超，瑶的技能可以给连接的英雄增加属性。": (
        "Link Yaria to Ma Chao: Yaria's Skill boosts the stats of the Hero she is linked to.",
        "Hubungkan Yaria ke Ma Chao: Skill Yaria menambah atribut Hero yang terhubung dengannya."),
    "蔡文姬的技能可以给范围内英雄回血，建议放在中间。": (
        "Cai Yan's Skill heals Heroes in range, so place her in the middle.",
        "Skill Cai Yan memulihkan HP Hero dalam jangkauan, jadi taruh dia di tengah."),
    "虞姬和敖隐放最后一排。拿到敖隐后需要把所有图腾都放最后一排，图腾在场上时能触发敖隐的卡牌效果，敖隐在战斗中持续提升等级。": (
        "Place Consort Yu and Ao'yin on the back row. Once you have Ao'yin, put every Totem on the back row: Totems on"
        " the board trigger Ao'yin's Card Effect, so Ao'yin keeps levelling up in battle.",
        "Taruh Consort Yu dan Ao'yin di baris paling belakang. Setelah dapat Ao'yin, taruh semua Totem di baris"
        " paling belakang: Totem di papan memicu Efek Kartu Ao'yin, sehingga Level Ao'yin terus naik dalam"
        " Pertempuran."),
    "钟馗的卡牌效果可以给两侧英雄加牺牲关键词，两侧放自身不带牺牲的英雄。小明和太乙都连李信。": (
        "Kui's Card Effect gives the Heroes on both sides the Sacrifice keyword, so flank him with Heroes that lack"
        " Sacrifice. Link Ming and Taiyi both to Li Xin.",
        "Efek Kartu Kui memberi keyword Sacrifice ke Hero di kedua sisinya, jadi taruh Hero tanpa Sacrifice di kedua"
        " sisinya. Hubungkan Ming dan Taiyi ke Li Xin."),

    # ResSeasonAILineupDataBin: SimpleDesc
    "7回合以前都不升级，碰到牛魔、曜、干将、孙尚香都直接买，可以等有曜了再合成。前期用干将当主C，后期通过遗志、传承、换帅养周瑜或吕布。": (
        "Don't level up before Round 7; buy Niu Mo, Yao, Gan and Lady Sun whenever you see them, and you can wait for"
        " Yao before Combining. Early on Gan is the Main Carry; later build up Zhou Yu or Lu Bu with Last Will,"
        " Inheritance and Change of Commander.",
        "Jangan naik level sebelum Ronde 7; langsung beli Niu Mo, Yao, Gan, dan Lady Sun setiap kali muncul, dan kamu"
        " bisa menunggu Yao sebelum Combine. Di awal Gan jadi Main Carry; nanti besarkan Zhou Yu atau Lu Bu lewat"
        " Last Will, Inheritance, dan Pergantian Komandan."),
    "C位百里玄策，上阵后不断对百里玄策使用古币牌增加等级。上官婉儿、盾山、程咬金产出古币，太乙可复活百里玄策。": (
        "Xuance is the Carry: once he is on the board, keep using Ancient Coin Cards on him to raise his Level."
        " Shangguan, Dunshan and Cheng Yaojin produce Ancient Coins, and Taiyi can Revive Xuance.",
        "Xuance adalah Carry: setelah dia di papan, terus gunakan Kartu Ancient Coin padanya untuk menaikkan Level."
        " Shangguan, Dunshan, dan Cheng Yaojin menghasilkan Ancient Coin, dan Taiyi bisa Revive Xuance."),
    "C位百里玄策，上阵后不断对百里玄策使用古币牌增加等级。其它英雄选能获取古币牌的英雄即可。": (
        "Xuance is the Carry: once he is on the board, keep using Ancient Coin Cards on him to raise his Level. For"
        " the other slots, any Heroes that get Ancient Coin Cards will do.",
        "Xuance adalah Carry: setelah dia di papan, terus gunakan Kartu Ancient Coin padanya untuk menaikkan Level."
        " Untuk posisi lain, cukup pilih Hero yang bisa mendapat Kartu Ancient Coin."),
    "乔汐6级后专属天赋可以召唤高等级英雄入场，此英雄等级算作临时等级，可以触发司空震的卡牌效果让他也获得临时等级。明世隐能保留临时等级。": (
        "From Lv. 6, Qiao Xi's Exclusive Talent Summons a high-Level Hero onto the board. That Hero's Level counts as"
        " Temporary Level, which triggers Sikong Zhen's Card Effect so he gains Temporary Levels too. Ming can keep"
        " Temporary Levels.",
        "Mulai Lv. 6, Exclusive Talent Qiao Xi bisa Summon Hero ber-Level tinggi ke papan. Level Hero itu dihitung"
        " sebagai Temporary Level, yang memicu Efek Kartu Sikong Zhen sehingga dia juga mendapat Temporary Level."
        " Ming bisa menyimpan Temporary Level."),
    "前期优先找蔡文姬，蔡文姬上阵后不断使用【三分】英雄牌来触发蔡文姬的卡牌效果，提升整体英雄等级。小乔来了后，配合【登场】英雄加速升级。": (
        "Look for Cai Yan first. Once she is on the board, keep playing 【Three Kingdoms】 Hero Cards to trigger her"
        " Card Effect and raise every Hero's Level. Once Xiao Qiao arrives, pair her with 【Deploy】 Heroes to level up"
        " faster.",
        "Utamakan mencari Cai Yan di awal. Setelah dia di papan, terus mainkan Kartu Hero 【Three Kingdoms】 untuk"
        " memicu Efek Kartu-nya dan menaikkan Level semua Hero. Setelah Xiao Qiao datang, pasangkan dengan Hero"
        " 【Deploy】 untuk naik level lebih cepat."),
    "前期优先找蔡文姬，蔡文姬上阵后不断使用【三分】英雄牌来触发蔡文姬的卡牌效果，提升整体英雄等级。小乔来了后，配合【登场】英雄加速升级。天赋方面主要选三分阵营或登场关键词相关天赋。": (
        "Look for Cai Yan first. Once she is on the board, keep playing 【Three Kingdoms】 Hero Cards to trigger her"
        " Card Effect and raise every Hero's Level. Once Xiao Qiao arrives, pair her with 【Deploy】 Heroes to level up"
        " faster. For Talents, mainly pick ones tied to the Three Kingdoms Faction or the Deploy keyword.",
        "Utamakan mencari Cai Yan di awal. Setelah dia di papan, terus mainkan Kartu Hero 【Three Kingdoms】 untuk"
        " memicu Efek Kartu-nya dan menaikkan Level semua Hero. Setelah Xiao Qiao datang, pasangkan dengan Hero"
        " 【Deploy】 untuk naik level lebih cepat. Untuk Talent, utamakan yang terkait Faction Three Kingdoms atau"
        " keyword Deploy."),
    "功能英雄芈月，上阵后使用战术牌触发卡牌效果，给装备最多的英雄升级。输出英雄蒙犽，其它位置拿任意可产出战术牌的英雄。": (
        "Mi Yue is the utility Hero: once she is on the board, Tactics Cards trigger her Card Effect and level up the"
        " Hero with the most Equipment. Meng Ya is the damage dealer; fill the other slots with any Heroes that"
        " produce Tactics Cards.",
        "Mi Yue adalah Hero utilitas: setelah dia di papan, Tactics Card memicu Efek Kartu-nya dan menaikkan Level"
        " Hero dengan Equipment terbanyak. Meng Ya adalah damage dealer; isi posisi lain dengan Hero apa pun yang"
        " menghasilkan Tactics Card."),
    "嫦娥的技能可以提升英雄等级，秘技牌能使4个英雄同时升级，只上阵4个强力英雄可以让嫦娥技能收益最大，这套阵容只需要一直用嫦娥的技能提升等级。": (
        "Chang'e's Skill raises Hero Levels and her Secret Skill Card levels up 4 Heroes at once. Fielding only 4"
        " strong Heroes gets the most out of her Skill; this Lineup just keeps using Chang'e's Skill to raise Levels.",
        "Skill Chang'e menaikkan Level Hero dan Kartu Secret Skill-nya menaikkan Level 4 Hero sekaligus. Hanya"
        " menurunkan 4 Hero kuat memaksimalkan manfaat Skill-nya; Lineup ini cukup terus memakai Skill Chang'e untuk"
        " menaikkan Level."),
    "李信的卡牌效果是：其它英雄触发牺牲效果时，提升等级。除李信其他位置拿牺牲英雄，且复活次数越多，能触发牺牲的次数越多。小明可以保留李信在战斗中提升的等级，每回合给李信稳定升级。": (
        "Li Xin's Card Effect: he gains Levels when other Heroes trigger Sacrifice effects. Fill every slot besides Li"
        " Xin with Sacrifice Heroes; the more they Revive, the more Sacrifices they trigger. Ming keeps the Levels Li"
        " Xin gains in battle, levelling him up steadily each Round.",
        "Efek Kartu Li Xin: Level-nya naik saat Hero lain memicu efek Sacrifice. Isi semua posisi selain Li Xin"
        " dengan Hero Sacrifice; makin sering mereka Revive, makin sering Sacrifice terpicu. Ming menyimpan Level"
        " yang didapat Li Xin dalam Pertempuran, menaikkan Level-nya dengan stabil setiap Ronde."),
    "核心英雄虞姬，找到虞姬后，凑齐三个图腾英雄，触发虞姬词条升级。次级核心张良，找到张良后，尽量多上开团英雄，提升等级。升到5级后找到敖隐和东皇阵容成型。": (
        "Consort Yu is the core Hero: once you have her, gather three Totem Heroes to trigger her Trait and level up."
        " Liang is the second core: once you have him, field as many Initiate Heroes as you can to raise Levels. At"
        " Lv. 5, finding Ao'yin and Donghuang completes the Lineup.",
        "Consort Yu adalah Hero inti: setelah mendapatkannya, kumpulkan tiga Hero Totem untuk memicu Trait-nya dan"
        " naik level. Liang adalah inti kedua: setelah mendapatkannya, turunkan Hero Initiate sebanyak mungkin untuk"
        " menaikkan Level. Di Lv. 5, Lineup lengkap setelah mendapat Ao'yin dan Donghuang."),
    "猪八戒的卡牌效果可以在英雄合成时给全部同阶英雄升级，因此阵容选3阶英雄。瑶给猪八戒增加属性，刘禅战斗中提供临时等级，明世隐保留战斗中的临时等级，使猪八戒的战力最大化。姬小满提供刷新帮助找场上的英雄牌。": (
        "Zhu Bajie's Card Effect levels up every Hero of the same Tier when a Hero Combines, so the Lineup uses Tier 3"
        " Heroes. Yaria boosts Zhu Bajie's stats, Liu Shan gives Temporary Levels in battle and Ming keeps them,"
        " maximizing Zhu Bajie's power. Mayene gives Refreshes that help find Hero Cards of Heroes on the board.",
        "Efek Kartu Zhu Bajie menaikkan Level semua Hero dengan Tier yang sama saat Hero di-Combine, jadi Lineup ini"
        " memakai Hero Tier 3. Yaria menambah atribut Zhu Bajie, Liu Shan memberi Temporary Level dalam Pertempuran,"
        " dan Ming menyimpannya, sehingga kekuatan Zhu Bajie maksimal. Mayene memberi Refresh yang membantu menemukan"
        " Kartu Hero dari Hero di papan."),
    "这套阵容的核心是增加阿科米亚核心等级。朵莉亚是必备英雄，上阵后其它位置全部使用带【整备】关键词的英雄，触发朵莉亚卡牌效果增加阿科米亚核心等级。": (
        "This Lineup is about raising the Arcomia Core's Level. Dolia is a must: once she is on the board, fill every"
        " other slot with Heroes with the 【Prepare】 keyword to trigger her Card Effect and raise the Arcomia Core's"
        " Level.",
        "Inti Lineup ini adalah menaikkan Level Arcomia Core. Dolia wajib ada: setelah dia di papan, isi semua posisi"
        " lain dengan Hero ber-keyword 【Prepare】 untuk memicu Efek Kartu-nya dan menaikkan Level Arcomia Core."),
    "阵容的核心是增加阿科米亚核心等级。朵莉亚是必备英雄，上阵后其它位置全部使用带【整备】关键词的英雄，触发朵莉亚卡牌效果增加阿科米亚核心等级。阿科米亚核心的等级会在开战时以临时等级均分给场上的日落海英雄。": (
        "The Lineup is about raising the Arcomia Core's Level. Dolia is a must: once she is on the board, fill every"
        " other slot with Heroes with the 【Prepare】 keyword to trigger her Card Effect and raise the Arcomia Core's"
        " Level. At the start of battle, the Arcomia Core's Level is split evenly among Sunset Heroes on the board as"
        " Temporary Levels.",
        "Inti Lineup adalah menaikkan Level Arcomia Core. Dolia wajib ada: setelah dia di papan, isi semua posisi"
        " lain dengan Hero ber-keyword 【Prepare】 untuk memicu Efek Kartu-nya dan menaikkan Level Arcomia Core. Saat"
        " Pertempuran dimulai, Level Arcomia Core dibagi rata ke Hero Sunset di papan sebagai Temporary Level."),

    # ResSeasonAILineupDataBin: LineupDesc (a row field, not inside the code)
    "以培养阿科米亚核心为主的阵容，操作简单，凑齐阵容英雄后全员自动成长。": (
        "A Lineup built around growing the Arcomia Core. Easy to play: once its Heroes are assembled, the whole team"
        " grows on its own.",
        "Lineup yang berfokus membesarkan Arcomia Core. Mudah dimainkan: setelah Hero Lineup lengkap, seluruh tim"
        " tumbuh sendiri."),
    "以敖隐为核心输出的阵容，操作简单，凑齐阵容英雄后全员自动成长。": (
        "A Lineup with Ao'yin as the core damage dealer. Easy to play: once its Heroes are assembled, the whole team"
        " grows on its own.",
        "Lineup dengan Ao'yin sebagai damage dealer inti. Mudah dimainkan: setelah Hero Lineup lengkap, seluruh tim"
        " tumbuh sendiri."),
    "以李信为单核的阵容，前期需要快速升级找到李信，后期强力。": (
        "A single-carry Lineup around Li Xin. Level up fast early to find him; strong late.",
        "Lineup dengan Li Xin sebagai carry tunggal. Naik level cepat di awal untuk menemukannya; kuat di akhir."),
    "以百里玄策为单核的阵容，随着百里玄策的等级提升，后期非常强力。": (
        "A single-carry Lineup around Xuance. As his Level rises, it becomes very strong late.",
        "Lineup dengan Xuance sebagai carry tunggal. Seiring Level-nya naik, Lineup ini sangat kuat di akhir."),
    "全低阶英雄，前期操作简单，后期需要转型，有一定运营难度。": (
        "All low-Tier Heroes. Easy early on, but it must transition late, which takes some management.",
        "Semua Hero Tier rendah. Mudah di awal, tetapi perlu transisi di akhir, yang butuh sedikit pengelolaan."),
    "操作简单，运营思路简单，只需要合成就能全员成长。": (
        "Easy to play with a simple game plan: just Combine and the whole team grows.",
        "Mudah dimainkan dengan rencana permainan simpel: cukup Combine dan seluruh tim tumbuh."),
    "运营简单，但有一定运气成分，快速搜到司空震就能赢，否则容易出局。": (
        "Simple to run but luck-dependent: find Sikong Zhen fast and you win, otherwise you are easily knocked out.",
        "Simpel dijalankan tetapi bergantung keberuntungan: cepat dapat Sikong Zhen maka kamu menang, kalau tidak,"
        " mudah tereliminasi."),
    "这套阵容凑齐4个英雄后每回合靠棋手技能成长，操作难度低，但找齐英雄有一定运气成分。": (
        "Once its 4 Heroes are assembled, this Lineup grows each Round through the Chessplayer Skill. Easy to play,"
        " though finding all the Heroes takes some luck.",
        "Setelah 4 Hero-nya lengkap, Lineup ini tumbuh setiap Ronde lewat Skill Chessplayer. Mudah dimainkan, meski"
        " butuh sedikit keberuntungan untuk melengkapi Hero-nya."),
    "这套阵容很多英雄为低阶，养成难度低，适合新手使用。": (
        "Many of this Lineup's Heroes are low-Tier, so it is easy to build up and suits new players.",
        "Banyak Hero di Lineup ini ber-Tier rendah, jadi mudah dibesarkan dan cocok untuk pemain baru."),
    "这是用战术牌提升战力的阵容，操作比较复杂，需频繁使用卡牌，推荐有一定游戏经验后再尝试。": (
        "This Lineup builds power with Tactics Cards. It is fairly complex and needs frequent card play, so try it"
        " once you have some experience.",
        "Lineup ini menambah kekuatan dengan Tactics Card. Cukup rumit dan perlu sering memainkan kartu, jadi coba"
        " setelah punya sedikit pengalaman."),

    # ResRecommendLineup: EquipDesc
    "亚连会给装备最多的英雄加属性，装备穿给主C，保证他穿的装备最多。": (
        "Allain boosts the stats of the Hero with the most Equipment, so put the Equipment on the Main Carry and make"
        " sure he wears the most.",
        "Allain menambah atribut Hero dengan Equipment terbanyak, jadi pakaikan Equipment ke Main Carry dan pastikan"
        " dia memakai Equipment paling banyak."),
    "优先拿法术输出装给诸葛亮，大乔可以穿回蓝装快速放技能。": (
        "Get magic damage Equipment for Kongming first; Da Qiao can wear Mana regen Equipment to cast her Skill fast.",
        "Utamakan Equipment magic damage untuk Kongming; Da Qiao bisa memakai Equipment pemulih Mana agar cepat"
        " mengeluarkan Skill."),
    "优先拿物理输出装给裴擒虎，多余装备给阿轲。": (
        "Get physical damage Equipment for Pei first; give spare Equipment to Arke.",
        "Utamakan Equipment physical damage untuk Pei; berikan Equipment sisa ke Arke."),
    "所有装备都先穿给蒙恬，芈月只给装备最多的英雄加等级。蒙恬和米莱狄优先拿恢复法力值的装备，释放技能召唤小兵。装备优先级：聚灵水晶>生命魔典>不死鸟之眼。": (
        "Put all Equipment on Meng Tian first: Mi Yue only levels up the Hero with the most Equipment. Meng Tian and"
        " Milady should get Mana-restoring Equipment first so they cast Skills to Summon soldiers. Equipment priority:"
        " Spirit-Gathering Crystal > Grimoire of Life > Eye of the Phoenix.",
        "Pakaikan semua Equipment ke Meng Tian lebih dulu: Mi Yue hanya menaikkan Level Hero dengan Equipment"
        " terbanyak. Meng Tian dan Milady sebaiknya mendapat Equipment pemulih Mana lebih dulu agar bisa mengeluarkan"
        " Skill untuk Summon prajurit. Prioritas Equipment: Spirit-Gathering Crystal > Grimoire of Life > Eye of the"
        " Phoenix."),
    "所有装备都先穿给蒙恬，芈月只给装备最多的英雄加等级。蒙恬和米莱狄优先拿恢复法力值的装备，释放技能召唤小兵。装备优先级：聚灵水晶>生命魔典>极寒风暴。": (
        "Put all Equipment on Meng Tian first: Mi Yue only levels up the Hero with the most Equipment. Meng Tian and"
        " Milady should get Mana-restoring Equipment first so they cast Skills to Summon soldiers. Equipment priority:"
        " Spirit-Gathering Crystal > Grimoire of Life > Glacial Buckler.",
        "Pakaikan semua Equipment ke Meng Tian lebih dulu: Mi Yue hanya menaikkan Level Hero dengan Equipment"
        " terbanyak. Meng Tian dan Milady sebaiknya mendapat Equipment pemulih Mana lebih dulu agar bisa mengeluarkan"
        " Skill untuk Summon prajurit. Prioritas Equipment: Spirit-Gathering Crystal > Grimoire of Life > Glacial"
        " Buckler."),
    "输出装优先给韩信。": ("Give damage Equipment to Han Xin first.", "Utamakan Equipment damage untuk Han Xin."),

    # ResRecommendLineup and ResHeroStrategyDataBin: LordInfos.Desc
    "三分的低阶英雄能够为香香提供可观的攻击力加成，帮助她在前期打出稳定且强力的输出，后期香香也有很强的作战能力。": (
        "Low-Tier Three Kingdoms Heroes give Xiangxiang a sizable Attack bonus, helping her deal steady, strong damage"
        " early on; Xiangxiang also fights well in the late game.",
        "Hero Three Kingdoms Tier rendah memberi Xiangxiang bonus Attack yang besar, membantunya memberikan damage"
        " yang stabil dan kuat di awal; di akhir game Xiangxiang juga kuat bertarung."),
    "可以产出很多效果牌，搭配芈月给蒙恬升级。": (
        "Produces many Effect Cards; pair with Mi Yue to level up Meng Tian.",
        "Menghasilkan banyak Effect Card; pasangkan dengan Mi Yue untuk menaikkan Level Meng Tian."),
    "姜导可以增强C位，可配合狄仁杰使用。": (
        "Director Jiang strengthens the Carry; pair him with Di Renjie.",
        "Director Jiang memperkuat Carry; pasangkan dengan Di Renjie."),
    "姜导技能挂给蒙恬，蒙恬等级越高召唤小兵等级越高。": (
        "Use Director Jiang's Skill on Meng Tian: the higher Meng Tian's Level, the higher the Level of the soldiers"
        " he Summons.",
        "Gunakan Skill Director Jiang pada Meng Tian: makin tinggi Level Meng Tian, makin tinggi Level prajurit yang"
        " di-Summon."),
    "姜导的专属技能封神一瞬可以增加C位的生存能力。": (
        "Director Jiang's exclusive Skill, Moment of Apotheosis, improves the Carry's survival.",
        "Skill eksklusif Director Jiang, Moment of Apotheosis, meningkatkan daya tahan Carry."),
    "常小娥可以提升场上英雄等级，提升英雄战力。": (
        "Chang Xiao'e raises the Level of Heroes on the board, boosting their power.",
        "Chang Xiao'e menaikkan Level Hero di papan, menambah kekuatan Hero."),
    "常小娥的技能每个回合能增强场上的英雄，可以提升整体等级。": (
        "Chang Xiao'e's Skill strengthens the Heroes on the board every Round, raising overall Levels.",
        "Skill Chang Xiao'e memperkuat Hero di papan setiap Ronde, menaikkan Level secara keseluruhan."),
    "派对泡泡选三分，每回合使用棋手技能稳定获得一张阵容牌。4级再开秘技牌，能帮助找到诸葛亮和小乔。": (
        "Pick Three Kingdoms for Party Bubble and use the Chessplayer Skill every Round to reliably get a Lineup card."
        " Open the Secret Skill Card at Lv. 4 to help find Kongming and Xiao Qiao.",
        "Pilih Three Kingdoms untuk Party Bubble dan gunakan Skill Chessplayer setiap Ronde untuk pasti mendapat satu"
        " kartu Lineup. Buka Kartu Secret Skill di Lv. 4 untuk membantu menemukan Kongming dan Xiao Qiao."),
    "派对泡泡选大河流域，每回合使用棋手技能稳定获得一张阵容牌。4级再开秘技牌，能帮助找到韩信。": (
        "Pick Riverlands for Party Bubble and use the Chessplayer Skill every Round to reliably get a Lineup card."
        " Open the Secret Skill Card at Lv. 4 to help find Han Xin.",
        "Pilih Riverlands untuk Party Bubble dan gunakan Skill Chessplayer setiap Ronde untuk pasti mendapat satu"
        " kartu Lineup. Buka Kartu Secret Skill di Lv. 4 untuk membantu menemukan Han Xin."),
    "爆发强，屯几张3阶牌，拿到秘技牌后爆发一波就能提升大量等级。": (
        "Strong bursts: stock up a few Tier 3 cards, and once you get the Secret Skill Card, one burst raises a lot of"
        " Levels.",
        "Ledakan kuat: simpan beberapa kartu Tier 3, dan setelah dapat Kartu Secret Skill, satu ledakan bisa"
        " menaikkan banyak Level."),
    "瑶妹可多提供一个小鹿在前排承伤，前期尽量连胜增强小鹿。": (
        "Yaria provides an extra deer to tank damage in the frontline; try to win streak early to strengthen the deer.",
        "Yaria memberi satu rusa tambahan untuk menahan damage di frontline; usahakan menang beruntun di awal untuk"
        " memperkuat rusa."),
    "瑶妹的小鹿能提供稳定的前排，配合图腾流前期不俗的战力来取得胜利；后期小鹿的等级奉献还能进一步提升图腾全队的等级。": (
        "Yaria's deer gives a steady frontline that, with the Totem Build's strong early power, wins fights; later,"
        " the deer's Level devotion raises the whole Totem team's Levels further.",
        "Rusa Yaria memberi frontline yang stabil, bersama kekuatan awal Build Totem yang lumayan untuk meraih"
        " kemenangan; nanti, Level yang dipersembahkan rusa semakin menaikkan Level seluruh tim Totem."),
    "白歌可以在触发多次合成后，提供场上英雄的同名牌，配合【亚瑟】使用。": (
        "After triggering several Combines, Bai Ge provides Same-Name Cards of Heroes on the board. Use with 【Arthur】.",
        "Setelah memicu beberapa kali Combine, Bai Ge memberi Kartu Bernama Sama dari Hero di papan. Gunakan bersama"
        " 【Arthur】."),
    "白歌可以在触发多次合成后，提供场上英雄的同名牌，配合小乔能更快的提升整体等级。": (
        "After triggering several Combines, Bai Ge provides Same-Name Cards of Heroes on the board. Paired with Xiao"
        " Qiao, it raises overall Levels faster.",
        "Setelah memicu beberapa kali Combine, Bai Ge memberi Kartu Bernama Sama dari Hero di papan. Bersama Xiao"
        " Qiao, Level keseluruhan naik lebih cepat."),
    "这套阵容前期缺前排，瑶妹可多提供一个小鹿在前排承伤。": (
        "This Lineup lacks a frontline early; Yaria provides an extra deer to tank damage in the frontline.",
        "Lineup ini kurang frontline di awal; Yaria memberi satu rusa tambahan untuk menahan damage di frontline."),
    "这套阵容后期缺输出，香香的技能可以提升输出。": (
        "This Lineup lacks damage late; Xiangxiang's Skill adds damage.",
        "Lineup ini kurang damage di akhir; Skill Xiangxiang bisa menambah damage."),
    "配合技能可以快速觉醒猪八戒。": ("With the Skill, Zhu Bajie Awakens quickly.", "Dengan Skill-nya, Zhu Bajie bisa cepat Awaken."),
    "镜可以帮助觉醒需要的英雄。": ("Jing helps Awaken the Heroes you need.", "Jing membantu Awaken Hero yang dibutuhkan."),
    "闹闹的技能可以获得指定阵容的英雄牌，如果有三分之地，可以使阵容更快成型。": (
        "Naonao's Skill gets Hero Cards of a chosen Faction; if Three Kingdoms is in the match, the Lineup comes"
        " together faster.",
        "Skill Naonao bisa mendapat Kartu Hero dari Faction pilihan; jika ada Three Kingdoms, Lineup lebih cepat"
        " terbentuk."),
    "闹闹的技能可以获得指定阵容的英雄牌，如果有大河流域，可以使阵容更快成型。": (
        "Naonao's Skill gets Hero Cards of a chosen Faction; if Riverlands is in the match, the Lineup comes together"
        " faster.",
        "Skill Naonao bisa mendapat Kartu Hero dari Faction pilihan; jika ada Riverlands, Lineup lebih cepat"
        " terbentuk."),
    "闹闹的技能可以获得指定阵容的英雄牌，如果有日落海，可以使阵容更快成型。": (
        "Naonao's Skill gets Hero Cards of a chosen Faction; if Sunset is in the match, the Lineup comes together"
        " faster.",
        "Skill Naonao bisa mendapat Kartu Hero dari Faction pilihan; jika ada Sunset, Lineup lebih cepat terbentuk."),
    "阵容刺客较多，小鹿充阵容坦度。": (
        "The Lineup has many Assassins; the deer adds tankiness.",
        "Lineup ini punya banyak Assassin; rusa menambah ketahanan Lineup."),
    "阿离可以保护C位，可配合狄仁杰使用。": (
        "Arli protects the Carry; pair her with Di Renjie.",
        "Arli melindungi Carry; pasangkan dengan Di Renjie."),
    "阿离的技能可以保护主C。": ("Arli's Skill protects the Main Carry.", "Skill Arli melindungi Main Carry."),

    # ResRecommendLineup and ResHeroStrategyDataBin: Name
    "73无阵营升级": ("Factionless 7×Tier 3", "Factionless 7×Tier 3"),
    "养成科技流": ("Tech Growth Build", "Build Tech Growth"),
    "大河开团韩信": ("Riverlands Initiate Han Xin", "Han Xin Initiate Riverlands"),
    "频繁施法诸葛亮": ("Frequent Casting Kongming", "Kongming Frequent Casting"),
    "阿离开团射": ("Arli Initiate Marksman", "Marksman Initiate Arli"),

    # ResRecommendLineup and ResHeroStrategyDataBin: OperationDetails.Desc
    "1级拿干将和弈星过渡，回合2升2级。": (
        "At Lv. 1 take Gan and Yixing as stopgaps, and level up to 2 in Round 2.",
        "Di Lv. 1 ambil Gan dan Yixing sebagai pengisi sementara, dan naik ke Lv. 2 di Ronde 2."),
    "2级优先找蔡文姬，拿到后再上其它三分牌提战力过渡。刷到大乔就上大乔，赵云的登场效果都可以触发大乔的卡牌效果给她减蓝条，大乔能频繁释放技能。回合5-6升3级。": (
        "At Lv. 2 look for Cai Yan first, then field other Three Kingdoms cards for power as stopgaps. Field Da Qiao"
        " as soon as you roll her: Zilong's Deploy effects trigger Da Qiao's Card Effect to shorten her Mana bar, so"
        " she casts her Skill often. Level up to 3 in Rounds 5-6.",
        "Di Lv. 2 utamakan mencari Cai Yan, lalu turunkan kartu Three Kingdoms lain untuk menambah kekuatan"
        " sementara. Turunkan Da Qiao begitu muncul: efek Deploy Zilong memicu Efek Kartu Da Qiao yang mengurangi bar"
        " Mana-nya, sehingga Da Qiao sering mengeluarkan Skill. Naik ke Lv. 3 di Ronde 5-6."),
    "2级用免费刷新搜几次，有虞姬鬼谷子就拿，没有攒能量，回合5左右升3级再开始搜牌。3级优先找张良，其它位置补开团英雄即可，没有云中君瑶可以先用公孙离。第一次拍卖优先拍张良，第二次拍卖优先拍韩信。": (
        "At Lv. 2 use the free Refreshes to search a few times; take Consort Yu or Guiguzi if they appear, otherwise"
        " save Energy, level up to 3 around Round 5 and then start searching. At Lv. 3 look for Liang first and fill"
        " other slots with Initiate Heroes; without Cirrus or Yaria, use Arli for now. In the first Auction bid for"
        " Liang first; in the second, Han Xin.",
        "Di Lv. 2 gunakan Refresh gratis untuk mencari beberapa kali; ambil Consort Yu atau Guiguzi jika muncul,"
        " kalau tidak, simpan Energy, naik ke Lv. 3 sekitar Ronde 5 lalu mulai mencari kartu. Di Lv. 3 utamakan"
        " mencari Liang dan isi posisi lain dengan Hero Initiate; tanpa Cirrus atau Yaria, pakai Arli dulu. Di Lelang"
        " pertama utamakan Liang; di Lelang kedua, Han Xin."),
    "3级开始刷牌，如果战力低就先拿牌稳血，能打赢就存能量升4级，4级刷3阶牌概率最高，一直在4级刷牌。": (
        "Start rolling at Lv. 3. If your power is low, take cards first to protect your HP; if you can win, save"
        " Energy to reach Lv. 4. Lv. 4 has the best odds for Tier 3 cards, so keep rolling at Lv. 4.",
        "Mulai Refresh di Lv. 3. Jika kekuatan rendah, ambil kartu dulu untuk menjaga HP; jika bisa menang, simpan"
        " Energy untuk naik ke Lv. 4. Lv. 4 punya peluang tertinggi untuk kartu Tier 3, jadi terus Refresh di Lv. 4."),
    "7-8回合左右4级，优先找诸葛亮，大乔蓝条快到10卖掉曹操和赵云上马超。大乔、马超、刘禅、诸葛亮配合能战斗中迅速提升等级。如果有小乔就用小乔配合【登场】英雄牌提升全体等级。太乙可以复活诸葛亮，增加容错。": (
        "Reach Lv. 4 around Rounds 7-8 and look for Kongming first. When Da Qiao's Mana bar is nearly down to 10, sell"
        " Cao Cao and Zilong and field Ma Chao. Da Qiao, Ma Chao, Liu Shan and Kongming together raise Levels quickly"
        " in battle. If you have Xiao Qiao, use her with 【Deploy】 Hero Cards to raise every Hero's Level. Taiyi can"
        " Revive Kongming, giving room for error.",
        "Capai Lv. 4 sekitar Ronde 7-8 dan utamakan mencari Kongming. Saat bar Mana Da Qiao hampir turun ke 10, jual"
        " Cao Cao dan Zilong lalu turunkan Ma Chao. Da Qiao, Ma Chao, Liu Shan, dan Kongming bersama-sama menaikkan"
        " Level dengan cepat dalam Pertempuran. Jika punya Xiao Qiao, pakai dia bersama Kartu Hero 【Deploy】 untuk"
        " menaikkan Level semua Hero. Taiyi bisa Revive Kongming, memberi ruang untuk kesalahan."),
    "刷到太乙先屯一张，决赛换太乙复活主C。": (
        "If you roll Taiyi, keep one in reserve and swap him in for the finals to Revive the Main Carry.",
        "Jika dapat Taiyi, simpan satu dulu dan masukkan dia di final untuk Revive Main Carry."),
    "前期只拿1张弈星，能量够就升级。": (
        "Early on take just 1 Yixing and level up whenever you have enough Energy.",
        "Di awal ambil 1 Yixing saja dan naik level setiap kali Energy cukup."),
    "回合1拿孙尚香和弈星过渡，回合2升2级。": (
        "In Round 1 take Lady Sun and Yixing as stopgaps, and level up to 2 in Round 2.",
        "Di Ronde 1 ambil Lady Sun dan Yixing sebagai pengisi sementara, dan naik ke Lv. 2 di Ronde 2."),
    "回合1有弈星拿弈星，没有空城，回合2升2级，回合3在2级搜牌，芈月、蒙恬、米莱狄必须各一张再升3级。": (
        "In Round 1 take Yixing if he shows up, otherwise leave the board empty. Level up to 2 in Round 2 and search"
        " at Lv. 2 in Round 3: get one each of Mi Yue, Meng Tian and Milady before levelling up to 3.",
        "Di Ronde 1 ambil Yixing jika muncul, kalau tidak, biarkan papan kosong. Naik ke Lv. 2 di Ronde 2 dan cari"
        " kartu di Lv. 2 pada Ronde 3: dapatkan masing-masing satu Mi Yue, Meng Tian, dan Milady sebelum naik ke Lv."
        " 3."),
    "回合2升2级，回合4升3级（第一次拍卖后）。这套阵容核心牌集中在3级，需要快速升级。优先找朵莉亚，其它位置全部用带【整备】关键词的英雄。": (
        "Level up to 2 in Round 2 and to 3 in Round 4 (after the first Auction). This Lineup's key cards are"
        " concentrated at Lv. 3, so level up fast. Look for Dolia first and fill every other slot with Heroes with the"
        " 【Prepare】 keyword.",
        "Naik ke Lv. 2 di Ronde 2 dan ke Lv. 3 di Ronde 4 (setelah Lelang pertama). Kartu inti Lineup ini terkumpul"
        " di Lv. 3, jadi naik level dengan cepat. Utamakan mencari Dolia dan isi semua posisi lain dengan Hero"
        " ber-keyword 【Prepare】."),
    "回合3升2级，前期拿产古币的英雄【李元芳】和【盾山】。可以搜到李元芳觉醒后再升3级。": (
        "Level up to 2 in Round 3 and take the Ancient Coin producers 【Fang】 and 【Dunshan】 early. You can wait until"
        " Fang Awakens before levelling up to 3.",
        "Naik ke Lv. 2 di Ronde 3 dan ambil penghasil Ancient Coin 【Fang】 dan 【Dunshan】 di awal. Kamu bisa menunggu"
        " sampai Fang Awaken sebelum naik ke Lv. 3."),
    "回合4-7可以在3级把芈月搜到觉醒，顺便找苍、西施、白起。芈月觉醒以后再升4级。西施拿到后每回合战术牌给蒙恬用，减少蒙恬蓝量快速释放技能召唤小兵。": (
        "In Rounds 4-7 you can stay at Lv. 3 until Mi Yue Awakens, picking up Chano, Shi and Bai Qi along the way."
        " Level up to 4 only after Mi Yue Awakens. Once you have Shi, use Tactics Cards on Meng Tian every Round to"
        " cut his Mana so he casts his Skill fast and Summons soldiers.",
        "Di Ronde 4-7 kamu bisa bertahan di Lv. 3 sampai Mi Yue Awaken, sambil mencari Chano, Shi, dan Bai Qi. Naik"
        " ke Lv. 4 setelah Mi Yue Awaken. Setelah dapat Shi, gunakan Tactics Card pada Meng Tian setiap Ronde untuk"
        " mengurangi Mana-nya agar cepat mengeluarkan Skill dan Summon prajurit."),
    "回合5升3级，升级后主要找张良，上阵交锋英雄配合张良词条升级。有图腾英雄也继续购买。": (
        "Level up to 3 in Round 5, then look mainly for Liang; field Clash Heroes to level up with Liang's Trait. Keep"
        " buying Totem Heroes too.",
        "Naik ke Lv. 3 di Ronde 5, lalu cari terutama Liang; turunkan Hero Clash untuk naik level bersama Trait"
        " Liang. Terus beli Hero Totem juga."),
    "回合5升3级，升级后优先找【狄仁杰】，找到后继续拿其它可产古币的英雄牌，产出古币全部给狄仁杰养单C。": (
        "Level up to 3 in Round 5, then look for 【Di Renjie】 first; after that keep taking other Hero Cards that"
        " produce Ancient Coins and give all the Ancient Coins to Di Renjie as the single Carry.",
        "Naik ke Lv. 3 di Ronde 5, lalu utamakan mencari 【Di Renjie】; setelah itu terus ambil Kartu Hero lain yang"
        " menghasilkan Ancient Coin dan berikan semua Ancient Coin ke Di Renjie sebagai Carry tunggal."),
    "回合8-11升4级，拿一张太乙复活蒙恬，剩下位置可以放任意产战术牌的英雄，靠战术牌触发芈月的卡牌效果，给蒙恬升级。": (
        "Level up to 4 in Rounds 8-11 and take a Taiyi to Revive Meng Tian. Fill the remaining slots with any Heroes"
        " that produce Tactics Cards; Tactics Cards trigger Mi Yue's Card Effect to level up Meng Tian.",
        "Naik ke Lv. 4 di Ronde 8-11 dan ambil satu Taiyi untuk Revive Meng Tian. Isi posisi sisa dengan Hero apa pun"
        " yang menghasilkan Tactics Card; Tactics Card memicu Efek Kartu Mi Yue untuk menaikkan Level Meng Tian."),
    "回合8升4级，升级后主要找【上官婉儿】，固定产出古币。回合12升5级，升级后找武则天，增加古币质量。": (
        "Level up to 4 in Round 8, then look mainly for 【Shangguan】, who produces Ancient Coins every Round. Level up"
        " to 5 in Round 12, then find Wu Zetian to improve your Ancient Coins' quality.",
        "Naik ke Lv. 4 di Ronde 8, lalu cari terutama 【Shangguan】, yang menghasilkan Ancient Coin setiap Ronde. Naik"
        " ke Lv. 5 di Ronde 12, lalu cari Wu Zetian untuk meningkatkan kualitas Ancient Coin."),
    "回合8升4级，找核心输出蒙犽，顺便搜能提供战术牌的英雄，通过不断使用战术牌提升蒙犽等级。": (
        "Level up to 4 in Round 8 and find the core damage dealer Meng Ya, searching along the way for Heroes that"
        " provide Tactics Cards; keep using Tactics Cards to raise Meng Ya's Level.",
        "Naik ke Lv. 4 di Ronde 8 dan cari damage dealer inti Meng Ya, sambil mencari Hero yang memberi Tactics Card;"
        " terus gunakan Tactics Card untuk menaikkan Level Meng Ya."),
    "回合8升4级，继续提升战力，补充带【整备】关键词的英雄。": (
        "Level up to 4 in Round 8, keep building power and add more Heroes with the 【Prepare】 keyword.",
        "Naik ke Lv. 4 di Ronde 8, terus tambah kekuatan dan lengkapi Hero ber-keyword 【Prepare】."),
    "回合8升4级，继续补充图腾英雄和交锋英雄。回合12升5级，升级后主要找东皇，东皇回血能量强大是最强的前排。没有东皇可以先培养大司命。": (
        "Level up to 4 in Round 8 and keep adding Totem and Clash Heroes. Level up to 5 in Round 12, then look mainly"
        " for Donghuang: his strong healing makes him the best frontline. Without Donghuang, build up Augran for now.",
        "Naik ke Lv. 4 di Ronde 8 dan terus tambah Hero Totem dan Hero Clash. Naik ke Lv. 5 di Ronde 12, lalu cari"
        " terutama Donghuang: pemulihan HP-nya yang kuat menjadikannya frontline terbaik. Tanpa Donghuang, besarkan"
        " Augran dulu."),
    "回合8升4级，继续补充图腾英雄和交锋英雄。回合12升5级，升级后主要找东皇，东皇回血能量强大是最强的前排。没有东皇可以先培养大司命。敖隐来了以后可以换敖隐当主C，场上图腾全部放最后排战斗中持续给敖隐加等级。": (
        "Level up to 4 in Round 8 and keep adding Totem and Clash Heroes. Level up to 5 in Round 12, then look mainly"
        " for Donghuang: his strong healing makes him the best frontline. Without Donghuang, build up Augran for now."
        " Once Ao'yin arrives, you can make him the Main Carry; put every Totem on the back row so they keep giving"
        " Ao'yin Levels in battle.",
        "Naik ke Lv. 4 di Ronde 8 dan terus tambah Hero Totem dan Hero Clash. Naik ke Lv. 5 di Ronde 12, lalu cari"
        " terutama Donghuang: pemulihan HP-nya yang kuat menjadikannya frontline terbaik. Tanpa Donghuang, besarkan"
        " Augran dulu. Setelah Ao'yin datang, kamu bisa menjadikannya Main Carry; taruh semua Totem di baris paling"
        " belakang agar terus memberi Level ke Ao'yin dalam Pertempuran."),
    "回合8升到4级开始搜韩信，其它位置补开团英雄，血量低就4级梭哈搜牌。": (
        "Reach Lv. 4 in Round 8 and start searching for Han Xin, filling other slots with Initiate Heroes. If HP is"
        " low, go all in on rolling at Lv. 4.",
        "Capai Lv. 4 di Ronde 8 dan mulai cari Han Xin, isi posisi lain dengan Hero Initiate. Jika HP rendah,"
        " habiskan semua Energy untuk Refresh di Lv. 4."),

    # ResRecommendLineup and ResHeroStrategyDataBin: PositionDesc
    "吕布可以提供吸血效果，两侧放阵容里输出最强的英雄，增强英雄的生存能力。": (
        "Lu Bu provides Lifesteal: flank him with the Lineup's strongest damage dealers to improve their survival.",
        "Lu Bu memberi Lifesteal: taruh Hero dengan damage terkuat di Lineup di kedua sisinya untuk meningkatkan daya"
        " tahan mereka."),
    "小明牵裴擒虎，觉醒小明后每回合能保留裴擒虎很多等级。刺客两侧站位抓对方C位。": (
        "Link Ming to Pei: once Ming Awakens, Pei keeps many of his Levels each Round. Place Assassins on the flanks"
        " to dive the enemy Carry.",
        "Hubungkan Ming ke Pei: setelah Ming Awaken, Pei menyimpan banyak Level-nya setiap Ronde. Taruh Assassin di"
        " sisi kiri dan kanan untuk menyerang Carry lawan."),
    "李元芳和狄仁杰放在一起，触发李元芳卡牌效果（李元芳周围不要放其它英雄，其英雄效果只对最近英雄生效）。": (
        "Place Fang next to Di Renjie to trigger Fang's Card Effect (put no other Heroes around Fang; his Hero Effect"
        " only works on the nearest Hero).",
        "Taruh Fang bersebelahan dengan Di Renjie untuk memicu Efek Kartu Fang (jangan taruh Hero lain di sekitar"
        " Fang; Efek Hero-nya hanya berlaku untuk Hero terdekat)."),
    "蒙恬牺牲可以召唤小兵，太乙连蒙恬，蒙恬复活后再次牺牲召唤小兵。": (
        "Meng Tian Summons soldiers when he Sacrifices. Link Taiyi to Meng Tian so that after he Revives he Sacrifices"
        " again and Summons more soldiers.",
        "Meng Tian bisa Summon prajurit saat Sacrifice. Hubungkan Taiyi ke Meng Tian agar setelah Revive dia"
        " Sacrifice lagi dan Summon prajurit lagi."),
    "蔡文姬放中间给周围英雄回血。": (
        "Put Cai Yan in the middle to heal the Heroes around her.",
        "Taruh Cai Yan di tengah untuk memulihkan HP Hero di sekitarnya."),
    "韩信需要切对面主C，预测对手位置来灵活调整站位。太乙放韩信旁边复活韩信。瑶放韩信旁边给他加属性。": (
        "Han Xin has to dive the enemy Main Carry, so predict where the opponent will be and adjust your placement."
        " Put Taiyi beside Han Xin to Revive him, and Yaria beside him to boost his stats.",
        "Han Xin harus menyerang Main Carry lawan, jadi tebak posisi lawan dan sesuaikan penempatan. Taruh Taiyi di"
        " samping Han Xin untuk Revive dia, dan Yaria di sampingnya untuk menambah atributnya."),

    # ResRecommendLineup and ResHeroStrategyDataBin: PreviewHeroes.Desc, OperationDetails.MainHeroIDs.Desc
    "功能英雄，依靠不断使用【出击】英雄牌提升整体等级": (
        "Utility Hero; keep playing 【Strike】 Hero Cards to raise overall Levels",
        "Hero utilitas; terus mainkan Kartu Hero 【Strike】 untuk menaikkan Level keseluruhan"),
    "功能英雄，依靠不断使用【战术牌】来增加C位等级": (
        "Utility Hero; keep using 【Tactics Cards】 to raise the Carry's Level",
        "Hero utilitas; terus gunakan 【Tactics Card】 untuk menaikkan Level Carry"),
    "功能英雄，每个回合固定产出古币": (
        "Utility Hero; produces Ancient Coins every Round",
        "Hero utilitas; menghasilkan Ancient Coin setiap Ronde"),
    "功能英雄，配合交锋英雄提升整体等级": (
        "Utility Hero; raises overall Levels with Clash Heroes",
        "Hero utilitas; menaikkan Level keseluruhan bersama Hero Clash"),
    "核心坦克，且提供吸血效果": ("Core tank, also provides Lifesteal", "Tank core, juga memberi Lifesteal"),
    "核心输出，依靠不断对狄仁杰使用古币增加攻速和提升等级": (
        "Core output; keep using Ancient Coins on Di Renjie to raise his Attack Speed and Level",
        "Output core; terus gunakan Ancient Coin pada Di Renjie untuk menaikkan Attack Speed dan Level-nya"),
    "核心输出，同时词条可以配合图腾英雄提升整体等级": (
        "Core output; its Trait also works with Totem Heroes to raise overall Levels",
        "Output core; Trait-nya juga bekerja bersama Hero Totem untuk menaikkan Level keseluruhan"),

    # ResRecommendLineup: Provider (the lineup author's nickname)
    "坦率的陶艺师": ("Candid Potter", "Perajin Tembikar Jujur"),

    # ResRecommendLineup and ResHeroStrategyDataBin: SimpleDesc
    "7张3阶牌，核心猪八戒，3阶英雄合成时触发猪八戒的卡牌效果，给全体3阶英雄升级。除了猪八戒最优裴擒虎、阿轲、小明，剩下3个位置补任意3阶英雄。": (
        "7 Tier 3 cards with Zhu Bajie at the core: when a Tier 3 Hero Combines, Zhu Bajie's Card Effect levels up"
        " every Tier 3 Hero. Besides Zhu Bajie, Pei, Arke and Ming are best; fill the remaining 3 slots with any Tier"
        " 3 Heroes.",
        "7 kartu Tier 3 dengan Zhu Bajie sebagai inti: saat Hero Tier 3 di-Combine, Efek Kartu Zhu Bajie menaikkan"
        " Level semua Hero Tier 3. Selain Zhu Bajie, Pei, Arke, dan Ming adalah pilihan terbaik; isi 3 posisi sisa"
        " dengan Hero Tier 3 apa pun."),
    "C位狄仁杰，上阵后不断对狄仁杰使用古币牌增加攻速。其它英雄选能获取古币牌的英雄即可。": (
        "Di Renjie is the Carry: once he is on the board, keep using Ancient Coin Cards on him to raise his Attack"
        " Speed. For the other slots, any Heroes that get Ancient Coin Cards will do.",
        "Di Renjie adalah Carry: setelah dia di papan, terus gunakan Kartu Ancient Coin padanya untuk menaikkan"
        " Attack Speed. Untuk posisi lain, cukup pilih Hero yang bisa mendapat Kartu Ancient Coin."),
    "关键牌张良和韩信，其它位置全拿带开团关键词的英雄，【开团】触发张良和韩信的卡牌效果提升等级。前期虞姬稳血，后期主C韩信输出高控制能力强。": (
        "Liang and Han Xin are the key cards; fill every other slot with Heroes with the Initiate keyword, since"
        " 【Initiate】 triggers Liang's and Han Xin's Card Effects to raise Levels. Early on Consort Yu protects your"
        " HP; late, Main Carry Han Xin deals high damage with strong control.",
        "Liang dan Han Xin adalah kartu kunci; isi semua posisi lain dengan Hero ber-keyword Initiate, karena"
        " 【Initiate】 memicu Efek Kartu Liang dan Han Xin untuk menaikkan Level. Di awal Consort Yu menjaga HP; di"
        " akhir, Main Carry Han Xin memberi damage tinggi dengan kontrol kuat."),
    "功能英雄小乔，小乔上阵后不断使用【登场】英雄牌提升整体英雄等级。前期核心输出赵云，后期可以转吕布或者周瑜，装备给主C。": (
        "Xiao Qiao is the utility Hero: once she is on the board, keep playing 【Deploy】 Hero Cards to raise every"
        " Hero's Level. Zilong is the early core damage dealer; later you can switch to Lu Bu or Zhou Yu. Give"
        " Equipment to the Main Carry.",
        "Xiao Qiao adalah Hero utilitas: setelah dia di papan, terus mainkan Kartu Hero 【Deploy】 untuk menaikkan"
        " Level semua Hero. Zilong adalah damage dealer inti di awal; nanti bisa beralih ke Lu Bu atau Zhou Yu."
        " Berikan Equipment ke Main Carry."),
    "功能英雄芈月，上阵后使用战术牌触发卡牌效果，给装备最多的英雄升级。输出英雄优先蒙犽，其它位置拿任意可产出战术牌的英雄。": (
        "Mi Yue is the utility Hero: once she is on the board, Tactics Cards trigger her Card Effect and level up the"
        " Hero with the most Equipment. Meng Ya is the preferred damage dealer; fill the other slots with any Heroes"
        " that produce Tactics Cards.",
        "Mi Yue adalah Hero utilitas: setelah dia di papan, Tactics Card memicu Efek Kartu-nya dan menaikkan Level"
        " Hero dengan Equipment terbanyak. Meng Ya adalah damage dealer utama; isi posisi lain dengan Hero apa pun"
        " yang menghasilkan Tactics Card."),
    "核心英雄虞姬，找到虞姬后，凑齐三个图腾英雄，触发虞姬词条升级。次级核心张良，找到张良后，尽量多上交锋英雄，提升等级。": (
        "Consort Yu is the core Hero: once you have her, gather three Totem Heroes to trigger her Trait and level up."
        " Liang is the second core: once you have him, field as many Clash Heroes as you can to raise Levels.",
        "Consort Yu adalah Hero inti: setelah mendapatkannya, kumpulkan tiga Hero Totem untuk memicu Trait-nya dan"
        " naik level. Liang adalah inti kedua: setelah mendapatkannya, turunkan Hero Clash sebanyak mungkin untuk"
        " menaikkan Level."),
    "蒙恬和米莱狄都能召唤小兵，苍可以让小兵阵亡时产生爆炸伤害，召唤小兵越多伤害越爆炸。蒙恬召唤的小兵和自身等级相关，用芈月来提升蒙恬的等级。米莱狄每回合固定提升召唤物等级，一定要尽早拿到。": (
        "Meng Tian and Milady both Summon soldiers, and Chano makes soldiers explode for damage when they fall: the"
        " more soldiers you Summon, the bigger the blasts. The soldiers Meng Tian Summons scale with his own Level, so"
        " use Mi Yue to raise it. Milady raises the Level of summons every Round, so get her as early as possible.",
        "Meng Tian dan Milady sama-sama bisa Summon prajurit, dan Chano membuat prajurit meledak dan memberi damage"
        " saat gugur: makin banyak prajurit yang di-Summon, makin besar ledakannya. Prajurit yang di-Summon Meng Tian"
        " mengikuti Level-nya sendiri, jadi gunakan Mi Yue untuk menaikkan Level Meng Tian. Milady menaikkan Level"
        " summon setiap Ronde, jadi dapatkan dia secepat mungkin."),
    "阵容养成核心在于英雄释放技能。大乔配合马超能快速释放技能，让诸葛亮和刘禅在战斗中迅速提升等级，诸葛亮无限放大。有【换帅】先屯一张，来了关键英雄后把前期过渡英雄的等级换给关键英雄。": (
        "This Lineup grows through Heroes casting Skills. Da Qiao with Ma Chao casts Skills fast, letting Kongming and"
        " Liu Shan level up quickly in battle so Kongming can cast endlessly. Keep a 【Change of Commander】 in reserve,"
        " and once the key Heroes arrive, swap your early stopgap Heroes' Levels onto them.",
        "Lineup ini tumbuh lewat Hero yang mengeluarkan Skill. Da Qiao bersama Ma Chao bisa cepat mengeluarkan Skill,"
        " membuat Kongming dan Liu Shan cepat naik Level dalam Pertempuran sehingga Kongming bisa terus mengeluarkan"
        " Skill. Simpan satu 【Pergantian Komandan】, dan setelah Hero kunci datang, pindahkan Level Hero pengisi"
        " sementara dari awal ke mereka."),

    # ResHeroStrategyDataBin: Title (test rows)
    "小妲己测试": ("Little Daji Test", "Tes Little Daji"),
    "瑶妹测试": ("Yaria Test", "Tes Yaria"),

    # Card, talent and skill texts 1.7.0.1 added or reworded.
    "<a href=11><color=#ffffff>╬<b>整备</b></color></a>：对距离最近的【河洛】英雄使用2张<color=#ffffff><b>古币</b></color>。": (
        "<a href=11><color=#ffffff>╬<b>Prepare</b></color></a>: Use 2 <color=#ffffff><b>Ancient Coins</b></color> on the"
        " nearest [Central Plains] Hero.",
        "<a href=11><color=#ffffff>╬<b>Prepare</b></color></a>: Gunakan 2 <color=#ffffff><b>Ancient Coin</b></color> pada"
        " Hero [Central Plains] terdekat."),
    "<a href=3130012><color=#99DEB0>╆转瞬</color></a>\n指定<color=#99DEB0>1名低于5阶</color>的英雄═临时等级<color=#99DEB0>+65</color>。若战斗胜利，将永久获得此等级。若战斗失败/平局，则获得一半。": (
        "<a href=3130012><color=#99DEB0>╆Fleeting</color></a>\nTarget <color=#99DEB0>1 Hero below Tier 5</color> to gain"
        " ═Temporary Level <color=#99DEB0>+65</color>. If you win the Battle, this Level becomes permanent. If you"
        " lose/draw, gain half.",
        "<a href=3130012><color=#99DEB0>╆Fleeting</color></a>\nTargetkan <color=#99DEB0>1 Hero di bawah Tier 5</color>"
        " untuk mendapat ═Temporary Level <color=#99DEB0>+65</color>. Jika kamu memenangkan Pertempuran, Level ini"
        " menjadi permanen. Jika kalah/seri, dapatkan setengahnya."),
    "<a href=3><color=#ffffff>╪<b>开团</b></color></a>：场上每有1个<a href=321><color=#ffffff>╉<b>图腾</b></color></a>，自身及随机2名不同己方英雄等级+1。": (
        "<a href=3><color=#ffffff>╪<b>Initiate</b></color></a>: For every <a href=321><color=#ffffff>╉<b>Totem</b></color></a>"
        " on the board, this Hero and 2 random different allied Heroes gain +1 Level.",
        "<a href=3><color=#ffffff>╪<b>Initiate</b></color></a>: Untuk setiap <a href=321><color=#ffffff>╉<b>Totem</b></color></a>"
        " di papan, Hero ini dan 2 Hero ally berbeda secara acak mendapatkan +1 Level."),
    "<a href=3><color=#ffffff>╪<b>开团</b></color></a>：场上每有1个<a href=321><color=#ffffff>╉<b>图腾</b></color></a>，自身及随机4名不同己方英雄等级+1。": (
        "<a href=3><color=#ffffff>╪<b>Initiate</b></color></a>: For every <a href=321><color=#ffffff>╉<b>Totem</b></color></a>"
        " on the board, this Hero and 4 random different allied Heroes gain +1 Level.",
        "<a href=3><color=#ffffff>╪<b>Initiate</b></color></a>: Untuk setiap <a href=321><color=#ffffff>╉<b>Totem</b></color></a>"
        " di papan, Hero ini dan 4 Hero ally berbeda secara acak mendapatkan +1 Level."),
    "<a href=3><color=#ffffff>╪<b>开团</b></color></a>：距离最近的4名己方英雄获得装备<color=#ffffff><b>玄微之种</b></color>。": (
        "<a href=3><color=#ffffff>╪<b>Initiate</b></color></a>: The 4 nearest allied Heroes gain the"
        " <color=#ffffff><b>Seed of Xuanwei</b></color> Equipment.",
        "<a href=3><color=#ffffff>╪<b>Initiate</b></color></a>: 4 Hero ally terdekat mendapat Equipment"
        " <color=#ffffff><b>Seed of Xuanwei</b></color>."),
    "<color=#99DEB0>╥阿科米亚核心</color>等级<color=#99DEB0>+200</color>。场上英雄升级时，<color=#99DEB0>╥阿科米亚核心</color>会获得<color=#99DEB0>60%</color>的等级（仅真实等级）。": (
        "<color=#99DEB0>╥Arcomia Core</color> Level <color=#99DEB0>+200</color>. When Heroes on the field gain Levels,"
        " <color=#99DEB0>╥Arcomia Core</color> gains <color=#99DEB0>60%</color> of those Levels (actual Levels only).",
        "<color=#99DEB0>╥Arcomia Core</color> Level <color=#99DEB0>+200</color>. Saat Hero di papan naik Level,"
        " <color=#99DEB0>╥Arcomia Core</color> mendapatkan <color=#99DEB0>60%</color> dari Level tersebut (hanya Level"
        " asli)."),
    "<color=#99DEB0>召唤╉图腾</color>，己方所有【大河】英雄获得相当于<a><color=#99DEB0>╉<b>图腾</b></color></a>等级<color=#99DEB0>50%</color>的<a>═临时等级</a>。": (
        "<color=#99DEB0>Summon a ╉Totem</color>. All your [Riverlands] Heroes gain the"
        " <a><color=#99DEB0>╉<b>Totem</b></color></a>'s Level × <color=#99DEB0>50%</color> as <a>═Temporary Level</a>.",
        "<color=#99DEB0>Summon ╉Totem</color>. Semua Hero [Riverlands] kamu mendapatkan Level"
        " <a><color=#99DEB0>╉<b>Totem</b></color></a> × <color=#99DEB0>50%</color> sebagai <a>═Temporary Level</a>."),
    "<color=#ffffff><b>唯一</b></color>。释放技能时，<color=#ffffff>35%概率重复释放一次</color>。每有7级，额外提升1%概率。近战英雄总上限70%。": (
        "<color=#ffffff><b>Unique</b></color>. When casting a Skill, there is a <color=#ffffff>35% chance to cast it"
        " again</color>. For every 7 levels, the chance increases by an additional 1%. Melee Heroes are capped at 70%.",
        "<color=#ffffff><b>Unique</b></color>. Saat memakai Skill, ada <color=#ffffff>peluang 35% untuk memakainya"
        " lagi</color>. Setiap 7 level, peluang bertambah 1%. Batas total Hero Melee 70%."),
    "释放技能时，<color=#ffffff>35%概率重复释放一次</color>。每有7级，额外提升1%概率。近战英雄总上限70%。": (
        "When casting a Skill, there is a <color=#ffffff>35% chance to cast it again</color>. The chance increases by 1%"
        " for every 7 levels. Melee Heroes are capped at 70%.",
        "Saat memakai Skill, ada <color=#ffffff>peluang 35% untuk memakainya lagi</color>. Peluangnya naik 1% setiap 7"
        " level. Batas total Hero Melee 70%."),
    "<color=#ffffff><b>唯一</b></color>，<color=#ffffff><b>限定远程英雄</b></color>。普通攻击会释放飞箭，对生命值最低的2名敌人造成<color=#ffffff>55%物理攻击力的物理伤害</color>。": (
        "<color=#ffffff><b>Unique</b></color>, <color=#ffffff><b>Ranged Heroes Only</b></color>. Basic attacks fire"
        " arrows, dealing <color=#ffffff>55% Physical Attack as Physical Damage</color> to the 2 enemies with the lowest"
        " Health.",
        "<color=#ffffff><b>Unique</b></color>, <color=#ffffff><b>Khusus Hero Ranged</b></color>. Basic Attack"
        " menembakkan panah, memberikan <color=#ffffff>Physical Damage sebesar 55% Physical Attack</color> ke 2 musuh"
        " dengan Health terendah."),
    "普通攻击会释放飞箭，对生命值最低的2名敌人造成<color=#ffffff>55%物理攻击力的物理伤害</color>。": (
        "Basic attacks fire arrows, dealing <color=#ffffff>55% Physical Attack as Physical Damage</color> to the 2"
        " enemies with the lowest Health.",
        "Basic Attack menembakkan panah, memberikan <color=#ffffff>Physical Damage sebesar 55% Physical Attack</color>"
        " ke 2 musuh dengan Health terendah."),
    "<color=#ffffffbf>被动：</color>冲锋并戳刺造成<color=#dfa15e>物理伤害</color>。\n<color=#ffffffbf>主动：</color>获得伤害加成。": (
        "<color=#ffffffbf>Passive:</color> Charges and thrusts, dealing <color=#dfa15e>Physical Damage</color>.\n"
        "<color=#ffffffbf>Active:</color> Gains a Damage bonus.",
        "<color=#ffffffbf>Pasif:</color> Menyerbu dan menusuk, memberikan <color=#dfa15e>Physical Damage</color>.\n"
        "<color=#ffffffbf>Aktif:</color> Mendapatkan bonus Damage."),
    "<color=#ffffffbf>被动：</color>圣殿骑士每次冲锋后进行戳刺，造成<color=#dfa15e>[0]点物理伤害</color><color=#dfa15e>（[1]+[2]%自身最大生命值）</color>。\n<color=#ffffffbf>主动：</color>获得15%伤害加成，持续5秒。": (
        "<color=#ffffffbf>Passive:</color> After each Charge, the Templar thrusts, dealing <color=#dfa15e>[0] Physical"
        " Damage</color><color=#dfa15e> ([1]+[2]% of its own Max HP)</color>.\n<color=#ffffffbf>Active:</color> Gains a"
        " 15% Damage bonus for 5 seconds.",
        "<color=#ffffffbf>Pasif:</color> Setelah setiap Charge, Templar menusuk, memberikan <color=#dfa15e>[0] Physical"
        " Damage</color><color=#dfa15e> ([1]+[2]% Max HP-nya sendiri)</color>.\n<color=#ffffffbf>Aktif:</color>"
        " Mendapatkan bonus Damage 15% selama 5 detik."),
    "<color=#ffffffbf>被动：</color>马超靠近冷晖枪时会拾取回收，同时<color=#9ff5d0>恢复自身100+75%物理攻击力的生命值</color>，并提升<color=#dfa15e>5点物理攻击力</color>。\n<color=#ffffffbf>主动：</color>马超立即<color=#9ff5d0>恢复自身100点生命值</color>，快速突袭至3格内最远的敌人身边，对其造成<color=#dfa15e>50+100%物理攻击力的物理伤害</color>并留下1把冷晖枪。": (
        "<color=#ffffffbf>Passive:</color> When Ma Chao approaches a Cold Dawn Spear, he retrieves it,"
        " <color=#9ff5d0>restoring 100+75% Physical Attack as Health</color> and gaining <color=#dfa15e>5 Physical"
        " Attack</color>.\n<color=#ffffffbf>Active:</color> Ma Chao immediately <color=#9ff5d0>restores 100"
        " Health</color>, rushes to the farthest enemy within 3 tiles, deals <color=#dfa15e>50+100% Physical Attack as"
        " Physical Damage</color> to it, and leaves behind 1 Cold Dawn Spear.",
        "<color=#ffffffbf>Pasif:</color> Saat Ma Chao mendekati Cold Dawn Spear, ia mengambilnya kembali,"
        " <color=#9ff5d0>memulihkan Health sebesar 100+75% Physical Attack</color> dan mendapatkan <color=#dfa15e>5"
        " Physical Attack</color>.\n<color=#ffffffbf>Aktif:</color> Ma Chao langsung <color=#9ff5d0>memulihkan 100"
        " Health</color>, menyerbu ke musuh terjauh dalam 3 petak, memberikan <color=#dfa15e>Physical Damage sebesar"
        " 50+100% Physical Attack</color>, dan meninggalkan 1 Cold Dawn Spear."),
    "╥阿科米亚核心不再分配等级。每秒对1个随机敌方单位造成<color=#FFE897>6次核心等级×1</color>的法术伤害。每击败1名敌方英雄，阿科米亚核心获得自身1%的等级成长。": (
        "╥Arcomia Core no longer distributes Levels. Every second, it deals <color=#FFE897>6 hits of Magic Damage equal"
        " to Core Level × 1</color> to a random enemy unit. For each enemy Hero defeated, Arcomia Core grows by 1% of"
        " its own Level.",
        "╥Arcomia Core tidak lagi membagikan Level. Setiap detik, Core memberikan <color=#FFE897>6 kali Magic Damage"
        " sebesar Level Core × 1</color> ke 1 unit musuh acak. Setiap 1 Hero musuh dikalahkan, Level Arcomia Core"
        " tumbuh 1% dari Level-nya sendiri."),
    "上阵6个所选阵营英雄时，获得1张<color=#FFE897>朋友多多</color>。\n<color=#FFE897>朋友多多</color>：随机获得5张技能所选阵营的英雄牌。": (
        "When you deploy 6 Heroes of the chosen Faction, gain 1 <color=#FFE897>Lots of Friends</color>.\n"
        "<color=#FFE897>Lots of Friends</color>: randomly gain 5 Hero Cards of the Faction chosen by the Skill.",
        "Saat kamu menurunkan 6 Hero dari Faction yang dipilih, dapatkan 1 <color=#FFE897>Lots of Friends</color>.\n"
        "<color=#FFE897>Lots of Friends</color>: dapatkan 5 Kartu Hero acak dari Faction yang dipilih oleh Skill."),
    "你在战斗过程中<color=#FFE897>╧复生</color>的英雄，获得200%攻速、100%暴击率和70%伤害减免，持续1.5秒。": (
        "Heroes that <color=#FFE897>╧Revive</color> during combat gain 200% Attack Speed, 100% Crit Rate and 70% Damage"
        " Reduction for 1.5 seconds.",
        "Hero yang <color=#FFE897>╧Revive</color> selama pertempuran mendapatkan 200% Attack Speed, 100% Crit Rate, dan"
        " 70% Damage Reduction selama 1,5 detik."),
    "你的<a href=321><color=#99DEB0>╉图腾</color></a>获得额外效果。\n<a href=324><color=#99DEB0>╉先知图腾</color></a>：友方英雄阵亡时，其等级的70%会作为<a href=3130011><color=#99DEB0>═临时等级</color></a>分配给己方等级最低的英雄。\n<a href=322><color=#99DEB0>╉往生图腾</color></a>：己方全体英雄物理及法术防御<color=#99DEB0>+15</color>。\n<a href=323><color=#99DEB0>╉因缘图腾</color></a>：己方全体英雄普攻<color=#99DEB0>2次</color>或释放技能时，等级<color=#99DEB0>+2</color>。": (
        "Your <a href=321><color=#99DEB0>╉Totem</color></a> gains extra effects.\n<a href=324><color=#99DEB0>╉Seer"
        " Totem</color></a>: When an allied Hero is Defeated, 70% of their Level is distributed as <a href=3130011>"
        "<color=#99DEB0>═Temporary Level</color></a> to the allied Hero with the lowest Level.\n<a href=322>"
        "<color=#99DEB0>╉Afterlife Totem</color></a>: All allied Heroes gain <color=#99DEB0>+15</color> Physical and"
        " Magic Defense.\n<a href=323><color=#99DEB0>╉Destiny Totem</color></a>: Each time an allied Hero performs"
        " <color=#99DEB0>2</color> basic attacks or casts a Skill, its Level <color=#99DEB0>+2</color>.",
        "<a href=321><color=#99DEB0>╉Totem</color></a> kamu mendapatkan efek tambahan.\n<a href=324><color=#99DEB0>╉Seer"
        " Totem</color></a>: Saat Hero ally dikalahkan, 70% Level-nya dibagikan sebagai <a href=3130011>"
        "<color=#99DEB0>═Temporary Level</color></a> ke Hero ally dengan Level terendah.\n<a href=322>"
        "<color=#99DEB0>╉Afterlife Totem</color></a>: Semua Hero ally mendapatkan <color=#99DEB0>+15</color> Physical"
        " dan Magic Defense.\n<a href=323><color=#99DEB0>╉Destiny Totem</color></a>: Setiap kali Hero ally melakukan"
        " <color=#99DEB0>2</color> basic attack atau memakai Skill, Level-nya <color=#99DEB0>+2</color>."),
    "你的【日落海】英雄每提升<color=#99DEB0>10级</color>，<color=#99DEB0>╥阿科米亚核心</color>获得<color=#99DEB0>4等级</color>。\n【日落海】英雄首次≥<color=#99DEB0>6名</color>时：获得<color=#99DEB0>2张</color>【远洋宝藏】；保持≥<color=#99DEB0>6名</color>时，每穿戴<color=#99DEB0>1件</color>【日落海专属装备】，<color=#99DEB0>╬整备额外触发1次</color>。\n【日落海】英雄≥<color=#99DEB0>8名</color>时：每回合战斗开始，随机召唤<color=#99DEB0>1名</color>与<color=#99DEB0>╥阿科米亚核心</color>同等级的【日落海】英雄（等级上限999）。": (
        "For every <color=#99DEB0>10 Levels</color> your [Sunset] Heroes gain, <color=#99DEB0>╥Arcomia Core</color>"
        " gains <color=#99DEB0>4 Levels</color>.\nWhen you first have ≥<color=#99DEB0>6</color> [Sunset] Heroes: gain"
        " <color=#99DEB0>2</color> [Ocean Treasure]. While you keep ≥<color=#99DEB0>6</color>, for each"
        " <color=#99DEB0>1</color> [Sunset Exclusive Equipment] worn, <color=#99DEB0>╬Prepare triggers 1 extra"
        " time</color>.\nWith ≥<color=#99DEB0>8</color> [Sunset] Heroes: at the start of each Round's Battle, randomly"
        " Summon <color=#99DEB0>1</color> [Sunset] Hero with the same Level as <color=#99DEB0>╥Arcomia Core</color>"
        " (Level capped at 999).",
        "Setiap kali Hero [Sunset] kamu naik <color=#99DEB0>10 Level</color>, <color=#99DEB0>╥Arcomia Core</color>"
        " mendapatkan <color=#99DEB0>4 Level</color>.\nSaat jumlah Hero [Sunset] pertama kali ≥<color=#99DEB0>6</color>:"
        " dapatkan <color=#99DEB0>2</color> [Ocean Treasure]. Selama tetap ≥<color=#99DEB0>6</color>, untuk setiap"
        " <color=#99DEB0>1</color> [Sunset Exclusive Equipment] yang dipakai, <color=#99DEB0>╬Prepare terpicu 1 kali"
        " tambahan</color>.\nDengan ≥<color=#99DEB0>8</color> Hero [Sunset]: di awal Pertempuran setiap Ronde, Summon"
        " <color=#99DEB0>1</color> Hero [Sunset] acak dengan Level yang sama dengan <color=#99DEB0>╥Arcomia Core</color>"
        " (Level maksimal 999)."),
    "你的英雄每次触发<a href=11><color=#99DEB0>╬整备</color></a>时，己方英雄<color=#99DEB0>+1%</color>最大生命值。": (
        "Each time your Hero triggers <a href=11><color=#99DEB0>╬Prepare</color></a>, your Heroes gain"
        " <color=#99DEB0>+1%</color> Max HP.",
        "Setiap kali Hero kamu memicu <a href=11><color=#99DEB0>╬Prepare</color></a>, Hero kamu mendapatkan"
        " <color=#99DEB0>+1%</color> Max HP."),
    "你的英雄每次触发<color=#99DEB0>╬整备</color>时，己方英雄<color=#99DEB0>+1%</color>最大生命值。": (
        "Each time your Hero triggers <color=#99DEB0>╬Prepare</color>, your Heroes gain <color=#99DEB0>+1%</color> Max"
        " HP.",
        "Setiap kali Hero kamu memicu <color=#99DEB0>╬Prepare</color>, Hero kamu mendapatkan <color=#99DEB0>+1%</color>"
        " Max HP."),
    "你的英雄每触发2次<a href=1><color=#ffffff>╨<b>登场</b></color></a>效果，大乔的法力值上限永久-5且等级+1。": (
        "Every time your Heroes trigger <a href=1><color=#ffffff>╨<b>Deploy</b></color></a> effects 2 times, Da Qiao's"
        " Max Mana is permanently reduced by 5 and her Level +1.",
        "Setiap kali Hero kamu memicu efek <a href=1><color=#ffffff>╨<b>Deploy</b></color></a> 2 kali, Max Mana Da Qiao"
        " berkurang permanen sebesar 5 dan Level-nya +1."),
    "光辉伤害提升至17%法术攻击力": (
        "Radiance damage increased to 17% Magic Attack", "Damage Radiance meningkat jadi 17% Magic Attack"),
    "光辉伤害提升至[0]+[1]%法术攻击力": (
        "Radiance damage increased to [0]+[1]% Magic Attack", "Damage Radiance meningkat jadi [0]+[1]% Magic Attack"),
    "光辉伤害提升至[142302p1q1]+[142302p1q3/100]%法术攻击力": (
        "Radiance damage increased to [142302p1q1]+[142302p1q3/100]% Magic Attack",
        "Damage Radiance meningkat jadi [142302p1q1]+[142302p1q3/100]% Magic Attack"),
    "卡牌指定英雄，最大生命值<color=#99DEB0>+55%</color>、法术攻击力<color=#99DEB0>+55%</color>、法术吸血<color=#99DEB0>+25%</color>；该英雄每回合等级<color=#99DEB0>+65</color>，等级上限突破至<color=#99DEB0>9999</color>。": (
        "Target a Hero: Max HP <color=#99DEB0>+55%</color>, Magic Attack <color=#99DEB0>+55%</color>, Magic Lifesteal"
        " <color=#99DEB0>+25%</color>; that Hero gains <color=#99DEB0>+65</color> levels per Round, with a Level cap"
        " increased to <color=#99DEB0>9999</color>.",
        "Pilih satu Hero: Max HP <color=#99DEB0>+55%</color>, Magic Attack <color=#99DEB0>+55%</color>, Magic Lifesteal"
        " <color=#99DEB0>+25%</color>; Hero itu mendapat <color=#99DEB0>+65</color> level per Ronde, dengan batas Level"
        " meningkat menjadi <color=#99DEB0>9999</color>."),
    "只能获得<color=#99DEB0>1-3阶</color>英雄卡；该类英雄最大生命值<color=#99DEB0>+20%</color>、物理攻击力<color=#99DEB0>+20%</color>、攻击速度<color=#99DEB0>+35%</color>。回合开始时，场上英雄等级<color=#99DEB0>+25</color>，等级上限突破至<color=#99DEB0>6666</color>。": (
        "Only <color=#99DEB0>Tier 1-3</color> Hero cards can be obtained; these Heroes gain <color=#99DEB0>+20%</color>"
        " Max HP, <color=#99DEB0>+20%</color> Physical Attack, and <color=#99DEB0>+35%</color> Attack Speed. At the start"
        " of the Round, field Hero levels <color=#99DEB0>+25</color>, with the Level cap increased to"
        " <color=#99DEB0>6666</color>.",
        "Hanya Hero Card <color=#99DEB0>Tier 1-3</color> yang bisa didapat; Hero ini mendapatkan"
        " <color=#99DEB0>+20%</color> Max HP, <color=#99DEB0>+20%</color> Physical Attack, dan <color=#99DEB0>+35%</color>"
        " Attack Speed. Di awal Ronde, level Hero di lapangan <color=#99DEB0>+25</color>, dengan batas Level dinaikkan"
        " menjadi <color=#99DEB0>6666</color>."),
    "回合开始时获得<color=#99DEB0>1张</color><a href=3130012><color=#99DEB0>╆转瞬</color></a>战歌：指定<color=#99DEB0>1名低于5阶</color>英雄<a href=3130011><color=#99DEB0>═临时等级</color></a><color=#99DEB0>+65</color>。战斗胜利则永久获得，失败/平局获得一半。": (
        "At the start of the Round, gain <color=#99DEB0>1</color> <a href=3130012><color=#99DEB0>╆Fleeting</color></a>"
        " War Song: Target <color=#99DEB0>1 Hero below Tier 5</color> to gain <a href=3130011><color=#99DEB0>═Temporary"
        " Level</color></a> <color=#99DEB0>+65</color>. Gain permanently on victory; gain half on draw/defeat.",
        "Di awal Ronde, dapatkan <color=#99DEB0>1</color> War Song <a href=3130012><color=#99DEB0>╆Fleeting</color></a>:"
        " pilih <color=#99DEB0>1 Hero di bawah Tier 5</color> untuk mendapatkan <a href=3130011><color=#99DEB0>═Temporary"
        " Level</color></a> <color=#99DEB0>+65</color>. Didapat permanen jika menang Pertempuran; setengahnya jika"
        " kalah/seri."),
    "回合开始时，场上友方英雄获得主要阵营人数+2的等级。": (
        "At the start of the Round, allied heroes on the field gain Levels equal to the number of heroes in the Main"
        " Faction +2.",
        "Di awal Ronde, hero ally di lapangan mendapat Level sebesar jumlah hero di Faction Utama +2."),
    "回合开始时，场上友方英雄获得场上5阶英雄数量×2的等级。": (
        "At the start of the Round, allied heroes on the field gain levels equal to the number of Tier 5 Heroes on the"
        " field ×2.",
        "Di awal Ronde, hero ally di lapangan mendapat level sebesar jumlah Hero Tier 5 di lapangan ×2."),
    "回合开始时，随机获得<color=#99DEB0>2张</color>高阶战术牌。\n你的【逐鹿】英雄最大生命值<color=#99DEB0>+8%</color>、物理及法术防御<color=#99DEB0>+8</color>。\n【逐鹿】英雄≥<color=#99DEB0>5名</color>时：【逐鹿】英雄释放技能时，己方所有英雄获得巨盾：物理及法术防御<color=#99DEB0>+2</color>，上限<color=#99DEB0>5层</color>。\n【逐鹿】英雄≥<color=#99DEB0>7名</color>时：获得<color=#99DEB0>2张</color>装备牌【机关匣】以及<color=#99DEB0>1张</color>【珍品宝箱】。": (
        "At the start of the Round, randomly gain <color=#99DEB0>2</color> high-Tier Tactics Cards.\nYour [Zhulu"
        " Plateau] Heroes gain Max HP <color=#99DEB0>+8%</color> and Physical and Magic Defense"
        " <color=#99DEB0>+8</color>.\nWith ≥<color=#99DEB0>5</color> [Zhulu Plateau] Heroes: when a [Zhulu Plateau] Hero"
        " casts a Skill, all your Heroes gain Great Shield: Physical and Magic Defense <color=#99DEB0>+2</color>, up to"
        " <color=#99DEB0>5 stacks</color>.\nWith ≥<color=#99DEB0>7</color> [Zhulu Plateau] Heroes: gain"
        " <color=#99DEB0>2</color> [Mechanism Box] Equipment Cards and <color=#99DEB0>1</color> [Treasure Chest].",
        "Di awal Ronde, dapatkan <color=#99DEB0>2</color> Tactics Card Tier tinggi secara acak.\nHero [Zhulu Plateau]"
        " kamu mendapatkan Max HP <color=#99DEB0>+8%</color> serta Physical dan Magic Defense"
        " <color=#99DEB0>+8</color>.\nDengan ≥<color=#99DEB0>5</color> Hero [Zhulu Plateau]: saat Hero [Zhulu Plateau]"
        " menggunakan Skill, semua Hero kamu mendapatkan Great Shield: Physical dan Magic Defense"
        " <color=#99DEB0>+2</color>, maksimal <color=#99DEB0>5 Stack</color>.\nDengan ≥<color=#99DEB0>7</color> Hero"
        " [Zhulu Plateau]: dapatkan <color=#99DEB0>2</color> Equipment Card [Mechanism Box] dan"
        " <color=#99DEB0>1</color> [Treasure Chest]."),
    "场上每有<color=#99DEB0>1个╉图腾</color>，【大河流域】英雄最大生命值<color=#99DEB0>+5%</color>、物理及法术防御<color=#99DEB0>+5</color>。\n【大河】英雄≥<color=#99DEB0>6名</color>时，战斗开始时，<color=#99DEB0>╉图腾周围1格内的己方单位</color>生命值上限<color=#99DEB0>+8%</color>、攻击速度<color=#99DEB0>+20%</color>，可叠加。\n【大河】英雄≥<color=#99DEB0>8名</color>时，开战时随机召唤<color=#99DEB0>1个</color>先知图腾、因缘图腾或往生图腾。": (
        "For every <color=#99DEB0>1 ╉Totem</color> on the board, [Riverlands] Heroes gain <color=#99DEB0>+5%</color> Max"
        " HP and <color=#99DEB0>+5</color> Physical and Magic Defense.\nWith ≥<color=#99DEB0>6</color> [Riverlands]"
        " Heroes: at the start of Battle, <color=#99DEB0>allied units within 1 tile of a ╉Totem</color> gain"
        " <color=#99DEB0>+8%</color> Max HP and <color=#99DEB0>+20%</color> Attack Speed. This can stack.\nWith"
        " ≥<color=#99DEB0>8</color> [Riverlands] Heroes: at the start of Battle, randomly Summon"
        " <color=#99DEB0>1</color> Seer Totem, Destiny Totem or Afterlife Totem.",
        "Untuk setiap <color=#99DEB0>1 ╉Totem</color> di papan, Hero [Riverlands] mendapat <color=#99DEB0>+5%</color> Max"
        " HP dan <color=#99DEB0>+5</color> Physical dan Magic Defense.\nDengan ≥<color=#99DEB0>6</color> Hero"
        " [Riverlands]: di awal Pertempuran, <color=#99DEB0>unit ally dalam jarak 1 petak dari ╉Totem</color> mendapat"
        " <color=#99DEB0>+8%</color> Max HP dan <color=#99DEB0>+20%</color> Attack Speed. Ini bisa stack.\nDengan"
        " ≥<color=#99DEB0>8</color> Hero [Riverlands]: di awal Pertempuran, Summon <color=#99DEB0>1</color> Seer Totem,"
        " Destiny Totem, atau Afterlife Totem secara acak."),
    "场上每有<color=#99DEB0>1名</color>【三分】英雄，全体【三分】英雄物理攻击力、法术攻击力<color=#99DEB0>+2%</color>，物理防御、法术防御<color=#99DEB0>+2%</color>。\n【三分】英雄首次≥<color=#99DEB0>5名</color>：永久召唤「猛虎擂台」，台中【三分】英雄物攻/法攻+<color=#99DEB0>30</color>点。擂台内敌人被击败则吸收灵魂，物攻/法攻+<color=#99DEB0>10</color>点。每吸收<color=#99DEB0>5次</color>，范围+<color=#99DEB0>1格</color>，最多<color=#99DEB0>3次</color>。\n【三分】英雄首次≥<color=#99DEB0>7名</color>：获得<color=#99DEB0>1张</color>【三分旗帜】。": (
        "For every <color=#99DEB0>1</color> [Three Kingdoms] Hero on the board, all [Three Kingdoms] Heroes gain"
        " <color=#99DEB0>+2%</color> Physical and Magic Attack and <color=#99DEB0>+2%</color> Physical and Magic"
        " Defense.\nThe first time you have ≥<color=#99DEB0>5</color> [Three Kingdoms] Heroes: permanently Summon the"
        " \"Tiger Arena\"; [Three Kingdoms] Heroes in it gain Physical/Magic Attack +<color=#99DEB0>30</color>. When an"
        " enemy is Defeated in the arena, it absorbs their soul: Physical/Magic Attack +<color=#99DEB0>10</color>. Every"
        " <color=#99DEB0>5</color> souls absorbed, its range +<color=#99DEB0>1 tile</color>, up to"
        " <color=#99DEB0>3 times</color>.\nThe first time you have ≥<color=#99DEB0>7</color> [Three Kingdoms] Heroes:"
        " gain <color=#99DEB0>1</color> [Three Kingdoms Banner].",
        "Untuk setiap <color=#99DEB0>1</color> Hero [Three Kingdoms] di papan, semua Hero [Three Kingdoms] mendapat"
        " <color=#99DEB0>+2%</color> Physical dan Magic Attack serta <color=#99DEB0>+2%</color> Physical dan Magic"
        " Defense.\nSaat pertama kali kamu memiliki ≥<color=#99DEB0>5</color> Hero [Three Kingdoms]: panggil \"Tiger"
        " Arena\" secara permanen; Hero [Three Kingdoms] di dalamnya mendapat Physical/Magic Attack"
        " +<color=#99DEB0>30</color>. Saat musuh dikalahkan di dalam arena, arena menyerap jiwanya: Physical/Magic"
        " Attack +<color=#99DEB0>10</color>. Setiap <color=#99DEB0>5</color> jiwa terserap, jangkauan"
        " +<color=#99DEB0>1 petak</color>, hingga <color=#99DEB0>3 kali</color>.\nSaat pertama kali kamu memiliki"
        " ≥<color=#99DEB0>7</color> Hero [Three Kingdoms]: dapatkan <color=#99DEB0>1</color> [Three Kingdoms Banner]."),
    "增加6点物理和法术防御力；毒奶改为造成10+45%法术攻击力的法术伤害，恢复10+45%法术攻击力的生命值。": (
        "Increases Physical and Magic Defense by 6; Toxic Healing now deals 10+45% Magic Attack as Magic Damage and"
        " restores 10+45% Magic Attack as Health.",
        "Meningkatkan Physical dan Magic Defense sebesar 6; Toxic Healing kini memberikan Magic Damage sebesar 10+45%"
        " Magic Attack dan memulihkan Health sebesar 10+45% Magic Attack."),
    "大司命灵体以外的1-3阶己方召唤物上场时，吸收该单位使<a href=321><color=#ffffff>╉<b>往生图腾</b></color></a>等级永久+2并获得20点法力值。": (
        "When a Tier 1-3 friendly Summon (excluding Augran's spirit) enters the field, absorb it to permanently increase"
        " <a href=321><color=#ffffff>╉<b>Afterlife Totem</b></color></a> Level by 2 and gain 20 Mana.",
        "Saat Summon sekutu Tier 1-3 (kecuali roh Augran) masuk ke papan, serap untuk menaikkan Level <a href=321>"
        "<color=#ffffff>╉<b>Afterlife Totem</b></color></a> secara permanen sebesar 2 dan dapatkan 20 Mana."),
    "契约英雄共战时，任意一方每击败<color=#99DEB0>1名</color>敌方英雄，双方物理攻击力、法术攻击力<color=#99DEB0>+5%</color>（上限<color=#99DEB0>60%</color>）。": (
        "When Contract Heroes fight together, for every <color=#99DEB0>1</color> enemy Hero defeated by either of them,"
        " both gain <color=#99DEB0>+5%</color> Physical and Magic Attack (up to <color=#99DEB0>60%</color>).",
        "Saat Hero Contract bertarung bersama, untuk setiap <color=#99DEB0>1</color> Hero musuh yang dikalahkan salah"
        " satunya, keduanya mendapatkan <color=#99DEB0>+5%</color> Physical Attack dan Magic Attack (maksimal"
        " <color=#99DEB0>60%</color>)."),
    "契约英雄共战时，战斗开始时契约英雄双方获取己方其他英雄等级之和×<color=#99DEB0>30%</color>的等级。": (
        "When Contract Heroes fight together, at the start of combat both gain Levels equal to the sum of your other"
        " Heroes' Levels ×<color=#99DEB0>30%</color>.",
        "Saat Hero Contract bertarung bersama, di awal Pertempuran keduanya mendapatkan Level sebesar total Level Hero"
        " kamu yang lain ×<color=#99DEB0>30%</color>."),
    "契约英雄共战时，每<color=#99DEB0>2秒</color>临时提升其<color=#99DEB0>8%</color>物理攻击力和法术攻击力（上限<color=#99DEB0>80%</color>）。": (
        "When Contract Heroes fight together, they temporarily gain <color=#99DEB0>8%</color> Physical Attack and Magic"
        " Attack every <color=#99DEB0>2 seconds</color> (up to <color=#99DEB0>80%</color>).",
        "Saat Hero Contract bertarung bersama, mereka mendapatkan <color=#99DEB0>8%</color> Physical Attack dan Magic"
        " Attack sementara setiap <color=#99DEB0>2 detik</color> (maksimal <color=#99DEB0>80%</color>)."),
    "契约英雄共战时，每次升级<color=#99DEB0>额外+4级</color>。": (
        "When Contract Heroes fight together, they gain <color=#99DEB0>+4 extra levels</color> each time they level up.",
        "Saat Hero Contract bertarung bersama, mereka mendapatkan <color=#99DEB0>+4 Level tambahan</color> setiap kali"
        " naik Level."),
    "孙尚香朝目标敌人发射1发弩炮，造成<color=#dfa15e>50+100%物理攻击力的物理伤害</color>，并降低命中敌人50%物理防御，持续5秒。": (
        "Lady Sun fires a crossbow bolt at the target enemy, dealing <color=#dfa15e>50+100% Physical Attack as Physical"
        " Damage</color> and reducing the hit enemy's Physical Defense by 50% for 5 seconds.",
        "Lady Sun menembakkan anak panah crossbow ke musuh target, memberikan <color=#dfa15e>Physical Damage sebesar"
        " 50+100% Physical Attack</color> dan mengurangi Physical Defense musuh yang terkena sebesar 50% selama 5"
        " detik."),
    "孙膑向目标敌人投掷1枚定时炸弹，2秒后爆炸对其及附近1格内的敌人造成<color=#d487e4>[118141p1q1]+[118141p1q3/100]%法术攻击力的法术伤害</color>。": (
        "Sun Bin throws a time bomb at the target enemy, which explodes after 2 seconds, dealing"
        " <color=#d487e4>[118141p1q1]+[118141p1q3/100]% Magic Attack as Magic Damage</color> to the target and enemies"
        " within 1 grid.",
        "Sun Bin melempar bom waktu ke musuh target, yang meledak setelah 2 detik, memberikan <color=#d487e4>Magic"
        " Damage sebesar [118141p1q1]+[118141p1q3/100]% Magic Attack</color> ke target dan musuh dalam jarak 1"
        " petak."),
    "安琪拉引导魔力朝敌人最多的方向施放炽热光辉，持续3秒，对路径上的敌人每0.1秒造成<color=#d487e4>10%法术攻击力的法术伤害</color>。": (
        "Angela channels magic to cast Blazing Radiance in the direction of the most enemies for 3 seconds, dealing"
        " <color=#d487e4>10% Magic Attack as Magic Damage</color> to enemies in the path every 0.1 seconds.",
        "Angela menyalurkan sihir untuk melepaskan Blazing Radiance ke arah musuh terbanyak selama 3 detik, memberikan"
        " <color=#d487e4>Magic Damage sebesar 10% Magic Attack</color> ke musuh di jalurnya setiap 0,1 detik."),
    "安琪拉引导魔力朝敌人最多的方向施放炽热光辉，持续3秒，对路径上的敌人每0.1秒造成<color=#d487e4>[0]点法术伤害</color><color=#d487e4>（[1]+[2]%法术攻击力）</color>。": (
        "Angela channels magic to cast Blazing Radiance in the direction of the most enemies for 3 seconds, dealing"
        " <color=#d487e4>[0] Magic Damage</color><color=#d487e4> ([1]+[2]% Magic Attack)</color> every 0.1 seconds to"
        " enemies in her path.",
        "Angela menyalurkan sihir untuk melepaskan Blazing Radiance ke arah musuh terbanyak selama 3 detik, memberikan"
        " <color=#d487e4>[0] Magic Damage</color><color=#d487e4> ([1]+[2]% Magic Attack)</color> setiap 0,1 detik ke"
        " musuh di jalurnya."),
    "安琪拉引导魔力朝敌人最多的方向施放炽热光辉，持续3秒，对路径上的敌人每0.1秒造成<color=#d487e4>[142300p1q1]+[142300p1q3/100]%法术攻击力的法术伤害</color>。": (
        "Angela channels magic to cast Blazing Radiance in the direction of the most enemies for 3 seconds, dealing"
        " <color=#d487e4>[142300p1q1]+[142300p1q3/100]% Magic Attack as Magic Damage</color> to enemies in the path"
        " every 0.1 seconds.",
        "Angela menyalurkan sihir untuk melepaskan Blazing Radiance ke arah musuh terbanyak selama 3 detik, memberikan"
        " <color=#d487e4>Magic Damage sebesar [142300p1q1]+[142300p1q3/100]% Magic Attack</color> ke musuh di jalurnya"
        " setiap 0,1 detik."),
    "导弹伤害提升至30+80%物理攻击力": (
        "Missile Damage Up to 30+80% Physical Attack", "Damage Misil Naik menjadi 30+80% Physical Attack"),
    "己方单位获得护盾、护盾被击破时，该单位生命值上限永久<color=#99DEB0>+110</color>。": (
        "Whenever an allied unit gains a Shield or has its Shield broken, that unit's Max HP permanently"
        " <color=#99DEB0>+110</color>.",
        "Setiap kali unit kamu mendapatkan Shield atau Shield-nya hancur, Max HP unit itu bertambah permanen"
        " <color=#99DEB0>+110</color>."),
    "己方英雄每释放<color=#99DEB0>1次</color>技能，所有英雄等级<color=#99DEB0>+2</color>。": (
        "Each time your Hero casts a Skill <color=#99DEB0>1 time</color>, All Heroes gain <color=#99DEB0>+2</color>"
        " Level.",
        "Setiap kali Hero kamu menggunakan Skill <color=#99DEB0>1 kali</color>, semua Hero mendapatkan"
        " <color=#99DEB0>+2</color> Level."),
    "廉颇用臂甲砸向目标敌人，获得持续4秒的<color=#ffffff>100点护盾</color>，造成<color=#dfa15e>50+80%物理攻击力的物理伤害</color>。": (
        "Lian Po smashes the target enemy with his gauntlets, gaining a <color=#ffffff>100-point Shield</color> for 4"
        " seconds and dealing <color=#dfa15e>50+80% Physical Attack as Physical Damage</color>.",
        "Lian Po menghantam musuh target dengan sarung tangannya, mendapat <color=#ffffff>Shield 100 poin</color> selama"
        " 4 detik dan memberikan <color=#dfa15e>Physical Damage sebesar 50+80% Physical Attack</color>."),
    "开局及棋手5级时获得1张<color=#ffffff><b>便携式机关</b></color>。\n棋手升至2/3/4级时，从<color=#ffffff><b>热能陷阱</b></color>、<color=#ffffff><b>电磁弹簧</b></color>、<color=#ffffff><b>等离子屏障</b></color>3种机关卡中随机获得1张。": (
        "At the start of the match and at Chessplayer Level 5, gain 1 <color=#ffffff><b>Portable Mechanism</b></color>.\n"
        "When the Chessplayer reaches Level 2/3/4, randomly gain 1 of 3 Mechanism cards: <color=#ffffff><b>Thermal"
        " Trap</b></color>, <color=#ffffff><b>Electromagnetic Spring</b></color>, or <color=#ffffff><b>Plasma"
        " Barrier</b></color>.",
        "Di awal pertandingan dan saat Chessplayer Level 5, dapatkan 1 <color=#ffffff><b>Portable"
        " Mechanism</b></color>.\nSaat Chessplayer mencapai Level 2/3/4, dapatkan secara acak 1 dari 3 kartu Mechanism:"
        " <color=#ffffff><b>Thermal Trap</b></color>, <color=#ffffff><b>Electromagnetic Spring</b></color>, atau"
        " <color=#ffffff><b>Plasma Barrier</b></color>."),
    "弩炮伤害提升至50+150%物理攻击力": (
        "Crossbow bolt damage increased to 50+150% Physical Attack",
        "Damage anak panah crossbow meningkat menjadi 50+150% Physical Attack"),
    "技能伤害提升至50+120%物理攻击力，护盾提升至250点": (
        "Skill damage increased to 50+120% Physical Attack, and Shield increased to 250",
        "Damage Skill meningkat menjadi 50+120% Physical Attack, dan Shield meningkat menjadi 250"),
    "战斗开始时，你的人数最多的同品阶英雄获得1%×已打出<color=#ffffff><b>宝藏牌</b></color>数量的伤害提升。": (
        "At the start of combat, your most numerous Hero Tier gains +1% Damage for every <color=#ffffff><b>Treasure"
        " card</b></color> played.",
        "Di awal pertarungan, Tier Hero terbanyak milikmu mendapat +1% damage untuk setiap <color=#ffffff><b>Treasure"
        " card</b></color> yang dimainkan."),
    "战斗开始时，你的全体英雄获得0.7%×已打出<color=#ffffff><b>宝藏牌</b></color>数量的伤害提升。": (
        "At the start of combat, all your Heroes gain +0.7% Damage for every <color=#ffffff><b>Treasure card</b></color>"
        " played.",
        "Di awal pertarungan, semua Hero milikmu mendapat +0,7% damage untuk setiap <color=#ffffff><b>Treasure"
        " card</b></color> yang dimainkan."),
    "战斗开始时，所有【河洛】英雄获得累计使用古币数（获得此天赋后）的<color=#99DEB0>═临时等级</color>。\n【河洛】英雄≥<color=#99DEB0>5名</color>时：【河洛】英雄受到致命伤害时进入无敌，攻击速度<color=#99DEB0>+80%</color>，持续<color=#99DEB0>0.5秒</color>。战斗中每触发<color=#99DEB0>1次╫牺牲</color>，无敌时间<color=#99DEB0>+0.25秒</color>（上限<color=#99DEB0>2秒</color>）。\n【河洛】英雄≥<color=#99DEB0>7名</color>时：【河洛】英雄获得<color=#99DEB0>╫牺牲</color>：所有友方单位<color=#99DEB0>+7═临时等级</color>，每次触发此<color=#99DEB0>╫牺牲</color>时，<color=#99DEB0>═临时等级</color>额外<color=#99DEB0>+7</color>。": (
        "At the start of Battle, all [Central Plains] Heroes gain <color=#99DEB0>═Temporary Level</color> equal to the"
        " number of Ancient Coins used (since gaining this Talent).\nWith ≥<color=#99DEB0>5</color> [Central Plains]"
        " Heroes: when a [Central Plains] Hero takes fatal Damage, it becomes Invincible and gains"
        " <color=#99DEB0>+80%</color> Attack Speed for <color=#99DEB0>0.5 seconds</color>. Each"
        " <color=#99DEB0>1 ╫Sacrifice</color> triggered in Battle adds <color=#99DEB0>+0.25 seconds</color> of"
        " Invincibility (up to <color=#99DEB0>2 seconds</color>).\nWith ≥<color=#99DEB0>7</color> [Central Plains]"
        " Heroes: [Central Plains] Heroes gain <color=#99DEB0>╫Sacrifice</color>: all allied units gain"
        " <color=#99DEB0>+7 ═Temporary Level</color>; each time this <color=#99DEB0>╫Sacrifice</color> triggers, its"
        " <color=#99DEB0>═Temporary Level</color> gains an extra <color=#99DEB0>+7</color>.",
        "Di awal Pertempuran, semua Hero [Central Plains] mendapat <color=#99DEB0>═Temporary Level</color> sebesar"
        " jumlah Ancient Coin yang digunakan (sejak mendapatkan Talent ini).\nDengan ≥<color=#99DEB0>5</color> Hero"
        " [Central Plains]: saat Hero [Central Plains] menerima damage fatal, Hero itu menjadi Invincible dan mendapat"
        " <color=#99DEB0>+80%</color> Attack Speed selama <color=#99DEB0>0,5 detik</color>. Setiap"
        " <color=#99DEB0>1 ╫Sacrifice</color> yang terpicu dalam Pertempuran menambah durasi Invincible"
        " <color=#99DEB0>+0,25 detik</color> (maksimal <color=#99DEB0>2 detik</color>).\nDengan"
        " ≥<color=#99DEB0>7</color> Hero [Central Plains]: Hero [Central Plains] mendapat"
        " <color=#99DEB0>╫Sacrifice</color>: semua unit ally mendapat <color=#99DEB0>+7 ═Temporary Level</color>;"
        " setiap kali <color=#99DEB0>╫Sacrifice</color> ini terpicu, <color=#99DEB0>═Temporary Level</color>-nya"
        " bertambah <color=#99DEB0>+7</color> lagi."),
    "打出古币时有概率<color=#99DEB0>额外触发2-4次</color>。你的古币额外提供<color=#99DEB0>6级</color>。": (
        "Ancient Coins have a chance to <color=#99DEB0>Trigger 2-4 Extra times</color>. Your Ancient Coins provide an"
        " additional <color=#99DEB0>6 levels</color>.",
        "Ancient Coin berpeluang <color=#99DEB0>terpicu 2-4 kali tambahan</color>. Ancient Coin kamu memberikan tambahan"
        " <color=#99DEB0>6 Level</color>."),
    "打出古币时有概率额外触发<color=#99DEB0>2-4</color>次。你的古币额外提供<color=#99DEB0>6级</color>。": (
        "Ancient Coins have a chance to Trigger <color=#99DEB0>2-4</color> Extra times. Your Ancient Coins provide an"
        " additional <color=#99DEB0>6 levels</color>.",
        "Ancient Coin berpeluang terpicu <color=#99DEB0>2-4</color> kali tambahan. Ancient Coin kamu memberikan tambahan"
        " <color=#99DEB0>6 Level</color>."),
    "打出后获得累积的钻石（当前{810299Diamond:0|0}）和全体英雄等级（当前{810299Level:0}）。持有时：胜利钻石<color=#99DEB0>+{0|5}</color>、等级<color=#99DEB0>+10</color>；失败钻石<color=#99DEB0>+{0|1}</color>、等级<color=#99DEB0>+50</color>；平局不计入。": (
        "When played, claim the accumulated Diamonds (currently {810299Diamond:0|0}) and All Hero Levels (currently"
        " {810299Level:0}). While held: Win: Diamonds <color=#99DEB0>+{0|5}</color>, Levels <color=#99DEB0>+10</color>;"
        " Loss: Diamonds <color=#99DEB0>+{0|1}</color>, Levels <color=#99DEB0>+50</color>; draws do not count.",
        "Saat dimainkan, klaim Diamond yang terkumpul (saat ini {810299Diamond:0|0}) dan Level Semua Hero (saat ini"
        " {810299Level:0}). Selama dipegang: Menang: Diamond <color=#99DEB0>+{0|5}</color>, Level"
        " <color=#99DEB0>+10</color>; Kalah: Diamond <color=#99DEB0>+{0|1}</color>, Level <color=#99DEB0>+50</color>;"
        " seri tidak dihitung."),
    "持有时每场战斗后累积奖励：\n胜利：钻石<color=#99DEB0>+{0|5}</color>、全体英雄等级<color=#99DEB0>+10</color>\n失败：钻石<color=#99DEB0>+{0|1}</color>、全体英雄等级<color=#99DEB0>+50</color>\n平局不计入。打出后领取全部累积（当前钻石{810299Diamond:0|0}，等级{810299Level:0}）。": (
        "Accumulate Rewards after each combat while held:\nWin: Diamonds <color=#99DEB0>+{0|5}</color>, All Hero Levels"
        " <color=#99DEB0>+10</color>\nLoss: Diamonds <color=#99DEB0>+{0|1}</color>, All Hero Levels"
        " <color=#99DEB0>+50</color>\nDraws do not count. Claim All accumulated Rewards upon playing (Current Diamonds"
        " {810299Diamond:0|0}, Levels {810299Level:0}).",
        "Kumpulkan Hadiah setelah setiap pertempuran selama dipegang:\nMenang: Diamond <color=#99DEB0>+{0|5}</color>,"
        " Level Semua Hero <color=#99DEB0>+10</color>\nKalah: Diamond <color=#99DEB0>+{0|1}</color>, Level Semua Hero"
        " <color=#99DEB0>+50</color>\nSeri tidak dihitung. Klaim semua Hadiah yang terkumpul saat dimainkan (Diamond"
        " saat ini {810299Diamond:0|0}, Level {810299Level:0})."),
    "施法时会标记当前目标，降低其10点物理及法术防御力；标记目标被击败时玄策进入狂暴状态（攻速提高150%，移速提高40%），持续7秒": (
        "Marks the current target on cast, reducing its Physical and Magic Defense by 10. When the marked target is"
        " Defeated, Xuance enters a Berserk state (Attack Speed +150%, Movement Speed +40%) for 7 seconds",
        "Menandai target saat ini ketika skill digunakan, mengurangi Physical dan Magic Defense-nya sebesar 10. Saat"
        " target yang ditandai dikalahkan, Xuance memasuki kondisi Berserk (Attack Speed +150%, Movement Speed +40%)"
        " selama 7 detik"),
    "施法直接获得最大护盾值（不再需要多次施法提升）并恢复10%最大生命值": (
        "Casting instantly grants the max Shield value (no longer requires multiple casts to stack) and restores 10%"
        " Max HP",
        "Menggunakan skill langsung memberikan nilai Shield maksimal (tidak perlu lagi beberapa kali cast untuk stack)"
        " dan memulihkan 10% Max HP"),
    "机械仆从获得200%法术攻击的额外生命值；机械仆从到达上限后，再次施放技能转而恢复仆从们的<color=#9ff5d0>所有生命值</color>": (
        "Mechanical Minions gain extra Health equal to 200% Magic Attack; once Mechanical Minions reach the limit,"
        " casting the Skill again instead restores <color=#9ff5d0>all of the minions' Health</color>",
        "Mechanical Minion mendapat Health tambahan sebesar 200% Magic Attack; setelah Mechanical Minion mencapai batas,"
        " menggunakan Skill lagi justru memulihkan <color=#9ff5d0>seluruh Health minion</color>"),
    "机械仆从获得200%法术攻击的额外生命值；机械仆从到达上限后，再次施放技能转而恢复仆从们的所有生命值": (
        "Mechanical Minions gain extra Health equal to 200% Magic Attack; once Mechanical Minions reach the limit,"
        " casting the Skill again instead restores all of the minions' Health",
        "Mechanical Minion mendapat Health tambahan sebesar 200% Magic Attack; setelah Mechanical Minion mencapai batas,"
        " menggunakan Skill lagi justru memulihkan seluruh Health minion"),
    "每召唤<color=#99DEB0>1个</color>单位（仅召唤物，<a href=321><color=#99DEB0>╉图腾</color></a>），下回合开始时所有英雄等级<color=#99DEB0>+2</color>。": (
        "For every <color=#99DEB0>1</color> unit summoned (only Summons and <a href=321><color=#99DEB0>╉Totems</color></a>),"
        " all Heroes gain <color=#99DEB0>+2</color> Levels at the start of the next Round.",
        "Untuk setiap <color=#99DEB0>1</color> unit yang dipanggil (hanya Summon dan <a href=321><color=#99DEB0>╉Totem"
        "</color></a>), semua Hero mendapatkan <color=#99DEB0>+2</color> Level di awal Ronde berikutnya."),
    "每召唤<color=#99DEB0>1个</color>单位（仅召唤物，╉图腾），下回合开始时所有英雄等级<color=#99DEB0>+2</color>。": (
        "For every <color=#99DEB0>1</color> unit summoned (only Summons and ╉Totems), all Heroes gain"
        " <color=#99DEB0>+2</color> Levels at the start of the next Round.",
        "Untuk setiap <color=#99DEB0>1</color> unit yang dipanggil (hanya Summon dan ╉Totem), semua Hero mendapat"
        " <color=#99DEB0>+2</color> Level di awal Ronde berikutnya."),
    "每当你的英雄触发<a href=1><color=#ffffff>╨<b>登场</b></color></a>效果，大乔的法力值上限永久-5且等级+1。": (
        "Whenever your Hero triggers a <a href=1><color=#ffffff>╨<b>Deploy</b></color></a> Effect, Da Qiao's Max Mana is"
        " permanently reduced by 5 and her Level +1.",
        "Setiap kali Hero-mu memicu efek <a href=1><color=#ffffff>╨<b>Deploy</b></color></a>, Max Mana Da Qiao berkurang"
        " permanen sebesar 5 dan Level-nya +1."),
    "每次召唤2个机械仆从；攻击伤害提升至50+60%法术攻击力": (
        "Summons 2 Mechanical Minions each time; attack damage increased to 50+60% Magic Attack",
        "Memanggil 2 Mechanical Minion setiap kali; damage serangan meningkat menjadi 50+60% Magic Attack"),
    "每次施法护盾值额外提升40点，最多5次": (
        "Shield value additionally increases by 40 per cast, up to 5 times",
        "Nilai Shield bertambah 40 setiap kali digunakan, hingga 5 kali"),
    "每触发<color=#99DEB0>1次</color><a href=1><color=#99DEB0>╨登场</color></a>，己方在场英雄物理攻击力和法术攻击力<color=#99DEB0>+1%</color>。": (
        "Each time <color=#99DEB0>1</color> <a href=1><color=#99DEB0>╨Deploy</color></a> triggers, your Heroes on the"
        " field gain <color=#99DEB0>+1%</color> Physical Attack and Magic Attack.",
        "Setiap kali <color=#99DEB0>1</color> <a href=1><color=#99DEB0>╨Deploy</color></a> terpicu, Hero kamu di papan"
        " mendapatkan <color=#99DEB0>+1%</color> Physical Attack dan Magic Attack."),
    "每触发<color=#99DEB0>1次</color>╨登场，己方在场英雄物理攻击力和法术攻击力<color=#99DEB0>+1%</color>。": (
        "Each time <color=#99DEB0>1</color> ╨Deploy triggers, your Heroes on the field gain <color=#99DEB0>+1%</color>"
        " Physical Attack and Magic Attack.",
        "Setiap kali <color=#99DEB0>1</color> ╨Deploy terpicu, Hero kamu di papan mendapatkan <color=#99DEB0>+1%</color>"
        " Physical Attack dan Magic Attack."),
    "海诺朝目标方向掷出能量化的命运神杖，对命中的敌人造成<color=#d487e4>100+150%法术攻击力的法术伤害</color>并朝目标敌人附近2名敌人掷出子杖，造成<color=#d487e4>50+100%法术攻击力的法术伤害</color>。": (
        "Heino throws his energized Fate Staff in the target direction, dealing <color=#d487e4>100+150% Magic Attack as"
        " Magic Damage</color> to enemies hit, and throws sub-staves at 2 enemies near the target, dealing"
        " <color=#d487e4>50+100% Magic Attack as Magic Damage</color>.",
        "Heino melempar Fate Staff berenergi ke arah target, memberikan <color=#d487e4>Magic Damage sebesar 100+150%"
        " Magic Attack</color> ke musuh yang terkena, dan melempar staf kecil ke 2 musuh di dekat target, memberikan"
        " <color=#d487e4>Magic Damage sebesar 50+100% Magic Attack</color>."),
    "炸弹伤害提升至100+175%法术攻击力": (
        "Increases Bomb Damage to 100+175% Magic Attack", "Meningkatkan damage Bom menjadi 100+175% Magic Attack"),
    "玄策舞动钩镰对目标敌人造成<color=#dfa15e>50+100%物理攻击力的物理伤害</color>，而后将其甩向玄策身后，落地时造成<color=#dfa15e>50+100%物理攻击力的物理伤害</color>并眩晕1秒。": (
        "Xuance swings his hook-sickle to deal <color=#dfa15e>50+100% Physical Attack as Physical Damage</color> to the"
        " target enemy, then flings it behind him, dealing <color=#dfa15e>50+100% Physical Attack as Physical"
        " Damage</color> on landing and stunning it for 1 second.",
        "Xuance mengayunkan sabit kaitnya untuk memberikan <color=#dfa15e>Physical Damage sebesar 50+100% Physical"
        " Attack</color> ke musuh target, lalu melemparkannya ke belakangnya, memberikan <color=#dfa15e>Physical Damage"
        " sebesar 50+100% Physical Attack</color> saat mendarat dan membuatnya stun selama 1 detik."),
    "神杖伤害提升至150+250%法术攻击力；子杖伤害提升至100+150%法术攻击力": (
        "Fate Staff damage increased to 150+250% Magic Attack; sub-staff damage increased to 100+150% Magic Attack",
        "Damage Fate Staff meningkat menjadi 150+250% Magic Attack; damage staf kecil meningkat menjadi 100+150% Magic"
        " Attack"),
    "突袭伤害提升至50+150%物理攻击力": (
        "Dash damage increased to 50+150% Physical Attack", "Damage dash meningkat menjadi 50+150% Physical Attack"),
    "米莱狄在距离自己最远的敌人附近召唤1个机械仆从，继承自己<color=#d487e4>100%法术攻击力</color>。\n仆从每次攻击造成<color=#d487e4>50+30%法术攻击力的法术伤害</color>，机械仆从到达最大数量后，再次施放技能，增加仆从15%攻击速度，持续5秒。": (
        "Milady summons 1 Mechanical Minion near the enemy farthest from her; it inherits <color=#d487e4>100% of her"
        " Magic Attack</color>.\nEach minion attack deals <color=#d487e4>50+30% Magic Attack as Magic Damage</color>."
        " Once the minions reach their maximum number, casting the Skill again gives them +15% Attack Speed for 5"
        " seconds.",
        "Milady memanggil 1 Mechanical Minion di dekat musuh terjauh darinya, yang mewarisi <color=#d487e4>100% Magic"
        " Attack-nya</color>.\nSetiap serangan minion memberikan <color=#d487e4>Magic Damage sebesar 50+30% Magic"
        " Attack</color>. Setelah jumlah minion mencapai maksimal, menggunakan Skill lagi menambah Attack Speed minion"
        " 15% selama 5 detik."),
    "米莱狄在距离自己最远的敌人附近召唤1个机械仆从，继承自己<color=#d487e4>100%法术攻击力</color>。\n仆从每次攻击造成<color=#d487e4>[0]点法术伤害</color><color=#d487e4>（[1]+[2]%法术攻击力）</color>，机械仆从到达最大数量后，再次施放技能，增加仆从60%攻击速度，持续5秒（不可叠加）。": (
        "Milady summons 1 Mechanical Minion near the enemy farthest from her; it inherits <color=#d487e4>100% of her"
        " Magic Attack</color>.\nEach minion attack deals <color=#d487e4>[0] Magic Damage</color><color=#d487e4> ([1] +"
        " [2]% Magic Attack)</color>. Once the minions reach their maximum number, casting the Skill again gives them"
        " +60% Attack Speed for 5 seconds (does not stack).",
        "Milady memanggil 1 Mechanical Minion di dekat musuh terjauh darinya, yang mewarisi <color=#d487e4>100% Magic"
        " Attack-nya</color>.\nSetiap serangan minion memberikan <color=#d487e4>[0] Magic Damage</color>"
        "<color=#d487e4> ([1] + [2]% Magic Attack)</color>. Setelah jumlah minion mencapai maksimal, menggunakan Skill"
        " lagi menambah Attack Speed minion 60% selama 5 detik (tidak menumpuk)."),
    "米莱狄在距离自己最远的敌人附近召唤1个机械仆从，继承自己<color=#d487e4>100%法术攻击力</color>。\n仆从每次攻击造成<color=#d487e4>[504040p1q1]+[504040p1q3/100]%法术攻击力的法术伤害</color>，机械仆从到达最大数量后，再次施放技能，增加仆从60%攻击速度，持续5秒（不可叠加）。": (
        "Milady summons 1 Mechanical Minion near the enemy farthest from her; it inherits <color=#d487e4>100% of her"
        " Magic Attack</color>.\nEach minion attack deals <color=#d487e4>[504040p1q1]+[504040p1q3/100]% Magic Attack as"
        " Magic Damage</color>. Once the minions reach their maximum number, casting the Skill again gives them +60%"
        " Attack Speed for 5 seconds (does not stack).",
        "Milady memanggil 1 Mechanical Minion di dekat musuh terjauh darinya, yang mewarisi <color=#d487e4>100% Magic"
        " Attack-nya</color>.\nSetiap serangan minion memberikan <color=#d487e4>Magic Damage sebesar"
        " [504040p1q1]+[504040p1q3/100]% Magic Attack</color>. Setelah jumlah minion mencapai maksimal, menggunakan"
        " Skill lagi menambah Attack Speed minion 60% selama 5 detik (tidak menumpuk)."),
    "第6/11回合": ("Round 6/11", "Ronde 6/11"),
    "获得3张天赋牌<color=#FFE897>限制性进化</color>：指定移除1名1~2阶英雄，获得高2阶的随机英雄牌，且上阵时为原等级+10。": (
        "Gain 3 <color=#FFE897>Restrictive Evolution</color> Talent Cards: remove 1 Tier 1-2 Hero to gain a random Hero"
        " Card 2 Tiers higher, which enters at the original Level +10.",
        "Dapatkan 3 Talent Card <color=#FFE897>Restrictive Evolution</color>: singkirkan 1 Hero Tier 1-2 untuk"
        " mendapatkan 1 Kartu Hero acak dengan Tier 2 lebih tinggi, yang masuk dengan Level asli +10."),
    "蒙犽发射12枚导弹攻击随机敌人，每枚造成<color=#dfa15e>30+60%物理攻击力的物理伤害</color>。多枚导弹命中同一目标时，后续伤害衰减40%。": (
        "Meng Ya fires 12 missiles at random enemies, each dealing <color=#dfa15e>30+60% Physical Attack as Physical"
        " Damage</color>. When several missiles hit the same target, each further hit deals 40% less Damage.",
        "Meng Ya meluncurkan 12 rudal untuk menyerang musuh acak, masing-masing memberikan <color=#dfa15e>Physical"
        " Damage sebesar 30+60% Physical Attack</color>. Saat beberapa rudal mengenai target yang sama, damage"
        " berikutnya berkurang 40%."),
    "蒙犽发射12枚导弹攻击随机敌人，每枚造成<color=#dfa15e>[0]点物理伤害</color><color=#dfa15e>（[1]+[2]%物理攻击力）</color>。多枚导弹命中同一目标时，后续伤害衰减40%。": (
        "Meng Ya launches 12 missiles to attack random enemies, each dealing <color=#dfa15e>[0] Physical"
        " Damage</color><color=#dfa15e> ([1]+[2]% Physical Attack)</color>. When multiple missiles hit the same target,"
        " subsequent Damage is reduced by 40%.",
        "Meng Ya meluncurkan 12 rudal untuk menyerang musuh acak, masing-masing memberikan <color=#dfa15e>[0] Physical"
        " Damage</color><color=#dfa15e> ([1]+[2]% Physical Attack)</color>. Saat beberapa rudal mengenai target yang"
        " sama, damage berikutnya berkurang 40%."),
    "钩镰伤害提升至50+130%物理攻击力": (
        "Hook sickle damage increased to 50+130% Physical Attack",
        "Damage hook sickle meningkat menjadi 50+130% Physical Attack"),

    # Achievements 1.7.0.1 added.
    "在10局比赛中，使用过阵容推荐": (
        "Use Lineup Recommendation in 10 matches", "Gunakan Rekomendasi Lineup dalam 10 pertandingan"),
    "在50局比赛中，使用过阵容推荐": (
        "Use Lineup Recommendation in 50 matches", "Gunakan Rekomendasi Lineup dalam 50 pertandingan"),
    "在100局比赛中，使用过阵容推荐": (
        "Use Lineup Recommendation in 100 matches", "Gunakan Rekomendasi Lineup dalam 100 pertandingan"),
    "累计夺冠100场": ("Win the Championship 100 times in total", "Raih Juara total 100 kali"),
    "累计夺冠500场": ("Win the Championship 500 times in total", "Raih Juara total 500 kali"),
    "累计夺冠1000场": ("Win the Championship 1,000 times in total", "Raih Juara total 1.000 kali"),
    "在万象大赛的单个回合中，通过装备【驱雷】击杀至少5名友方英雄": (
        "Defeat at least 5 allied heroes using the [Thunder Drive] Equipment in a single Round of the ACE Tournament.",
        "Defeat setidaknya 5 hero ally menggunakan Equipment [Thunder Drive] dalam satu Ronde ACE Tournament."),
    "在钻石狂潮中，近10场比赛的盈亏总额": (
        "Total profit and loss in the last 10 Diamond Frenzy games",
        "Total untung dan rugi dalam 10 game Diamond Frenzy terakhir"),
    "集齐线条小狗1个天幕、1张名片、1个传送特效、1个头像框、1个聊天气泡和5个表情": (
        "Collect 1 Line Puppy Sky Screen, 1 Nameplate, 1 Teleport Effect, 1 Avatar Frame, 1 Chat Bubble and 5 Emotes",
        "Kumpulkan 1 Sky Screen, 1 Nameplate, 1 Efek Teleportasi, 1 Bingkai Avatar, 1 Chat Bubble, dan 5 Emote Line"
        " Puppy"),
    "完成1局超级英雄": ("Complete 1 Super Hero match", "Selesaikan 1 pertandingan Super Hero"),
    "完成3局超级英雄": ("Complete 3 Super Hero matches", "Selesaikan 3 pertandingan Super Hero"),
    "超级英雄进入前3名": ("Finish in the top 3 in Super Hero", "Masuk 3 besar di Super Hero"),
    "星级根据完成人数动态变化,完成人数越少,星级越高": (
        "The star rating changes with the number of players who complete it: the fewer players, the higher the stars",
        "Rating bintang berubah sesuai jumlah pemain yang menyelesaikannya: makin sedikit pemain, makin tinggi"
        " bintangnya"),

    # Super Hero: the mode 1.7.0.1 added, and its event.
    "新玩法超级英雄": ("New Mode: Super Hero", "Mode Baru: Super Hero"),
    "超快成长！养出超级英雄": ("Super-fast growth! Raise a Super Hero", "Tumbuh super cepat! Bentuk Super Hero"),
    "超级英雄活动奖励": ("Super Hero Event Rewards", "Hadiah Event Super Hero"),
    "<color=#98cbff>一、活动规则</color>\n<color=#FFFFFF>1、完成超级英雄对局任务即可领取钻石奖励。</color>": (
        "<color=#98cbff>I. Event Rules</color>\n<color=#FFFFFF>1. Complete Super Hero match missions to claim Diamond"
        " rewards.</color>",
        "<color=#98cbff>I. Aturan Event</color>\n<color=#FFFFFF>1. Selesaikan misi pertandingan Super Hero untuk klaim"
        " hadiah Diamond.</color>"),
    "超级周末：每天前{1}次翻出钻石翻倍（{0} / {1}）": (
        "Super Weekend: Diamonds from your first {1} flips each day are doubled ({0} / {1})",
        "Super Weekend: Diamond dari {1} balik kartu pertama setiap hari jadi ganda ({0} / {1})"),

    # Strategy tags on the Chessplayer and Hero guides (tables B990CF372E5633C5, 5560E5A826433EFA): a short
    # label on a narrow chip, worded like the catalog's own tags there ("Keyword: Prepare", "Group Upgrade").
    "6级天赋": ("Level 6 Talent", "Talent Level 6"),
    "三分牌加等级": ("Three Kingdoms Cards Gain Levels", "Kartu Three Kingdoms Naik Level"),
    "使用古币复活": ("Revive with Ancient Coins", "Revive dengan Ancient Coins"),
    "保护图腾": ("Protect Totems", "Lindungi Totem"),
    "保护队友": ("Protect Allies", "Lindungi Ally"),
    "关键词开团": ("Keyword: Initiate", "Kata Kunci: Initiate"),
    "关键词登场": ("Keyword: Deploy", "Kata Kunci: Deploy"),
    "养成海月": ("Build Up Haya", "Kembangkan Haya"),
    "冻结英雄": ("Freeze Heroes", "Bekukan Hero"),
    "减少廉颇蓝条": ("Reduce Lian Po's Mana Bar", "Kurangi Mana Bar Lian Po"),
    "减少法力值": ("Reduce Mana", "Kurangi Mana"),
    "减少蒙恬蓝条": ("Reduce Meng Tian's Mana Bar", "Kurangi Mana Bar Meng Tian"),
    "前期过渡": ("Early-Game Transition", "Transisi Early-Game"),
    "变为高阶": ("Become High Tier", "Jadi Tier Tinggi"),
    "合成同阶升级": ("Combine Same Tier to Upgrade", "Combine Tier Sama untuk Upgrade"),
    "后期王牌": ("Late-Game Ace", "Ace Late-Game"),
    "回蓝更快召唤": ("Faster Mana, Faster Summons", "Mana Cepat, Summon Cepat"),
    "回血保护队友": ("Heal to Protect Allies", "Heal untuk Lindungi Ally"),
    "增加临时等级": ("Increase Temporary Level", "Naikkan Temporary Level"),
    "增加召唤物伤害": ("Increase Summon Damage", "Naikkan Damage Summon"),
    "增加廉颇生命": ("Increase Lian Po's HP", "Naikkan HP Lian Po"),
    "增加攻击": ("Increase Attack", "Naikkan Attack"),
    "增加核心等级": ("Increase Core Level", "Naikkan Level Core"),
    "复活": ("Revive", "Revive"),
    "复活增加容错": ("Revive for Margin of Error", "Revive untuk Toleransi Kesalahan"),
    "小兵爆炸伤害": ("Soldier Explosion Damage", "Damage Ledakan Prajurit"),
    "快速释放技能": ("Fast Skill Casting", "Skill Cepat"),
    "提供刷新": ("Grants Refreshes", "Memberikan Refresh"),
    "提供召唤物": ("Grants Summons", "Memberikan Summon"),
    "提供增益": ("Grants Buffs", "Memberikan Buff"),
    "攻击群体升级": ("Attacks Upgrade the Group", "Serangan Upgrade Grup"),
    "整备触发登场": ("Prepare Triggers Deploy", "Prepare Memicu Deploy"),
    "炸盾造成伤害": ("Shield Burst Deals Damage", "Shield Burst Memberikan Damage"),
    "登场增加等级": ("Deploy Increases Level", "Deploy Menaikkan Level"),
    "登场提供古币": ("Deploy Provides Ancient Coins", "Deploy Memberikan Ancient Coins"),
    "登场给效果牌": ("Deploy Grants Effect Card", "Deploy Memberikan Kartu Efek"),
    "群体爆炸": ("Group Explosion", "Ledakan Grup"),
    "买牌得效果牌": ("Buy Cards for Effect Cards", "Beli Kartu dapat Kartu Efek"),
    "关键牌一分为二": ("Split a Key Card in Two", "Belah Kartu Kunci Jadi Dua"),
    "养成无敌王牌": ("Build an Invincible Ace", "Kembangkan Ace Tak Terkalahkan"),
    "冻结低阶变高阶": ("Freeze Low Tier into High Tier", "Bekukan Tier Rendah jadi Tier Tinggi"),
    "升级附加属性": ("Upgrade Bonus Stats", "Upgrade Bonus Atribut"),
    "召唤敌方最强英雄": ("Summon the Enemy's Strongest Hero", "Summon Hero Terkuat Musuh"),
    "召唤随机英雄": ("Summon Random Heroes", "Summon Hero Acak"),
    "回溯卡牌": ("Rewind Cards", "Putar Balik Kartu"),
    "回环打出2次卡牌": ("Loop: Play Cards Twice", "Loop: Mainkan Kartu 2 Kali"),
    "场外火力支持": ("Off-Field Fire Support", "Dukungan Tembakan dari Luar"),
    "增加王牌等级": ("Increase Ace Level", "Naikkan Level Ace"),
    "增强链接英雄": ("Empower the Linked Hero", "Perkuat Hero Terhubung"),
    "复制不断": ("Endless Copies", "Salin Tanpa Henti"),
    "复制场上英雄": ("Copy Heroes on the Board", "Salin Hero di Papan"),
    "复制敌方英雄牌": ("Copy Enemy Hero Cards", "Salin Kartu Hero Musuh"),
    "大量买牌": ("Buy Lots of Cards", "Beli Banyak Kartu"),
    "小鹿前排承伤": ("Deer Tanks in Front Row", "Rusa Menahan Damage di Depan"),
    "小鹿阵亡均分等级": ("Fallen Deer Shares Its Levels", "Rusa Gugur Membagi Level"),
    "布置3种机关": ("Place 3 Kinds of Mechanisms", "Pasang 3 Jenis Mekanisme"),
    "掌控全局": ("Control the Whole Game", "Kuasai Seluruh Permainan"),
    "提供位移": ("Grants Mobility", "Memberikan Mobilitas"),
    "提供吸血免控": ("Grants Lifesteal and CC Immunity", "Memberikan Lifesteal dan Kebal CC"),
    "提供群体等级": ("Grants Group Levels", "Memberikan Level Grup"),
    "提供阵营效果牌": ("Grants Faction Effect Cards", "Memberikan Kartu Efek Faction"),
    "无限买卖": ("Endless Buying and Selling", "Jual Beli Tanpa Batas"),
    "机关效果多样": ("Varied Mechanism Effects", "Efek Mekanisme Beragam"),
    "灵活多变": ("Flexible", "Fleksibel"),
    "经济倒转": ("Economy Reversal", "Pembalikan Ekonomi"),
    "群体增加等级": ("Group Level Increase", "Naikkan Level Grup"),
    "群体英雄升级": ("Group Hero Upgrade", "Upgrade Hero Grup"),
    "群体英雄增伤": ("Group Hero Damage Boost", "Boost Damage Hero Grup"),
    "能量刷新二选一": ("Energy Refresh: Choose 1 of 2", "Refresh Energy: Pilih 1 dari 2"),
    "获取同阵营英雄": ("Get Same-Faction Heroes", "Dapatkan Hero Faction Sama"),
    "获得随机宝藏": ("Gain Random Treasures", "Dapatkan Harta Acak"),
    "超速觉醒": ("Rapid Awakening", "Awaken Super Cepat"),
    "选择四种武器": ("Choose from Four Weapons", "Pilih dari Empat Senjata"),
    "阵容瞬间成型": ("Lineup Forms Instantly", "Lineup Langsung Terbentuk"),
    "额外获得阵营天赋": ("Extra Faction Talent", "Talent Faction Tambahan"),
    "飞行器可输出": ("Aircraft Deals Damage", "Pesawat Memberikan Damage"),
    "初始阵容系列": ("Starting Lineup Series", "Seri Lineup Awal"),
    "已使用古币": ("Ancient Coins used", "Ancient Coin terpakai"),
    "猛虎擂台吸收": ("Tiger Arena absorbed", "Diserap Tiger Arena"),
    "装备知识": ("Equipment Knowledge", "Pengetahuan Equipment"),

    # Room settings and King of Kings matchmaking (1.7.0.1).
    "{0}的亲密关系进入了房间": ("An Intimate Relationship of {0} entered the room", "Hubungan Dekat {0} masuk ke room"),
    "{0}的好友进入了房间": ("A friend of {0} entered the room", "Teman {0} masuk ke room"),
    "以后不会弹出": ("This won't pop up again", "Ini tidak akan muncul lagi"),
    "开启本功能后，在匹配成功后将会自动接受匹配": (
        "When on, matches are accepted automatically once found",
        "Saat aktif, pertandingan otomatis diterima begitu ditemukan"),
    "关闭本功能后，在匹配成功后将不再自动接受匹配": (
        "When off, matches are no longer accepted automatically once found",
        "Saat nonaktif, pertandingan tidak lagi otomatis diterima begitu ditemukan"),
    "匹配中，无法进行设置": ("Can't change settings while matchmaking", "Tidak bisa mengubah pengaturan saat mencari pertandingan"),
    "只有房主可以设置房间匹配规则": (
        "Only the room owner can set the room's matchmaking rules",
        "Hanya pemilik room yang bisa mengatur aturan matchmaking room"),
    "处于队伍中，无法进行祈愿": ("Can't Wish while in a team", "Tidak bisa Doa saat berada di tim"),
    "当前处于组队状态，将无法触发王中王组队": (
        "You're in a team, so a King of Kings team can't be formed",
        "Kamu sedang dalam tim, jadi tim King of Kings tidak bisa dibentuk"),
    "房主关闭了{0}设置": ("The room owner turned off the {0} setting", "Pemilik room menonaktifkan pengaturan {0}"),
    "房主开启了{0}设置": ("The room owner turned on the {0} setting", "Pemilik room mengaktifkan pengaturan {0}"),
    "更换房主后，{0}已关闭": ("The room owner changed; {0} is now off", "Pemilik room berganti; {0} kini nonaktif"),
    "更换房主后，{0}已开启": ("The room owner changed; {0} is now on", "Pemilik room berganti; {0} kini aktif"),
    "房间内已有最强王者段位或已开启王中王的玩家，暂时无法设置此项": (
        "A player in the room is Strongest King rank or has unlocked King of Kings, so this can't be set for now",
        "Ada pemain di room dengan rank Strongest King atau yang sudah membuka King of Kings, jadi ini belum bisa"
        " diatur"),
    "该玩家设置了不允许任何人免邀请进入房间": (
        "This player doesn't allow anyone to join their room without an invitation",
        "Pemain ini tidak mengizinkan siapa pun masuk ke room-nya tanpa undangan"),
    "该玩家设置了仅允许亲密关系免邀请进入房间": (
        "This player only allows Intimate Relationships to join their room without an invitation",
        "Pemain ini hanya mengizinkan Hubungan Dekat masuk ke room-nya tanpa undangan"),
    "队伍加入了王者或王中王玩家，{0}玩家设置将不可用": (
        "An Honor or King of Kings player joined the team; the {0} player setting is unavailable",
        "Pemain Honor atau King of Kings bergabung ke tim; pengaturan pemain {0} tidak tersedia"),
    "队伍已无王者或王中王玩家，{0}玩家设置已可用": (
        "The team no longer has an Honor or King of Kings player; the {0} player setting is available",
        "Tim tidak lagi punya pemain Honor atau King of Kings; pengaturan pemain {0} tersedia"),
    "确认后将关闭王中王组队功能：加入王中王队伍、挑战者队伍可获得有分同享效果。单人挑战可获得胜利多加分，失败不扣分效果。": (
        "Confirming turns off King of Kings teaming. Joining a King of Kings team or a challenger team grants Shared"
        " Score; challenging solo grants extra points on a win and no point loss on a defeat.",
        "Konfirmasi akan menonaktifkan tim King of Kings. Bergabung ke tim King of Kings atau tim penantang memberikan"
        " Shared Score; menantang solo memberikan poin tambahan saat menang dan tidak mengurangi poin saat kalah."),
    "带队获胜": ("Won as Captain", "Menang sebagai Kapten"),
    "独自获胜": ("Won Solo", "Menang Solo"),
    "平均得分": ("Average Score", "Skor Rata-rata"),
    "战力保护": ("Combat Power Protection", "Proteksi Combat Power"),
    "暂无最近一起玩过的玩家": ("No players you've played with recently", "Belum ada pemain yang baru-baru ini main bersamamu"),
    "最近": ("Recent", "Terbaru"),
    "本局事件：{0}": ("Match Event: {0}", "Event Pertandingan: {0}"),
    "本局奖池：{0}": ("Match Prize Pool: {0}", "Prize Pool Pertandingan: {0}"),
    "本赛季尚未参加排位赛": ("You haven't played Ranked this season", "Kamu belum main Ranked di season ini"),
    "等待最终排名结算中": ("Waiting for the final ranking", "Menunggu peringkat akhir"),
    "该玩法不可用": ("This mode is unavailable", "Mode ini tidak tersedia"),
    "获奖总人次": ("Total Winners", "Total Pemenang"),
    "正在配置棋手皮肤、棋盘皮肤": (
        "Setting up Chessplayer and chessboard skins", "Menyiapkan skin Chessplayer dan skin papan catur"),
    "%s挑战了您的夺冠阵容，挑战失败，恭喜您获得胜利。": (
        "%s challenged your Championship Lineup but failed. Congratulations on your Victory.",
        "%s menantang Lineup Juara kamu tetapi gagal. Selamat atas Kemenanganmu."),
    "房主可以设置不匹配王中王玩家": (
        "The room owner can choose not to match King of Kings players",
        "Pemilik room bisa memilih untuk tidak dicocokkan dengan pemain King of Kings"),
    "这里可以对房间进行设置": ("Set up the room here", "Atur room di sini"),
    "这里可以设置允许主动进入房间的玩家类型": (
        "Choose here which players may join the room on their own",
        "Pilih di sini pemain mana yang boleh masuk ke room sendiri"),
    "这里可以设置是否允许玩家加入我的王中王队伍": (
        "Choose here whether players may join your King of Kings team",
        "Pilih di sini apakah pemain boleh bergabung ke tim King of Kings-mu"),
    "这里可以设置是否自动接受匹配": (
        "Choose here whether to auto-accept matches", "Pilih di sini apakah pertandingan diterima otomatis"),
    "<color=#98cbff>一、房间设置</color>\n<color=#FFFFFF>房间设置用于调整您的房间准入与对局匹配规则，可在创建房间时进行设置。\n具体规则如下：\n1、自动接受匹配\n开启后，在对局匹配成功时，会自动接受匹配，无需手动确认。\n2、免邀请进入房间\n可设置为允许好友、亲密关系免邀请直接进入您的房间；\n关闭该功能后，任何人都不允许直接进入您的房间。\n3、允许玩家加入我的王中王队伍\n当王中王玩家以王中王小号创建房间后，若房间人数=1时，会出现组队开关；\n勾选后，您将在\"挑战王中王\"中做为队长组队作战；\n取消勾选后，您将在\"挑战王中王\"中单人作战。\n4、不匹配王中王玩家\n仅至尊星耀及以下玩家可用，段位抵达王者或解锁王中王后，该功能无法再进行设置。\n开启该设置后，您在匹配对局中将不会匹配到任何王中王玩家。</color>": (
        "<color=#98cbff>I. Room Settings</color>\n<color=#FFFFFF>Room settings adjust who may enter your room and how"
        " its matches are made. Set them when you create a room.\nThe rules are as follows:\n1. Auto-accept matches\n"
        "When on, a match is accepted automatically once found, with no manual confirmation.\n2. Join without an"
        " invitation\nYou can allow friends and Intimate Relationships to enter your room directly without an"
        " invitation;\nwhen this is off, no one may enter your room directly.\n3. Allow players to join my King of"
        " Kings team\nWhen a King of Kings player creates a room with their King of Kings sub-account and the room has"
        " 1 player, a team switch appears;\nwhen ticked, you fight as the Captain of a team in \"Challenge the King of"
        " Kings\";\nwhen unticked, you fight solo in \"Challenge the King of Kings\".\n4. Don't match King of Kings"
        " players\nAvailable only to players at Supreme Star or below; once you reach Honor rank or unlock King of"
        " Kings, this can no longer be set.\nWhen on, you will not be matched with any King of Kings player.</color>",
        "<color=#98cbff>I. Pengaturan Room</color>\n<color=#FFFFFF>Pengaturan room mengatur siapa yang boleh masuk ke"
        " room-mu dan aturan matchmaking-nya. Atur saat membuat room.\nAturannya sebagai berikut:\n1. Terima"
        " pertandingan otomatis\nSaat aktif, pertandingan otomatis diterima begitu ditemukan, tanpa konfirmasi"
        " manual.\n2. Masuk tanpa undangan\nKamu bisa mengizinkan teman dan Hubungan Dekat masuk langsung ke room-mu"
        " tanpa undangan;\nsaat nonaktif, tidak ada yang boleh masuk langsung ke room-mu.\n3. Izinkan pemain bergabung"
        " ke tim King of Kings-ku\nSaat pemain King of Kings membuat room dengan sub-akun King of Kings dan room berisi"
        " 1 pemain, muncul tombol tim;\njika dicentang, kamu bertarung sebagai Kapten tim di \"Challenge the King of"
        " Kings\";\njika tidak dicentang, kamu bertarung solo di \"Challenge the King of Kings\".\n4. Jangan cocokkan"
        " dengan pemain King of Kings\nHanya untuk pemain Supreme Star ke bawah; setelah mencapai rank Honor atau"
        " membuka King of Kings, ini tidak bisa diatur lagi.\nSaat aktif, kamu tidak akan dicocokkan dengan pemain King"
        " of Kings mana pun.</color>"),

    # Lineup Recommendation: the rework that picks a Chessplayer first.
    "阵容推荐改版说明": ("Lineup Recommendation Revamp Notes", "Catatan Pembaruan Rekomendasi Lineup"),
    "阵容推荐系统改造为先选择棋手，再展示阵容。": (
        "Lineup Recommendation now asks you to choose a Chessplayer first, then shows its lineups.",
        "Rekomendasi Lineup kini memintamu memilih Chessplayer dulu, lalu menampilkan lineup-nya."),
    "阵容系统将由固定栏位调整为每位棋手独立持有对应数量的栏位。版本更新前已解锁的阵容栏位会折算为等量栏位扩充卡，通过邮件发放。": (
        "Lineup slots change from a fixed set to slots held by each Chessplayer separately. Lineup slots unlocked"
        " before the update are converted into the same number of Slot Expansion Cards and sent by mail.",
        "Slot lineup berubah dari jumlah tetap menjadi slot yang dimiliki tiap Chessplayer secara terpisah. Slot lineup"
        " yang dibuka sebelum update diubah menjadi Slot Expansion Card dalam jumlah yang sama dan dikirim lewat"
        " mail."),
    "阵容投稿时必填内容如下：\n1、至少添加2个及以上英雄\n2、至少编辑1个阵容核心标签（王牌、坦克核心、功能核心）\n3、有填写阵容标题和阵容描述\n4、至少有1个英雄穿戴装备": (
        "A lineup submission must include:\n1. At least 2 Heroes\n2. At least 1 lineup core tag (Ace, Tank Core,"
        " Functional Core)\n3. A lineup title and lineup description\n4. At least 1 Hero wearing Equipment",
        "Pengiriman lineup wajib berisi:\n1. Minimal 2 Hero\n2. Minimal 1 tag core lineup (Ace, Tank Core, Functional"
        " Core)\n3. Judul lineup dan deskripsi lineup\n4. Minimal 1 Hero memakai Equipment"),
    "已投稿": ("Submitted", "Terkirim"),
    "已替换": ("Replaced", "Diganti"),
    "尝新棋手": ("Try New Chessplayers", "Coba Chessplayer Baru"),
    "攻略面板": ("Guide Panel", "Panel Panduan"),
    "新建棋手阵容": ("New Chessplayer Lineup", "Lineup Chessplayer Baru"),
    "无推荐阵容": ("No recommended lineups", "Tidak ada lineup rekomendasi"),
    "棋手无推荐阵容": ("This Chessplayer has no recommended lineups", "Chessplayer ini tidak punya lineup rekomendasi"),
    "收藏{0}阵容成功": ("Saved the {0} lineup to Favorites", "Lineup {0} berhasil disimpan ke Favorit"),
    "该阵容未推荐当前棋手，无法收藏": (
        "This lineup isn't recommended for the current Chessplayer and can't be saved to Favorites",
        "Lineup ini tidak direkomendasikan untuk Chessplayer saat ini dan tidak bisa disimpan ke Favorit"),
    "该阵容未配置推荐棋手，无法收藏": (
        "This lineup has no recommended Chessplayer and can't be saved to Favorites",
        "Lineup ini tidak punya Chessplayer rekomendasi dan tidak bisa disimpan ke Favorit"),
    "确认棋手后刷新出对应阵容": (
        "Confirm a Chessplayer to show its lineups", "Konfirmasi Chessplayer untuk menampilkan lineup-nya"),
    "这是棋手适配的阵容": ("These are lineups suited to the Chessplayer", "Ini lineup yang cocok untuk Chessplayer"),
    "这里是棋手列表": ("This is the Chessplayer list", "Ini daftar Chessplayer"),
    "选择一套阵容": ("Choose a lineup", "Pilih lineup"),
    "输入阵容名称": ("Enter lineup name", "Masukkan nama lineup"),
    "简介": ("Overview", "Ringkasan"),
    "克制关系": ("Counters", "Counter"),
    "【克制关系】": ("[Counters]", "[Counter]"),
    "请输入克制关系": ("Enter counters", "Masukkan counter"),
    "<color=#98cbff>一、生涯系统说明</color>\n\n1、生涯系统承载了您的各项游戏数据，可在主页面进行查看：游玩时长、对局总场次、获得点赞次数、王者印记拥有数量、本赛季棋手数据、成就数据以及账号的对局数据等内容。": (
        "<color=#98cbff>I. Career System Overview</color>\n\n1. The Career System records your various game data,"
        " viewable on the main page: playtime, total matches played, Likes received, Mark of Kings owned, this season's"
        " Chessplayer data, Achievement data, your account's match data and more.",
        "<color=#98cbff>I. Ikhtisar Career System</color>\n\n1. Career System mencatat berbagai data game-mu, yang bisa"
        " dilihat di halaman utama: waktu bermain, total pertandingan, Like yang diterima, jumlah Mark of Kings, data"
        " Chessplayer season ini, data Achievement, data pertandingan akunmu, dan lainnya."),

    # Ace Duel schedules.
    "王牌对决·万象大赛在每天16:00-23:00开启，每整点在备战区段位分排名前列的玩家中随机确认6名玩家开启1场对局。参与选手对局排位分按五倍计算（输赢都按基础得分的五倍计算）。对局时刻如下：": (
        "Ace Duel · ACE Tournament opens daily from 16:00-23:00. On every hour, 6 players are picked at random from"
        " the top-ranked players by Rank points in the Prepare area for 1 match. Participants' Ranked points count five"
        " times (wins and losses both count at five times the base score). Match times are as follows:",
        "Ace Duel · ACE Tournament dibuka setiap hari pukul 16:00-23:00. Setiap jam tepat, 6 pemain dipilih acak dari"
        " pemain dengan poin Rank teratas di area Prepare untuk 1 pertandingan. Poin Ranked peserta dihitung lima kali"
        " lipat (menang maupun kalah dihitung lima kali skor dasar). Jadwal pertandingan sebagai berikut:"),
    "王牌对决·钻石狂潮在每天12:00-15:00开启，每整点在备战区总盈利钻石数排名前列的玩家中随机确认6名玩家开启1场对局。对局固定带入50000钻石。对局时刻如下：": (
        "Ace Duel · Diamond Frenzy opens daily from 12:00-15:00. On every hour, 6 players are picked at random from the"
        " top-ranked players by total Diamond profit in the Prepare area for 1 match. Each match has a fixed stake of"
        " 50000 Diamonds. Match times are as follows:",
        "Ace Duel · Diamond Frenzy dibuka setiap hari pukul 12:00-15:00. Setiap jam tepat, 6 pemain dipilih acak dari"
        " pemain dengan total keuntungan Diamond teratas di area Prepare untuk 1 pertandingan. Setiap pertandingan"
        " punya taruhan tetap 50000 Diamond. Jadwal pertandingan sebagai berikut:"),

    # Events, shop and gifts.
    "<color=#98cbff>一、活动规则</color>\n<color=#FFFFFF>1、在对局中遇到王中王玩家即可领取奖励，包含自己。</color>\n<color=#FFFFFF>2、对局仅限万象大赛。</color>": (
        "<color=#98cbff>I. Event Rules</color>\n<color=#FFFFFF>1. Meet a King of Kings player in a match (including"
        " yourself) to claim the reward.</color>\n<color=#FFFFFF>2. ACE Tournament matches only.</color>",
        "<color=#98cbff>I. Aturan Event</color>\n<color=#FFFFFF>1. Bertemu pemain King of Kings dalam pertandingan"
        " (termasuk diri sendiri) untuk klaim hadiah.</color>\n<color=#FFFFFF>2. Hanya pertandingan ACE"
        " Tournament.</color>"),
    "<color=#98cbff>一、活动规则</color>\n<color=#FFFFFF>1、完成每日登录和对局任务即可领取蔷薇币奖励。</color>\n<color=#FFFFFF>2、活动任务将在每日0点刷新。</color>": (
        "<color=#98cbff>I. Event Rules</color>\n<color=#FFFFFF>1. Complete the daily login and match tasks to claim Rose"
        " Coin rewards.</color>\n<color=#FFFFFF>2. Event tasks reset daily at 0:00.</color>",
        "<color=#98cbff>I. Aturan Event</color>\n<color=#FFFFFF>1. Selesaikan tugas login harian dan pertandingan untuk"
        " klaim hadiah Rose Coin.</color>\n<color=#FFFFFF>2. Tugas Event di-reset setiap hari pukul 0:00.</color>"),
    "线条小狗天幕祈愿即将下线": ("Line Puppy Sky Screen Wish ends soon", "Doa Sky Screen Line Puppy segera berakhir"),
    "每{0}抽（<color=#ED6962>{1}</color>/{0}）可领1个自选礼包，已选自选礼包<color=#ED6962>{2}</color>/{3}个": (
        "Claim 1 Selectable Gift Pack every {0} draws (<color=#ED6962>{1}</color>/{0}). Selectable Gift Packs chosen:"
        " <color=#ED6962>{2}</color>/{3}",
        "Klaim 1 Gift Pack Pilihan setiap {0} tarikan (<color=#ED6962>{1}</color>/{0}). Gift Pack Pilihan dipilih:"
        " <color=#ED6962>{2}</color>/{3}"),
    "购买<color=#ed6962ff>{0}x{1}</color>，可获赠<color=#ed6962ff>{2}x{3}</color>，可参与祈愿获得奖励": (
        "Buy <color=#ed6962ff>{0}x{1}</color> to receive <color=#ed6962ff>{2}x{3}</color> for Wishes that earn rewards",
        "Beli <color=#ed6962ff>{0}x{1}</color> untuk mendapat <color=#ed6962ff>{2}x{3}</color> yang bisa dipakai Doa"
        " untuk mendapat hadiah"),
    "新手礼包": ("Starter Pack", "Paket Pemula"),
    "打开礼包必定获得：夺宝币*24，改名卡*1、高级点心礼盒*1。": (
        "Opening the pack always grants: Treasure Coin x24, Rename Card x1, Advanced Snack Box x1.",
        "Membuka paket pasti memberikan: Treasure Coin x24, Kartu Ganti Nama x1, Advanced Snack Box x1."),
    "自选棋手体验卡（3天）": ("Selectable Chessplayer Trial Card (3 Days)", "Kartu Trial Chessplayer Pilihan (3 Hari)"),
    "从姜导，镜，明先生，昭君，阿离，安琪拉6个棋手中，选择1个获得一张3天体验卡！": (
        "Choose 1 of 6 Chessplayers: Director Jiang, Jing, Mr. Ming, Zhaojun, Arli and Angela, and get a 3-day Trial"
        " Card!",
        "Pilih 1 dari 6 Chessplayer: Director Jiang, Jing, Mr. Ming, Zhaojun, Arli, dan Angela, dan dapatkan Kartu"
        " Trial 3 hari!"),
    "留存治愈时刻，把线条小狗的快乐打包送出。赠送可增加 10 点亲密度。「小狗限定快照」": (
        "Keep a healing moment and send Line Puppy's joy as a gift. Send to increase Intimacy by 10. \"A puppy-only"
        " snapshot\"",
        "Simpan momen yang menenangkan dan kirim kebahagiaan Line Puppy sebagai hadiah. Kirim untuk menambah Intimacy"
        " sebesar 10. \"Foto khusus anak anjing\""),
    "获得“接收心心”个性戳戳1天使用权，在定制系统中装配后可在组队房间内使用。": (
        "Obtain 1-day Usage rights for the \"Receive Hearts\" Personalized Poke. Equip it in the Custom System to use"
        " it in team rooms.",
        "Dapatkan hak pakai 1 hari untuk Personalized Poke \"Terima Hati\". Pasang di Sistem Kustomisasi untuk"
        " menggunakannya di room tim."),
    "获得“接收心心”个性戳戳30天使用权，在定制系统中装配后可在组队房间内使用。": (
        "Obtain 30-day Usage rights for the \"Receive Hearts\" Personalized Poke. Equip it in the Custom System to use"
        " it in team rooms.",
        "Dapatkan hak pakai 30 hari untuk Personalized Poke \"Terima Hati\". Pasang di Sistem Kustomisasi untuk"
        " menggunakannya di room tim."),
    "获得“接收心心”个性戳戳365天使用权，在定制系统中装配后可在组队房间内使用。": (
        "Obtain 365-day Usage rights for the \"Receive Hearts\" Personalized Poke. Equip it in the Custom System to"
        " use it in team rooms.",
        "Dapatkan hak pakai 365 hari untuk Personalized Poke \"Terima Hati\". Pasang di Sistem Kustomisasi untuk"
        " menggunakannya di room tim."),
    "获得“接收心心”个性戳戳，使用后可一直生效，在定制系统中装配后可在组队房间内使用。": (
        "Obtain the \"Receive Hearts\" Personalized Poke. Once used, it remains permanently active. Equip it in the"
        " Custom System to use it in team rooms.",
        "Dapatkan Personalized Poke \"Terima Hati\". Setelah digunakan, aktif secara permanen. Pasang di Sistem"
        " Kustomisasi untuk menggunakannya di room tim."),

    # Music titles.
    "We Are（我们）": ("We Are", "We Are"),
    "听从裙摆": ("Follow the Hem", "Ikuti Ayunan Rok"),
    "我们·一直都在": ("Us · Always Here", "Kita · Selalu Ada"),
    "我们·为你而来": ("Us · Here for You", "Kita · Datang untukmu"),
    "王牌加冕": ("Crowning the Ace", "Penobatan Sang Ace"),

    # Yuhuan's skin Prismatic Scale.
    "幻彩音阶": ("Prismatic Scale", "Prismatic Scale"),
    "幻彩音阶名片": ("Prismatic Scale Nameplate", "Nameplate Prismatic Scale"),
    "她的琴音看得见——字面意义上的。": ("You can see her music, literally.", "Musiknya bisa dilihat, secara harfiah."),
    "玉环的舞台，在大厦最豪华的演播厅。\n\n据说，玉环的琴由这个时代最先进的光谱材料构造，能为观众带来如梦似幻的可视化演出。\n在她演奏的时候，一个个可爱的音符光影随着音乐起舞，时而聚作璀璨星河，时而散作漫天流萤。\n仅玉环一人一琴，便可以完成这场既生动又热闹的演出。\n\n“这绝对是这个时代最伟大的发明！”\n“我起猛了，竟然看到音符飞起来了！”\n“这个八分音符摸起来凉凉的耶！”\n\n玉环的舞台，可以在任何地方。\n\n天桥上的风有点大，少女的抽泣声碎在风里。她抱着琴走过去，没说话，挨着少女坐下。\n手指一拨，几个暖橙色的音符跳出来，在傍晚的空气里晕开。\n她弹得轻，音符却很聪明，像活泼的精灵，围绕在少女身边。\n一个音符绕着她飞了一圈，带走她脸上的点点泪光，然后飞到天上，融成了晚霞。\n\n“你的琴，竟然有这样的魔力？我好像没有那么难过了。”\n少女停止了哭泣，看着玉环的眼睛。\n玉环停下手指，微笑着点了点头": (
        "Yuhuan's stage is the grandest studio in the tower.\n\nThey say Yuhuan's instrument is built from this era's"
        " most advanced spectral materials, giving the audience a dreamlike visual show.\nAs she plays, lovely notes of"
        " light dance to the music, now gathering into a glittering galaxy, now scattering like a sky full of"
        " fireflies.\nYuhuan alone, with one instrument, can put on a show this vivid and lively.\n\n\"This has to be"
        " the greatest invention of our time!\"\n\"Am I dreaming? I just saw the notes fly!\"\n\"This eighth note feels"
        " cool to the touch!\"\n\nYuhuan's stage can be anywhere.\n\nThe wind on the footbridge was strong, and a girl's"
        " sobs broke apart in it. Yuhuan walked over with her instrument, said nothing, and sat down beside her.\nWith"
        " one pluck, a few warm orange notes leapt out and spread through the evening air.\nShe played softly, yet the"
        " notes were clever, circling the girl like lively sprites.\nOne note flew a loop around her, carried away the"
        " tears on her face, then rose into the sky and melted into the sunset.\n\n\"Your instrument has magic like"
        " this? I don't feel so sad anymore.\"\nThe girl stopped crying and looked into Yuhuan's eyes.\nYuhuan rested"
        " her fingers, smiled and nodded",
        "Panggung Yuhuan ada di studio termegah di menara.\n\nKonon, alat musik Yuhuan dibuat dari material spektrum"
        " tercanggih di zaman ini, menghadirkan pertunjukan visual bak mimpi bagi penonton.\nSaat ia bermain, not-not"
        " cahaya yang lucu menari mengikuti musik, kadang berkumpul menjadi galaksi berkilauan, kadang menyebar seperti"
        " kunang-kunang memenuhi langit.\nHanya Yuhuan seorang dengan satu alat musik, pertunjukan yang hidup dan"
        " meriah ini pun tercipta.\n\n\"Ini pasti penemuan terhebat di zaman ini!\"\n\"Aku mimpi, ya? Aku lihat not-not"
        " itu terbang!\"\n\"Not seperdelapan ini terasa dingin saat disentuh!\"\n\nPanggung Yuhuan bisa di mana"
        " saja.\n\nAngin di jembatan penyeberangan cukup kencang, dan isak tangis seorang gadis pecah terbawa angin."
        " Yuhuan menghampirinya sambil membawa alat musiknya, tanpa berkata apa-apa, lalu duduk di sampingnya.\nSekali"
        " petik, beberapa not jingga hangat melompat keluar dan menyebar di udara senja.\nIa bermain pelan, tapi"
        " not-not itu cerdik, mengelilingi sang gadis seperti peri yang lincah.\nSatu not terbang memutarinya, membawa"
        " pergi air mata di wajahnya, lalu naik ke langit dan melebur menjadi lembayung senja.\n\n\"Alat musikmu punya"
        " sihir seperti ini? Aku jadi tidak terlalu sedih lagi.\"\nGadis itu berhenti menangis dan menatap mata"
        " Yuhuan.\nYuhuan menghentikan jarinya, tersenyum, dan mengangguk"),

    # Wish and event rules 1.7.0.1 reworded: the catalog's own text with the new dates and numbers.
    "<color=#98cbff>一、时间</color>\n<color=#FFFFFF>1. 祈愿时间：2026年09月25日 00:00:00-2026年10月21日 23:59:59。\n2.兑换时间：2026年10月15日更新后-2026年10月21日 23:59:59。</color>\n\n<color=#98cbff>二、祈愿规则：</color>\n<color=#FFFFFF>1. 日月行者内有日和月两个奖池，在日奖池内消耗10点券购买1个爱心投送1天体验卡可获赠1个【金穗】，在月奖池内消耗10点券购买1个爱心投送1天体验卡可获赠1个【月桂】，可分别用于日和月奖池的抽取。\n2. 日和月奖池相互独立，每个奖池内共有9个奖品，每次祈愿必定获得其中1个奖励，奖励不会重复获得，9次之内必定获得奖池内的所有奖励。\n3. 单奖池内每次消耗的【金穗】/【月桂】数量将会递增，依次为1、4、8、12、16、24、32、48、68。\n4. 获得大奖【瑶妹·朝露晓升】或【常小娥·云舒见影】后，将赠送对应奖池内剩余所有奖励。\n5. 日月同辉：\n（1）每次抽取均有可能触发日月同辉机制，若在日奖池触发，则会获得一定数量的【月桂】，若在月奖池触发，则会获得一定数量的【金穗】；\n（2）若在日奖池触发时已获得月奖池内的所有奖励，则获得的【月桂】将会转化为等量的【金穗】，在月奖池触发时同理；\n（3）若在当抽抽取后已获得日奖池和月奖池内的所有奖励，则该机制不会触发。\n6.10月15日更新后可使用一定数量的【金穗】/【月桂】在兑换商店中兑换指定商品，祈愿结束后兑换商店也将一起关闭，请拥有【金穗】/【月桂】的玩家们及时兑换，兑换时间结束后活动道具（金穗，月桂）将被清空。\n7.日月行者奖池限时开启，抽奖进度不会被其他祈愿活动继承。</color>\n\n<color=#98cbff>三、概率公示：</color>\n<color=#FFFFFF>1、奖池综合概率：\n【日奖池】\n瑶妹-朝露晓升 5.76%\n朝露晓升名片 7.59%\n个性戳戳-晨昭鹿鸣 9.41%\n聊天气泡-升曦凝露 9.41%\n表情-鹿过 10.22%\n表情-早上好 10.22%\n夺宝币*6 15.80%\n随机特效（30天） 15.80%\n亲密度道具-朝露晓升明信片*10 15.80%\n【月奖池】\n常小娥-云舒见影 5.76%\n云舒见影名片 7.59%\n个性戳戳-云疏兔影 9.41%\n聊天气泡-月隐云踪 9.41%\n表情-ME兔 10.22%\n表情-晚安 10.22%\n夺宝币*6 15.80%\n随机特效（30天） 15.80%\n亲密度道具-云舒见影明信片*10 15.80%\n2、日月同辉概率：\n每次抽取均有可能触发，触发概率独立，为5%，触发后可能获得的代币数量及概率见下方公示\n月桂/金穗*2 60%\n月桂/金穗*4 30%\n月桂/金穗*6 10%</color>": (
        "<color=#98cbff>I. Time</color>\n<color=#FFFFFF>1. Wish period: September 25, 2026, 00:00:00 - October 21, 2026, 23:59:59.\n2. Redemption period: after the October 15, 2026 update - October 21, 2026, 23:59:59.</color>\n\n<color=#98cbff>II. Wish Rules:</color>\n<color=#FFFFFF>1. The Sun & Moon Traveler Event features two prize pools: Sun and Moon. Purchasing a 1-Day Love Delivery trial card for 10 Coupons in the Sun pool grants 1 [Golden Spike]. Purchasing a 1-Day Love Delivery trial card for 10 Coupons in the Moon pool grants 1 [Laurel]. These can be used to draw from their respective pools.\n2. The Sun and Moon pools are independent. Each contains 9 rewards. Each Wish guarantees 1 reward, with no duplicates. All rewards in a pool are guaranteed within 9 draws.\n3. The cost of [Golden Spike]/[Laurel] per draw increases within a single pool: 1, 4, 8, 12, 16, 24, 32, 48, 68.\n4. Obtaining the grand prize [Yaria: Morning Dew] or [Chang Xiao'e: Cloud Shadow] grants all Remaining rewards in that pool.\n5. Sun & Moon Radiance:\n(1) Every draw has a chance to Trigger the Sun & Moon Radiance mechanic. If triggered in the Sun pool, you receive a certain amount of [Laurel]. If triggered in the Moon pool, you receive a certain amount of [Golden Spike];\n(2) If all rewards in the Moon pool have already been Obtained when triggered in the Sun pool, the [Laurel] will be converted into an equal amount of [Golden Spike], and vice versa;\n(3) This mechanic will not Trigger if all rewards from both pools have already been Obtained.\n6. After the October 15 update, a set amount of [Golden Spike]/[Laurel] can be redeemed for specific items in the Exchange Shop. The Exchange Shop closes together with the Wish event, so players holding [Golden Spike]/[Laurel] should redeem them in time; when the redemption period ends, the event items (Golden Spike, Laurel) will be cleared.\n7. The Sun & Moon Traveler prize pools are available for a limited time. Progress will not carry over to other Wish events.</color>\n\n<color=#98cbff>III. Probability Disclosure:</color>\n<color=#FFFFFF>1. Overall Pool Probabilities:\n[Sun Pool]\nYaria - Morning Dew 5.76%\nMorning Dew Nameplate 7.59%\nCustom Poke - Morning Deer 9.41%\nChat Bubble - Dawn Dew 9.41%\nEmote - Deer Passing 10.22%\nEmote - Good Morning 10.22%\nTreasure Coin x6 15.80%\nRandom Effect (30 Days) 15.80%\nIntimacy Item - Morning Dew Postcard x10 15.80%\n[Moon Pool]\nChang Xiao'e - Cloud Shadow 5.76%\nCloud Shadow Nameplate 7.59%\nCustom Poke - Cloud Rabbit 9.41%\nChat Bubble - Moon Shadow 9.41%\nEmote - ME Rabbit 10.22%\nEmote - Good Night 10.22%\nTreasure Coin x6 15.80%\nRandom Effect (30 Days) 15.80%\nIntimacy Item - Cloud Shadow Postcard x10 15.80%\n2. Sun & Moon Radiance Probability:\nEach draw has a 5% independent chance to Trigger. Token quantities and probabilities upon Trigger are as follows:\nLaurel/Golden Spike x2 60%\nLaurel/Golden Spike x4 30%\nLaurel/Golden Spike x6 10%</color>",
        "<color=#98cbff>I. Waktu</color>\n<color=#FFFFFF>1. Waktu Doa: 25 September 2026, 00:00:00 - 21 Oktober 2026, 23:59:59.\n2. Waktu Penukaran: setelah update 15 Oktober 2026 - 21 Oktober 2026, 23:59:59.</color>\n\n<color=#98cbff>II. Aturan Doa:</color>\n<color=#FFFFFF>1. Event Sun & Moon Traveler memiliki dua prize pool: Sun dan Moon. Membeli kartu uji coba 1 Hari Love Delivery seharga 10 Kupon di pool Sun memberikan 1 [Golden Spike]. Membeli kartu uji coba 1 Hari Love Delivery seharga 10 Kupon di pool Moon memberikan 1 [Laurel]. Keduanya bisa digunakan untuk menarik dari pool masing-masing.\n2. Pool Sun dan Moon terpisah. Masing-masing berisi 9 hadiah. Setiap Doa menjamin 1 hadiah, tanpa duplikat. Semua hadiah di satu pool dijamin didapat dalam 9 tarikan.\n3. Biaya [Golden Spike]/[Laurel] per tarikan meningkat dalam satu pool: 1, 4, 8, 12, 16, 24, 32, 48, 68.\n4. Mendapatkan hadiah utama [Yaria: Morning Dew] atau [Chang Xiao'e: Cloud Shadow] memberikan semua hadiah yang Tersisa di pool tersebut.\n5. Sun & Moon Radiance:\n(1) Setiap tarikan berpeluang Memicu mekanik Sun & Moon Radiance. Jika terpicu di pool Sun, kamu menerima sejumlah [Laurel]. Jika terpicu di pool Moon, kamu menerima sejumlah [Golden Spike];\n(2) Jika semua hadiah di pool Moon sudah Didapat saat terpicu di pool Sun, [Laurel] akan diubah menjadi [Golden Spike] dalam jumlah yang sama, dan sebaliknya;\n(3) Mekanik ini tidak akan Terpicu jika semua hadiah dari kedua pool sudah Didapat.\n6. Setelah update 15 Oktober, sejumlah [Golden Spike]/[Laurel] bisa ditukar dengan item tertentu di Exchange Shop. Exchange Shop ditutup bersama event Doa, jadi pemain yang memiliki [Golden Spike]/[Laurel] harap segera menukarnya; setelah waktu penukaran berakhir, item event (Golden Spike, Laurel) akan dihapus.\n7. Prize pool Sun & Moon Traveler tersedia dalam waktu terbatas. Progres tidak akan dibawa ke event Doa lainnya.</color>\n\n<color=#98cbff>III. Pengungkapan Peluang:</color>\n<color=#FFFFFF>1. Peluang Pool Keseluruhan:\n[Sun Pool]\nYaria - Morning Dew 5,76%\nMorning Dew Nameplate 7,59%\nCustom Poke - Morning Deer 9,41%\nChat Bubble - Dawn Dew 9,41%\nEmote - Deer Passing 10,22%\nEmote - Good Morning 10,22%\nTreasure Coin x6 15,80%\nEfek Acak (30 Hari) 15,80%\nItem Intimacy - Morning Dew Postcard x10 15,80%\n[Moon Pool]\nChang Xiao'e - Cloud Shadow 5,76%\nCloud Shadow Nameplate 7,59%\nCustom Poke - Cloud Rabbit 9,41%\nChat Bubble - Moon Shadow 9,41%\nEmote - ME Rabbit 10,22%\nEmote - Good Night 10,22%\nTreasure Coin x6 15,80%\nEfek Acak (30 Hari) 15,80%\nItem Intimacy - Cloud Shadow Postcard x10 15,80%\n2. Peluang Sun & Moon Radiance:\nSetiap tarikan memiliki peluang independen 5% untuk Terpicu. Jumlah Token dan peluang saat Terpicu sebagai berikut:\nLaurel/Golden Spike x2 60%\nLaurel/Golden Spike x4 30%\nLaurel/Golden Spike x6 10%</color>"),
    "<color=#98cbff>一、时间：</color>\n<color=#FFFFFF>1.祈愿时间：2026年10月16日 00:00:00-2026年11月11日 23:59:59。\n2.兑换时间：2026年10月16日 00:00:00-2026年11月14日 23:59:59。\n注：11月11日祈愿时间结束后，线条小狗祈愿币将不可使用，请及时使用；11月11日后仅保留兑换商店，请拥有线条小狗积分的玩家们及时兑换，兑换时间结束后活动道具（线条小狗祈愿币，线条小狗积分）将被清空。</color>\n\n<color=#98cbff>二、祈愿规则：</color>\n<color=#FFFFFF>1.在活动界面消耗60点券购买6个爱心投送1天体验卡可获赠6个【线条小狗祈愿币】，每次祈愿消耗6个线条小狗祈愿币。活动期间，每人祈愿限1000次。\n2.祈愿福利： \n（1）祈愿福利1：首次进入奖池将会赠送线条小狗祈愿币×5，首抽仅需10点券；\n（2）祈愿福利2：每累计祈愿10次，可领线条小狗积分、表情奖励自选礼（限领前6次）\n3.兑换积分可用于在兑换商店中兑换指定奖励，详细兑换内容可前往兑换商店查看。\n4.重复获取：抽到已拥有的天幕、名片、特效、表情等不可重复获得的内容，将会自动转化为指定数量的线条小狗积分，具体重复转化数量如下：\n线条小狗天幕：150；线条小狗名片：60；线条小狗传送特效：45；线条小狗头像框：20；线条小狗聊天气泡：20；表情：20。\n5.线条小狗天幕祈愿奖池限时开启，抽奖进度不会被其他祈愿活动继承。</color>\n\n<color=#98cbff>三、概率公示：</color>\n<color=#FFFFFF>天幕-线条小狗的旅行：1%\n线条小狗名片：1%\n传送特效-线条小狗出动：1%\n线条小狗头像框：1.25%\n线条小狗气泡：1.25%\n表情-扔心心：1.25%\n表情-接住心心：1.25%\n表情-挥手：1.25%\n表情-走了：1.25%\n线条小狗积分*38：6%\n亲密度道具-线条小狗拍立得*1：6%\n接收心心个性戳戳（1天）：14%\n线条小狗积分*18：26%\n线条小狗积分*8：37.5%</color>": (
        "<color=#98cbff>I. Time:</color>\n<color=#FFFFFF>1. Wish period: 2026-10-16 00:00:00 - 2026-11-11 23:59:59.\n2. Redemption period: 2026-10-16 00:00:00 - 2026-11-14 23:59:59.\nNote: After the Wish period ends on November 11, Line Puppy Wish Coins can no longer be used, so please use them in time. After November 11 only the Exchange Shop remains; players holding Line Puppy Points should redeem them in time. When the redemption period ends, the event items (Line Puppy Wish Coins, Line Puppy Points) will be cleared.</color>\n\n<color=#98cbff>II. Wish Rules:</color>\n<color=#FFFFFF>1. On the event screen, spend 60 Coupons to buy 6 Love Delivery 1-Day Trial Cards and receive 6 [Line Puppy Wish Coins] as a bonus. Each Wish costs 6 Line Puppy Wish Coins. Each player is limited to 1000 Wishes during the event.\n2. Wish perks:\n(1) Perk 1: On first entering the prize pool you receive Line Puppy Wish Coin x5, so your first draw costs only 10 Coupons;\n(2) Perk 2: Every 10 Wishes, claim Line Puppy Points and an Emote Reward Selectable Gift (first 6 times only)\n3. Exchange Points can be used to redeem specific rewards in the Exchange Shop; see the Exchange Shop for details.\n4. Duplicates: drawing a Sky Screen, Nameplate, Effect, Emote or other non-repeatable item you already own automatically converts it into a set number of Line Puppy Points, as follows:\nLine Puppy Sky Screen: 150; Line Puppy Nameplate: 60; Line Puppy Teleport Effect: 45; Line Puppy Avatar Frame: 20; Line Puppy Chat Bubble: 20; Emote: 20.\n5. The Line Puppy Sky Screen Wish pool is open for a limited time, and draw progress does not carry over to other Wish events.</color>\n\n<color=#98cbff>III. Probability Disclosure:</color>\n<color=#FFFFFF>Sky Screen - Line Puppy's Journey: 1%\nLine Puppy Nameplate: 1%\nTeleport Effect - Line Puppy, Go!: 1%\nLine Puppy Avatar Frame: 1.25%\nLine Puppy Bubble: 1.25%\nEmote - Throw Hearts: 1.25%\nEmote - Catch the Heart: 1.25%\nEmote - Wave: 1.25%\nEmote - I'm Leaving: 1.25%\nLine Puppy Points x38: 6%\nIntimacy Item - Line Puppy Instant Photo x1: 6%\nReceive Hearts Personalized Poke (1 Day): 14%\nLine Puppy Points x18: 26%\nLine Puppy Points x8: 37.5%</color>",
        "<color=#98cbff>I. Waktu:</color>\n<color=#FFFFFF>1. Waktu Doa: 16 Oktober 2026 00:00:00 - 11 November 2026 23:59:59.\n2. Waktu Penukaran: 16 Oktober 2026 00:00:00 - 14 November 2026 23:59:59.\nCatatan: Setelah waktu Doa berakhir pada 11 November, Koin Doa Line Puppy tidak bisa digunakan lagi, jadi segera gunakan. Setelah 11 November hanya Exchange Shop yang tersisa; pemain yang memiliki Poin Line Puppy harap segera menukarnya. Setelah waktu penukaran berakhir, item event (Koin Doa Line Puppy, Poin Line Puppy) akan dihapus.</color>\n\n<color=#98cbff>II. Aturan Doa:</color>\n<color=#FFFFFF>1. Di layar event, habiskan 60 Kupon untuk membeli 6 Kartu Uji Coba 1 Hari Love Delivery dan dapatkan bonus 6 [Koin Doa Line Puppy]. Setiap Doa memakai 6 Koin Doa Line Puppy. Setiap pemain dibatasi 1000 Doa selama event.\n2. Bonus Doa:\n(1) Bonus 1: Saat pertama kali masuk prize pool kamu mendapat Koin Doa Line Puppy x5, jadi tarikan pertama hanya 10 Kupon;\n(2) Bonus 2: Setiap 10 Doa, klaim Poin Line Puppy dan Hadiah Emote Pilihan (hanya 6 kali pertama)\n3. Poin penukaran bisa digunakan untuk menukar hadiah tertentu di Exchange Shop; lihat Exchange Shop untuk detailnya.\n4. Duplikat: mendapatkan Sky Screen, Nameplate, Efek, Emote, atau item tidak berulang lain yang sudah kamu miliki akan otomatis diubah menjadi sejumlah Poin Line Puppy, sebagai berikut:\nSky Screen Line Puppy: 150; Nameplate Line Puppy: 60; Efek Teleportasi Line Puppy: 45; Bingkai Avatar Line Puppy: 20; Chat Bubble Line Puppy: 20; Emote: 20.\n5. Prize pool Doa Sky Screen Line Puppy dibuka dalam waktu terbatas, dan progres tarikan tidak dibawa ke event Doa lainnya.</color>\n\n<color=#98cbff>III. Pengungkapan Peluang:</color>\n<color=#FFFFFF>Sky Screen - Perjalanan Line Puppy: 1%\nNameplate Line Puppy: 1%\nEfek Teleportasi - Line Puppy Beraksi: 1%\nBingkai Avatar Line Puppy: 1,25%\nBubble Line Puppy: 1,25%\nEmote - Lempar Hati: 1,25%\nEmote - Tangkap Hati: 1,25%\nEmote - Lambaian: 1,25%\nEmote - Aku Pergi: 1,25%\nPoin Line Puppy x38: 6%\nItem Intimacy - Foto Instan Line Puppy x1: 6%\nPersonalized Poke Terima Hati (1 Hari): 14%\nPoin Line Puppy x18: 26%\nPoin Line Puppy x8: 37,5%</color>"),
    "2、<color=#98cbff>支持规则</color>：玩家可对认为最有机会夺冠的选手进行支持，可同时支持多位选手，每次可支持100钻石，每名选手最多可支持10000钻石。": (
        "2. <color=#98cbff>Support Rules</color>: Players can support the contestant they think has the best chance of winning the Championship. They can support multiple contestants simultaneously, with each support costing 100 Diamonds, and each contestant can be supported with up to 10,000 Diamonds.",
        "2. <color=#98cbff>Aturan Dukungan</color>: Pemain bisa mendukung kontestan yang menurut mereka paling berpeluang menjadi Juara. Mereka bisa mendukung beberapa kontestan sekaligus, setiap dukungan memerlukan 100 Diamond, dan setiap kontestan bisa didukung hingga maksimal 10.000 Diamond."),
    "<color=#98cbff>一、活动规则</color>\n<color=#FFFFFF>欢迎来到英雄连连看~\n1、活动开启规则：活动持续期间内，可以随时、多次参与连连看玩法。每期活动结算时间为周日的23点59，请确保在结算时间前完成所有关卡哦（否则可能不会分到奖励喔）。\n2、奖励结算规则：完整通关（完成所有关卡）即拥有赢取钻石奖池资格。钻石奖池根据排名分取，答题总耗时越短，排名越高，分得的钻石便越多。\n3、总耗时计算规则：关卡开始到关卡结束的总耗时时长，错误1题增加15秒罚时。</color>\n<color=#98cbff>二、题库</color>\n<color=#FFFFFF>1、题库主题：基于英雄们本身的特性展开，每期不同，欢迎体验~！\n2、题库设计：根据每期主题变更题库，会从中随取，本期9个关卡。</color>": (
        "<color=#98cbff>1. Event Rules</color>\n<color=#FFFFFF>Welcome to Hero Match-Up~\n1. Event Rules: You can Participate in Match-Up at any Time during the Event. Each round ends on Sunday at 23:59. Please ensure all levels are completed before the deadline (otherwise you may not receive Rewards).\n2. Reward Rules: Complete all levels to qualify for the Diamond Prize pool. Diamonds are distributed based on Ranking; the shorter the total Time, the higher the rank and the more Diamonds you receive.\n3. Time Calculation: Total Time from Start to Finish. Each incorrect answer adds a 15-second penalty.</color>\n<color=#98cbff>2. Question Bank</color>\n<color=#FFFFFF>1. Themes: Based on Hero characteristics, changing each round.\n2. Design: 9 levels this round, randomly selected based on the Theme.</color>",
        "<color=#98cbff>1. Aturan Event</color>\n<color=#FFFFFF>Selamat datang di Hero Match-Up~\n1. Aturan Event: Kamu bisa ikut Match-Up kapan saja selama Event. Tiap ronde berakhir hari Minggu pukul 23:59. Pastikan semua level selesai sebelum batas waktu (jika tidak, kamu mungkin tidak menerima Hadiah).\n2. Aturan Hadiah: Selesaikan semua level untuk lolos ke Prize pool Diamond. Diamonds dibagikan berdasarkan Peringkat; makin singkat total Waktu, makin tinggi peringkat dan makin banyak Diamonds yang kamu terima.\n3. Perhitungan Waktu: Total Waktu dari Mulai sampai Selesai. Tiap jawaban salah menambah penalti 15 detik.</color>\n<color=#98cbff>2. Bank Soal</color>\n<color=#FFFFFF>1. Tema: Berdasarkan karakteristik Hero, berganti setiap ronde.\n2. Desain: 9 level di ronde ini, dipilih secara acak berdasarkan Tema.</color>"),
}

# The weekly leaderboards, ranked 第一 .. 第一百. `%s%s` is the season and the Chessplayer.
LEADERBOARDS: dict[str, tuple[str, str]] = {
    "上周钻石狂潮排行榜排名第": (
        "Ranked No. {n} on the Diamond Frenzy leaderboard last week",
        "Peringkat No. {n} di leaderboard Diamond Frenzy minggu lalu"),
    "上周成就大师排行榜排名第": (
        "Ranked No. {n} on the Achievement Master leaderboard last week",
        "Peringkat No. {n} di leaderboard Achievement Master minggu lalu"),
    "上周战力巅峰排行榜排名第": (
        "Ranked No. {n} on the Peak Combat Power leaderboard last week",
        "Peringkat No. {n} di leaderboard Peak Combat Power minggu lalu"),
    "上周%s%s棋手代言榜排名第": (
        "Ranked No. {n} on the %s%s Chessplayer Spokesperson leaderboard last week",
        "Peringkat No. {n} di leaderboard Spokesperson Chessplayer %s%s minggu lalu"),
}

# "<Chessplayer>上大分" titles; the catalog only has the longer "<Chessplayer>这波上大分" (Scores Big).
SCORES_BIG = ("乔汐", "姜导", "嬴律", "孙小宾", "安琪拉", "小妲己", "常小娥", "庄小鱼", "弈星", "明先生", "昭君",
              "武凤", "玉环", "班叔", "瑶妹", "白歌", "镜", "闹闹", "阿离", "香香", "马可")

# The base titles whose numbered tiers 1.6.0.1 added, each translated by the catalog under its own name.
TIERED_TITLES = (
    "E人聚集", "一刹光辉", "一直合成一直爽", "万众瞩目", "万象启幕", "万象棋天天见", "万象答王", "不差钱", "临危受命",
    "买它！买它！", "人形印钻", "人气新星", "人见人爱", "以武会友", "众人拾柴", "传说卡皇", "你是懂表情的", "停不下来",
    "光彩夺目", "全员百分百", "八方来财", "兵器谱", "冠绝天下", "刷到停不下", "刷到天荒地老", "勤修不辍", "包发财",
    "包大人", "千招百式", "印记收集者", "口令专家", "史诗卡佬", "同享常驻", "启程之证", "命中之神", "啥都试试",
    "善财童子", "嗨起来", "夜以继日", "大腿带飞", "大额开张", "天下英雄", "头号闺蜜", "奶妈的自我修养", "好礼相赠",
    "完美橱窗", "带飞队长", "常胜将军", "常驻粉丝", "幻梦星彩", "开黑团长", "彩戏师", "彩虹屁大师", "得心应手",
    "心路历程", "忠实观众", "快聊选手", "快速成长", "成长之路", "我就要它", "我有钥", "我爱我家", "我要验牌",
    "戳到你了", "扩容一下", "扶我起来", "抄作业大师", "披星戴月", "拉拉队教练", "拍卖大师", "拍卖新秀", "持家有道",
    "指法芬芳", "挚爱亲朋", "整点活儿", "无限后手", "星耀无忧者", "显眼包", "最佳搭子", "最强大脑", "来啥打啥",
    "来打我呀", "框王", "步步高升", "水晶收集者", "永不言六", "泡言泡语", "洒洒水啦", "海内存知己", "清仓",
    "游戏人生", "满勤王", "炉火纯青", "热情观众", "牌界中坚", "特邀大使", "独树一帜", "王牌选手", "王者之路",
    "王者无忧者", "生意头脑", "登峰之路", "白手起家", "省钱新手", "眼光独到", "眼花缭乱", "稀有卡痴", "竞拍强者",
    "红包收割机", "纳税大户", "翻一番", "肝胆相照", "花钱不眨眼", "荣光追迹者", "荣耀会员", "行走的能量黑洞",
    "认真学习", "豪气干云", "豪气抵扣", "财大气粗", "财源滚滚", "贴贴", "赢赢赢！", "路漫漫", "躺赢", "轻拳出击",
    "输出拉满", "过命兄弟", "还活着", "这波不亏", "连看之巅", "逐宝问珍", "钞能力玩家", "钻石大亨", "钻石无忧者",
    "钻石蒸发术", "铁杆死党", "铂金无忧者", "长安舞榭", "随叫随到", "集卡新秀", "零元GO", "颜艺", "高光时刻",
    "黄金无忧者", "鼓励师",
) + tuple(f"{name}上大分" for name in SCORES_BIG)
TIERS = 10
RANKS = 100

# The card-pack covers bin `9E45602F1857539D` (Encyclopedia > Diamond Frenzy > Starting Lineup) labels
# each cover with a short form of a name the catalog only has inside a longer string. Its device cycle
# was withdrawn (2026-10-16, `extra_text`), so these reach only a catalog table that holds the same short
# form; they stay because a catalog string never needs a cycle, and a resealed bin would need them. `derived` generates
# the targets from those longer strings: a pack header from the catalog's coloured header, a contract
# from its `契约·` form, a hero from its `逆天改命(<hero>)` pack name. The faction-hero labels have no
# longer form anywhere, so their sources are listed and their targets joined from the catalog's own
# faction and hero names.
_PACK_HEADER = re.compile(r"<color=[^>]+>([^<]+卡包)</color>")
_COLORED = re.compile(r"<color=[^>]+>([^<]+)</color>")
_CONTRACT = re.compile(r"契约·([^()]+\([^()]+\))")
_HERO_PACK = re.compile(r"逆天改命\(([^()]+)\)")
_CONTRACT_PREFIX = "Contract: "
FACTION_HEROES = (
    "河洛-李白", "河洛-李信", "日落海-艾琳", "日落海-莱西奥", "三分-诸葛亮", "三分-甄姬",
    "逐鹿-蒙犽", "逐鹿-嬴政", "逐鹿-扁鹊", "大河-韩信", "大河-刘邦", "大河-大司命",
)
# Game data 1.7.0.1 split each talent's text: the catalog has "<series header>\n<effect>" as one string,
# the new tables hold the effect alone and the series name (`╬整备系列`) without its tags. `derived`
# takes both from the catalog's two-line form.
_SERIES = "系列"
_TAG = re.compile(r"<[^<>]*>")


def chinese_number(value: int) -> str:
    """<value> (1..100) the way the game writes it: 七, 十八, 七十五, 一百."""
    if value == 100:
        return "一百"
    tens, ones = divmod(value, 10)
    digits = "一二三四五六七八九"
    head = "" if tens == 0 else ("十" if tens == 1 else digits[tens - 1] + "十")
    return head + (digits[ones - 1] if ones else "")


def _title(unique: dict[str, str], zh: str) -> str | None:
    """The catalog's name for title <zh>, tidied for use with a tier suffix."""
    if zh.endswith("上大分") and zh not in unique:
        name = unique.get(zh[:-3])
        return f"{name} Scores Big" if name else None
    text = unique.get(zh)
    if not text:
        return None
    text = text.strip().rstrip(".")
    return text[:1].upper() + text[1:]


def _inner(target: str, prefix: str, wrapped: str) -> str | None:
    """The part of <target> that sits where <wrapped> does in the source's longer form, or None."""
    if not target.startswith(prefix):
        return None
    rest = target[len(prefix):]
    return rest[1:-1] if wrapped == "()" and rest.startswith("(") and rest.endswith(")") else rest


def derived(unique: dict[str, str]) -> dict[str, str]:
    """Short forms whose translation the catalog carries only inside a longer string of its own."""
    out: dict[str, str] = {}
    for zh, target in unique.items():
        if match := _PACK_HEADER.fullmatch(zh):
            inner = _COLORED.fullmatch(target)
            if inner:
                out[match[1]] = inner[1]
        elif match := _CONTRACT.fullmatch(zh):
            if target.startswith(_CONTRACT_PREFIX):
                out[match[1]] = target[len(_CONTRACT_PREFIX):]
        elif match := _HERO_PACK.fullmatch(zh):
            pack = unique.get("逆天改命")
            hero = _inner(target, f"{pack} ", "()") if pack else None
            if hero:
                out[match[1]] = hero
    for zh in FACTION_HEROES:
        faction, hero = zh.split("-", 1)
        parts = unique.get(faction), unique.get(hero) or out.get(hero)
        if all(parts):
            out[zh] = f"{parts[0]} - {parts[1]}"
    for zh, target in unique.items():
        head, _, body = zh.partition("\n")
        target_head, _, target_body = target.partition("\n")
        series = _TAG.sub("", head)
        if not series.endswith(_SERIES) or not target_body or body.count("\n") != target_body.count("\n"):
            continue
        for source, text in ((body, target_body), (series, _TAG.sub("", target_head))):
            if text.strip() and not check({source: text}):
                out.setdefault(source, text.strip())
    return out


def entries(unique: dict[str, str], code: str) -> dict[str, str]:
    """Every supplementary (Chinese -> target) pair for language <code>, given the catalog's <unique> map."""
    index = 1 if code == "id" else 0
    out = {zh: pair[index] for zh, pair in TEXTS.items()}
    for prefix, pair in LEADERBOARDS.items():
        for rank in range(1, RANKS + 1):
            out[prefix + chinese_number(rank)] = pair[index].replace("{n}", str(rank))
    for zh in TIERED_TITLES:
        title = _title(unique, zh)
        if title is None:
            continue
        if zh.endswith("上大分"):
            out.setdefault(zh, title)
        for tier in range(1, TIERS + 1):
            out[f"{zh}({chinese_number(tier)})"] = f"{title} ({_ROMAN[tier]})"
    for zh, target in derived(unique).items():
        out.setdefault(zh, target)
    return out


def check(pairs: dict[str, str]) -> list[str]:
    """The sources in <pairs> whose target does not carry exactly the source's placeholders and tags."""
    return [zh for zh, target in pairs.items()
            if sorted(_MARKUP.findall(zh)) != sorted(_MARKUP.findall(target))]


def apply(data: dict, code: str) -> int:
    """Add this module's translations to a loaded `catalog.json.gz` in place; returns how many were added.

    Only sources the catalog does not translate are added, so the catalog always wins.
    """
    unique = data.setdefault("unique", {})
    pairs = entries(unique, code)
    bad = check(pairs)
    if bad:
        raise ValueError(f"catalog supplement changes the placeholders of {bad[:3]}")
    added = 0
    for zh, target in pairs.items():
        if zh not in unique:
            unique[zh] = target
            added += 1
    return added
