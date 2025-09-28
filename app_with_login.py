# app_with_login.py
import asyncio, json, os, platform, re, shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

# --------------------- CONFIG ---------------------
st.set_page_config(page_title="Monitor de Impressoras", page_icon="🖨️", layout="wide")

DATA_PATH = Path("printers.json")         # arquivo onde salvamos a lista
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")  # defina via variável de ambiente em produção
DEFAULT_PRINTERS = [
    {"ip": "192.168.1.10", "setor": "Recepção"},
    {"ip": "192.168.1.11", "setor": "Centro Cirúrgico"},
]

# --------------------- FUNÇÃO DE DATA/HORA PADRÃO ---------------------
def now_str():
    # formato BR (sem "T")
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")

# --------------------- PÁGINA / ESTILO ---------------------
st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
[data-testid="stMetricValue"] { font-weight: 700; }
.kpi {border-radius: 16px; padding: 14px 16px; border: 1px solid rgba(0,0,0,0.08);}
.kpi h3 {margin: 0 0 8px 0; font-size: 0.95rem; opacity: 0.85;}
.box {border: 1px solid rgba(0,0,0,0.08); border-radius: 16px; padding: 16px;}
thead tr th {text-transform: uppercase; font-size: 0.8rem; letter-spacing: .03em;}
</style>
""", unsafe_allow_html=True)

# --------------------- CABEÇALHO ---------------------
c0, c1 = st.columns([1, 6])
with c0:
    try:
        st.image("static/logo.png", use_container_width=True)  # ajuste o caminho se sua logo estiver em outro local
    except Exception:
        pass
with c1:
    st.title("🖨️ Monitor de Impressoras — Ping ICMP")
    st.caption("Ping periódico • somente admin pode editar a lista")

# --------------------- LOGIN BÁSICO ---------------------
st.sidebar.header("🔐 Acesso")
is_admin = False
if ADMIN_PASSWORD:
    typed = st.sidebar.text_input("Senha do admin", type="password")
    if typed and typed == ADMIN_PASSWORD:
        is_admin = True
        st.sidebar.success("Você está como ADMIN.")
    elif typed and typed != ADMIN_PASSWORD:
        st.sidebar.error("Senha incorreta.")
else:
    st.sidebar.info("Defina ADMIN_PASSWORD no ambiente para proteger a edição.")
    # sem senha definida → edição liberada
    is_admin = True

# --------------------- CARREGAR/SALVAR ---------------------
def load_printers():
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return DEFAULT_PRINTERS.copy()

def save_printers(data: List[dict]):
    try:
        DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        st.error(f"Falha ao salvar printers.json: {e}")

if "printers" not in st.session_state:
    st.session_state.printers = load_printers()

# --------------------- HELPERS DE PING ---------------------
@dataclass
class HostResult:
    ip: str
    up: bool
    when: str  # horário da rodada de ping

def build_ping_cmd(ip: str, timeout_s: float):
    sysname = platform.system().lower()
    if sysname == "linux":
        return ["ping", "-c", "1", "-W", str(int(timeout_s)), ip]
    elif sysname == "darwin":
        return ["ping", "-c", "1", "-W", str(int(timeout_s * 1000)), ip]
    elif sysname.startswith("win"):
        return ["ping", "-n", "1", "-w", str(int(timeout_s * 1000)), ip]
    return ["ping", "-c", "1", ip]

async def ping_one(ip: str, timeout_s: float) -> HostResult:
    if shutil.which("ping") is None:
        return HostResult(ip, False, now_str())
    cmd = build_ping_cmd(ip, timeout_s)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=timeout_s + 1.0)
        except asyncio.TimeoutError:
            proc.kill()
            return HostResult(ip, False, now_str())
        up = (proc.returncode == 0)
        return HostResult(ip, up, now_str())
    except Exception:
        return HostResult(ip, False, now_str())

async def ping_many(ips: List[str], timeout_s: float, concurrency: int) -> List[HostResult]:
    sem = asyncio.Semaphore(concurrency)
    async def wrapped(ip):
        async with sem:
            return await ping_one(ip, timeout_s)
    tasks = [wrapped(ip) for ip in ips]
    return await asyncio.gather(*tasks)

def is_valid_ipv4(ip: str) -> bool:
    return bool(re.match(r"^\s*(25[0-5]|2[0-4]\d|[01]?\d?\d)(\.(25[0-5]|2[0-4]\d|[01]?\d?\d)){3}\s*$", ip))

# --------------------- SIDEBAR (CONFIG) ---------------------
st.sidebar.header("⚙️ Configuração")
interval_ms = st.sidebar.number_input("Intervalo (ms)", min_value=500, step=500, value=3000)
timeout_s = st.sidebar.number_input("Timeout do ping (s)", min_value=0.2, step=0.1, value=1.0, format="%.1f")
concurrency = st.sidebar.number_input("Concorrência", min_value=1, max_value=1000, value=200, step=10)

# Auto-refresh via JavaScript (dispensa st_autorefresh)
st.markdown(
    f"""
    <script>
      setTimeout(function() {{
        window.location.reload();
      }}, {int(interval_ms)});
    </script>
    """,
    unsafe_allow_html=True
)

# --------------------- CADASTRO (somente admin) -------------
st.subheader("Cadastro de Impressoras")
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.2, 1.2])
    ip_input = c1.text_input("IP", placeholder="Ex.: 192.168.1.50", disabled=not is_admin)
    setor_input = c2.text_input("Setor", placeholder="Ex.: Almoxarifado", disabled=not is_admin)
    add_clicked = c3.button("➕ Adicionar", use_container_width=True, disabled=not is_admin)
    clear_clicked = c4.button("🗑️ Limpar lista", use_container_width=True, disabled=not is_admin)

    if add_clicked:
        if not ip_input.strip():
            st.warning("Informe o **IP**.")
        elif not is_valid_ipv4(ip_input.strip()):
            st.error("IP inválido. Ex.: 192.168.1.50")
        else:
            st.session_state.printers.append({"ip": ip_input.strip(), "setor": setor_input.strip()})
            save_printers(st.session_state.printers)
            st.success(f"Adicionado: {ip_input.strip()} — {setor_input.strip() or '(sem setor)'}")

    if clear_clicked:
        st.session_state.printers = []
        save_printers(st.session_state.printers)
        st.info("Lista de impressoras esvaziada.")

    if st.session_state.printers:
        ips_existentes = [f"{p['ip']} — {p['setor']}" for p in st.session_state.printers]
        col_rm1, col_rm2 = st.columns([6,1.2])
        to_remove = col_rm1.selectbox("Remover impressora", options=["(selecionar)"] + ips_existentes, index=0, disabled=not is_admin)
        if col_rm2.button("Remover", use_container_width=True, disabled=not is_admin):
            if to_remove != "(selecionar)":
                idx = ips_existentes.index(to_remove)
                removed = st.session_state.printers.pop(idx)
                save_printers(st.session_state.printers)
                st.warning(f"Removido: {removed['ip']} — {removed['setor']}")

# --------------------- PING + DASHBOARD ---------------------
ips = [p["ip"] for p in st.session_state.printers]
setores_map = {p["ip"]: p["setor"] for p in st.session_state.printers}

if not ips:
    st.stop()

with st.spinner("Pingando impressoras..."):
    results = asyncio.run(ping_many(ips, timeout_s, concurrency))

total = len(ips)
up_count = sum(1 for r in results if r.up)
down_count = total - up_count

k1, k2, k3, k4 = st.columns(4)
for col, title, val in [(k1,"Ativas (UP)",up_count),(k2,"Inativas (DOWN)",down_count),(k3,"Total",total)]:
    with col:
        st.markdown('<div class="kpi"><h3>'+title+'</h3>', unsafe_allow_html=True)
        st.metric(label="", value=val)
        st.markdown('</div>', unsafe_allow_html=True)
with k4:
    st.markdown('<div class="kpi"><h3>Última checagem</h3>', unsafe_allow_html=True)
    st.metric(label="", value=now_str())
    st.markdown('</div>', unsafe_allow_html=True)

rows = [{
    "IP": r.ip,
    "Setor": setores_map.get(r.ip, ""),
    "Status": "🟢 Online" if r.up else "🔴 Offline",
    "Checado às": now_str(),  # horário desta rodada
} for r in sorted(results, key=lambda x: tuple(int(n) for n in x.ip.split(".")) if x.ip.count(".")==3 else x.ip)]

df = pd.DataFrame(rows, columns=["IP","Setor","Status","Checado às"])
st.subheader("Impressoras")
st.dataframe(df, use_container_width=True, height=min(700, 40 + 35*max(1,len(df))))

st.caption("Somente o admin (senha correta) pode adicionar/remover. Outros acessos ficam em modo leitura.")
