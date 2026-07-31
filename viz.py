"""BÖLÜM 8 — GÖRSELLEŞTİRME (test dosyası)"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import gridspec
from scipy import stats
from pathlib import Path

VERI = Path("data")
GRAFIK = Path("figures")
GRAFIK.mkdir(exist_ok=True)

CLAY, GRASS, HARD = "#B5563A", "#4A7C4E", "#2F6FA8"
VURGU, NOTR, SOLUK = "#B5563A", "#44515C", "#9AA5AD"
ZEMIN_RENK = {"Clay": CLAY, "Grass": GRASS, "Hard": HARD}

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "font.family": "DejaVu Sans", "font.size": 10,
    "axes.edgecolor": "#D5DBDF", "axes.linewidth": 0.8,
    "xtick.color": "#5A6670", "ytick.color": "#5A6670",
    "axes.labelcolor": "#3A444C", "text.color": "#22282D",
    "axes.spines.top": False, "axes.spines.right": False,
})

SIRA = ["Clay→Grass", "Grass→Hard", "Clay→Hard", "Hard→Clay", "Grass→Clay"]
ETIKET = {"Clay→Grass": "Toprak → Çim", "Grass→Hard": "Çim → Sert",
          "Clay→Hard": "Toprak → Sert", "Hard→Clay": "Sert → Toprak",
          "Grass→Clay": "Çim → Toprak"}


def tp_hesapla(g, sutun):
    return (g.groupby(["blok_id", "oyuncu_id", "oyuncu_ad", "gecis_tipi"])
             .apply(lambda x: x.loc[x.faz == "uyum", sutun].mean()
                            - x.loc[x.faz == "baz", sutun].mean(),
                    include_groups=False).rename("TP").reset_index())


def _ci(v):
    ci = stats.bootstrap((v,), np.mean, n_resamples=3000,
                         random_state=1).confidence_interval
    return v.mean(), ci.low, ci.high


# ============================================================
# GRAFİK 1 — Etkinin üç aşamada eriyişi
# ============================================================

def grafik1(g):
    paneller = [
        ("z_iade", "A · İade performansı\n(rakip + tur düzeltmeli)", NOTR),
        ("z_servis", "B · Servis — plasebo testi\n(aynı düzeltme)", SOLUK),
        ("z_iade_turn", "C · İade + turnuva kontrolü\n(hangi kortta oynandığı sabitlendi)", NOTR),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 5.4), sharey=True)

    for ax, (sut, baslik, renk) in zip(axes, paneller):
        tp = tp_hesapla(g, sut)
        for i, tip in enumerate(SIRA):
            v = tp.loc[tp.gecis_tipi == tip, "TP"].dropna().values
            ort, lo, hi = _ci(v)
            anlamli = (lo > 0) or (hi < 0)
            c = VURGU if (tip == "Clay→Grass" and anlamli) else (renk if anlamli else SOLUK)
            ax.plot([lo, hi], [i, i], color=c, lw=2.4, solid_capstyle="round",
                    alpha=1 if anlamli else 0.55)
            ax.plot(ort, i, "o", color=c, ms=8, mec="white", mew=1.4,
                    alpha=1 if anlamli else 0.55, zorder=3)

        ax.axvline(0, color="#98A3AB", lw=1, ls=(0, (4, 3)), zorder=0)
        ax.set_yticks(range(len(SIRA)))
        ax.set_yticklabels([ETIKET[t] for t in SIRA])
        ax.set_title(baslik, fontsize=10.5, loc="left", pad=12, color="#2C353C")
        ax.set_xlim(-0.42, 0.42)
        ax.invert_yaxis()
        ax.grid(axis="x", color="#EDF0F2", lw=0.8)
        ax.set_axisbelow(True)

    axes[1].set_xlabel("Geçiş etkisi (standart sapma)\n← ilk maçlarda daha kötü   |   ilk maçlarda daha iyi →",
                       fontsize=9, labelpad=10)

    fig.suptitle("Zemin geçişinde “uyum cezası” bulduğumu sandım. Bir kontrol değişkeni onu yok etti.",
                 fontsize=13.5, x=0.011, ha="left", y=0.985, weight="bold")
    fig.text(0.011, 0.905,
             "Bloğun ilk 2 maçı ile kalan maçları arasındaki fark · ATP 2021–2025 · "
             "1.441 zemin bloğu · çubuklar %95 bootstrap güven aralığı",
             fontsize=8.6, color="#6C7780")
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    fig.savefig(GRAFIK / "1_etkinin_erimesi.png", dpi=200, bbox_inches="tight")
    print("  ✓ 1_etkinin_erimesi.png")
    plt.close(fig)


# ============================================================
# GRAFİK 2 — Neden? Çim bloğunun içinde hangi turnuva ne zaman
# ============================================================

def grafik2(g):
    cg = g[g.gecis_tipi == "Clay→Grass"].copy()
    cg["konum"] = np.where(cg.blok_sira <= 2, "ilk2", "sonra")
    pay = pd.crosstab(cg.tourney_name, cg.konum, normalize="columns") * 100

    hiz = (g[g.surface == "Grass"].groupby("tourney_name")
             .agg(rpw=("rpw", "mean"), n=("rpw", "size")).query("n >= 100"))
    ortak = [t for t in hiz.index if t in pay.index]
    hiz = hiz.loc[ortak].sort_values("rpw")
    pay = pay.loc[hiz.index]

    fig = plt.figure(figsize=(13.5, 5.2))
    gs = gridspec.GridSpec(1, 2, width_ratios=[1.15, 1], wspace=0.32)
    y = np.arange(len(hiz))

    ax1 = fig.add_subplot(gs[0])
    ax1.barh(y - 0.2, pay["ilk2"], height=0.38, color=GRASS, label="Bloğun ilk 2 maçı")
    ax1.barh(y + 0.2, pay["sonra"], height=0.38, color="#C3D2C4", label="3. maç ve sonrası")
    ax1.set_yticks(y); ax1.set_yticklabels(hiz.index)
    ax1.set_xlabel("Çim bloğundaki maçların yüzdesi", fontsize=9)
    ax1.set_title("Çim sezonunun başında ve sonunda\nfarklı turnuvalar oynanıyor",
                  fontsize=10.5, loc="left", pad=12)
    ax1.legend(frameon=False, fontsize=8.8, loc="lower right")
    ax1.grid(axis="x", color="#EDF0F2", lw=0.8); ax1.set_axisbelow(True)

    ax2 = fig.add_subplot(gs[1])
    renkler = [VURGU if t in ("Stuttgart", "Halle", "'s-Hertogenbosch") else SOLUK
               for t in hiz.index]
    ax2.barh(y, hiz.rpw * 100, height=0.6, color=renkler)
    ax2.set_yticks(y); ax2.set_yticklabels([])
    ax2.set_xlim(30, 39)
    ax2.set_xlabel("Ortalama iade puanı kazanma (%)", fontsize=9)
    ax2.set_title("Ve o turnuvalar aynı hızda oynamıyor\n(kırmızı: sezon başı turnuvaları)",
                  fontsize=10.5, loc="left", pad=12)
    for i, (t, r) in enumerate(zip(hiz.index, hiz.rpw)):
        ax2.text(r * 100 + 0.12, i, f"{r*100:.1f}", va="center", fontsize=8.4, color="#5A6670")
    ax2.grid(axis="x", color="#EDF0F2", lw=0.8); ax2.set_axisbelow(True)

    fig.suptitle("Sahte bulgunun kaynağı: çim sezonu en hızlı kortlarda başlıyor, Wimbledon'da bitiyor.",
                 fontsize=13.5, x=0.011, ha="left", y=0.99, weight="bold")
    fig.text(0.011, 0.915,
             "Toprak→çim geçişi yapan 259 blok · Wimbledon maçlarının payı ilk 2 maçta %5, "
             "3. maçtan sonra %47 · ATP 2021–2025",
             fontsize=8.6, color="#6C7780")
    fig.subplots_adjust(left=0.13, right=0.98, top=0.80, bottom=0.11)
    fig.savefig(GRAFIK / "2_turnuva_kompozisyonu.png", dpi=200, bbox_inches="tight")
    print("  ✓ 2_turnuva_kompozisyonu.png")
    plt.close(fig)


# ============================================================
# GRAFİK 3 — Blok içi seyir: uyum eğrisi diye bir şey yok
# ============================================================

def grafik3(g):
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    for sut, ad, renk in [("z_iade_turn", "İade", NOTR), ("z_servis_turn", "Servis", SOLUK)]:
        xs, ort, lo, hi = [], [], [], []
        for i in range(1, 9):
            v = g.loc[g.blok_sira == i, sut].dropna().values
            if len(v) < 150:
                continue
            m, l, h = _ci(v)
            xs.append(i); ort.append(m); lo.append(l); hi.append(h)
        ax.fill_between(xs, lo, hi, color=renk, alpha=0.13, lw=0)
        ax.plot(xs, ort, "-o", color=renk, lw=2.2, ms=6, mec="white", mew=1.3, label=ad)
        ax.annotate(ad, (xs[-1], ort[-1]), xytext=(9, 0), textcoords="offset points",
                    va="center", fontsize=10, color=renk, weight="bold")

    ax.axvspan(0.5, 2.5, color="#F0F3F5", zorder=0)
    ax.text(1.5, ax.get_ylim()[1] * 0.93, "uyum penceresi", ha="center",
            fontsize=8.6, color="#8A959D")
    ax.axhline(0, color="#98A3AB", lw=1, ls=(0, (4, 3)))
    ax.set_xlabel("Yeni zemin bloğundaki maç sırası", fontsize=9.5)
    ax.set_ylabel("Düzeltilmiş performans (standart sapma)", fontsize=9.5)
    ax.set_xticks(range(1, 9))
    ax.grid(axis="y", color="#EDF0F2", lw=0.8); ax.set_axisbelow(True)

    fig.suptitle("Gerçek bir uyum eğrisi olsaydı, çizgi soldan sağa yükselirdi. Yükselmiyor.",
                 fontsize=13, x=0.011, ha="left", y=0.99, weight="bold")
    fig.text(0.011, 0.915,
             "Turnuva kontrollü performans · 1.441 blok · gölgeli alan %95 güven aralığı · ATP 2021–2025",
             fontsize=8.6, color="#6C7780")
    fig.tight_layout(rect=[0, 0, 1, 0.89])
    fig.savefig(GRAFIK / "3_blok_ici_seyir.png", dpi=200, bbox_inches="tight")
    print("  ✓ 3_blok_ici_seyir.png")
    plt.close(fig)


# ============================================================
# GRAFİK 4 — Blok algoritması tenis takvimini yeniden üretiyor
# ============================================================

def grafik4(d, oyuncular=("Carlos Alcaraz", "Novak Djokovic", "Alexander Zverev"), yil=2024):
    import matplotlib.dates as mdates
    from matplotlib.patches import Patch

    fig, ax = plt.subplots(figsize=(12.5, 4.4))

    for i, oy in enumerate(oyuncular):
        a = d[(d.oyuncu_ad == oy) & (d.yil == yil)]
        for _, gr in a.groupby("blok_id"):
            bas = gr.tarih.min()
            bit = gr.tarih.max() + pd.Timedelta(days=7)   # turnuva ~1 hafta sürer
            ax.barh(i, bit - bas, left=bas, height=0.44,
                    color=ZEMIN_RENK[gr.surface.iloc[0]],
                    edgecolor="white", linewidth=1.4)
            n = int(gr.blok_boy.iloc[0])
            if (bit - bas).days >= 21:
                ax.text(bas + (bit - bas) / 2, i, str(n), ha="center", va="center",
                        color="white", fontsize=9, weight="bold")

    ax.set_xlim(pd.Timestamp(f"{yil}-01-01"), pd.Timestamp(f"{yil}-12-15"))
    ax.set_ylim(len(oyuncular) - 0.5, -0.6)
    ax.set_yticks(range(len(oyuncular)))
    ax.set_yticklabels([o.split()[-1] for o in oyuncular], fontsize=11)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.grid(axis="x", color="#EDF0F2", lw=0.8)
    ax.set_axisbelow(True)

    ax.legend(handles=[Patch(facecolor=CLAY, label="Toprak"),
                       Patch(facecolor=GRASS, label="Çim"),
                       Patch(facecolor=HARD, label="Sert")],
              frameon=False, ncol=3, fontsize=9.5,
              loc="upper center", bbox_to_anchor=(0.5, 1.13))

    fig.suptitle("Algoritmaya tek bir turnuva adı vermedim. Tenis takvimini kendi buldu.",
                 fontsize=13, x=0.011, ha="left", y=0.99, weight="bold")
    fig.text(0.011, 0.90,
             f"{yil} sezonu · her kutu bir “zemin bloğu”, içindeki sayı o bloktaki maç sayısı · "
             "kural: zemin değişince yeni blok başlar",
             fontsize=8.6, color="#6C7780")
    fig.tight_layout(rect=[0, 0, 1, 0.85])
    fig.savefig(GRAFIK / "4_sezon_takvimi.png", dpi=200, bbox_inches="tight")
    print("  ✓ 4_sezon_takvimi.png")
    plt.close(fig)


# ============================================================
# YARDIMCI — tüm blokları kur (grafik 4 filtrelenmemiş veri ister)
# ============================================================

def tum_bloklar(d, maks_bosluk=60):
    d = d.sort_values(["oyuncu_id", "tarih", "tur_sira", "match_num"]).reset_index(drop=True)
    zd = d.surface != d.groupby("oyuncu_id").surface.shift()
    ua = d.groupby("oyuncu_id").tarih.diff().dt.days > maks_bosluk
    yo = d.oyuncu_id != d.oyuncu_id.shift()
    d["blok_id"] = (zd | ua | yo).cumsum()
    d["blok_sira"] = d.groupby("blok_id").cumcount() + 1
    d["blok_boy"] = d.groupby("blok_id").blok_sira.transform("max")
    return d


if __name__ == "__main__":
    print("[8] Grafikler")
    g = pd.read_parquet(VERI / "atp_bloklar.parquet")
    grafik1(g)
    grafik2(g)
    grafik3(g)

    hepsi = tum_bloklar(pd.read_parquet(VERI / "atp_rezidu.parquet"))
    grafik4(hepsi)