#!/usr/bin/env python3
import argparse, os, re, sys, textwrap

VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "migrations", "versions")

# === Mapea IDs largos -> IDs cortos (<=32) ===
ID_MAP = {
    # 2025-10-22 (ya usamos estos más arriba; por si aparece de nuevo)
    "add_complex_photos_20251022": "cpx_photos_20251022",
    "add_beauty_center_photos_20251022": "bty_photos_20251022",
    "add_timeslot_beauty_fk_20251022": "bty_fk_20251022",

    # 2025-10-28 (de tu error log)
    "add_staff_and_timeslot_professional_20251028": "stp_20251028",
    "beauty_public_booking_toggle_20251028": "bpb_20251028",
    "complex_public_booking_toggle_20251028": "cpb_20251028",
    "field_public_booking_toggle_20251028": "fpb_20251028",
    "professional_booking_and_daily_availability_20251028": "pbda_20251028",
    "professional_public_booking_toggle_20251028": "ppb_20251028",

    # 2025-11-03
    "20251103_beauty_center_fixed_booking": "bcfb_20251103",
}

MAXLEN = 32
ASSIGN_RE = re.compile(
    r'^(\s*)(revision|down_revision)(\s*=\s*)(["\'])([^"\']+)(\4)(\s*)$',
    re.IGNORECASE,
)

def ensure_versions_dir():
    if not os.path.isdir(VERSIONS_DIR):
        print(f"[ERR] No existe: {VERSIONS_DIR}")
        sys.exit(2)

def rewrite_file(path, dry_run=False):
    changed = False
    out_lines = []
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    for i, line in enumerate(lines, start=1):
        m = ASSIGN_RE.match(line)
        if not m:
            out_lines.append(line)
            continue

        indent, key, eq, quote, val, _, tail = m.groups()
        new_val = ID_MAP.get(val, val)  # aplica mapping si existe

        # valida longitud
        if len(new_val) > MAXLEN:
            raise RuntimeError(
                f"{os.path.basename(path)}:{i} {key}='{new_val}' len={len(new_val)}>{MAXLEN}"
            )

        if new_val != val:
            changed = True
            print(f"[CHANGE] {os.path.basename(path)}:{i} {key}: '{val}' -> '{new_val}'")

        out_lines.append(f"{indent}{key}{eq}{quote}{new_val}{quote}{tail}\n")

    if changed and not dry_run:
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(out_lines)
    return changed

def main():
    ap = argparse.ArgumentParser(
        description="Fix Alembic revision/down_revision IDs to <=32 chars using a predefined map."
    )
    ap.add_argument("--dry-run", action="store_true", help="No escribe cambios, solo muestra")
    args = ap.parse_args()

    ensure_versions_dir()

    any_changed = False
    for fname in sorted(os.listdir(VERSIONS_DIR)):
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(VERSIONS_DIR, fname)
        try:
            changed = rewrite_file(fpath, dry_run=args.dry_run)
            any_changed = any_changed or changed
        except RuntimeError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)

    if not any_changed:
        print("[OK] No hubo cambios (ya estaba todo corregido o no aplicaba el map).")
    else:
        print("[OK] Reescritura completada." + (" (dry-run)" if args.dry_run else ""))

if __name__ == "__main__":
    main()
