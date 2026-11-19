import asyncio
import io
import os
import traceback
from html import escape
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

import openpyxl
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether

from scraper import scrape_google_maps_sync

app = FastAPI(title="LeadHunter API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Thread pool para rodar o Playwright fora do event loop principal ───────────
_executor = ThreadPoolExecutor(max_workers=3)

# ── In-memory job store ────────────────────────────────────────────────────────
jobs: dict[str, dict] = {}


class SearchRequest(BaseModel):
    keyword: str
    location: str
    max_results: Optional[int] = 20


# ── Background worker (roda em thread separada) ────────────────────────────────
def _run_search_thread(job_id: str, keyword: str, location: str, max_results: int):
    """Executa o scraper síncrono em uma thread separada."""
    jobs[job_id]["status"] = "running"
    jobs[job_id]["message"] = f"Buscando '{keyword}' em {location}…"

    try:
        # Chama diretamente — scrape_google_maps_sync é 100% síncrono
        results = scrape_google_maps_sync(keyword, location, max_results)

        jobs[job_id]["status"] = "done"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["results"] = results
        jobs[job_id]["total"] = len(results)
        jobs[job_id]["message"] = f"{len(results)} leads encontrados!"
        print(f"[INFO] Job {job_id} concluído: {len(results)} resultados.")

    except Exception as e:
        err_msg = str(e) or type(e).__name__
        print(f"[ERROR] Job {job_id} falhou: {err_msg}")
        traceback.print_exc()
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = f"Erro: {err_msg}"
        jobs[job_id]["progress"] = 0


def _lead_list(lead: dict, *keys: str) -> list[str]:
    items: list[str] = []
    for key in keys:
        value = lead.get(key)
        if isinstance(value, list):
            source_values = value
        elif value:
            source_values = [value]
        else:
            source_values = []

        for item in source_values:
            text = str(item or "").strip()
            if text and text not in items:
                items.append(text)
    return items


def _build_pdf_response(results: list[dict], keyword: str, location: str, job_id: str):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "LeadPDFTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#111827"),
        spaceAfter=8,
        alignment=0, # Left align
    )
    subtitle_style = ParagraphStyle(
        "LeadPDFSubtitle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#4b5563"),
        spaceAfter=15,
    )
    label_style = ParagraphStyle(
        "LeadPDFLabel",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#4b5563"),
    )
    value_style = ParagraphStyle(
        "LeadPDFValue",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#111827"),
        wordWrap="CJK", # Allows breaking long URLs
    )
    section_style = ParagraphStyle(
        "LeadPDFSection",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=16,
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=0,
    )

    story = [
        Paragraph("LeadHunter - Relatório de Leads", title_style),
        Paragraph(
            f"Busca: <b>{escape(keyword)}</b> em <b>{escape(location)}</b> &nbsp;|&nbsp; Total: <b>{len(results)}</b> leads &nbsp;|&nbsp; Job: {escape(job_id)}",
            subtitle_style,
        ),
        Spacer(1, 10),
    ]

    # Available width is 297mm (A4 landscape) - 28mm (margins) = 269mm
    total_width = 269 * mm

    for idx, lead in enumerate(results, 1):
        phones = _lead_list(lead, "telefones", "phones", "telefone")
        websites = _lead_list(lead, "websites", "socials", "website")
        whatsapp = _lead_list(lead, "whatsapp")

        # HEADER TABLE
        header = Table(
            [[
                Paragraph(f"#{idx} - {escape(str(lead.get('nome') or 'Lead sem nome'))}", section_style),
                Paragraph(escape(str(lead.get("categoria") or "Categoria não informada")), label_style),
            ]],
            colWidths=[189 * mm, 80 * mm],
        )
        header.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef2ff")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#c7d2fe")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbeafe")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))

        # INFO TABLE
        info_table = Table(
            [
                [Paragraph("Avaliação", label_style), Paragraph(escape(str(lead.get("avaliacao") or "—")), value_style), Paragraph("Avaliações", label_style), Paragraph(escape(str(lead.get("total_avaliacoes") or "—")), value_style)],
                [Paragraph("Endereço", label_style), Paragraph(escape(str(lead.get("endereco") or "—")), value_style), Paragraph("Maps", label_style), Paragraph(f'<link href="{escape(str(lead.get("google_maps_url") or ""))}"><font color="blue"><u>Abrir link</u></font></link>' if lead.get("google_maps_url") else "—", value_style)],
            ],
            colWidths=[25 * mm, 109.5 * mm, 25 * mm, 109.5 * mm],
        )
        info_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))

        # CONTACTS TABLE
        contacts_text = ", ".join(escape(phone) for phone in phones) or "—"
        whatsapp_text = ", ".join(escape(item) for item in whatsapp) or "—"
        
        # Safe URL linking for websites
        website_links = []
        for site in websites:
            safe_site = escape(site)
            website_links.append(f'<link href="{safe_site}"><font color="blue"><u>{safe_site}</u></font></link>')
        websites_text = ", ".join(website_links) or "—"

        contacts_table = Table(
            [
                [Paragraph("Telefones", label_style), Paragraph(contacts_text, value_style)],
                [Paragraph("WhatsApp", label_style), Paragraph(whatsapp_text, value_style)],
                [Paragraph("Sites / Sociais", label_style), Paragraph(websites_text, value_style)],
            ],
            colWidths=[40 * mm, 229 * mm],
        )
        contacts_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafafa")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))

        # Use KeepTogether to ensure a lead is not split across pages if possible
        lead_block = KeepTogether([
            header,
            info_table,
            contacts_table,
            Spacer(1, 15),
        ])
        
        story.append(lead_block)

    doc.build(story)
    buffer.seek(0)

    filename = f"leads_{keyword}_{location}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf".replace(" ", "_")
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.post("/api/search")
async def start_search(req: SearchRequest):
    job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "progress": 5,
        "message": "Iniciando busca…",
        "results": [],
        "total": 0,
        "keyword": req.keyword,
        "location": req.location,
    }
    # Submete para o thread pool — não bloqueia o event loop do FastAPI
    _executor.submit(
        _run_search_thread, job_id, req.keyword, req.location, req.max_results
    )
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    job = jobs[job_id]

    # Incrementa progresso visual enquanto roda
    if job["status"] == "running" and job["progress"] < 90:
        job["progress"] = min(job["progress"] + 3, 90)

    return job


