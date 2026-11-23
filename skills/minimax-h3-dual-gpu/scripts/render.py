"""Render the reference MiniMax H3 clip on an isolated local Windows ComfyUI."""
import argparse
import csv
import ctypes
import json
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class MemoryStatus(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [
        (name, ctypes.c_uint64) for name in
        ("total", "available", "page", "free_page", "virtual", "free_virtual", "extended")
    ]


def system_used_mib():
    status = MemoryStatus()
    status.size = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError()
    return round((status.total - status.available) / 2**20, 2)


def api(port, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(f"http://127.0.0.1:{port}/{path}", data=data,
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(error.read().decode(errors="replace")) from error


def export_clip(source, video):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(source),
                    "-vf", "crop=1280:720:0:8", "-t", "5", "-c:v", "libx264",
                    "-crf", "17", "-preset", "fast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-movflags", "+faststart", str(video)], check=True)


def render(args):
    graph = json.loads(args.workflow.read_text(encoding="utf-8-sig"))
    if tuple(graph["5"]["inputs"][k] for k in ("width", "height", "length")) != (1280, 736, 124):
        raise ValueError("This export expects a 1280x736, 124-frame source.")
    root = args.output.resolve(strict=True)
    stem = "h3-dual-" + uuid.uuid4().hex[:12]
    graph["14"]["inputs"]["filename_prefix"] = stem + "-source"
    peaks = {}
    monitor_errors = []
    start = time.monotonic()
    gpu = subprocess.Popen(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu",
                            "--format=csv,noheader,nounits", "-lms", "250"],
                           stdout=subprocess.PIPE, text=True)

    def sample():
        try:
            with (root / (stem + ".csv")).open("x", newline="", buffering=1) as stream:
                writer = csv.writer(stream)
                writer.writerow(["elapsed_s", "gpu", "used_MiB", "util_pct", "system_used_MiB"])
                for line in gpu.stdout:
                    index, used, utilization = map(int, line.strip().split(","))
                    ram = system_used_mib()
                    writer.writerow([round(time.monotonic() - start, 3), index, used, utilization, ram])
                    key = f"gpu_{index}_MiB"
                    peaks[key] = max(peaks.get(key, 0), used)
                    peaks["system_MiB"] = max(peaks.get("system_MiB", 0), ram)
        except Exception as error:
            monitor_errors.append(str(error))

    thread = threading.Thread(target=sample)
    thread.start()
    receipt = {"graph": graph, "status": "pending"}
    metrics = root / (stem + ".json")
    try:
        identifier = api(args.port, "prompt", {"prompt": graph})["prompt_id"]
        receipt["prompt_id"] = identifier
        metrics.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(identifier, flush=True)
        while not (item := api(args.port, "history/" + identifier).get(identifier)):
            time.sleep(0.5)
        if item["status"]["status_str"] != "success":
            errors = [v.get("exception_message") for k, v in item["status"]["messages"]
                      if k == "execution_error"]
            receipt.update(status="execution_failed", errors=errors)
            raise RuntimeError(f"ComfyUI job failed: {errors}")
        media = item["outputs"]["14"]["images"][0]
        source = (root / media.get("subfolder", "") / media["filename"]).resolve(strict=True)
        if not source.is_relative_to(root):
            raise ValueError("Source outside the configured output directory")
        video = root / (stem + ".mp4")
        export_clip(source, video)
        receipt.update(status="rendered", video=video.name, wall_s=round(time.monotonic()-start, 2))
    finally:
        gpu.terminate()
        gpu.wait()
        thread.join()
        receipt.update(sampled_peaks=peaks, monitor_errors=monitor_errors)
        if receipt["status"] == "pending":
            receipt["status"] = "client_incomplete"
        metrics.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    if monitor_errors or not {"gpu_0_MiB", "gpu_1_MiB"} <= peaks.keys():
        raise RuntimeError(f"Incomplete telemetry; see {metrics}")
    print(metrics)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8199)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workflow", type=Path, default=Path(__file__).resolve().parents[1] /
                        "workflows" / "720p.json")
    render(parser.parse_args())
