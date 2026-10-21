"""Translations for text the game added after the catalog was built, merged into the catalog as it loads.

The catalog is the PC pipeline's file and is not edited here (`AGENTS.md`), so data updates that add or
reword strings in tables the catalog already covers leave those rows Chinese until upstream catches up.
Game data 1.5.0.1 and 1.6.0.1 added about 1200 such strings to package `1`: an achievement-title system
whose titles come in numbered tiers (`完美橱窗(二)`), four weekly leaderboards ranked 1 to 100, the King of
Kings sub-account, the Line Puppy event, and card texts whose numbers changed. `apply` fills them in.
The official lineups' strategy text is here too: it lives in config bins the catalog does not cover, inside
their share codes, for the share-code pass to write.
`derived` adds the short forms the card-pack covers label each cover with (`逆天改命卡包`, `河洛-李白`),
whose wording the catalog carries only inside its own longer strings; that bin itself was withdrawn.

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
        "Memainkan 4 Hero Tier 3 atau lebih rendah memberi Kartu Treasure. Lineup ini semuanya Hero Tier 1-3, jadi"
        " cocok dipasangkan dengan Marco."),
    "打出4张3阶及以下英雄能获得宝藏牌，这套阵容前期低阶英雄多，比较适合搭配马可。": (
        "Playing 4 Heroes of Tier 3 or lower grants a Treasure Card. This Lineup has many low-Tier Heroes early on, so"
        " it pairs well with Marco.",
        "Memainkan 4 Hero Tier 3 atau lebih rendah memberi Kartu Treasure. Lineup ini punya banyak Hero Tier rendah"
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
        "Lineup ini terutama membesarkan Hero dengan memakai Effect Card untuk memicu Efek Kartu Mi Yue. Little Daji"
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
