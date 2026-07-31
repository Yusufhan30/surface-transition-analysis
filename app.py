"""
Zemin Geçiş Hızı Analizi — ATP 2021–2025
========================================
Soru: Bir tenisçi zemin değiştirdiğinde, yeni zemindeki ilk maçlarında
      o zemindeki normal seviyesinin altında mı oynuyor?

Bölüm  1  Veri çekimi
Bölüm  2  Temizlik
Bölüm  3  Uzun format
Bölüm  4  Doğrulama
Bölüm  5  Rezidüalizasyon (rakip / zemin / tur / turnuva düzeltmesi)
Bölüm  6  Blok tespiti
Bölüm  7  Geçiş cezası — betimsel testler
Bölüm  8  Görselleştirme  →  ayrı dosyada: viz.py
Bölüm  9  İstatistiksel modelleme (H1, H2, H3)
Bölüm 10  Robustluk kontrolleri

Veri: Tennismylife/TML-Database (CC BY-NC-SA)
      Köken: Jeff Sackmann / Tennis Abstract
"""

import warnings
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from pathlib import Path
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder

warnings.filterwarnings("ignore", category=FutureWarning)


BASE_URL = "https://raw.githubusercontent.com/Tennismylife/TML-Database/master/{}.csv"
YILLAR = [2021, 2022, 2023, 2024, 2025]

VERI = Path(__file__).parent / "data"
VERI.mkdir(parents=True, exist_ok=True)

HAM_DOSYA = VERI / "atp_ham.parquet"
TEMIZ_DOSYA = VERI / "atp_temiz.parquet"
UZUN_DOSYA = VERI / "atp_uzun.parquet"
REZIDU_DOSYA = VERI / "atp_rezidu.parquet"
BLOK_DOSYA = VERI / "atp_bloklar.parquet"

ROBUSTLUK_KOS = True    


GECERLI_SEVIYE = {"G", "M", "250", "500", "F"}
GECERLI_ZEMIN = {"Clay", "Grass", "Hard"}
IPTAL_ISARETLERI = ["RET", "W/O", "DEF"]
IST_SUTUNLARI = ["w_svpt", "w_1stWon", "w_2ndWon",
                 "l_svpt", "l_1stWon", "l_2ndWon"]

TUR_SIRA = {"R128": 1, "RR": 2, "R64": 2, "R32": 3,
            "R16": 4, "QF": 5, "SF": 6, "BR": 6, "F": 7}

ORTAK_SUTUNLAR = ["tourney_id", "tourney_name", "tourney_date", "surface",
                  "tourney_level", "indoor", "round", "match_num",
                  "best_of", "minutes", "yil"]

# --- model ---
ALPHA = 5.0
TEMEL = ["oyuncu_id", "rakip_id", "surface", "round"]
TURNUVA = TEMEL + ["turnuva"]

# --- blok ---
MAKS_BOSLUK_GUN = 60    # bundan uzun ara = yeni blok (sakatlık / sezon arası)
MIN_BLOK_BOY = 5        # 2 uyum + en az 3 baz maçı
K = 2                   # uyum penceresi: bloğun ilk kaç maçı


# ======================
# BÖLÜM 1 — VERİ ÇEKİMİ  
# ======================

def veri_getir(yeniden_indir=False):
    if HAM_DOSYA.exists() and not yeniden_indir:
        ham = pd.read_parquet(HAM_DOSYA)
        print(f"[1] Diskten okundu: {len(ham):,} maç")
        return ham

    print("[1] İndiriliyor...")
    parcalar = []
    for y in YILLAR:
        d = pd.read_csv(BASE_URL.format(y))
        d["yil"] = y
        print(f"      {y}: {len(d):>6,} maç")
        parcalar.append(d)

    ham = pd.concat(parcalar, ignore_index=True)
    ham.to_parquet(HAM_DOSYA)
    print(f"    Toplam {len(ham):,} maç → {HAM_DOSYA.name}")
    return ham


