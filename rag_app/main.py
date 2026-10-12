from contextlib import asynccontextmanager
from html import escape
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from rag_app.config import ROOT, Settings
from rag_app.domain import ChatRequest, ChatResponse, FeedbackRequest
from rag_app.ingestion import load_manifest
from rag_app.provider import ProviderFailure, create_provider
from rag_app.security import RateLimiter, identity
from rag_app.service import ChatService
from rag_app.store import Store


def create_app(settings: Settings | None = None, provider=None):
    settings = settings or Settings()
    store = Store(settings.storage_dir / "rag.sqlite3")
    provider = provider or (create_provider(settings) if settings.has_key else None)
    service = ChatService(settings, store, provider)
    limiter = RateLimiter(settings.rate_limit_per_minute)

    @asynccontextmanager
    async def lifespan(app):
        store.purge_history(settings.history_retention_days)
        yield
        if provider and hasattr(provider, "close"):
            provider.close()

    app = FastAPI(
        title="DATN — Chatbot giáo dục dinh dưỡng",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.store = store
    app.state.service = service

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # Origin check helps prevent cross-site paid requests. Production also requires JWT.
        origin = request.headers.get("origin")
        if (
            request.method in {"POST", "DELETE"}
            and origin
            and origin != str(request.base_url).rstrip("/")
        ):
            return JSONResponse({"detail": "Origin không được phép"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = str(uuid4())
        return response

    def current_owner(request: Request, response: Response):
        owner = identity(request, response, settings)
        store.purge_history(settings.history_retention_days)
        return owner

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "nutrition-rag", "version": "0.1.0"}

    @app.get("/api/status")
    def status():
        chunks, _, metadata = store.load_index()
        return {
            "index_ready": bool(chunks),
            "index_mode": metadata.get("mode", "missing"),
            "chunk_count": len(chunks),
            "answer_mode": settings.answer_mode,
            "provider_configured": settings.has_key,
            "openai_configured": bool(settings.openai_api_key.get_secret_value()),
            "gemini_configured": bool(settings.gemini_api_key.get_secret_value()),
            "model": settings.active_model,
            "embedding_model": settings.active_embedding_model,
            "always_real_api": False,
            "knowledge_uses_real_api": True,
            "safety_requires_provider": False,
            "app_env": settings.app_env,
            "food_service_connected": service.foods.status()['ready'],
            "food_catalog": service.foods.status(),
            'supplement_catalog':service.supplements.status(),
            "menu_service_connected": False,
            "history_retention_days": settings.history_retention_days,
        }

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(body: ChatRequest, request: Request, owner: str = Depends(current_owner)):
        limiter.check(owner)
        # Anonymous cookies can be reset: additionally limit by network address.
        limiter.check("ip:" + (request.client.host if request.client else "unknown"))
        try:
            return service.chat(body, owner)
        except PermissionError as error:
            raise HTTPException(404, "Không tìm thấy cuộc trò chuyện") from error
        except ProviderFailure as error:
            raise HTTPException(503, str(error)) from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.get("/api/documents")
    def documents():
        manifest = load_manifest(settings.source_manifest)
        return [
            {
                "id": s["id"],
                "title": s["title"],
                "year": s["year"],
                "enabled": s["enabled"],
                "role": s["role"],
                "reason": s.get("reason", ""),
                "warnings": s.get("warnings", []),
                "segments": s.get("segments", []),
                "format": s.get("format", "pdf"),
            }
            for s in manifest["sources"]
        ]

    @app.get("/api/documents/{source_id}/pdf")
    def document_pdf(source_id: str, owner: str = Depends(current_owner)):
        source = next(
            (
                s
                for s in load_manifest(settings.source_manifest)["sources"]
                if s["id"] == source_id and s.get("enabled")
            ),
            None,
        )
        if source is None:
            raise HTTPException(404, "Nguồn không được duyệt hoặc không tồn tại")
        if source.get("format", "pdf") != "pdf":
            raise HTTPException(404, "Nguồn này là DOCX; dùng bản xem trích đoạn")
        path = (ROOT / "data" / source["filename"]).resolve()
        if not path.is_relative_to((ROOT / "data").resolve()) or not path.is_file():
            raise HTTPException(404, "Không tìm thấy PDF")
        return FileResponse(path, media_type="application/pdf")

    @app.get('/api/foods')
    def food_search(q: str = Query(default='',max_length=200), dataset: str = 'auto',
                    limit: int = Query(default=20,ge=1,le=100),
                    offset: int = Query(default=0,ge=0,le=100000), owner: str = Depends(current_owner)):
        from rag_app.food_data import SOURCES
        if dataset not in {'auto',*SOURCES}:
            raise HTTPException(422,'Nguồn dữ liệu không hợp lệ')
        matches=service.foods.search(q,dataset,len(service.foods.records)) if q.strip() else [
            {**service.foods.get(r['id']),'match_score':None} for r in service.foods.records.values()
            if dataset=='auto' or r['dataset']==dataset]
        return {'catalog':service.foods.status(),'total':len(matches),'offset':offset,'limit':limit,'results':[
            {k:r[k] for k in ('id','name','name_en','dataset','basis','match_score')}
            for r in matches[offset:offset+limit]]}

    @app.get('/api/foods/{food_id}')
    def food_detail(food_id: str, owner: str = Depends(current_owner)):
        if food_id not in service.foods.records:
            raise HTTPException(404,'Không tìm thấy bản ghi thực phẩm')
        return service.foods.get(food_id)

    @app.get('/api/supplements')
    def supplement_search(q:str=Query(default='',max_length=200),domain:str='',
                          limit:int=Query(default=20,ge=1,le=100),offset:int=Query(default=0,ge=0,le=100000),
                          owner:str=Depends(current_owner)):
        if domain and domain not in {'label','portion','gi','yield','retention','recipe','carb_choice'}:
            raise HTTPException(422,'Nhóm dữ liệu bổ sung không hợp lệ')
        records=service.supplements.search(q,domain or None,len(service.supplements.records)) if q.strip() else [
            row for row in service.supplements.records.values() if not domain or row['domain']==domain]
        return {'catalog':service.supplements.status(),'total':len(records),'offset':offset,'limit':limit,
                'results':[{k:r[k] for k in ['id','domain','name','source_id','locator','calculation_enabled']}
                           for r in records[offset:offset+limit]]}

    @app.get('/api/supplements/{record_id}/preview',response_class=HTMLResponse)
    def supplement_preview(record_id:str,owner:str=Depends(current_owner)):
        from rag_app.supplements import render_reference
        record=service.supplements.records.get(record_id)
        if record is None:
            raise HTTPException(404,'Không tìm thấy bản ghi bổ sung')
        return render_reference(record)

    @app.get('/api/supplements/{record_id}')
    def supplement_detail(record_id:str,owner:str=Depends(current_owner)):
        record=service.supplements.records.get(record_id)
        if record is None:
            raise HTTPException(404,'Không tìm thấy bản ghi bổ sung')
        return record

    @app.get('/api/documents/{source_id}/original')
    def document_original(source_id:str,owner:str=Depends(current_owner)):
        source=next((s for s in load_manifest(settings.source_manifest)['sources']
                     if s['id']==source_id and s.get('enabled') and s.get('original_raw_file')),None)
        if source is None:
            raise HTTPException(404,'Không tìm thấy nguồn gốc được duyệt')
        base=ROOT/'data/collected/rag_supplements_2026-10-08'
        path=(base/source['original_raw_file']).resolve()
        if not path.is_relative_to(base.resolve()) or not path.is_file():
            raise HTTPException(404,'Không tìm thấy file nguồn gốc')
        return FileResponse(path,media_type='application/pdf' if path.suffix=='.pdf' else 'text/plain',filename=path.name)

    @app.get('/api/supplements/{record_id}/original')
    def supplement_original(record_id:str,owner:str=Depends(current_owner)):
        record=service.supplements.records.get(record_id)
        if record is None:
            raise HTTPException(404,'Không tìm thấy bản ghi bổ sung')
        source=service.supplements.manifest['sources'][record['source_id']]
        base=ROOT/'data/collected/rag_supplements_2026-10-08'
        path=(base/source['raw_file']).resolve()
        if not path.is_relative_to(base.resolve()) or not path.is_file():
            raise HTTPException(404,'Không tìm thấy file gốc')
        return FileResponse(path,media_type='application/pdf' if path.suffix=='.pdf' else 'text/plain',filename=path.name)

    @app.get('/api/foods/{food_id}/preview',response_class=HTMLResponse)
    def food_preview(food_id: str, owner: str = Depends(current_owner)):
        if food_id not in service.foods.records:
            raise HTTPException(404,'Không tìm thấy bản ghi thực phẩm')
        from rag_app.food_data import render_food
        return render_food(service.foods.get(food_id))

    @app.get("/api/documents/{source_id}/preview", response_class=HTMLResponse)
    def document_preview(source_id: str, owner: str = Depends(current_owner)):
        sources = load_manifest(settings.source_manifest)["sources"]
        source = next((s for s in sources if s["id"] == source_id and s.get("enabled")), None)
        chunks = [c for c in store.load_index()[0] if c.source_id == source_id]
        if source is None or not chunks:
            raise HTTPException(404, "Nguồn chưa được index hoặc không được duyệt")
        import re
        def locator_order(chunk):
            positions = [int(match.group()) for loc in chunk.locators
                         if (match := re.search(r'\d+', loc)) is not None]
            return (min(positions, default=0), chunk.id)

        chunks.sort(key=locator_order)
        body = "".join(f'<section id="chunk-{escape(c.id)}"><h2>{escape(c.section)}</h2>'
                       f'<p>Vị trí nguồn: {escape(", ".join(c.locators))}</p>'
                       f'<pre>{escape(c.text)}</pre></section>' for c in chunks)
        original_link=(f'<p><a href="/api/documents/{escape(source_id,quote=True)}/original">Tải bản nguồn gốc đã lưu</a></p>'
                       if source.get('original_raw_file') else '')
        return '<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đoạn nguồn đã index</title><link rel="stylesheet" href="/static/styles.css"><link rel="stylesheet" href="/static/source-preview.css"><body class="source-preview"><main><h1>' + escape(source["title"]) + '</h1><p>Đoạn nguồn chọn lọc; đối chiếu bản gốc. Vị trí p/t/r/c là phần tử DOCX; PDF page là trang file PDF; block là vị trí snapshot HTML.</p>' + original_link + body + '</main></body></html>'

    @app.get("/api/sessions")
    def sessions(owner: str = Depends(current_owner)):
        return store.sessions(owner)

    @app.get("/api/sessions/{session_id}")
    def history(session_id: UUID, owner: str = Depends(current_owner)):
        try:
            return store.history(owner, str(session_id))
        except PermissionError as error:
            raise HTTPException(404, "Không tìm thấy cuộc trò chuyện") from error

    @app.delete("/api/sessions/{session_id}", status_code=204)
    def delete_history(session_id: UUID, owner: str = Depends(current_owner)):
        if not store.delete_session(owner, str(session_id)):
            raise HTTPException(404, "Không tìm thấy cuộc trò chuyện")
        service.forget_session(owner, session_id)
        return Response(status_code=204)

    @app.post("/api/feedback", status_code=204)
    def feedback(body: FeedbackRequest, owner: str = Depends(current_owner)):
        if not store.feedback(owner, str(body.message_id), body.rating):
            raise HTTPException(404, "Chỉ phản hồi câu trả lời đã lưu thuộc người dùng")
        return Response(status_code=204)

    @app.get("/")
    def index():
        return FileResponse(ROOT / "web" / "index.html")

    @app.get("/docs", include_in_schema=False)
    def api_docs():
        return FileResponse(ROOT / "web" / "api.html")

    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
    return app
