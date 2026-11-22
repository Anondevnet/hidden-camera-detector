"""Command-line interface for `hcd`."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import cv2
import uvicorn

from hcd import __version__
from hcd.ble.scan import scan_ble, score_advertisements
from hcd.models import BleScanReport, NetworkScanReport, VisionReport
from hcd.network.scan import scan_network
from hcd.vendors import lookup_mac, registry_meta, vendor_records
from hcd.vision.annotate import annotate_frame
from hcd.vision.io import analyze_frames, analyze_image, iter_video_frames, load_image
from hcd.vision.synthetic import evaluate_synthetic, make_demo_image


def _dump(payload: object, as_json: bool) -> None:
    if as_json:
        if hasattr(payload, "model_dump"):
            print(json.dumps(payload.model_dump(), indent=2))
        else:
            print(json.dumps(payload, indent=2, default=str))
        return
    if isinstance(payload, NetworkScanReport):
        _print_network(payload)
    elif isinstance(payload, BleScanReport):
        _print_ble(payload)
    elif isinstance(payload, VisionReport):
        _print_vision(payload)
    else:
        print(payload)


def _print_network(report: NetworkScanReport) -> None:
    print(f"cidr: {report.cidr}  devices: {len(report.devices)}")
    if not report.devices:
        print("No neighbors found. Try without --no-sweep, or check you are on a LAN.")
        return
    for device in report.devices:
        identity = device.ip or "?"
        if device.mac:
            identity += f"  {device.mac}"
        vendor = f"  [{device.vendor_name}]" if device.vendor_name else ""
        print(f"  {device.score:3d} {device.likelihood.value:14s}  {identity}{vendor}")
        for reason in device.reasons:
            if reason.weight:
                print(f"       +{reason.weight:<3} {reason.detail}")
            else:
                print(f"           {reason.detail}")


def _print_ble(report: BleScanReport) -> None:
    print(f"ble devices: {len(report.devices)}")
    for device in report.devices:
        name = device.name or "(no name)"
        print(f"  {device.score:3d} {device.likelihood.value:14s}  {device.kind:8s}  {device.address}  {name}")
        for reason in device.reasons:
            print(f"       +{reason.weight:<3} {reason.detail}")


def _print_vision(report: VisionReport) -> None:
    print(
        f"mode={report.mode}  size={report.width}x{report.height}  "
        f"frames={report.frames}  detections={len(report.detections)}"
    )
    for det in report.detections:
        print(
            f"  {det.kind:6s}  score={det.score:.2f}  "
            f"@({det.x:.1f},{det.y:.1f}) r={det.radius:.1f}  "
            f"circ={det.circularity:.2f}  seen={det.frames_seen}"
        )


def _cmd_network(args: argparse.Namespace) -> int:
    report = scan_network(
        cidr=args.cidr,
        timeout=args.timeout,
        discovery_timeout=args.discovery_timeout,
        sweep=not args.no_sweep,
    )
    _dump(report, args.json)
    return 0


def _cmd_ble(args: argparse.Namespace) -> int:
    if args.from_json:
        rows = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        report = score_advertisements(rows)
    else:
        report = scan_ble(timeout=args.timeout)
    _dump(report, args.json)
    return 0


def _cmd_glint(args: argparse.Namespace) -> int:
    mode = "ir" if args.ir else "glint"
    if args.file:
        path = Path(args.file)
        suffix = path.suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            frame = load_image(path)
            report = analyze_image(frame, mode=mode)
            last = frame
        else:
            frames = iter_video_frames(str(path), max_frames=args.max_frames)
            report = analyze_frames(frames, mode=mode)
            last = frames[-1]
    else:
        frames = iter_video_frames(args.source, max_frames=args.max_frames)
        report = analyze_frames(frames, mode=mode)
        last = frames[-1]
    if args.out:
        annotated = annotate_frame(last, report.detections)
        if not cv2.imwrite(args.out, annotated):
            print(f"failed to write {args.out}", file=sys.stderr)
            return 1
        print(f"wrote {args.out}", file=sys.stderr)
    _dump(report, args.json)
    return 0


def _cmd_vendors(args: argparse.Namespace) -> int:
    if args.mac:
        hit = lookup_mac(args.mac)
        if hit is None:
            print("no bundled vendor match")
            return 1
        print(json.dumps(hit.__dict__, indent=2) if args.json else f"{hit.name} ({hit.role}) prefix={hit.prefix}")
        return 0
    if args.json:
        slim = [
            {"id": v["id"], "name": v["name"], "role": v["role"], "prefixes": len(v["prefixes"])}
            for v in vendor_records()
        ]
        print(json.dumps({"source": registry_meta(), "vendors": slim}, indent=2))
    else:
        meta = registry_meta()
        print(f"IEEE MA-L curated snapshot, retrieved {meta.get('retrieved')}")
        for vendor in vendor_records():
            print(f"  {vendor['name']:36s} {vendor['role']:12s} {len(vendor['prefixes']):4d} prefixes")
    return 0


def _self_signed_cert(directory: Path) -> tuple[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    cert = directory / "cert.pem"
    key = directory / "key.pem"
    if cert.is_file() and key.is_file():
        return str(cert), str(key)
    cmd = [
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-sha256",
        "-days",
        "7",
        "-nodes",
        "-subj",
        "/CN=hcd-local",
        "-addext",
        "subjectAltName=DNS:localhost,IP:127.0.0.1",
        "-keyout",
        str(key),
        "-out",
        str(cert),
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0 or not cert.is_file():
        raise RuntimeError(
            "Could not create a self-signed certificate. Install openssl or serve over HTTP on localhost.\n"
            + (result.stderr or result.stdout)
        )
    return str(cert), str(key)


def _cmd_serve(args: argparse.Namespace) -> int:
    if args.https:
        cert, key = _self_signed_cert(Path(args.tls_dir))
        scheme = "https"
    else:
        cert, key = None, None
        scheme = "http"
    print(
        f"Serving {scheme}://{args.host}:{args.port}/  "
        "(use HTTPS or localhost for the phone camera; accept the cert warning if self-signed)",
        file=sys.stderr,
    )
    uvicorn.run(
        "hcd.api:app",
        host=args.host,
        port=args.port,
        log_level="info",
        ssl_certfile=cert,
        ssl_keyfile=key,
    )
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    path, detections = make_demo_image(str(out))
    metrics = {key: value.as_dict() for key, value in evaluate_synthetic().items()}
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {report_path}", file=sys.stderr)
    print(f"wrote {path}  ({len(detections)} detections on the demo frame)", file=sys.stderr)
    print(json.dumps(metrics, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hcd",
        description="Hidden-camera detector: LAN, BLE, and lens-glint / IR cues. "
        "Only scan spaces and networks you are staying in or authorized to check.",
    )
    parser.add_argument("--version", action="version", version=f"hcd {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    net = sub.add_parser("network", help="Sweep the LAN for likely cameras")
    net.add_argument("--cidr", help="IPv4 CIDR (default: guessed /24 of this machine)")
    net.add_argument("--timeout", type=float, default=0.4, help="TCP connect timeout in seconds")
    net.add_argument("--discovery-timeout", type=float, default=2.0, help="ONVIF / mDNS / SSDP wait")
    net.add_argument("--no-sweep", action="store_true", help="Do not actively touch the subnet first")
    net.add_argument("--json", action="store_true")
    net.set_defaults(func=_cmd_network)

    ble = sub.add_parser("ble", help="Scan Bluetooth Low Energy advertisements")
    ble.add_argument("--timeout", type=float, default=8.0)
    ble.add_argument("--from-json", help="Score recorded advertisements instead of using the radio")
    ble.add_argument("--json", action="store_true")
    ble.set_defaults(func=_cmd_ble)

    glint = sub.add_parser("glint", help="Detect lens glints or IR dots in a camera or file")
    glint.add_argument("--source", type=int, default=0, help="Webcam index (default 0)")
    glint.add_argument("--file", help="Image or video file instead of a live camera")
    glint.add_argument("--ir", action="store_true", help="IR-dot mode instead of flashlight glint")
    glint.add_argument("--out", help="Write an annotated PNG of the last frame")
    glint.add_argument("--max-frames", type=int, default=60)
    glint.add_argument("--json", action="store_true")
    glint.set_defaults(func=_cmd_glint)

    serve = sub.add_parser("serve", help="Phone-friendly web UI and /v1/detect API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--https", action="store_true", help="Self-signed TLS so a phone can use getUserMedia")
    serve.add_argument("--tls-dir", default=".tls")
    serve.set_defaults(func=_cmd_serve)

    vendors = sub.add_parser("vendors", help="List bundled camera / IoT MAC OUI vendors")
    vendors.add_argument("--mac", help="Look up a single MAC address")
    vendors.add_argument("--json", action="store_true")
    vendors.set_defaults(func=_cmd_vendors)

    demo = sub.add_parser("demo", help="Render the synthetic demo image and fixture metrics")
    demo.add_argument("--out", default="docs/img/demo_glint.png")
    demo.add_argument("--report", default="docs/img/synthetic_metrics.json")
    demo.set_defaults(func=_cmd_demo)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
