#!/usr/bin/env python3
"""AFIP Homologation Test Script.

Exercises the full AFIP electronic billing flow against the homologation
(test) environment without needing the database or web server running.

Commands:
  test  - Run the full 4-step homologation test (default)
  list  - List all previously authorized receipts

Usage:
  cd backend && PYTHONPATH=src .venv/bin/python ../scripts/test_afip_homo.py
  cd backend && PYTHONPATH=src .venv/bin/python ../scripts/test_afip_homo.py list
  cd backend && PYTHONPATH=src .venv/bin/python ../scripts/test_afip_homo.py list --cbte-tipo 1
"""

import argparse
import json
import os
import sys
import tempfile
import time
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path

MAX_AUTH_RETRIES = 3
AUTH_RETRY_DELAY = 5  # seconds
WSAA_REFRESH_BUFFER_MINUTES = 30
FALLBACK_RUNTIME_VALID_MINUTES = WSAA_REFRESH_BUFFER_MINUTES + 1
TA_CACHE_DIR = Path.home() / ".cache" / "elsabor"
TA_CACHE_FILE = TA_CACHE_DIR / "afip_wsaa_ta_cache.json"
TA_CACHE_FILE_LEGACY = Path(tempfile.gettempdir()) / "afip_wsaa_ta_cache.json"

CBTE_TIPO_NAMES = {
    1: "Factura A",
    2: "Nota de Débito A",
    3: "Nota de Crédito A",
    6: "Factura B",
    7: "Nota de Débito B",
    8: "Nota de Crédito B",
    11: "Factura C",
    12: "Nota de Débito C",
    13: "Nota de Crédito C",
}


def _load_cached_ta() -> dict | None:
    """Load a cached TA from disk if still valid."""
    if not TA_CACHE_FILE.exists():
        return None
    try:
        data = json.loads(TA_CACHE_FILE.read_text())
        expiration = _parse_expiration(data["expiration"])
        if datetime.now(UTC) < expiration:
            return data
    except Exception:
        pass
    return None


def _parse_expiration(expiration: str) -> datetime:
    parsed = datetime.fromisoformat(expiration)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _ensure_runtime_validity(expiration: datetime) -> datetime:
    """Keep fallback credentials usable for the first WSFE call in this run."""
    minimum_expiration = datetime.now(UTC) + timedelta(
        minutes=FALLBACK_RUNTIME_VALID_MINUTES
    )
    if expiration >= minimum_expiration:
        return expiration
    return minimum_expiration


def _load_cached_ta_ignore_expiry() -> dict | None:
    """Load a cached TA from disk ignoring local expiration.

    Searches the persistent path first, then the legacy /tmp/ path.
    Used as a fallback when AFIP says the TA is still valid but our
    local expiry check disagrees.
    """
    for path in (TA_CACHE_FILE, TA_CACHE_FILE_LEGACY):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
            token = data.get("token")
            sign = data.get("sign")
            expiration = data.get("expiration")
            if not (
                isinstance(token, str)
                and isinstance(sign, str)
                and isinstance(expiration, str)
            ):
                continue
            # Validate that expiration parses so fallback does not crash later.
            _parse_expiration(expiration)
            return {"token": token, "sign": sign, "expiration": expiration}
        except Exception:
            continue
    return None