# =================================
# BÖLÜM 2 — TEMİZLİK
# =================================

def temizle(ham):
    df = ham.copy()
    n0 = len(df)
    rapor = {}

    df = df[df.tourney_level.astype(str).isin(GECERLI_SEVIYE)]
    rapor["Takım/gösteri + Davis Cup + Olimpiyat"] = n0 - len(df)
    n = len(df)

    df = df[df.surface.isin(GECERLI_ZEMIN)]
    rapor["Zemin bilgisi eksik"] = n - len(df)
    n = len(df)

    maske = df.score.astype(str).str.contains(
        "|".join(IPTAL_ISARETLERI), case=False, na=False)
    df = df[~maske]
    rapor["Yarıda kalan maç (RET/W-O/DEF)"] = n - len(df)
    n = len(df)

    df = df.dropna(subset=IST_SUTUNLARI)
    rapor["Servis istatistiği eksik"] = n - len(df)
    n = len(df)

    df = df[(df.w_svpt > 20) & (df.l_svpt > 20)]
    rapor["Anormal kısa maç"] = n - len(df)

    df = df.reset_index(drop=True)

    print(f"\n[2] Temizlik: {n0:,} → {len(df):,}  (%{len(df)/n0*100:.1f} kaldı)")
    for k, v in rapor.items():
        print(f"      {k:<40} {v:>6,} satır  (%{v/n0*100:.1f})")

    df.to_parquet(TEMIZ_DOSYA)
    return df, rapor


# ============================================================
# BÖLÜM 3 — UZUN FORMAT  (1 maç → 2 satır: her oyuncunun perspektifi)
# ============================================================

def _taraf(df, ben, rakip, ek_ben, ek_rakip):
    """Maçın tek bir oyuncu perspektifini çıkarır.

    ben / rakip       -> biyografik sütun öneki (winner_name, loser_rank ...)
    ek_ben / ek_rakip -> istatistik sütun öneki (w_svpt, l_1stWon ...)
    """
    d = df[ORTAK_SUTUNLAR].copy()

    d["oyuncu_id"] = df[f"{ben}_id"]
    d["oyuncu_ad"] = df[f"{ben}_name"]
    d["rakip_id"] = df[f"{rakip}_id"]
    d["rakip_ad"] = df[f"{rakip}_name"]
    d["oyuncu_sira"] = df[f"{ben}_rank"]
    d["rakip_sira"] = df[f"{rakip}_rank"]
    d["kazandi"] = 1 if ben == "winner" else 0

    # İADE
    d["iade_toplam"] = df[f"{ek_rakip}_svpt"]
    d["iade_kazanc"] = (df[f"{ek_rakip}_svpt"]
                        - df[f"{ek_rakip}_1stWon"]
                        - df[f"{ek_rakip}_2ndWon"])

    # SERVİS
    d["srv_toplam"] = df[f"{ek_ben}_svpt"]
    d["srv_kazanc"] = df[f"{ek_ben}_1stWon"] + df[f"{ek_ben}_2ndWon"]

    return d


def uzun_formata_cevir(df):
    uzun = pd.concat([
        _taraf(df, "winner", "loser", "w", "l"),
        _taraf(df, "loser", "winner", "l", "w"),
    ], ignore_index=True)

    uzun["tur_sira"] = uzun["round"].map(TUR_SIRA).fillna(3).astype(int)
    uzun["tarih"] = pd.to_datetime(uzun.tourney_date,
                                   format="%Y%m%d", errors="coerce")
    uzun["rpw"] = uzun.iade_kazanc / uzun.iade_toplam
    uzun["spw"] = uzun.srv_kazanc / uzun.srv_toplam

    # turnuva kimliği: aynı turnuvanın farklı yılları ayrı kort sayılır
    uzun["turnuva"] = uzun.tourney_name.astype(str) + "_" + uzun.yil.astype(str)

    uzun = uzun.sort_values(["oyuncu_id", "tarih", "tur_sira", "match_num"])
    uzun = uzun.reset_index(drop=True)

    print(f"\n[3] Uzun format: {len(uzun):,} satır")
    uzun.to_parquet(UZUN_DOSYA)
    return uzun


