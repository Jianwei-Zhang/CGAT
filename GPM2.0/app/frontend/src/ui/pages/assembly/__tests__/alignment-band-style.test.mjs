import test from "node:test";
import assert from "node:assert/strict";
import {
  readHitIdentityPct, resolveAlignmentBandStyle, resolveDarkAlignmentBandStyle, sortAlignmentBands,
  alignmentBandSvgAttrs, alignmentBandTooltipMetrics, renderAlignmentIdentityLegend,
} from "../alignment-band-style.js";
import { resolveHitIdentityPct } from "../track-render-geometry.js";

test("missing identity stays unknown, real zero survives, raw match counts remain compatible", () => {
  for (const identityPct of [undefined, null, "", " ", NaN, Infinity, "unknown"]) {
    assert.equal(readHitIdentityPct({ identityPct, mapq: 60 }), null);
  }
  assert.equal(readHitIdentityPct({ identityPct: 0 }), 0);
  assert.equal(readHitIdentityPct({ identity_pct: "93.27" }), 93.27);
  assert.equal(readHitIdentityPct({ match_length: 9327, block_length: 10000 }), 93.27);
  assert.equal(readHitIdentityPct({ matches: 0, blockLength: 100 }), 0);
  assert.equal(readHitIdentityPct({ matches: null, blockLength: 100 }), null);
  assert.equal(readHitIdentityPct({ matches: 100, blockLength: 0 }), null);
  assert.equal(resolveHitIdentityPct({}), 0, "zero threshold still includes unknown hits");
});

test("fixed continuous opaque scale preserves track hues and clamps only the color floor", () => {
  for (const tone of ["primary", "companion"]) {
    assert.deepEqual(resolveAlignmentBandStyle(tone, 0), resolveAlignmentBandStyle(tone, 80));
    const fills = [80, 85, 90, 93.27, 95, 100].map((identity) => resolveAlignmentBandStyle(tone, identity).fill);
    const channels = fills.map((fill) => fill.match(/\d+/g).map(Number));
    fills.forEach((fill) => assert.match(fill, /^rgb\(\d+, \d+, \d+\)$/));
    channels.slice(1).forEach((rgb, index) => rgb.forEach((channel, i) => assert.ok(channel < channels[index][i])));
    assert.notEqual(resolveAlignmentBandStyle(tone, null).fill, fills[0]);
  }
});

test("draw order is stable, high identity wins, filtering never rescales survivors or mutates source", () => {
  const hits = [{ key: "high", identityPct: 95 }, { key: "zero", identityPct: 0 },
    { key: "unknown" }, { key: "tie", identityPct: 95 }, { key: "low", identityPct: 85 }];
  const before = structuredClone(hits);
  assert.deepEqual(sortAlignmentBands(hits).map((hit) => hit.key), ["unknown", "zero", "low", "high", "tie"]);
  assert.deepEqual(hits, before);
  const originalAttrs = new Map(hits.map((hit) => [hit.key, alignmentBandSvgAttrs(hit, "companion")]));
  sortAlignmentBands(hits.filter((hit) => resolveHitIdentityPct(hit) >= 90)).forEach((hit) => {
    assert.equal(alignmentBandSvgAttrs(hit, "companion"), originalAttrs.get(hit.key));
  });
});

test("SVG export attributes and exact tooltip distinguish unknown from zero", () => {
  const attrs = alignmentBandSvgAttrs({ identityPct: 93.27 }, "primary");
  assert.ok(attrs.includes(`fill="${resolveAlignmentBandStyle("primary", 93.27).fill}"`));
  assert.match(attrs, /data-band-identity-pct="93.27"/);
  assert.match(alignmentBandSvgAttrs({}), /data-band-identity-pct=""/);
  assert.equal(alignmentBandTooltipMetrics({ identityPct: 93.27, alignLength: 10000 }), "Identity: 93.27% | Alignment length: 10,000 bp");
  assert.match(alignmentBandTooltipMetrics({ identityPct: 0 }), /^Identity: 0.00%/);
  assert.match(alignmentBandTooltipMetrics({ mapq: 60 }), /^Identity: Unknown/);
});


