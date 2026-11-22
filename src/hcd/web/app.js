/* Phone-friendly lens-glint / IR detector. Default path runs in the browser. */
(() => {
  const $ = (id) => document.getElementById(id);
  const consent = $("consent");
  const app = $("app");
  const dock = $("dock");
  const video = $("video");
  const overlay = $("overlay");
  const statusEl = $("status");
  const hint = $("hint");
  const results = $("results");
  const startBtn = $("start");
  const torchBtn = $("torch");
  const useServer = $("use-server");

  let mode = "glint";
  let stream = null;
  let track = null;
  let running = false;
  let torchOn = false;
  let raf = 0;
  let work = document.createElement("canvas");
  let tracks = [];
  const PERSIST = 3;
  const MATCH = 16;

  $("agree").addEventListener("click", () => {
    consent.hidden = true;
    app.hidden = false;
    dock.hidden = false;
  });

  $("mode-glint").addEventListener("click", () => setMode("glint"));
  $("mode-ir").addEventListener("click", () => setMode("ir"));

  function setMode(next) {
    mode = next;
    $("mode-glint").setAttribute("aria-pressed", String(next === "glint"));
    $("mode-ir").setAttribute("aria-pressed", String(next === "ir"));
    tracks = [];
  }

  startBtn.addEventListener("click", async () => {
    if (running) {
      stopCamera();
      return;
    }
    await startCamera();
  });

  torchBtn.addEventListener("click", async () => {
    if (!track) return;
    try {
      torchOn = !torchOn;
      await track.applyConstraints({ advanced: [{ torch: torchOn }] });
      torchBtn.textContent = torchOn ? "Torch on" : "Torch";
    } catch (err) {
      torchOn = false;
      hint.textContent = "This browser cannot toggle the flashlight. Try Android Chrome, or use a separate light.";
      torchBtn.disabled = true;
    }
  });

  $("upload-image").addEventListener("change", (ev) => uploadFile(ev.target, "/v1/detect/image"));
  $("upload-video").addEventListener("change", (ev) => uploadFile(ev.target, "/v1/detect/video"));

  async function startCamera() {
    hint.textContent = "";
    if (!window.isSecureContext) {
      hint.textContent =
        "The camera needs a secure context. Open this page on https:// or localhost, or run hcd serve --https --host 0.0.0.0";
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
    } catch (err) {
      hint.textContent = "Could not open the camera: " + (err.message || err);
      return;
    }
    video.srcObject = stream;
    await video.play();
    track = stream.getVideoTracks()[0];
    const caps = track.getCapabilities ? track.getCapabilities() : {};
    torchBtn.disabled = !caps.torch;
    running = true;
    startBtn.textContent = "Stop";
    statusEl.textContent = mode === "ir" ? "IR mode" : "Glint mode";
    loop();
  }

  function stopCamera() {
    running = false;
    cancelAnimationFrame(raf);
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    track = null;
    torchOn = false;
    startBtn.textContent = "Start camera";
    torchBtn.disabled = true;
    torchBtn.textContent = "Torch";
    statusEl.textContent = "Camera idle";
    const ctx = overlay.getContext("2d");
    ctx && ctx.clearRect(0, 0, overlay.width, overlay.height);
  }

  async function loop() {
    if (!running) return;
    const detections = useServer.checked ? await detectOnServer() : detectInBrowser();
    draw(detections);
    renderList(detections);
    statusEl.textContent = `${mode === "ir" ? "IR" : "Glint"} · ${detections.length} stable hit${detections.length === 1 ? "" : "s"}`;
    raf = requestAnimationFrame(loop);
  }

  function detectInBrowser() {
    if (!video.videoWidth) return [];
    const scale = Math.min(1, 480 / video.videoWidth);
    const w = Math.max(1, Math.round(video.videoWidth * scale));
    const h = Math.max(1, Math.round(video.videoHeight * scale));
    work.width = w;
    work.height = h;
    const ctx = work.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(video, 0, 0, w, h);
    const image = ctx.getImageData(0, 0, w, h);
    const raw = mode === "ir" ? findIrDots(image) : findGlints(image);
    return stabilize(raw, w, h);
  }

  let serverBusy = false;
  let lastServer = [];
  async function detectOnServer() {
    if (!video.videoWidth) return lastServer;
    if (serverBusy) return lastServer;
    serverBusy = true;
    try {
      const w = Math.min(video.videoWidth, 640);
      const h = Math.round((w / video.videoWidth) * video.videoHeight);
      work.width = w;
      work.height = h;
      work.getContext("2d").drawImage(video, 0, 0, w, h);
      const blob = await new Promise((resolve) => work.toBlob(resolve, "image/jpeg", 0.7));
      const body = new FormData();
      body.append("file", blob, "frame.jpg");
      body.append("mode", mode);
      const res = await fetch("/v1/detect/image", { method: "POST", body });
      if (!res.ok) throw new Error(await res.text());
      const report = await res.json();
      lastServer = (report.detections || []).map((d) => ({
        x: d.x / report.width,
        y: d.y / report.height,
        radius: d.radius / report.width,
        score: d.score,
        kind: d.kind,
        frames_seen: d.frames_seen,
      }));
    } catch (err) {
      hint.textContent = "Server detect failed: " + (err.message || err);
    } finally {
      serverBusy = false;
    }
    return lastServer;
  }

  function findGlints(image) {
    const { width, height, data } = image;
    const gray = new Uint8ClampedArray(width * height);
    let sum = 0;
    for (let i = 0, p = 0; i < data.length; i += 4, p++) {
      const g = 0.114 * data[i] + 0.587 * data[i + 1] + 0.299 * data[i + 2];
      gray[p] = g;
    }
    const thresh = Math.max(220, percentile(gray, 0.997));
    return blobsFromMask(gray, width, height, (i) => gray[i] >= thresh, 200, 0.62, "glint");
  }

  function findIrDots(image) {
    const { width, height, data } = image;
    const gray = new Uint8ClampedArray(width * height);
    const mask = new Uint8Array(width * height);
    for (let i = 0, p = 0; i < data.length; i += 4, p++) {
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      gray[p] = 0.114 * b + 0.587 * g + 0.299 * r;
      const magenta = r > 150 && b > 150 && r + b > 2 * g + 30;
      const hot = r > 230 && b > 230 && g > 200;
      mask[p] = magenta || hot ? 1 : 0;
    }
    return blobsFromMask(gray, width, height, (i) => mask[i] === 1, 140, 0.5, "ir_dot");
  }

  function percentile(arr, q) {
    const hist = new Uint32Array(256);
    for (let i = 0; i < arr.length; i++) hist[arr[i]]++;
    const target = q * arr.length;
    let acc = 0;
    for (let v = 0; v < 256; v++) {
      acc += hist[v];
      if (acc >= target) return v;
    }
    return 255;
  }

  function blobsFromMask(gray, width, height, keep, minBright, minCirc, kind) {
    const seen = new Uint8Array(width * height);
    const maxArea = Math.max(6, 0.004 * width * height);
    const hits = [];
    const stack = [];
    for (let y = 1; y < height - 1; y++) {
      for (let x = 1; x < width - 1; x++) {
        const i = y * width + x;
        if (seen[i] || !keep(i)) continue;
        stack.length = 0;
        stack.push(i);
        seen[i] = 1;
        const pixels = [];
        while (stack.length) {
          const p = stack.pop();
          pixels.push(p);
          const px = p % width;
          const py = (p / width) | 0;
          for (let dy = -1; dy <= 1; dy++) {
            for (let dx = -1; dx <= 1; dx++) {
              const nx = px + dx;
              const ny = py + dy;
              if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
              const ni = ny * width + nx;
              if (seen[ni] || !keep(ni)) continue;
              seen[ni] = 1;
              stack.push(ni);
            }
          }
        }
        const area = pixels.length;
        if (area < 4 || area > maxArea) continue;
        let sx = 0, sy = 0, minX = width, minY = height, maxX = 0, maxY = 0, bright = 0;
        for (const p of pixels) {
          const px = p % width;
          const py = (p / width) | 0;
          sx += px;
          sy += py;
          bright += gray[p];
          if (px < minX) minX = px;
          if (py < minY) minY = py;
          if (px > maxX) maxX = px;
          if (py > maxY) maxY = py;
        }
        const bw = maxX - minX + 1;
        const bh = maxY - minY + 1;
        const aspect = Math.max(bw, bh) / Math.max(1, Math.min(bw, bh));
        if (aspect > 1.6) continue;
        const cx = sx / area;
        const cy = sy / area;
        let perimeter = 0;
        for (const p of pixels) {
          const px = p % width;
          const py = (p / width) | 0;
          if (
            !keep(py * width + px - 1) ||
            !keep(py * width + px + 1) ||
            !keep((py - 1) * width + px) ||
            !keep((py + 1) * width + px)
          ) {
            perimeter += 1;
          }
        }
        const circ = perimeter > 0 ? (4 * Math.PI * area) / (perimeter * perimeter) : 0;
        // Grid perimeter overestimates compared to OpenCV arcLength, so be slightly looser.
        if (circ < minCirc * 0.55) continue;
        const brightness = bright / area;
        if (brightness < minBright) continue;
        const radius = Math.max(Math.sqrt(area / Math.PI), Math.max(bw, bh) / 2);
        hits.push({
          x: cx / width,
          y: cy / height,
          radius: radius / width,
          score: Math.max(0, Math.min(1, 0.5 * circ + 0.5 * (brightness / 255))),
          kind,
          frames_seen: 1,
        });
      }
    }
    hits.sort((a, b) => b.score - a.score);
    return hits.slice(0, 20);
  }

  function stabilize(raw, width, height) {
    const next = [];
    const used = new Set();
    for (const hit of raw) {
      let best = -1;
      let bestD = MATCH / width;
      for (let i = 0; i < tracks.length; i++) {
        if (used.has(i)) continue;
        const d = Math.hypot(tracks[i].x - hit.x, tracks[i].y - hit.y);
        if (d <= bestD) {
          bestD = d;
          best = i;
        }
      }
      if (best < 0) {
        next.push({ ...hit, frames_seen: 1, fresh: true });
      } else {
        used.add(best);
        next.push({ ...hit, frames_seen: tracks[best].frames_seen + 1, fresh: true });
      }
    }
    tracks = next;
    return tracks.filter((t) => t.frames_seen >= PERSIST);
  }

  function draw(detections) {
    const w = overlay.width = video.clientWidth;
    const h = overlay.height = video.clientHeight;
    const ctx = overlay.getContext("2d");
    ctx.clearRect(0, 0, w, h);
    for (const det of detections) {
      const x = det.x * w;
      const y = det.y * h;
      const r = Math.max(10, det.radius * w + 6);
      ctx.strokeStyle = det.kind === "ir_dot" ? "#d46ec8" : "#e8a04a";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = ctx.strokeStyle;
      ctx.font = "14px system-ui, sans-serif";
      ctx.fillText(`${det.kind} ${det.score.toFixed(2)}`, x + r + 4, y - r);
    }
  }

  function renderList(detections) {
    results.innerHTML = detections
      .map(
        (d) =>
          `<li>${d.kind} score ${d.score.toFixed(2)} at ${(d.x * 100).toFixed(0)}%, ${(d.y * 100).toFixed(0)}% (seen ${d.frames_seen} frames)</li>`
      )
      .join("");
  }

  async function uploadFile(input, url) {
    const file = input.files && input.files[0];
    input.value = "";
    if (!file) return;
    hint.textContent = "Uploading…";
    const body = new FormData();
    body.append("file", file);
    body.append("mode", mode);
    body.append("annotate", "true");
    try {
      const res = await fetch(url, { method: "POST", body });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const imgUrl = URL.createObjectURL(blob);
      stopCamera();
      const ctx = overlay.getContext("2d");
      const img = new Image();
      img.onload = () => {
        overlay.width = overlay.clientWidth;
        overlay.height = overlay.clientHeight;
        ctx.drawImage(img, 0, 0, overlay.width, overlay.height);
        URL.revokeObjectURL(imgUrl);
      };
      img.src = imgUrl;
      // Also fetch JSON without annotate for the list. Re-upload is wasteful; parse is hard from PNG.
      // Do a second request without annotate for the numbers.
      const body2 = new FormData();
      body2.append("file", file);
      body2.append("mode", mode);
      const jsonRes = await fetch(url, { method: "POST", body: body2 });
      const report = await jsonRes.json();
      const dets = (report.detections || []).map((d) => ({
        x: d.x / report.width,
        y: d.y / report.height,
        radius: d.radius / report.width,
        score: d.score,
        kind: d.kind,
        frames_seen: d.frames_seen,
      }));
      renderList(dets);
      statusEl.textContent = `Upload · ${dets.length} detection${dets.length === 1 ? "" : "s"}`;
      hint.textContent = "Showing the annotated server result. The original file stayed on this machine’s server.";
    } catch (err) {
      hint.textContent = "Upload failed: " + (err.message || err);
    }
  }
})();