# ====================
# BÖLÜM 4 — DOĞRULAMA  
# =====================

def dogrula(df, uzun):
    print("\n[4] Doğrulama")
    sonuclar = []

    sonuclar.append(("Satır sayısı 2 katı", len(uzun) == 2 * len(df)))

    toplam = uzun.rpw.mean() + uzun.spw.mean()
    sonuclar.append((f"RPW + SPW = 1  ({toplam:.4f})", abs(toplam - 1) < 1e-6))

    z = uzun.groupby("surface").rpw.mean()
    sonuclar.append(("Zemin sırası Clay > Hard > Grass",
                     z["Clay"] > z["Hard"] > z["Grass"]))

    w = uzun[(uzun.tourney_name.str.contains("Wimbledon", na=False))
             & (uzun["round"] == "F") & (uzun.yil == 2025)]
    kazanan = w[w.kazandi == 1].iloc[0]
    sonuclar.append((f"Wimbledon 2025 F — {kazanan.oyuncu_ad} RPW={kazanan.rpw:.4f}",
                     abs(kazanan.rpw - 0.3636) < 0.001))

    for ad, gecti in sonuclar:
        print(f"      {'PASS' if gecti else 'FAIL'}  {ad}")

    print("\n      Zemin bazında ortalama iade yüzdesi:")
    ozet = uzun.groupby("surface").rpw.agg(
        ortalama="mean", std="std", mac="count").round(4)
    print(ozet.to_string().replace("\n", "\n      "))

    return all(gecti for _, gecti in sonuclar)


# =========================
# BÖLÜM 5 — REZİDÜALİZASYON
# =========================

def rezidu_uret(u, kolonlar, hedef, agirlik, cikti_ad, detay=False, sessiz=False):
    """Ham yüzdeden rakip / zemin / tur (ve istenirse turnuva) etkisini çıkarır.

    Model:  hedef = ortalama + kendi_becerim + rakibin_etkisi + bağlam
    Rezidü = gözlenen − tahmin = "beklenenden ne kadar saptım"
    """
    X = OneHotEncoder(handle_unknown="ignore").fit_transform(u[kolonlar].astype(str))
    model = Ridge(alpha=ALPHA, fit_intercept=True)
    model.fit(X, u[hedef].values, sample_weight=u[agirlik].values)

    r = u[hedef] - model.predict(X)
    r = r - r.mean()
    u[cikti_ad] = r.groupby(u.surface).transform(lambda s: s / s.std())

    if not sessiz:
        r2 = model.score(X, u[hedef].values, sample_weight=u[agirlik].values)
        print(f"      {cikti_ad:<16} R² = {r2:.3f}   ({len(kolonlar)} kontrol değişkeni)")

    if detay:
        print("      Tur bazında ham → düzeltilmiş:")
        kars = u.groupby("tur_sira").agg(ham=(hedef, "mean"),
                                         duzeltilmis=(cikti_ad, "mean"))
        print(kars.round(4).to_string().replace("\n", "\n      "))
    return u


# ==========================
# BÖLÜM 6 — BLOK TESPİTİ
# ==========================

def bloklari_bul(d):
    """Her oyuncunun maçlarını kronolojik dizip zemin bloklarına ayırır."""
    d = d.sort_values(["oyuncu_id", "tarih", "tur_sira", "match_num"])
    d = d.reset_index(drop=True)

    zemin_degisti = d.surface != d.groupby("oyuncu_id").surface.shift()
    uzun_ara = d.groupby("oyuncu_id").tarih.diff().dt.days > MAKS_BOSLUK_GUN
    yeni_oyuncu = d.oyuncu_id != d.oyuncu_id.shift()

    d["blok_id"] = (zemin_degisti | uzun_ara | yeni_oyuncu).cumsum()
    d["blok_sira"] = d.groupby("blok_id").cumcount() + 1
    d["blok_boy"] = d.groupby("blok_id").blok_sira.transform("max")

    ozet = d.groupby("blok_id").agg(oyuncu_id=("oyuncu_id", "first"),
                                    zemin=("surface", "first")).reset_index()
    ozet["onceki_zemin"] = ozet.groupby("oyuncu_id").zemin.shift()
    ozet["gecis_tipi"] = ozet.onceki_zemin + "→" + ozet.zemin
    d = d.merge(ozet[["blok_id", "onceki_zemin", "gecis_tipi"]], on="blok_id")

    print(f"\n[6] Blok tespiti: {d.blok_id.nunique():,} ham blok")
    return d


