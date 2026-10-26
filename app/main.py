import os
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.routes.auth_routes import router as auth_router
from app.routes.items_routes import router as items_router
from app.routes.registros_routes import router as registros_router
from app.routes.evidencias_routes import router as evidencias_router
from app.routes.consolidado_routes import router as consolidado_router
from app.routes.reportes_routes import router as reportes_router
from app.routes.sedes_routes import router as sedes_router
from app.routes.plan_anual_routes import router as plan_anual_router

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))

app = FastAPI(title="Sistema SG-SST API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en producción, restringir orígenes explícitamente
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Mantiene el mismo formato de error {"error": "..."} que ya usa el frontend ---
@app.exception_handler(HTTPException)
async def manejador_http_exception(request: Request, exc: HTTPException):
    detalle = exc.detail
    if isinstance(detalle, dict):
        return JSONResponse(status_code=exc.status_code, content=detalle)
    return JSONResponse(status_code=exc.status_code, content={"error": detalle})


@app.exception_handler(RequestValidationError)
async def manejador_validacion(request: Request, exc: RequestValidationError):
    primer_error = exc.errors()[0] if exc.errors() else {}
    campo = ".".join(str(p) for p in primer_error.get("loc", [])[1:])
    mensaje = f"Campo inválido: {campo}. {primer_error.get('msg', '')}" if campo else "Datos inválidos"
    return JSONResponse(status_code=400, content={"error": mensaje})


app.include_router(auth_router)
app.include_router(items_router)
app.include_router(registros_router)
app.include_router(evidencias_router)
app.include_router(consolidado_router)
app.include_router(reportes_router)
app.include_router(sedes_router)
app.include_router(plan_anual_router)

@app.get("/api/salud")
def salud():
    return {"estado": "ok", "servicio": "sgsst-api"}


# --- Sirve el frontend (equivalente a lo que hacía Flask con send_from_directory) ---
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=5000, reload=True)