test("100 percent identity uses a softened opaque endpoint with a stronger but restrained outline", () => {
  for (const [tone,fill,stroke,oldBase] of [
    ["primary","rgb(148, 169, 197)","rgb(132, 157, 189)",[97,129,170]],
    ["companion","rgb(186, 167, 135)","rgb(176, 154, 117)",[154,126,78]],
  ]) {
    const style=resolveAlignmentBandStyle(tone,100);
    assert.deepEqual(style,{fill,stroke});
    const channels=style.fill.match(/\d+/g).map(Number);
    const outline=style.stroke.match(/\d+/g).map(Number);
    channels.forEach((channel,i)=>{assert.ok(channel>oldBase[i]);assert.ok(outline[i]<channel);});
    assert.deepEqual(resolveAlignmentBandStyle(tone,110),style);
    assert.notEqual(resolveAlignmentBandStyle(tone,99).fill,style.fill,"99 and 100 remain distinguishable");
    assert.equal(alignmentBandTooltipMetrics({identityPct:100}),"Identity: 100.00% | Alignment length: Unknown");
  }
});

test("legend endpoints stay identical to the main/local/export paint scale without rescaling identity", () => {
  const html=renderAlignmentIdentityLegend({},value=>value);
  // Swatches resolve the same endpoints through tokens, so the legend follows
  // the active theme without duplicating the paint scale.
  for (const tone of ["primary","companion"]) {
    assert.ok(html.includes(`linear-gradient(to right, var(--alignment-legend-${tone}-low), var(--alignment-legend-${tone}-high))`));
    assert.ok(alignmentBandSvgAttrs({identityPct:100},tone).includes(`fill="${resolveAlignmentBandStyle(tone,100).fill}"`));
  }
  assert.match(html,/≤80%/);assert.match(html,/100%/);assert.match(html,/softened/);
  assert.doesNotMatch(html,/rgba\(|opacity/);
});

test("dark band ramp keeps primary and companion hues apart and monotonic without alpha", () => {
  const levels=[0,80,85,90,95,100];
  const ramp=(tone)=>levels.map((identity)=>resolveDarkAlignmentBandStyle(tone,identity));
  for (const tone of ["primary","companion"]) {
    const styles=ramp(tone);
    styles.forEach(({fill,stroke})=>{
      assert.match(fill,/^rgb\(\d+, \d+, \d+\)$/);
      assert.match(stroke,/^rgb\(\d+, \d+, \d+\)$/);
    });
    assert.deepEqual(styles[0],styles[1],"unknown/<=80 share the darkest floor");
    const luminances=styles.slice(1).map(({fill})=>{
      const [r,g,b]=fill.match(/\d+/g).map(Number);
      return 0.2126*r+0.7152*g+0.0722*b;
    });
    luminances.slice(1).forEach((value,index)=>assert.ok(value>luminances[index],`${tone} ramp brightens with identity`));
    assert.notEqual(resolveDarkAlignmentBandStyle(tone,null).fill,styles[0].fill,"unknown is not a measured zero");
  }
  levels.forEach((identity)=>{
    const primary=resolveDarkAlignmentBandStyle("primary",identity).fill;
    const companion=resolveDarkAlignmentBandStyle("companion",identity).fill;
    assert.notEqual(primary,companion,`tone separation at identity ${identity}`);
    const [pr,pg,pb]=primary.match(/\d+/g).map(Number);
    const [cr,cg,cb]=companion.match(/\d+/g).map(Number);
    assert.ok(pb>cr,"primary stays bluer than companion at every level");
    assert.ok(cg>=pg-14,"companion stays warmer than primary at every level");
  });
  // The mounted dark ramp must stay below the pale light ramp so bars do not glow.
  for (const tone of ["primary","companion"]) {
    for (const identity of [80,100]) {
      const light=resolveAlignmentBandStyle(tone,identity).fill.match(/\d+/g).map(Number);
      const dark=resolveDarkAlignmentBandStyle(tone,identity).fill.match(/\d+/g).map(Number);
      assert.ok(dark.reduce((a,b)=>a+b,0)<light.reduce((a,b)=>a+b,0),
        `${tone} ${identity}% dark fill is deeper than the light fill`);
    }
  }
});

test("band svg attributes keep light export paint and carry the dark ramp as variables", () => {
  const attrs=alignmentBandSvgAttrs({identityPct:93.27},"primary");
  const light=resolveAlignmentBandStyle("primary",93.27);
  const dark=resolveDarkAlignmentBandStyle("primary",93.27);
  assert.ok(attrs.includes(`--alignment-band-fill:${light.fill};`));
  assert.ok(attrs.includes(`--alignment-band-dark-fill:${dark.fill};`));
  assert.ok(attrs.includes(`--alignment-band-dark-stroke:${dark.stroke}`));
  assert.doesNotMatch(attrs,/rgba\(/);
});