def gecerli_bloklar(d):
    """Analize uygun blokları süzer ve uyum / baz fazlarını işaretler."""
    g = d[(d.blok_boy >= MIN_BLOK_BOY)
          & d.onceki_zemin.notna()            # sezonun ilk bloğu değil
          & (d.onceki_zemin != d.surface)     # gerçek zemin değişimi
          ].copy()

    g["faz"] = np.where(g.blok_sira <= K, "uyum", "baz")

    print(f"      Geçerli: {g.blok_id.nunique():,} blok · "
          f"{len(g):,} maç · {g.oyuncu_id.nunique():,} oyuncu")
    for tip, n in g.groupby("gecis_tipi").blok_id.nunique().sort_values(ascending=False).items():
        print(f"        {tip:<14} {n:>4} blok")

    g.to_parquet(BLOK_DOSYA)
    return g


def blok_ornegi(d, oyuncu, yil):
    """Gözle doğrulama: bir oyuncunun bir sezondaki blokları."""
    a = d[(d.oyuncu_ad == oyuncu) & (d.yil == yil)]
    print(f"\n      {oyuncu} — {yil} blokları:")
    for _, gr in a.groupby("blok_id"):
        print(f"        {gr.surface.iloc[0]:<6} | {gr.blok_boy.iloc[0]:>2} maç | "
              f"{gr.tarih.min().date()} → {gr.tarih.max().date()} | "
              f"önceki: {str(gr.onceki_zemin.iloc[0]):<6} | "
              f"{', '.join(gr.tourney_name.unique()[:3])}")


# ====================================
# BÖLÜM 7 — GEÇİŞ CEZASI (betimsel)
# ====================================

def tp_hesapla(g, sutun):
    """Her blok için: ilk K maçın ortalaması − kalan maçların ortalaması.

    Negatif = geçişte bozulma.  Pozitif = geçişte daha iyi.
    """
    return (g.groupby(["blok_id", "oyuncu_id", "oyuncu_ad", "gecis_tipi"])
             .apply(lambda x: x.loc[x.faz == "uyum", sutun].mean()
                            - x.loc[x.faz == "baz", sutun].mean(),
                    include_groups=False)
             .rename("TP").reset_index())


def test_et(tp, etiket, min_n=20):
    x = tp.TP.dropna()
    p = stats.ttest_1samp(x, 0).pvalue
    print(f"\n      {etiket}")
    print(f"        GENEL  {x.mean():+.4f} SD   p={p:.4f}   n={len(x):,} blok")

    for tip, gr in tp.groupby("gecis_tipi"):
        v = gr.TP.dropna()
        if len(v) < min_n:
            print(f"        {tip:<13} {v.mean():+.4f}   n={len(v):>3}  (yetersiz örneklem)")
            continue
        ci = stats.bootstrap((v.values,), np.mean, n_resamples=3000,
                             random_state=1).confidence_interval
        print(f"        {tip:<13} {v.mean():+.4f}  [{ci.low:+.3f}, {ci.high:+.3f}]  "
              f"p={stats.ttest_1samp(v, 0).pvalue:.4f}  n={len(v):>3}")
    return x.mean(), p