@app.get("/api/results/{job_id}")
async def get_results(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return jobs[job_id]


@app.get("/api/export/{job_id}")
async def export_excel(job_id: str):
    if job_id not in jobs or not jobs[job_id].get("results"):
        raise HTTPException(status_code=404, detail="Resultados não encontrados")

    results = jobs[job_id]["results"]
    keyword  = jobs[job_id].get("keyword", "leads")
    location = jobs[job_id].get("location", "")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leads"

    columns = [
        ("posicao",         "#"),
        ("nome",            "Nome"),
        ("categoria",       "Categoria"),
        ("avaliacao",       "⭐ Estrelas"),
        ("total_avaliacoes","Qtd. Avaliações"),
        ("telefones",       "Telefones"),
        ("whatsapp",        "WhatsApp"),
        ("websites",        "Websites"),
        ("endereco",        "Endereço"),
        ("google_maps_url", "Google Maps"),
    ]

    from openpyxl.styles import Font, PatternFill, Alignment
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill("solid", fgColor="1a1a2e")

    for col_idx, (key, label) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, lead in enumerate(results, 2):
        for col_idx, (key, _) in enumerate(columns, 1):
            val = lead.get(key, "")
            if isinstance(val, list):
                val = "\n".join(val)
            ws.cell(row=row_idx, column=col_idx, value=val)

    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

    ws.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = (
        f"leads_{keyword}_{location}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    ).replace(" ", "_")

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/export-pdf/{job_id}")
async def export_pdf(job_id: str):
    if job_id not in jobs or not jobs[job_id].get("results"):
        raise HTTPException(status_code=404, detail="Resultados não encontrados")

    results = jobs[job_id]["results"]
    keyword = jobs[job_id].get("keyword", "leads")
    location = jobs[job_id].get("location", "")
    return _build_pdf_response(results, keyword, location, job_id)


@app.get("/api/jobs")
async def list_jobs():
    return [
        {
            "job_id":   j["job_id"],
            "status":   j["status"],
            "keyword":  j.get("keyword"),
            "location": j.get("location"),
            "total":    j.get("total", 0),
            "message":  j.get("message"),
        }
        for j in reversed(list(jobs.values()))
    ]


# ── Serve static files ─────────────────────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
