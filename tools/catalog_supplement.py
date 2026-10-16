"""Translations for text the game added after the catalog was built, merged into the catalog as it loads.

The catalog is the PC pipeline's file and is not edited here (`AGENTS.md`), so data updates that add or
reword strings in tables the catalog already covers leave those rows Chinese until upstream catches up.
Game data 1.5.0.1 and 1.6.0.1 added about 1200 such strings to package `1`: an achievement-title system
whose titles come in numbered tiers (`完美橱窗(二)`), four weekly leaderboards ranked 1 to 100, the King of
Kings sub-account, the Line Puppy event, and card texts whose numbers changed. `apply` fills them in.

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
    "<color=#FFE897>你的召唤单位</color>等级+6。每回合开始时，再+6。": (
        "<color=#FFE897>Your summoned units</color> gain +6 levels. At the start of each Round, gain another +6.",
        "<color=#FFE897>Unit yang kau panggil</color> mendapatkan +6 level. Pada awal setiap Ronde, mendapatkan +6 lagi."),
    "你的单位每合计进行25次普攻，所有己方英雄等级永久+2。": (
        "Every 25 total basic attacks performed by your units, all allied Hero levels permanently +2.",
        "Setiap total 25 serangan dasar yang dilakukan unit kamu, level semua Hero ally +2 secara permanen."),
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