# ============================================================
# BÖLÜM 9 — İSTATİSTİKSEL MODELLEME
# ============================================================
# Not: statsmodels MixedLM denendi; oyuncu varyansı parametre uzayının
# sınırında (sıfırda) tahmin edildiği için Hessian tekilleşiyor ve standart
# hatalar patlıyor (SH ≈ 3.4 milyon). Varyansın sıfır çıkması H3'ün cevabının
# kendisi. Bu yüzden blok düzeyinde OLS + oyuncu bazında kümelenmiş standart
# hata kullanıyoruz: aynı bağımlılığı hesaba katar, sayısal olarak kararlıdır.

def blok_tp(g, sutun):
    """Blok düzeyinde geçiş cezası + oyuncu ve tarih bilgisi."""
    t = (g.groupby(["blok_id", "oyuncu_id", "oyuncu_ad", "gecis"])
          .apply(lambda x: x.loc[x.uyum == 1, sutun].mean()
                         - x.loc[x.uyum == 0, sutun].mean(),
                 include_groups=False)
          .rename("TP").reset_index().dropna())
    return t.merge(g.groupby("blok_id").tarih.min().rename("baslangic"), on="blok_id")


def model_hazirla(gecerli):
    g = gecerli.copy()
    g["uyum"] = (g["faz"] == "uyum").astype(int)
    g["gecis"] = g["gecis_tipi"].str.replace("→", "_")
    return g[g["gecis"] != "Hard_Grass"]      # n=10, model bozuyor


def h1_genel_etki(g):
    print("\n[9] H1 — Genel geçiş etkisi  (oyuncu bazında kümelenmiş SH)")
    print(f"      {'model':<16} {'katsayı':>9} {'SH':>9} {'p':>9}")
    veri = {}
    for sut, ad in [("z_iade", "iade"),
                    ("z_iade_turn", "iade+turnuva"),
                    ("z_servis", "servis"),
                    ("z_servis_turn", "servis+turnuva")]:
        t = blok_tp(g, sut)
        veri[ad] = t
        m = smf.ols("TP ~ 1", t).fit(cov_type="cluster",
                                     cov_kwds={"groups": t["oyuncu_id"]})
        print(f"      {ad:<16} {m.params['Intercept']:+9.4f} "
              f"{m.bse['Intercept']:9.4f} {m.pvalues['Intercept']:9.4f}")
    return veri


def h2_gecis_tipi(t):
    print("\n      H2 — Geçiş tipine göre (turnuva kontrollü iade)")
    m = smf.ols("TP ~ C(gecis) - 1", t).fit(
        cov_type="cluster", cov_kwds={"groups": t["oyuncu_id"]})
    for k in m.params.index:
        ad = k.replace("C(gecis)[", "").replace("]", "").replace("_", "→")
        yildiz = "*" if m.pvalues[k] < 0.05 else " "
        print(f"        {ad:<14} {m.params[k]:+.4f}  SH={m.bse[k]:.4f}  "
              f"p={m.pvalues[k]:.4f} {yildiz}")
    return m


def h3_guvenilirlik(veri, kesim="2023-07-01", min_blok=4):
    """Aynı oyuncunun iki ayrı dönemdeki geçiş cezası birbirini tutuyor mu?"""
    print(f"\n      H3 — Dönem-ayrımlı güvenilirlik (kesim: {kesim})")
    for ad, t in veri.items():
        a = t[t.baslangic < kesim].groupby("oyuncu_id").TP.agg(["mean", "size"])
        b = t[t.baslangic >= kesim].groupby("oyuncu_id").TP.agg(["mean", "size"])
        ortak = (a[a["size"] >= min_blok]
                 .join(b[b["size"] >= min_blok], lsuffix="_a", rsuffix="_b", how="inner"))
        r, p = stats.pearsonr(ortak.mean_a, ortak.mean_b)
        print(f"        {ad:<16} n={len(ortak):>3} oyuncu   r={r:+.3f}   p={p:.3f}")


