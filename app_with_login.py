# app_with_login.py — Streamlit 1.50, autorefresh via plugin + ping síncrono estável
import json, platform, re, shutil, subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh  # plugin de auto-refresh

# =============== CONFIG ===============
st.set_page_config(page_title="Monitor de Impressoras", layout="wide")
DATA_PATH = Path("printers.json")

DEFAULT_PRINTERS = [
    {"ip": "192.168.1.10", "setor": "Recepção"},
    {"ip": "192.168.1.11", "setor": "Centro Cirúrgico"},
]

def now_str() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")

# =============== ESTILO ===============
SURFACE = "#0F1115"
CARD    = "#161A22"
BORDER  = "rgba(255,255,255,0.08)"
TEXT_MUTED = "rgba(255,255,255,0.72)"

st.markdown(
    f"""
    <style>
      .stApp, body {{ background:{SURFACE}; }}
      .block-container {{ padding-top: 1.2rem; padding-bottom: 1.6rem; }}

      .brand {{ display:flex; gap:18px; align-items:flex-start; flex-wrap:wrap; }}
      .brand h1 {{ margin:0; font-size:1.95rem; line-height:1.28; }}
      .brand p  {{ margin:.35rem 0 0; color:{TEXT_MUTED}; font-size:.98rem; line-height:1.35; }}

      .logo-box{{padding-top:10px;}}
      .logo-box img{{max-height:72px;width:auto;display:block;}}

      .kpi {{ background:{CARD}; border:1px solid {BORDER}; border-radius:14px; padding:14px; }}
      .kpi h3 {{ margin:0 0 6px 0; font-size:.85rem; color:{TEXT_MUTED}; letter-spacing:.02em; }}
      .kpi .value {{ font-size:1.6rem; font-weight:800; }}
      .box {{ background:{CARD}; border:1px solid {BORDER}; border-radius:14px; padding:12px; }}
      .box h3 {{ margin:0 0 8px 0; font-size:1rem; }}
      .chip {{ display:inline-flex; align-items:center; gap:.5rem; padding:.18rem .6rem; border-radius:999px;
               font-weight:700; font-size:.85rem; }}
      .chip.up   {{ background: rgba(34,197,94,.12); color:#22c55e; border:1px solid rgba(34,197,94,.35); }}
      .chip.down {{ background: rgba(239, 68, 68,.12); color:#ef4444; border:1px solid rgba(239, 68, 68,.35); }}

      .tblwrap {{ max-height: 520px; overflow:auto; border-radius:12px; border:1px solid {BORDER}; }}
      table.pretty {{ width:100%; border-collapse:separate; border-spacing:0; }}
      table.pretty thead th {{ position:sticky; top:0; z-index:1; background:{CARD};
                               text-transform:uppercase; font-size:.75rem; letter-spacing:.04em; color:{TEXT_MUTED};
                               padding:10px 12px; border-bottom:1px solid {BORDER}; }}
      table.pretty tbody td {{ padding:12px; border-bottom:1px solid {BORDER}; background:transparent; }}
      table.pretty tbody tr:nth-child(odd) td {{ background: rgba(255,255,255,0.02); }}
      table.pretty tbody tr:hover td {{ background: rgba(28,126,214,0.08); }}
      label, .stTextInput label {{ font-weight:600; color:{TEXT_MUTED}; }}
      div[data-baseweb="input"] input {{ height: 38px; }}
      button[kind="secondary"] {{ height:38px; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# =============== CABEÇALHO ===============
col1, col2 = st.columns([0.9, 7.1])
with col1:
    st.markdown('<div class="logo-box">', unsafe_allow_html=True)
    for path in ("static/logo.png", "logo.png"):
        try:
            st.image(path, width=118)
            break
        except Exception:
            pass
    st.markdown('</div>', unsafe_allow_html=True)
with col2:
    st.markdown(
        """
        <div class="brand">
          <div>
            <h1>Monitoramento de Impressoras - Rede</h1>
            <p>Atualização automática • dashboard corporativo</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# =============== ESTADO / PERSISTÊNCIA ===============
def load_printers():
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return DEFAULT_PRINTERS.copy()

def save_printers(data: List[dict]):
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

if "printers" not in st.session_state:
    st.session_state.printers = load_printers()

# =============== SIDEBAR — CONFIG (PERSISTENTE) ===============
st.sidebar.header("⚙️ Configuração")
st.session_state.setdefault("interval_s", 3)
st.session_state.setdefault("timeout_s", 1.0)

# Widgets COM key — o Streamlit persiste sozinho
st.sidebar.number_input("Intervalo entre pings (s)", min_value=1, step=1, key="interval_s")
st.sidebar.number_input("Timeout do ping (s)", min_value=0.2, step=0.1, format="%.1f", key="timeout_s")

# Valores atuais
interval_s = st.session_state["interval_s"]
timeout_s  = st.session_state["timeout_s"]

# 🔄 Autorefresh via plugin — key dinâmico “reseta” o timer quando o intervalo muda
interval_ms = int(interval_s * 1000)
st_autorefresh(interval=interval_ms, key=f"auto_refresh_{interval_ms}")

# =============== PING SÍNCRONO (CONFIÁVEL) ===============
@dataclass
class HostResult:
    ip: str
    up: bool
    when: str

def build_ping_cmd(ip: str, timeout_s: float):
    sysname = platform.system().lower()
    if sysname == "linux":
        return ["ping", "-c", "1", "-W", str(int(timeout_s)), ip]
    if sysname == "darwin":
        return ["ping", "-c", "1", "-W", str(int(timeout_s * 1000)), ip]
    if sysname.startswith("win"):
        return ["ping", "-n", "1", "-w", str(int(timeout_s * 1000)), ip]
    return ["ping", "-c", "1", ip]

def ping_one_sync(ip: str, timeout_s: float) -> HostResult:
    ts = now_str()
    if shutil.which("ping") is None:
        return HostResult(ip, False, ts)
    cmd = build_ping_cmd(ip, timeout_s)
    try:
        # stdout/stderr suprimidos, usamos apenas returncode
        rc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        return HostResult(ip, rc == 0, ts)
    except Exception:
        return HostResult(ip, False, ts)

def ping_many_sequencial(ips: List[str], timeout_s: float) -> List[HostResult]:
    return [ping_one_sync(ip, timeout_s) for ip in ips]

def is_valid_ipv4(ip: str) -> bool:
    return bool(re.match(r"^\s*(25[0-5]|2[0-4]\d|[01]?\d?\d)(\.(25[0-5]|2[0-4]\d|[01]?\d?\d)){3}\s*$", ip))

# =============== CADASTRO (todos podem editar) ===============
st.markdown('<div class="box"><h3>Cadastro de Impressoras</h3>', unsafe_allow_html=True)
cIP, cSetor, cAdd, cClear = st.columns([3, 2, 1, 1])
ip_input    = cIP.text_input("IP", placeholder="Ex.: 192.168.1.50")
setor_input = cSetor.text_input("Setor", placeholder="Ex.: Almoxarifado")
add         = cAdd.button("➕ Adicionar")
clear       = cClear.button("🗑️ Limpar")

if add:
    if not is_valid_ipv4(ip_input.strip()):
        st.error("IP inválido.")
    else:
        st.session_state.printers.append({"ip": ip_input.strip(), "setor": setor_input.strip()})
        save_printers(st.session_state.printers)
        st.success("Impressora adicionada.")

if clear:
    st.session_state.printers = []
    save_printers([])
    st.info("Lista esvaziada.")

if st.session_state.printers:
    ips_existentes = [f"{p['ip']} — {p['setor']}" for p in st.session_state.printers]
    cSel, cBtn = st.columns([5, 1])
    to_remove = cSel.selectbox("Remover", ["(selecionar)"] + ips_existentes, index=0)
    rm = cBtn.button("Remover", disabled=(to_remove == "(selecionar)"))
    if rm:
        idx = ips_existentes.index(to_remove)
        removed = st.session_state.printers.pop(idx)
        save_printers(st.session_state.printers)
        st.warning(f"Removido: {removed['ip']} — {removed['setor']}")
st.markdown('</div>', unsafe_allow_html=True)

# =============== DASHBOARD ===============
ips = [p["ip"] for p in st.session_state.printers]
setores_map = {p["ip"]: p["setor"] for p in st.session_state.printers}

if not ips:
    st.info("Adicione ao menos uma impressora para iniciar o monitoramento.")
    st.stop()

with st.spinner("Pingando impressoras..."):
    results = ping_many_sequencial(ips, timeout_s)

total = len(ips)
up_count = sum(1 for r in results if r.up)
down_count = total - up_count
now_fmt = now_str()

# KPIs
k1, k2, k3, k4 = st.columns(4)
with k1: st.markdown(f'<div class="kpi"><h3>Ativas (UP)</h3><div class="value">{up_count}</div></div>', unsafe_allow_html=True)
with k2: st.markdown(f'<div class="kpi"><h3>Inativas (DOWN)</h3><div class="value">{down_count}</div></div>', unsafe_allow_html=True)
with k3: st.markdown(f'<div class="kpi"><h3>Total</h3><div class="value">{total}</div></div>', unsafe_allow_html=True)
with k4: st.markdown(f'<div class="kpi"><h3>Última checagem</h3><div class="value">{now_fmt}</div></div>', unsafe_allow_html=True)

# Filtro rápido
st.text_input("🔎 Filtro (IP ou Setor)", key="quick_filter", placeholder="Ex.: 192.168.1.10 ou Recepção")

# Tabela
filtered = []
q = (st.session_state.quick_filter or "").strip().lower()
for r in sorted(results, key=lambda x: tuple(int(n) for n in x.ip.split(".")) if x.ip.count(".")==3 else x.ip):
    if q and not (q in r.ip.lower() or q in setores_map.get(r.ip, "").lower()):
        continue
    chip = '<span class="chip up">● Ativa</span>' if r.up else '<span class="chip down">● Offline</span>'
    filtered.append({"IP": r.ip, "Setor": setores_map.get(r.ip, ""), "Status": chip, "Checado às": r.when})

df = pd.DataFrame(filtered, columns=["IP","Setor","Status","Checado às"])
st.markdown("### Impressoras")
st.markdown(f'<div class="tblwrap">{df.to_html(escape=False, index=False, classes="pretty")}</div>', unsafe_allow_html=True)

# Exportar CSV
csv_bytes = df.assign(Status=df["Status"].str.replace(r"<.*?>","", regex=True)).to_csv(index=False).encode("utf-8")
st.download_button(
    "⬇️ Exportar CSV",
    data=csv_bytes,
    file_name=f"impressoras_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv",
)
