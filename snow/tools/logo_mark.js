// Turns a resort's logo into the faint mark drawn behind its name on the Mountain tab (snow/logos/<key>.png).
//
//   node tools/logo_mark.js INPUT OUT.png [--crop x0,y0,x1,y1] [--mode auto|alpha|dark|light] [--preview FILE.png] [--name "Alta"]
//
// INPUT is a file or an https address: SVG, PNG, WebP, JPEG, GIF or ICO. The mark is the logo's shape alone, black
// with see-through, trimmed to its own edges and at most 320 px on its longer side; the page tints it. --crop keeps
// part of the picture, as fractions of its width and height (0,0,1,0.6 is the top three fifths), for a logo whose
// emblem sits beside or above its lettering. --mode says where the shape is:
//   alpha  the picture's own see-through (a logo on no background)
//   dark   a dark logo on a light background: the darker, the more solid
//   light  a light logo on a dark background
//   auto   alpha where the picture has see-through, else whichever of dark and light its corners point to
// --preview writes a picture of the mark as it sits in the header, stronger than the page shows it, to judge it by.
// Needs Node and Playwright with Chromium, which the cloud sessions have; nothing else. It asks only for INPUT.
const fs = require("fs");
const {chromium} = require("playwright");

const args = process.argv.slice(2);
const flag = (name, otherwise) => { const at = args.indexOf(`--${name}`); return at < 0 ? otherwise : args[at + 1]; };
const [input, output] = args.filter((a, n) => !a.startsWith("--") && !(args[n - 1] || "").startsWith("--"));
if (!input || !output) { console.error("usage: node tools/logo_mark.js INPUT OUT.png [--crop x0,y0,x1,y1] [--mode auto|alpha|dark|light] [--preview FILE.png] [--name NAME]"); process.exit(2); }
const crop = flag("crop", "0,0,1,1").split(",").map(Number), mode = flag("mode", "auto"), preview = flag("preview", null), name = flag("name", "Mountain");
const MIME = {svg: "image/svg+xml", png: "image/png", webp: "image/webp", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif", ico: "image/x-icon", avif: "image/avif"};
const AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36";

async function bytes() {
  if (!/^https?:/.test(input)) return {data: fs.readFileSync(input), type: null};
  const reply = await fetch(input, {headers: {"User-Agent": AGENT}});
  if (!reply.ok) throw new Error(`${reply.status} for ${input}`);
  return {data: Buffer.from(await reply.arrayBuffer()), type: (reply.headers.get("content-type") || "").split(";")[0]};
}

(async () => {
  const {data, type} = await bytes();
  const head = data.subarray(0, 400).toString("utf8");
  const ext = input.split("?")[0].split(".").pop().toLowerCase();
  const mime = /<svg|<\?xml/.test(head) ? MIME.svg : (type && type.startsWith("image/") ? type : MIME[ext] || "image/png");
  const browser = await chromium.launch();
  const page = await browser.newPage({viewport: {width: 420, height: 180}, deviceScaleFactor: 2});
  const made = await page.evaluate(async ({uri, crop, mode}) => {
    const img = new Image();
    await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = () => reject(new Error("the picture would not load")); img.src = uri; });
    // An SVG with no size of its own is drawn large; everything is drawn so its longer side is 1200 px.
    const w0 = img.naturalWidth || 600, h0 = img.naturalHeight || 600, scale = 1200 / Math.max(w0, h0);
    const W = Math.max(1, Math.round(w0 * scale)), H = Math.max(1, Math.round(h0 * scale));
    const canvas = Object.assign(document.createElement("canvas"), {width: W, height: H}), ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0, W, H);
    const px = ctx.getImageData(0, 0, W, H).data, n = W * H;
    let clear = 0;
    for (let i = 0; i < n; i++) if (px[i * 4 + 3] < 128) clear++;
    const lum = (i) => (0.299 * px[i * 4] + 0.587 * px[i * 4 + 1] + 0.114 * px[i * 4 + 2]) / 255;
    let used = mode;
    if (mode === "auto") {
      if (clear > n * 0.04) used = "alpha";
      else { const corners = [0, W - 1, (H - 1) * W, n - 1].map(lum); used = corners.reduce((a, b) => a + b) / 4 > 0.5 ? "dark" : "light"; }
    }
    const solid = new Float32Array(n);
    let most = 0;
    for (let i = 0; i < n; i++) {
      const a = px[i * 4 + 3] / 255;
      solid[i] = used === "alpha" ? a : used === "dark" ? a * (1 - lum(i)) : a * lum(i);
      if (solid[i] > most) most = solid[i];
    }
    const [fx0, fy0, fx1, fy1] = crop;
    const cx0 = Math.round(fx0 * W), cy0 = Math.round(fy0 * H), cx1 = Math.round(fx1 * W), cy1 = Math.round(fy1 * H);
    let x0 = W, y0 = H, x1 = -1, y1 = -1;
    for (let y = cy0; y < cy1; y++) for (let x = cx0; x < cx1; x++) if (solid[y * W + x] / (most || 1) > 0.08) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
    if (x1 < 0) throw new Error("nothing of the logo is in that part of the picture");
    const w = x1 - x0 + 1, h = y1 - y0 + 1, cut = Object.assign(document.createElement("canvas"), {width: w, height: h}), cutCtx = cut.getContext("2d");
    const out = cutCtx.createImageData(w, h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) out.data[(y * w + x) * 4 + 3] = Math.round(255 * Math.min(1, solid[(y + y0) * W + x + x0] / (most || 1)));
    cutCtx.putImageData(out, 0, 0);
    const fit = Math.min(1, 320 / Math.max(w, h)), last = Object.assign(document.createElement("canvas"), {width: Math.max(1, Math.round(w * fit)), height: Math.max(1, Math.round(h * fit))});
    const lastCtx = last.getContext("2d");
    lastCtx.imageSmoothingQuality = "high";
    lastCtx.drawImage(cut, 0, 0, last.width, last.height);
    return {uri: last.toDataURL("image/png"), width: last.width, height: last.height, mode: used, from: [w0, h0]};
  }, {uri: `data:${mime};base64,${data.toString("base64")}`, crop, mode});
  fs.writeFileSync(output, Buffer.from(made.uri.split(",")[1], "base64"));
  if (preview) {
    // The header as the page draws it, twice: at the page's strength, and three times as strong to see the shape.
    const card = (strength) => `<div style="position:relative;overflow:hidden;width:393px;height:129px;background:#fff;border-bottom:1px solid #dde2e8;font:650 26px/1.1 -apple-system,Inter,Helvetica,Arial,sans-serif;color:#0b2d63">
      <i style="position:absolute;left:-46px;top:-36px;width:220px;height:220px;background:#2a78d6;opacity:${strength};-webkit-mask:url(${made.uri}) center/contain no-repeat;mask:url(${made.uri}) center/contain no-repeat"></i>
      <span style="position:absolute;left:14px;top:22px">${name.replace(/[<&]/g, "")}</span><span style="position:absolute;left:14px;top:58px;font:400 13px sans-serif;color:#6b7480">Updated today 1:13 PM</span></div>`;
    await page.setViewportSize({width: 393, height: 262});
    await page.setContent(`<body style="margin:0">${card(0.11)}${card(0.34)}</body>`);
    await page.screenshot({path: preview});
  }
  await browser.close();
  console.log(`${output}: ${made.width}x${made.height}, read as ${made.mode}, from a picture ${made.from.join("x")}`);
})().catch((error) => { console.error(String(error.message || error)); process.exit(1); });