def pratik_birim(uzun, sd_birim=0.10):
    """Standart sapma birimini yüzde puanı ve maç başına puana çevirir."""
    print(f"\n      Pratik karşılık ({sd_birim:.2f} SD ne demek?)")
    for z in ["Clay", "Grass", "Hard"]:
        s = uzun[uzun.surface == z]
        sd = (s.rpw - s.rpw.mean()).std() * 100
        puan = sd_birim * sd / 100 * s.iade_toplam.mean()
        print(f"        {z:<6} {sd_birim*sd:.2f} yüzde puanı = "
              f"maç başına {puan:.2f} iade puanı")


# ============================================================
# BÖLÜM 10 — ROBUSTLUK KONTROLLERİ
# ============================================================

def _tek_varyant(u, sutun, K_=2, MINB=5, BOSLUK=60):
    """Verilen parametrelerle blokları kurup genel ve Clay→Grass etkisini döndürür."""
    d = u.sort_values(["oyuncu_id", "tarih", "tur_sira", "match_num"]).reset_index(drop=True)
    zd = d.surface != d.groupby("oyuncu_id").surface.shift()
    ua = d.groupby("oyuncu_id").tarih.diff().dt.days > BOSLUK
    yo = d.oyuncu_id != d.oyuncu_id.shift()

    d["blok_id"] = (zd | ua | yo).cumsum()
    d["blok_sira"] = d.groupby("blok_id").cumcount() + 1
    d["blok_boy"] = d.groupby("blok_id").blok_sira.transform("max")

    oz = d.groupby("blok_id").agg(oyuncu_id=("oyuncu_id", "first"),
                                  zemin=("surface", "first")).reset_index()
    oz["onceki"] = oz.groupby("oyuncu_id").zemin.shift()
    oz["gecis"] = oz.onceki + "_" + oz.zemin
    d = d.merge(oz[["blok_id", "onceki", "gecis"]], on="blok_id")

    g = d[(d.blok_boy >= MINB) & d.onceki.notna() & (d.onceki != d.surface)].copy()
    g["uyum"] = (g.blok_sira <= K_).astype(int)

    t = (g.groupby(["blok_id", "oyuncu_id", "gecis"])
          .apply(lambda x: x.loc[x.uyum == 1, sutun].mean()
                         - x.loc[x.uyum == 0, sutun].mean(),
                 include_groups=False).rename("TP").reset_index().dropna())

    def fit(df):
        if len(df) < 30:
            return np.nan, np.nan
        m = smf.ols("TP ~ 1", df).fit(cov_type="cluster",
                                      cov_kwds={"groups": df.oyuncu_id})
        return m.params["Intercept"], m.pvalues["Intercept"]

    b, p = fit(t)
    cg = t[t.gecis.str.startswith("Clay") & t.gecis.str.endswith("Grass")]
    cb, cp = fit(cg)
    return len(t), b, p, cb, cp


