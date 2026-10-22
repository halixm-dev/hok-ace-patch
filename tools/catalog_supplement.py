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
    # card and in the share code's 【name】 prefix. The creators' handles 1.7.0.1 added (Provider, Author)
    # stay as written; inside a sentence a handle is romanized, since a target may not keep Chinese.

    # ResSeasonAILineupDataBin: EffectCardDesc (advice on Effect Cards; game data 1.7.0.1)
    "【5阶英雄兑换券】找海月，加快阵容成型。\n【扶摇直上】快速升到6级拿专属天赋。\n【破镜之证】提供等级成长。": (
        "【Tier 5 Hero Voucher】 finds Haya and speeds up the Lineup.\n【Soaring High】 gets you to Lv. 6 fast"
        " for the Exclusive Talent.\n【Proof of Breakthrough】 provides Level growth.",
        "【Voucher Hero Tier 5】 mencari Haya dan mempercepat Lineup.\n【Soaring High】 cepat naik ke Lv. 6 untuk"
        " Exclusive Talent.\n【Proof of Breakthrough】 memberi pertumbuhan Level."),
    "优先拿给两张牌的": ("Prefer the ones that give two cards", "Utamakan yang memberi dua kartu"),
    "全军动员可以触发全场整备；众星闪耀加全体等级，照影帮助我们觉醒": (
        "Full Army Mobilization triggers Prepare across the board, Starry Radiance raises everyone's Level,"
        " and Shadow Projection helps us Awaken",
        "Full Army Mobilization memicu Prepare di seluruh papan, Starry Radiance menaikkan Level semua Hero,"
        " dan Shadow Projection membantu Awaken"),
    "前期不用攒效果牌，后期通过锦囊出现整备和唤醒效果牌就直接拿。": (
        "No need to save Effect Cards early; late, take any Prepare or Awaken Effect Card a Kit offers.",
        "Tak perlu menyimpan Kartu Efek di awal; di akhir, langsung ambil Kartu Efek Prepare atau Awaken"
        " yang muncul dari Kit."),
    "单核必抢六阶卡": ("Single-carry builds must grab Tier 6 cards", "Build carry tunggal wajib merebut kartu Tier 6"),
    "可以多囤一点触发登场，整备": (
        "Stock up on cards that trigger Deploy and Prepare",
        "Simpan lebih banyak kartu pemicu Deploy dan Prepare"),
    "后期孙尚香换帅成周瑜": (
        "Late, swap Lady Sun into Zhou Yu with Change of Commander",
        "Di akhir, tukar Lady Sun menjadi Zhou Yu dengan Pergantian Komandan"),
    "后期通过不断合成给到的效果锦囊牌，优先选择传承给老虎使用，增加全员等级": (
        "Late, from the Effect Guide cards that repeated Combines give, pick Inheritance first and use it on"
        " Pei to raise the whole team's Level",
        "Di akhir, dari kartu Panduan Efek hasil Combine berulang, utamakan Inheritance dan gunakan pada Pei"
        " untuk menaikkan Level seluruh tim"),
    "唤醒、集体唤醒给露娜用、临阵磨枪、全军动员给曹操用": (
        "Use Awaken and Mass Awakening on Luna, and Sharpening Weapons Before Battle and Full Army"
        " Mobilization on Cao Cao",
        "Gunakan Awaken dan Mass Awakening pada Luna, serta Sharpening Weapons Before Battle dan Full Army"
        " Mobilization pada Cao Cao"),
    "唤醒可以触发庄周蒙犽，快速提质量，发号施令便宜实用，逐鹿必拿。": (
        "Awaken triggers Zhuangzi and Meng Ya to raise quality fast; Commanding Presence is cheap and"
        " useful, a must for Zhulu Plateau.",
        "Awaken memicu Zhuangzi dan Meng Ya untuk cepat menaikkan kualitas; Commanding Presence murah dan"
        " berguna, wajib untuk Zhulu Plateau."),
    "唤醒或集体唤醒给露娜，临阵磨枪和全军动员给上官婉儿。这些都能触发整备获得更多古币，增加花木兰复活次数（上限10次）。": (
        "Give Awaken or Mass Awakening to Luna, and Sharpening Weapons Before Battle and Full Army"
        " Mobilization to Shangguan. Each triggers Prepare for more Ancient Coins, adding Revives for Mulan"
        " (up to 10).",
        "Berikan Awaken atau Mass Awakening ke Luna, dan Sharpening Weapons Before Battle serta Full Army"
        " Mobilization ke Shangguan. Masing-masing memicu Prepare untuk Ancient Coin tambahan, menambah"
        " Revive Mulan (maks. 10)."),
    "唤醒露娜，集体唤醒触发双倍；前期不用攒效果牌，后期通过锦囊出现整备和唤醒效果牌就直接拿。——抖音搜肝帝": (
        "Awaken Luna; Mass Awakening triggers twice. No need to save Effect Cards early; late, take any"
        " Prepare or Awaken Effect Card a Kit offers. Search Gandi on Douyin",
        "Awaken Luna; Mass Awakening memicu dua kali. Tak perlu menyimpan Kartu Efek di awal; di akhir,"
        " langsung ambil Kartu Efek Prepare atau Awaken yang muncul dari Kit. Cari Gandi di Douyin"),
    "在三本的锦囊效果牌里面我们优先拿两张开团 ，其次是大河流域征召令 ，再其次就是两张闪现 ": (
        "From the Effect Cards in Kits at Chessplayer Lv. 3, take the two Initiate cards first, then"
        " Riverlands Recruitment Order, then the two Flash cards",
        "Dari Kartu Efek di Kit saat Chessplayer Lv. 3, utamakan dua kartu Initiate, lalu Riverlands"
        " Recruitment Order, lalu dua kartu Flash"),
    "大河人口越多越强，众星闪耀加整体等级，其次拿装备或者经济。": (
        "Riverlands grows stronger with more Population, and Starry Radiance raises everyone's Level; after"
        " that, take Equipment or economy.",
        "Riverlands makin kuat dengan Populasi lebih banyak, dan Starry Radiance menaikkan Level semua Hero;"
        " setelah itu ambil Equipment atau ekonomi."),
    "特装就是上限，武装分解商店1点能量可以买到，效果锦囊也可以开到。\n如果能拿到人口，多打出位决赛圈还能多挂钟馗太乙。": (
        "Special Equipment sets the ceiling: Weapon Dismantle sells it in the shop for 1 Energy, and Effect"
        " Guides can roll it too.\nWith extra Population, the spare play slots let you add Kui and Taiyi in"
        " the finals.",
        "Equipment spesial menentukan batas atas: Weapon Dismantle menjualnya di toko seharga 1 Energy, dan"
        " Panduan Efek juga bisa memberikannya.\nDengan Populasi tambahan, slot main ekstra bisa dipakai"
        " untuk Kui dan Taiyi di final."),
    "能拿就拿，后期转强力五阶卡。": (
        "Take it when you can, then switch to strong Tier 5 cards late.",
        "Ambil kalau bisa, lalu beralih ke kartu Tier 5 yang kuat di akhir."),
    "能量和5阶兑换券是刚需！": ("Energy and Tier 5 Vouchers are a must!", "Energy dan Voucher Tier 5 wajib!"),
    "被卡牌很好用": ("Great when your cards are blocked", "Bagus saat kartumu ditahan"),
    "这几张效果牌必拿。拿着或者存着": (
        "Always take these Effect Cards, to use or to keep",
        "Kartu Efek ini wajib diambil, untuk dipakai atau disimpan"),

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
    "优先机械头，其次炽热支配者，输出的话，可以带个无尽。": (
        "Robot Head first, then Sanguine Dominator; for damage, add an Endless Greatsword.",
        "Utamakan Robot Head, lalu Sanguine Dominator; untuk damage, tambahkan Endless Greatsword."),
    "优先给猴子和露娜做装备，其次是周瑜，猴子装备推荐无尽、魔律之刃、炽热支配者、露娜装备推荐大书、魔律之刃、炽\n热支配者、周瑜装备推荐大书、魔律之刃、聚灵水晶": (
        "Equip Wukong and Luna first, then Zhou Yu. Wukong: Endless Greatsword, Blade of Magic Law, Sanguine"
        " Dominator. Luna: Savant's Wrath, Blade of Magic Law, Sanguine Dominator. Zhou Yu: Savant's Wrath,"
        " Blade of Magic Law, Spirit-Gathering Crystal",
        "Utamakan Equipment untuk Wukong dan Luna, lalu Zhou Yu. Wukong: Endless Greatsword, Blade of Magic"
        " Law, Sanguine Dominator. Luna: Savant's Wrath, Blade of Magic Law, Sanguine Dominator. Zhou Yu:"
        " Savant's Wrath, Blade of Magic Law, Spirit-Gathering Crystal"),
    "冰矛和免控给艾琳": ("Frost Spear and Control Immunity go to Erin", "Frost Spear dan Kebal Kontrol untuk Erin"),
    "前期拿一件生命魔典非常舒服\n有控就用苍穹换掉霸者\n神器优先拿机器头": (
        "An early Grimoire of Life feels great\nAgainst crowd control, swap Overlord's Platemail for Pure"
        " Sky\nArtifact: Robot Head first",
        "Grimoire of Life di awal terasa sangat nyaman\nJika lawan punya kontrol, ganti Overlord's Platemail"
        " dengan Pure Sky\nArtifact: utamakan Robot Head"),
    "司空震必备金色圣剑，推荐再带一个炽热支配者解控，最后一件没有其他特殊装备的话就带痛苦面具。": (
        "Sikong Zhen must have Golden Blade. Sanguine Dominator is also recommended to remove crowd control, and for"
        " the last slot take Mask of Agony if no other special Equipment is available.",
        "Sikong Zhen wajib memakai Golden Blade. Disarankan juga membawa Sanguine Dominator untuk menghapus crowd"
        " control, dan untuk slot terakhir bawa Mask of Agony jika tidak ada Equipment khusus lain."),
    "司空震金色圣剑必备！苏烈拿肉装即可": (
        "Sikong Zhen must have Golden Blade! Su Lie just takes tank items",
        "Sikong Zhen wajib punya Golden Blade! Su Lie cukup ambil item tank"),
    "司空震需要金属圣剑，其他两个装备推荐痛苦面具和炽热，其他人装备不重要，有啥带啥": (
        "Sikong Zhen needs Golden Blade, plus Mask of Agony and Sanguine Dominator; the others' items don't"
        " matter, use whatever you have",
        "Sikong Zhen butuh Golden Blade, ditambah Mask of Agony dan Sanguine Dominator; item Hero lain tidak"
        " penting, pakai apa saja yang ada"),
    "夺冠上限两件套：\n机器头（高额增伤和免控）\n噬神之书（法术吸血）\n其他特装：\n护命灵珠（护盾和增伤）\n魂祭绝刃（也带法术吸血）\n普装推荐：\n炽热支配者（开局免控）\n名刀（打花木兰）\n圣杯（前期启动）。": (
        "The two-item set for winning:\nRobot Head (big damage boost and Control Immunity)\nInsatiable Tome"
        " (Magic Lifesteal)\nOther special items:\nLife-Saving Bead (Shield and damage boost)\nSoul-Sacrificing"
        " Blade (also Magic Lifesteal)\nRegular items:\nSanguine Dominator (Control Immunity at the"
        " start)\nDestiny (against Mulan)\nBroken Grail (fast early start).",
        "Dua item kunci untuk juara:\nRobot Head (bonus damage besar dan Kebal Kontrol)\nInsatiable Tome"
        " (Magic Lifesteal)\nItem spesial lain:\nLife-Saving Bead (Shield dan bonus damage)\nSoul-Sacrificing"
        " Blade (juga Magic Lifesteal)\nItem biasa:\nSanguine Dominator (Kebal Kontrol di awal"
        " pertempuran)\nDestiny (melawan Mulan)\nBroken Grail (aktif cepat di awal)."),
    "嬴律必备免控炽热，防止技能被打断，痛苦面具和虚无法杖最大化嬴律伤害。\n神装推荐：机器头、怒神法杖、梦魇之牙": (
        "Ying Lu must have Sanguine Dominator for Control Immunity so his Skills aren't interrupted; Mask of"
        " Agony and Void Staff maximize his damage.\nArtifacts: Robot Head, Angry God Staff, Nightmare Fang",
        "Ying Lu wajib punya Sanguine Dominator untuk Kebal Kontrol agar Skill-nya tidak terganggu; Mask of"
        " Agony dan Void Staff memaksimalkan damage-nya.\nArtifact: Robot Head, Angry God Staff, Nightmare Fang"),
    "嬴政必备炽热，免疫控制，防止大招被打断。法穿提供高额输出，名刀保命": (
        "Ying Zheng must have Sanguine Dominator for Control Immunity so his Ultimate isn't interrupted."
        " Magic Pierce gives big damage, and Destiny keeps him alive",
        "Ying Zheng wajib punya Sanguine Dominator untuk Kebal Kontrol agar Ultimate-nya tidak terganggu."
        " Magic Pierce memberi damage besar, dan Destiny menjaganya tetap hidup"),
    "孙悟空的蓝条长，需要聚灵水晶补充启动速度。露娜带魔律之刃的上限非常高。": (
        "Wukong has a long Mana bar, so he needs Spirit-Gathering Crystal to start faster. Luna with Blade"
        " of Magic Law has a very high ceiling.",
        "Bar Mana Wukong panjang, jadi dia butuh Spirit-Gathering Crystal agar lebih cepat aktif. Luna"
        " dengan Blade of Magic Law punya batas atas sangat tinggi."),
    "对应装备即可，无特定要求。": (
        "Matching Equipment is enough; nothing specific.",
        "Equipment yang sesuai sudah cukup; tidak ada syarat khusus."),
    "对面单核没有机器头，考虑带变猪杖。": (
        "If the enemy single carry has no Robot Head, consider a pig-transformation staff.",
        "Jika carry tunggal lawan tidak punya Robot Head, pertimbangkan tongkat pengubah babi."),
    "所有装备都优先穿给C位，芈月的英雄效果只对穿戴装备最多的英雄生效。": (
        "Give all Equipment to the Carry first; Mi Yue's Hero Effect only works on the Hero wearing the most"
        " Equipment.",
        "Prioritaskan semua Equipment untuk Carry; Efek Hero Mi Yue hanya berlaku untuk Hero yang memakai Equipment"
        " terbanyak."),
    "拿射手装拿射手装！": ("Take Marksman items. Marksman items!", "Ambil item Marksman. Item Marksman!"),
    "敖隐必备自然法杖高频触发变猪，射手装备均适配，对手近战多就寒霜。\n东皇必备名刀，防止技能压制期间自身死亡，剩下的补肉装即可。\n大司命只需要一件铸梦·逐风就可以质变": (
        "Ao'yin must have Nature Staff to trigger Pig Transformation often; any Marksman item suits him,"
        " plus Frost Assault against many melee enemies.\nDonghuang must have Destiny so he doesn't die while"
        " suppressing; fill the rest with tank items.\nOne Dream-Forged Windchaser is all Augran needs to transform",
        "Ao'yin wajib punya Nature Staff untuk sering memicu Pig Transformation; semua item Marksman cocok,"
        " plus Frost Assault jika banyak musuh melee.\nDonghuang wajib punya Destiny agar tidak mati saat"
        " menekan musuh; sisanya isi dengan item tank.\nAugran cukup satu Dream-Forged Windchaser untuk"
        " berubah drastis"),
    "敖隐最佳装：自然法杖（无限变猪）；破晓（比例真伤）；寒霜侵袭（减速风筝）；名刀。\n东皇推荐装：不死鸟之眼（高额回复）；霸者重装（高血免伤）；魔女斗篷（打嬴政司空震必备）。": (
        "Ao'yin's best items: Nature Staff (endless Pig Transformation); Daybreaker (percentage true"
        " damage); Frost Assault (slow and kite); Destiny.\nDonghuang's items: Eye of the Phoenix (big"
        " healing); Overlord's Platemail (high HP and damage reduction); Succubus Cloak (a must against Ying"
        " Zheng and Sikong Zhen).",
        "Item terbaik Ao'yin: Nature Staff (Pig Transformation tanpa batas); Daybreaker (true damage"
        " persentase); Frost Assault (memperlambat dan kite); Destiny.\nItem Donghuang: Eye of the Phoenix"
        " (pemulihan besar); Overlord's Platemail (HP tinggi dan pengurangan damage); Succubus Cloak (wajib"
        " melawan Ying Zheng dan Sikong Zhen)."),
    "无尽巨剑、炽热支配者、魔律之刃\r\n如果对面没控制，把炽热换成无尽\r\n也就是两把无尽": (
        "Endless Greatsword, Sanguine Dominator, Blade of Magic Law\nIf the enemy has no crowd control, swap"
        " Sanguine Dominator for Endless Greatsword\nthat is, two Endless Greatswords",
        "Endless Greatsword, Sanguine Dominator, Blade of Magic Law\nJika lawan tidak punya kontrol, ganti"
        " Sanguine Dominator dengan Endless Greatsword\nartinya dua Endless Greatsword"),
    "杨玉环最好是有个圣杯，司空震必须有圣剑，最好有面具，不然牢大就刮": (
        "Yuhuan should ideally have Broken Grail; Sikong Zhen must have Golden Blade and ideally Mask of"
        " Agony, or the big guy falls flat",
        "Yuhuan sebaiknya punya Broken Grail; Sikong Zhen wajib punya Golden Blade dan sebaiknya Mask of"
        " Agony, kalau tidak, si jagoan bakal tumbang"),
    "法源之杯可以帮助蒙恬快速回蓝，蒙恬召唤小兵可以给他提供免伤，加上霸者重凯后有非常高的减伤，御灵之纱则是提供护盾，让霸者重凯的减伤效果能持续更久。": (
        "Mana Chalice helps Meng Tian regain Mana fast; his summoned minions give him damage reduction,"
        " which gets very high with Overlord's Platemail, and Spirit Veil adds a Shield so Overlord's"
        " Platemail's reduction lasts longer.",
        "Mana Chalice membantu Meng Tian cepat memulihkan Mana; minion panggilannya memberi pengurangan"
        " damage, yang jadi sangat tinggi dengan Overlord's Platemail, dan Spirit Veil memberi Shield agar"
        " pengurangan damage Overlord's Platemail bertahan lebih lama."),
    "海月必拿不死鸟之眼，神器必选护命灵珠\r\n其他装备推荐霸者重装、聚灵水晶、炽热支配者": (
        "Haya must take Eye of the Phoenix, with Life-Saving Bead as the Artifact\nOther items: Overlord's"
        " Platemail, Spirit-Gathering Crystal, Sanguine Dominator",
        "Haya wajib ambil Eye of the Phoenix, dengan Life-Saving Bead sebagai Artifact\nItem lain: Overlord's"
        " Platemail, Spirit-Gathering Crystal, Sanguine Dominator"),
    "玄策推荐带一个炽热支配者解控。": (
        "Xuance should carry a Sanguine Dominator to remove crowd control.",
        "Xuance disarankan membawa Sanguine Dominator untuk menghapus crowd control."),
    "玉环必备大书和圣杯、诸葛亮必备变猪和大书，干将有圣杯即可。": (
        "Yuhuan must have Savant's Wrath and Broken Grail, Kongming a pig-transformation item and Savant's"
        " Wrath, and Gan just needs Broken Grail.",
        "Yuhuan wajib punya Savant's Wrath dan Broken Grail, Kongming wajib punya item pengubah babi dan"
        " Savant's Wrath, dan Gan cukup Broken Grail."),
    "瑶妹通用破茧，名刀看情况去发 。公孙离 日渊破小冰毛 ，看情况将三件输出装其中一件替换为保命装 。": (
        "Yaria: Cocoon-Breaking Garment as standard, Destiny as needed. Arli: Sun Abyss, Daybreaker and a"
        " small frost item; swap one of the three damage items for a survival item as needed.",
        "Yaria: Cocoon-Breaking Garment sebagai standar, Destiny sesuai kebutuhan. Arli: Sun Abyss,"
        " Daybreaker, dan item es kecil; ganti salah satu dari tiga item damage dengan item bertahan hidup"
        " sesuai kebutuhan."),
    "肉装给大司命，法装给东皇，瑶穿变猪分享给队友": (
        "Tank items to Augran, magic items to Donghuang; Yaria wears the pig-transformation item and shares"
        " it with allies",
        "Item tank untuk Augran, item magic untuk Donghuang; Yaria memakai item pengubah babi dan membaginya ke rekan"),
    "花木兰装备推荐无尽+凝渊+炽热，神器推荐机器头和魂灭灵冠。如果遇到对手是艾琳阿离和狄仁杰，建议带凝渊+炽热+反甲或冰心。【有机器头就不需要炽热】": (
        "Mulan: Endless Greatsword + Abyssal Freeze + Sanguine Dominator; Artifacts: Robot Head and"
        " Soul-Destroying Crown. Against Erin, Arli and Di Renjie, take Abyssal Freeze + Sanguine Dominator"
        " + Thorn Heavy Armor or an Ice Heart. 【With Robot Head you don't need Sanguine Dominator】",
        "Mulan: Endless Greatsword + Abyssal Freeze + Sanguine Dominator; Artifact: Robot Head dan"
        " Soul-Destroying Crown. Melawan Erin, Arli, dan Di Renjie, ambil Abyssal Freeze + Sanguine"
        " Dominator + Thorn Heavy Armor atau Ice Heart. 【Dengan Robot Head, tidak perlu Sanguine Dominator】"),
    "花木兰首选无尽和凝渊，对手物理阵容凝渊换冥王，带炽热防止技能被打断。\n神装推荐：机器头、魂灭灵冠、护命灵珠、百锻刀": (
        "Mulan: Endless Greatsword and Abyssal Freeze first; against physical Lineups swap Abyssal Freeze"
        " for Underworld King, and take Sanguine Dominator so her Skills aren't interrupted.\nArtifacts:"
        " Robot Head, Soul-Destroying Crown, Life-Saving Bead, Hundred-Forged Blade",
        "Mulan: utamakan Endless Greatsword dan Abyssal Freeze; melawan Lineup fisik ganti Abyssal Freeze"
        " dengan Underworld King, dan ambil Sanguine Dominator agar Skill-nya tidak terganggu.\nArtifact:"
        " Robot Head, Soul-Destroying Crown, Life-Saving Bead, Hundred-Forged Blade"),
    "装备优先给主C，云中君的卡牌效果可以提升穿戴装备英雄的等级。": (
        "Give Equipment to the Main Carry first; Cirrus's Card Effect raises the Level of Heroes wearing Equipment.",
        "Prioritaskan Equipment untuk Main Carry; Efek Kartu Cirrus meningkatkan Level Hero yang memakai Equipment."),
    "装备优先给朵莉亚：戒律之刃、圣杯、近卫荣耀；米莱迪：炽热、戒律之刃、自然法杖；肉装都给雅典娜": (
        "Equip Dolia first: Blade of Magic Law, Broken Grail, Guardian's Glory; Milady: Sanguine Dominator,"
        " Blade of Magic Law, Nature Staff; all tank items go to Athena",
        "Utamakan Equipment untuk Dolia: Blade of Magic Law, Broken Grail, Guardian's Glory; Milady:"
        " Sanguine Dominator, Blade of Magic Law, Nature Staff; semua item tank untuk Athena"),
    "装备前期可以给虞姬，后期来了敖隐等级高之后再给敖隐。": (
        "Early on, Equipment can go to Consort Yu; later, once Ao'yin arrives and his Level is high, give it to"
        " Ao'yin.",
        "Di awal, Equipment bisa diberikan ke Consort Yu; nanti setelah Ao'yin datang dan Level-nya tinggi, berikan"
        " ke Ao'yin."),
    "装备司空震必备“圣剑”+“免控”，最后一件随便做，肉装给亚瑟，妲己后期是不缺装备的。猛猛提升！抖音-强者无敌": (
        "Sikong Zhen must have “Golden Blade” + “Control Immunity”; the last item is up to you. Tank items"
        " go to Arthur, and Daji never lacks Equipment late. Power up! Douyin: Qiangzhe Wudi",
        "Sikong Zhen wajib punya “Golden Blade” + “Kebal Kontrol”; item terakhir bebas. Item tank untuk"
        " Arthur, dan Daji tidak pernah kekurangan Equipment di akhir. Naikkan terus! Douyin: Qiangzhe Wudi"),
    "装备推荐：\r\n主C海月，必备【不死鸟之眼】和【御灵之纱】，备选【纯净苍穹】，【极寒风暴】和【反伤重甲】各留一件，对付远程，尤其是溜边儿艾琳和嬴政。\r\n神器推荐【护命灵珠】和【机械头】。\r": (
        "Items:\nHaya is the Main Carry: 【Eye of the Phoenix】 and 【Spirit Veil】 are musts, 【Pure Sky】 is"
        " optional, and keep one each of 【Glacial Buckler】 and 【Thorn Heavy Armor】 against ranged enemies,"
        " especially edge-kiting Erin and Ying Zheng.\nArtifacts: 【Life-Saving Bead】 and 【Robot Head】.\n",
        "Rekomendasi item:\nHaya sebagai Main Carry: 【Eye of the Phoenix】 dan 【Spirit Veil】 wajib, 【Pure Sky】"
        " opsional, dan simpan masing-masing satu 【Glacial Buckler】 dan 【Thorn Heavy Armor】 untuk melawan"
        " musuh jarak jauh, terutama Erin dan Ying Zheng yang men-kite dari pinggir.\nArtifact: 【Life-Saving"
        " Bead】 dan 【Robot Head】.\n"),
    "输出装给公孙离，肉装给曹操，后期把孙尚香换帅成周瑜，肉装给周瑜": (
        "Damage items to Arli, tank items to Cao Cao; late, swap Lady Sun into Zhou Yu with Change of"
        " Commander and give him the tank items",
        "Item damage untuk Arli, item tank untuk Cao Cao; di akhir, tukar Lady Sun menjadi Zhou Yu dengan"
        " Pergantian Komandan dan berikan item tank kepadanya"),
    "露娜双重施法月下无限连，猴子高爆发输出，后期传承遗志换帅上海月吕布+觉醒老虎——抖音搜肝帝看攻略": (
        "Luna double-casts her endless moonlit combo and Wukong bursts hard; late, use Inheritance, Last"
        " Will and Change of Commander to bring in Haya, Lu Bu and an Awakened Pei. For the guide, search"
        " Gandi on Douyin",
        "Luna merapal ganda kombo bulan tanpa batasnya dan Wukong memberi burst besar; di akhir, gunakan"
        " Inheritance, Last Will, dan Pergantian Komandan untuk memasukkan Haya, Lu Bu, dan Pei yang Awaken."
        " Untuk panduannya, cari Gandi di Douyin"),
    "韩信：冥王、鸡爪、名刀、变猪、凝渊都可以；神器：末世": (
        "Han Xin: Underworld King, a claw, Destiny, a pig-transformation item or Abyssal Freeze all work;"
        " Artifact: Doomsday",
        "Han Xin: Underworld King, item cakar, Destiny, item pengubah babi, atau Abyssal Freeze semuanya"
        " boleh; Artifact: Doomsday"),

    # ResSeasonAILineupDataBin: LordInfos.Desc
    "T0级别的小偷棋手": ("A T0 thief Chessplayer", "Chessplayer pencuri kelas T0"),
    "上线更高——抖音搜肝帝": ("A higher ceiling. Search Gandi on Douyin", "Batas atas lebih tinggi. Cari Gandi di Douyin"),
    "上限最高，启动后找齐牌上六级无敌。": (
        "The highest ceiling: once it starts and the cards are complete, it's unbeatable at Lv. 6.",
        "Batas atas tertinggi: setelah aktif dan kartu lengkap, tak terkalahkan di Lv. 6."),
    "乔汐专属天赋召唤的英雄也算获得临时等级，非常适配司空震的卡牌效果。": (
        "Heroes summoned by Qiao Xi's Exclusive Talent also count as gaining Temporary Levels, which suits Sikong"
        " Zhen's Card Effect very well.",
        "Hero yang di-Summon oleh Exclusive Talent Qiao Xi juga dihitung mendapat Temporary Level, sangat cocok"
        " dengan Efek Kartu Sikong Zhen."),
    "买牌额外得效果牌，增强前期战力。": (
        "Buying cards gives extra Effect Cards, boosting early power.",
        "Membeli kartu memberi Kartu Efek tambahan, menambah kekuatan di awal."),
    "人家那么可爱，当然是男孩子了": ("So cute, of course he's a boy", "Imut begitu, tentu saja dia laki-laki"),
    "低压运营和基层提拔提等级，公孙离和猪八戒夺取把等级集中": (
        "Low-Pressure Strategy and Base Promotion raise Levels, and Arli's and Zhu Bajie's Steal pools them",
        "Strategi Tekanan Rendah dan Promosi Dasar menaikkan Level, dan Steal Arli serta Zhu Bajie mengumpulkannya"),
    "使用技能每回合稳定提升等级，操作简单，发挥稳定。秘技牌需要等上阵4名英雄后再使用。": (
        "Use the Skill every Round to raise Levels steadily. Simple to play and consistent. Wait until you have 4"
        " Heroes on the board before using the Secret Skill Card.",
        "Gunakan Skill setiap Ronde untuk menaikkan Level dengan stabil. Mudah dimainkan dan konsisten. Tunggu sampai"
        " ada 4 Hero di papan sebelum menggunakan Kartu Secret Skill."),
    "初始机关选择屏障，要根据敌方阵容调整机关陷阱\r的位置，稳定获取螺丝，构筑升级可以优先选择等离子屏障。": (
        "Pick Barrier as the starting Mechanism and adjust the Mechanism traps' positions to the enemy"
        " Lineup to earn Screws steadily; for build upgrades, plasma Shield comes first.",
        "Pilih Barrier sebagai Mekanisme awal dan sesuaikan posisi jebakan Mekanisme dengan Lineup lawan"
        " agar Screw terus didapat; untuk peningkatan build, utamakan plasma Shield."),
    "刷牌选手": ("A card roller", "Jagoan refresh kartu"),
    "前期快速升5级，记得上场3个河洛英雄后开第一个秘技。凑齐体系牌确保连胜后再升6级，第二个秘技相当于点兵点将。": (
        "Rush to Lv. 5 early, and open the first Secret Skill once 3 Central Plains Heroes are on the board."
        " Go to Lv. 6 only after the core cards secure a win streak; the second Secret Skill works like"
        " Drafting Troops.",
        "Cepat naik ke Lv. 5 di awal, dan buka Secret Skill pertama setelah 3 Hero Central Plains di papan."
        " Naik ke Lv. 6 hanya setelah kartu inti menjamin win streak; Secret Skill kedua bekerja seperti"
        " Drafting Troops."),
    "启动快，觉醒快，在中期能够快速抢牌和觉醒。": (
        "Starts fast and Awakens fast, grabbing cards and Awakening quickly mid game.",
        "Cepat aktif dan cepat Awaken, merebut kartu dan Awaken dengan cepat di pertengahan permainan."),
    "启动最快，有白歌、孙膑同行可以用镜卡同行——抖音搜肝帝": (
        "The fastest start; against Bai Ge or Sun Bin on the same Lineup, use Jing to hold their cards."
        " Search Gandi on Douyin",
        "Paling cepat aktif; jika Bai Ge atau Sun Bin memakai Lineup yang sama, gunakan Jing untuk menahan"
        " kartu mereka. Cari Gandi di Douyin"),
    "在万象棋，我可不刮哦": ("In this game, I don't lose!", "Di game ini, aku tidak kalah!"),
    "复制对手的英雄，提升己方战力。": (
        "Copies opponents' Heroes to boost your own power.",
        "Menyalin Hero lawan untuk menambah kekuatan sendiri."),
    "大河流域的低阶英雄能够为香香提供可观的攻击力加成，帮助她在前期打出稳定且强力的输出，后期香香也有很强的作战能力。": (
        "Low-Tier Riverlands Heroes give Xiangxiang a sizable Attack bonus, helping her deal steady, strong damage"
        " early on; Xiangxiang also fights well in the late game.",
        "Hero Riverlands Tier rendah memberi Xiangxiang bonus Attack yang besar, membantunya memberikan damage yang"
        " stabil dan kuat di awal; di akhir game Xiangxiang juga kuat bertarung."),
    "奇才和灵感爆发切庄周，无限打合成即可": (
        "Use Prodigy and Inspiration Burst on Zhuangzi and keep Combining",
        "Gunakan Prodigy dan Inspiration Burst pada Zhuangzi dan terus Combine"),
    "如梦似幻大概率让阵容直接成形，梦幻引擎可以提供额外的古币来源。": (
        "Dreamlike will most likely complete the Lineup outright, and Dream Engine adds another source of"
        " Ancient Coins.",
        "Dreamlike kemungkinan besar langsung melengkapi Lineup, dan Dream Engine memberi sumber Ancient"
        " Coin tambahan."),
    "姜导适配养单C的阵容，能增加英雄等级和提供吸血。技能给百里玄策使用。": (
        "Director Jiang suits Lineups built around a single Carry: he raises Hero Levels and grants Lifesteal. Use his"
        " Skill on Xuance.",
        "Director Jiang cocok untuk Lineup yang membangun satu Carry: menaikkan Level Hero dan memberi Lifesteal."
        " Gunakan Skill-nya pada Xuance."),
    "嬴律的沉淀收益、固定收益为其提供超高的经济来源，帮助阵容快速成形。收购双倍等政策增加资源的囤积": (
        "Ying Lu's Accumulated Profit and Fixed Income give a huge economy that completes the Lineup fast,"
        " and policies such as double acquisitions stockpile more resources",
        "Accumulated Profit dan Pendapatan Tetap Ying Lu memberi ekonomi sangat besar agar Lineup cepat"
        " terbentuk, dan kebijakan seperti akuisisi ganda menimbun lebih banyak sumber daya"),
    "安琪拉的飞行器既能给英雄提升临时等级，还可以开出范围自爆或者吸取等级的强化，很适合养一些比较肉的英雄作为主C。": (
        "Angela's Aircraft gives Heroes Temporary Levels and can roll an area self-destruct or"
        " Level-draining enhancement, so it suits raising a tankier Hero as the Main Carry.",
        "Pesawat Angela memberi Hero Temporary Level dan bisa mendapat peningkatan self-destruct area atau"
        " penyerap Level, jadi cocok untuk membesarkan Hero yang lebih tangguh sebagai Main Carry."),
    "完美适配这套阵容的棋手": (
        "The Chessplayer that fits this Lineup perfectly",
        "Chessplayer yang paling cocok untuk Lineup ini"),
    "小妲己的技能可以获得大量效果牌，非常适合有芈月的阵容，而小妲己的专属天赋可以稳定的使用2次高阶推演战术给蒙恬提供10蓝。": (
        "Little Daji's Skill brings lots of Effect Cards, which suits Lineups with Mi Yue, and her Exclusive"
        " Talent reliably casts Advanced Deduction Tactics twice to give Meng Tian 10 Mana.",
        "Skill Little Daji memberi banyak Kartu Efek, cocok untuk Lineup dengan Mi Yue, dan Exclusive"
        " Talent-nya dengan stabil memakai Advanced Deduction Tactics dua kali untuk memberi Meng Tian 10 Mana."),
    "就是够轮椅！": ("It's just that easy!", "Memang semudah itu!"),
    "庄小鱼最适配的高阶阵容除了河洛就是大河，如果对方没有司空震等aoe清图腾，这套还是非常强的。": (
        "Besides Central Plains, Riverlands is Zhuang Xiaoyu's best high-Tier Lineup; unless the enemy has"
        " Sikong Zhen or other AOE to clear Totems, this build is very strong.",
        "Selain Central Plains, Riverlands adalah Lineup Tier tinggi terbaik untuk Zhuang Xiaoyu; kecuali"
        " lawan punya Sikong Zhen atau AOE lain untuk membersihkan Totem, build ini sangat kuat."),
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
    "开局和第4回合选【卦象·节】，第一个秘技选能量，棋手快速升5级后马上搜牌凑齐阵容，接着用卦象·丰临时刷新找露娜和合成。": (
        "At the start and in Round 4 pick 【Hexagram: Moderation】 and take Energy for the first Secret Skill;"
        " rush the Chessplayer to Lv. 5, then search at once to complete the Lineup, and use Hexagram:"
        " Abundance's temporary Refreshes to find Luna and Combine.",
        "Di awal dan Ronde 4 pilih 【Hexagram: Moderation】 dan ambil Energy untuk Secret Skill pertama; cepat"
        " naikkan Chessplayer ke Lv. 5, lalu segera cari kartu untuk melengkapi Lineup, dan gunakan Refresh"
        " sementara dari Hexagram: Abundance untuk mencari Luna dan Combine."),
    "战略决策优先沉淀收益、固定收益和风险对冲。秘技优先拿升级经验的，6级专属选【资源再分配】有对手淘汰能拿神器和回血。": (
        "For Strategic Decisions, take Accumulated Profit, Fixed Income and Risk Hedging first. For Secret"
        " Skills, take the EXP ones; at Lv. 6 pick the exclusive 【Resource Redistribution】, which gives"
        " Artifacts and healing when an opponent is eliminated.",
        "Untuk Strategic Decision, utamakan Accumulated Profit, Pendapatan Tetap, dan Lindung Nilai Risiko."
        " Untuk Secret Skill, ambil yang memberi EXP; di Lv. 6 pilih eksklusif 【Resource Redistribution】,"
        " yang memberi Artifact dan pemulihan saat lawan tereliminasi."),
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
    "明先生很早的版本加强过之后，一发不可收拾，出色的搜牌和经济能力稳做领跑大哥，而嬴政不吃等级，命运馈赠全能量直接起飞。": (
        "Since a buff in a very early version, Mr. Ming has been unstoppable: his excellent card search and"
        " economy keep him leading the pack, and since Ying Zheng doesn't need Levels, taking all Energy"
        " from Fate Gift sends him flying.",
        "Sejak di-buff di versi yang sangat awal, Mr. Ming tak terbendung: pencarian kartu dan ekonominya"
        " yang sangat baik membuatnya selalu memimpin, dan karena Ying Zheng tidak butuh Level, mengambil"
        " semua Energy dari Fate Gift membuatnya melesat."),
    "明先生拥有强大的经济天赋，每回合免费刷新可以帮我们更好的找齐阵容；玩泳池派对时，先开卦象：节，之后都开卦象：丰就可以": (
        "Mr. Ming has a strong economy Talent, and his free Refresh every Round helps us complete the"
        " Lineup; for Pool Party, open Hexagram: Moderation first, then always Hexagram: Abundance",
        "Mr. Ming punya Talent ekonomi yang kuat, dan Refresh gratisnya setiap Ronde membantu melengkapi"
        " Lineup; untuk Pool Party, buka Hexagram: Moderation dulu, lalu selalu Hexagram: Abundance"),
    "昭君有一个冰冻强化为：冻结后，英雄不变、觉醒进度+2，该强化极大程度加强了大河龙蛇的成型速度！": (
        "Zhaojun has a Freeze Enhancement: when frozen, a Hero stays the same and gains +2 Awakening"
        " progress. It greatly speeds up Riverlands Dragon-Snake!",
        "Zhaojun punya Freeze Enhancement: saat dibekukan, Hero tetap sama dan progres Awaken +2. Ini sangat"
        " mempercepat Dragon-Snake Riverlands terbentuk!"),
    "最后 不要因为犹豫错过你的最佳选择 ！": (
        "Finally, don't miss your best pick by hesitating!",
        "Terakhir, jangan sampai pilihan terbaikmu lewat karena ragu!"),
    "最适配逐鹿体系的棋手之一": (
        "One of the best Chessplayers for Zhulu Plateau",
        "Salah satu Chessplayer paling cocok untuk Zhulu Plateau"),
    "有同行偷同行，没同行留驭势一起用打合成": (
        "Against a player on the same Lineup, steal from them; otherwise save Momentum Control and use them"
        " together to Combine",
        "Jika ada pemain dengan Lineup sama, curi darinya; jika tidak, simpan Momentum Control dan gunakan"
        " bersama untuk Combine"),
    "棋手技能提供加等级、额外效果牌等增益。": (
        "The Chessplayer Skill provides buffs such as extra Levels and Effect Cards.",
        "Skill Chessplayer memberi buff seperti Level dan Kartu Efek tambahan."),
    "棋手技能随机给牌，随到阵容牌可加速阵容成型。前期1能量拿牌易连胜。": (
        "The Chessplayer Skill gives random cards; drawing Lineup cards speeds up the build. Cards for 1"
        " Energy early make win streaks easy.",
        "Skill Chessplayer memberi kartu acak; mendapat kartu Lineup mempercepat build. Kartu seharga 1"
        " Energy di awal memudahkan win streak."),
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
    "瑶妹前期需要打连胜，小鹿作为优质肉盾解决了大河龙蛇前期没有前排的问题，奉献的机制再次拉高了后期的上限。": (
        "Yaria needs an early win streak; the deer is a solid tank that fixes Riverlands Dragon-Snake's lack"
        " of an early front row, and its offering mechanic raises the late-game ceiling further.",
        "Yaria butuh win streak di awal; rusa adalah tank andal yang menutup kelemahan Dragon-Snake"
        " Riverlands tanpa barisan depan di awal, dan mekanisme persembahannya makin menaikkan batas atas di akhir."),
    "瑶妹的小鹿能提供稳定前排，配合图腾流前期不俗的战力来取得胜利；后期小鹿的等级奉献还能进一步提升图腾全队的等级。": (
        "Yaria's deer gives a steady frontline that, with the Totem Build's strong early power, wins fights; later,"
        " the deer's Level devotion raises the whole Totem team's Levels further.",
        "Rusa Yaria memberi frontline yang stabil, bersama kekuatan awal Build Totem yang lumayan untuk meraih"
        " kemenangan; nanti, Level yang dipersembahkan rusa semakin menaikkan Level seluruh tim Totem."),
    "白歌可以通过即兴创作和灵感爆发，单回合打出大量露娜激活整备。并且通过效果锦囊拿到大量的效果卡，非常适配这套阵容": (
        "With Improvisation and Inspiration Burst, Bai Ge can play lots of Luna in one Round to trigger"
        " Prepare, and gets plenty of Effect Cards from Effect Guides: a great fit for this Lineup",
        "Dengan Improvisasi dan Inspiration Burst, Bai Ge bisa memainkan banyak Luna dalam satu Ronde untuk"
        " memicu Prepare, dan mendapat banyak Kartu Efek dari Panduan Efek: sangat cocok untuk Lineup ini"),
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
    "血量最稳，有白歌可以拿来卡白歌牌，启动更快——抖音搜肝帝": (
        "The steadiest HP; against Bai Ge, use it to hold Bai Ge's cards, and it starts faster. Search Gandi"
        " on Douyin",
        "HP paling stabil; jika ada Bai Ge, gunakan untuk menahan kartu Bai Ge, dan lebih cepat aktif. Cari"
        " Gandi di Douyin"),
    "装备神器多，中期启动比较吃经济天赋，有经济天赋上限也很高。": (
        "Plenty of Equipment and Artifacts; the mid-game start leans on economy Talents, and with them the"
        " ceiling is high too.",
        "Banyak Equipment dan Artifact; aktivasi di pertengahan bergantung pada Talent ekonomi, dan dengan"
        " itu batas atasnya juga tinggi."),
    "超冷门巨阴吃分棋手": (
        "An ultra-niche, super-sneaky Chessplayer that farms points",
        "Chessplayer langka dan sangat licik untuk mengumpulkan poin"),
    "这个只能昭君玩，完全依赖于昭君机制": (
        "Only Zhaojun can play this: it depends entirely on her mechanic",
        "Hanya Zhaojun yang bisa memainkannya: sepenuhnya bergantung pada mekanismenya"),
    "这套阵容主要靠使用效果牌时，触发芈月的卡牌效果培养英雄，小妲己能提供更多的效果牌，非常适合有芈月的阵容。": (
        "This Lineup mainly grows Heroes by playing Effect Cards to trigger Mi Yue's Card Effect. Little Daji provides"
        " more Effect Cards, a great fit for Lineups with Mi Yue.",
        "Lineup ini terutama membesarkan Hero dengan menggunakan Effect Card untuk memicu Efek Kartu Mi Yue. Little Daji"
        " memberi lebih banyak Effect Card, sangat cocok untuk Lineup dengan Mi Yue."),
    "闹闹有非常优秀的找牌机制，可以保证中期体系成形更快，6本后闹闹也可以多选择一个阵营天赋，大河的专属天赋都很强。": (
        "Naonao has an excellent card-finding mechanic that completes the core sooner mid game, and after"
        " Lv. 6 she can pick one more Faction Talent; Riverlands' Exclusive Talents are all strong.",
        "Naonao punya mekanisme pencarian kartu yang sangat baik sehingga kartu inti lengkap lebih cepat di"
        " pertengahan, dan setelah Lv. 6 dia bisa memilih satu Talent Faction tambahan; Exclusive Talent"
        " Riverlands semuanya kuat."),
    "闹闹的技能只花1点能量拿牌，前期经常能随到需要的牌。秘技牌在4级用，有概率能出李信。": (
        "Naonao's Skill gets a card for just 1 Energy and often rolls the card you need early on. Use the Secret Skill"
        " Card at Lv. 4 for a chance at Li Xin.",
        "Skill Naonao mengambil kartu hanya dengan 1 Energy dan di awal sering mendapat kartu yang dibutuhkan."
        " Gunakan Kartu Secret Skill di Lv. 4 untuk peluang mendapat Li Xin."),
    "闹闹的秘技和技能可以快速帮忙找牌，额外的阵营天赋则是提高阵容上限。": (
        "Naonao's Secret Skills and Skill find cards fast, and the extra Faction Talent raises the Lineup's ceiling.",
        "Secret Skill dan Skill Naonao cepat membantu mencari kartu, dan Talent Faction tambahan menaikkan"
        " batas atas Lineup."),
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
    "马可有冰耀宝石镜和复制场上三张牌，可以快速觉醒所有牌，后期还有增伤，可以完美适配三分射\n": (
        "Marco has the frost gem mirror and copies three cards on the board, Awakening every card fast, and"
        " adds damage late: a perfect fit for Three Kingdoms Marksmen\n",
        "Marco punya cermin permata es dan menyalin tiga kartu di papan, membuat semua kartu cepat Awaken,"
        " dan menambah damage di akhir: sangat cocok untuk Marksman Three Kingdoms\n"),

    # ResSeasonAILineupDataBin: Name (a narrow card and the share code's 【name】 prefix)
    "999韩信太容易": ("Lv. 999 Han Xin Made Easy", "Han Xin Lv. 999 Itu Mudah"),
    "三分倒转-肝帝\r": ("Three Kingdoms Reversal - Gandi", "Three Kingdoms Reversal - Gandi"),
    "三分登场流": ("Three Kingdoms Deploy Build", "Build Deploy Three Kingdoms"),
    "三阶无阵营组合": ("Factionless Tier 3 Combo", "Kombo Tier 3 Tanpa Faction"),
    "乔汐速六司空震": ("Qiao Xi Rush-6 Sikong Zhen", "Qiao Xi Rush 6 Sikong Zhen"),
    "二保一艾琳": ("Erin, Two Guard One", "Erin, Dua Jaga Satu"),
    "低压嬴律无脑吃分": ("Low-Pressure Ying Lu Easy Points", "Poin Mudah Ying Lu Tekanan Rendah"),
    "古币成长流": ("Ancient Coin Growth Build", "Build Growth Ancient Coin"),
    "图腾成长流": ("Totem Growth Build", "Build Growth Totem"),
    "大河图腾流": ("Riverlands Totem Build", "Build Riverlands Totem"),
    "大河龙蛇": ("Riverlands Dragon-Snake", "Dragon-Snake Riverlands"),
    "妲己轮椅日落倒转": ("Daji Autopilot Sunset Reversal", "Sunset Reversal Autopilot Daji"),
    "嫦娥四小队": ("Chang'e Squad of Four", "Regu Empat Chang'e"),
    "孙小宾三分倒转": ("Sun Xiaobin Three Kingdoms Reversal", "Three Kingdoms Reversal Sun Xiaobin"),
    "安琪拉廉颇炸盾": ("Angela Lian Po Shield Burst", "Shield Burst Lian Po Angela"),
    "安琪拉整备流": ("Angela Prepare Build", "Build Prepare Angela"),
    "安琪拉自爆海月": ("Angela Self-Destruct Haya", "Haya Self-Destruct Angela"),
    "常小娥四人队": ("Chang Xiao'e Team of Four", "Tim Empat Chang Xiao'e"),
    "常小娥海陆空": ("Chang Xiao'e Land, Sea, and Air", "Land, Sea, and Air Chang Xiao'e"),
    "庄小鱼高阶龙蛇": ("Zhuang Xiaoyu High-Tier Dragon-Snake", "Dragon-Snake Tier Tinggi Zhuang Xiaoyu"),
    "弈星雷霆战机": ("Yixing Thunder Fighter", "Thunder Fighter Yixing"),
    "战术牌成长流": ("Tactics Card Growth Build", "Build Growth Tactics Card"),
    "新手全5阶昭君": ("Beginner All-Tier-5 Zhaojun", "Zhaojun Semua Tier 5 Pemula"),
    "无限复活木兰": ("Infinite Revive Mulan", "Mulan Revive Tanpa Batas"),
    "日落海整备流": ("Sunset Prepare Build", "Build Prepare Sunset"),
    "明先生泳池派对": ("Mr. Ming Pool Party", "Pool Party Mr. Ming"),
    "明先生逐鹿嬴政": ("Mr. Ming Zhulu Plateau Ying Zheng", "Ying Zheng Zhulu Plateau Mr. Ming"),
    "最强弈星偷牌河洛": ("Strongest Yixing Card-Steal Central Plains", "Central Plains Curi Kartu Yixing Terkuat"),
    "河洛古币流": ("Central Plains Ancient Coin Build", "Build Ancient Coin Central Plains"),
    "河洛牺牲李信": ("Central Plains Sacrifice Li Xin", "Li Xin Sacrifice Central Plains"),
    "玉环999司空震": ("Yuhuan Lv. 999 Sikong Zhen", "Sikong Zhen Lv. 999 Yuhuan"),
    "班叔奶柱流": ("Uncle Ban Healing Barrier Build", "Build Barrier Heal Uncle Ban"),
    "班叔龙蛇陷阱流": ("Uncle Ban Dragon-Snake Trap Build", "Build Trap Dragon-Snake Uncle Ban"),
    "瑶妹牺牲李信": ("Yaria Sacrifice Li Xin", "Li Xin Sacrifice Yaria"),
    "白歌三分倒转刺": ("Bai Ge Three Kingdoms Reversal Assassins", "Assassin Three Kingdoms Reversal Bai Ge"),
    "色彩香香开团射": ("Secai's Xiangxiang Initiate Marksmen", "Marksman Initiate Xiangxiang Secai"),
    "蒙恬召唤": ("Meng Tian Summons", "Summon Meng Tian"),
    "逐鹿战术牌流": ("Zhulu Plateau Tactics Card Build", "Build Tactics Card Zhulu Plateau"),
    "逐鹿雷霆战机": ("Zhulu Plateau Thunder Fighter", "Thunder Fighter Zhulu Plateau"),
    "闹闹日落海": ("Naonao Sunset", "Sunset Naonao"),
    "闹闹花木兰": ("Naonao Mulan", "Mulan Naonao"),
    "阿离干将遗志海月": ("Arli Gan Last Will Haya", "Haya Last Will Gan Arli"),
    "阿离颗秒万暴守约": ("Arli One-Shot Crit Shouyue", "Shouyue Crit Sekali Tembak Arli"),
    "马可万血猪": ("Marco 10K-HP Zhu Bajie", "Marco Zhu Bajie 10K HP"),
    "马可三分射": ("Marco Three Kingdoms Marksmen", "Marksman Three Kingdoms Marco"),
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
    "3级小刷找到虞姬和鬼谷子稳血，运气好拿到少司缘张良，或者拿一张云中君或者瑶，保证五级开如梦似幻的时候场上有四张大河阵容不会开歪。\n天赋以阵容天赋和稳血为主。": (
        "At Lv. 3, roll a little to find Consort Yu and Guiguzi and protect your HP; with luck you get"
        " Dyadia and Liang, or take a Cirrus or Yaria, so there are four Riverlands cards on the board when"
        " Dreamlike opens at Lv. 5 and it doesn't go astray.\nTalents: Lineup Talents and HP protection.",
        "Di Lv. 3, sedikit refresh untuk mencari Consort Yu dan Guiguzi dan menjaga HP; jika beruntung dapat"
        " Dyadia dan Liang, atau ambil Cirrus atau Yaria, agar ada empat kartu Riverlands di papan saat"
        " Dreamlike dibuka di Lv. 5 dan hasilnya tidak meleset.\nTalent: Talent Lineup dan penjaga HP."),
    "4回合回溯上回合的两张牌，然后把手上的牌全用了，打够8张解锁时之回环，然后直接升四，升四找到阵容体系牌，然后先不打，找齐后先用时之回环，再打阵容体系牌，之后升五找露娜周瑜，依旧不大存在手上，然后升六，开永恒时之回环，在回环里打这些牌": (
        "Round 4: Undo last Round's two cards, then play everything in hand; play 8 cards to unlock Time"
        " Loop, then go straight to Lv. 4 and find the core cards, but don't play them yet. Once you have"
        " them all, use Time Loop first, then play them. Next go to Lv. 5 for Luna and Zhou Yu, again"
        " keeping them in hand, then go to Lv. 6, open Eternal Time Loop and play these cards inside the loop",
        "Ronde 4: Urungkan dua kartu dari Ronde sebelumnya, lalu mainkan semua kartu di tangan; mainkan 8"
        " kartu untuk membuka Time Loop, lalu langsung naik ke Lv. 4 dan cari kartu inti, tapi jangan"
        " dimainkan dulu. Setelah lengkap, gunakan Time Loop dulu, baru mainkan. Lalu naik ke Lv. 5 untuk"
        " Luna dan Zhou Yu, tetap simpan di tangan, lalu naik ke Lv. 6, buka Eternal Time Loop dan mainkan"
        " kartu-kartu ini di dalam loop"),
    "4至7回合不花能量自动升级，获得的效果牌优先选找3阶英雄的，最好效果牌开出猪八戒或拍卖拿到，没有的话，8至11回合升至3级去找猪八戒。梦奇必拿，上阵后再卖掉非常划算。": (
        "In Rounds 4-7, spend no Energy and level up automatically. For Effect Cards, prefer ones that find Tier 3"
        " Heroes; ideally get Zhu Bajie from an Effect Card or the Auction, otherwise level up to 3 in Rounds 8-11 to"
        " look for him. Always take Menki: fielding him and then selling him is great value.",
        "Di Ronde 4-7, jangan pakai Energy dan biarkan naik level otomatis. Untuk Effect Card, utamakan yang mencari"
        " Hero Tier 3; idealnya dapatkan Zhu Bajie dari Effect Card atau Lelang, kalau tidak, naik ke Lv. 3 di Ronde"
        " 8-11 untuk mencarinya. Menki wajib diambil: turunkan ke papan lalu jual, sangat menguntungkan."),
    "5本后找敖隐和东皇，有多余人口补瑶和太乙挂给敖隐/对手单核阵容给东皇\n买卖杨玉环觉醒其余低阶卡；二拍优先级：敖隐＞东皇＞大司命；": (
        "After Lv. 5 find Ao'yin and Donghuang; with spare Population add Yaria and Taiyi, linked to Ao'yin,"
        " or to Donghuang against single-carry Lineups\nBuy and sell Yuhuan to Awaken the other low-Tier"
        " cards; 2nd Auction priority: Ao'yin > Donghuang > Augran;",
        "Setelah Lv. 5 cari Ao'yin dan Donghuang; jika Populasi tersisa, tambahkan Yaria dan Taiyi yang"
        " dihubungkan ke Ao'yin, atau ke Donghuang melawan Lineup carry tunggal\nBeli dan jual Yuhuan untuk"
        " meng-Awaken kartu Tier rendah lainnya; prioritas Lelang ke-2: Ao'yin > Donghuang > Augran;"),
    "5本补鲁班七号，刷体系牌打合成。最后一张驭势有同行留给同行，没同行就偷钟馗/太乙等牌打决赛，三拍后上6本。三拍推荐:扶摇直上/新生力量": (
        "At Lv. 5 add Luban No.7, roll for core cards and Combine. Save the last Momentum Control for a"
        " player on the same Lineup; if there's none, steal Kui, Taiyi and the like for the finals. Go to"
        " Lv. 6 after the 3rd Auction. 3rd Auction picks: Soaring High / New Force",
        "Di Lv. 5 tambahkan Luban No.7, refresh kartu inti dan Combine. Simpan Momentum Control terakhir"
        " untuk pemain dengan Lineup sama; jika tidak ada, curi Kui, Taiyi, dan sejenisnya untuk final. Naik"
        " ke Lv. 6 setelah Lelang ke-3. Pilihan Lelang ke-3: Soaring High / New Force"),
    "5级后主要找吕布，吕布吸血效果能大幅增加英雄的生存能力，吕布也是一个强力输出英雄，后期可以培养他。如果有换帅可以把低阶英雄的等级换给吕布。有遗志和传承对孙尚香使用，孙尚香输出低后期建议换掉。": (
        "After Lv. 5, look mainly for Lu Bu: his Lifesteal greatly improves Hero survival, and he is also a strong"
        " damage dealer worth building up late. With Change of Commander, swap a low-Tier Hero's Levels onto Lu Bu."
        " Use Last Will and Inheritance on Lady Sun; her damage is low, so replace her late.",
        "Setelah Lv. 5, cari terutama Lu Bu: Lifesteal-nya sangat meningkatkan daya tahan Hero, dan dia juga damage"
        " dealer kuat yang layak dibesarkan di akhir. Dengan Pergantian Komandan, pindahkan Level Hero Tier rendah ke"
        " Lu Bu. Gunakan Last Will dan Inheritance pada Lady Sun; damage-nya rendah, jadi sebaiknya diganti di akhir."),
    "6回合左右上4本找体系牌，遇到同行直接用两张驭势。灵活使用老夫子打合成找牌。二拍优先级:赢政>庄周＞杨玉环>蒙伢>鲁班七号": (
        "Around Round 6 go to Lv. 4 for the core cards, and against a player on the same Lineup use both"
        " Momentum Controls at once. Use Fuzi flexibly to Combine and find cards. 2nd Auction priority: Ying"
        " Zheng > Zhuangzi > Yuhuan > Meng Ya > Luban No.7",
        "Sekitar Ronde 6 naik ke Lv. 4 untuk kartu inti, dan jika ada pemain dengan Lineup sama langsung"
        " gunakan dua Momentum Control. Gunakan Fuzi dengan fleksibel untuk Combine dan mencari kartu."
        " Prioritas Lelang ke-2: Ying Zheng > Zhuangzi > Yuhuan > Meng Ya > Luban No.7"),
    "7回合一般就上5级了，免费刷新不出嬴政不着急，存钱第八回合选卦象丰，直接爆牌刷新，找齐阵容。\n蒙犽是打出位，存够四张打出觉醒就卖。\n嬴政后期的上限就在于机器头和噬神之书，打合成通过效果锦囊，或者商店的武装分解，找特殊装备。": (
        "You usually reach Lv. 5 in Round 7. Don't worry if free Refreshes don't bring Ying Zheng: save up,"
        " pick Abundance for the Hexagram in Round 8, then flood Refreshes to complete the Lineup.\nMeng Ya"
        " is the play slot: sell him once he Awakens after four plays.\nYing Zheng's ceiling late comes from"
        " Robot Head and Insatiable Tome: find the special items through Effect Guides from Combines or the"
        " shop's Weapon Dismantle.",
        "Biasanya Lv. 5 tercapai di Ronde 7. Jangan khawatir jika Refresh gratis tidak memberi Ying Zheng:"
        " menabung, pilih Abundance untuk Hexagram di Ronde 8, lalu refresh habis-habisan untuk melengkapi"
        " Lineup.\nMeng Ya adalah slot main: jual setelah dia Awaken dari empat kali dimainkan.\nBatas atas"
        " Ying Zheng di akhir ada pada Robot Head dan Insatiable Tome: cari item spesial lewat Panduan Efek"
        " dari Combine atau Weapon Dismantle di toko."),
    "8回合升4，不操作，10回合升级到五级，复制留着觉醒小乔和甄姬，都觉醒后，复制露娜，不断打出登场和三分牌即可，13回合到6级选阳光普照\n\n": (
        "Round 8: go to Lv. 4 and do nothing else; Round 10: reach Lv. 5 and keep copies to Awaken Xiao Qiao"
        " and Lady Zhen. Once both have Awakened, copy Luna and keep playing Deploy and Three Kingdoms"
        " cards; in Round 13, at Lv. 6, pick Radiant Sunshine\n\n",
        "Ronde 8: naik ke Lv. 4 tanpa aksi lain; Ronde 10: naik ke Lv. 5 dan simpan salinan untuk"
        " meng-Awaken Xiao Qiao dan Lady Zhen. Setelah keduanya Awaken, salin Luna dan terus mainkan kartu"
        " Deploy dan Three Kingdoms; di Ronde 13, di Lv. 6, pilih Radiant Sunshine\n\n"),
    "一回合机关选择选屏障，放第一排铺满，干将/孙膑等牌各买一张，先觉醒干将后觉醒孙膑。一拍优先级:刘禅>明世隐>梦奇": (
        "Round 1: pick Barrier as the Mechanism and fill the front row with it; buy one each of Gan, Sun Bin"
        " and the like, Awakening Gan first, then Sun Bin. 1st Auction priority: Liu Shan > Ming > Menki",
        "Ronde 1: pilih Barrier sebagai Mekanisme dan penuhi barisan depan; beli masing-masing satu Gan, Sun"
        " Bin, dan sejenisnya, Awaken Gan dulu, lalu Sun Bin. Prioritas Lelang ke-1: Liu Shan > Ming > Menki"),
    "一直打吟柔，司空震等级333并觉醒后，阿科米亚核心等级666级后，司空震就能到999了": (
        "Keep playing triples: once Sikong Zhen is Lv. 333 and Awakened and the Arcomia Core reaches Lv."
        " 666, Sikong Zhen hits Lv. 999",
        "Terus mainkan tripel: setelah Sikong Zhen Lv. 333 dan Awaken serta Arcomia Core mencapai Lv. 666,"
        " Sikong Zhen mencapai Lv. 999"),
    "七回合拍卖优先姜子牙，无上限的去拿，司空震最多6能量，海诺莱西奥最多五能量，7回合或者8回合后升五级后边打吟柔（指的是打三张同阵营，同品阶的牌）边找阵容牌，找齐后，一直打吟柔，两次大招用完后，升六级": (
        "At the Round 7 Auction take Ziya first, at any price; Sikong Zhen up to 6 Energy, Heino and Alessio"
        " up to 5. After reaching Lv. 5 in Round 7 or 8, play triples (three cards of the same Faction and"
        " Tier) while searching for Lineup cards; once complete, keep playing triples, and after both"
        " Ultimates are used, go to Lv. 6",
        "Di Lelang Ronde 7 utamakan Ziya, berapa pun harganya; Sikong Zhen hingga 6 Energy, Heino dan"
        " Alessio hingga 5. Setelah naik ke Lv. 5 di Ronde 7 atau 8, mainkan tripel (tiga kartu dengan"
        " Faction dan Tier yang sama) sambil mencari kartu Lineup; setelah lengkap, terus mainkan tripel,"
        " dan setelah kedua Ultimate terpakai, naik ke Lv. 6"),
    "上3本找齐体系牌，瑶和云中君二选一过渡，保证战力能持续连胜后，存钱\n上5本；一拍优先级/觉醒优先级：少司缘＞张良＞虞姬＞云中君；": (
        "At Lv. 3 gather the core cards, using Yaria or Cirrus as a stopgap; once your power can hold the"
        " streak, save up\nfor Lv. 5. 1st Auction and Awaken priority: Dyadia > Liang > Consort Yu > Cirrus;",
        "Di Lv. 3 kumpulkan kartu inti, dengan Yaria atau Cirrus sebagai pengisi sementara; setelah kekuatan"
        " cukup untuk menjaga win streak, menabung\nuntuk Lv. 5. Prioritas Lelang ke-1 dan Awaken: Dyadia >"
        " Liang > Consort Yu > Cirrus;"),
    "上5本后使用[朋友多多]找花木兰、武则天，体系牌齐后上6本选阵营天赋，\n存整备、登场效果牌，保证每回合花木兰复活次数足够。": (
        "After Lv. 5, use [Many Friends] to find Mulan and Wu Zetian; with all core cards, go to Lv. 6 and"
        " pick the Faction Talent,\nand save Prepare and Deploy Effect Cards so Mulan has enough Revives every Round.",
        "Setelah Lv. 5, gunakan [Banyak Teman] untuk mencari Mulan dan Wu Zetian; setelah kartu inti"
        " lengkap, naik ke Lv. 6 dan pilih Talent Faction,\nlalu simpan Kartu Efek Prepare dan Deploy agar"
        " Revive Mulan cukup setiap Ronde."),
    "上5本找觉醒诸葛亮找杨玉环，阵容齐全后存钱上6本，选择等离子屏障强化，找到杨玉环后挂明世隐。三拍优先级:众星闪耀>扶摇直上>军械库": (
        "At Lv. 5, Awaken Kongming and find Yuhuan; with the Lineup complete, save up for Lv. 6 and pick"
        " Level 3 plasma Shield, then link Ming to Yuhuan once you find her. 3rd Auction priority: Starry"
        " Radiance > Soaring High > Armory",
        "Di Lv. 5, Awaken Kongming dan cari Yuhuan; setelah Lineup lengkap, menabung untuk Lv. 6 dan pilih"
        " plasma Shield Level 3, lalu hubungkan Ming ke Yuhuan setelah menemukannya. Prioritas Lelang ke-3:"
        " Starry Radiance > Soaring High > Armory"),
    "上一张奕星，一张牛魔，一张狂铁后，再合成三次奕星觉醒奕星，锦囊里开到日落海牌直接上，三回合拍卖优先拿姬小满，可以顶到6能量，其次亚瑟可以顶到4能量，其他日落海英雄最多3能量，然后第四回合上场拍卖回来的日落海英雄，然后直接升五": (
        "Field a Yixing, a Niu Mo and a Biron, then Combine Yixing three more times to Awaken him; play any"
        " Sunset card a Kit gives. At the Round 3 Auction take Mayene first, worth up to 6 Energy, then"
        " Arthur up to 4, and other Sunset Heroes up to 3. In Round 4 field the Sunset Heroes from the"
        " Auction, then go straight to Lv. 5",
        "Pasang satu Yixing, satu Niu Mo, dan satu Biron, lalu Combine Yixing tiga kali lagi untuk"
        " meng-Awaken-nya; langsung mainkan kartu Sunset dari Kit. Di Lelang Ronde 3 utamakan Mayene, layak"
        " hingga 6 Energy, lalu Arthur hingga 4, dan Hero Sunset lain hingga 3. Di Ronde 4 pasang Hero"
        " Sunset dari Lelang, lalu langsung naik ke Lv. 5"),
    "上三级找全阵容英雄，太乙除外": (
        "At Lv. 3, find every Lineup Hero except Taiyi",
        "Di Lv. 3, cari semua Hero Lineup kecuali Taiyi"),
    "上阵觉醒苏烈后不再购买苏烈，每回合记得丢小菟": (
        "Once an Awakened Su Lie is on the board, stop buying Su Lie, and remember to throw Little Rabbit every Round",
        "Setelah Su Lie yang Awaken di papan, berhenti membeli Su Lie, dan ingat lempar Little Rabbit setiap Ronde"),
    "不搜牌，有多余能量就升级，升到4级开始搜马超和瑶。": (
        "Don't search for cards; spend spare Energy on levelling up, and at Lv. 4 start searching for Ma Chao and"
        " Yaria.",
        "Jangan cari kartu; pakai sisa Energy untuk naik level, dan di Lv. 4 mulai cari Ma Chao dan Yaria."),
    "不断打出效果牌加等级和法强，同时多打合成获得锦囊牌，利用镜囊给的效果卡去提升阵容的质量。": (
        "Keep playing Effect Cards for Levels and Magic Attack, Combine often for Kits, and use the Effect"
        " Cards they give to raise the Lineup's quality.",
        "Terus mainkan Kartu Efek untuk Level dan Magic Attack, sering Combine untuk Kit, dan gunakan Kartu"
        " Efek darinya untuk menaikkan kualitas Lineup."),
    "不花能量刷新商店，如果自动刷出需要的英雄牌可以购买，有铠推荐买，前期战力很强。": (
        "Don't spend Energy to Refresh the Shop; buy needed Hero Cards if the automatic Refresh shows them. Kaizer is"
        " worth buying: he is very strong early.",
        "Jangan pakai Energy untuk Refresh Shop; beli Kartu Hero yang dibutuhkan jika muncul dari Refresh otomatis."
        " Kaizer layak dibeli: sangat kuat di awal."),
    "两个日落海整备可以作为打出位，卖一个每回合换一个日落海整备上去": (
        "Two Sunset Prepare Heroes can serve as play slots: sell one each Round and swap in another Sunset"
        " Prepare Hero",
        "Dua Hero Prepare Sunset bisa jadi slot main: jual satu setiap Ronde dan ganti dengan Hero Prepare"
        " Sunset lain"),
    "中期上4找韩信，然后找齐阵容上5，优先觉醒韩信": (
        "Mid game, go to Lv. 4 to find Han Xin, then complete the Lineup and go to Lv. 5; Awaken Han Xin first",
        "Di pertengahan, naik ke Lv. 4 untuk mencari Han Xin, lalu lengkapi Lineup dan naik ke Lv. 5;"
        " utamakan Awaken Han Xin"),
    "中期没啥操作，就是找牌觉醒，然后冻住，到后期全五阶了之后，可以直接挂机了。": (
        "Little to do mid game: find cards, Awaken them and freeze them; once everything is Tier 5 late, it"
        " plays itself.",
        "Tidak banyak aksi di pertengahan: cari kartu, Awaken, lalu bekukan; setelah semua Tier 5 di akhir,"
        " cukup autopilot."),
    "之后位置不够，把阿珂传承了，有合成打合成，锦囊里拿唤醒，集体唤醒，临阵磨枪，全军动员这些卡，同时传承遗志留手上，最后等级汇总，抖音搜小阿豪有保姆级视频": (
        "When you run out of slots, pass Arke on with Inheritance. Combine whenever you can and take Awaken,"
        " Mass Awakening, Sharpening Weapons Before Battle and Full Army Mobilization from Kits, while"
        " keeping Inheritance and Last Will in hand to pool the Levels at the end. Search Xiao A'hao on"
        " Douyin for step-by-step videos",
        "Saat slot habis, wariskan Arke dengan Inheritance. Combine kapan pun bisa dan ambil Awaken, Mass"
        " Awakening, Sharpening Weapons Before Battle, dan Full Army Mobilization dari Kit, sambil menyimpan"
        " Inheritance dan Last Will di tangan untuk mengumpulkan Level di akhir. Cari Xiao A'hao di Douyin"
        " untuk video langkah demi langkah"),
    "五回合升级到三级，找齐场上牌，优先觉醒蔡文姬曹操，公孙离吸刘禅等级，曹操觉醒以后卖掉刘禅换貂蝉": (
        "In Round 5 reach Lv. 3 and complete the board; Awaken Cai Yan and Cao Cao first, let Arli absorb"
        " Liu Shan's Levels, and once Cao Cao Awakens, sell Liu Shan for Diaochan",
        "Di Ronde 5 naik ke Lv. 3 dan lengkapi papan; utamakan Awaken Cai Yan dan Cao Cao, biarkan Arli"
        " menyerap Level Liu Shan, dan setelah Cao Cao Awaken, jual Liu Shan untuk Diaochan"),
    "五级后开大直接如梦似幻直接牌来全齐，如果没有核心东皇敖隐可以小刷，血量高直接上六开第二个如梦似幻，攒钱开梦幻引擎，通过梦幻引擎实现全员觉醒。\n合成锦囊准备一张遗志或者传承，决赛圈传承掉遗志掉虞姬换太乙挂给东皇或者敖隐。": (
        "After Lv. 5, use the Ultimate: Dreamlike brings the whole set of cards at once. If the core"
        " Donghuang or Ao'yin is missing, roll a little; with high HP go straight to Lv. 6 for the second"
        " Dreamlike, then save up for Dream Engine, which Awakens the whole team.\nKeep a Last Will or"
        " Inheritance from Combine Kits; in the finals, pass Consort Yu on with it and bring in Taiyi,"
        " linked to Donghuang or Ao'yin.",
        "Setelah Lv. 5, gunakan Ultimate: Dreamlike memberi semua kartu sekaligus. Jika inti Donghuang atau"
        " Ao'yin belum ada, sedikit refresh; jika HP tinggi langsung naik ke Lv. 6 untuk Dreamlike kedua,"
        " lalu menabung untuk Dream Engine, yang membuat semua Hero Awaken.\nSimpan satu Last Will atau"
        " Inheritance dari Kit Combine; di final, wariskan Consort Yu dengannya dan masukkan Taiyi yang"
        " dihubungkan ke Donghuang atau Ao'yin."),
    "优先觉醒干将，再拿牛魔、孙膑、曜\n伞绑定干将，靠合成刷遗志": (
        "Awaken Gan first, then take Niu Mo, Sun Bin and Yao\nBind the umbrella to Gan and Combine to roll"
        " for Last Will",
        "Utamakan Awaken Gan, lalu ambil Niu Mo, Sun Bin, dan Yao\nIkat payung ke Gan dan Combine untuk"
        " mencari Last Will"),
    "公式化打法，双觉醒，狂铁提供战力，奕星升级必备，选秀拿体系牌或者日落海牌！": (
        "A formula build with two Awakenings: Biron supplies power and Yixing is a must for leveling; in the"
        " draft, take core cards or Sunset cards!",
        "Build rumus dengan dua Awaken: Biron memberi kekuatan dan Yixing wajib untuk naik level; saat"
        " draft, ambil kartu inti atau kartu Sunset!"),
    "分三种情况，没有能量改造的情况下，后期把所有牌卖了，只留雅典娜和艾琳，上太乙辅助艾琳即可。如果拿到能量改造，就把亚瑟卖了，上场露娜（不要卖掉），不断刷等级即可。天赋优先拿能量汲取，如果有阿克米亚核心这装备，可以上司空震": (
        "There are three cases. Without Energy Modification, sell every card late except Athena and Erin,"
        " and bring in Taiyi to support Erin. With Energy Modification, sell Arthur, put Luna on the board"
        " (don't sell her) and keep rolling for Levels. For Talents, take Energy Siphon first, and with the"
        " Arcomia Core Equipment you can add Sikong Zhen",
        "Ada tiga kondisi. Tanpa Modifikasi Energy, di akhir jual semua kartu kecuali Athena dan Erin, lalu"
        " masukkan Taiyi untuk mendukung Erin. Dengan Modifikasi Energy, jual Arthur, taruh Luna di papan"
        " (jangan dijual) dan terus refresh untuk Level. Untuk Talent, utamakan Energy Siphon, dan jika ada"
        " Equipment Arcomia Core, bisa menambahkan Sikong Zhen"),
    "刷牌升级": ("Roll cards and level up", "Refresh kartu dan naik level"),
    "刷遗志，刷出遗志再升级棋手": (
        "Roll for Last Will, and level up the Chessplayer only once you have it",
        "Cari Last Will, dan naikkan level Chessplayer hanya setelah mendapatkannya"),
    "前三波买个弈星直接上等级3": (
        "In the first three Rounds, buy a Yixing and go straight to Lv. 3",
        "Di tiga Ronde pertama, beli Yixing dan langsung naik ke Lv. 3"),
    "前期可以单挂一张弈星，不刷商店升到3级": (
        "Early on you can field just one Yixing and level up to 3 without Refreshing the Shop",
        "Di awal kamu bisa menurunkan satu Yixing saja dan naik ke Lv. 3 tanpa Refresh Shop"),
    "前期可以单挂奕星速升四级": (
        "Early, you can field Yixing alone and rush to Lv. 4",
        "Di awal, kamu bisa memasang Yixing sendiri dan cepat naik ke Lv. 4"),
    "前期可以拿狂铁过渡；拿弈星之后升级": (
        "Early, you can take Biron as a stopgap; level up after getting Yixing",
        "Di awal, kamu bisa ambil Biron sebagai pengisi sementara; naik level setelah dapat Yixing"),
    "前期可以选择1回合一张孙尚香+一张弈星开局，如果其他棋手非前期连胜棋手，也可以觉醒孙尚香开局。3回合拍卖优先拿曹操/蔡文姬，7回合拍卖手牌有甄姬，优先拿露娜。如没有甄姬小乔，优先拿甄姬小乔。1-7回合主要是在升级的过程中，尽可能的保存血量。": (
        "Early, you can open with a Lady Sun and a Yixing in Round 1; if no other Chessplayer is an"
        " early-streak one, you can also open with an Awakened Lady Sun. At the Round 3 Auction take Cao Cao"
        " or Cai Yan first; at the Round 7 Auction, if Lady Zhen is in hand, take Luna first, and if you"
        " lack Lady Zhen and Xiao Qiao, take them first. Rounds 1-7 are mostly about leveling up while"
        " saving as much HP as you can.",
        "Di awal, kamu bisa membuka dengan Lady Sun dan Yixing di Ronde 1; jika tidak ada Chessplayer lain"
        " yang kuat win streak di awal, bisa juga membuka dengan Lady Sun yang Awaken. Di Lelang Ronde 3"
        " utamakan Cao Cao atau Cai Yan; di Lelang Ronde 7, jika Lady Zhen ada di tangan, utamakan Luna, dan"
        " jika belum punya Lady Zhen dan Xiao Qiao, utamakan mereka. Ronde 1-7 fokus naik level sambil"
        " menjaga HP sebanyak mungkin."),
    "前期给的多就拿个觉醒干将过渡，不给就算了别用能量d。然后速三开始d牌": (
        "If the early game gives plenty, take an Awakened Gan as a stopgap; if not, skip it and don't spend"
        " Energy on rolls. Then rush to Lv. 3 and start rolling",
        "Jika awal permainan memberi banyak, ambil Gan yang Awaken sebagai pengisi sementara; jika tidak,"
        " lewati dan jangan pakai Energy untuk refresh. Lalu cepat naik ke Lv. 3 dan mulai refresh"),
    "前期觉醒香香上牛魔和弈星过度，四回合升级到2级": (
        "Early, Awaken Xiangxiang and use Niu Mo and Yixing as stopgaps; level up to Lv. 2 in Round 4",
        "Di awal, Awaken Xiangxiang dan pakai Niu Mo serta Yixing sebagai pengisi sementara; naik ke Lv. 2 di Ronde 4"),
    "前期配合小鹿轻松连胜加等级": (
        "Early, the deer makes win streaks and Levels easy",
        "Di awal, rusa membuat win streak dan Level jadi mudah"),
    "升到3级开始刷阵容里的卡牌，最好等刷到猪八戒再开始合成。手上留一张猪八戒，马可技能牌提供的冰曜宝石镜优先复制猪八戒让他觉醒。": (
        "At Lv. 3 start rolling for the Lineup's cards; ideally wait until you find Zhu Bajie before Combining. Keep"
        " one Zhu Bajie in hand and use the Ice Crystal Gemstone Mirror from Marco's Skill card to copy Zhu Bajie"
        " first so he Awakens.",
        "Di Lv. 3 mulai Refresh untuk kartu Lineup; sebaiknya tunggu sampai dapat Zhu Bajie sebelum Combine. Simpan"
        " satu Zhu Bajie di tangan dan gunakan Cermin Permata Kristal Es dari kartu Skill Marco untuk menyalin Zhu"
        " Bajie lebih dulu agar dia Awaken."),
    "升到四级后，找齐阵容体系牌后可以升五级搜牌。": (
        "After reaching Lv. 4 and gathering the Lineup's core cards, go to Lv. 5 to search for more.",
        "Setelah Lv. 4 dan kartu inti Lineup lengkap, naik ke Lv. 5 untuk mencari kartu."),
    "单挂弈星一直留到升5级，如果对手或自己是嬴律可以等第一轮竞拍结束后根据至高决策来进行升级。第一轮竞拍优先：程咬金>梦琪>铠>明世隐。": (
        "Field Yixing alone and keep him until Lv. 5; if an opponent or you are Ying Lu, you can wait until"
        " after the first Auction and level up by Supreme Decision. 1st Auction priority: Cheng Yaojin >"
        " Menki > Kaizer > Ming.",
        "Pasang Yixing sendiri dan pertahankan sampai Lv. 5; jika lawan atau kamu memakai Ying Lu, tunggu"
        " sampai Lelang pertama selesai dan naik level sesuai Supreme Decision. Prioritas Lelang ke-1: Cheng"
        " Yaojin > Menki > Kaizer > Ming."),
    "单指把牌找的差不多看血量健康就可以尝试上六了，没必要硬找到全觉醒": (
        "Once you've found most of the cards and HP is healthy, try going to Lv. 6; no need to force a full Awakening",
        "Setelah sebagian besar kartu ditemukan dan HP aman, coba naik ke Lv. 6; tidak perlu memaksakan semua Awaken"),
    "单放个奕星，不用觉醒。空位的话，靠偷对面的卡牌来补充战力": (
        "Field a lone Yixing; no need to Awaken him. Fill empty slots by stealing the opponents' cards",
        "Pasang satu Yixing saja; tidak perlu Awaken. Isi slot kosong dengan mencuri kartu lawan"),
    "只打出天赋给的那一张牌，升到4本，开朋友多多": (
        "Play only the one card the Talent gives, reach Lv. 4, and open Many Friends",
        "Mainkan hanya satu kartu dari Talent, naik ke Lv. 4, dan buka Banyak Teman"),
    "合成后获得的效果锦囊优先拿传承、遗志、换帅，后期把孙尚香等级换给吕布或周瑜。其它英雄可以用遗志、传承把等级都换给C位。": (
        "From the Effect Guides you get after Combining, take Inheritance, Last Will and Change of Commander first,"
        " and later swap Lady Sun's Levels onto Lu Bu or Zhou Yu. Other Heroes can pass all their Levels to the Carry"
        " with Last Will and Inheritance.",
        "Dari Panduan Efek yang didapat setelah Combine, utamakan Inheritance, Last Will, dan Pergantian Komandan,"
        " lalu di akhir pindahkan Level Lady Sun ke Lu Bu atau Zhou Yu. Hero lain bisa memindahkan semua Level-nya ke"
        " Carry dengan Last Will dan Inheritance."),
    "同上": ("Same as above", "Sama seperti di atas"),
    "后期传承遗志阿珂、小乔、甄姬、曹操的等级给海月，然后超级换帅吕布登场999级，觉醒老虎登场，整备后的老虎可以直接999级。--抖音搜肝帝\r": (
        "Late, use Inheritance and Last Will to pass the Levels of Arke, Xiao Qiao, Lady Zhen and Cao Cao to"
        " Haya, then use Super Commander Swap to Deploy Lu Bu at Lv. 999, and Deploy an Awakened Pei: after"
        " Prepare, he can reach Lv. 999 directly. Search Gandi on Douyin",
        "Di akhir, gunakan Inheritance dan Last Will untuk memindahkan Level Arke, Xiao Qiao, Lady Zhen, dan"
        " Cao Cao ke Haya, lalu gunakan Super Commander Swap untuk Deploy Lu Bu di Lv. 999, dan Deploy Pei"
        " yang Awaken: setelah Prepare, dia bisa langsung mencapai Lv. 999. Cari Gandi di Douyin"),
    "后期可以找太乙复活猪八戒，如果血量健康能量充足，升到6级，马可的专属天赋可以让英雄伤害提升。": (
        "Late game, find Taiyi to Revive Zhu Bajie. If your HP is healthy and Energy plentiful, level up to 6: Marco's"
        " Exclusive Talent raises Hero damage.",
        "Di akhir, cari Taiyi untuk Revive Zhu Bajie. Jika HP aman dan Energy cukup, naik ke Lv. 6: Exclusive Talent"
        " Marco meningkatkan damage Hero."),
    "后期墨子卖了换鲁班大师": ("Late, sell Mozi for Master Luban", "Di akhir, jual Mozi dan ganti dengan Master Luban"),
    "后期把狂铁传承掉上海月": (
        "Late, pass Biron on with Inheritance and bring in Haya",
        "Di akhir, wariskan Biron dengan Inheritance dan masukkan Haya"),
    "后期有姜子牙和司空震便可直接启动刷牌，疯狂提升司空震等级，后面的妲己秘技根本用不完。全部觉醒后即可成型！": (
        "Late, once you have Ziya and Sikong Zhen, start rolling cards to pump Sikong Zhen's Level; Daji's"
        " Secret Skills will be more than you can use. Once all are Awakened, the Lineup is complete!",
        "Di akhir, setelah ada Ziya dan Sikong Zhen, mulai refresh kartu untuk menaikkan Level Sikong Zhen;"
        " Secret Skill Daji tidak akan habis terpakai. Setelah semua Awaken, Lineup lengkap!"),
    "后期轻松999": ("Lv. 999 comes easily late", "Lv. 999 mudah dicapai di akhir"),
    "四级搜核心李信，其他牺牲挂件不要多拿": (
        "At Lv. 4 search for the core, Li Xin; don't take too many Sacrifice extras",
        "Di Lv. 4 cari inti, Li Xin; jangan ambil terlalu banyak Hero Sacrifice pelengkap"),
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
    "在后期，可以在锦囊里保留一张传承，或者遗志。因为在甄姬的登场被触发时，会出现大量不能和场上英雄合成的英雄牌。直接卖掉很亏，我们可以通过传承/遗志【阿珂】来空出一个人口。拿到的露娜不要急着打出，用灵感爆发一切二之后再来使用。": (
        "Late, keep an Inheritance or a Last Will in your Kits. When Lady Zhen's Deploy triggers, it brings"
        " many Hero cards that can't Combine with the board, and selling them outright is a waste;"
        " Inheritance or Last Will on 【Arke】 frees a Population slot instead. Don't rush to play the Luna"
        " you get: split it with Inspiration Burst first, then use it.",
        "Di akhir, simpan satu Inheritance atau Last Will di Kit. Saat Deploy Lady Zhen aktif, muncul banyak"
        " kartu Hero yang tidak bisa di-Combine dengan papan, dan menjualnya langsung itu rugi; Inheritance"
        " atau Last Will pada 【Arke】 justru membebaskan satu slot Populasi. Jangan buru-buru memainkan Luna"
        " yang didapat: bagi dulu dengan Inspiration Burst, baru gunakan."),
    "在等级3搜蒙恬，芈月，西施，苍，觉醒芈月上等级4，如果芈月没觉醒，就8回合上4，在等级4把蒙恬等级拉到100级后再上等级5。": (
        "At Lv. 3 search for Meng Tian, Mi Yue, Shi and Chano, and Awaken Mi Yue to reach Lv. 4; if Mi Yue"
        " hasn't Awakened, go to Lv. 4 in Round 8. At Lv. 4, get Meng Tian to Lv. 100 before going to Lv. 5.",
        "Di Lv. 3 cari Meng Tian, Mi Yue, Shi, dan Chano, lalu Awaken Mi Yue untuk naik ke Lv. 4; jika Mi"
        " Yue belum Awaken, naik ke Lv. 4 di Ronde 8. Di Lv. 4, naikkan Meng Tian ke Lv. 100 sebelum naik ke Lv. 5."),
    "基本上大成了，吃鸡概率，80%了。前三是稳了。最后决战的时候，把明世隐卖掉，上钟馗（左边放花木兰，右边放程咬金），然后再把露娜卖掉，把太乙给花木兰复活。": (
        "The Lineup is basically complete: about an 80% chance to win, and top 3 is safe. For the final"
        " battle, sell Ming and bring in Kui (Mulan on his left, Cheng Yaojin on his right), then sell Luna"
        " and give Taiyi to Mulan to Revive her.",
        "Lineup pada dasarnya sudah jadi: peluang juara sekitar 80%, dan 3 besar aman. Di pertempuran final,"
        " jual Ming dan masukkan Kui (Mulan di kirinya, Cheng Yaojin di kanannya), lalu jual Luna dan"
        " berikan Taiyi ke Mulan untuk Revive."),
    "如果觉得你运气不好，这一套可以无缝转接大河那一套，就是大河龙蛇，就是选备选里的虞姬少司缘鬼谷子大司命这几个有图腾的，然后五星刷敖隐跟东皇，大号龙蛇前期没输出的话，留下干将，能刷到遗志什么的，或者把它冻成输出": (
        "If your luck is bad, this build switches seamlessly into Riverlands Dragon-Snake: pick the Totem"
        " Heroes from the alternates (Consort Yu, Dyadia, Guiguzi, Augran), then roll for Ao'yin and"
        " Donghuang at 5 stars. If the Dragon-Snake lacks early damage, keep Gan, roll for Last Will and the"
        " like, or freeze him as your damage dealer",
        "Jika kurang beruntung, build ini bisa langsung beralih ke Dragon-Snake Riverlands: pilih Hero Totem"
        " dari cadangan (Consort Yu, Dyadia, Guiguzi, Augran), lalu refresh untuk Ao'yin dan Donghuang di"
        " bintang 5. Jika Dragon-Snake kurang damage di awal, simpan Gan, cari Last Will dan sejenisnya,"
        " atau bekukan dia sebagai damage dealer"),
    "存钱速升4本找诸葛亮，商店刷新明世隐和刘禅可以买，不花能量刷新。明世隐先挂诸葛亮且有多少买多少。二拍优先级:杨玉环>诸葛亮": (
        "Save up and rush to Lv. 4 to find Kongming; buy Ming and Liu Shan when shop Refreshes show them,"
        " but don't spend Energy on Refreshes. Link Ming to Kongming first, and buy as many as you can. 2nd"
        " Auction priority: Yuhuan > Kongming",
        "Menabung dan cepat naik ke Lv. 4 untuk mencari Kongming; beli Ming dan Liu Shan jika muncul di"
        " Refresh toko, tapi jangan pakai Energy untuk Refresh. Hubungkan Ming ke Kongming dulu, dan beli"
        " sebanyak mungkin. Prioritas Lelang ke-2: Yuhuan > Kongming"),
    "孙膑1-2回合各一张弈星(2-3回合回溯觉醒弈星)。白歌来牌顺觉醒弈星，不顺不觉醒干拉刀4本。镜单挂弈星，每\r回合一张镜像拿手里，三回合上2本。——抖音搜肝帝": (
        "Sun Bin: a Yixing in each of Rounds 1-2 (Undo in Rounds 2-3 to Awaken Yixing). Bai Ge: Awaken"
        " Yixing if the cards flow; if not, skip it and push to Lv. 4. Jing: field Yixing alone, keep a"
        " Mirror in hand every Round, and reach Lv. 2 in Round 3. Search Gandi on Douyin",
        "Sun Bin: satu Yixing di masing-masing Ronde 1-2 (Urungkan di Ronde 2-3 untuk meng-Awaken Yixing)."
        " Bai Ge: Awaken Yixing jika kartu lancar; jika tidak, lewati dan paksa naik ke Lv. 4. Jing: pasang"
        " Yixing sendiri, simpan satu Mirror di tangan setiap Ronde, dan naik ke Lv. 2 di Ronde 3. Cari"
        " Gandi di Douyin"),
    "孙膑找到2个甄姬就可以回环。白歌找到一张甄姬小乔血量允许的情况下直接拉6本奇才甄姬启动。镜在第七回合曹操+镜像，小乔+镜像，甄姬+镜像，阿珂+镜像，然后万镜复制场上四张，然后曹操小乔直接打出，甄姬、阿珂继续跟镜像。字符有限——抖音搜肝帝": (
        "Sun Bin: loop once you have 2 Lady Zhen. Bai Ge: once you have a Lady Zhen and a Xiao Qiao, and HP"
        " allows, push to Lv. 6 and start with Prodigy on Lady Zhen. Jing: in Round 7, Cao Cao + Mirror,"
        " Xiao Qiao + Mirror, Lady Zhen + Mirror and Arke + Mirror, then Myriad Mirrors copies those four on"
        " the board; play Cao Cao and Xiao Qiao at once, and keep Lady Zhen and Arke following the Mirrors."
        " Space is short: search Gandi on Douyin",
        "Sun Bin: lakukan loop setelah punya 2 Lady Zhen. Bai Ge: setelah punya Lady Zhen dan Xiao Qiao, dan"
        " HP memungkinkan, paksa naik ke Lv. 6 dan mulai dengan Prodigy pada Lady Zhen. Jing: di Ronde 7,"
        " Cao Cao + Mirror, Xiao Qiao + Mirror, Lady Zhen + Mirror, dan Arke + Mirror, lalu Myriad Mirrors"
        " menyalin keempatnya di papan; langsung mainkan Cao Cao dan Xiao Qiao, dan biarkan Lady Zhen serta"
        " Arke terus mengikuti Mirror. Ruang terbatas: cari Gandi di Douyin"),
    "尽快上6让蒙恬可以10蓝，决赛可以换上觉醒钟馗减对面C位等级。": (
        "Reach Lv. 6 as soon as possible so Meng Tian can have 10 Mana; in the finals, swap in an Awakened"
        " Kui to lower the enemy carry's Level.",
        "Capai Lv. 6 secepatnya agar Meng Tian bisa punya 10 Mana; di final, masukkan Kui yang Awaken untuk"
        " menurunkan Level carry lawan."),
    "尽快把棋手升到6级，搜司空震和其他需要的卡牌。": (
        "Raise your Chessplayer to Lv. 6 as fast as possible and search for Sikong Zhen and the other cards you need.",
        "Naikkan Chessplayer ke Lv. 6 secepat mungkin dan cari Sikong Zhen serta kartu lain yang dibutuhkan."),
    "开场四小队稳血为主，干将前期能力不错，可以上狂铁，后期通过跳级夺取日落海核心等级。": (
        "Open with the squad of four to protect your HP; Gan is solid early and Biron can join. Late, Steal"
        " the Sunset core's Levels by skipping Levels.",
        "Buka dengan regu empat untuk menjaga HP; Gan kuat di awal dan Biron bisa masuk. Di akhir, Steal"
        " Level inti Sunset dengan lompat level."),
    "开完朋友多多之后，把阵容找齐，就可以上6本": (
        "After Many Friends, complete the Lineup, then go to Lv. 6",
        "Setelah Banyak Teman, lengkapi Lineup, lalu naik ke Lv. 6"),
    "开局买一张狂铁，狂铁每回合自动成长适合前期过渡，回合2升2级。": (
        "Buy a Biron at the start: he grows automatically each Round, a good early stopgap. Level up to 2 in Round 2.",
        "Beli satu Biron di awal: dia tumbuh otomatis setiap Ronde, cocok sebagai pengisi sementara di awal. Naik ke"
        " Lv. 2 di Ronde 2."),
    "开局买一张狂铁，狂铁每回合自动成长适合前期过渡，没有狂铁可以用牛魔或弈星过渡。回合2升2级。": (
        "Buy a Biron at the start: he grows automatically each Round, a good early stopgap. Without Biron, use Niu Mo"
        " or Yixing as stopgaps. Level up to 2 in Round 2.",
        "Beli satu Biron di awal: dia tumbuh otomatis setiap Ronde, cocok sebagai pengisi sementara di awal. Tanpa"
        " Biron, pakai Niu Mo atau Yixing sebagai pengisi sementara. Naik ke Lv. 2 di Ronde 2."),
    "开局先打战略决策，选择低压运营和基层提拔，等到第一次拍卖回来把至高决策打出还会给战略决策，把开局没拿到的另一个补上，低压运营是根据血量来提升等级的所以前期优先拿战力高的赢": (
        "Play Strategic Decision first and pick Low-Pressure Strategy and Base Promotion; after the first"
        " Auction, playing Supreme Decision gives another Strategic Decision, so add the one you didn't get"
        " at the start. Low-Pressure Strategy raises Levels based on HP, so early on prefer strong Heroes and win",
        "Mainkan Strategic Decision dulu dan pilih Strategi Tekanan Rendah dan Promosi Dasar; setelah Lelang"
        " pertama, memainkan Supreme Decision memberi Strategic Decision lagi, jadi tambahkan yang belum"
        " didapat di awal. Strategi Tekanan Rendah menaikkan Level berdasarkan HP, jadi di awal utamakan"
        " Hero kuat dan menang"),
    "开局拿一张李元芳过渡，回合2升2级。": (
        "Take a Fang at the start as a stopgap, and level up to 2 in Round 2.",
        "Ambil satu Fang di awal sebagai pengisi sementara, dan naik ke Lv. 2 di Ronde 2."),
    "开局挂一张弈星，卖血直接升级。\n第一张卦象选节，加钱，第四回合直接拉四级。\n拍卖会优先抢芈月，核心功能给嬴政加等级的。\n其余牌可抢西施/白起/老夫子。": (
        "Open with a single Yixing and give up HP to level up straight away.\nFor the first Hexagram pick"
        " Moderation for money, and go to Lv. 4 in Round 4.\nAt the Auction grab Mi Yue first: her key role"
        " is giving Ying Zheng Levels.\nFor the rest, grab Shi, Bai Qi or Fuzi.",
        "Buka dengan satu Yixing dan korbankan HP untuk langsung naik level.\nUntuk Hexagram pertama pilih"
        " Moderation untuk uang, dan naik ke Lv. 4 di Ronde 4.\nDi Lelang utamakan Mi Yue: peran utamanya"
        " memberi Level ke Ying Zheng.\nSisanya, ambil Shi, Bai Qi, atau Fuzi."),
    "弈星、牛魔开局，前期偷到什么用什么。速上3本，利用免费刷新、老夫子、梦奇找芈月。一拍优先级:芈月>西施>老夫子>梦奇>白起": (
        "Open with Yixing and Niu Mo, and early on use whatever you steal. Rush to Lv. 3 and find Mi Yue"
        " with free Refreshes, Fuzi and Menki. 1st Auction priority: Mi Yue > Shi > Fuzi > Menki > Bai Qi",
        "Buka dengan Yixing dan Niu Mo, dan di awal pakai apa pun yang dicuri. Cepat naik ke Lv. 3 dan cari"
        " Mi Yue dengan Refresh gratis, Fuzi, dan Menki. Prioritas Lelang ke-1: Mi Yue > Shi > Fuzi > Menki > Bai Qi"),
    "弈星、狂铁开局": ("Open with Yixing and Biron", "Buka dengan Yixing dan Biron"),
    "当我们在三本觉醒一张公孙离加任意一张大河牌觉醒 即可选择升本 ，我们直接升到五本找我们剩下的一张体系牌 ，如果你已经在三本拿到了那我们在五本不做停留直接上六 ！": (
        "Once Arli and any one Riverlands card have Awakened at Lv. 3, level up: go straight to Lv. 5 to"
        " find our last core card, and if you already got it at Lv. 3, don't stop at 5, go straight to 6!",
        "Setelah Arli dan satu kartu Riverlands mana pun Awaken di Lv. 3, naik level: langsung ke Lv. 5"
        " untuk mencari kartu inti terakhir, dan jika sudah didapat di Lv. 3, jangan berhenti di 5, langsung ke 6!"),
    "找两个辅助": ("Find two Supports", "Cari dua Support"),
    "找全阵容升四级找扁鹊": (
        "Complete the Lineup, then go to Lv. 4 for Dr Bian",
        "Lengkapi Lineup, lalu naik ke Lv. 4 untuk mencari Dr Bian"),
    "找到马超和瑶之后继续升级到6级，补一张吕布给马超加吸血。血量健康的话棋手秘技牌等凑齐4个英雄再使用，血量低可看情况提前用。": (
        "After finding Ma Chao and Yaria, keep levelling up to 6 and add a Lu Bu to give Ma Chao Lifesteal. If your HP"
        " is healthy, wait until you have all 4 Heroes before using the Chessplayer's Secret Skill Card; if HP is low,"
        " use it earlier as needed.",
        "Setelah mendapat Ma Chao dan Yaria, terus naik level sampai Lv. 6 dan tambahkan Lu Bu untuk memberi"
        " Lifesteal ke Ma Chao. Jika HP aman, tunggu sampai keempat Hero lengkap sebelum menggunakan Kartu Secret"
        " Skill Chessplayer; jika HP rendah, gunakan lebih awal sesuai situasi."),
    "拿体系牌，4人成型，优先觉醒八戒，血量低，优先打出阿轲。": (
        "Take the core cards: the Lineup works with 4. Awaken Zhu Bajie first, and when HP is low, play Arke first.",
        "Ambil kartu inti: Lineup terbentuk dengan 4 Hero. Utamakan Awaken Zhu Bajie, dan saat HP rendah,"
        " utamakan memainkan Arke."),
    "有四张强力牌后升2级，拿到基层提拔后可以把开局四张牌选择觉醒，优先觉醒牛魔和干将，在2级找公孙离和阵容牌，用公孙离把开局的四张牌吸干就可以卖掉了": (
        "With four strong cards, go to Lv. 2; after Base Promotion, choose to Awaken your four opening"
        " cards, Niu Mo and Gan first. At Lv. 2, find Arli and the Lineup cards; once Arli has drained the"
        " four opening cards' Levels, sell them",
        "Setelah punya empat kartu kuat, naik ke Lv. 2; setelah Promosi Dasar, pilih untuk meng-Awaken empat"
        " kartu awal, utamakan Niu Mo dan Gan. Di Lv. 2, cari Arli dan kartu Lineup; setelah Arli menyerap"
        " habis Level empat kartu awal, jual kartunya"),
    "有弈星可以拿一张，每回合只花费1能量使用棋手技能，开出什么英雄上什么英雄，其余能量都留着升级。优先选经济类的天赋或加血的天赋。": (
        "Take a Yixing if you see one. Spend only 1 Energy per Round on the Chessplayer Skill and field whatever Hero"
        " it gives; save the rest of your Energy for levelling. Prefer economy Talents or healing Talents.",
        "Ambil satu Yixing jika ada. Pakai hanya 1 Energy per Ronde untuk Skill Chessplayer dan turunkan Hero apa pun"
        " yang didapat; simpan sisa Energy untuk naik level. Utamakan Talent ekonomi atau Talent penambah HP."),
    "李元芳卖掉换太乙": ("Sell Fang for Taiyi", "Jual Fang dan ganti dengan Taiyi"),
    "棋手一路直接升到六级，不使用能量刷新，升至六级后先丢金色小菟，再丢小菟": (
        "Take the Chessplayer straight to Lv. 6 without spending Energy on Refreshes; at Lv. 6 throw the"
        " golden Little Rabbit first, then the normal Little Rabbit",
        "Naikkan Chessplayer langsung ke Lv. 6 tanpa memakai Energy untuk Refresh; di Lv. 6 lempar Little"
        " Rabbit emas dulu, lalu Little Rabbit biasa"),
    "棋手二级时，免费刷新遇到米莱迪、亚联可以拿；4回合升3级开始找牌；觉醒优先朵莉亚和米莱迪": (
        "At Chessplayer Lv. 2, take Milady or Allain if a free Refresh shows them; go to Lv. 3 in Round 4"
        " and start searching; Awaken Dolia and Milady first",
        "Di Chessplayer Lv. 2, ambil Milady atau Allain jika muncul dari Refresh gratis; naik ke Lv. 3 di"
        " Ronde 4 dan mulai mencari kartu; utamakan Awaken Dolia dan Milady"),
    "棋手快速升5级后，商店里有体系牌要买，给到免费的铠和盾山可以作为备用前排。优先觉醒婉儿>李白>花木兰，商店有露娜先购买不用。第二轮竞拍优先：婉儿>花木兰>露娜>李白>武则天。": (
        "After rushing the Chessplayer to Lv. 5, buy the core cards in the shop; the free Kaizer and Dunshan"
        " can serve as a spare front row. Awaken Shangguan > Li Bai > Mulan first, and if the shop has Luna,"
        " buy her but don't use her yet. 2nd Auction priority: Shangguan > Mulan > Luna > Li Bai > Wu Zetian.",
        "Setelah Chessplayer cepat naik ke Lv. 5, beli kartu inti di toko; Kaizer dan Dunshan gratis bisa"
        " jadi barisan depan cadangan. Utamakan Awaken Shangguan > Li Bai > Mulan, dan jika toko punya Luna,"
        " beli tapi jangan dipakai dulu. Prioritas Lelang ke-2: Shangguan > Mulan > Luna > Li Bai > Wu Zetian."),
    "牛魔、干将等一阶强力卡稳定战力，保证前期连胜；牛魔、弈星为前期提供经济优势。\n": (
        "Strong Tier 1 cards such as Niu Mo and Gan keep your power stable and the early streak going; Niu"
        " Mo and Yixing give an early economy edge.\n",
        "Kartu Tier 1 kuat seperti Niu Mo dan Gan menjaga kekuatan tetap stabil dan win streak di awal; Niu"
        " Mo dan Yixing memberi keunggulan ekonomi di awal.\n"),
    "白歌到4或5级之后开启爆牌模式，我们可以在4级使用我们连败积累的免费刷新，搜齐我们的核心牌曹操/甄姬/小乔/孙悟空，就可以尽快上5。在有足够容错的情况下，可以在5级积攒经济上6，在6级使用我们的奇才复制甄姬或露娜，一波成型。": (
        "From Lv. 4 or 5, Bai Ge goes into card-flood mode: at Lv. 4 use the free Refreshes saved from the"
        " losing streak to gather the core cards Cao Cao, Lady Zhen, Xiao Qiao and Wukong, then go to Lv. 5"
        " as soon as you can. With enough margin, save up at Lv. 5 to reach Lv. 6, and at Lv. 6 use Prodigy"
        " to copy Lady Zhen or Luna and complete the Lineup in one go.",
        "Mulai Lv. 4 atau 5, Bai Ge masuk mode banjir kartu: di Lv. 4 gunakan Refresh gratis dari Lose"
        " streak untuk mengumpulkan kartu inti Cao Cao, Lady Zhen, Xiao Qiao, dan Wukong, lalu naik ke Lv. 5"
        " secepatnya. Jika cukup aman, menabung di Lv. 5 untuk naik ke Lv. 6, dan di Lv. 6 gunakan Prodigy"
        " untuk menyalin Lady Zhen atau Luna dan menyelesaikan Lineup sekaligus."),
    "第1回合，上场牛魔和干将，飞行器给干将；\n第2回合，上场弈星；\r\n第3回合，棋手升2级；\r\n第1轮拍卖，优先拿阵容英雄，优先级：鬼谷子＞少司缘＞明世隐。\r": (
        "Round 1: field Niu Mo and Gan, with the Aircraft on Gan;\nRound 2: field Yixing;\nRound 3:"
        " Chessplayer to Lv. 2;\n1st Auction: Lineup Heroes first, priority: Guiguzi > Dyadia > Ming.\n",
        "Ronde 1: pasang Niu Mo dan Gan, Pesawat ke Gan;\nRonde 2: pasang Yixing;\nRonde 3: Chessplayer ke Lv."
        " 2;\nLelang ke-1: utamakan Hero Lineup, prioritas: Guiguzi > Dyadia > Ming.\n"),
    "第4回合，棋手升3级，上阵拍卖的英雄牌，选择棋手秘技；\r\n第5—7回合，棋手升4级；\r\n第2轮拍卖，优先拿阵容英雄，优先级：海月＞太乙真人＞大司命＞东皇太一。\r": (
        "Round 4: Chessplayer to Lv. 3, field the Hero cards from the Auction and choose a Chessplayer"
        " Secret Skill;\nRounds 5-7: Chessplayer to Lv. 4;\n2nd Auction: Lineup Heroes first, priority: Haya >"
        " Taiyi Zhenren > Augran > Donghuang.\n",
        "Ronde 4: Chessplayer ke Lv. 3, pasang kartu Hero dari Lelang dan pilih Secret Skill"
        " Chessplayer;\nRonde 5-7: Chessplayer ke Lv. 4;\nLelang ke-2: utamakan Hero Lineup, prioritas: Haya >"
        " Taiyi Zhenren > Augran > Donghuang.\n"),
    "第8—11回合，棋手升5级，刷新找体系牌，找到海月和三个图腾即可升级棋手；\r（海月来之前用大司命或东皇太一打工）\n第3轮拍卖，破镜之证＞扶摇直上＞能量超新星；\r\n第12回合及以后，升6级拿专属天赋，打合成开锦囊优化主C装备。\r": (
        "Rounds 8-11: Chessplayer to Lv. 5; Refresh for core cards and level up once you have Haya and three"
        " Totems\n(until Haya arrives, Augran or Donghuang fills in)\n3rd Auction: Proof of Breakthrough >"
        " Soaring High > Energy Supernova;\nRound 12 onward: Lv. 6 for the Exclusive Talent, and Combine for"
        " Kits to improve the Main Carry's Equipment.\n",
        "Ronde 8-11: Chessplayer ke Lv. 5; Refresh untuk kartu inti dan naik level setelah ada Haya dan tiga"
        " Totem\n(sebelum Haya datang, Augran atau Donghuang mengisi)\nLelang ke-3: Proof of Breakthrough >"
        " Soaring High > Energy Supernova;\nRonde 12 dan seterusnya: Lv. 6 untuk Exclusive Talent, dan"
        " Combine untuk Kit guna meningkatkan Equipment Main Carry.\n"),
    "第一个回合我们一定要拿到牛魔干将 ，这是我们必胜的法则 ！第二个回合我们补上元芳一星 ，元芳会自动升级 到达时十级给我们香香的武器带来攻击力 ，奕欣则是在我们升旗手等级时会额外获得两点经验 稳赚不赔 ": (
        "In Round 1 we must get Niu Mo and Gan: that's our winning rule! In Round 2 add a 1-star Fang, who"
        " levels up on his own and at Lv. 10 adds Attack to Xiangxiang's weapon, while Yixing gives 2 extra"
        " EXP whenever we level up the Chessplayer: a sure win",
        "Di Ronde 1 kita wajib dapat Niu Mo dan Gan: itu kunci kemenangan! Di Ronde 2 tambahkan Fang bintang"
        " 1, yang naik level sendiri dan di Lv. 10 menambah Attack senjata Xiangxiang, sementara Yixing"
        " memberi 2 EXP tambahan setiap kali Chessplayer naik level: pasti untung"),
    "第一回合买一张奕星，第二回合回溯一张奕星再买一张奕星合成，第三回合直接升级，然后再回溯一张奕星，这个时候奕星会觉醒回手，同时会给个锦囊，锦囊里拿给两张牌的，然后直接使用，然后手上的牌全部留下回合用，包括奕星": (
        "Round 1: buy a Yixing. Round 2: Undo to get a Yixing back, buy another and Combine. Round 3: level"
        " up and Undo another Yixing; he Awakens and returns to hand, and you get a Kit: take the one that"
        " gives two cards and use it right away, then keep every card in hand for the next Round, Yixing included",
        "Ronde 1: beli Yixing. Ronde 2: Urungkan untuk mendapat Yixing kembali, beli satu lagi lalu Combine."
        " Ronde 3: naik level dan Urungkan satu Yixing lagi; dia Awaken dan kembali ke tangan, dan kamu"
        " mendapat Kit: ambil yang memberi dua kartu dan langsung gunakan, lalu simpan semua kartu di tangan"
        " untuk Ronde berikutnya, termasuk Yixing"),
    "第一回合弈星卖血，二回合升二级找守约": (
        "Round 1: Yixing, giving up HP; Round 2: reach Lv. 2 and find Shouyue",
        "Ronde 1: Yixing sambil mengorbankan HP; Ronde 2: naik ke Lv. 2 dan cari Shouyue"),
    "第一回合技能+弈星，第二回合上本后再使用技能。\n一拍优先级：程咬金＞铠＞盾山＞百里守约": (
        "Round 1: Skill + Yixing; Round 2: level up, then use the Skill.\n1st Auction priority: Cheng Yaojin"
        " > Kaizer > Dunshan > Shouyue",
        "Ronde 1: Skill + Yixing; Ronde 2: naik level, lalu gunakan Skill.\nPrioritas Lelang ke-1: Cheng"
        " Yaojin > Kaizer > Dunshan > Shouyue"),
    "第三个回合我们升到二本 ，随后进入拍卖拿下我们的体系牌 张良 瑶妹 云中君 邵思源 鬼谷子 虞姬 公孙离，按此顺序拿牌即可 。然后我们直接升到三本开始搜索体系牌。优先保证鬼谷子公孙离瑶妹在场 ，剩下四张谁先来上谁 。  ": (
        "In Round 3 raise the Chessplayer to Lv. 2, then take our core cards at the Auction in this order:"
        " Liang, Yaria, Cirrus, Dyadia, Guiguzi, Consort Yu, Arli. Then go straight to Lv. 3 and search for"
        " core cards. Keep Guiguzi, Arli and Yaria on the board first; the other four go in as they come.",
        "Di Ronde 3 naikkan Chessplayer ke Lv. 2, lalu ambil kartu inti di Lelang dengan urutan: Liang,"
        " Yaria, Cirrus, Dyadia, Guiguzi, Consort Yu, Arli. Lalu langsung naik ke Lv. 3 dan cari kartu inti."
        " Utamakan Guiguzi, Arli, dan Yaria di papan; empat lainnya masuk sesuai yang datang."),
    "第二次拍卖优先选海诺和雅典娜。回合8-11将棋手升到5级，主要找海诺和雅典娜，海诺在每次阿科米亚核心提升等级时都可提供额外等级。": (
        "In the second Auction, pick Heino and Athena first. Raise your Chessplayer to Lv. 5 in Rounds 8-11 and look"
        " mainly for Heino and Athena; Heino gives extra Levels every time the Arcomia Core levels up.",
        "Di Lelang kedua, utamakan Heino dan Athena. Naikkan Chessplayer ke Lv. 5 di Ronde 8-11 dan cari terutama"
        " Heino dan Athena; Heino memberi Level tambahan setiap kali Arcomia Core naik Level."),
    "等等级吸起来就开始升级，升到6级选择绝对压制给公孙离加30％免伤，再加上霸者的免伤，把场上英雄觉醒给公孙离加攻速，最后造就70％免伤和4.0攻速打半神如果选了重装上阵和全副武装就有85％的免伤谁也打不动打谁都很痛": (
        "Once the Levels are absorbed, start leveling up. At Lv. 6 pick Absolute Suppression for 30% damage"
        " reduction on Arli; with Overlord's damage reduction and the board's Awakened Heroes adding to her"
        " Attack Speed, she ends up with 70% damage reduction and 4.0 Attack Speed against demigods. With"
        " Heavy Gear and Fully Armed it reaches 85%: nobody can hurt her, and she hurts everyone",
        "Setelah Level terserap, mulai naik level. Di Lv. 6 pilih Absolute Suppression untuk 30% pengurangan"
        " damage pada Arli; ditambah pengurangan damage dari Overlord dan Hero Awaken di papan yang menambah"
        " Attack Speed-nya, hasilnya 70% pengurangan damage dan 4.0 Attack Speed melawan demigod. Dengan"
        " Heavy Gear dan Fully Armed menjadi 85%: tak ada yang bisa melukainya, dan dia melukai semua"),
    "米莱迪、朵莉亚觉醒之后就可以升4级找雅典娜；后期上鲁班大师；鲁班大师机器人的等级就等于召唤物最高等级": (
        "Once Milady and Dolia have Awakened, go to Lv. 4 for Athena; add Master Luban late, whose robot's"
        " Level equals the highest Level among the summons",
        "Setelah Milady dan Dolia Awaken, naik ke Lv. 4 untuk Athena; tambahkan Master Luban di akhir, yang"
        " Level robotnya sama dengan Level summon tertinggi"),
    "继续卖血，第二张卦象依然选节，继续拿钱。\n命运馈赠两张全选阴，都要能量，有钱搜的到嬴政，就能稳血。\n四级可以用免费的刷新小刷，稳一下血。\n": (
        "Keep giving up HP and pick Moderation again for the second Hexagram, for more money.\nFor both Fate"
        " Gifts pick Yin and take Energy; with money to find Ying Zheng, your HP stabilizes.\nAt Lv. 4, use"
        " the free Refreshes for a small roll to steady your HP.\n",
        "Terus korbankan HP dan pilih Moderation lagi untuk Hexagram kedua, untuk tambahan uang.\nUntuk kedua"
        " Fate Gift pilih Yin dan ambil Energy; dengan uang untuk mencari Ying Zheng, HP jadi stabil.\nDi Lv."
        " 4, gunakan Refresh gratis untuk sedikit refresh agar HP stabil.\n"),
    "自然去找体系牌，升5级再去找牌切记，前期不要乱买！选秀姜子牙是必拿的！": (
        "Find the core cards naturally and search properly only at Lv. 5; don't buy at random early! Ziya is"
        " a must in the draft!",
        "Cari kartu inti secara alami dan baru serius mencari di Lv. 5; jangan asal beli di awal! Ziya wajib"
        " diambil saat draft!"),
    "苏烈一定要拿，觉醒后的苏烈前期战力很强。单挂一张苏烈，棋手技能都用给苏烈，有多余的英雄可以开战前上阵打完卖掉。": (
        "Always take Su Lie: an Awakened Su Lie is very strong early. Field a single Su Lie and use every Chessplayer"
        " Skill on him; spare Heroes can be fielded before battle and sold afterwards.",
        "Su Lie wajib diambil: Su Lie yang sudah Awaken sangat kuat di awal. Turunkan satu Su Lie saja dan gunakan"
        " semua Skill Chessplayer padanya; Hero sisa bisa diturunkan sebelum Pertempuran lalu dijual setelahnya."),
    "觉醒狂铁开局": ("Open with an Awakened Biron", "Buka dengan Biron yang Awaken"),
    "请输入文本": ("Enter text", "Masukkan teks"),
    "过度": ("Transition", "Transisi"),
    "这个就是把一阶的买四张刷到觉醒，然后把觉醒的牌全放上去，第四回合选兵的时候最好选那个冻完五阶的，那个没有，就选那个可以冻两个的，第一回合你也可以动你的坦克，然后输出最好选干将为干将是一阶牌里输出最高的。": (
        "Buy four of each Tier 1 Hero and roll them to Awakening, then put all the Awakened cards on the"
        " board. When choosing troops in Round 4, best pick the one that freezes Tier 5; if that's not"
        " offered, the one that can freeze two. In Round 1 you can also freeze your tank, and for damage Gan"
        " is best, being the strongest damage dealer among Tier 1 cards.",
        "Beli empat dari setiap Hero Tier 1 dan refresh sampai Awaken, lalu taruh semua kartu yang Awaken di"
        " papan. Saat memilih pasukan di Ronde 4, sebaiknya pilih yang membekukan Tier 5; jika tidak ada,"
        " pilih yang bisa membekukan dua. Di Ronde 1 kamu juga bisa membekukan tank-mu, dan untuk damage Gan"
        " paling baik, karena damage-nya tertinggi di antara kartu Tier 1."),
    "通过不断的合成场上英雄，找到效果卡传承，对裴擒虎使用，大幅度增加司空震等级": (
        "Keep Combining the Heroes on the board to find Inheritance Effect Cards, and use them on Pei to"
        " raise Sikong Zhen's Level a lot",
        "Terus Combine Hero di papan untuk mendapat Kartu Efek Inheritance, dan gunakan pada Pei untuk"
        " menaikkan Level Sikong Zhen secara besar"),
    "通过技能找牌，中期用铠、百里守约、沈梦溪过度稳血，存钱上本即可。\n二拍优先级：花木兰＞武则天＞上官婉儿": (
        "Find cards with the Skill; mid game, use Kaizer, Shouyue and Shen Mengxi as stopgaps to protect"
        " your HP, and save up to level up.\n2nd Auction priority: Mulan > Wu Zetian > Shangguan",
        "Cari kartu dengan Skill; di pertengahan, pakai Kaizer, Shouyue, dan Shen Mengxi sebagai pengisi"
        " sementara untuk menjaga HP, dan menabung untuk naik level.\nPrioritas Lelang ke-2: Mulan > Wu"
        " Zetian > Shangguan"),
    "速升三级开始找牌": ("Rush to Lv. 3 and start searching for cards", "Cepat naik ke Lv. 3 dan mulai mencari kartu"),
    "遗志转海月，伞绑定海月，补上太乙、小明\r、扁鹊\n刷不到海月可以用吕布": (
        "Last Will into Haya and bind the umbrella to her; add Taiyi, Ming and Dr Bian\nIf you can't find"
        " Haya, Lu Bu works",
        "Last Will ke Haya dan ikat payung padanya; tambahkan Taiyi, Ming, dan Dr Bian\nJika Haya tidak"
        " didapat, Lu Bu juga bisa"),
    "阵容成型后一直打合成获得锦囊【唤醒/集体唤醒/临阵磨枪/全军动员】，商店的露娜必须要买，这些都是给木兰增加复活次数的资源。不花费资源太乙作为备选复活，多余能量买钟馗觉醒可以常驻。第三轮竞拍推荐：一线生机>新生力量>破境之证>能量超新星。": (
        "Once the Lineup is complete, keep Combining for Kits 【Awaken / Mass Awakening / Sharpening Weapons"
        " Before Battle / Full Army Mobilization】, and always buy Luna from the shop: these all add Revives"
        " for Mulan. Taiyi is a free backup Revive, and spare Energy can buy Kui to Awaken and keep on the"
        " board. 3rd Auction: A Glimmer of Hope > New Force > Proof of Breakthrough > Energy Supernova.",
        "Setelah Lineup lengkap, terus Combine untuk Kit 【Awaken / Mass Awakening / Sharpening Weapons"
        " Before Battle / Full Army Mobilization】, dan selalu beli Luna di toko: semuanya menambah Revive"
        " Mulan. Taiyi adalah Revive cadangan gratis, dan Energy lebih bisa membeli Kui untuk di-Awaken dan"
        " tetap di papan. Lelang ke-3: A Glimmer of Hope > New Force > Proof of Breakthrough > Energy Supernova."),

    # ResSeasonAILineupDataBin: PositionDesc
    "1.图腾可以利用东皇保护，防刺客切入。\n2.图腾位置单挂右边，防止被AOE伤害。\n3.图腾可以单围敖隐，左右双挂虞姬敖隐带冰矛风筝单体近战大哥。\n": (
        "1. Use Donghuang to shield the Totems from diving Assassins.\n2. Keep the Totems alone on the right,"
        " away from AOE.\n3. The Totems can ring Ao'yin, with Consort Yu on both sides; with a Frost Spear,"
        " Ao'yin kites a lone melee carry.\n",
        "1. Gunakan Donghuang untuk melindungi Totem dari Assassin.\n2. Taruh Totem sendiri di kanan, jauh"
        " dari AOE.\n3. Totem bisa mengelilingi Ao'yin, dengan Consort Yu di kedua sisi; dengan Frost Spear,"
        " Ao'yin men-kite carry melee tunggal.\n"),
    "中期站位:小乔在中间装黄盾，大家都能吃到，猴子站位可以随便吸曹操小乔甄姬随机一个等级——抖音搜肝帝看攻略": (
        "Mid-game setup: Xiao Qiao in the middle with the yellow shield so everyone gets it; Wukong can"
        " stand anywhere and absorbs the Level of Cao Cao, Xiao Qiao or Lady Zhen at random. For the guide,"
        " search Gandi on Douyin",
        "Formasi pertengahan: Xiao Qiao di tengah dengan perisai kuning agar semua mendapatkannya; Wukong"
        " bebas di mana saja dan menyerap Level Cao Cao, Xiao Qiao, atau Lady Zhen secara acak. Untuk"
        " panduannya, cari Gandi di Douyin"),
    "主C孙悟空，露娜，肉装在周瑜成型后优先给周瑜。": (
        "The Main Carries are Wukong and Luna; once Zhou Yu is set up, give him the tank Equipment first.",
        "Main Carry adalah Wukong dan Luna; setelah Zhou Yu terbentuk, utamakan Equipment tank untuknya."),
    "全部站最后一排，中间的空位放3级屏障，第二排第三排铺满2级屏障，地雷和弹簧放第一排即可。": (
        "Everyone in the back row, with a Lv. 3 Barrier in the middle gap, Lv. 2 Barriers filling rows 2 and"
        " 3, and Mines and Springs in the front row.",
        "Semua di barisan paling belakang, Barrier Lv. 3 di celah tengah, Barrier Lv. 2 memenuhi baris 2 dan"
        " 3, dan Mine serta Spring di barisan depan."),
    "决赛圈注意下安琪拉的站位，如果对方有闪现的英雄，则用雅典娜和其他友方英雄将安琪拉包围住，防止闪现英雄近身。": (
        "In the finals, mind Angela's position: if the enemy has Flash Heroes, surround Angela with Athena and other"
        " allied Heroes to keep Flash Heroes from reaching her.",
        "Di final, perhatikan posisi Angela: jika lawan punya Hero Flash, kelilingi Angela dengan Athena dan Hero"
        " sekutu lain agar Hero Flash tidak bisa mendekat."),
    "前期小鹿当前排顶前面，12回合后小鹿放后面，让其他牺牲单位先牺牲。": (
        "Early, the deer holds the front row; after Round 12 move it back so the other Sacrifice units die first.",
        "Di awal, rusa menahan barisan depan; setelah Ronde 12 pindahkan ke belakang agar unit Sacrifice"
        " lain gugur lebih dulu."),
    "前期干将主c\n缩角，曜、牛魔放前排\r\n遗志后海月放前排": (
        "Early, Gan carries\nfrom a corner, with Yao and Niu Mo in front\nAfter Last Will, Haya goes in front",
        "Di awal, Gan sebagai carry\ndi sudut, Yao dan Niu Mo di depan\nSetelah Last Will, Haya di depan"),
    "前期蒙恬没有10蓝的时候站前排，后期蒙恬有10蓝了后就站角落。": (
        "Early, while Meng Tian lacks 10 Mana, he stands in front; once he has 10 Mana late, put him in a corner.",
        "Di awal, selama Meng Tian belum punya 10 Mana, dia di depan; setelah punya 10 Mana di akhir, taruh di sudut."),
    "如图所示": ("As shown", "Seperti pada gambar"),
    "嬴律缩脚保证输出环境，庄周站中间为全队提供免控的同时吃满黄盾。": (
        "Ying Lu stays in a corner to deal damage safely; Zhuangzi in the middle gives the team Control"
        " Immunity and gets the full yellow shield.",
        "Ying Lu di sudut agar aman memberi damage; Zhuangzi di tengah memberi tim Kebal Kontrol sekaligus"
        " mendapat perisai kuning penuh."),
    "嬴政挂角落，其他人龟甲阵，把敌人聚集起来，嬴政开大后可以全打到。": (
        "Put Ying Zheng in a corner and the rest in a turtle formation to bunch enemies up, so his Ultimate"
        " hits them all.",
        "Taruh Ying Zheng di sudut dan sisanya dalam formasi kura-kura untuk mengumpulkan musuh, agar"
        " Ultimate-nya mengenai semuanya."),
    "嬴政站最里边防刺客切入，注意钟馗的勾，站位基本随意，大招一开全屏开射。": (
        "Ying Zheng stands deepest to stop Assassins diving him; watch for Kui's hook. Otherwise the setup"
        " barely matters: once the Ultimate starts, he hits the whole board.",
        "Ying Zheng berdiri paling dalam agar tidak diserang Assassin; waspadai tarikan Kui. Selain itu"
        " formasi bebas: begitu Ultimate aktif, dia menyerang seluruh papan."),
    "守约缩角\r\n铠和盾山压前排送死\r\n太乙复活给守约\r\n小明链子给守约": (
        "Shouyue in a corner\nKaizer and Dunshan push the front row and die\nTaiyi's Revive goes to"
        " Shouyue\nMing's link goes to Shouyue",
        "Shouyue di sudut\nKaizer dan Dunshan maju di barisan depan dan gugur\nRevive Taiyi untuk"
        " Shouyue\nHubungkan Ming ke Shouyue"),
    "小明链子给到老虎身上就行。": ("Just link Ming to Pei.", "Cukup hubungkan Ming ke Pei."),
    "就照着我这个站位来，后期的话就把明世隐卖掉，上钟馗（左边放花木兰，右边放程咬金），然后决战的时候把露娜卖掉，上太乙真人给花木兰复活": (
        "Just copy my setup. Late, sell Ming and bring in Kui (Mulan on his left, Cheng Yaojin on his"
        " right); then for the final battle sell Luna and bring in Taiyi Zhenren to Revive Mulan",
        "Ikuti saja formasi ini. Di akhir, jual Ming dan masukkan Kui (Mulan di kirinya, Cheng Yaojin di"
        " kanannya); lalu di pertempuran final jual Luna dan masukkan Taiyi Zhenren untuk Revive Mulan"),
    "廉颇顶前面就行，不怕被消耗": (
        "Lian Po just holds the front; he doesn't mind taking hits",
        "Lian Po cukup menahan di depan; dia tidak takut diserang"),
    "成型站位：\r\n站位如图，围着太乙真人吃【近卫荣耀】的双抗加成。\r\n明世隐和太乙真人都连接海月。\r\n决赛，可以用觉醒钟馗替换明世隐。\r\n钟馗给前排挂牺牲词条。\r\n有扁鹊可以换东皇太一。": (
        "Final setup:\nAs shown, gather around Taiyi Zhenren for 【Guardian's Glory】's bonus to both"
        " defenses.\nLink both Ming and Taiyi Zhenren to Haya.\nIn the finals, an Awakened Kui can replace"
        " Ming.\nKui gives the front row the Sacrifice Trait.\nWith Dr Bian, you can swap in Donghuang.",
        "Formasi akhir:\nSeperti pada gambar, berkumpul di sekitar Taiyi Zhenren untuk bonus kedua pertahanan"
        " dari 【Guardian's Glory】.\nHubungkan Ming dan Taiyi Zhenren ke Haya.\nDi final, Kui yang Awaken bisa"
        " menggantikan Ming.\nKui memberi Trait Sacrifice ke barisan depan.\nJika ada Dr Bian, bisa diganti"
        " Donghuang."),
    "无刺客就按图中这么站，有刺客莱西奥和司空震放第一排角落，音符搜小阿豪，有全网最细的视频教学": (
        "Without enemy Assassins, stand as shown; against Assassins, put Alessio and Sikong Zhen in a"
        " front-row corner. Search Xiao A'hao on Douyin for the most detailed video tutorials anywhere",
        "Tanpa Assassin lawan, berdiri seperti pada gambar; saat ada Assassin, taruh Alessio dan Sikong Zhen"
        " di sudut barisan depan. Cari Xiao A'hao di Douyin untuk tutorial video paling detail"),
    "明世隐和太乙真人连司空震。钟馗两侧都要放英雄来触发他的卡牌效果。": (
        "Link Ming and Taiyi Zhenren to Sikong Zhen. Place Heroes on both sides of Kui to trigger his Card Effect.",
        "Hubungkan Ming dan Taiyi Zhenren ke Sikong Zhen. Taruh Hero di kedua sisi Kui untuk memicu Efek Kartu-nya."),
    "有东皇后，图腾不会被优先攻击，可以保证敖隐持续触发自身效果。\n面对刺客就缩角落站位，对手AOE充足就一字长蛇阵，东皇大司命站前排，其余放后排，保证图腾生存即可。": (
        "With Donghuang on the board, Totems aren't focused first, so Ao'yin keeps triggering his"
        " effect.\nAgainst Assassins, huddle in a corner; against heavy AOE, spread out in a single line with"
        " Donghuang and Augran in front and the rest at the back. Just keep the Totems alive.",
        "Dengan Donghuang di papan, Totem tidak diserang lebih dulu, jadi Ao'yin terus memicu"
        " efeknya.\nMelawan Assassin, berkumpul di sudut; melawan AOE kuat, berbaris satu garis dengan"
        " Donghuang dan Augran di depan dan sisanya di belakang. Cukup pastikan Totem tetap hidup."),
    "木兰可以放在后排避免被集火消耗复活次数。特别注意小心【班叔】的三级弹簧，有班叔陷阱时，可以让队友都放到前排。": (
        "Keep Mulan in the back row so focus fire doesn't burn her Revives. Watch out for 【Uncle Ban】's Lv."
        " 3 Springs: against his traps, move your teammates to the front row.",
        "Taruh Mulan di barisan belakang agar Revive-nya tidak habis karena fokus serangan. Waspadai Spring"
        " Lv. 3 milik 【Uncle Ban】: saat ada jebakannya, pindahkan rekan ke barisan depan."),
    "李元芳和百里玄策放在一起，触发李元芳卡牌效果（李元芳周围不要放其它英雄，其英雄效果只对最近英雄生效）。太乙放在玄策旁边复活玄策。": (
        "Place Fang next to Xuance to trigger Fang's Card Effect (put no other Heroes around Fang; his Hero Effect"
        " only works on the nearest Hero). Put Taiyi beside Xuance to Revive him.",
        "Taruh Fang bersebelahan dengan Xuance untuk memicu Efek Kartu Fang (jangan taruh Hero lain di sekitar Fang;"
        " Efek Hero-nya hanya berlaku untuk Hero terdekat). Taruh Taiyi di samping Xuance untuk Revive Xuance."),
    "没什么正位，这几个就是最强的五阶，你拿出来随便放就行了，前排放前排，后排放后排。": (
        "No fixed setup: these are the strongest Tier 5s, so place them however you like, front-liners in"
        " front and back-liners at the back.",
        "Tidak ada formasi pasti: ini Hero Tier 5 terkuat, jadi taruh sesukamu, barisan depan di depan dan"
        " barisan belakang di belakang."),
    "海月站前面，其他都站后面": ("Haya in front, everyone else at the back", "Haya di depan, yang lain di belakang"),
    "瑶、明世隐、太乙真人都连猪八戒。": (
        "Link Yaria, Ming and Taiyi Zhenren all to Zhu Bajie.",
        "Hubungkan Yaria, Ming, dan Taiyi Zhenren semuanya ke Zhu Bajie."),
    "瑶妹、太乙挂韩信": ("Link Yaria and Taiyi to Han Xin", "Hubungkan Yaria dan Taiyi ke Han Xin"),
    "瑶连马超，瑶的技能可以给连接的英雄增加属性。": (
        "Link Yaria to Ma Chao: Yaria's Skill boosts the stats of the Hero she is linked to.",
        "Hubungkan Yaria ke Ma Chao: Skill Yaria menambah atribut Hero yang terhubung dengannya."),
    "站位最优解如图，司空震稳稳输出，大后期姬小满可以换成太乙提供复活或者钟馗降低对面等级！抖音-强者无敌": (
        "The best setup is as shown: Sikong Zhen deals damage safely. Very late, swap Mayene for Taiyi to"
        " Revive or for Kui to lower enemy Levels! Douyin: Qiangzhe Wudi",
        "Formasi terbaik seperti pada gambar: Sikong Zhen memberi damage dengan aman. Di akhir permainan,"
        " ganti Mayene dengan Taiyi untuk Revive atau Kui untuk menurunkan Level lawan! Douyin: Qiangzhe Wudi"),
    "米莱狄站角落记得带炽热，防止被钩；朵莉亚位于中心，保证“泳池”可以覆盖到全部队友": (
        "Milady goes in a corner with Sanguine Dominator so she can't be hooked; Dolia in the center so her"
        " “pool” covers every ally",
        "Milady di sudut dengan Sanguine Dominator agar tidak bisa ditarik; Dolia di tengah agar “kolam”-nya"
        " menjangkau semua rekan"),
    "英雄只放后两排前两排全放弹簧陷阱\n前两排摆放如下：句号是空格，问号是陷阱，感叹号是弹簧\n？？？。？？？\n。。！！！。。\n东皇来了之句号的位置可以放图腾\n抽到屏障就放第一排扛伤害\n升三级和六级技能给陷阱": (
        "Heroes only in the back two rows; fill the front two with Spring Traps\nFront two rows (. = empty, ?"
        " = trap, ! = spring):\n???.???\n..!!!..\nOnce Donghuang arrives, put Totems on the empty spots\nPut any"
        " Barrier you draw in the front row to absorb damage\nAt Lv. 3 and Lv. 6, give the Skill to the traps",
        "Hero hanya di dua baris belakang; isi dua baris depan dengan Spring Trap\nDua baris depan (. ="
        " kosong, ? = jebakan, ! = spring):\n???.???\n..!!!..\nSetelah Donghuang datang, taruh Totem di tempat"
        " kosong\nTaruh Barrier yang didapat di barisan depan untuk menahan damage\nDi Lv. 3 dan Lv. 6,"
        " berikan Skill ke jebakan"),
    "蔡文姬的技能可以给范围内英雄回血，建议放在中间。": (
        "Cai Yan's Skill heals Heroes in range, so place her in the middle.",
        "Skill Cai Yan memulihkan HP Hero dalam jangkauan, jadi taruh dia di tengah."),
    "虞姬和敖隐放最后一排。拿到敖隐后需要把所有图腾都放最后一排，图腾在场上时能触发敖隐的卡牌效果，敖隐在战斗中持续提升等级。": (
        "Place Consort Yu and Ao'yin on the back row. Once you have Ao'yin, put every Totem on the back row: Totems on"
        " the board trigger Ao'yin's Card Effect, so Ao'yin keeps levelling up in battle.",
        "Taruh Consort Yu dan Ao'yin di baris paling belakang. Setelah dapat Ao'yin, taruh semua Totem di baris"
        " paling belakang: Totem di papan memicu Efek Kartu Ao'yin, sehingga Level Ao'yin terus naik dalam"
        " Pertempuran."),
    "通用站位鬼谷子第一排 ，少司原左边沉底，公孙离则站在右边  。注意 ！在遇到逐鹿体系以及倒转体系还有单刺客体系时我们都需要改变站位 。想系统学习请关注抖音 色彩直播间 ": (
        "Standard setup: Guiguzi in the front row, Dyadia at the back on the left, Arli on the right. Note!"
        " Change the setup against Zhulu Plateau, Reversal and single-Assassin builds. To learn it properly,"
        " follow Secai's live stream on Douyin",
        "Formasi umum: Guiguzi di barisan depan, Dyadia di belakang sebelah kiri, Arli di kanan. Perhatian!"
        " Ubah formasi saat melawan build Zhulu Plateau, Reversal, dan Assassin tunggal. Untuk belajar"
        " lengkap, ikuti live stream Secai di Douyin"),
    "都在蔡文姬周围吃防御和回血，阿离在角落输出": (
        "Everyone around Cai Yan for her defense and healing, with Arli dealing damage from a corner",
        "Semua di sekitar Cai Yan untuk pertahanan dan pemulihannya, Arli memberi damage dari sudut"),
    "钟馗的卡牌效果可以给两侧英雄加牺牲关键词，两侧放自身不带牺牲的英雄。小明和太乙都连李信。": (
        "Kui's Card Effect gives the Heroes on both sides the Sacrifice keyword, so flank him with Heroes that lack"
        " Sacrifice. Link Ming and Taiyi both to Li Xin.",
        "Efek Kartu Kui memberi keyword Sacrifice ke Hero di kedua sisinya, jadi taruh Hero tanpa Sacrifice di kedua"
        " sisinya. Hubungkan Ming dan Taiyi ke Li Xin."),
    "钟馗给程咬金花木兰或李白，露娜上场后不卖，防止对手卡牌。": (
        "Link Kui to Cheng Yaojin, Mulan or Li Bai; once Luna is on the board, don't sell her, so opponents"
        " can't take the card.",
        "Hubungkan Kui ke Cheng Yaojin, Mulan, atau Li Bai; setelah Luna di papan, jangan dijual agar lawan"
        " tidak mendapat kartunya."),

    # ResSeasonAILineupDataBin: SimpleDesc
    "30秒学会三分倒转，首先记住三张卡:露娜、曹操、甄姬。露娜和甄姬是登场牌，从手牌上场时触发效果;曹操是整备牌，回合开始时触发，且露娜登场能触发曹操整备。字符有限，详细细节一-抖音搜肝帝": (
        "Learn Three Kingdoms Reversal in 30 seconds. First remember three cards: Luna, Cao Cao, Lady Zhen."
        " Luna and Lady Zhen are Deploy cards that trigger when played from your hand; Cao Cao is a Prepare"
        " card that triggers at the start of a Round, and Luna's Deploy also triggers Cao Cao's Prepare."
        " Space is short: for details, search Gandi on Douyin",
        "Pelajari Three Kingdoms Reversal dalam 30 detik. Pertama ingat tiga kartu: Luna, Cao Cao, Lady"
        " Zhen. Luna dan Lady Zhen adalah kartu Deploy yang aktif saat dimainkan dari tangan; Cao Cao adalah"
        " kartu Prepare yang aktif di awal Ronde, dan Deploy Luna juga memicu Prepare Cao Cao. Ruang"
        " terbatas: untuk detailnya, cari Gandi di Douyin"),
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
    "三阶无阵营组合。八戒能给每张卡和成提供额外等级，老虎吸别人等级，小明转换成真实等级，阿轲登场提供等级。血量低，优先打阿轲。": (
        "A factionless Tier 3 combo. Zhu Bajie gives extra Levels for each card Combined, Pei absorbs"
        " others' Levels, Ming turns them into real Levels, and Arke gives Levels on Deploy. When HP is low,"
        " play Arke first.",
        "Kombo Tier 3 tanpa Faction. Zhu Bajie memberi Level tambahan untuk setiap kartu yang di-Combine,"
        " Pei menyerap Level Hero lain, Ming mengubahnya menjadi Level asli, dan Arke memberi Level saat"
        " Deploy. Saat HP rendah, utamakan memainkan Arke."),
    "主c廉颇，技能生成护盾，盾破造成伤害\n不吃等级\n扁鹊上场会让廉颇伤害有质的提升\n\n\n——抖音余烬": (
        "Lian Po carries: his Skill creates a Shield that deals damage when it breaks\nHe doesn't need"
        " Levels\nDr Bian on the board boosts his damage dramatically\n\n\nDouyin: Yujin",
        "Lian Po sebagai carry: Skill-nya membuat Shield yang memberi damage saat pecah\nTidak butuh Level\nDr"
        " Bian di papan meningkatkan damage-nya secara drastis\n\n\nDouyin: Yujin"),
    "乔汐6级后专属天赋可以召唤高等级英雄入场，此英雄等级算作临时等级，可以触发司空震的卡牌效果让他也获得临时等级。明世隐能保留临时等级。": (
        "From Lv. 6, Qiao Xi's Exclusive Talent Summons a high-Level Hero onto the board. That Hero's Level counts as"
        " Temporary Level, which triggers Sikong Zhen's Card Effect so he gains Temporary Levels too. Ming can keep"
        " Temporary Levels.",
        "Mulai Lv. 6, Exclusive Talent Qiao Xi bisa Summon Hero ber-Level tinggi ke papan. Level Hero itu dihitung"
        " sebagai Temporary Level, yang memicu Efek Kartu Sikong Zhen sehingga dia juga mendapat Temporary Level."
        " Ming bisa menyimpan Temporary Level."),
    "使用古币可以提升花木兰复活次数，程咬金/上官婉儿整备提供古币，露娜触发整备效果，通过唤醒、集体唤醒、全军动员等牌使花木兰获得多次复活。": (
        "Ancient Coins add Revives for Mulan: Cheng Yaojin's and Shangguan's Prepare provides the coins,"
        " Luna triggers Prepare, and cards such as Awaken, Mass Awakening and Full Army Mobilization give"
        " Mulan many Revives.",
        "Ancient Coin menambah Revive Mulan: Prepare Cheng Yaojin dan Shangguan memberi koinnya, Luna memicu"
        " Prepare, dan kartu seperti Awaken, Mass Awakening, dan Full Army Mobilization memberi Mulan banyak Revive."),
    "使用逐鹿战术牌，可以给嬴律提供超高法术攻击，芈月提高嬴律等级，西施给嬴律减蓝达到技能无缝衔接，高频合成触发鲁班七号卡牌效果获得战术牌。": (
        "Zhulu Plateau Tactics Cards give Ying Lu huge Magic Attack, Mi Yue raises his Level, Shi lowers his"
        " Mana for back-to-back Skills, and frequent Combines trigger Luban No.7's Card Effect for more"
        " Tactics Cards.",
        "Tactics Card Zhulu Plateau memberi Ying Lu Magic Attack sangat tinggi, Mi Yue menaikkan Level-nya,"
        " Shi menurunkan Mana-nya agar Skill bisa beruntun, dan Combine yang sering memicu Efek Kartu Luban"
        " No.7 untuk Tactics Card tambahan."),
    "利用11回合后小鹿牺牲会分享等级的效果，将等级集中到李信身上。局势较顺15回合后就能轻松999": (
        "After Round 11 the deer's Sacrifice shares its Levels: pool them all into Li Xin. If things go"
        " well, Lv. 999 comes easily after Round 15",
        "Setelah Ronde 11, Sacrifice rusa membagi Level-nya: kumpulkan semuanya ke Li Xin. Jika lancar, Lv."
        " 999 mudah dicapai setelah Ronde 15"),
    "利用大河词条的联动自动升级以及大河流 卡牌极强的战斗力配合我们香香的武器取得游戏胜利 ": (
        "Win with the Riverlands Trait's linked auto-leveling, the Riverlands cards' huge combat power and"
        " Xiangxiang's weapon",
        "Menang dengan naik level otomatis dari Trait Riverlands, kekuatan tempur besar kartu Riverlands,"
        " dan senjata Xiangxiang"),
    "利用木兰的无限复活和单体爆发收割全场。觉醒婉儿+程咬金每回合整备获得8个古币，能给木兰额外提供2次复活，打出露娜能再次触发咬金婉儿的整备效果无限叠加（复活次数上限10次）。": (
        "Mulan's endless Revives and single-target burst sweep the board. Awakened Shangguan and Cheng"
        " Yaojin gain 8 Ancient Coins from Prepare each Round, giving Mulan 2 more Revives, and playing Luna"
        " triggers their Prepare again so it stacks (up to 10 Revives).",
        "Revive tanpa batas dan burst target tunggal Mulan menyapu papan. Shangguan dan Cheng Yaojin yang"
        " Awaken mendapat 8 Ancient Coin dari Prepare setiap Ronde, memberi Mulan 2 Revive tambahan, dan"
        " memainkan Luna memicu Prepare mereka lagi hingga menumpuk (maks. 10 Revive)."),
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
    "前期伞绑定干将叠等级\r\n优先觉醒干将后再买曜、孙膑、牛魔\r\n之后反复买这四个英雄拿锦囊开遗志\r\n前期不要升级棋手，遗志在棋手二级三级出的概率最高\r\n拿到遗志后速拉到五级找海月\r\n——抖音余烬": (
        "Early, bind the umbrella to Gan to stack Levels\nAwaken Gan first, then buy Yao, Sun Bin and Niu"
        " Mo\nKeep buying these four Heroes for Kits until Last Will appears\nDon't level your Chessplayer"
        " early: Last Will is most likely at Chessplayer Lv. 2-3\nOnce you have Last Will, rush to Lv. 5 to"
        " find Haya\nDouyin: Yujin",
        "Di awal, ikat payung ke Gan untuk menumpuk Level\nAwaken Gan dulu, lalu beli Yao, Sun Bin, dan Niu"
        " Mo\nTerus beli keempat Hero ini untuk Kit sampai Last Will muncul\nJangan naikkan level Chessplayer"
        " di awal: Last Will paling sering muncul di Chessplayer Lv. 2-3\nSetelah dapat Last Will, cepat naik"
        " ke Lv. 5 untuk mencari Haya\nDouyin: Yujin"),
    "前期依靠三分的强势和公孙离的高等级，过度，后期上小乔甄姬露娜倒转，从头强到尾\n": (
        "Ride Three Kingdoms' early strength and Arli's high Level through the early game, then switch to"
        " the Xiao Qiao, Lady Zhen and Luna Reversal late: strong from start to finish\n",
        "Andalkan kekuatan awal Three Kingdoms dan Level tinggi Arli di awal, lalu beralih ke Reversal Xiao"
        " Qiao, Lady Zhen, dan Luna di akhir: kuat dari awal sampai akhir\n"),
    "功能英雄芈月，上阵后使用战术牌触发卡牌效果，给装备最多的英雄升级。输出英雄蒙犽，其它位置拿任意可产出战术牌的英雄。": (
        "Mi Yue is the utility Hero: once she is on the board, Tactics Cards trigger her Card Effect and level up the"
        " Hero with the most Equipment. Meng Ya is the damage dealer; fill the other slots with any Heroes that"
        " produce Tactics Cards.",
        "Mi Yue adalah Hero utilitas: setelah dia di papan, Tactics Card memicu Efek Kartu-nya dan menaikkan Level"
        " Hero dengan Equipment terbanyak. Meng Ya adalah damage dealer; isi posisi lain dengan Hero apa pun yang"
        " menghasilkan Tactics Card."),
    "司空震主c，姜子牙为司空震提供真实等级，亚瑟，莱西奥，海诺为司空震提供临时等级，姬小满提供刷新次数帮助我们找到阵容所需牌": (
        "Sikong Zhen carries: Ziya gives him real Levels, Arthur, Alessio and Heino give him Temporary"
        " Levels, and Mayene gives Refreshes to find the cards the Lineup needs",
        "Sikong Zhen sebagai carry: Ziya memberinya Level asli, Arthur, Alessio, dan Heino memberinya"
        " Temporary Level, dan Mayene memberi Refresh untuk mencari kartu yang dibutuhkan Lineup"),
    "同行的克星，也是舞凤，闹闹，赢律，明先生，的严父。": (
        "The bane of players on the same Lineup, and a strict father to Wufeng, Naonao, Ying Lu and Mr. Ming.",
        "Momok bagi pemain dengan Lineup yang sama, sekaligus ayah galak bagi Wufeng, Naonao, Ying Lu, dan Mr. Ming."),
    "大河龙蛇阵容，三图腾给敖隐、东皇提供Buff加持局内战力，多开团词条通过张良转化为等级，虞姬根据图腾数量提升等级，以此达到阵容闭环。": (
        "A Riverlands Dragon-Snake Lineup: three Totems buff Ao'yin and Donghuang in battle, Liang turns"
        " extra Initiate Traits into Levels, and Consort Yu gains Levels per Totem, closing the loop.",
        "Lineup Dragon-Snake Riverlands: tiga Totem memberi Buff ke Ao'yin dan Donghuang dalam pertempuran,"
        " Liang mengubah Trait Initiate tambahan menjadi Level, dan Consort Yu naik Level sesuai jumlah"
        " Totem, sehingga Lineup saling melengkapi."),
    "嫦娥的技能可以提升英雄等级，秘技牌能使4个英雄同时升级，只上阵4个强力英雄可以让嫦娥技能收益最大，这套阵容只需要一直用嫦娥的技能提升等级。": (
        "Chang'e's Skill raises Hero Levels and her Secret Skill Card levels up 4 Heroes at once. Fielding only 4"
        " strong Heroes gets the most out of her Skill; this Lineup just keeps using Chang'e's Skill to raise Levels.",
        "Skill Chang'e menaikkan Level Hero dan Kartu Secret Skill-nya menaikkan Level 4 Hero sekaligus. Hanya"
        " menurunkan 4 Hero kuat memaksimalkan manfaat Skill-nya; Lineup ini cukup terus memakai Skill Chang'e untuk"
        " menaikkan Level."),
    "嬴律的低压运营使场上英雄等级自动提升和基层提拔打出1-3阶牌额外加等级，使场上低阶牌等级疯涨，再用公孙离和猪八戒的夺取把等级集中，全觉醒公孙离攻速4.0": (
        "Ying Lu's Low-Pressure Strategy levels the board's Heroes on its own and Base Promotion adds Levels"
        " for each Tier 1-3 card played, so low-Tier cards skyrocket; then Arli's and Zhu Bajie's Steal"
        " pools the Levels. Fully Awakened, Arli reaches 4.0 Attack Speed",
        "Strategi Tekanan Rendah Ying Lu menaikkan Level Hero di papan secara otomatis dan Promosi Dasar"
        " menambah Level untuk setiap kartu Tier 1-3 yang dimainkan, sehingga kartu Tier rendah melonjak;"
        " lalu Steal Arli dan Zhu Bajie mengumpulkan Level-nya. Saat semua Awaken, Attack Speed Arli mencapai 4.0"),
    "守约单核，伞绑定守约保命\r\n钟馗给前排挂牺牲\r\n前排送死降低守约蓝耗\r\n——抖音余烬": (
        "Shouyue as the single carry, with the umbrella bound to him to keep him alive\nKui gives the front"
        " row Sacrifice\nThe front row dies to cut Shouyue's Mana cost\nDouyin: Yujin",
        "Shouyue sebagai carry tunggal, payung diikat padanya agar tetap hidup\nKui memberi Sacrifice ke"
        " barisan depan\nBarisan depan gugur untuk mengurangi biaya Mana Shouyue\nDouyin: Yujin"),
    "小菟每回合稳定提升等级，越到后期，强度越高的轮椅流阵容！": (
        "Little Rabbit raises Levels steadily every Round: an autopilot Lineup that gets stronger the longer"
        " the game goes!",
        "Little Rabbit menaikkan Level dengan stabil setiap Ronde: Lineup autopilot yang makin kuat seiring"
        " permainan berjalan!"),
    "庄小鱼加强后多四点能量，这套高阶龙蛇又可以重出江湖了，克制单核近战等，": (
        "Zhuang Xiaoyu's buff gives 4 more Energy, so this high-Tier Dragon-Snake is back; it counters"
        " single-carry melee builds and more,",
        "Buff Zhuang Xiaoyu memberi 4 Energy tambahan, jadi Dragon-Snake Tier tinggi ini kembali; efektif"
        " melawan build carry tunggal melee dan lainnya,"),
    "推荐ban逐鹿的时候再玩，别在有嬴政的时候玩，有香香看情况玩。其他情况选了必吃分": (
        "Best played when Zhulu Plateau is banned; avoid it when Ying Zheng is around, and judge for"
        " yourself against Xiangxiang. Otherwise it's guaranteed points",
        "Paling baik dimainkan saat Zhulu Plateau di-ban; hindari saat ada Ying Zheng, dan lihat situasi"
        " jika ada Xiangxiang. Selain itu, poin dijamin"),
    "整备+开团，韩信挂机都能一回合100级": (
        "Prepare + Initiate: Han Xin gains 100 Levels a Round on autopilot",
        "Prepare + Initiate: Han Xin naik 100 Level per Ronde secara autopilot"),
    "明先生综合数据全棋手第一，而这套也是他主流玩法，版本T0；\n出色的经济和搜牌能力，让明先生中期找到嬴政快速稳血， 后期通过合成效果锦囊，找到吸血和机器头，这边稳了直接夺冠。": (
        "Mr. Ming tops every Chessplayer in overall stats, and this is his main build: T0 this patch.\nHis"
        " strong economy and card search find Ying Zheng mid game to stabilize HP; late, Effect Guides from"
        " Combines bring Lifesteal and Robot Head. Once that holds, you take first place.",
        "Mr. Ming unggul dari semua Chessplayer dalam statistik keseluruhan, dan ini build utamanya: T0 di"
        " patch ini.\nEkonomi dan pencarian kartunya yang kuat menemukan Ying Zheng di pertengahan permainan"
        " untuk menstabilkan HP; di akhir, Panduan Efek dari Combine memberi Lifesteal dan Robot Head."
        " Setelah stabil, kamu juara."),
    "最强三分倒转，猴子露娜主c，周瑜主坦，小乔和阿珂为队友提供等级，甄姬给牌，曹操是中转站，露娜是启动器，孙小宾的时之回环能够让我们阵容核心快速觉醒，能再很短的时间有很大的提升": (
        "The strongest Three Kingdoms Reversal: Wukong and Luna carry, Zhou Yu tanks, Xiao Qiao and Arke"
        " give allies Levels, Lady Zhen gives cards, Cao Cao is the relay and Luna the starter. Sun"
        " Xiaobin's Time Loop Awakens the core fast for a big jump in very little time",
        "Three Kingdoms Reversal terkuat: Wukong dan Luna sebagai carry, Zhou Yu tank, Xiao Qiao dan Arke"
        " memberi Level ke rekan, Lady Zhen memberi kartu, Cao Cao sebagai perantara dan Luna sebagai"
        " pemicu. Time Loop Sun Xiaobin membuat inti Lineup cepat Awaken untuk lonjakan besar dalam waktu singkat"),
    "有的时候会很爽，有的时候会很拉，完全看运气，靠赌的一个阵容。": (
        "Sometimes it's amazing, sometimes it flops: a gamble that comes down to luck.",
        "Kadang sangat seru, kadang gagal total: Lineup untung-untungan yang sepenuhnya bergantung keberuntungan."),
    "李信的卡牌效果是：其它英雄触发牺牲效果时，提升等级。除李信其他位置拿牺牲英雄，且复活次数越多，能触发牺牲的次数越多。小明可以保留李信在战斗中提升的等级，每回合给李信稳定升级。": (
        "Li Xin's Card Effect: he gains Levels when other Heroes trigger Sacrifice effects. Fill every slot besides Li"
        " Xin with Sacrifice Heroes; the more they Revive, the more Sacrifices they trigger. Ming keeps the Levels Li"
        " Xin gains in battle, levelling him up steadily each Round.",
        "Efek Kartu Li Xin: Level-nya naik saat Hero lain memicu efek Sacrifice. Isi semua posisi selain Li Xin"
        " dengan Hero Sacrifice; makin sering mereka Revive, makin sering Sacrifice terpicu. Ming menyimpan Level"
        " yang didapat Li Xin dalam Pertempuran, menaikkan Level-nya dengan stabil setiap Ronde."),
    "核心-朵莉亚：凭借朵莉亚大招的“泳池”，给队友回血回蓝，更快更多的释放技能；亚连、米莱迪每回合的整备配合朵莉亚词条，可以给全员提升等级；少司缘图腾，也可以给全员加等级；后期加鲁班大师": (
        "Core: Dolia. Her Ultimate's “pool” restores allies' HP and Mana so they cast Skills faster and more"
        " often; Allain's and Milady's Prepare each Round works with Dolia's Trait to level up the whole"
        " team; Dyadia's Totem also levels everyone; add Master Luban late",
        "Inti: Dolia. “Kolam” dari Ultimate-nya memulihkan HP dan Mana rekan agar lebih cepat dan sering"
        " memakai Skill; Prepare Allain dan Milady setiap Ronde bersama Trait Dolia menaikkan Level seluruh"
        " tim; Totem Dyadia juga menaikkan Level semua Hero; tambahkan Master Luban di akhir"),
    "核心英雄是蒙恬，西施提供推演战术减蒙恬的蓝上限，芈月通过效果牌提升蒙恬等级，苍可以让蒙恬召唤的小兵死后能对周围的敌人造成伤害，白起是打出位，鲁班大师最后上补伤害。": (
        "Meng Tian is the core: Shi's Deduction Tactics lower his max Mana, Mi Yue raises his Level with"
        " Effect Cards, Chano makes his summoned minions damage nearby enemies when they die, Bai Qi is the"
        " play slot, and Master Luban joins last for extra damage.",
        "Meng Tian adalah inti: Deduction Tactics dari Shi menurunkan Mana maksimalnya, Mi Yue menaikkan"
        " Level-nya lewat Kartu Efek, Chano membuat minion panggilannya memberi damage ke musuh sekitar saat"
        " mati, Bai Qi adalah slot main, dan Master Luban masuk terakhir untuk tambahan damage."),
    "核心英雄虞姬，找到虞姬后，凑齐三个图腾英雄，触发虞姬词条升级。次级核心张良，找到张良后，尽量多上开团英雄，提升等级。升到5级后找到敖隐和东皇阵容成型。": (
        "Consort Yu is the core Hero: once you have her, gather three Totem Heroes to trigger her Trait and level up."
        " Liang is the second core: once you have him, field as many Initiate Heroes as you can to raise Levels. At"
        " Lv. 5, finding Ao'yin and Donghuang completes the Lineup.",
        "Consort Yu adalah Hero inti: setelah mendapatkannya, kumpulkan tiga Hero Totem untuk memicu Trait-nya dan"
        " naik level. Liang adalah inti kedua: setelah mendapatkannya, turunkan Hero Initiate sebanyak mungkin untuk"
        " menaikkan Level. Di Lv. 5, Lineup lengkap setelah mendapat Ao'yin dan Donghuang."),
    "此套阵容记住核心逻辑，两个最最关键英雄，姜子牙和司空震。姜子牙刷非河洛牌给司空震提供等级，司空震吸收临时等级，阿米亚核心分配是核心等级，333级司空震+666核心=999司空震！抖音-强者无敌": (
        "Remember the core logic: the two key Heroes are Ziya and Sikong Zhen. Ziya rolls non-Central Plains"
        " cards to give Sikong Zhen Levels, Sikong Zhen absorbs Temporary Levels, and the Arcomia Core"
        " shares out the Core Level: Lv. 333 Sikong Zhen + Lv. 666 Core = Lv. 999 Sikong Zhen! Douyin: Qiangzhe Wudi",
        "Ingat logika intinya: dua Hero kunci adalah Ziya dan Sikong Zhen. Ziya me-refresh kartu non-Central"
        " Plains untuk memberi Level ke Sikong Zhen, Sikong Zhen menyerap Temporary Level, dan Arcomia Core"
        " membagikan Level Core: Sikong Zhen Lv. 333 + Core Lv. 666 = Sikong Zhen Lv. 999! Douyin: Qiangzhe Wudi"),
    "猪八戒的卡牌效果可以在英雄合成时给全部同阶英雄升级，因此阵容选3阶英雄。瑶给猪八戒增加属性，刘禅战斗中提供临时等级，明世隐保留战斗中的临时等级，使猪八戒的战力最大化。姬小满提供刷新帮助找场上的英雄牌。": (
        "Zhu Bajie's Card Effect levels up every Hero of the same Tier when a Hero Combines, so the Lineup uses Tier 3"
        " Heroes. Yaria boosts Zhu Bajie's stats, Liu Shan gives Temporary Levels in battle and Ming keeps them,"
        " maximizing Zhu Bajie's power. Mayene gives Refreshes that help find Hero Cards of Heroes on the board.",
        "Efek Kartu Zhu Bajie menaikkan Level semua Hero dengan Tier yang sama saat Hero di-Combine, jadi Lineup ini"
        " memakai Hero Tier 3. Yaria menambah atribut Zhu Bajie, Liu Shan memberi Temporary Level dalam Pertempuran,"
        " dan Ming menyimpannya, sehingga kekuatan Zhu Bajie maksimal. Mayene memberi Refresh yang membantu menemukan"
        " Kartu Hero dari Hero di papan."),
    "玉环可以治疗班叔的屏障，班叔的屏障2级后阻挡敌方近战的同时还可以挡住飞行物。玉环/干将/孙膑等超高技能频率英雄触发诸葛亮和刘禅被动，提供临时等级战力，明世隐将临时等级转化为真实等级": (
        "Yuhuan heals Uncle Ban's Barriers, and from Lv. 2 his Barriers block projectiles as well as enemy"
        " melee. Fast-casting Heroes such as Yuhuan, Gan and Sun Bin trigger Kongming's and Liu Shan's"
        " passives for Temporary Levels, and Ming turns those into real Levels",
        "Yuhuan memulihkan Barrier Uncle Ban, dan mulai Lv. 2 Barrier-nya menahan proyektil sekaligus melee"
        " musuh. Hero dengan frekuensi Skill tinggi seperti Yuhuan, Gan, dan Sun Bin memicu pasif Kongming"
        " dan Liu Shan untuk Temporary Level, dan Ming mengubahnya menjadi Level asli"),
    "瑶和明世隐保护艾琳，海月在前面挡住": (
        "Yaria and Ming protect Erin while Haya holds the front",
        "Yaria dan Ming melindungi Erin, sementara Haya menahan di depan"),
    "这套阵容的核心是增加阿科米亚核心等级。朵莉亚是必备英雄，上阵后其它位置全部使用带【整备】关键词的英雄，触发朵莉亚卡牌效果增加阿科米亚核心等级。": (
        "This Lineup is about raising the Arcomia Core's Level. Dolia is a must: once she is on the board, fill every"
        " other slot with Heroes with the 【Prepare】 keyword to trigger her Card Effect and raise the Arcomia Core's"
        " Level.",
        "Inti Lineup ini adalah menaikkan Level Arcomia Core. Dolia wajib ada: setelah dia di papan, isi semua posisi"
        " lain dengan Hero ber-keyword 【Prepare】 untuk memicu Efek Kartu-nya dan menaikkan Level Arcomia Core."),
    "通过整备词条提升等级，进而提升战斗力。前中期不着急打合成，在血量健康的情况下，可以等到亚瑟来了之后一起打，吃亚瑟的词条，后期可以把狂铁卖了，留一个打出位，用来打出露娜": (
        "Prepare Traits raise Levels and with them combat power. Don't rush Combines early to mid game: with"
        " healthy HP, wait for Arthur and Combine together to benefit from his Trait. Late, sell Biron to"
        " keep a play slot for Luna",
        "Trait Prepare menaikkan Level dan kekuatan tempur. Jangan buru-buru Combine di awal hingga"
        " pertengahan permainan: jika HP aman, tunggu Arthur lalu Combine bersama agar dapat Trait-nya. Di"
        " akhir, jual Biron untuk menyisakan slot main bagi Luna"),
    "通过芈月词条不断打出效果卡给主C嬴政加等级，同时触发嬴政词条无限叠法强，一秒融化敌方阵容。": (
        "Mi Yue's Trait keeps playing Effect Cards to level up the Main Carry Ying Zheng, while triggering"
        " Ying Zheng's Trait to stack Magic Attack without limit and melt the enemy Lineup in a second.",
        "Trait Mi Yue terus memainkan Kartu Efek untuk menaikkan Level Main Carry Ying Zheng, sekaligus"
        " memicu Trait Ying Zheng untuk menumpuk Magic Attack tanpa batas dan melelehkan Lineup lawan dalam sedetik."),
    "阵容原理：\r\n安琪拉飞行器自爆强化造成的伤害越高（包括对己方伤害），等级提升越多，配合大河三个图腾，能快速提升海月等级。\r\n棋手安琪拉飞行器提供临时等级，明世隐转换临时等级。\r": (
        "How it works:\nThe more damage Angela's Aircraft self-destruct enhancement deals (allies included),"
        " the more Levels it gives; with three Riverlands Totems, Haya levels up fast.\nChessplayer Angela's"
        " Aircraft gives Temporary Levels, and Ming converts them.\n",
        "Cara kerjanya:\nMakin besar damage dari peningkatan self-destruct Pesawat Angela (termasuk ke"
        " rekan), makin banyak Level yang didapat; dengan tiga Totem Riverlands, Haya cepat naik"
        " Level.\nPesawat Chessplayer Angela memberi Temporary Level, dan Ming mengubahnya.\n"),
    "阵容的核心是增加阿科米亚核心等级。朵莉亚是必备英雄，上阵后其它位置全部使用带【整备】关键词的英雄，触发朵莉亚卡牌效果增加阿科米亚核心等级。阿科米亚核心的等级会在开战时以临时等级均分给场上的日落海英雄。": (
        "The Lineup is about raising the Arcomia Core's Level. Dolia is a must: once she is on the board, fill every"
        " other slot with Heroes with the 【Prepare】 keyword to trigger her Card Effect and raise the Arcomia Core's"
        " Level. At the start of battle, the Arcomia Core's Level is split evenly among Sunset Heroes on the board as"
        " Temporary Levels.",
        "Inti Lineup adalah menaikkan Level Arcomia Core. Dolia wajib ada: setelah dia di papan, isi semua posisi"
        " lain dengan Hero ber-keyword 【Prepare】 untuk memicu Efek Kartu-nya dan menaikkan Level Arcomia Core. Saat"
        " Pertempuran dimulai, Level Arcomia Core dibagi rata ke Hero Sunset di papan sebagai Temporary Level."),
    "高上限的三分玩法之一，通过场上英雄的互相联动配合白歌的棋手技能": (
        "A high-ceiling Three Kingdoms build: the Heroes on the board work off one another and Bai Ge's"
        " Chessplayer Skill",
        "Build Three Kingdoms dengan batas atas tinggi: Hero di papan saling terhubung dengan Skill"
        " Chessplayer Bai Ge"),

    # ResSeasonAILineupDataBin: TalentDesc (advice on Talents; game data 1.7.0.1)
    "乐善好施加等级很快，同路人成年礼获得大量的三分牌\n": (
        "Benevolent and Charitable adds Levels fast; Fellow Traveler and Coming of Age bring lots of Three"
        " Kingdoms cards\n",
        "Benevolent and Charitable menambah Level dengan cepat; Teman Seperjalanan dan Coming of Age memberi"
        " banyak kartu Three Kingdoms\n"),
    "优先刷牌天赋，其次给经济给能量的，回血保血的天赋也行": (
        "Card-rolling Talents first, then economy and Energy; healing and HP-saving Talents also work",
        "Utamakan Talent refresh kartu, lalu ekonomi dan Energy; Talent pemulihan dan penjaga HP juga boleh"),
    "优先选择增加经验，能量以及等级的天赋": (
        "Prefer Talents that add EXP, Energy and Levels",
        "Utamakan Talent yang menambah EXP, Energy, dan Level"),
    "刻舟减蓝必选，复印机加快阵容成形速度，防御/生存类天赋也可选择": (
        "Mana Reduction is a must, Copier speeds up the Lineup, and defense or survival Talents work too",
        "Mana Reduction wajib, Copier mempercepat Lineup terbentuk, dan Talent pertahanan atau bertahan"
        " hidup juga boleh"),
    "古币相关天赋均可": ("Any Ancient Coin Talent works", "Talent Ancient Coin apa pun boleh"),
    "古币类优先": ("Ancient Coin Talents first", "Utamakan Talent Ancient Coin"),
    "大河专属天赋基本都可以选择，破败神威这类提升普攻输出的天赋也可以选。": (
        "Almost any Riverlands Exclusive Talent works, and Talents that boost Basic Attack damage, such as"
        " Divine Might of Ruin, are fine too.",
        "Hampir semua Exclusive Talent Riverlands bisa dipilih, dan Talent yang menaikkan damage Basic"
        " Attack seperti Divine Might of Ruin juga boleh."),
    "天赋推荐古币相关，其次是点兵点将、全军列阵或援军帮助阵容成型。装备天赋推荐机器头>魂灭灵冠>百锻刀>驱雷>青莲剑谱。": (
        "Take Ancient Coin Talents first, then Drafting Troops, Full Army Formation or Reinforcements to"
        " complete the Lineup. Equipment Talents: Robot Head > Soul-Destroying Crown > Hundred-Forged Blade"
        " > Thunder Drive > Green Lotus Sword Manual.",
        "Utamakan Talent Ancient Coin, lalu Drafting Troops, Full Army Formation, atau Reinforcements untuk"
        " melengkapi Lineup. Talent Equipment: Robot Head > Soul-Destroying Crown > Hundred-Forged Blade >"
        " Thunder Drive > Green Lotus Sword Manual."),
    "天赋的选择我们只看三点给牌给等级或者给钱 ，你一定要看这波的对手去选择天赋选择能打的过的而不要选择更好的 ！": (
        "For Talents, look at three things only: cards, Levels or economy. Always pick the Talent based on"
        " this Round's opponents: choose what lets you beat them, not what looks better!",
        "Untuk Talent, lihat tiga hal saja: kartu, Level, atau ekonomi. Selalu pilih Talent berdasarkan"
        " lawan di Ronde ini: pilih yang bisa mengalahkan mereka, bukan yang terlihat lebih bagus!"),
    "成年礼，大河最好天赋，用过才知道。\n同心协力前期战力暴涨；\n点兵点将，全员觉醒神器；\n其他推荐：紧急救援；灵祭升华等。": (
        "Coming of Age: the best Riverlands Talent; try it and you'll see.\nConcerted Effort: a huge early"
        " power spike;\nDrafting Troops: Awakens the whole team, a must-have;\nAlso good: Emergency Rescue,"
        " Spirit Sacrifice Sublimation, etc.",
        "Coming of Age: Talent Riverlands terbaik; coba sendiri dan kamu akan tahu.\nConcerted Effort:"
        " kekuatan melonjak di awal;\nDrafting Troops: semua Hero Awaken, wajib punya;\nLainnya: Emergency"
        " Rescue, Spirit Sacrifice Sublimation, dll."),
    "拿可以帮我们找体系牌的天赋；升格无敌，拿到就能夺冠！": (
        "Take Talents that help find your core cards; Ascension is unbeatable: get it and you win!",
        "Ambil Talent yang membantu mencari kartu inti; Ascension tak tertandingi: dapatkan dan kamu juara!"),
    "拿经济天赋，帮助我们快速升级": ("Take economy Talents to level up fast", "Ambil Talent ekonomi agar cepat naik level"),
    "搜牌和血量类天赋对这套构筑都很关键，看到必拿。": (
        "Card-search and HP Talents are key to this build: take them on sight.",
        "Talent pencari kartu dan HP sangat penting untuk build ini: langsung ambil saat terlihat."),
    "有给图腾的天赋必拿。\n【无限进步】和【泉水】提供经济和血量。\n【护命灵珠】是海月神器，提供护盾和伤害加成。": (
        "Always take Talents that give Totems.\n【Infinite Progress】 and 【Fountain】 provide economy and"
        " HP.\n【Life-Saving Bead】 is Haya's best Artifact, granting a Shield and bonus damage.",
        "Selalu ambil Talent yang memberi Totem.\n【Infinite Progress】 dan 【Air Mancur】 memberi ekonomi dan"
        " HP.\n【Life-Saving Bead】 adalah Artifact terbaik Haya, memberi Shield dan bonus damage."),
    "看到必拿！": ("Take it on sight!", "Lihat, langsung ambil!"),
    "经济类和人口天赋": ("Economy and Population Talents", "Talent ekonomi dan Populasi"),
    "给装备的牌优先选择": ("Prefer cards that give Equipment", "Utamakan kartu yang memberi Equipment"),
    "能拿五阶英雄的天赋都可以拿\n以防后期对手卡海月": (
        "Any Talent that gives Tier 5 Heroes is good\nin case opponents hold Haya late",
        "Talent apa pun yang memberi Hero Tier 5 boleh diambil\nuntuk jaga-jaga lawan menahan Haya di akhir"),
    "贤士登门提高找牌效率，春风化雨提供高频合成效率，意外之财等放大合成收益的均可拿。": (
        "Sage's Arrival finds cards faster, Spring Rain keeps Combines frequent, and anything that boosts"
        " Combine rewards, such as Windfall, is worth taking.",
        "Sage's Arrival mempercepat pencarian kartu, Spring Rain membuat Combine lebih sering, dan apa pun"
        " yang memperbesar hasil Combine seperti Windfall layak diambil."),
    "贤士登门：芈月嬴政免费送。\n春风化雨：双倍的贤士登门，拿到基本吃了。\n点兵点将：全员觉醒。\n其他天赋：紧急救援/拾荒者等": (
        "Sage's Arrival: Mi Yue and Ying Zheng for free.\nSpring Rain: a double Sage's Arrival; get it and"
        " you've basically won.\nDrafting Troops: the whole team Awakens.\nOthers: Emergency Rescue, Scavenger, etc.",
        "Sage's Arrival: Mi Yue dan Ying Zheng gratis.\nSpring Rain: Sage's Arrival ganda; dapatkan dan kamu"
        " hampir pasti menang.\nDrafting Troops: semua Hero Awaken.\nLainnya: Emergency Rescue, Scavenger, dll."),
    "身外身吃鸡天赋，一个响指sss级棱彩天赋更快找牌，这里只能选择三个天赋，更过天赋推荐——抖音搜肝帝看攻略": (
        "Body Double is a winning Talent, and A Snap, an SSS-grade Prismatic Talent, finds cards faster."
        " Only three Talents fit here; for more, search Gandi on Douyin for the guide",
        "Body Double adalah Talent kemenangan, dan A Snap, Talent Prismatic kelas SSS, mencari kartu lebih"
        " cepat. Hanya tiga Talent muat di sini; untuk rekomendasi lain, cari Gandi di Douyin untuk panduannya"),
    "这三个天赋是优先级的。镜像迷离是最优的，不仅把对面大哥偷过来，还偷对面大哥的等级，甚至面对同行降维打击": (
        "These three Talents are priorities. Mirror Illusion is the best: it steals the enemy's carry along"
        " with its Levels, crushing even players on the same Lineup",
        "Tiga Talent ini prioritas. Mirror Illusion yang terbaik: mencuri carry lawan beserta Level-nya,"
        " bahkan menghancurkan pemain dengan Lineup yang sama"),
    "逐鹿 神级天赋": ("Zhulu Plateau god-tier Talent", "Talent kelas dewa Zhulu Plateau"),
    "逐鹿神级天赋，看到就点，不用犹豫": (
        "Zhulu Plateau's god-tier Talent: pick it the moment you see it, no hesitation",
        "Talent kelas dewa Zhulu Plateau: langsung pilih saat terlihat, tanpa ragu"),

    # ResSeasonAILineupDataBin: LineupDesc (a row field, not inside the code)
    "三分英雄登场提升等级，公孙离吸等级造成超高输出": (
        "Three Kingdoms Heroes gain Levels on Deploy, and Arli absorbs Levels for huge damage",
        "Hero Three Kingdoms naik Level saat Deploy, dan Arli menyerap Level untuk damage sangat besar"),
    "以培养阿科米亚核心为主的阵容，操作简单，凑齐阵容英雄后全员自动成长": (
        "A Lineup built around growing the Arcomia Core. Easy to play: once its Heroes are assembled, the"
        " whole team grows on its own.",
        "Lineup yang berfokus membesarkan Arcomia Core. Mudah dimainkan: setelah Hero Lineup lengkap,"
        " seluruh tim tumbuh sendiri."),
    "以培养阿科米亚核心为主的阵容，操作简单，凑齐阵容英雄后全员自动成长。": (
        "A Lineup built around growing the Arcomia Core. Easy to play: once its Heroes are assembled, the whole team"
        " grows on its own.",
        "Lineup yang berfokus membesarkan Arcomia Core. Mudah dimainkan: setelah Hero Lineup lengkap, seluruh tim"
        " tumbuh sendiri."),
    "以敖隐为核心输出的阵容，操作简单，凑齐阵容英雄后全员自动成长": (
        "A Lineup with Ao'yin as the core damage dealer. Easy to play: once its Heroes are assembled, the"
        " whole team grows on its own.",
        "Lineup dengan Ao'yin sebagai damage dealer inti. Mudah dimainkan: setelah Hero Lineup lengkap,"
        " seluruh tim tumbuh sendiri."),
    "以敖隐为核心输出的阵容，操作简单，凑齐阵容英雄后全员自动成长。": (
        "A Lineup with Ao'yin as the core damage dealer. Easy to play: once its Heroes are assembled, the whole team"
        " grows on its own.",
        "Lineup dengan Ao'yin sebagai damage dealer inti. Mudah dimainkan: setelah Hero Lineup lengkap, seluruh tim"
        " tumbuh sendiri."),
    "以李信为单核的阵容，前期需要快速升级找到李信，后期强力": (
        "A single-carry Lineup around Li Xin. Level up fast early to find him; strong late.",
        "Lineup dengan Li Xin sebagai carry tunggal. Naik level cepat di awal untuk menemukannya; kuat di akhir."),
    "以李信为单核的阵容，前期需要快速升级找到李信，后期强力。": (
        "A single-carry Lineup around Li Xin. Level up fast early to find him; strong late.",
        "Lineup dengan Li Xin sebagai carry tunggal. Naik level cepat di awal untuk menemukannya; kuat di akhir."),
    "以百里玄策为单核的阵容，随着百里玄策的等级提升，后期非常强力": (
        "A single-carry Lineup around Xuance. As his Level rises, it becomes very strong late.",
        "Lineup dengan Xuance sebagai carry tunggal. Seiring Level-nya naik, Lineup ini sangat kuat di akhir."),
    "以百里玄策为单核的阵容，随着百里玄策的等级提升，后期非常强力。": (
        "A single-carry Lineup around Xuance. As his Level rises, it becomes very strong late.",
        "Lineup dengan Xuance sebagai carry tunggal. Seiring Level-nya naik, Lineup ini sangat kuat di akhir."),
    "伞给干将，前期养干将蹭蹭加等级，后期遗志找海月": (
        "The umbrella goes to Gan, who gains Levels fast early; late, use Last Will to find Haya",
        "Payung untuk Gan, yang cepat naik Level di awal; di akhir, gunakan Last Will untuk mencari Haya"),
    "全低阶英雄，前期操作简单，后期需要转型，有一定运营难度。": (
        "All low-Tier Heroes. Easy early on, but it must transition late, which takes some management.",
        "Semua Hero Tier rendah. Mudah di awal, tetapi perlu transisi di akhir, yang butuh sedikit pengelolaan."),
    "利用镜像牌不断合成3阶英雄，群体升级": (
        "Use Mirror cards to keep Combining Tier 3 Heroes for team-wide Level-ups",
        "Gunakan kartu Mirror untuk terus meng-Combine Hero Tier 3 agar seluruh tim naik level"),
    "前期多上英雄连胜，棋手香香也能打出超高伤害~": (
        "Field many Heroes early for a win streak; Chessplayer Xiangxiang can deal huge damage too~",
        "Pasang banyak Hero di awal untuk win streak; Chessplayer Xiangxiang juga bisa memberi damage sangat besar~"),
    "嬴律的技能打出1-3阶英雄可额外加等级，配合低阶大河英雄易连胜": (
        "Ying Lu's Skill adds Levels for each Tier 1-3 Hero played; with low-Tier Riverlands Heroes, win"
        " streaks come easily",
        "Skill Ying Lu menambah Level untuk setiap Hero Tier 1-3 yang dimainkan; dengan Hero Riverlands Tier"
        " rendah, win streak mudah didapat"),
    "嬴政无限释放技能，全屏大招爽感拉满": (
        "Ying Zheng casts Skills endlessly: board-wide Ultimates for maximum thrills",
        "Ying Zheng memakai Skill tanpa batas: Ultimate di seluruh papan, sangat memuaskan"),
    "小妲己的技能提供免费刷新很适配倒转阵容，难度高，不建议新手使用": (
        "Little Daji's Skill gives free Refreshes, which suits Reversal Lineups. Hard: not recommended for"
        " new players",
        "Skill Little Daji memberi Refresh gratis, cocok untuk Lineup Reversal. Sulit: tidak disarankan"
        " untuk pemain baru"),
    "小菟每回合稳定提升等级，越到后期越强！司空震裴擒虎双C": (
        "Little Rabbit raises Levels steadily every Round and grows stronger late! Sikong Zhen and Pei as"
        " twin carries",
        "Little Rabbit menaikkan Level dengan stabil setiap Ronde dan makin kuat di akhir! Sikong Zhen dan"
        " Pei sebagai carry ganda"),
    "小菟每回合稳定提升等级，越到后期越强！艾琳可以溜各种近战英雄": (
        "Little Rabbit raises Levels steadily every Round and grows stronger late! Erin can kite all kinds"
        " of melee Heroes",
        "Little Rabbit menaikkan Level dengan stabil setiap Ronde dan makin kuat di akhir! Erin bisa"
        " men-kite berbagai Hero melee"),
    "廉颇释放技能产生护盾，搭配扁鹊炸盾产生伤害": (
        "Lian Po's Skill creates a Shield, and Dr Bian bursts it for damage",
        "Skill Lian Po membuat Shield, dan Dr Bian meledakkannya untuk damage"),
    "操作简单，运营思路简单，只需要合成就能全员成长": (
        "Easy to play with a simple game plan: just Combine and the whole team grows.",
        "Mudah dimainkan dengan rencana permainan simpel: cukup Combine dan seluruh tim tumbuh."),
    "操作简单，运营思路简单，只需要合成就能全员成长。": (
        "Easy to play with a simple game plan: just Combine and the whole team grows.",
        "Mudah dimainkan dengan rencana permainan simpel: cukup Combine dan seluruh tim tumbuh."),
    "敖隐和东皇搭配3图腾英雄，战斗中持续提升等级": (
        "Ao'yin and Donghuang with 3 Totem Heroes keep gaining Levels in battle",
        "Ao'yin dan Donghuang bersama 3 Hero Totem terus naik Level dalam pertempuran"),
    "昭君的技能可以把1阶英雄变为5阶，不怕卡牌，稳定成长": (
        "Zhaojun's Skill turns Tier 1 Heroes into Tier 5, so blocked cards don't matter and growth is steady",
        "Skill Zhaojun mengubah Hero Tier 1 menjadi Tier 5, jadi kartu yang ditahan lawan tidak masalah dan"
        " pertumbuhan stabil"),
    "朵莉亚大招“泳池”给队友回蓝回血，米莱狄苍无限召唤": (
        "Dolia's Ultimate “pool” restores allies' Mana and HP, and Milady and Chano summon endlessly",
        "Ultimate Dolia “kolam” memulihkan Mana dan HP rekan, dan Milady serta Chano memanggil tanpa batas"),
    "玉环的技能提供免费卡牌很适配倒转阵容，难度高，不建议新手使用": (
        "Yuhuan's Skill gives free cards, which suits Reversal Lineups. Hard: not recommended for new players",
        "Skill Yuhuan memberi kartu gratis, cocok untuk Lineup Reversal. Sulit: tidak disarankan untuk pemain baru"),
    "班叔的机关可以把敌人困住，后排英雄无伤输出": (
        "Uncle Ban's Mechanisms trap enemies so the back-row Heroes deal damage unharmed",
        "Mekanisme Uncle Ban menjebak musuh agar Hero barisan belakang memberi damage tanpa terluka"),
    "用战术牌提升战力，需频繁使用卡牌，推荐有一定游戏经验后再尝试": (
        "Builds power with Tactics Cards and needs frequent card play. Try it once you have some experience",
        "Menambah kekuatan dengan Tactics Card dan perlu sering memainkan kartu. Coba setelah punya sedikit"
        " pengalaman"),
    "花木兰搭配婉儿、程咬金、露娜实现无限复活，越战越强！": (
        "Mulan with Shangguan, Cheng Yaojin and Luna Revives endlessly and grows stronger every fight!",
        "Mulan bersama Shangguan, Cheng Yaojin, dan Luna bisa Revive tanpa batas dan makin kuat setiap pertempuran!"),
    "花木兰搭配婉儿、程咬金、露娜实现无限复活，越战越强！看见同行玩河洛多再选": (
        "Mulan with Shangguan, Cheng Yaojin and Luna Revives endlessly and grows stronger every fight! Pick"
        " it when fewer rivals play Central Plains",
        "Mulan bersama Shangguan, Cheng Yaojin, dan Luna bisa Revive tanpa batas dan makin kuat setiap"
        " pertempuran! Pilih saat sedikit pemain lain memakai Central Plains"),
    "蒙恬10蓝后无限召唤小兵，全屏爆炸伤害": (
        "At 10 Mana, Meng Tian summons minions endlessly for board-wide explosive damage",
        "Dengan 10 Mana, Meng Tian memanggil minion tanpa batas untuk damage ledakan di seluruh papan"),
    "运营简单，但有一定运气成分，快速搜到司空震就能赢，否则容易出局": (
        "Simple to run but luck-dependent: find Sikong Zhen fast and you win, otherwise you are easily knocked out.",
        "Simpel dijalankan tetapi bergantung keberuntungan: cepat dapat Sikong Zhen maka kamu menang, kalau"
        " tidak, mudah tereliminasi."),
    "运营简单，但有一定运气成分，快速搜到司空震就能赢，否则容易出局。": (
        "Simple to run but luck-dependent: find Sikong Zhen fast and you win, otherwise you are easily knocked out.",
        "Simpel dijalankan tetapi bergantung keberuntungan: cepat dapat Sikong Zhen maka kamu menang, kalau tidak,"
        " mudah tereliminasi."),
    "这套阵容凑齐4个英雄后每回合靠棋手技能成长，操作难度低，但找齐英雄有一定运气成分。": (
        "Once its 4 Heroes are assembled, this Lineup grows each Round through the Chessplayer Skill. Easy to play,"
        " though finding all the Heroes takes some luck.",
        "Setelah 4 Hero-nya lengkap, Lineup ini tumbuh setiap Ronde lewat Skill Chessplayer. Mudah dimainkan, meski"
        " butuh sedikit keberuntungan untuk melengkapi Hero-nya."),
    "这套阵容很多英雄为低阶，养成难度低，适合新手使用": (
        "Many of this Lineup's Heroes are low-Tier, so it is easy to build up and suits new players.",
        "Banyak Hero di Lineup ini ber-Tier rendah, jadi mudah dibesarkan dan cocok untuk pemain baru."),
    "这套阵容很多英雄为低阶，养成难度低，适合新手使用。": (
        "Many of this Lineup's Heroes are low-Tier, so it is easy to build up and suits new players.",
        "Banyak Hero di Lineup ini ber-Tier rendah, jadi mudah dibesarkan dan cocok untuk pemain baru."),
    "这是用战术牌提升战力的阵容，操作比较复杂，需频繁使用卡牌，推荐有一定游戏经验后再尝试。": (
        "This Lineup builds power with Tactics Cards. It is fairly complex and needs frequent card play, so try it"
        " once you have some experience.",
        "Lineup ini menambah kekuatan dengan Tactics Card. Cukup rumit dan perlu sering memainkan kartu, jadi coba"
        " setelah punya sedikit pengalaman."),
    "速4找韩信，凑齐阵容每回合挂机成长": (
        "Rush to Lv. 4 for Han Xin; with the Lineup complete, it grows every Round on autopilot",
        "Cepat ke Lv. 4 untuk mencari Han Xin; setelah Lineup lengkap, tumbuh setiap Ronde secara autopilot"),
    "闹闹开局选日落海，中期开技能凑齐日落海英雄，挂机成长": (
        "Naonao opens with Sunset and uses her Skill mid game to gather the Sunset Heroes, then grows on autopilot",
        "Naonao membuka dengan Sunset dan memakai Skill-nya di pertengahan untuk mengumpulkan Hero Sunset,"
        " lalu tumbuh secara autopilot"),
    "闹闹开局选河洛，中期开技能帮助找到花木兰": (
        "Naonao opens with Central Plains and uses her Skill mid game to help find Mulan",
        "Naonao membuka dengan Central Plains dan memakai Skill-nya di pertengahan untuk membantu mencari Mulan"),
    "阵容构筑简单，合成就能一直升级，但与棋手适配度一般，仅推荐其他阵容禁用时选择": (
        "Simple to build: just Combine to keep leveling up. It fits the Chessplayer only so-so, so pick it"
        " only when other Lineups are banned",
        "Mudah disusun: cukup Combine untuk terus naik level. Kecocokannya dengan Chessplayer biasa saja,"
        " jadi pilih hanya saat Lineup lain di-ban"),
    "阿离的伞给守约，后期守约一枪一个后排": (
        "Arli's umbrella goes to Shouyue; late, Shouyue picks off a back-liner with every shot",
        "Payung Arli untuk Shouyue; di akhir, Shouyue menumbangkan satu barisan belakang di setiap tembakan"),
    "飞行器既能攻击敌人，又能增加英雄等级，全力养海月，后期一打多": (
        "The Aircraft attacks enemies and raises Hero Levels: go all in on Haya, who takes on several enemies late",
        "Pesawat menyerang musuh dan menaikkan Level Hero: fokus besarkan Haya, yang bisa melawan banyak"
        " musuh di akhir"),
    "高风险、高上限，通过不断打出登场牌提升战力，推荐有一定游戏经验再尝试": (
        "High risk, high ceiling: keep playing Deploy cards to build power. Try it once you have some experience",
        "Risiko tinggi, batas atas tinggi: terus mainkan kartu Deploy untuk menambah kekuatan. Coba setelah"
        " punya sedikit pengalaman"),
    "高风险、高上限，通过不断打出登场牌提升战力，推荐有一定游戏经验再尝试。": (
        "High risk, high ceiling: keep playing Deploy cards to build power. Try it once you have some experience.",
        "Risiko tinggi, batas atas tinggi: terus mainkan kartu Deploy untuk menambah kekuatan. Coba setelah"
        " punya sedikit pengalaman."),

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
