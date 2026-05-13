#!/usr/bin/env python3
"""
Lab Tk-8 — Dashboard HMI Completo
Integra: Tkinter dark UI + matplotlib + pyserial + threading + CSV
MCU envía: 'N,temp,pres,hum,alt\n'  (CSV por UART)
Diseño basado en mockup de Figma (tema oscuro #1e2736)
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import serial, serial.tools.list_ports
import threading, queue, time, csv
from datetime import datetime
from collections import deque
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ── Paleta de colores (del diseño en Figma) ───────────────────
BG   = '#1e2736'; BG2  = '#0f172a'; BG3  = '#111827'
ACE  = '#2E75B6'; VRD  = '#22c55e'; RJO  = '#ef4444'
AMR  = '#fbbf24'; PRP  = '#a855f7'
T1   = '#e2e8f0'; T2   = '#94a3b8'; T3   = '#64748b'

# ═══════════════════════════════════════════════════════════════
# MODELO
# ═══════════════════════════════════════════════════════════════
class Modelo:
    N = 300
    def __init__(self):
        self.temp = self.pres = self.hum = self.alt = 0.0
        self.t_max = -999.0; self.t_min = 999.0; self.lecturas = 0
        self.umbral = 35.0; self.alarma = False; self.conectado = False
        self.h_temp = deque(maxlen=self.N)
        self.h_pres = deque(maxlen=self.N)
        self.h_hum  = deque(maxlen=self.N)
        self.q_datos = queue.Queue(maxsize=1000)
        self.q_log   = queue.Queue()

    def update(self, d):
        self.temp = d['temp']; self.pres = d['pres']
        self.hum  = d['hum'];  self.alt  = d['alt']
        self.lecturas += 1
        self.t_max = max(self.t_max, self.temp)
        self.t_min = min(self.t_min, self.temp)
        self.h_temp.append(self.temp)
        self.h_pres.append(self.pres)
        self.h_hum.append(self.hum)
        prev = self.alarma
        self.alarma = self.temp > self.umbral
        if self.alarma and not prev:
            ts = datetime.now().strftime('%H:%M:%S')
            self.q_log.put(('ALARMA', f'{ts}  ⚠ ALARMA T={self.temp:.1f}°C>{self.umbral:.1f}°C'))
        self.q_datos.put(True)

# ═══════════════════════════════════════════════════════════════
# HILO SERIAL (reutilizado del Lab Tk-7)
# ═══════════════════════════════════════════════════════════════
class HiloSerial(threading.Thread):
    def __init__(self, modelo):
        super().__init__(daemon=True)
        self.m = modelo; self.ser = None
        self.activo = threading.Event()

    def conectar(self, pto, baud):
        try:
            self.ser = serial.Serial(pto, baud, timeout=2)
            time.sleep(2); self.activo.set()
            self.m.conectado = True
            self.m.q_log.put(('INFO', f'{datetime.now():%H:%M:%S}  Conectado: {pto}@{baud}'))
            return True
        except serial.SerialException as e:
            self.m.q_log.put(('ERROR', str(e))); return False

    def desconectar(self):
        self.activo.clear(); self.m.conectado = False
        if self.ser and self.ser.is_open: self.ser.close()
        self.m.q_log.put(('INFO', f'{datetime.now():%H:%M:%S}  Desconectado'))

    def enviar(self, cmd):
        if self.ser and self.ser.is_open and self.activo.is_set():
            self.ser.write((cmd.strip()+'\n').encode())

    def run(self):
        while True:
            self.activo.wait()
            try:
                raw = self.ser.readline().decode('utf-8',errors='ignore').strip()
                if not raw or raw.startswith('#'): continue
                p = raw.split(',')
                if len(p) >= 4:
                    self.m.update({'temp':float(p[1]),'pres':float(p[2]),
                                   'hum':float(p[3]),'alt':float(p[4]) if len(p)>4 else 0.0})
            except: pass

# ═══════════════════════════════════════════════════════════════
# UI
# ═══════════════════════════════════════════════════════════════
class Dashboard:
    def __init__(self):
        self.m = Modelo()
        self.hilo = HiloSerial(self.m)
        self.hilo.start()
        self._csv_f = None; self._csv_w = None

        self.root = tk.Tk()
        self.root.title('Dashboard HMI — Interfaces y Puertos')
        self.root.geometry('1100x680')
        self.root.configure(bg=BG)
        self.root.protocol('WM_DELETE_WINDOW', self._cerrar)
        self._construir()
        self._poll()

    def _construir(self):
        # ── Barra superior ──────────────────────────────────────
        top = tk.Frame(self.root, bg=BG3, height=48)
        top.pack(fill=tk.X); top.pack_propagate(False)

        tk.Label(top, text='⚙  Dashboard HMI — Monitoreo de Proceso',
            bg=BG3, fg=T1, font=('Arial',12,'bold')
        ).pack(side=tk.LEFT, padx=14, pady=10)

        # Selector de puerto
        puertos = [p.device for p in serial.tools.list_ports.comports()]
        self.var_pto  = tk.StringVar(value=puertos[0] if puertos else '')
        self.var_baud = tk.StringVar(value='115200')
        for lbl, var, vals, w in [
            ('Puerto:', self.var_pto, puertos, 10),
            ('Baud:',   self.var_baud, ['9600','19200','57600','115200'], 8)]:
            tk.Label(top, text=lbl, bg=BG3, fg=T2, font=('Arial',9)).pack(side=tk.LEFT, padx=(10,2))
            ttk.Combobox(top, textvariable=var, values=vals, width=w).pack(side=tk.LEFT, pady=10)

        self.btn_cx = tk.Button(top, text='Conectar', command=self._conectar,
            bg=VRD, fg='white', font=('Arial',9,'bold'), relief=tk.FLAT, padx=12)
        self.btn_cx.pack(side=tk.LEFT, padx=8)

        self.btn_csv = tk.Button(top, text='📁 Exportar CSV', command=self._exportar,
            bg='#374151', fg=T1, font=('Arial',9), relief=tk.FLAT, padx=10)
        self.btn_csv.pack(side=tk.LEFT, padx=4)

        self.lbl_cx = tk.Label(top, text='● Desconectado', bg=BG3, fg=RJO, font=('Arial',9,'bold'))
        self.lbl_cx.pack(side=tk.LEFT, padx=8)

        self.lbl_n = tk.Label(top, text='N: 0', bg=BG3, fg=T3, font=('Arial',8))
        self.lbl_n.pack(side=tk.RIGHT, padx=14)

        # ── Área central ─────────────────────────────────────────
        centro = tk.Frame(self.root, bg=BG)
        centro.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        # ── Panel izquierdo: indicadores ─────────────────────────
        izq = tk.Frame(centro, bg=BG2, width=230)
        izq.pack(side=tk.LEFT, fill=tk.Y, padx=(0,4))
        izq.pack_propagate(False)

        self.ind = {}
        for key, nombre, uni, color in [
            ('temp','TEMPERATURA','°C',RJO),('pres','PRESIÓN','hPa',ACE),
            ('hum','HUMEDAD','%',VRD),('alt','ALTITUD','m',PRP)]:
            f = tk.Frame(izq, bg=BG2); f.pack(fill=tk.X, padx=10, pady=6)
            tk.Label(f,text=nombre,bg=BG2,fg=T2,font=('Arial',8)).pack(anchor='w')
            lbl=tk.Label(f,text=f'-- {uni}',bg=BG2,fg=color,font=('Courier New',20,'bold'))
            lbl.pack(anchor='w')
            self.ind[key] = (lbl, uni)

        # Estadísticas
        sep = tk.Frame(izq, bg='#374151', height=1); sep.pack(fill=tk.X, padx=10, pady=4)
        self.lbl_tmax = tk.Label(izq,text='Máx: --',bg=BG2,fg=AMR,font=('Arial',9))
        self.lbl_tmax.pack(anchor='w',padx=10)
        self.lbl_tmin = tk.Label(izq,text='Mín: --',bg=BG2,fg=ACE,font=('Arial',9))
        self.lbl_tmin.pack(anchor='w',padx=10)

        # Indicador LED de alarma en Canvas
        cv_alm = tk.Canvas(izq, width=210, height=50, bg=BG2, highlightthickness=0)
        cv_alm.pack(pady=10)
        self.oval_alm = cv_alm.create_oval(10,10,40,40, fill='#374151', outline='')
        self.txt_alm  = cv_alm.create_text(50,25,text='Sin alarma',
            fill=T3, font=('Arial',10,'bold'), anchor='w')
        self.cv_alm = cv_alm

        # ── Panel derecho: gráfica + control + log ───────────────
        der = tk.Frame(centro, bg=BG)
        der.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Gráfica
        self.fig = Figure(figsize=(8,3.5), dpi=90, facecolor=BG2)
        self.ax  = self.fig.add_subplot(111, facecolor='#111827')
        self.ax.tick_params(colors=T2,labelsize=7)
        self.ax.spines[:].set_color('#374151')
        self.ax.set_ylabel('Temperatura (°C)', color=RJO, fontsize=8)
        self.ax.grid(True,alpha=0.15,color='#374151')
        self.ax.set_title('Temperatura en tiempo real', color=T1, fontsize=8, pad=4)
        self.linea_t, = self.ax.plot([],[],RJO,lw=1.5,label='T°')
        self.linea_umb = self.ax.axhline(y=35,color=AMR,ls='--',lw=1,alpha=0.7,label='Umbral')
        self.ax.legend(loc='upper right',fontsize=7,facecolor=BG2,labelcolor=T1)
        self.fig.tight_layout()

        self.cv_fig = FigureCanvasTkAgg(self.fig, master=der)
        self.cv_fig.get_tk_widget().pack(fill=tk.X, padx=4, pady=4)

        # Panel de control
        ctrl = tk.Frame(der, bg=BG3)
        ctrl.pack(fill=tk.X, padx=4, pady=2)
        for txt, cmd in [('LED V ON','SET:LED:0:1'),('LED V OFF','SET:LED:0:0'),
                         ('LED R ON','SET:LED:1:1'),('LED R OFF','SET:LED:1:0'),
                         ('PING','PING')]:
            tk.Button(ctrl, text=txt, command=lambda c=cmd: self.hilo.enviar(c),
                bg='#1F4E79', fg='white', font=('Arial',8), relief=tk.FLAT,
                padx=8, pady=4).pack(side=tk.LEFT, padx=3, pady=6)
        tk.Label(ctrl, text='Umbral T°:', bg=BG3, fg=T2, font=('Arial',8)).pack(side=tk.LEFT, padx=(16,2))
        self.var_umb = tk.DoubleVar(value=35.0)
        tk.Scale(ctrl, variable=self.var_umb, from_=10, to=80, resolution=0.5,
            orient=tk.HORIZONTAL, bg=BG3, fg=T1, highlightthickness=0,
            troughcolor='#374151', length=120).pack(side=tk.LEFT)

        # Log
        self.log = scrolledtext.ScrolledText(der, height=5, bg='#0d1520',
            fg=T3, font=('Courier New',8), relief=tk.FLAT, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True, padx=4, pady=(2,4))
        self.log.tag_config('ALARMA',foreground=RJO)
        self.log.tag_config('INFO',  foreground=VRD)
        self.log.tag_config('ERROR', foreground=AMR)

    # ── Polling: leer colas y actualizar UI ─────────────────────
    def _poll(self):
        m = self.m
        m.umbral = self.var_umb.get()

        # Eventos de log
        while not m.q_log.empty():
            nivel, txt = m.q_log.get_nowait()
            self.log.config(state=tk.NORMAL)
            self.log.insert(tk.END, txt+'\n', nivel)
            self.log.see(tk.END)
            self.log.config(state=tk.DISABLED)
            if 'Conectado' in txt and nivel=='INFO':
                self.lbl_cx.config(text='● Conectado', fg=VRD)
                self.btn_cx.config(text='Desconectar', bg=RJO)
            elif 'Desconectado' in txt:
                self.lbl_cx.config(text='● Desconectado', fg=RJO)
                self.btn_cx.config(text='Conectar', bg=VRD)

        # Datos nuevos
        if not m.q_datos.empty():
            while not m.q_datos.empty(): m.q_datos.get_nowait()
            for key,(lbl,uni) in self.ind.items():
                val = getattr(m, key)
                lbl.config(text=f'{val:.2f} {uni}')
            self.lbl_n.config(text=f'N: {m.lecturas}')
            self.lbl_tmax.config(text=f'Máx: {m.t_max:.1f} °C')
            self.lbl_tmin.config(text=f'Mín: {m.t_min:.1f} °C')
            # Alarma
            if m.alarma:
                self.cv_alm.itemconfig(self.oval_alm, fill=RJO)
                self.cv_alm.itemconfig(self.txt_alm, text=f'⚠ ALARMA {m.temp:.1f}°C', fill=RJO)
            else:
                self.cv_alm.itemconfig(self.oval_alm, fill=VRD)
                self.cv_alm.itemconfig(self.txt_alm, text='✓ Normal', fill=VRD)
            # Gráfica
            datos = list(m.h_temp)
            self.linea_t.set_data(range(len(datos)), datos)
            self.linea_umb.set_ydata([m.umbral]*2)
            self.ax.set_xlim(0, max(len(datos),10))
            if datos:
                mg = max((max(datos)-min(datos))*0.15, 2)
                self.ax.set_ylim(min(datos)-mg, max(datos)+mg)
            self.cv_fig.draw_idle()
            # CSV log continuo
            if self._csv_w:
                self._csv_w.writerow([datetime.now().isoformat(timespec='s'),
                    m.temp,m.pres,m.hum,m.alt])
                self._csv_f.flush()

        self.root.after(100, self._poll)

    def _conectar(self):
        if self.m.conectado: self.hilo.desconectar()
        else: self.hilo.conectar(self.var_pto.get(), int(self.var_baud.get()))

    def _exportar(self):
        ruta = filedialog.asksaveasfilename(
            defaultextension='.csv', filetypes=[('CSV','*.csv')])
        if not ruta: return
        if self._csv_f: self._csv_f.close()
        self._csv_f = open(ruta, 'w', newline='')
        self._csv_w = csv.writer(self._csv_f)
        self._csv_w.writerow(['timestamp','temp_C','pres_hPa','hum_%','alt_m'])
        messagebox.showinfo('CSV', f'Guardando log en:\n{ruta}')

    def _cerrar(self):
        self.hilo.desconectar()
        if self._csv_f: self._csv_f.close()
        self.root.destroy()

    def run(self): self.root.mainloop()


if __name__ == '__main__':
    Dashboard().run()