def robustluk_tablosu(uzun_ham):
    """Parametre ve model seçimlerini tek tek değiştirip sonucu karşılaştırır."""
    global ALPHA
    print("\n[10] Robustluk kontrolleri")
    print(f"      {'varyant':<26} {'blok':>6} {'GENEL':>9} {'p':>7} "
          f"{'Clay→Grass':>11} {'p':>7}")
    print("      " + "-" * 70)

    def satir(ad, n, b, p, cb, cp):
        print(f"      {ad:<26} {n:>6,} {b:+9.4f} {p:>7.3f} {cb:>+11.4f} {cp:>7.3f}")

    # a) blok kuralı varyantları (aynı rezidüller)
    u = rezidu_uret(uzun_ham.copy(), TURNUVA, "rpw", "iade_toplam", "zr", sessiz=True)
    for ad, kw in [("TEMEL (K=2, min=5, 60g)", {}),
                   ("uyum penceresi K=1", {"K_": 1}),
                   ("uyum penceresi K=3", {"K_": 3}),
                   ("min blok boyu = 4", {"MINB": 4}),
                   ("min blok boyu = 6", {"MINB": 6}),
                   ("min blok boyu = 8", {"MINB": 8}),
                   ("boşluk eşiği 45 gün", {"BOSLUK": 45}),
                   ("boşluk eşiği 90 gün", {"BOSLUK": 90})]:
        satir(ad, *_tek_varyant(u, "zr", **kw))

    # b) model varyantları (rezidüller yeniden hesaplanır)
    eski = ALPHA
    for a in (1.0, 20.0):
        ALPHA = a
        uu = rezidu_uret(uzun_ham.copy(), TURNUVA, "rpw", "iade_toplam", "zr", sessiz=True)
        satir(f"ridge alpha = {int(a)}", *_tek_varyant(uu, "zr"))
    ALPHA = eski

    # c) örneklem varyantları
    uu = uzun_ham[uzun_ham.tourney_level.isin(["G", "M"])].copy()
    uu = rezidu_uret(uu, TURNUVA, "rpw", "iade_toplam", "zr", sessiz=True)
    satir("sadece Slam + Masters", *_tek_varyant(uu, "zr"))

    uu = uzun_ham.copy()
    uu["surface"] = np.where(uu.indoor.astype(str).str.upper().str.startswith("I"),
                             uu.surface + "_ic", uu.surface)
    uu = rezidu_uret(uu, TURNUVA, "rpw", "iade_toplam", "zr", sessiz=True)
    satir("indoor ayrı zemin sayılır", *_tek_varyant(uu, "zr"))

    # d) plasebo — servis tarafı, aynı turnuva kontrolüyle
    uu = rezidu_uret(uzun_ham.copy(), TURNUVA, "spw", "srv_toplam", "zr", sessiz=True)
    satir("SERVİS (plasebo)", *_tek_varyant(uu, "zr"))


# ============================================================
# ÇALIŞTIR
# ============================================================

if __name__ == "__main__":

    # --- veri hazırlığı (Bölüm 1-4) ---
    ham = veri_getir()
    temiz, rapor = temizle(ham)
    uzun = uzun_formata_cevir(temiz)
    tamam = dogrula(temiz, uzun)
    print(f"\n      {'TÜM KONTROLLER GEÇTİ' if tamam else 'DİKKAT: kontrol başarısız'}")

    # --- rezidüalizasyon (Bölüm 5): dört model ---
    print("\n[5] Rezidüalizasyon")
    uzun = rezidu_uret(uzun, TEMEL,   "rpw", "iade_toplam", "z_iade", detay=True)
    uzun = rezidu_uret(uzun, TEMEL,   "spw", "srv_toplam",  "z_servis")
    uzun = rezidu_uret(uzun, TURNUVA, "rpw", "iade_toplam", "z_iade_turn")
    uzun = rezidu_uret(uzun, TURNUVA, "spw", "srv_toplam",  "z_servis_turn")
    uzun.to_parquet(REZIDU_DOSYA)

    # --- bloklar (Bölüm 6) ---
    bloklu = bloklari_bul(uzun)
    gecerli = gecerli_bloklar(bloklu)
    blok_ornegi(bloklu, "Carlos Alcaraz", 2024)

    # --- betimsel geçiş cezası (Bölüm 7) ---
    print("\n[7] Geçiş cezası — betimsel")
    test_et(tp_hesapla(gecerli, "z_iade"),        "A) İADE — temel model")
    test_et(tp_hesapla(gecerli, "z_servis"),      "B) SERVİS — plasebo")
    test_et(tp_hesapla(gecerli, "z_iade_turn"),   "C) İADE — turnuva kontrollü")

    # --- modelleme (Bölüm 9) ---
    g_model = model_hazirla(gecerli)
    veri_tp = h1_genel_etki(g_model)
    h2_gecis_tipi(veri_tp["iade+turnuva"])
    h3_guvenilirlik(veri_tp)
    pratik_birim(uzun)

    # --- robustluk (Bölüm 10) ---
    if ROBUSTLUK_KOS:
        robustluk_tablosu(uzun)

    print(f"\n{'=' * 60}")
    print(f"Bitti. Veri çıktıları: {VERI}")
    print("Grafikler için:  python viz.py")