def _is_ta_already_valid_fault(error_msg: str) -> bool:
    """Detect ARCA lockout fault text robustly across case/accents."""
    normalized = unicodedata.normalize("NFKD", error_msg.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return "ya posee un ta valido" in normalized


def _save_ta_cache(token: str, sign: str, expiration: str) -> None:
    """Save TA credentials to disk for reuse across runs."""
    TA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TA_CACHE_FILE.write_text(
        json.dumps({"token": token, "sign": sign, "expiration": expiration})
    )


def _authenticate() -> None:
    """Authenticate with WSAA, using disk cache when possible."""
    from bakery.services.afip_wsaa import WSAACredentials, wsaa_client

    cached = _load_cached_ta()
    if cached:
        print("  Using cached TA from disk")
        expiration = _parse_expiration(cached["expiration"])
        creds = WSAACredentials(
            token=cached["token"], sign=cached["sign"], expiration=expiration
        )
        wsaa_client._credentials = creds
    else:
        creds = None
        for attempt in range(1, MAX_AUTH_RETRIES + 1):
            try:
                wsaa_client.clear_cache()
                creds = wsaa_client.get_credentials()
                _save_ta_cache(creds.token, creds.sign, creds.expiration.isoformat())
                break
            except Exception as e:
                error_msg = str(e)
                if _is_ta_already_valid_fault(error_msg):
                    print(
                        "  ARCA says a valid TA already exists — checking local cache..."
                    )
                    cached = _load_cached_ta_ignore_expiry()
                    if cached:
                        print("  Found cached TA (ignoring local expiry)")
                        cached_expiration = _parse_expiration(cached["expiration"])
                        runtime_expiration = _ensure_runtime_validity(cached_expiration)
                        if runtime_expiration != cached_expiration:
                            print(
                                "  Reusing cached TA for this run despite local expiry"
                            )
                        creds = WSAACredentials(
                            token=cached["token"],
                            sign=cached["sign"],
                            expiration=runtime_expiration,
                        )
                        wsaa_client._credentials = creds
                        _save_ta_cache(
                            cached["token"], cached["sign"], cached["expiration"]
                        )
                        break
                    print(
                        "  ERROR: TA exists on ARCA but local cache is lost.\n"
                        "  Wait ~10 minutes (testing) or ~2 minutes (production) "
                        "and retry."
                    )
                    sys.exit(1)
                if attempt < MAX_AUTH_RETRIES:
                    print(f"  Attempt {attempt}/{MAX_AUTH_RETRIES} failed: {e}")
                    print(f"  Retrying in {AUTH_RETRY_DELAY}s...")
                    time.sleep(AUTH_RETRY_DELAY)
                else:
                    print(f"  FAIL after {MAX_AUTH_RETRIES} attempts: {e}")
                    sys.exit(1)

    print(f"  Authenticated (expires {creds.expiration})")


def _setup_settings(args: argparse.Namespace) -> None:
    """Configure AFIP settings from CLI args."""
    import base64

    os.environ["DATABASE_URL"] = "postgresql+psycopg://unused:unused@localhost/unused"
    os.environ["SECRET_KEY"] = "test-secret"

    from bakery.config import settings

    cert_bytes = Path(args.cert).read_bytes()
    key_bytes = Path(args.key).read_bytes()
    settings.afip_cert_content = base64.b64encode(cert_bytes).decode()
    settings.afip_key_content = base64.b64encode(key_bytes).decode()
    settings.afip_cuit = args.cuit
    settings.afip_punto_venta = args.punto_venta
    settings.afip_environment = args.environment


def cmd_list(args: argparse.Namespace) -> None:
    """List all authorized receipts for a given tipo and punto de venta."""
    _setup_settings(args)

    from bakery.services.afip_wsfe import wsfe_client

    cbte_tipo = args.cbte_tipo
    tipo_name = CBTE_TIPO_NAMES.get(cbte_tipo, f"Tipo {cbte_tipo}")
    pv = args.punto_venta

    print(f"Listing {tipo_name} (tipo={cbte_tipo}) at PV={pv}...")
    _authenticate()

    ultimo = wsfe_client.get_ultimo_comprobante(pv, cbte_tipo)
    if ultimo == 0:
        print(f"\nNo {tipo_name} receipts found.")
        return

    print(
        f"\n{'#':>5}  {'Fecha':<10}  {'Total':>10}  {'CAE':<16}  {'Vto CAE':<10}  Resultado"
    )
    print("-" * 75)

    for i in range(1, ultimo + 1):
        try:
            info = wsfe_client.consultar_comprobante(pv, cbte_tipo, i)
            fecha = info.cbte_fecha or ""
            if len(fecha) == 8:
                fecha = f"{fecha[:4]}-{fecha[4:6]}-{fecha[6:8]}"
            vto = info.cae_vto or ""
            if len(vto) == 8:
                vto = f"{vto[:4]}-{vto[4:6]}-{vto[6:8]}"
            print(
                f"{i:>5}  {fecha:<10}  ${info.imp_total:>9}  {info.cae or 'N/A':<16}  {vto:<10}  {info.resultado}"
            )
        except Exception as e:
            print(f"{i:>5}  ERROR: {e}")

    print(f"\nTotal: {ultimo} {tipo_name} receipt(s)")


def cmd_test(args: argparse.Namespace) -> None:
    """Run the full 4-step homologation test."""
    _setup_settings(args)

    from bakery.services.afip_wsfe import wsfe_client

    results: dict[str, bool] = {}
    cbte_tipo = 6  # Factura B

    print("=" * 60)
    print("AFIP Homologation Test")
    print("=" * 60)

    from bakery.config import settings

    print(f"  CUIT:          {args.cuit}")
    print(f"  Punto Venta:   {args.punto_venta}")
    print(f"  Environment:   {args.environment}")
    print(f"  Certificate:   {args.cert}")
    print(f"  WSAA URL:      {settings.afip_wsaa_url}")
    print(f"  WSFEv1 URL:    {settings.afip_wsfe_url}")
    print("=" * 60)

    # Step 1: WSAA Authentication
    print("\n[1/4] WSAA Authentication...")
    try:
        _authenticate()
        results["WSAA Auth"] = True
        print("  -> PASS")
    except SystemExit:
        results["WSAA Auth"] = False
        _print_summary(results)
        sys.exit(1)

    # Step 2: FECompUltimoAutorizado
    print(
        f"\n[2/4] FECompUltimoAutorizado (PV={args.punto_venta}, Tipo={cbte_tipo})..."
    )
    ultimo_cbte = 0
    try:
        ultimo_cbte = wsfe_client.get_ultimo_comprobante(args.punto_venta, cbte_tipo)
        print(f"  Last receipt: {ultimo_cbte}")
        results["FECompUltimoAutorizado"] = True
        print("  -> PASS")
    except Exception as e:
        print(f"  -> FAIL: {e}")
        results["FECompUltimoAutorizado"] = False
        _print_summary(results)
        sys.exit(1)

    # Step 3: FECAESolicitar
    next_cbte = ultimo_cbte + 1
    cbte_fecha = datetime.now().strftime("%Y%m%d")
    print(
        f"\n[3/4] FECAESolicitar (Factura B #{next_cbte}, total=$100, neto=$82.64, iva=$17.36, fecha={cbte_fecha})..."
    )
    cae_result = None
    try:
        cae_result = wsfe_client.solicitar_cae(
            punto_venta=args.punto_venta,
            cbte_tipo=cbte_tipo,
            cbte_desde=next_cbte,
            cbte_hasta=next_cbte,
            cbte_fecha=cbte_fecha,
            imp_total="100.00",
            imp_neto="82.64",  # 100 / 1.21
            imp_iva="17.36",  # 100 - 82.64
            doc_tipo=99,  # Consumidor final
            doc_nro="0",
            concepto=1,  # Productos
        )
        print(f"  Resultado:   {cae_result.resultado}")
        print(f"  CAE:         {cae_result.cae}")
        print(f"  CAE Vto:     {cae_result.cae_vto}")
        print(f"  Cbte Numero: {cae_result.cbte_numero}")
        if cae_result.observations:
            print(f"  Obs/Err:     {cae_result.observations}")
        approved = cae_result.resultado == "A" and cae_result.cae is not None
        results["FECAESolicitar"] = approved
        print(f"  -> {'PASS' if approved else 'FAIL'}")
    except Exception as e:
        print(f"  -> FAIL: {e}")
        results["FECAESolicitar"] = False
        _print_summary(results)
        sys.exit(1)

    # Step 4: FECompConsultar
    print(f"\n[4/4] FECompConsultar (receipt #{next_cbte})...")
    try:
        info = wsfe_client.consultar_comprobante(args.punto_venta, cbte_tipo, next_cbte)
        print(f"  Cbte Numero: {info.cbte_numero}")
        print(f"  Cbte Fecha:  {info.cbte_fecha}")
        print(f"  Imp Total:   {info.imp_total}")
        print(f"  CAE:         {info.cae}")
        print(f"  CAE Vto:     {info.cae_vto}")
        print(f"  Resultado:   {info.resultado}")

        # Verify CAE matches what we got from FECAESolicitar
        cae_matches = cae_result is not None and info.cae == cae_result.cae
        if cae_matches:
            print("  CAE matches FECAESolicitar -> OK")
        else:
            print(
                f"  CAE MISMATCH: solicitar={cae_result.cae if cae_result else 'N/A'}"
                f" vs consultar={info.cae}"
            )
        results["FECompConsultar"] = cae_matches
        print(f"  -> {'PASS' if cae_matches else 'FAIL'}")
    except Exception as e:
        print(f"  -> FAIL: {e}")
        results["FECompConsultar"] = False

    _print_summary(results)
    sys.exit(0 if all(results.values()) else 1)


def _print_summary(results: dict[str, bool]) -> None:
    """Print final pass/fail summary."""
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for step, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {step}")
    total = len(results)
    passed_count = sum(1 for v in results.values() if v)
    print(f"\n  {passed_count}/{total} steps passed")
    if passed_count == total:
        print("  All homologation tests passed!")
    else:
        print("  Some tests FAILED.")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="AFIP homologation test script")
    parser.add_argument(
        "--cert",
        default=os.path.expanduser("~/.ssh/dev_arca.cert"),
        help="Path to PEM certificate (default: ~/.ssh/dev_arca.cert)",
    )
    parser.add_argument(
        "--key",
        default=os.path.expanduser("~/.ssh/dev_arca.key"),
        help="Path to PEM private key (default: ~/.ssh/dev_arca.key)",
    )
    parser.add_argument(
        "--cuit",
        default="20144566395",
        help="CUIT number (default: 20144566395)",
    )
    parser.add_argument(
        "--punto-venta",
        type=int,
        default=1,
        help="Punto de venta (default: 1)",
    )
    parser.add_argument(
        "--environment",
        default="testing",
        choices=["testing", "production"],
        help="AFIP environment (default: testing)",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("test", help="Run the full homologation test (default)")

    list_parser = subparsers.add_parser("list", help="List authorized receipts")
    list_parser.add_argument(
        "--cbte-tipo",
        type=int,
        default=6,
        help="Receipt type: 1=Factura A, 6=Factura B (default: 6)",
    )

    args = parser.parse_args()

    # Validate cert/key exist
    if not os.path.isfile(args.cert):
        print(f"FAIL: Certificate not found: {args.cert}")
        sys.exit(1)
    if not os.path.isfile(args.key):
        print(f"FAIL: Private key not found: {args.key}")
        sys.exit(1)

    if args.command == "list":
        cmd_list(args)
    else:
        cmd_test(args)


if __name__ == "__main__":
    main()
